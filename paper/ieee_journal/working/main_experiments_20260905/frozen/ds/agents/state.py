"""Agent state + the Resident agent (spec §2.3, §3 should_wake).

State is three-tier: static (never changes) / semi-stable (traits, trust priors) /
dynamic (location, exposure, family safety, injury, action). The Resident satisfies
the engine's Agent protocol: should_wake / decide / rule_fallback / snapshot.

decide() goes through the gateway; on LLMCallFailed the engine calls rule_fallback()
(the same rule-based policy the mock backend uses, so behavior stays coherent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ds.agents.decide import Decision, build_toy_messages
from ds.agents.memory import Memory
from ds.agents.trust import Trust
from ds.llm.backends import resident_policy
from ds.llm.gateway import LLMGateway


@dataclass
class StaticAttrs:
    age: int = 40
    decision_capable: bool = True
    decision_policy: Literal["generative", "rule", "dependent"] = "generative"
    # Compatibility view for the toy scenario. Formal Carr resources live on
    # Household, not independently on each resident.
    has_vehicle: bool = True
    functional_limitations: dict[str, bool] = field(default_factory=dict)
    household_id: str = ""
    zone: str = ""
    home: Any = (0, 0)


@dataclass
class DynamicState:
    location: Any = (0, 0)
    family_all_safe: bool = True
    injured: bool = False
    evacuating: bool = False
    last_intent: str = "stay"
    last_action: str = "stay"
    last_outcome: str = "executed"
    warned: bool = False  # ever received an official warning (delivery model)
    warned_step: int = -1  # step the warning was first received (-1 = never)
    evac_step: int = -1    # step evacuation first started (-1 = never)


class Resident:
    """A single resident agent (individual decision unit; households compose these)."""

    def __init__(
        self,
        agent_id: str,
        static: StaticAttrs | None = None,
        traits: str = "cautious, trusts officials",
        persona: str = "a local resident",
        trust: Trust | None = None,
        memory_capacity: int = 200,
        panic_prone: bool = False,
    ):
        self.id = agent_id
        self.static = static or StaticAttrs()
        self.state = DynamicState(location=self.static.home, family_all_safe=True)
        self.traits = traits
        self.persona = persona
        self.trust = trust or Trust()
        self.memory = Memory(capacity=memory_capacity)
        self.panic_prone = panic_prone
        self.inbox: list[dict] = []

    # ---- wake gate (spec §3) ---------------------------------------------- #
    def should_wake(self, *, events: list, world: Any, step: int) -> bool:
        if (
            not self.static.decision_capable
            or self.static.decision_policy == "dependent"
        ):
            return False
        # Note: warnings are delivered into the inbox (delivery-gated) BEFORE this
        # gate runs, so we wake on `inbox`, not on raw event coverage — an agent who
        # did not receive the warning should not wake because of it.
        if self.state.injured or self.state.evacuating:
            return True
        if self.inbox:
            return True
        try:
            if world.distance_to_fire(self.state.location) < 3000:
                return True
        except Exception:
            pass
        if not self.state.family_all_safe:
            return True
        return False

    # ---- decision --------------------------------------------------------- #
    def _messages(self, events: list, world: Any, step: int) -> list[dict]:
        fire_m = world.distance_to_fire(self.state.location)
        # Information the agent PERCEIVES = only what reached its inbox
        # (delivery-gated warnings + messages from others). The raw event stream is
        # NOT perceived directly: an official warning is only "heard" if the
        # delivery model put it in the inbox (v2 §2.4). Fire distance, by contrast,
        # is directly observable to everyone.
        new_info = [m.get("content", "") for m in self.inbox]
        memories = self.memory.recall(step)
        return build_toy_messages(
            self.persona, self.traits, self.state.location,
            self.state.family_all_safe, fire_m, new_info, memories,
        )

    async def decide(self, *, events, world, gateway: LLMGateway, step: int) -> Decision:
        msgs = self._messages(events, world, step)
        # Component-isolated seed: ablations reuse the same exogenous streams.
        from ds.kernel.rng import stream_seed

        seed = stream_seed(
            gateway_seed(gateway),
            "llm_decision",
            entity_id=self.id,
            step=step,
        )
        dec = await gateway.complete(
            step=step, agent_id=self.id, model=_model_of(gateway),
            messages=msgs, schema=Decision, seed=seed,
        )
        return dec

    def rule_fallback(self, *, step: int = -1) -> Decision:
        """Same rule policy the mock uses, so a fallback stays behaviorally coherent."""
        payload = resident_policy([], 0, Decision)
        # rule_fallback keeps the previous action if nothing forces a change
        payload.setdefault("action", self.state.last_action)
        dec = Decision(**payload)
        return dec

    def commit_execution(self, decision: Decision, outcome: Any, *, step: int) -> None:
        """Commit state only after the world returns an execution outcome."""
        self.state.last_intent = decision.action
        self.state.last_outcome = getattr(outcome, "status", "unknown")
        executed = getattr(outcome, "executed_action", None)
        if self.state.last_outcome == "executed" and executed is not None:
            self.state.last_action = executed
        if (
            self.state.last_outcome == "executed"
            and executed == "evacuate"
            and not self.state.evacuating
        ):
            self.state.evacuating = True
            self.state.evac_step = step
        for text in decision.remember:
            self.memory.write_text(max(step, 0), text, kind="reflection")

    # ---- logging ---------------------------------------------------------- #
    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "loc": list(self.state.location) if isinstance(self.state.location, tuple)
            else self.state.location,
            "family_safe": self.state.family_all_safe,
            "injured": self.state.injured,
            "evacuating": self.state.evacuating,
            "last_intent": self.state.last_intent,
            "last_action": self.state.last_action,
            "last_outcome": self.state.last_outcome,
            "warned": self.state.warned,
        }


# --------------------------------------------------------------------------- #
# helpers for event/agent coupling                                            #
# --------------------------------------------------------------------------- #
def _event_covers(event: Any, agent: "Resident") -> bool:
    if hasattr(event, "recipient_covers"):
        return event.recipient_covers(agent)
    if isinstance(event, dict):
        rec = event.get("recipients", "all")
        return rec == "all" or agent.id in rec
    return True


def _event_text(event: Any) -> str:
    if hasattr(event, "text"):
        return event.text
    if isinstance(event, dict):
        return event.get("text", str(event))
    return str(event)


# the gateway doesn't carry a seed/model by itself; we stash them at construction
def gateway_seed(gw: LLMGateway) -> int:
    return getattr(gw, "run_seed", 0)


def _model_of(gw: LLMGateway) -> str:
    return getattr(gw, "decision_model", "mock")
