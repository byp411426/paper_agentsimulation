"""Carr controlled-case resident adapter and deterministic offline policy.

The policy is intentionally transparent and exists only for zero-cost mechanism
tests.  Publication-facing generative runs use the same resident/world boundary
with a declared model backend.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from ds.agents.decide import ResidentDecision
from ds.agents.planning import ExecutablePlan
from ds.agents.state import Resident, StaticAttrs, gateway_seed
from ds.kernel.rng import stream_seed
from ds.llm.backends import minimal_valid
from ds.llm.gateway import LLMGateway


@dataclass(frozen=True)
class MechanismFlags:
    memory: bool = True
    feedback: bool = True
    planning: bool = True
    interaction: bool = True

    @classmethod
    def from_condition(cls, condition: str) -> "MechanismFlags":
        mapping = {
            "full": cls(),
            "full_minus_memory": cls(memory=False),
            "full_minus_feedback": cls(feedback=False),
            "full_minus_planning": cls(planning=False),
            "full_minus_interaction": cls(interaction=False),
        }
        try:
            return mapping[condition]
        except KeyError as exc:
            raise ValueError(f"unknown Carr mechanism condition: {condition}") from exc


class CarrResident(Resident):
    """Resident with explicit Carr plan and mechanism state."""

    def __init__(
        self,
        agent_id: str,
        *,
        static: StaticAttrs,
        household: Any,
        role: str,
        partner_id: str,
        vehicle_id: str,
        dependent_ids: tuple[str, ...],
        mechanisms: MechanismFlags,
        depart_step: int,
        primary_route_id: str,
        alternate_route_id: str,
        persona: str,
        prompt_version: str = "carr_s_controlled_resident_v3",
        coordination_deadline_step: int | None = None,
        route_observation_mode: str = "live_world",
    ):
        super().__init__(
            agent_id,
            static=static,
            persona=persona,
            traits="household-aware, cautious under uncertainty",
        )
        self.household = household
        self.role = role
        self.partner_id = partner_id
        self.vehicle_id = vehicle_id
        self.dependent_ids = dependent_ids
        self.mechanisms = mechanisms
        self.controlled_depart_step = depart_step
        self.primary_route_id = primary_route_id
        self.alternate_route_id = alternate_route_id
        self.prompt_version = prompt_version
        self.coordination_deadline_step = coordination_deadline_step
        if route_observation_mode not in {"live_world", "feedback_gated"}:
            raise ValueError(
                "route_observation_mode must be live_world or feedback_gated"
            )
        self.route_observation_mode = route_observation_mode
        self.observed_routes: dict[str, dict[str, Any]] | None = None
        self.route_observation_step: int | None = None
        self.plan: ExecutablePlan | None = None
        self.plan_history: list[dict[str, Any]] = []
        self.feedback_events: list[dict[str, Any]] = []
        self.emitted_proposals: list[dict[str, Any]] = []

    def initialize_route_observation(
        self,
        current: dict[str, dict[str, Any]],
        *,
        step: int,
    ) -> None:
        """Initialize the resident's private route observation."""
        self.observed_routes = copy.deepcopy(current)
        self.route_observation_step = step

    def initialize_controlled_plan(
        self,
        *,
        route_id: str,
        vehicle_id: str,
        depart_step: int,
        dependent_ids: tuple[str, ...],
        created_step: int,
    ) -> None:
        """Seed the resident's private initial plan."""
        self.plan = ExecutablePlan(
            id=f"controlled-initial-plan:{self.id}",
            route_id=route_id,
            vehicle_id=vehicle_id,
            depart_step=depart_step,
            dependent_ids=dependent_ids,
            created_step=created_step,
        )
        self.plan_history.append(
            {
                "step": created_step,
                "route_id": route_id,
                "status": "planned",
                "failure": None,
                "source": "controlled_initial_state",
            }
        )

    def record_emitted_message(self, message: Any) -> None:
        """Track successfully enqueued proposals without implying acceptance."""
        if getattr(message, "kind", None) != "proposal":
            return
        self.emitted_proposals.append(
            {
                "message_id": message.message_id,
                "route_id": message.payload.get("route_id"),
                "vehicle_id": message.payload.get("vehicle_id"),
                "depart_step": message.payload.get("depart_step"),
                "sent_step": message.sent_step,
            }
        )

    def should_wake(self, *, events: list, world: Any, step: int) -> bool:
        if (
            not self.static.decision_capable
            or self.static.decision_policy == "dependent"
            or world.is_safe(self.id)
        ):
            return False
        if self.inbox:
            return True
        if self.plan is not None and self.plan.status != "completed":
            return True
        if self.household.commitments:
            return True
        return world.distance_to_fire(self.state.location) < 3000

    async def decide(
        self,
        *,
        events,
        world,
        gateway: LLMGateway,
        step: int,
    ) -> ResidentDecision:
        messages = self._carr_messages(world=world, step=step)
        return await gateway.complete(
            step=step,
            agent_id=self.id,
            model=getattr(gateway, "decision_model", "mock"),
            messages=messages,
            schema=ResidentDecision,
            seed=stream_seed(
                gateway_seed(gateway),
                "llm_decision",
                entity_id=self.id,
                step=step,
            ),
            temperature=getattr(gateway, "temperature", 0.0),
        )

    def rule_fallback(self, *, step: int = -1) -> ResidentDecision:
        return ResidentDecision(
            assessment="backend failure; preserve current physical state",
            action="stay",
        )

    def commit_execution(
        self,
        decision: ResidentDecision,
        outcome: Any,
        *,
        step: int,
    ) -> None:
        self.state.last_intent = decision.action
        self.state.last_outcome = getattr(outcome, "status", "unknown")
        executed = getattr(outcome, "executed_action", None)
        if self.state.last_outcome == "executed" and executed is not None:
            self.state.last_action = executed

        if self.mechanisms.planning and decision.route_id and decision.vehicle_id:
            if self.plan is None or (
                self.plan.route_id,
                self.plan.vehicle_id,
                self.plan.depart_step,
            ) != (
                decision.route_id,
                decision.vehicle_id,
                decision.depart_step,
            ):
                self.plan = ExecutablePlan(
                    id=f"plan:{self.id}:{step}:{decision.route_id}",
                    route_id=decision.route_id,
                    vehicle_id=decision.vehicle_id,
                    depart_step=decision.depart_step
                    if decision.depart_step is not None
                    else step,
                    dependent_ids=tuple(decision.accompany_dependents),
                    created_step=step,
                )

        if self.state.last_outcome == "rejected" and self.mechanisms.feedback:
            reason = getattr(outcome, "reason", None) or "rejected"
            self.feedback_events.append(
                {"step": step, "kind": "execution_rejected", "reason": reason}
            )
            if self.plan is not None:
                self.plan.status = "blocked"
                self.plan.last_failure = reason
        elif (
            self.state.last_outcome == "executed"
            and executed == "evacuate"
        ):
            self.state.evacuating = True
            if self.state.evac_step < 0:
                self.state.evac_step = step
            if self.plan is not None:
                self.plan.status = "completed"

        if self.mechanisms.feedback and any(
            "route is closed" in text.lower()
            for text in decision.remember
        ):
            self.feedback_events.append(
                {
                    "step": step,
                    "kind": "road_closure_update",
                    "route_id": decision.route_id,
                }
            )

        if self.mechanisms.memory:
            for text in decision.remember:
                self.memory.write_text(max(step, 0), text, kind="reflection")

        if self.plan is not None:
            record = {
                "step": step,
                "route_id": self.plan.route_id,
                "status": self.plan.status,
                "failure": self.plan.last_failure,
                "source": (
                    "controlled_initial_state"
                    if self.plan.id.startswith("controlled-initial-plan:")
                    else "model_decision"
                ),
            }
            if not self.plan_history or self.plan_history[-1] != record:
                self.plan_history.append(record)

    def snapshot(self) -> dict:
        base = super().snapshot()
        base.update(
            {
                "household_id": self.static.household_id,
                "role": self.role,
                "plan": (
                    {
                        "id": self.plan.id,
                        "route_id": self.plan.route_id,
                        "vehicle_id": self.plan.vehicle_id,
                        "depart_step": self.plan.depart_step,
                        "status": self.plan.status,
                        "last_failure": self.plan.last_failure,
                    }
                    if self.plan
                    else None
                ),
                "feedback_events": len(self.feedback_events),
                "memory_items": len(self.memory.items),
                "route_observation_mode": self.route_observation_mode,
                "route_observation_step": self.route_observation_step,
            }
        )
        return base

    def _route_observation(self, *, world: Any, step: int) -> dict:
        current = world.route_snapshot()
        if self.route_observation_mode == "live_world":
            self.initialize_route_observation(current, step=step)
            return copy.deepcopy(current)

        if self.observed_routes is None:
            raise RuntimeError(
                "feedback-gated route observation must be initialized before run"
            )
        if self.mechanisms.feedback:
            previous = self.observed_routes
            if current != previous:
                changed_routes = sorted(
                    route_id
                    for route_id in set(previous) | set(current)
                    if previous.get(route_id) != current.get(route_id)
                )
                self.feedback_events.append(
                    {
                        "step": step,
                        "kind": "route_observation_update",
                        "route_ids": changed_routes,
                    }
                )
            self.initialize_route_observation(current, step=step)
        return copy.deepcopy(self.observed_routes)

    def _carr_messages(self, *, world: Any, step: int) -> list[dict]:
        execution_feedback_v8 = self.prompt_version == (
            "carr_s_controlled_resident_v8"
        )
        inbox = [
            {
                "message_id": item.get("message_id"),
                "sender": item.get("sender"),
                "channel": item.get("channel"),
                "kind": item.get("kind"),
                "content": item.get("content", ""),
                "payload": item.get("payload", {}),
            }
            for item in self.inbox
        ]
        accepted = [
            {
                "id": commitment.id,
                "route_id": commitment.route_id,
                "vehicle_id": commitment.vehicle_id,
                "depart_step": commitment.depart_step,
                "accepted_by": sorted(commitment.accepted_by),
            }
            for commitment in self.household.commitments.values()
            if commitment.status == "accepted"
        ]
        warning_memory = any(
            item.kind == "warning" for item in self.memory.items
        )
        accepted_signatures = {
            (
                commitment["route_id"],
                commitment["vehicle_id"],
                commitment["depart_step"],
            )
            for commitment in accepted
        }
        pending_proposal = next(
            (
                proposal
                for proposal in reversed(self.emitted_proposals)
                if step <= int(proposal["sent_step"]) + 1
                and (
                    proposal["route_id"],
                    proposal["vehicle_id"],
                    proposal["depart_step"],
                )
                not in accepted_signatures
            ),
            None,
        )
        current_plan = (
            {
                "route_id": self.plan.route_id,
                "vehicle_id": self.plan.vehicle_id,
                "depart_step": self.plan.depart_step,
                "status": self.plan.status,
                **(
                    {"last_failure": self.plan.last_failure}
                    if execution_feedback_v8
                    else {}
                ),
            }
            if self.plan
            else None
        )
        state = {
            "prompt_version": self.prompt_version,
            "step": step,
            "agent_id": self.id,
            "role": self.role,
            "resident_profile": {
                "persona": self.persona,
                "age": self.static.age,
                "functional_limitations": {
                    name: enabled
                    for name, enabled in sorted(
                        self.static.functional_limitations.items()
                    )
                },
            },
            "partner_id": self.partner_id,
            "household_id": self.static.household_id,
            "household_member_count": len(self.household.member_ids),
            "decision_member_count": len(
                self.household.decision_member_ids
            ),
            "vehicle_id": self.vehicle_id,
            "dependent_ids": list(self.dependent_ids),
            "warning_memory": warning_memory,
            "inbox": inbox,
            "hazard_distance_m": world.distance_to_fire(self.state.location),
            "routes": self._route_observation(world=world, step=step),
            "route_observation_step": self.route_observation_step,
            "route_observation_mode": self.route_observation_mode,
            "primary_route_id": self.primary_route_id,
            "alternate_route_id": self.alternate_route_id,
            "controlled_depart_step": self.controlled_depart_step,
            "earliest_proposal_depart_step": step + 1,
            "coordination_deadline_step": self.coordination_deadline_step,
            "current_plan": current_plan,
            "accepted_commitments": accepted,
            "pending_proposal": pending_proposal,
            "mechanisms": {
                "memory": self.mechanisms.memory,
                "feedback": self.mechanisms.feedback,
                "planning": self.mechanisms.planning,
                "interaction": self.mechanisms.interaction,
            },
        }
        if execution_feedback_v8:
            vehicle = self.household.vehicles[self.vehicle_id]
            state["household_vehicle_state"] = {
                "vehicle_id": vehicle.id,
                "location": vehicle.location,
                "reserved_by": vehicle.reserved_by,
                "occupied_by": sorted(vehicle.occupied_by),
                "available_seats": vehicle.available_seats,
            }
            state["recent_execution_feedback"] = (
                self.feedback_events[-3:]
                if self.mechanisms.feedback
                else []
            )
        execution_guidance = (
            " An accepted_commitment is a jointly acknowledged coordination "
            "state. While it remains feasible, do not evacuate before its exact "
            "depart_step; at that step use its exact route_id, vehicle_id, and "
            "depart_step together with the partner. If unable to follow it, "
            "communicate a revision before acting differently. Inspect "
            "recent_execution_feedback and household_vehicle_state before "
            "reusing a vehicle. If it is reserved by another member who has "
            "already left, do not repeat the failed vehicle request; seek help "
            "or wait for a new feasible plan. Only the coordinator lists the "
            "dependent IDs unless a received message explicitly reassigns care."
            if execution_feedback_v8
            else ""
        )
        return [
            {
                "role": "system",
                "content": (
                    "You are one adult resident in a controlled wildfire "
                    "simulation. Decide only from CONTROLLED_STATE_JSON. "
                    "Return one JSON object with exactly these fields: "
                    "assessment (string, <=200 characters); action "
                    "(stay|prepare|evacuate|seek_help|offer_help); "
                    "destination_id, route_id, vehicle_id (string or null); "
                    "depart_step (integer or null); accompany_dependents "
                    "(list of supplied dependent IDs); messages (list of "
                    "objects with to, content, kind, payload), where kind must "
                    "be proposal|acknowledgement|acceptance|notice; "
                    "payload must be a JSON object (use {} rather than null); "
                    "message_responses (list of objects with message_id, "
                    "disposition accepted|rejected, and optional reason); "
                    "remember (list of short "
                    "strings). Never invent roads, IDs, vehicles, received "
                    "messages, or shared commitments. A proposal to the "
                    "partner must use kind=proposal and payload keys route_id, "
                    "vehicle_id, depart_step. Proposal depart_step must be at "
                    "least earliest_proposal_depart_step, because the partner "
                    "cannot process it until a later decision phase. Do not "
                    "send new proposals after coordination_deadline_step. "
                    "When pending_proposal is not null, wait for its recipient "
                    "processing phase and do not send a replacement proposal. "
                    "Respond only to message IDs "
                    "actually present in inbox. If a mechanism flag is false, "
                    "do not use that mechanism. Evacuate only through an open "
                    "route in the resident-observed routes field with the "
                    "supplied vehicle; the physical world independently "
                    "arbitrates execution. current_plan is private resident "
                    "state, not a shared household commitment. Use "
                    "destination_id=controlled_safe_zone. When interaction is "
                    "enabled, coordinate only through actual messages and "
                    "accepted_commitments; a sent proposal is not yet an "
                    "accepted commitment. The coordinator lists supplied "
                    "dependent IDs when taking responsibility for them; the "
                    "partner does not duplicate that list."
                    + execution_guidance
                ),
            },
            {
                "role": "user",
                "content": "CONTROLLED_STATE_JSON=" + json.dumps(
                    state,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]


def carr_controlled_policy(
    messages: list[dict],
    seed: int,
    schema: Any | None,
) -> dict:
    """Transparent policy for offline mechanism integration checks."""
    state = _controlled_state(messages)
    out = minimal_valid(schema)
    mechanisms = state["mechanisms"]
    inbox = state["inbox"]
    incoming_proposals = [
        item
        for item in inbox
        if item.get("kind") == "proposal"
    ]
    warning_now = any(
        item.get("channel") == "official" for item in inbox
    )
    hazard_close = state["hazard_distance_m"] < 3000
    known_emergency = (
        warning_now
        or state["warning_memory"]
        or bool(incoming_proposals)
        or hazard_close
        or state["current_plan"] is not None
    )
    responses = [
        {
            "message_id": proposal["message_id"],
            "disposition": "accepted",
        }
        for proposal in incoming_proposals
        if mechanisms["interaction"] and proposal.get("message_id")
    ]

    plan = state["current_plan"]
    route_id = plan.get("route_id") if plan else None
    depart_step = (
        plan.get("depart_step")
        if plan and plan.get("depart_step") is not None
        else state["controlled_depart_step"]
    )
    if incoming_proposals and mechanisms["planning"]:
        proposal_payload = incoming_proposals[-1]["payload"]
        route_id = proposal_payload.get("route_id")
        proposal_depart_step = proposal_payload.get("depart_step")
        if isinstance(proposal_depart_step, int):
            depart_step = proposal_depart_step
    if route_id is None and known_emergency and mechanisms["planning"]:
        route_id = state["primary_route_id"]

    routes = state["routes"]
    route_closed = bool(
        route_id and not routes.get(route_id, {}).get("open", False)
    )
    if route_closed and mechanisms["feedback"]:
        if mechanisms["planning"]:
            alternate = state["alternate_route_id"]
            route_id = alternate if routes.get(alternate, {}).get("open") else None
            depart_step = max(
                depart_step,
                state["earliest_proposal_depart_step"],
            )
        else:
            route_id = None

    accepted_routes = {
        (
            commitment.get("route_id"),
            commitment.get("vehicle_id"),
            commitment.get("depart_step"),
        )
        for commitment in state["accepted_commitments"]
    }
    has_compatible_commitment = (
        route_id,
        state["vehicle_id"],
        depart_step,
    ) in accepted_routes

    outgoing = []
    proposal_depart_step = max(
        depart_step,
        state["earliest_proposal_depart_step"],
    )
    deadline = state.get("coordination_deadline_step")
    pending_proposal = state.get("pending_proposal")
    if (
        mechanisms["interaction"]
        and mechanisms["planning"]
        and state["role"] == "coordinator"
        and route_id is not None
        and not has_compatible_commitment
        and pending_proposal is None
        and (deadline is None or state["step"] <= deadline)
    ):
        outgoing.append(
            {
                "to": state["partner_id"],
                "kind": "proposal",
                "content": (
                    f"Coordinate evacuation via {route_id} at step "
                    f"{proposal_depart_step} using {state['vehicle_id']}."
                ),
                "payload": {
                    "route_id": route_id,
                    "vehicle_id": state["vehicle_id"],
                    "depart_step": proposal_depart_step,
                },
            }
        )

    if not known_emergency:
        action = "stay"
    elif incoming_proposals and not has_compatible_commitment:
        action = "prepare"
    elif state["step"] < depart_step:
        action = "prepare"
    elif route_id is None:
        action = "prepare"
    elif mechanisms["interaction"] and not has_compatible_commitment:
        action = "prepare"
    else:
        action = "evacuate"

    remember: list[str] = []
    if warning_now:
        remember.append("Official evacuation warning received.")
    if route_closed and mechanisms["feedback"]:
        remember.append("The planned route is closed; update the plan.")

    out.update(
        {
            "assessment": (
                f"controlled policy: action={action}, route={route_id}, "
                f"commitment={has_compatible_commitment}"
            ),
            "action": action,
            "destination_id": "controlled_safe_zone"
            if action == "evacuate"
            else None,
            "route_id": route_id,
            "vehicle_id": state["vehicle_id"] if route_id else None,
            "depart_step": depart_step if route_id else None,
            "accompany_dependents": (
                state["dependent_ids"]
                if state["role"] == "coordinator"
                else []
            ),
            "messages": outgoing,
            "message_responses": responses,
            "remember": remember,
        }
    )
    return out


def _controlled_state(messages: list[dict]) -> dict:
    for message in reversed(messages):
        content = message.get("content", "")
        marker = "CONTROLLED_STATE_JSON="
        if content.startswith(marker):
            return json.loads(content[len(marker) :])
    raise ValueError("controlled Carr policy did not receive state JSON")
