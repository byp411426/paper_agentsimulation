"""LLM gateway — the lifeline of the whole system (spec M0 §2, v2 §2.6).

Five guarantees:
  1. Cache = model snapshot (reproducibility).
  2. Every call is logged (who / step / model / status / tokens / cost / latency).
  3. Failures are never silent: transient failures receive 3 attempts, while
     non-retryable billing/auth failures abort the run. Other exhausted calls
     become `failed`; the engine may then record `fallback_rule`.
  4. Budget fuse: a per-run USD ceiling; exceeding it raises BudgetExceeded.
     (Concurrency can overshoot by <= max_concurrency * unit_cost — accepted.)
  5. Structured output: decisions are JSON validated by a pydantic schema; one
     repair attempt on malformed output, else it counts as a failure.

The gateway talks to a `Backend` (mock or litellm), never to litellm directly,
so the offline CI path is a first-class citizen.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .backends import (
    Backend,
    BackendError,
    BackendFatalError,
    LiteLLMBackend,
    MockBackend,
)
from .cache import LLMCache

T = TypeVar("T", bound=BaseModel)


def _strip_markdown_json(text: str) -> str:
    """Remove a ```json ... ``` fence some models add around structured JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


class BudgetExceeded(Exception):
    ...


class LLMCallFailed(Exception):
    ...


class LLMBackendUnavailable(Exception):
    """The configured provider cannot serve further calls in this run."""


def make_backend(spec: dict) -> Backend:
    """Build a Backend from a models.yaml entry."""
    kind = spec.get("backend", "litellm")
    if kind == "mock":
        return MockBackend()
    return LiteLLMBackend()


