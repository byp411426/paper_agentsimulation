"""LLM backends behind a uniform protocol (spec §5.4: CI uses a mock backend).

The gateway never talks to litellm directly — it talks to a `Backend`. Two exist:

  * MockBackend   — offline, deterministic, zero-cost. Its default policy is a
                    rule-based disaster resident that reads the prompt (fire
                    distance, warnings, injuries) and returns a *behaviorally
                    meaningful* decision. This lets the whole pipeline be tested
                    offline, and is reused as rule_fallback / the M1.5 rule agent.
  * LiteLLMBackend — real models via litellm.acompletion.

Both return a normalized `LLMResponse`, so the gateway is decoupled from
litellm's response shape (and the v2 "resp.usage judged-empty" fix lives here).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    response_model: str | None = None
    finish_reason: str | None = None
    reasoning_chars: int = 0


class BackendError(Exception):
    """Raised by a backend when a call genuinely fails (network, auth, etc.)."""


class BackendFatalError(BackendError):
    """Non-retryable provider access failure such as exhausted credit/auth."""


def is_fatal_provider_error(error: BaseException | str) -> bool:
    """Classify provider failures that cannot recover inside the current run."""
    message = str(error).casefold()
    markers = (
        "insufficient balance",
        "insufficient_balance",
        "insufficient quota",
        "insufficient_quota",
        "invalid api key",
        "incorrect api key",
        "authentication failed",
        "unauthorized",
        "'seed' must be integer",
        "seed must be integer",
    )
    return any(marker in message for marker in markers)


class Backend(Protocol):
    async def acomplete(
        self,
        *,
        model_id: str,
        messages: list[dict],
        temperature: float,
        seed: int,
        timeout: float,
        schema: Any | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def approx_tokens(text: str) -> int:
    """Deterministic ~token count (≈4 chars/token). Good enough for cost math."""
    return max(1, len(text) // 4)


def strip_reasoning_prefix(content: str) -> str:
    """Remove a provider-rendered leading <think> block, if present."""
    return re.sub(
        r"^\s*<think>.*?</think>\s*",
        "",
        content,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _seed_from(messages: list[dict], seed: int) -> int:
    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False) + f"|{seed}"
    return int(hashlib.sha256(blob.encode()).hexdigest(), 16) % (2**32)


def minimal_valid(schema: Any) -> dict:
    """Build a minimal dict that satisfies a pydantic v2 model's required fields.

    Used by the mock so ANY decision schema works without hand-coding. Optional
    fields (with defaults) are left out; the policy overlays semantic fields.
    """
    if schema is None:
        return {}
    out: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        ann = field.annotation
        out[name] = _default_for(ann)
    return out


def _default_for(ann: Any) -> Any:
    # Literal[...] -> first choice
    args = getattr(ann, "__args__", None)
    origin = getattr(ann, "__origin__", None)
    from typing import Literal

    if getattr(ann, "__class__", None).__name__ == "_LiteralGenericAlias" or (
        origin is Literal
    ):
        return ann.__args__[0]
    if ann in (int,):
        return 0
    if ann in (float,):
        return 0.0
    if ann in (bool,):
        return False
    if ann in (str,):
        return ""
    if origin in (list,):
        return []
    if origin in (dict,):
        return {}
    # Optional / Union: pick a non-None arm default, else None
    if args:
        for a in args:
            if a is not type(None):  # noqa: E721
                try:
                    return _default_for(a)
                except Exception:
                    pass
        return None
    return None


# --------------------------------------------------------------------------- #
# resident policy — the rule-based "brain" used by the mock                    #
# --------------------------------------------------------------------------- #
_ACTIONS = ("stay", "prepare", "evacuate", "split", "seek_help", "offer_help")


def resident_policy(messages: list[dict], seed: int, schema: Any | None) -> dict:
    """A deterministic rule-based disaster resident.

    Reads cues from the prompt text and returns a plausible decision. This is the
    single source of "reasonable behavior" for offline runs and for rule_fallback.
    Behavior is intentionally legible so smoke tests can assert on it:
      * a warning present or fire very close  -> more likely to evacuate/prepare
      * injured / family not safe             -> seek_help
      * otherwise                             -> stay
    Randomness is seeded so the same (prompt, seed) always yields the same action.
    """
    text = " ".join(m.get("content", "") for m in messages).lower()
    rng = random.Random(_seed_from(messages, seed))

    fire_m = _extract_fire_distance(text)
    warned = any(w in text for w in ("evacuation order", "warning", "evacuate now",
                                     "alert", "ordered to leave"))
    injured = "injured" in text or "injury" in text
    family_unsafe = ("family unconfirmed" in text or "family not safe" in text
                     or "family: unconfirmed" in text)

    # base evacuation propensity
    p = 0.05
    if warned:
        p += 0.55
    if fire_m is not None:
        if fire_m < 1000:
            p += 0.6
        elif fire_m < 3000:
            p += 0.3
        elif fire_m < 8000:
            p += 0.1
    p = min(p, 0.98)

    draw = rng.random()
    if injured or family_unsafe:
        action = "seek_help"
    elif draw < p:
        action = "evacuate"
    elif draw < p + 0.2:
        action = "prepare"
    else:
        action = "stay"

    out = minimal_valid(schema)
    # overlay semantic fields if the schema has them
    fields = set(schema.model_fields.keys()) if schema is not None else set()
    if "action" in fields:
        out["action"] = action
    for tf in ("thought", "assessment"):
        if tf in fields:
            out[tf] = _mk_thought(action, warned, fire_m)
    if "importance" in fields:
        out["importance"] = 5 if warned else (3 if action != "stay" else 1)
    if "messages" in fields:
        out["messages"] = []
    if "remember" in fields:
        out["remember"] = ([f"heard evacuation warning at fire distance {fire_m}m"]
                            if warned else [])
    return out


def _extract_fire_distance(text: str) -> float | None:
    m = re.search(r"fire\s*(?:distance|is|at)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*m", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*m(?:eters)?\s*(?:from|to)\s*(?:the\s*)?fire", text)
    if m:
        return float(m.group(1))
    return None


def _mk_thought(action: str, warned: bool, fire_m: float | None) -> str:
    d = f"{fire_m:.0f}m away" if fire_m is not None else "unknown distance"
    if action == "evacuate":
        return f"Fire is {d} and {'an order was issued' if warned else 'closing in'}; leaving now."
    if action == "prepare":
        return f"Fire is {d}; packing and getting ready in case it worsens."
    if action == "seek_help":
        return "Cannot manage alone right now; reaching out for help."
    return f"Fire is {d}; staying put and monitoring for now."


# --------------------------------------------------------------------------- #
# backends                                                                     #
# --------------------------------------------------------------------------- #
class MockBackend:
    """Offline deterministic backend. Default policy = resident_policy.

    fail_mode: if set, every call raises BackendError (drives test_fallback_detected).
    """

    def __init__(
        self,
        policy: Callable[[list[dict], int, Any], dict] = resident_policy,
        fail_mode: bool = False,
    ):
        self.policy = policy
        self.fail_mode = fail_mode
        self.calls = 0

    async def acomplete(
        self, *, model_id, messages, temperature, seed, timeout, schema=None, **kwargs
    ) -> LLMResponse:
        self.calls += 1
        if self.fail_mode:
            raise BackendError("mock backend forced failure")
        payload = self.policy(messages, seed, schema)
        content = json.dumps(payload, ensure_ascii=False)
        pt = approx_tokens(json.dumps(messages, ensure_ascii=False))
        ct = approx_tokens(content)
        return LLMResponse(content=content, prompt_tokens=pt, completion_tokens=ct)

    async def aclose(self) -> None:
        """Mock backend owns no network resources."""


class LiteLLMBackend:
    """Real backend via litellm.acompletion. Imported lazily so CI needs no key."""

    async def acomplete(
        self, *, model_id, messages, temperature, seed, timeout, schema=None, **kwargs
    ) -> LLMResponse:
        import litellm

        structured_output_mode = kwargs.pop(
            "structured_output_mode",
            "json_object",
        )
        response_format = kwargs.pop(
            "response_format",
            {"type": "json_object"},
        )
        call_kwargs: dict[str, Any] = dict(
            model=model_id,
            messages=messages,
            temperature=temperature,
            timeout=timeout,
        )
        if structured_output_mode == "tool":
            if schema is None:
                raise BackendError("tool structured output requires a schema")
            function_name = "return_structured_decision"
            call_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "description": "Return the resident decision.",
                        "parameters": schema.model_json_schema(),
                    },
                }
            ]
            call_kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": function_name},
            }
        elif structured_output_mode == "json_schema":
            if schema is None:
                raise BackendError("json_schema structured output requires a schema")
            call_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            }
        elif structured_output_mode != "json_object":
            raise BackendError(
                f"unknown structured_output_mode={structured_output_mode!r}"
            )
        elif response_format is not None:
            call_kwargs["response_format"] = response_format
        # seed is best-effort: OpenAI supports it, some proxies ignore it (spec §10.2)
        call_kwargs["seed"] = seed
        call_kwargs.update(kwargs)
        try:
            resp = await litellm.acompletion(**call_kwargs)
        except Exception as e:  # normalize every failure to BackendError
            if is_fatal_provider_error(e):
                raise BackendFatalError(str(e)) from e
            raise BackendError(str(e)) from e

        choice = resp.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []
        if structured_output_mode == "tool" and tool_calls:
            original_content = tool_calls[0].function.arguments or ""
        else:
            original_content = message.content or ""
        content = strip_reasoning_prefix(original_content)
        reasoning_content = getattr(message, "reasoning_content", None) or ""
        reasoning_details = getattr(message, "reasoning_details", None) or ""
        reasoning_chars = len(str(reasoning_content)) + len(str(reasoning_details))
        if content != original_content:
            reasoning_chars += len(original_content) - len(content)
        usage = getattr(resp, "usage", None)
        # v2 fix: guard against a missing/partial usage object
        pt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else approx_tokens(
            json.dumps(messages, ensure_ascii=False)
        )
        ct = int(getattr(usage, "completion_tokens", 0) or 0) if usage else approx_tokens(
            content
        )
        return LLMResponse(
            content=content,
            prompt_tokens=pt,
            completion_tokens=ct,
            response_model=str(getattr(resp, "model", "") or "") or None,
            finish_reason=str(getattr(choice, "finish_reason", "") or "") or None,
            reasoning_chars=reasoning_chars,
        )

    async def aclose(self) -> None:
        """Close LiteLLM's cached async HTTP clients on their owning loop."""
        import litellm

        await litellm.close_litellm_async_clients()
