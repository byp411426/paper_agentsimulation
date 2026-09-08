"""Natural-timing Carr-S resident used only by the E1 empirical scenario.

Unlike the controlled E2 adapter, this resident is never given a target
departure step or an initialized route plan.  It still uses the same household,
interaction, world-arbitration, gateway, and kernel interfaces.
"""

from __future__ import annotations

import json
from typing import Any

from ds.agents.carr import CarrResident
from ds.agents.decide import ResidentDecision


class CarrEmpiricalResident(CarrResident):
    """Carr resident with event-driven reconsideration and natural timing."""

    def __init__(
        self,
        *args: Any,
        household_profile: dict[str, Any],
        followup_interval_steps: int = 4,
        step_minutes: int = 30,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if followup_interval_steps < 1:
            raise ValueError("followup_interval_steps must be positive")
        if step_minutes < 1:
            raise ValueError("step_minutes must be positive")
        self.household_profile = dict(household_profile)
        self.followup_interval_steps = followup_interval_steps
        self.step_minutes = step_minutes
        self.first_order_received_step: int | None = None
        self.last_decision_step: int | None = None
        self.next_scheduled_wake_step: int | None = None
        self._last_hazard_band = "far"

    def should_wake(self, *, events: list, world: Any, step: int) -> bool:
        if (
            not self.static.decision_capable
            or self.static.decision_policy == "dependent"
            or world.is_safe(self.id)
        ):
            return False
        if self.inbox:
            return True
        if self.state.last_outcome == "rejected" and (
            self.last_decision_step is None
            or step > self.last_decision_step
        ):
            return True
        if self.plan is not None and self.plan.status != "completed":
            if self.plan.status == "blocked" or self.plan.depart_step <= step:
                return True
        if any(
            commitment.status == "accepted"
            and commitment.depart_step is not None
            and commitment.depart_step <= step
            for commitment in self.household.commitments.values()
        ):
            return True
        if (
            self.next_scheduled_wake_step is not None
            and step >= self.next_scheduled_wake_step
        ):
            return True

        distance = float(world.distance_to_fire(self.state.location))
        hazard_band = (
            "critical" if distance < 1500 else "near" if distance < 3000 else "far"
        )
        if hazard_band != self._last_hazard_band:
            self._last_hazard_band = hazard_band
            return hazard_band != "far"
        return False

    async def decide(
        self,
        *,
        events: list,
        world: Any,
        gateway: Any,
        step: int,
    ) -> ResidentDecision:
        for item in self.inbox:
            if item.get("channel") != "official":
                continue
            text = str(item.get("content", "")).lower()
            if "mandatory" in text or "voluntary" in text or "order" in text:
                if self.first_order_received_step is None:
                    self.first_order_received_step = step
        return await super().decide(
            events=events,
            world=world,
            gateway=gateway,
            step=step,
        )

    def commit_execution(
        self,
        decision: ResidentDecision,
        outcome: Any,
        *,
        step: int,
    ) -> None:
        super().commit_execution(decision, outcome, step=step)
        self.last_decision_step = step
        if self.state.evacuating:
            self.next_scheduled_wake_step = None
            return
        if self.state.last_outcome == "rejected":
            self.next_scheduled_wake_step = step + 1
            return
        candidates = [step + self.followup_interval_steps]
        if self.plan is not None and self.plan.status != "completed":
            candidates.append(max(step + 1, int(self.plan.depart_step)))
        active_departures = [
            int(commitment.depart_step)
            for commitment in self.household.commitments.values()
            if commitment.status == "accepted"
            and commitment.depart_step is not None
            and int(commitment.depart_step) > step
        ]
        candidates.extend(active_departures)
        self.next_scheduled_wake_step = min(candidates)

    def snapshot(self) -> dict[str, Any]:
        base = super().snapshot()
        base.update(
            {
                "first_order_received_step": self.first_order_received_step,
                "last_decision_step": self.last_decision_step,
                "next_scheduled_wake_step": self.next_scheduled_wake_step,
            }
        )
        return base

    def _carr_messages(self, *, world: Any, step: int) -> list[dict[str, str]]:
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
        accepted_signatures = {
            (
                item["route_id"],
                item["vehicle_id"],
                item["depart_step"],
            )
            for item in accepted
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
                "last_failure": self.plan.last_failure,
            }
            if self.plan is not None
            else None
        )
        vehicle_states = [
            {
                "vehicle_id": vehicle.id,
                "location": vehicle.location,
                "capacity": vehicle.capacity,
                "available_seats": vehicle.available_seats,
                "reserved_by": vehicle.reserved_by,
                "occupied_by": sorted(vehicle.occupied_by),
            }
            for vehicle in sorted(
                self.household.vehicles.values(), key=lambda item: item.id
            )
        ]
        state = {
            "prompt_version": self.prompt_version,
            "scenario_semantics": (
                "Carr-informed controlled scenario; not a historical reconstruction"
            ),
            "step": step,
            "minutes_per_step": self.step_minutes,
            "hours_since_scenario_start": (
                step * self.step_minutes / 60
            ),
            "agent_id": self.id,
            "role": self.role,
            "resident_profile": {
                "persona": self.persona,
                "age": self.static.age,
                "functional_limitations": {
                    key: value
                    for key, value in sorted(
                        self.static.functional_limitations.items()
                    )
                    if value
                },
            },
            "household_profile": self.household_profile,
            "household_id": self.static.household_id,
            "decision_member_ids": list(self.household.decision_member_ids),
            "dependent_ids": list(self.dependent_ids),
            "partner_id": self.partner_id,
            "inbox": inbox,
            "warning_memory": any(
                item.kind == "warning" for item in self.memory.items
            ),
            "recent_memories": self.memory.recall(step, k=8),
            "hazard_distance_m": world.distance_to_fire(self.state.location),
            "routes": world.route_snapshot(),
            "household_vehicles": vehicle_states,
            "current_plan": current_plan,
            "accepted_commitments": accepted,
            "pending_proposal": pending_proposal,
            "earliest_proposal_depart_step": step + 1,
            "recent_execution_feedback": self.feedback_events[-3:],
        }
        return [
            {
                "role": "system",
                "content": (
                    "You are one adult resident in a controlled wildfire social "
                    "simulation. Decide only from EMPIRICAL_STATE_JSON. There is "
                    "no preset departure time and no hidden household agreement. "
                    "Return one JSON object matching these fields: assessment; "
                    "action (stay|prepare|evacuate|seek_help|offer_help); "
                    "destination_id, route_id, vehicle_id; depart_step; "
                    "accompany_dependents; messages; message_responses; remember. "
                    "Use only supplied IDs and open routes. If evacuating now, set "
                    "depart_step to the current step. A future plan may choose any "
                    "later step within the scenario. In a multi-decision-member "
                    "household, a shared-vehicle joint departure requires an "
                    "actually accepted proposal; never pretend family members "
                    "already agreed. Proposal payload must contain route_id, "
                    "vehicle_id, and an integer depart_step no earlier than "
                    "earliest_proposal_depart_step. Respond only to message IDs in "
                    "inbox. A resident without an available household vehicle may "
                    "seek help or send a notice to neighbors, but must not invent a "
                    "vehicle. Use destination_id=controlled_safe_zone only for an "
                    "evacuation. The coordinator is responsible for listing all "
                    "dependent IDs unless a received message explicitly reassigns "
                    "care. Follow an accepted commitment exactly while feasible; "
                    "after a rejected execution, use the recorded failure to revise "
                    "the plan instead of repeating an impossible request. Return "
                    "JSON only."
                ),
            },
            {
                "role": "user",
                "content": "EMPIRICAL_STATE_JSON="
                + json.dumps(state, sort_keys=True, separators=(",", ":")),
            },
        ]
