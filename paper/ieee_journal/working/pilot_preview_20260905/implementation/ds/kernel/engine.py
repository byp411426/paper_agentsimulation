"""Simulation engine — the heart of the kernel (spec §3, v2 §2.6 step order).

Ten-step order per tick (order is load-bearing; a wrong order corrupts causality):

  ① world.update            — fire spreads / roads / shelter capacity advance first,
                              so what agents perceive is the POST-update world
  ② events = due events     — warnings / closures from the EventPack (never AI-made)
  ③ deliver warnings        — probabilistic reception model stamps who actually got it
  ④ awake = should_wake     — no-event agents keep running rules at zero cost
  ⑤ collect intentions      — all awake agents see the same post-update world phase
  ⑥ shuffle + arbitrate     — settle in seeded-shuffled order (no index bias);
                              world vetoes illegal actions (closed road / full shelter)
  ⑦ apply + commit + emit   — results commit agent state; messages enqueue
  ⑧ interaction.deliver     — dm instant, community delayed one step
  ⑨ log.dump_step           — full snapshot
  ⑩ final classification    — terminal summary is VALID, INVALID, or ABORTED

Collaborators are injected and only need to satisfy the small protocols below, so
the same engine drives the toy village and the real Carr world unchanged.
"""

from __future__ import annotations

import asyncio
import time

from typing import Any, Protocol, runtime_checkable

from ds.kernel.actions import ExecutionOutcome, IntentEnvelope, ResolvedIntent
from ds.kernel.clock import Clock
from ds.kernel.logger import RunLogger
from ds.llm.gateway import (
    BudgetExceeded,
    LLMBackendUnavailable,
    LLMCallFailed,
    LLMGateway,
)


@runtime_checkable
class World(Protocol):
    def update(self, clock: Clock) -> None: ...
    def apply_events(self, events: list, clock: Clock) -> None: ...
    def resolve_batch(
        self, intents: list[IntentEnvelope], clock: Clock, run_seed: int
    ) -> list[ResolvedIntent]: ...
    def apply_batch(
        self, resolved: list[ResolvedIntent], clock: Clock
    ) -> dict[str, ExecutionOutcome]: ...
    def snapshot(self) -> dict: ...


@runtime_checkable
class Agent(Protocol):
    id: str
    def should_wake(self, *, events: list, world: Any, step: int) -> bool: ...
    async def decide(self, *, events: list, world: Any, gateway: LLMGateway,
                     step: int) -> Any: ...
    def rule_fallback(self, *, step: int = -1) -> Any: ...
    def commit_execution(self, decision: Any, outcome: Any, *, step: int) -> None: ...
    def snapshot(self) -> dict: ...


@runtime_checkable
class Interaction(Protocol):
    def deliver_warnings(self, events: list, agents: list, clock: Clock,
                         run_seed: int) -> None: ...
    def emit(self, agent: Any, decision: Any, clock: Clock) -> None: ...
    def process(self, agent: Any, decision: Any, clock: Clock) -> None: ...
    def deliver(self, clock: Clock) -> None: ...
    def snapshot(self) -> dict: ...


@runtime_checkable
class EventSource(Protocol):
    def events_due(self, step: int) -> list: ...


