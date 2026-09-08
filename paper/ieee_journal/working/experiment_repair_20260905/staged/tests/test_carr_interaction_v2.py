"""W4 e1_party_v2 household acceptance and execution tests."""

from __future__ import annotations

import pytest

from ds.households.state import (
    CareRequirement,
    CommitmentAcceptanceResult,
    DepartureParty,
    Household,
    HouseholdCommitmentV2,
    VehicleResource,
)


HOME = object()
SAFE = object()


def _household(*, vehicles: dict[str, int] | None = None):
    household = Household(
        id="hh1",
        member_ids=("a1", "a2", "c1", "c2", "c3", "c4"),
        decision_member_ids=("a1", "a2"),
        dependent_ids=("c1", "c2", "c3", "c4"),
    )
    for vehicle_id, capacity in (vehicles or {"v1": 5}).items():
        household.vehicles[vehicle_id] = VehicleResource(
            id=vehicle_id, location=HOME, capacity=capacity
        )
    return household


def _commitment(
    *,
    party_id: str = "p1",
    travelers=frozenset({"a1", "a2"}),
    accompanying=frozenset({"c1"}),
    caregivers=(("c1", "a1"),),
    vehicle_id: str = "v1",
    depart_step: int = 7,
    supersedes_id: str | None = None,
) -> HouseholdCommitmentV2:
    return HouseholdCommitmentV2(
        id=party_id,
        protocol_version="e1_party_v2",
        party=DepartureParty(
            traveler_ids=frozenset(travelers),
            accompanying_member_ids=frozenset(accompanying),
            caregiver_by_member=tuple(caregivers),
            vehicle_id=vehicle_id,
            route_id="route_primary",
            depart_step=depart_step,
        ),
        accepted_by=frozenset(travelers),
        created_step=4,
        supersedes_id=supersedes_id,
    )


def _care() -> dict[str, CareRequirement]:
    return {
        "c1": CareRequirement("c1", "minor", None),
        "c2": CareRequirement("c2", "minor", None),
        "c3": CareRequirement("c3", "minor", None),
        "c4": CareRequirement("c4", "minor", None),
    }


def _capable() -> dict[str, bool]:
    return {"a1": True, "a2": True, "c1": False, "c2": False, "c3": False, "c4": False}


