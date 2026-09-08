"""Household is shared state and constraints, never a replacement LLM agent."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from ds.kernel.rng import stream_seed


@dataclass
class VehicleResource:
    id: str
    location: object
    capacity: int
    occupied_by: set[str] = field(default_factory=set)
    reserved_by: str | None = None

    @property
    def available_seats(self) -> int:
        return self.capacity - len(self.occupied_by)


@dataclass(frozen=True)
class HouseholdCommitment:
    id: str
    proposal: str
    accepted_by: frozenset[str]
    created_step: int
    route_id: str | None = None
    vehicle_id: str | None = None
    depart_step: int | None = None
    status: Literal["accepted", "cancelled"] = "accepted"
    supersedes_id: str | None = None


@dataclass(frozen=True)
class DepartureParty:
    traveler_ids: frozenset[str]
    accompanying_member_ids: frozenset[str]
    caregiver_by_member: tuple[tuple[str, str], ...]
    vehicle_id: str
    route_id: str
    depart_step: int

    @property
    def member_ids(self) -> frozenset[str]:
        return self.traveler_ids | self.accompanying_member_ids


@dataclass(frozen=True)
class HouseholdCommitmentV2:
    id: str
    protocol_version: Literal["e1_party_v2"]
    party: DepartureParty
    accepted_by: frozenset[str]
    created_step: int
    status: Literal["accepted", "cancelled", "executed", "rejected"] = "accepted"
    supersedes_id: str | None = None


@dataclass(frozen=True)
class CommitmentAcceptanceResult:
    accepted: bool
    commitment_id: str | None
    reason_code: str | None


@dataclass(frozen=True)
class CareRequirement:
    member_id: str
    assistance_type: Literal[
        "minor", "mobility", "self_care", "independent_living"
    ]
    caregiver_id: str | None


@dataclass(frozen=True)
class HouseholdDepartureRecord:
    household_id: str
    party_id: str
    commitment_id: str | None
    step: int
    traveler_ids: tuple[str, ...]
    accompanying_member_ids: tuple[str, ...]
    caregiver_by_member: tuple[tuple[str, str], ...]
    vehicle_id: str
    route_id: str
    coordinated: bool
    outcome: Literal["executed", "rejected"]
    reason_code: str | None


@dataclass
class DependentMemberState:
    id: str
    location: object
    safe: bool = False
    caregiver_id: str | None = None
    mobility: Literal["independent", "assisted"] = "assisted"
    in_transit: bool = False


@dataclass(frozen=True)
class VehicleRequest:
    decision_id: str
    agent_id: str
    vehicle_id: str
    request_step: int
    priority: int = 0


@dataclass(frozen=True)
class VehicleAllocation:
    decision_id: str
    agent_id: str
    vehicle_id: str
    status: Literal["allocated", "rejected"]
    reason: str | None = None


@dataclass
class Household:
    id: str
    member_ids: tuple[str, ...]
    decision_member_ids: tuple[str, ...]
    dependent_ids: tuple[str, ...] = ()
    vehicles: dict[str, VehicleResource] = field(default_factory=dict)
    commitments: dict[str, HouseholdCommitment] = field(default_factory=dict)
    v2_commitments: dict[str, HouseholdCommitmentV2] = field(default_factory=dict)
    departure_records: list[HouseholdDepartureRecord] = field(default_factory=list)
    dependent_states: dict[str, DependentMemberState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        members = set(self.member_ids)
        decisions = set(self.decision_member_ids)
        dependents = set(self.dependent_ids)
        if len(members) != len(self.member_ids):
            raise ValueError("household member_ids must be unique")
        if not decisions <= members or not dependents <= members:
            raise ValueError("decision and dependent members must belong to household")
        if decisions & dependents:
            raise ValueError("a member cannot be both decision and dependent")
        if set(self.dependent_states) - dependents:
            raise ValueError("dependent_states keys must belong to dependent_ids")

    def accept_commitment(self, commitment: HouseholdCommitment) -> None:
        if not set(commitment.accepted_by) <= set(self.member_ids):
            raise ValueError("commitment accepted_by includes a non-member")
        if not commitment.accepted_by:
            raise ValueError("accepted commitment needs at least one accepting member")
        active = [
            current
            for current in self.commitments.values()
            if current.status == "accepted" and current.id != commitment.id
        ]
        superseded = (
            max(active, key=lambda current: (current.created_step, current.id))
            if active
            else None
        )
        for current in active:
            self.commitments[current.id] = replace(current, status="cancelled")
        if commitment.supersedes_id is None and superseded is not None:
            commitment = replace(
                commitment,
                supersedes_id=superseded.id,
            )
        self.commitments[commitment.id] = commitment

    def has_feasible_commitment_formation(
        self,
        *,
        route_id: str | None = None,
        min_created_step: int | None = None,
    ) -> bool:
        """Return whether a validated all-decision-member agreement was formed.

        Cancelled commitments remain part of the coordination history, so a
        later revision does not erase evidence that an earlier agreement was
        successfully formed.
        """
        required = set(self.decision_member_ids)
        return any(
            required <= set(commitment.accepted_by)
            and bool(commitment.route_id)
            and commitment.vehicle_id in self.vehicles
            and isinstance(commitment.depart_step, int)
            and not isinstance(commitment.depart_step, bool)
            and (route_id is None or commitment.route_id == route_id)
            and (
                min_created_step is None
                or commitment.created_step >= min_created_step
            )
            for commitment in self.commitments.values()
        )

    def compatible_commitment(
        self,
        *,
        route_id: str,
        vehicle_id: str,
        depart_step: int,
    ) -> HouseholdCommitment | None:
        required = set(self.decision_member_ids)
        candidates = [
            commitment
            for commitment in self.commitments.values()
            if commitment.status == "accepted"
            and commitment.route_id == route_id
            and commitment.vehicle_id == vehicle_id
            and commitment.depart_step == depart_step
            and required <= set(commitment.accepted_by)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda commitment: commitment.created_step)

    def active_v2_parties(self) -> list[HouseholdCommitmentV2]:
        """Accepted, not-yet-executed v2 commitments (revisions excluded)."""
        return [
            commitment
            for commitment in self.v2_commitments.values()
            if commitment.status == "accepted"
        ]

    def try_accept_commitment_v2(
        self,
        *,
        commitment: HouseholdCommitmentV2,
        decision_capable: dict[str, bool],
        care_requirements: dict[str, CareRequirement],
        earliest_depart_step: int,
        party_origin: object,
    ) -> CommitmentAcceptanceResult:
        """Structured acceptance for the e1_party_v2 protocol (W4 contract).

        Ordinary resource conflicts return a rejected result with a reason
        code; they never raise a run-level exception.
        """
        members = set(self.member_ids)
        party = commitment.party
        all_party_members = party.member_ids
        party_accepters = set(commitment.accepted_by)
        caregivers = dict(party.caregiver_by_member)

        if not all_party_members <= members:
            return CommitmentAcceptanceResult(False, None, "not_same_household")
        if not party_accepters <= members:
            return CommitmentAcceptanceResult(False, None, "accepter_not_member")
        if not party.traveler_ids:
            return CommitmentAcceptanceResult(False, None, "empty_travelers")

        missing_acceptance = [
            member
            for member in party.traveler_ids
            if decision_capable.get(member, False)
            and member not in party_accepters
        ]
        if missing_acceptance:
            return CommitmentAcceptanceResult(
                False, None, "missing_decision_acceptance"
            )

        assisted = [
            member
            for member in party.accompanying_member_ids
            if member in care_requirements
        ]
        for member in assisted:
            if member not in caregivers:
                return CommitmentAcceptanceResult(False, None, "missing_caregiver")
        if any(
            caregiver not in party.traveler_ids
            for caregiver in caregivers.values()
        ):
            return CommitmentAcceptanceResult(False, None, "caregiver_not_traveler")

        vehicle = self.vehicles.get(party.vehicle_id)
        if vehicle is None:
            return CommitmentAcceptanceResult(False, None, "vehicle_unknown")
        if vehicle.capacity < len(all_party_members):
            return CommitmentAcceptanceResult(False, None, "vehicle_capacity")
        if vehicle.location != party_origin:
            return CommitmentAcceptanceResult(False, None, "vehicle_not_at_origin")
        if not party.route_id:
            return CommitmentAcceptanceResult(False, None, "empty_route")
        if party.depart_step < earliest_depart_step:
            return CommitmentAcceptanceResult(False, None, "depart_step_too_early")

        supersedes_id = commitment.supersedes_id
        for active in self.active_v2_parties():
            if active.id == commitment.id:
                continue
            overlaps = (
                active.party.vehicle_id == party.vehicle_id
                or bool(active.party.member_ids & all_party_members)
            )
            if not overlaps:
                continue
            if supersedes_id == active.id:
                self.v2_commitments[active.id] = replace(
                    active,
                    status="cancelled",
                    supersedes_id=commitment.id,
                )
                continue
            reason = (
                "vehicle_in_use"
                if active.party.vehicle_id == party.vehicle_id
                else "member_overlap"
            )
            return CommitmentAcceptanceResult(False, None, reason)
        accepted = replace(
            commitment,
            status="accepted",
            supersedes_id=supersedes_id,
        )
        self.v2_commitments[commitment.id] = accepted
        return CommitmentAcceptanceResult(True, commitment.id, None)

    def execute_v2_party(
        self,
        *,
        commitment: HouseholdCommitmentV2,
        step: int,
        traveler_intents: set[str],
        origin: object,
        destination: object,
    ) -> HouseholdDepartureRecord:
        """Execute a due v2 party under the W4 world contract.

        Every decision-capable traveler must submit a matching intent; missing
        intents reject the whole party.  Non-decision members move with the
        verified party.  Each call returns exactly one departure record.
        """
        party = commitment.party
        vehicle = self.vehicles[party.vehicle_id]
        missing = [
            member
            for member in party.traveler_ids
            if member not in traveler_intents
        ]
        if missing:
            record = HouseholdDepartureRecord(
                household_id=self.id,
                party_id=commitment.id,
                commitment_id=commitment.id,
                step=step,
                traveler_ids=tuple(sorted(party.traveler_ids)),
                accompanying_member_ids=tuple(
                    sorted(party.accompanying_member_ids)
                ),
                caregiver_by_member=party.caregiver_by_member,
                vehicle_id=party.vehicle_id,
                route_id=party.route_id,
                coordinated=set(self.decision_member_ids)
                <= set(party.traveler_ids),
                outcome="rejected",
                reason_code="missing_traveler_intent",
            )
            self.v2_commitments[commitment.id] = replace(
                commitment, status="rejected"
            )
            self.departure_records.append(record)
            return record
        if vehicle.location != origin:
            record = HouseholdDepartureRecord(
                household_id=self.id,
                party_id=commitment.id,
                commitment_id=commitment.id,
                step=step,
                traveler_ids=tuple(sorted(party.traveler_ids)),
                accompanying_member_ids=tuple(
                    sorted(party.accompanying_member_ids)
                ),
                caregiver_by_member=party.caregiver_by_member,
                vehicle_id=party.vehicle_id,
                route_id=party.route_id,
                coordinated=set(self.decision_member_ids)
                <= set(party.traveler_ids),
                outcome="rejected",
                reason_code="vehicle_not_at_origin",
            )
            self.v2_commitments[commitment.id] = replace(
                commitment, status="rejected"
            )
            self.departure_records.append(record)
            return record
        vehicle.location = destination
        record = HouseholdDepartureRecord(
            household_id=self.id,
            party_id=commitment.id,
            commitment_id=commitment.id,
            step=step,
            traveler_ids=tuple(sorted(party.traveler_ids)),
            accompanying_member_ids=tuple(sorted(party.accompanying_member_ids)),
            caregiver_by_member=party.caregiver_by_member,
            vehicle_id=party.vehicle_id,
            route_id=party.route_id,
            coordinated=set(self.decision_member_ids) <= set(party.traveler_ids),
            outcome="executed",
            reason_code=None,
        )
        self.v2_commitments[commitment.id] = replace(
            commitment, status="executed"
        )
        self.departure_records.append(record)
        return record

    def resolve_vehicle_requests(
        self,
        requests: list[VehicleRequest],
        *,
        run_seed: int,
        step: int,
    ) -> dict[str, VehicleAllocation]:
        """Resolve one batch without depending on request list order.

        Existing reservation, declared priority and request time are deterministic
        rules. A counter-derived tie-break is used only when those rules cannot
        distinguish requests.
        """
        decision_ids = [request.decision_id for request in requests]
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("vehicle request decision_id must be unique")
        results: dict[str, VehicleAllocation] = {}
        grouped: dict[str, list[VehicleRequest]] = {}
        for request in requests:
            if request.agent_id not in self.member_ids:
                results[request.decision_id] = VehicleAllocation(
                    request.decision_id,
                    request.agent_id,
                    request.vehicle_id,
                    "rejected",
                    "requester is not a household member",
                )
                continue
            grouped.setdefault(request.vehicle_id, []).append(request)

        for vehicle_id, contenders in grouped.items():
            vehicle = self.vehicles.get(vehicle_id)
            if vehicle is None:
                for request in contenders:
                    results[request.decision_id] = VehicleAllocation(
                        request.decision_id,
                        request.agent_id,
                        vehicle_id,
                        "rejected",
                        "unknown household vehicle",
                    )
                continue
            if vehicle.available_seats <= 0:
                for request in contenders:
                    results[request.decision_id] = VehicleAllocation(
                        request.decision_id,
                        request.agent_id,
                        vehicle_id,
                        "rejected",
                        "vehicle has no available seats",
                    )
                continue
            if (
                vehicle.reserved_by is not None
                and all(
                    request.agent_id != vehicle.reserved_by
                    for request in contenders
                )
            ):
                for request in contenders:
                    results[request.decision_id] = VehicleAllocation(
                        request.decision_id,
                        request.agent_id,
                        vehicle_id,
                        "rejected",
                        f"vehicle reserved by {vehicle.reserved_by}",
                    )
                continue

            ordered = sorted(
                contenders,
                key=lambda request: (
                    0 if vehicle.reserved_by == request.agent_id else 1,
                    -request.priority,
                    request.request_step,
                    stream_seed(
                        run_seed,
                        "arbitration",
                        entity_id=f"{self.id}:{vehicle_id}:{request.decision_id}",
                        step=step,
                    ),
                ),
            )
            winner = ordered[0]
            results[winner.decision_id] = VehicleAllocation(
                winner.decision_id,
                winner.agent_id,
                vehicle_id,
                "allocated",
            )
            for request in ordered[1:]:
                results[request.decision_id] = VehicleAllocation(
                    request.decision_id,
                    request.agent_id,
                    vehicle_id,
                    "rejected",
                    f"vehicle allocated to {winner.agent_id}",
                )
        return results

    def commit_vehicle_allocations(
        self,
        allocations: dict[str, VehicleAllocation],
    ) -> None:
        """Commit only allocations returned by one completed batch."""
        by_vehicle: dict[str, list[VehicleAllocation]] = {}
        for allocation in allocations.values():
            if allocation.status == "allocated":
                by_vehicle.setdefault(allocation.vehicle_id, []).append(allocation)
        for vehicle_id, winners in by_vehicle.items():
            if len(winners) > 1:
                raise ValueError("one vehicle cannot have multiple batch winners")
            winner = winners[0]
            vehicle = self.vehicles[vehicle_id]
            vehicle.reserved_by = winner.agent_id