class Engine:
    def __init__(
        self,
        *,
        run_seed: int,
        total_steps: int,
        step_minutes: int,
        world: World,
        agents: list[Agent],
        interaction: Interaction,
        events: EventSource,
        gateway: LLMGateway,
        logger: RunLogger,
        decision_model: str = "mock",
        temperature: float = 0.7,
        fallback_threshold: float = 0.01,
    ):
        self.run_seed = run_seed
        self.total_steps = total_steps
        self.world = world
        self.agents = agents
        self.ix = interaction
        self.events = events
        self.gw = gateway
        self.log = logger
        self.clock = Clock(step_minutes)
        self.decision_model = decision_model
        self.temperature = temperature
        self.fallback_threshold = fallback_threshold
        self.completed_steps = 0
        self._wall_clock_started: float | None = None
        # stash run-level context on the gateway so agents can read seed/model
        # without the engine threading them through every decide() call
        self.gw.run_seed = run_seed
        self.gw.decision_model = decision_model
        self.gw.temperature = temperature

    async def run(self) -> dict:
        self._wall_clock_started = time.perf_counter()
        try:
            for _ in range(self.total_steps):
                self.clock.tick()
                step = self.clock.t

                # ① world advances first
                self.world.update(self.clock)

                # ② due events (warnings / closures)
                events = self.events.events_due(step)
                self.world.apply_events(events, self.clock)

                # ③ probabilistic warning delivery — stamps reception on agents
                self.ix.deliver_warnings(
                    events, self.agents, self.clock, self.run_seed
                )

                # ④ wake gate — sorted for stable iteration; deterministic
                awake = [
                    a for a in sorted(self.agents, key=lambda x: x.id)
                    if a.should_wake(events=events, world=self.world, step=step)
                ]

                import copy
                self._audit_before = {"world": copy.deepcopy(self.world.snapshot()),
                    "agents": copy.deepcopy([a.snapshot() for a in self.agents])}
                # ⑤ collect intentions while the world is immutable for this phase
                decisions = await asyncio.gather(
                    *(
                        self._safe_decide(agent, events, step)
                        for agent in awake
                    )
                )
                for agent, decision in zip(awake, decisions):
                    self.ix.process(agent, decision, self.clock)

                # ⑥ resolve all intentions before any world application
                envelopes = [
                    IntentEnvelope(
                        decision_id=f"{self.gw.run_id}:{step}:{agent.id}",
                        agent_id=agent.id,
                        agent=agent,
                        decision=decision,
                    )
                    for agent, decision in zip(awake, decisions)
                ]
                resolved = self.world.resolve_batch(
                    envelopes, self.clock, self.run_seed
                )
                outcomes_by_id = self.world.apply_batch(resolved, self.clock)

                # ⑦ only keyed execution outcomes may commit resident state
                for envelope in envelopes:
                    outcome = outcomes_by_id[envelope.decision_id]
                    envelope.agent.commit_execution(
                        envelope.decision, outcome, step=step
                    )
                    self.ix.emit(envelope.agent, envelope.decision, self.clock)

                # ⑧ message delivery
                self.ix.deliver(self.clock)

                # ⑨ full snapshot with intention and execution outcome
                self.log.dump_step(
                    self._step_record(
                        step, awake, decisions, envelopes, outcomes_by_id
                    )
                )
                self.completed_steps += 1

        except BudgetExceeded as exc:
            return self._finish(
                "ABORTED",
                reason_code="BUDGET_EXCEEDED",
                abort_reason=str(exc),
            )
        except LLMBackendUnavailable as exc:
            return self._finish(
                "ABORTED",
                reason_code="BACKEND_UNAVAILABLE",
                abort_reason=str(exc),
            )
        except BaseException as exc:
            self._finish(
                "ABORTED",
                reason_code="UNHANDLED_EXCEPTION",
                abort_reason=f"{type(exc).__name__}: {exc}",
            )
            raise

        return self._finish(
            self.gw.validity_status(self.fallback_threshold)
        )

    def _finish(
        self,
        status: str,
        reason_code: str | None = None,
        abort_reason: str | None = None,
    ) -> dict:
        summary = self._summary(
            status=status,
            reason_code=reason_code,
            abort_reason=abort_reason,
        )
        self.log.dump_final(summary)
        self.gw.flush()
        return summary

    async def _safe_decide(self, agent: Agent, events: list, step: int):
        static = getattr(agent, "static", None)
        if getattr(static, "decision_policy", "generative") == "rule":
            return agent.rule_fallback(step=step)
        try:
            return await agent.decide(
                events=events, world=self.world, gateway=self.gw, step=step
            )
        except LLMCallFailed as e:
            if self.gw.abort_on_call_failure:
                raise LLMBackendUnavailable(
                    "declared backend logical decision failed; "
                    f"agent={agent.id}, step={step}: {e}"
                ) from e
            self.gw.mark_fallback(step, agent.id, str(e))
            return agent.rule_fallback(step=step)

    def _step_record(
        self,
        step: int,
        awake: list,
        decisions: list,
        envelopes: list[IntentEnvelope],
        outcomes_by_id: dict[str, ExecutionOutcome],
    ) -> dict:
        return {
            "step": step,
            "sim_minutes": self.clock.sim_minutes,
            "world": self.world.snapshot(),
            "n_awake": len(awake),
            "state_before_decisions": self._audit_before,
            "decisions": [
                {
                    "agent": a.id,
                    "decision_id": envelope.decision_id,
                    "decision": _dec_dump(d),
                    "outcome": _dec_dump(
                        outcomes_by_id[envelope.decision_id]
                    ),
                }
                for a, d, envelope in zip(awake, decisions, envelopes)
            ],
            "agents": [a.snapshot() for a in sorted(self.agents, key=lambda x: x.id)],
            "interaction": self.ix.snapshot(),
        }

    def _summary(
        self,
        *,
        status: str,
        reason_code: str | None = None,
        abort_reason: str | None = None,
    ) -> dict:
        summary = {
            "run_seed": self.run_seed,
            "planned_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "last_completed_step": (
                self.clock.t if self.completed_steps else None
            ),
            "status": status,
            "world_final": self.world.snapshot(),
            "gateway": self.gw.stats(),
            "wall_clock_seconds": round(
                time.perf_counter() - self._wall_clock_started, 6
            )
            if self._wall_clock_started is not None
            else None,
        }
        if reason_code is not None:
            summary["reason_code"] = reason_code
        if abort_reason is not None:
            summary["abort_reason"] = abort_reason
        return summary


def _dec_dump(d: Any) -> Any:
    if hasattr(d, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(d)
    if hasattr(d, "model_dump"):
        return d.model_dump()
    return d
