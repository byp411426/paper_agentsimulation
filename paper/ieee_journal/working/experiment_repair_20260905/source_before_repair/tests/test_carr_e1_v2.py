"""Carr E1 v2 runner wiring tests (W5 contract item 7.10)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from ds.agents.carr_empirical_v2 import (
    CarrEmpiricalResidentV2,
    OfficialInformationReceipt,
)
from ds.households.state import Household, VehicleResource
from ds.interaction.carr_empirical_v2 import CarrEmpiricalInteractionV2
from ds.kernel.clock import Clock
from ds.world.carr_empirical_v2 import CarrEmpiricalWorldV2


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resident(agent_id: str, household_id: str, age: int = 40):
    return CarrEmpiricalResidentV2(
        agent_id=agent_id,
        household_id=household_id,
        profile={
            "age": age,
            "decision_capable": age >= 18,
            "functional_limitations": {},
            "needs_execution_assistance": False,
            "pums_static": {},
            "latent_traits": {},
        },
        vehicles={},
    )


def _household(household_id: str, members: tuple[str, ...], decisions: tuple[str, ...]):
    household = Household(
        id=household_id,
        member_ids=members,
        decision_member_ids=decisions,
        dependent_ids=tuple(member for member in members if member not in decisions),
    )
    household.vehicles[f"{household_id}:v1"] = VehicleResource(
        id=f"{household_id}:v1",
        location=("home", household_id),
        capacity=5,
    )
    return household


def _world(residents: dict, households: dict, closure_step: int = 9):
    return CarrEmpiricalWorldV2(
        households=households,
        residents=residents,
        config={
            "initial_distance_m": 9000,
            "approach_per_step_m": 250,
            "closure_step": closure_step,
            "route_capacity_per_step": 10,
            "primary_route_id": "primary",
            "alternate_route_id": "alternate",
            "safe_zone": "safe",
        },
        run_seed=7,
    )


def test_no_cross_household_warning_delivery():
    from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2 as R
    from experiments.carr.empirical_v2_runner import OfficialOrderEvent

    a1 = _resident("A_r1", "A")
    b1 = _resident("B_r1", "B")
    residents = {"A_r1": a1, "B_r1": b1}
    households = {
        "A": _household("A", ("A_r1",), ("A_r1",)),
        "B": _household("B", ("B_r1",), ("B_r1",)),
    }
    ix = CarrEmpiricalInteractionV2(
        run_seed=1,
        household_dm_probability=1.0,
        community_message_probability=0.15,
        social_graph=None,
        residents=residents,
        households=households,
        decision_capable={"A_r1": True, "B_r1": True},
        care_requirements={},
    )
    order_a = OfficialOrderEvent(
        event_id="order_a", severity="mandatory", issued_step=3, recipient_id="A_r1"
    )
    order_b = OfficialOrderEvent(
        event_id="order_b", severity="voluntary", issued_step=3, recipient_id="B_r1"
    )
    ix.deliver_warnings([order_a, order_b], list(residents.values()), Clock(30), 1)
    assert any(item["source_event_id"] == "order_a" for item in a1.inbox)
    assert any(item["source_event_id"] == "order_b" for item in b1.inbox)
    assert not any(item["source_event_id"] == "order_b" for item in a1.inbox)
    assert not any(item["source_event_id"] == "order_a" for item in b1.inbox)


def test_none_household_has_no_receipt():
    from experiments.carr.empirical_v2_runner import OfficialOrderEvent

    c1 = _resident("C_r1", "C")
    ix = CarrEmpiricalInteractionV2(
        run_seed=2,
        household_dm_probability=1.0,
        community_message_probability=0.15,
        social_graph=None,
        residents={"C_r1": c1},
        households={"C": _household("C", ("C_r1",), ("C_r1",))},
        decision_capable={"C_r1": True},
        care_requirements={},
    )
    order = OfficialOrderEvent(
        event_id="order_x", severity="mandatory", issued_step=3, recipient_id="OTHER"
    )
    ix.deliver_warnings([order], [c1], Clock(30), 2)
    assert c1.inbox == []
    assert ix.receipts == []


def test_closure_not_in_perception_before_step_and_rejection_updates_it():
    from ds.kernel.actions import ExecutionOutcome

    a1 = _resident("A_r1", "A")
    world = _world({"A_r1": a1}, {"A": _household("A", ("A_r1",), ("A_r1",))})
    assert a1.perceived_routes["primary"]["open"] is True
    clock = Clock(30)
    for _ in range(8):
        clock.tick()
    world.update(clock)
    assert a1.perceived_routes["primary"]["open"] is True  # no leak
    outcome = ExecutionOutcome(
        decision_id="d1",
        agent_id="A_r1",
        status="rejected",
        executed_action="evacuate",
        reason="route_closed: primary",
    )
    from ds.agents.decide import ResidentDecision

    a1.commit_execution(
        ResidentDecision(action="evacuate", route_id="primary"), outcome, step=9
    )
    assert a1.perceived_routes["primary"]["open"] is False
    assert a1.recent_execution_feedback[-1]["last_failure"] == "route_closed: primary"


def test_private_commitments_not_visible_to_non_party_member():
    a1 = _resident("A_r1", "A")
    a2 = _resident("A_r2", "A")
    a1.my_commitments.append({"commitment_id": "secret", "depart_step": 7})
    assert a2.my_commitments == []
    world = _world(
        {"A_r1": a1, "A_r2": a2},
        {"A": _household("A", ("A_r1", "A_r2"), ("A_r1", "A_r2"))},
    )
    reservations = world.visible_reservations("A", viewer_id="A_r2")
    assert all("commitment_id" not in item for item in reservations)


def test_channel_probabilities_are_separated():
    from ds.kernel.clock import Clock as C

    a1 = _resident("A_r1", "A")
    a2 = _resident("A_r2", "A")
    households = {"A": _household("A", ("A_r1", "A_r2"), ("A_r1", "A_r2"))}
    ix = CarrEmpiricalInteractionV2(
        run_seed=3,
        household_dm_probability=1.0,
        community_message_probability=0.15,
        social_graph=None,
        residents={"A_r1": a1, "A_r2": a2},
        households=households,
        decision_capable={"A_r1": True, "A_r2": True},
        care_requirements={},
    )
    assert ix.household_dm_probability == 1.0
    assert ix.community_message_probability == 0.15
    assert ix.household_dm_probability != ix.community_message_probability


def test_unverified_rumor_requires_source_lineage():
    a1 = _resident("A_r1", "A")
    ix = CarrEmpiricalInteractionV2(
        run_seed=4,
        household_dm_probability=1.0,
        community_message_probability=0.15,
        social_graph=None,
        residents={"A_r1": a1},
        households={"A": _household("A", ("A_r1",), ("A_r1",))},
        decision_capable={"A_r1": True},
        care_requirements={},
    )
    from types import SimpleNamespace

    decision = SimpleNamespace(
        messages=[
            SimpleNamespace(
                to="community",
                kind="notice",
                content="already mandatory!",
                payload={
                    "forward_official": True,
                    "source_event_id": "order_not_owned",
                },
            )
        ]
    )
    ix.emit(a1, decision, Clock(5))
    message = next(iter(ix.messages.values()))
    assert message["payload"]["unverified_rumor"] is True
    assert message["payload"]["source_event_id"] is None


def test_focal_and_coordinator_written_in_profiles():
    profiles_path = (
        PROJECT_ROOT
        / "eventpacks/carr_2018/population/e1_profiles_v2_seed4201/e1_profiles_seed4201.jsonl"
    )
    if not profiles_path.exists():
        pytest.skip("profiles not built")
    first = json.loads(profiles_path.read_text(encoding="utf-8").splitlines()[0])
    assert first["focal_resident_id"]
    assert first["coordinator_id"]
    assert first["focal_resident_id"] == first["coordinator_id"]


def test_mock_preflight_deterministic_ledgers(tmp_path):
    import subprocess
    import sys

    profiles = (
        PROJECT_ROOT
        / "eventpacks/carr_2018/population/e1_profiles_v2_seed4201/e1_profiles_seed4201.jsonl"
    )
    if not profiles.exists():
        pytest.skip("profiles not built")
    config = (
        PROJECT_ROOT
        / "experiments/carr/configs/carr_s_e1_empirical_v2_preflight.yaml"
    )
    households_csv = (
        PROJECT_ROOT
        / "eventpacks/carr_2018/population/pilot_seed42_n1000_v2/synthetic_households.csv"
    )
    tracts = (
        PROJECT_ROOT
        / "eventpacks/carr_2018/population/tiger/tracts/shasta_tracts.geojson"
    )
    hashes = []
    for index in range(2):
        out = tmp_path / f"run{index}"
        subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/run_carr_e1_v2_preflight.py"),
                "--config",
                str(config),
                "--backend",
                "mock",
                "--n-households",
                "6",
                "--seed",
                "99",
                "--out-dir",
                str(out),
                "--households-csv",
                str(households_csv),
                "--tracts",
                str(tracts),
            ],
            check=True,
            capture_output=True,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        digest = hashlib.sha256()
        for path in sorted((out / "carr_s_e1_v2_preflight").glob("*.jsonl")):
            digest.update(path.read_bytes())
        hashes.append(digest.hexdigest())
    assert hashes[0] == hashes[1]


def test_delivered_message_is_processed_and_inbox_cleared():
    a1 = _resident("A_r1", "A")
    a1.deliver_message(
        {
            "message_id": "m1",
            "sender_id": "A_r1",
            "kind": "proposal",
            "content": "go",
            "channel": "household_dm",
            "payload": {"protocol_version": "e1_party_v2"},
        }
    )
    processed = a1.process_inbox(step=5)
    assert [p["message_id"] for p in processed] == ["m1"]
    assert processed[0]["message_kind"] == "proposal"
    assert processed[0]["processed_step"] == 5
    assert a1.inbox == []


def test_normalize_proposal_fills_missing_fields():
    from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2 as R
    from ds.agents.decide import E1ResidentDecision

    resident = _resident("A_r1", "A")
    decision = E1ResidentDecision(
        action="evacuate",
        route_id="tiger_primary",
        vehicle_id="v1",
        depart_step=0,
        messages=[
            {
                "to": "household",
                "kind": "proposal",
                "content": "go",
                "payload": {"route_id": "tiger_primary", "depart_step": 0},
            }
        ],
    )
    normalized = resident._normalize_proposal(decision, step=7)
    payload = normalized.messages[0].payload
    assert payload["protocol_version"] == "e1_party_v2"
    assert payload["traveler_ids"] == ["A_r1"]
    assert payload["vehicle_id"] == "v1"
    assert payload["depart_step"] == 8  # at least step + 1
    assert normalized.depart_step == 8
