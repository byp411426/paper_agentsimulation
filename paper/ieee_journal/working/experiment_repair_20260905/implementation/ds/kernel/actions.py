"""Typed boundary between resident intentions and world execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IntentEnvelope:
    decision_id: str
    agent_id: str
    agent: Any = field(repr=False, compare=False)
    decision: Any = field(repr=False, compare=False)


@dataclass(frozen=True)
class ResolvedIntent:
    decision_id: str
    agent_id: str
    agent: Any = field(repr=False, compare=False)
    decision: Any = field(repr=False, compare=False)
    action: Any = field(repr=False, compare=False)


@dataclass(frozen=True)
class ExecutionOutcome:
    decision_id: str
    agent_id: str
    status: str
    executed_action: str | None
    reason: str | None = None
    resource_allocations: dict[str, str] = field(default_factory=dict)
    state_delta: dict[str, Any] = field(default_factory=dict)
