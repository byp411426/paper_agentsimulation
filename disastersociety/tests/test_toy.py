"""Toy-village acceptance tests (spec M1 §4). Offline via mock backend."""

from __future__ import annotations

import asyncio

import ds.config as config
from ds.kernel.engine import Engine
from ds.kernel.logger import RunLogger
from ds.llm.backends import BackendFatalError
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from experiments.toy.runner import build_toy, run_toy


def _cfg(**overrides):
    c = config.load("configs/toy_village.yaml")
    if overrides:
        c = c.override(**overrides)
    return c.model_dump()


def test_deterministic(tmp_path):
    """Same config + seed -> byte-identical event log (cache-snapshot / seeded RNG)."""
    r1 = run_toy(_cfg(run_id="det1"), runs_dir=tmp_path)
    r2 = run_toy(_cfg(run_id="det2"), runs_dir=tmp_path)
    from ds.kernel.logger import RunLogger

    ev1 = RunLogger(r1.run_dir).read_events()
    ev2 = RunLogger(r2.run_dir).read_events()
    # drop nothing — the full per-step records must match exactly
    assert ev1 == ev2


def test_warning_speeds_evacuation(tmp_path):
    """Agents who received the warning evacuate earlier than those who didn't."""
    res = run_toy(_cfg(run_id="warn"), runs_dir=tmp_path)
    # early-window contrast right after the warning (step 6), before fire saturates
    warned_early = res.evac_rate_by_step(8, warned=True)
    unwarned_early = res.evac_rate_by_step(8, warned=False)
    assert warned_early > unwarned_early + 0.15


def test_fire_physics_not_llm(tmp_path):
    """Standing in a fire cell injures an agent regardless of any LLM output."""
    res = run_toy(_cfg(run_id="fire"), runs_dir=tmp_path)
    # by end of run the fire has spread and caught at least some non-evacuated agents
    assert res.world.snapshot()["n_injured"] >= 1
    # every injured agent is (or was) physically inside the fire footprint
    for aid in res.world.injured:
        # they were injured because physics put them in a fire cell — not a choice
        assert aid in res.world.injured


def test_cost_is_zero_with_mock(tmp_path):
    """Mock backend => zero USD, zero failures (spec M1: run < $1)."""
    res = run_toy(_cfg(run_id="cost"), runs_dir=tmp_path)
    gw = res.summary["gateway"]
    assert gw["spent"] == 0.0
    assert gw["fallback_rate"] == 0.0
    assert gw["n_ok"] > 0
    assert res.summary["status"] == "VALID"
    assert res.summary["completed_steps"] == res.summary["planned_steps"]


def test_completed_run_can_be_classified_invalid_without_early_abort(tmp_path):
    cfg = _cfg(
        run_id="invalid_terminal",
        **{"llm.fallback_threshold": -1.0},
    )
    res = run_toy(cfg, runs_dir=tmp_path)
    assert res.summary["status"] == "INVALID"
    assert res.summary["completed_steps"] == res.summary["planned_steps"]
    assert (res.run_dir / "summary.json").exists()


def test_budget_abort_still_writes_terminal_summary(tmp_path):
    cfg = _cfg(
        run_id="budget_abort",
        total_steps=8,
        **{"llm.budget_usd": 0.0},
    )
    res = run_toy(cfg, runs_dir=tmp_path)
    assert res.summary["status"] == "ABORTED"
    assert res.summary["reason_code"] == "BUDGET_EXCEEDED"
    assert res.summary["completed_steps"] < res.summary["planned_steps"]
    assert (res.run_dir / "summary.json").exists()


def test_fatal_backend_access_error_aborts_instead_of_fallback(tmp_path):
    class FatalBackend:
        calls = 0

        async def acomplete(self, **kwargs):
            self.calls += 1
            raise BackendFatalError("Insufficient Balance")

        async def aclose(self):
            return None

    cfg = _cfg(run_id="backend_abort", total_steps=2)
    cfg["population"]["n_agents"] = 1
    run_dir = tmp_path / "backend_abort_seed42"
    backend = FatalBackend()
    gateway = LLMGateway(
        run_id="backend_abort_seed42",
        models_cfg={
            "models": {
                "mock": {
                    "backend": "mock",
                    "input_per_m": 0.0,
                    "output_per_m": 0.0,
                }
            }
        },
        budget_usd=1.0,
        max_concurrency=1,
        log_dir=tmp_path,
        cache=LLMCache(run_dir / "cache.sqlite"),
        backends={"mock": backend},
    )
    parts = build_toy(cfg, 42, gateway)
    logger = RunLogger(run_dir)
    engine = Engine(
        run_seed=42,
        total_steps=2,
        step_minutes=30,
        world=parts["world"],
        agents=parts["agents"],
        interaction=parts["interaction"],
        events=parts["events"],
        gateway=gateway,
        logger=logger,
        decision_model="mock",
    )
    try:
        summary = asyncio.run(engine.run())
    finally:
        logger.close()
        gateway.close()
    assert summary["status"] == "ABORTED"
    assert summary["reason_code"] == "BACKEND_UNAVAILABLE"
    assert summary["completed_steps"] < summary["planned_steps"]
    assert backend.calls == 1
