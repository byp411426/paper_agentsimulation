"""Toy grid world (spec M1 §4) — satisfies the engine's World protocol.

10x10 grid, fire spreads from an origin, agents flee toward (0,0). Everything
physical is deterministic given the run seed (v2: fire frontier iterated in sorted
order so replays are byte-identical). No LLM anywhere in here (red line #1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ds.kernel.actions import ExecutionOutcome, IntentEnvelope, ResolvedIntent
from ds.kernel.clock import Clock
from ds.kernel.rng import stream_rng, stream_seed


@dataclass
class MoveTo:
    cell: tuple
    intent: str = "evacuate"


@dataclass
class Stay:
    intent: str = "stay"


@dataclass
class Rejected:
    reason: str
    intent: str


class ToyWorld:
    def __init__(self, size=(10, 10), fire_origin=(8, 8), spread_prob=0.35,
                 run_seed: int = 0, cell_meters: float = 500.0):
        self.n, self.m = size
        self.fire: set[tuple] = {tuple(fire_origin)}
        self.p = spread_prob
        self.run_seed = run_seed
        self.cell_m = cell_meters
        self.evacuated: set[str] = set()
        self.injured: set[str] = set()
        self._agents_ref: dict[str, Any] = {}

    def bind_agents(self, agents: list) -> None:
        self._agents_ref = {a.id: a for a in agents}

    # ---- World protocol --------------------------------------------------- #
    def update(self, clock: Clock) -> None:
        # deterministic frontier growth; SORTED iteration (v2 reproducibility fix)
        rng = stream_rng(self.run_seed, "hazard_spread", step=clock.t)
        frontier = set()
        for (x, y) in sorted(self.fire):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.n and 0 <= ny < self.m and (nx, ny) not in self.fire:
                    if rng.random() < self.p:
                        frontier.add((nx, ny))
        self.fire |= frontier
        # anyone standing in a fire cell is injured (physics, not AI — red line #1)
        for aid, a in sorted(self._agents_ref.items()):
            if tuple(a.state.location) in self.fire and aid not in self.evacuated:
                a.state.injured = True
                self.injured.add(aid)

    def apply_events(self, events: list, clock: Clock) -> None:
        """Toy events are informational; the controlled Carr world mutates here."""

    def distance_to_fire(self, loc) -> float:
        x, y = loc
        return min(abs(x - fx) + abs(y - fy) for fx, fy in self.fire) * self.cell_m

    def arbitrate(self, agent: Any, decision: Any) -> Any:
        action = getattr(decision, "action", "stay")
        if action in ("evacuate", "seek_help"):
            x, y = agent.state.location
            target = (max(0, x - 1), max(0, y - 1))  # step toward (0,0)
            if target in self.fire:
                return Rejected("target cell on fire", intent=action)
            return MoveTo(target, intent=action)
        return Stay(intent=action)

    def resolve_batch(
        self,
        intents: list[IntentEnvelope],
        clock: Clock,
        run_seed: int,
    ) -> list[ResolvedIntent]:
        """Resolve every intent against the same pre-application world state."""
        # The key provides an order-independent tie-break hook for future shared
        # resources; ToyWorld itself has no contested capacity.
        ordered = sorted(
            intents,
            key=lambda item: stream_seed(
                run_seed,
                "arbitration",
                entity_id=item.decision_id,
                step=clock.t,
            ),
        )
        return [
            ResolvedIntent(
                decision_id=item.decision_id,
                agent_id=item.agent_id,
                agent=item.agent,
                decision=item.decision,
                action=self.arbitrate(item.agent, item.decision),
            )
            for item in ordered
        ]

    def apply_batch(
        self,
        resolved: list[ResolvedIntent],
        clock: Clock,
    ) -> dict[str, ExecutionOutcome]:
        """Apply a previously resolved batch and key outcomes by decision ID."""
        return {
            item.decision_id: self.apply(
                item.agent,
                item.action,
                clock,
                decision_id=item.decision_id,
            )
            for item in resolved
        }

    def apply(
        self,
        agent: Any,
        action: Any,
        clock: Clock,
        *,
        decision_id: str = "",
    ) -> ExecutionOutcome:
        if isinstance(action, Rejected):
            return ExecutionOutcome(
                decision_id=decision_id,
                agent_id=agent.id,
                status="rejected",
                executed_action=None,
                reason=action.reason,
            )
        if isinstance(action, MoveTo):
            old_location = agent.state.location
            agent.state.location = action.cell
            if action.cell == (0, 0):
                self.evacuated.add(agent.id)
            return ExecutionOutcome(
                decision_id=decision_id,
                agent_id=agent.id,
                status="executed",
                executed_action=action.intent,
                state_delta={
                    "location": {
                        "before": old_location,
                        "after": action.cell,
                    }
                },
            )
        return ExecutionOutcome(
            decision_id=decision_id,
            agent_id=agent.id,
            status="executed",
            executed_action=getattr(action, "intent", "stay"),
        )

    def snapshot(self) -> dict:
        return {
            "fire_size": len(self.fire),
            "n_evacuated": len(self.evacuated),
            "n_injured": len(self.injured),
        }
