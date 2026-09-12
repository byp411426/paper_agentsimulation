"""Carr E1 v2 world: real route state, hazard, and party arbitration."""

from __future__ import annotations

from typing import Any
from dataclasses import replace
from copy import deepcopy

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
        self.observation_records: dict[str, dict] = {}
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
        for household in self.households.values():
            for c in household.active_v2_parties():
                if c.party.depart_step < clock.t:
                    household.v2_commitments[c.id] = replace(c, status='cancelled')
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

    def observe_resident(self, resident_id: str, step: int) -> dict:
        """Record the local observations actually supplied at decision time.

        This interface exposes the same hazard/resources as the existing prompt;
        it does not reveal the world's hidden route closures.
        """
        hid = self.residents[resident_id].household_id
        observation_id = f"observation:{step}:{resident_id}"
        record = {
            "observation_id": observation_id,
            "resident_id": resident_id,
            "step": step,
            "phase": "before_decision",
            "content": {
                "hazard_distance_m": self.hazard_distance_for(hid, step),
                "shared_resource_reservations": self.visible_reservations(hid, resident_id),
            },
        }
        self.observation_records[observation_id] = deepcopy(record)
        return deepcopy(record)

    def physical_snapshot(self, household_id: str | None = None) -> dict:
        """Copy authoritative physical facts, independent of resident beliefs."""
        households = (self.households.values() if household_id is None
                      else [self.households[household_id]])
        households = list(households)
        member_ids = {m for hh in households for m in hh.member_ids}
        return deepcopy({
            "member_locations": {m: self.member_locations[m] for m in sorted(member_ids)},
            "vehicles": {
                hh.id: {v.id: {"id": v.id, "location": v.location,
                    "capacity": v.capacity, "occupied_by": sorted(v.occupied_by),
                    "reserved_by": v.reserved_by} for v in hh.vehicles.values()}
                for hh in households
            },
            "route_usage": self.route_usage,
        })

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

    def commitment_statuses_for(self, resident_id: str) -> list[dict]:
        household = self.households[self.residents[resident_id].household_id]
        return [{'commitment_id': c.id, 'status': c.status,
                 'depart_step': c.party.depart_step, 'route_id': c.party.route_id,
                 'vehicle_id': c.party.vehicle_id, 'traveler_ids': sorted(c.party.traveler_ids)}
                for c in household.v2_commitments.values() if resident_id in c.accepted_by]

    def resolve_batch(self, envelopes, clock, run_seed):
        """Read-only proposal validation; all resource changes occur at commit."""
        resolved = []
        for e in envelopes:
            d=e.decision; hh=self.households[e.agent.household_id]
            if d.action != 'evacuate':
                action=('noop',d.action)
            elif self.member_locations.get(e.agent_id) != ('home',hh.id):
                action=('rejected','resident_not_at_origin')
            elif getattr(d,'departure_mode',None)=='commitment':
                c=hh.v2_commitments.get(d.commitment_id)
                if c is None or c.status!='accepted':
                    action=('rejected','commitment_not_active')
                elif e.agent_id not in c.party.traveler_ids:
                    action=('rejected','not_a_traveler')
                elif d.depart_step is None or not d.route_id or not d.vehicle_id:
                    action=('rejected','incomplete_departure_request')
                elif d.depart_step != clock.t:
                    action=('rejected','departure_not_due')
                elif (c.party.depart_step,c.party.route_id,c.party.vehicle_id)!=(d.depart_step,d.route_id,d.vehicle_id):
                    action=('rejected','current_intent_commitment_mismatch')
                else:
                    action=('party',c.id)
            elif getattr(d,'departure_mode',None)=='solo':
                companions=frozenset(d.accompany_dependents)
                if getattr(d, 'party_proposal', None) is not None:
                    action=('rejected','conflicting_solo_and_joint_proposal')
                elif d.depart_step is None or not d.route_id or not d.vehicle_id:
                    action=('rejected','incomplete_departure_request')
                elif d.depart_step != clock.t:
                    action=('rejected','departure_not_due')
                elif not companions <= set(hh.dependent_ids):
                    action=('rejected','invalid_accompanying_members')
                elif any(self.member_locations.get(m)!=('home',hh.id) for m in companions):
                    action=('rejected','party_member_not_at_origin')
                else:
                    action=('solo',None)
            else:
                action=('rejected','explicit_departure_mode_required')
            resolved.append(ResolvedIntent(decision_id=e.decision_id,agent_id=e.agent_id,
                agent=e.agent,decision=d,action=action))
        return resolved

    def apply_batch(self, resolved, clock):
        outcomes={}; groups={}
        def finish(intent,status,reason=None,commitment=None,physical_before=None):
            allocations = {}
            delta = {'commitment_id':commitment} if commitment else {}
            if physical_before is not None:
                delta.update(physical_before=physical_before,
                             physical_after=self.physical_snapshot(intent.agent.household_id))
            if status == 'executed' and intent.decision.action == 'evacuate':
                allocations = {'vehicle_id': intent.decision.vehicle_id,
                               'route_id': intent.decision.route_id,
                               'party_id': commitment}
            outcomes[intent.decision_id]=ExecutionOutcome(
                decision_id=intent.decision_id,agent_id=intent.agent_id,status=status,
                requested_action=intent.decision.action,
                executed_action=intent.decision.action if status=='executed' else None,
                reason=reason, resource_allocations=allocations, state_delta=delta)
        ordered=sorted(resolved,key=lambda x:x.agent_id)
        stream_rng(self.run_seed,'e1_world_commit',step=clock.t).shuffle(ordered)
        for intent in ordered:
            kind,cid=intent.action;hh=self.households[intent.agent.household_id]
            if kind=='rejected':
                finish(intent,'rejected',cid);continue
            if kind=='noop':
                finish(intent,'executed');continue
            if kind=='solo':
                d=intent.decision;companions=frozenset(d.accompany_dependents)
                cid='auto_'+intent.decision_id
                c=HouseholdCommitmentV2(id=cid,protocol_version='e1_party_v2',
                    party=DepartureParty(traveler_ids=frozenset({intent.agent_id}),
                        accompanying_member_ids=companions,
                        caregiver_by_member=tuple((m,intent.agent_id) for m in sorted(companions)),
                        vehicle_id=d.vehicle_id,route_id=d.route_id,depart_step=clock.t),
                    accepted_by=frozenset({intent.agent_id}),created_step=clock.t)
                accepted=hh.try_accept_commitment_v2(commitment=c,
                    decision_capable={m:True for m in hh.decision_member_ids},
                    care_requirements=self._care_requirements,earliest_depart_step=clock.t,
                    party_origin=('home',hh.id))
                if not accepted.accepted:
                    finish(intent,'rejected',accepted.reason_code);continue
            groups.setdefault((hh.id,cid),[]).append(intent)
        for (hid,cid),intents in groups.items():
            hh=self.households[hid];c=hh.v2_commitments[cid];party=c.party
            physical_before = self.physical_snapshot(hid)
            reason=None
            if c.status!='accepted':reason='party_not_active'
            elif party.depart_step!=clock.t:reason='party_not_due'
            elif any(self.member_locations.get(m)!=('home',hid) for m in party.member_ids):reason='party_member_not_at_origin'
            elif party.route_id not in self.route_state:reason='unknown_route'
            elif not self.route_state[party.route_id]['open']:reason='route_closed'
            elif self.route_usage.get(party.route_id,0)>=self.route_state[party.route_id]['capacity_per_step']:reason='route_capacity_exhausted'
            if reason:
                hh.v2_commitments[cid]=replace(c,status='rejected')
                for intent in intents:finish(intent,'rejected',reason,cid,physical_before)
                continue
            record=hh.execute_v2_party(commitment=c,step=clock.t,
                traveler_intents={i.agent_id for i in intents},origin=('home',hid),destination=self.safe_zone)
            if record.outcome=='executed':
                self.route_usage[party.route_id]=self.route_usage.get(party.route_id,0)+1
                for m in party.member_ids:self.member_locations[m]=self.safe_zone
            for intent in intents:finish(intent,record.outcome,record.reason_code,cid,physical_before)
        return outcomes

    def snapshot(self) -> dict:
        return deepcopy({
            "log_schema_version": "e1_evaluation_v1",
            "step": self._step,
            "route_state": self.route_state,
            "hazard_offsets": self.hazard_offsets,
            "vehicles": self.physical_snapshot()["vehicles"],
            "route_usage": self.route_usage,
            "observations": list(self.observation_records.values()),
            "household_commitments": {
                hh.id: {c.id: {"id": c.id, "created_step": c.created_step,
                    "status": c.status, "supersedes_id": c.supersedes_id,
                    "accepted_by": sorted(c.accepted_by),
                    "party": {"traveler_ids": sorted(c.party.traveler_ids),
                        "accompanying_member_ids": sorted(c.party.accompanying_member_ids),
                        "caregiver_by_member": dict(c.party.caregiver_by_member),
                        "route_id": c.party.route_id, "vehicle_id": c.party.vehicle_id,
                        "depart_step": c.party.depart_step}}
                    for c in hh.v2_commitments.values()} for hh in self.households.values()},
            "member_locations": {
                key: str(value) for key, value in self.member_locations.items()
            },
        })