def test_common_departure_accepted_and_executed():
    household = _household()
    commitment = _commitment()
    result = household.try_accept_commitment_v2(
        commitment=commitment,
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert result.accepted is True
    record = household.execute_v2_party(
        commitment=commitment,
        step=7,
        traveler_intents={"a1", "a2"},
        origin=HOME,
        destination=SAFE,
    )
    assert record.outcome == "executed"
    assert household.vehicles["v1"].location is SAFE
    assert household.v2_commitments["p1"].status == "executed"


def test_capacity_rejection():
    household = _household(vehicles={"v1": 5})
    commitment = _commitment(
        accompanying=frozenset({"c1", "c2", "c3", "c4"}),
        caregivers=(
            ("c1", "a1"),
            ("c2", "a1"),
            ("c3", "a2"),
            ("c4", "a2"),
        ),
    )
    result = household.try_accept_commitment_v2(
        commitment=commitment,
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert result.accepted is False
    assert result.reason_code == "vehicle_capacity"


def test_two_parties_two_vehicles_same_step():
    household = _household(vehicles={"v1": 5, "v2": 5})
    first = _commitment(
        party_id="p1",
        travelers=frozenset({"a1"}),
        accompanying=frozenset({"c1", "c2"}),
        caregivers=(("c1", "a1"), ("c2", "a1")),
    )
    second = _commitment(
        party_id="p2",
        travelers=frozenset({"a2"}),
        accompanying=frozenset({"c3", "c4"}),
        caregivers=(("c3", "a2"), ("c4", "a2")),
        vehicle_id="v2",
    )
    kwargs = dict(
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert household.try_accept_commitment_v2(commitment=first, **kwargs).accepted
    assert household.try_accept_commitment_v2(commitment=second, **kwargs).accepted
    record1 = household.execute_v2_party(
        commitment=first, step=7, traveler_intents={"a1"}, origin=HOME, destination=SAFE
    )
    record2 = household.execute_v2_party(
        commitment=second, step=7, traveler_intents={"a2"}, origin=HOME, destination=SAFE
    )
    assert record1.outcome == "executed"
    assert record2.outcome == "executed"
    assert len(household.departure_records) == 2


def test_split_departure_safe_and_coordinated_rate_leq_one():
    household = _household(vehicles={"v1": 5, "v2": 5})
    first = _commitment(party_id="p1", travelers=frozenset({"a1"}), vehicle_id="v1")
    second = _commitment(
        party_id="p2",
        travelers=frozenset({"a2"}),
        accompanying=frozenset({"c2", "c3", "c4"}),
        caregivers=(("c2", "a2"), ("c3", "a2"), ("c4", "a2")),
        vehicle_id="v2",
        depart_step=8,
    )
    kwargs = dict(
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert household.try_accept_commitment_v2(commitment=first, **kwargs).accepted
    assert household.try_accept_commitment_v2(commitment=second, **kwargs).accepted
    household.execute_v2_party(
        commitment=first, step=7, traveler_intents={"a1"}, origin=HOME, destination=SAFE
    )
    household.execute_v2_party(
        commitment=second,
        step=8,
        traveler_intents={"a2"},
        origin=HOME,
        destination=SAFE,
    )
    executed = [r for r in household.departure_records if r.outcome == "executed"]
    coordinated = sum(1 for r in executed if r.coordinated)
    assert len(executed) == 2
    assert coordinated / len(executed) <= 1.0


def test_care_recipient_double_claim_rejected():
    household = _household(vehicles={"v1": 5, "v2": 5})
    first = _commitment(
        party_id="p1", travelers=frozenset({"a1"}), accompanying=frozenset({"c1"})
    )
    second = _commitment(
        party_id="p2",
        travelers=frozenset({"a2"}),
        accompanying=frozenset({"c1"}),
        caregivers=(("c1", "a2"),),
        vehicle_id="v2",
    )
    kwargs = dict(
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert household.try_accept_commitment_v2(commitment=first, **kwargs).accepted
    result = household.try_accept_commitment_v2(commitment=second, **kwargs)
    assert result.accepted is False
    assert result.reason_code == "member_overlap"


def test_caregiver_must_be_traveler():
    household = _household()
    commitment = _commitment(
        travelers=frozenset({"a1"}), caregivers=(("c1", "a2"),)
    )
    result = household.try_accept_commitment_v2(
        commitment=commitment,
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert result.accepted is False
    assert result.reason_code == "caregiver_not_traveler"


def test_missing_traveler_intent_rejects_without_moving():
    household = _household()
    commitment = _commitment()
    household.try_accept_commitment_v2(
        commitment=commitment,
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    record = household.execute_v2_party(
        commitment=commitment,
        step=7,
        traveler_intents={"a1"},
        origin=HOME,
        destination=SAFE,
    )
    assert record.outcome == "rejected"
    assert record.reason_code == "missing_traveler_intent"
    assert household.vehicles["v1"].location is HOME
    assert household.v2_commitments["p1"].status == "rejected"


def test_vehicle_cannot_be_reused_after_departure():
    household = _household()
    first = _commitment(party_id="p1")
    kwargs = dict(
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert household.try_accept_commitment_v2(commitment=first, **kwargs).accepted
    household.execute_v2_party(
        commitment=first, step=7, traveler_intents={"a1", "a2"}, origin=HOME, destination=SAFE
    )
    second = _commitment(
        party_id="p2",
        travelers=frozenset({"a1"}),
        accompanying=frozenset(),
        caregivers=(),
        depart_step=10,
    )
    result = household.try_accept_commitment_v2(commitment=second, **kwargs)
    assert result.accepted is False
    assert result.reason_code == "vehicle_not_at_origin"


def test_revision_cancels_superseded_party():
    household = _household()
    first = _commitment(party_id="p1")
    kwargs = dict(
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert household.try_accept_commitment_v2(commitment=first, **kwargs).accepted
    revised = _commitment(
        party_id="p2",
        travelers=frozenset({"a1"}),
        accompanying=frozenset({"c1"}),
        caregivers=(("c1", "a1"),),
        depart_step=8,
        supersedes_id="p1",
    )
    result = household.try_accept_commitment_v2(commitment=revised, **kwargs)
    assert result.accepted is True
    assert household.v2_commitments["p1"].status == "cancelled"
    assert household.v2_commitments["p1"].supersedes_id is None
    assert household.v2_commitments["p2"].supersedes_id == "p1"
    assert household.v2_commitments["p2"].supersedes_id == "p1"


def test_conflicts_never_raise():
    household = _household(vehicles={"v1": 1})
    commitment = _commitment()
    result = household.try_accept_commitment_v2(
        commitment=commitment,
        decision_capable=_capable(),
        care_requirements=_care(),
        earliest_depart_step=5,
        party_origin=HOME,
    )
    assert isinstance(result, CommitmentAcceptanceResult)
    assert result.accepted is False
    assert result.reason_code == "vehicle_capacity"