class LLMGateway:
    def __init__(
        self,
        run_id: str,
        models_cfg: dict,
        budget_usd: float,
        max_concurrency: int = 16,
        log_dir: str | Path = "experiments/runs",
        cache: LLMCache | None = None,
        backends: dict[str, Backend] | None = None,
        abort_on_call_failure: bool = False,
    ):
        self.run_id = run_id
        self.models: dict[str, dict] = models_cfg["models"]
        self.budget = budget_usd
        self.spent = 0.0
        self.cache = cache if cache is not None else LLMCache()
        self.sem = asyncio.Semaphore(max_concurrency)
        self.n_ok = self.n_cache = self.n_failed = self.n_fallback = 0
        self.live_prompt_tokens = 0
        self.live_completion_tokens = 0
        self.logical_prompt_tokens = 0
        self.logical_completion_tokens = 0
        # allow injecting backends (tests inject a shared MockBackend / fail backend)
        self._backends: dict[str, Backend] = backends or {}
        self.abort_on_call_failure = bool(abort_on_call_failure)
        self.log_path = Path(log_dir) / run_id / "llm_calls.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # buffered log; flushed on dump / before assert_valid raises
        self._logf = open(self.log_path, "a", encoding="utf-8")
        self._closed = False
        self._backends_closed = False

    # ---- backend resolution ------------------------------------------------ #
    def _backend(self, model: str) -> Backend:
        if model not in self._backends:
            self._backends[model] = make_backend(self.models[model])
        return self._backends[model]

    def _model_id(self, model: str) -> str:
        return self.models[model].get("model_id", model)

    def _provider_seed(self, model: str, logical_seed: int) -> int:
        """Map the logical stream seed into a declared provider range."""
        maximum = self.models[model].get("provider_seed_max")
        if maximum is None:
            return int(logical_seed)
        maximum = int(maximum)
        if maximum < 0:
            raise ValueError("provider_seed_max must be non-negative")
        return int(logical_seed) % (maximum + 1)

    def _call_kwargs(self, model: str) -> dict:
        spec = self.models[model]
        kw: dict[str, Any] = {}
        if spec.get("base_url"):
            kw["api_base"] = spec["base_url"]
        # Optional provider call parameters (e.g. max_tokens) declared in the
        # model registry; provenance hashes the registry file.
        if isinstance(spec.get("call_kwargs"), dict):
            kw.update(spec["call_kwargs"])
        env_names = list(spec.get("api_key_env_candidates", []))
        if spec.get("api_key_env"):
            env_names.insert(0, spec["api_key_env"])
        if env_names:
            import os

            kw["api_key"] = next(
                (
                    os.environ[name]
                    for name in env_names
                    if os.environ.get(name)
                ),
                "",
            )
        return kw

    def _request_timeout(self, model: str) -> float:
        value = float(
            self.models[model].get("request_timeout_seconds", 60)
        )
        if value <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        return value

    def _max_attempts(self, model: str) -> int:
        value = int(self.models[model].get("max_attempts", 3))
        if value < 1:
            raise ValueError("max_attempts must be at least 1")
        return value

    # ---- cost & logging ---------------------------------------------------- #
    def _cost(self, model: str, pt: int, ct: int) -> float:
        m = self.models[model]
        return (pt * m["input_per_m"] + ct * m["output_per_m"]) / 1_000_000

    def _record(self, rec: dict) -> None:
        self._logf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._logf.flush()

    def flush(self) -> None:
        if not self._closed:
            self._logf.flush()

    def close(self) -> None:
        """Close local synchronous resources.

        Online runners must prefer :meth:`aclose` so backend HTTP clients are
        closed on the same event loop that created them.
        """
        if not self._closed:
            self.flush()
            self._logf.close()
            self._closed = True

    async def aclose(self) -> None:
        """Close every distinct backend, then the gateway log."""
        if self._backends_closed:
            self.close()
            return
        seen: set[int] = set()
        try:
            for backend in self._backends.values():
                identity = id(backend)
                if identity in seen:
                    continue
                seen.add(identity)
                close = getattr(backend, "aclose", None)
                if close is not None:
                    await close()
        finally:
            self._backends_closed = True
            self.close()

    # ---- main entry: structured completion --------------------------------- #
    async def complete(
        self,
        *,
        step: int,
        agent_id: str,
        model: str,
        messages: list[dict],
        schema: Type[T],
        seed: int,
        temperature: float = 0.7,
    ) -> T:
        decision_id = f"{self.run_id}:{step}:{agent_id}"
        key = LLMCache.make_key(model, messages, seed, temperature)
        provider_seed = self._provider_seed(model, seed)
        seed_record = {
            "logical_seed": int(seed),
            "provider_seed": provider_seed,
        }

        # 1. cache
        hit = self.cache.get(key)
        if hit:
            self.n_cache += 1
            self.logical_prompt_tokens += int(hit[1])
            self.logical_completion_tokens += int(hit[2])
            self._record(
                dict(run_id=self.run_id, decision_id=decision_id,
                     step=step, agent_id=agent_id, model=model,
                     key=key, status="cache_hit", latency_ms=0,
                     pt=hit[1], ct=hit[2], cost=0.0, **seed_record)
            )
            return schema.model_validate_json(hit[0])

        # 2. budget
        if self.spent >= self.budget:
            self.flush()
            raise BudgetExceeded(
                f"run {self.run_id} spent {self.spent:.4f} >= {self.budget}"
            )

        backend = self._backend(model)
        model_id = self._model_id(model)
        extra = self._call_kwargs(model)
        request_timeout = self._request_timeout(model)
        max_attempts = self._max_attempts(model)
        t0 = time.time()
        last_err: Exception | None = None

        # 3. call with concurrency limit + retries
        async with self.sem:
            resp = None
            for attempt in range(max_attempts):
                try:
                    resp = await backend.acomplete(
                        model_id=model_id, messages=messages,
                        temperature=temperature, seed=provider_seed,
                        timeout=request_timeout,
                        schema=schema, **extra,
                    )
                    break
                except BackendFatalError as e:
                    self.n_failed += 1
                    self._record(
                        dict(
                            run_id=self.run_id,
                            decision_id=decision_id,
                            step=step,
                            agent_id=agent_id,
                            model=model,
                            key=key,
                            status="fatal_backend_error",
                            error=str(e),
                            **seed_record,
                        )
                    )
                    self.flush()
                    raise LLMBackendUnavailable(str(e)) from e
                except BackendError as e:
                    last_err = e
                    await asyncio.sleep(2**attempt * 0.01)  # short backoff in tests
            if resp is None:
                self.n_failed += 1
                self._record(
                    dict(run_id=self.run_id, decision_id=decision_id,
                         step=step, agent_id=agent_id,
                         model=model, key=key, status="failed", error=str(last_err),
                         **seed_record)
                )
                self.flush()
                raise LLMCallFailed(str(last_err))

        raw = resp.content
        pt, ct = resp.prompt_tokens, resp.completion_tokens
        self.live_prompt_tokens += pt
        self.live_completion_tokens += ct
        self.logical_prompt_tokens += pt
        self.logical_completion_tokens += ct
        cost = self._cost(model, pt, ct)
        self.spent += cost
        latency = int((time.time() - t0) * 1000)

        # 4. parse + validate, one repair attempt
        try:
            out = schema.model_validate_json(_strip_markdown_json(raw))
        except (json.JSONDecodeError, ValidationError):
            repair_schema = json.dumps(
                schema.model_json_schema(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            fix_msgs = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                 "The previous output was not valid JSON for the required schema. "
                 "Output ONLY the corrected JSON object, no explanation. "
                 f"Every enum value must match this JSON Schema exactly: {repair_schema}"},
            ]
            try:
                async with self.sem:
                    resp2 = await backend.acomplete(
                        model_id=model_id, messages=fix_msgs,
                        temperature=temperature, seed=provider_seed,
                        timeout=request_timeout,
                        schema=schema, **extra,
                    )
            except BackendFatalError as e:
                self.n_failed += 1
                self._record(
                    dict(
                        run_id=self.run_id,
                        decision_id=decision_id,
                        step=step,
                        agent_id=agent_id,
                        model=model,
                        key=key,
                        status="fatal_backend_error",
                        error=f"repair call failed: {e}",
                        **seed_record,
                    )
                )
                self.flush()
                raise LLMBackendUnavailable(str(e)) from e
            except BackendError as e:
                self.n_failed += 1
                self._record(
                    dict(run_id=self.run_id, decision_id=decision_id,
                         step=step, agent_id=agent_id,
                         model=model, key=key, status="failed",
                         error=f"repair call failed: {e}", **seed_record)
                )
                self.flush()
                raise LLMCallFailed(str(e)) from e
            pt += resp2.prompt_tokens
            ct += resp2.completion_tokens
            self.live_prompt_tokens += resp2.prompt_tokens
            self.live_completion_tokens += resp2.completion_tokens
            self.logical_prompt_tokens += resp2.prompt_tokens
            self.logical_completion_tokens += resp2.completion_tokens
            cost += self._cost(model, resp2.prompt_tokens, resp2.completion_tokens)
            self.spent += self._cost(model, resp2.prompt_tokens, resp2.completion_tokens)
            raw = resp2.content
            try:
                out = schema.model_validate_json(
                    _strip_markdown_json(raw)
                )  # second failure => failed
            except (json.JSONDecodeError, ValidationError) as e:
                self.n_failed += 1
                self._record(
                    dict(run_id=self.run_id, decision_id=decision_id,
                         step=step, agent_id=agent_id,
                         model=model, key=key, status="failed",
                         error=f"schema invalid after repair: {e}", **seed_record)
                )
                self.flush()
                raise LLMCallFailed(str(e)) from e

        self.n_ok += 1
        self.cache.put(key, model, out.model_dump_json(), pt, ct)
        self._record(
            dict(run_id=self.run_id, decision_id=decision_id,
                 step=step, agent_id=agent_id, model=model,
                 key=key, status="ok", latency_ms=latency, pt=pt, ct=ct,
                 cost=cost, response_model=resp.response_model,
                 finish_reason=resp.finish_reason,
                 reasoning_chars=resp.reasoning_chars, **seed_record)
        )
        return out

    # ---- rule fallback accounting (called by the engine, not self) --------- #
    def mark_fallback(self, step: int, agent_id: str, reason: str) -> None:
        self.n_fallback += 1
        self._record(
            dict(run_id=self.run_id,
                 decision_id=f"{self.run_id}:{step}:{agent_id}",
                 step=step, agent_id=agent_id,
                 status="fallback_rule", reason=reason)
        )

    # ---- failure-rate classification -------------------------------------- #
    def fallback_rate(self) -> float:
        # failed + fallback commonly describe the same logical decision.
        total = self.n_ok + self.n_cache + self.n_fallback
        return self.n_fallback / total if total else 0.0

    def validity_status(self, threshold: float = 0.01) -> str:
        """Classify a completed run using the project engineering gate."""
        return "INVALID" if self.fallback_rate() > threshold else "VALID"

    def assert_valid(self, threshold: float = 0.01) -> None:
        """Compatibility helper for explicit post-run checks."""
        if self.validity_status(threshold) == "INVALID":
            self.flush()
            raise RuntimeError(
                f"run {self.run_id} INVALID: fallback rate "
                f"{self.fallback_rate():.2%} > {threshold:.0%}; results void, "
                f"check backend/balance and re-run."
            )

    def stats(self) -> dict:
        return dict(
            run_id=self.run_id, spent=round(self.spent, 6),
            n_ok=self.n_ok, n_cache=self.n_cache,
            n_failed=self.n_failed, n_fallback=self.n_fallback,
            fallback_rate=round(self.fallback_rate(), 6),
            live_prompt_tokens=self.live_prompt_tokens,
            live_completion_tokens=self.live_completion_tokens,
            logical_prompt_tokens=self.logical_prompt_tokens,
            logical_completion_tokens=self.logical_completion_tokens,
        )
