"""M0 gateway tests (spec §2 acceptance, §5.4 CI). All offline via mock backend."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ds.agents.decide import OutMsg, ResidentDecision
from ds.eval.individual import empirical_prob
from ds.kernel.rng import derive, stream_rng, stream_seed
from ds.llm.backends import (
    BackendError,
    BackendFatalError,
    LLMResponse,
    LiteLLMBackend,
    MockBackend,
    is_fatal_provider_error,
    strip_reasoning_prefix,
)
from ds.llm.gateway import (
    BudgetExceeded,
    LLMBackendUnavailable,
    LLMCallFailed,
    LLMGateway,
)
from tests.conftest import XSchema, make_gateway


# a mock backend that always returns a fixed valid payload for XSchema
class ConstBackend:
    def __init__(self):
        self.calls = 0
        self.closes = 0

    async def acomplete(self, *, model_id, messages, temperature, seed, timeout,
                        schema=None, **kw):
        self.calls += 1
        return LLMResponse(content='{"x": 1}', prompt_tokens=10, completion_tokens=5)

    async def aclose(self):
        self.closes += 1


class CaptureSeedBackend(ConstBackend):
    def __init__(self):
        super().__init__()
        self.seeds = []

    async def acomplete(self, *, seed, **kwargs):
        self.seeds.append(seed)
        return await super().acomplete(seed=seed, **kwargs)


class FailBackend:
    def __init__(self):
        self.calls = 0

    async def acomplete(self, **kw):
        self.calls += 1
        raise BackendError("forced failure")


class FatalBackend:
    def __init__(self):
        self.calls = 0

    async def acomplete(self, **kw):
        self.calls += 1
        raise BackendFatalError("Insufficient Balance")


# a backend that returns broken JSON once, then valid (drives repair path)
class RepairBackend:
    def __init__(self):
        self.calls = 0
        self.message_batches = []

    async def acomplete(self, **kw):
        self.calls += 1
        self.message_batches.append(kw["messages"])
        if self.calls == 1:
            return LLMResponse(content="not json at all", prompt_tokens=10,
                               completion_tokens=5)
        return LLMResponse(content='{"x": 7}', prompt_tokens=10, completion_tokens=5)


# a backend whose action varies with the seed (drives empirical_prob test)
class SeedVaryingBackend:
    def __init__(self):
        self.seen_seeds = []

    async def acomplete(self, *, model_id, messages, temperature, seed, timeout,
                        schema=None, **kw):
        self.seen_seeds.append(seed)
        action = "evacuate" if seed % 2 == 0 else "stay"
        return LLMResponse(content=json.dumps({"action": action}),
                           prompt_tokens=5, completion_tokens=3)


class ActSchema(BaseModel):
    action: str


def test_provider_rendered_thinking_prefix_is_removed_before_json_parse():
    payload = '<think>private reasoning</think>\n{"x": 1}'
    assert strip_reasoning_prefix(payload) == '{"x": 1}'
    untouched = '{"assessment": "literal <think> marker"}'
    assert strip_reasoning_prefix(untouched) == untouched


async def test_litellm_tool_mode_forces_and_reads_schema_arguments(monkeypatch):
    captured = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        function = SimpleNamespace(arguments='{"x": 9}')
        message = SimpleNamespace(
            content="",
            tool_calls=[SimpleNamespace(function=function)],
            reasoning_content="private",
            reasoning_details=None,
        )
        choice = SimpleNamespace(message=message, finish_reason="tool_calls")
        return SimpleNamespace(
            choices=[choice],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            model="MiniMax/MiniMax-M2.7",
        )

    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(acompletion=fake_completion),
    )
    response = await LiteLLMBackend().acomplete(
        model_id="openai/MiniMax-M2.7",
        messages=[{"role": "user", "content": "Return JSON"}],
        temperature=0.0,
        seed=1,
        timeout=30,
        schema=XSchema,
        structured_output_mode="tool",
        response_format=None,
    )
    assert response.content == '{"x": 9}'
    assert captured["tool_choice"]["function"]["name"] == (
        "return_structured_decision"
    )
    assert captured["tools"][0]["function"]["parameters"]["required"] == ["x"]
    assert "response_format" not in captured


def test_empty_message_payload_normalizes_null_to_object():
    message = OutMsg(
        to="partner",
        content="I received the warning.",
        kind="notice",
        payload=None,
    )
    assert message.payload == {}


def test_resident_assessment_truncates_nonsemantic_overflow():
    decision = ResidentDecision(
        assessment="x" * 300,
        action="stay",
    )
    assert decision.assessment == "x" * 240


async def test_cache_hit(tmp_path):
    """Second identical call is served from cache: n_cache==1, no extra backend call."""
    be = ConstBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})
    msgs = [{"role": "user", "content": "give me x"}]
    a = await gw.complete(step=0, agent_id="t", model="mock", messages=msgs,
                          schema=XSchema, seed=1)
    b = await gw.complete(step=0, agent_id="t", model="mock", messages=msgs,
                          schema=XSchema, seed=1)
    assert a == b
    assert gw.n_cache == 1
    assert be.calls == 1  # backend hit exactly once
    stats = gw.stats()
    assert stats["live_prompt_tokens"] == 10
    assert stats["live_completion_tokens"] == 5
    assert stats["logical_prompt_tokens"] == 20
    assert stats["logical_completion_tokens"] == 10


async def test_async_close_closes_shared_backend_once(tmp_path):
    backend = ConstBackend()
    gw = make_gateway(
        tmp_path,
        backends={"mock": backend, "alias": backend},
    )
    await gw.aclose()
    await gw.aclose()
    assert backend.closes == 1
    assert gw._closed is True


async def test_fallback_detected(tmp_path):
    """Backend always fails -> every call raises LLMCallFailed, nothing swallowed."""
    be = FailBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})
    msgs = [{"role": "user", "content": "x"}]
    failures = 0
    for i in range(10):
        try:
            await gw.complete(step=i, agent_id="t", model="mock", messages=msgs,
                              schema=XSchema, seed=i)
        except LLMCallFailed:
            failures += 1
    assert failures == 10
    assert gw.n_failed == 10
    assert be.calls == 30  # 3 retries each, none silently succeeded


async def test_fatal_backend_access_error_is_not_retried(tmp_path):
    be = FatalBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})
    with pytest.raises(LLMBackendUnavailable, match="Insufficient Balance"):
        await gw.complete(
            step=0,
            agent_id="t",
            model="mock",
            messages=[{"role": "user", "content": "x"}],
            schema=XSchema,
            seed=1,
        )
    assert be.calls == 1
    assert gw.n_failed == 1
    gw.flush()
    records = [
        json.loads(line)
        for line in gw.log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[-1]["status"] == "fatal_backend_error"


def test_provider_fatal_error_classifier_is_narrow():
    assert is_fatal_provider_error("Insufficient Balance")
    assert is_fatal_provider_error("incorrect API key supplied")
    assert is_fatal_provider_error("'seed' must be Integer")
    assert not is_fatal_provider_error("request timed out")
    assert is_fatal_provider_error("用户额度不足, 剩余额度: -0.109176")
    assert is_fatal_provider_error("账户余额不足")
    assert not is_fatal_provider_error("Too many concurrent requests due to low balance")
    assert not is_fatal_provider_error("请求频率过高，请稍后重试")


async def test_chinese_provider_credit_error_stops_without_transport_retries(tmp_path, monkeypatch):
    calls = 0

    async def exhausted(**kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("用户额度不足, 剩余额度: -0.109176")

    monkeypatch.setitem(sys.modules, 'litellm', SimpleNamespace(acompletion=exhausted))
    gateway = make_gateway(tmp_path, backends={'mock': LiteLLMBackend()})
    try:
        with pytest.raises(LLMBackendUnavailable):
            await gateway.complete(step=25, agent_id='r', model='mock',
                                   messages=[], schema=XSchema, seed=7)
        assert calls == 1 and gateway.n_failed == 1
        assert gateway.n_fallback == gateway.n_ok == 0
        record = json.loads(gateway.log_path.read_text().splitlines()[-1])
        assert record['status'] == 'fatal_backend_error'
    finally:
        gateway.close()
        gateway.cache.close()


async def test_provider_seed_is_bounded_without_changing_cache_identity(
    tmp_path,
):
    backend = CaptureSeedBackend()
    cfg = {
        "models": {
            "mock": {
                "backend": "mock",
                "input_per_m": 0.0,
                "output_per_m": 0.0,
                "provider_seed_max": 2**31 - 1,
            }
        }
    }
    gw = make_gateway(
        tmp_path,
        backends={"mock": backend},
        model_cfg=cfg,
    )
    logical_seed = 2**32 - 1
    await gw.complete(
        step=0,
        agent_id="t",
        model="mock",
        messages=[{"role": "user", "content": "x"}],
        schema=XSchema,
        seed=logical_seed,
    )
    assert backend.seeds == [2**31 - 1]
    gw.flush()
    record = json.loads(
        gw.log_path.read_text(encoding="utf-8").splitlines()[-1]
    )
    assert record["logical_seed"] == logical_seed
    assert record["provider_seed"] == 2**31 - 1


async def test_budget_fuse(tmp_path):
    """Exceeding the USD ceiling raises BudgetExceeded on the next call."""
    be = ConstBackend()
    # priced model: 10 prompt + 5 completion tokens at 1000/M => 0.000015 each,
    # set a tiny budget so the second call trips it
    cfg = {"models": {"mock": {"backend": "mock", "input_per_m": 1e6,
                               "output_per_m": 1e6}}}
    gw = make_gateway(tmp_path, backends={"mock": be}, budget=0.02, model_cfg=cfg)
    msgs = [{"role": "user", "content": "x"}]
    # first call: cost = (10+5)*1e6/1e6 = 15 USD -> pushes spent way over budget
    await gw.complete(step=0, agent_id="t", model="mock", messages=msgs,
                      schema=XSchema, seed=1)
    with pytest.raises(BudgetExceeded):
        await gw.complete(step=1, agent_id="t", model="mock", messages=msgs,
                          schema=XSchema, seed=2)


async def test_json_repair(tmp_path):
    """Malformed JSON triggers exactly one repair call, then succeeds."""
    be = RepairBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})
    msgs = [{"role": "user", "content": "x"}]
    out = await gw.complete(step=0, agent_id="t", model="mock", messages=msgs,
                            schema=XSchema, seed=1)
    assert out.x == 7
    assert be.calls == 2  # original + one repair
    assert '"required":["x"]' in be.message_batches[1][-1]["content"]
    assert gw.n_ok == 1
    assert gw.stats()["live_prompt_tokens"] == 20
    assert gw.stats()["live_completion_tokens"] == 10


async def test_empirical_prob_distinct_seeds(tmp_path):
    """v2 §5.3: k samples must use DISTINCT derived seeds, not collapse to one."""
    be = SeedVaryingBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})

    async def decide_once(seed: int):
        return await gw.complete(step=0, agent_id="t", model="mock",
                                 messages=[{"role": "user", "content": "act"}],
                                 schema=ActSchema, seed=seed)

    p = await empirical_prob(decide_once, base_seed=42, k=8)
    # the 8 derived seeds must be distinct (no cache collapse)
    assert len(set(be.seen_seeds)) == 8
    # and the probability is a real fraction, not 0/1
    assert 0.0 < p < 1.0


def test_derive_is_deterministic_and_distinct():
    a = [derive(42, i) for i in range(8)]
    b = [derive(42, i) for i in range(8)]
    assert a == b               # reproducible
    assert len(set(a)) == 8     # distinct across i


def test_component_streams_are_reproducible_and_isolated():
    warning_a = stream_seed(
        42, "warning_delivery", entity_id="a1", step=3, draw_index=0
    )
    warning_b = stream_seed(
        42, "warning_delivery", entity_id="a1", step=3, draw_index=0
    )
    arbitration = stream_seed(
        42, "arbitration", entity_id="a1", step=3, draw_index=0
    )
    assert warning_a == warning_b
    assert warning_a != arbitration

    # Consuming arbitrarily many draws from one component cannot move another.
    hazard = stream_rng(42, "hazard_spread", step=3)
    for _ in range(100):
        hazard.random()
    assert stream_seed(
        42, "warning_delivery", entity_id="a1", step=3, draw_index=0
    ) == warning_a


def test_gateway_uses_first_available_api_key_environment(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.setenv("SECOND_KEY", "secret-value")
    cfg = {
        "models": {
            "proxy": {
                "backend": "mock",
                "api_key_env_candidates": ["FIRST_KEY", "SECOND_KEY"],
                "input_per_m": 0.0,
                "output_per_m": 0.0,
            }
        }
    }
    gw = LLMGateway(
        run_id="env-candidates",
        models_cfg=cfg,
        budget_usd=1.0,
        log_dir=tmp_path,
    )
    try:
        assert gw._call_kwargs("proxy")["api_key"] == "secret-value"
    finally:
        gw.close()


async def test_fallback_rate_gate(tmp_path):
    """assert_valid raises once fallback rate exceeds threshold."""
    be = ConstBackend()
    gw = make_gateway(tmp_path, backends={"mock": be})
    # 99 ok + 2 fallback = ~1.98% > 1%
    for i in range(99):
        await gw.complete(step=i, agent_id="t", model="mock",
                          messages=[{"role": "user", "content": f"x{i}"}],
                          schema=XSchema, seed=i)
    # These backend diagnostics describe the same two logical decisions as the
    # two rule fallbacks below and must not enter the denominator again.
    gw.n_failed = 2
    gw.mark_fallback(0, "a", "backend down")
    gw.mark_fallback(1, "b", "backend down")
    assert gw.fallback_rate() == pytest.approx(2 / 101)
    assert gw.validity_status() == "INVALID"
    with pytest.raises(RuntimeError, match="INVALID"):
        gw.assert_valid()


async def test_resident_policy_reacts_to_warning(tmp_path):
    """Mock resident policy: a warning + near fire pushes toward evacuate."""
    gw = make_gateway(tmp_path)  # real MockBackend with resident_policy

    async def decide(content: str, seed: int):
        return await gw.complete(step=0, agent_id="t", model="mock",
                                 messages=[{"role": "user", "content": content}],
                                 schema=ActSchema, seed=seed)

    # aggregate over seeds to get a rate
    warned = [await decide("EVACUATION ORDER issued. fire distance: 500m", s)
              for s in range(20)]
    calm = [await decide("A quiet day. fire distance: 20000m", s)
            for s in range(20)]
    warned_rate = sum(o.action == "evacuate" for o in warned) / 20
    calm_rate = sum(o.action == "evacuate" for o in calm) / 20
    assert warned_rate > calm_rate + 0.2
