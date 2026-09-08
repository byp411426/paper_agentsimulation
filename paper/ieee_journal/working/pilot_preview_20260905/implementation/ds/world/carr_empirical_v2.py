"""Carr E1 v2 world: real route state, hazard, and party arbitration."""

from __future__ import annotations

from typing import Any

from ds.households.state import (
    DepartureParty,
    Household,
    HouseholdCommitmentV2,
)
from ds.kernel.actions import ExecutionOutcome, IntentEnvelope, ResolvedIntent
from ds.kernel.clock import Clock
from ds.kernel.rng import stream_rng


class CarrEmpiricalWorldV2:
    """Real physical state for E1 v2; residents hold private beliefs."""

    def __init__(
        self,
        *,
        households: dict[str, Household],
        residents: dict[str, Any],
        config: dict[str, Any],
        run_seed: int,
    ):
        self.households = households
        self.residents = residents
        self.config = config
        self.run_seed = run_seed
        self.safe_zone = config.get("safe_zone", "controlled_safe_zone")
        capacity = int(config.get("route_capacity_per_step", 10))
        self.route_state = {
            route_id: {"open": True, "capacity_per_step": capacity}
            for route_id in (
                config.get("primary_route_id", "primary"),
                config.get("alternate_route_id", "alternate"),
            )
        }
        self.closure_step = int(config.get("closure_step", 9))
        self.member_locations = {
            member_id: ("home", household.id)
            for household in households.values()
            for member_id in household.member_ids
        }
        self.route_usage: dict[str, int] = {}
        self._step = 0
        self._care_requirements = config.get("care_requirements", {})
        self.hazard_offsets = {
            household_id: -250.0
            + 500.0
            * stream_rng(
                run_seed,
                "e1_hazard_offset",
                entity_id=household_id,
            ).random()
            for household_id in households
        }

    # ---- protocol hooks --------------------------------------------------- #
    def update(self, clock: Clock) -> None:
        self._step = clock.t
        if self._step >= self.closure_step:
            self.route_state[self.config.get("primary_route_id", "primary")][
                "open"
            ] = False
        self.route_usage = {}

    def apply_events(self, events: list, clock: Clock) -> None:
        for event in events:
            if event.kind == "route_closure":
                route_id = event.route_id
                if route_id in self.route_state:
                    self.route_state[route_id]["open"] = False

    # ---- queries ---------------------------------------------------------- #
    def hazard_distance_for(self, household_id: str, step: int) -> float:
        offset = self.hazard_offsets[household_id]
        return max(
            0.0,
            float(self.config.get("initial_distance_m", 9000))
            + offset
            - float(self.config.get("approach_per_step_m", 250)) * step,
        )

    def party_due_for(self, agent_id: str, step: int) -> bool:
        resident = self.residents[agent_id]
        household = self.households[resident.household_id]
        return any(
            agent_id in commitment.party.traveler_ids
            and commitment.party.depart_step == step
            for commitment in household.active_v2_parties()
        )

    def visible_reservations(self, household_id: str, viewer_id: str) -> list[dict]:
        household = self.households[household_id]
        return [
            {
                "vehicle_id": vehicle.id,
                "reserved_by": vehicle.reserved_by,
                "location": vehicle.location,
                "occupied": len(vehicle.occupied_by),
                "capacity": vehicle.capacity,
            }
            for vehicle in household.vehicles.values()
        ]

    def member_summaries(self, household_id: str) -> list[dict]:
        household = self.households[household_id]
        profile_members = {
            member.get("resident_id"): member
            for member in getattr(household, "profile", {}).get(
                "member_profiles", []
            )
        }
        return [
            {
                "resident_id": member_id,
                "location": self.member_locations.get(member_id, ("home", household_id)),
                "age": profile_members.get(member_id, {}).get("age"),
                "relationship": profile_members.get(member_id, {}).get(
                    "relationship"
                ),
                "needs_execution_assistance": profile_members.get(
                    member_id, {}
                ).get("needs_execution_assistance", False),
            }
            for member_id in household.member_ids
        ]

    def vehicle_summaries(self, household_id: str) -> list[dict]:
        return [
            {
                "id": vehicle.id,
                "capacity": vehicle.capacity,
                "location": vehicle.location,
                "reserved_by": vehicle.reserved_by,
            }
            for vehicle in self.households[household_id].vehicles.values()
        ]

    def housing_summary(self, household_id: str) -> dict:
        profile = getattr(self.households[household_id], "profile", {})
        return profile.get("shared_attributes", {})

    def pet_state(self, household_id: str) -> bool:
        profile = getattr(self.households[household_id], "profile", {})
        return bool(profile.get("shared_attributes", {}).get("pet_owned", False))

    def livestock_state(self, household_id: str) -> bool:
        profile = getattr(self.households[household_id], "profile", {})
        return bool(
            profile.get("shared_attributes", {}).get("livestock_owned", False)
        )

    # ---- arbitration ------------------------------------------------------ #
    def _matching_party(self, household: Household, decision: Any, agent_id: str) -> Any | None:
        for commitment in household.active_v2_parties():
            party = commitment.party
            if (
                party.depart_step == self._step
                and agent_id in party.traveler_ids
                and party.route_id == decision.route_id
                and party.vehicle_id == decision.vehicle_id
            ):
                return commitment
        return None

    def resolve_batch(
        self, envelopes: list[IntentEnvelope], clock: Clock, run_seed: int
    ) -> list[ResolvedIntent]:
        resolved = []
        for envelope in envelopes:
            decision = envelope.decision
            if decision.action != "evacuate":
                resolved.append(
                    ResolvedIntent(
                        decision_id=envelope.decision_id,
                        agent_id=envelope.agent_id,
                        agent=envelope.agent,
                        decision=decision,
                        action=("noop", decision.action),
                    )
                )
                continue
            household = self.households[envelope.agent.household_id]
            if self.member_locations.get(envelope.agent_id) != ("home", household.id):
                resolved.append(ResolvedIntent(decision_id=envelope.decision_id,
                    agent_id=envelope.agent_id, agent=envelope.agent, decision=decision,
                    action=("rejected", "resident_not_at_origin")))
                continue
            party = self._matching_party(household, decision, envelope.agent_id)
            if party is None:
                # Auto-form a party from a valid evacuation intent when no
                # message-formed commitment exists.  Travelers = the
                # evacuating adult; accompanying = care recipients needing
                # assistance; caregiver = the evacuating adult.  Messages
                # remain the coordination channel and may form or revise
                # parties at later steps.
                if decision.vehicle_id and decision.route_id:
                    depart_step = max(
                        int(decision.depart_step or self._step), self._step
                    )
                    accompanying = frozenset(
                        member_id
                        for member_id in household.dependent_ids
                        if member_id in self._care_requirements
                        and self.member_locations.get(member_id) == ("home", household.id)
                    )
                    caregiver_by_member = tuple(
                        (member_id, envelope.agent_id)
                        for member_id in accompanying
                    )
                    commitment = HouseholdCommitmentV2(
                        id=f"auto_{envelope.decision_id}",
                        protocol_version="e1_party_v2",
                        party=DepartureParty(
                            traveler_ids=frozenset({envelope.agent_id}),
                            accompanying_member_ids=accompanying,
                            caregiver_by_member=caregiver_by_member,
                            vehicle_id=decision.vehicle_id,
                            route_id=decision.route_id,
                            depart_step=depart_step,
                        ),
                        accepted_by=frozenset({envelope.agent_id}),
                        created_step=self._step,
                    )
                    accepted = household.try_accept_commitment_v2(
                        commitment=commitment,
                        decision_capable={
                            member_id: member_id == envelope.agent_id
                            for member_id in household.decision_member_ids
                        },
                        care_requirements={
                            member_id: self._care_requirements[member_id]
                            for member_id in accompanying
                        },
                        earliest_depart_step=self._step,
                        party_origin=("home", household.id),
                    )
                    if accepted.accepted:
                        resolved.append(
                            ResolvedIntent(
                                decision_id=envelope.decision_id,
                                agent_id=envelope.agent_id,
                                agent=envelope.agent,
                                decision=decision,
                                action=("party", commitment.id),
                            )
                        )
                        continue
                resolved.append(
                    ResolvedIntent(
                        decision_id=envelope.decision_id,
                        agent_id=envelope.agent_id,
                        agent=envelope.agent,
                        decision=decision,
                        action=("rejected", "no_matching_party"),
                    )
                )
                continue
            resolved.append(
                ResolvedIntent(
                    decision_id=envelope.decision_id,
                    agent_id=envelope.agent_id,
                    agent=envelope.agent,
                    decision=decision,
                    action=("party", party.id),
                )
            )
        return resolved

    def apply_batch(
        self, resolved: list[ResolvedIntent], clock: Clock
    ) -> dict[str, ExecutionOutcome]:
        outcomes: dict[str, ExecutionOutcome] = {}
        by_party: dict[tuple[str, str], list[ResolvedIntent]] = {}
        for intent in resolved:
            kind = intent.action[0]
            if kind == "party":
                household_id = intent.agent.household_id
                by_party.setdefault((household_id, intent.action[1]), []).append(
                    intent
                )

        for (household_id, commitment_id), intents in by_party.items():
            household = self.households[household_id]
            commitment = household.v2_commitments.get(commitment_id)
            if commitment is None or commitment.status != "accepted":
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id,
                        agent_id=intent.agent_id,
                        status="rejected",
                        executed_action="evacuate",
                        reason="party_not_active",
                    )
                continue
            if commitment.party.depart_step != clock.t:
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="party_not_due")
                continue
            if any(self.member_locations.get(m) != ("home", household_id)
                   for m in commitment.party.member_ids):
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="party_member_not_at_origin")
                continue
            route_id = commitment.party.route_id
            if route_id not in self.route_state:
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="unknown_route")
                continue
            if (
                not self.route_state[route_id]["open"]
                or self.route_usage.get(route_id, 0)
                >= self.route_state[route_id]["capacity_per_step"]
            ):
                reason = (
                    "route_closed"
                    if not self.route_state[route_id]["open"]
                    else "route_capacity_exhausted"
                )
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id,
                        agent_id=intent.agent_id,
                        status="rejected",
                        executed_action="evacuate",
                        reason=reason,
                    )
                continue
            traveler_intents = {
                intent.agent_id for intent in intents
            }
            record = household.execute_v2_party(
                commitment=commitment,
                step=clock.t,
                traveler_intents=traveler_intents,
                origin=("home", household_id),
                destination=self.safe_zone,
            )
            executed = record.outcome == "executed"
            if executed:
                self.route_usage[route_id] = self.route_usage.get(route_id, 0) + 1
            for intent in intents:
                outcomes[intent.decision_id] = ExecutionOutcome(
                    decision_id=intent.decision_id,
                    agent_id=intent.agent_id,
                    status="executed" if executed else "rejected",
                    executed_action="evacuate",
                    reason=record.reason_code,
                )
            if executed:
                for member_id in (
                    commitment.party.traveler_ids
                    | commitment.party.accompanying_member_ids
                ):
                    self.member_locations[member_id] = self.safe_zone

        for intent in resolved:
            if intent.decision_id in outcomes:
                continue
            if intent.action[0] == "rejected":
                outcomes[intent.decision_id] = ExecutionOutcome(
                    decision_id=intent.decision_id,
                    agent_id=intent.agent_id,
                    status="rejected",
                    executed_action=None,
                    reason=intent.action[1],
                )
                continue
            outcomes[intent.decision_id] = ExecutionOutcome(
                decision_id=intent.decision_id,
                agent_id=intent.agent_id,
                status="executed",
                executed_action=intent.action[1],
            )
        return outcomes

    def snapshot(self) -> dict:
        return {
            "step": self._step,
            "route_state": self.route_state,
            "hazard_offsets": self.hazard_offsets,
            "household_commitments": {
                hh.id: {c.id: {"id": c.id, "created_step": c.created_step,
                    "status": c.status, "supersedes_id": c.supersedes_id,
                    "accepted_by": sorted(c.accepted_by),
                    "party": {"traveler_ids": sorted(c.party.traveler_ids),
                        "accompanying_member_ids": sorted(c.party.accompanying_member_ids),
                        "route_id": c.party.route_id, "vehicle_id": c.party.vehicle_id,
                        "depart_step": c.party.depart_step}}
                    for c in hh.v2_commitments.values()} for hh in self.households.values()},
            "member_locations": {
                key: str(value) for key, value in self.member_locations.items()
            },
        }
