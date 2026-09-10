"""Regression cases for input, information, consent and execution boundaries."""
from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from ds.agents.carr_empirical_v2 import OfficialInformationReceipt, CarrEmpiricalResidentV2
from ds.households.state import DepartureParty, HouseholdCommitmentV2
from ds.kernel.clock import Clock
from ds.population.synth import build_donor_tables, prepare_carr_donor_features
from ds.population.profile_validation import validate_e1_profiles
from tests.test_e1_process_repair import setup, decision, apply, propose, accept


def profile(hid="H", size=2, structure="nonfamily_not_living_alone"):
    ids = [f"{hid}_{i}" for i in range(size)]
    return {"household_id": hid, "shared_attributes": {
        "vehicle_count": 1, "household_structure": structure},
        "member_profiles": [{"household_id": hid, "resident_id": rid,
            "age": 30, "decision_capable": True} for rid in ids],
        "decision_resident_ids": ids, "nondecision_member_ids": [],
        "care_recipient_ids": [], "focal_resident_id": ids[0], "coordinator_id": ids[0]}


@pytest.mark.parametrize("code,size,expected", [
    (4, 1, "nonfamily_living_alone"), (5, 2, "nonfamily_not_living_alone"),
    (6, 1, "nonfamily_living_alone"), (7, 2, "nonfamily_not_living_alone"),
])
def test_all_nonfamily_hht_categories(code, size, expected):
    housing = pd.DataFrame([{"SERIALNO": "donor", "WGTP": 1, "NP": size,
                            "HINCP": 30000, "VEH": 1, "HHT": code}])
    persons = pd.DataFrame([{"SERIALNO": "donor", "SPORDER": i + 1, "AGEP": 40,
                            "RELP": 0 if i == 0 else 12}
                            for i in range(size)])
    features = prepare_carr_donor_features(build_donor_tables(housing, persons))
    assert features.households.iloc[0]["household_structure"] == expected


@pytest.mark.parametrize("size,structure", [
    (2, "nonfamily_living_alone"), (1, "nonfamily_not_living_alone")])
def test_contradictory_housing_fails_before_model_call(size, structure):
    with pytest.raises(ValueError, match="contradicts"):
        validate_e1_profiles([profile(size=size, structure=structure)])


def test_valid_nonfamily_not_alone_and_invalid_role_lists():
    p = profile()
    validate_e1_profiles([p])  # exact comparison; not a 'living_alone' substring test
    p["decision_resident_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="decision_resident_ids"):
        validate_e1_profiles([p])


def test_direct_runner_refuses_to_truncate_existing_log(tmp_path):
    from experiments.carr.empirical_v2_runner import run_e1_v2
    existing = tmp_path / "protected" / "events" / "events.jsonl"
    existing.parent.mkdir(parents=True)
    existing.write_text("original-log\n")
    with pytest.raises(FileExistsError, match="protected"):
        run_e1_v2(cfg={"run": {"run_id": "protected"}}, out_dir=tmp_path,
                  gateway=None, run_seed=7, n_households=1, profiles_path=tmp_path / "absent.jsonl")
    assert existing.read_text() == "original-log\n"


def test_shared_initial_routes_cannot_change_another_residents_belief():
    shared = {"primary": {"open": True}}
    a = CarrEmpiricalResidentV2(agent_id="a", household_id="H", profile={}, vehicles={}, initial_routes=shared)
    b = CarrEmpiricalResidentV2(agent_id="b", household_id="H", profile={}, vehicles={}, initial_routes=shared)
    a.perceived_routes["primary"]["open"] = False
    assert b.perceived_routes["primary"]["open"] and shared["primary"]["open"]


def test_direct_household_recipient_uses_household_delivery():
    rs, hh, w, ix = setup()
    ix.community_message_probability = 0
    ix.emit(rs["a"], decision(messages=[{"to": "b", "kind": "notice", "content": "Please discuss transport."}]), Clock(30, 1))
    ix.deliver(Clock(30, 1))
    m = next(iter(ix.messages.values()))
    assert m["channel"] == "household_dm" and m["recipient_ids"] == ["b"]
    assert len(rs["b"].inbox) == 1 and rs["c"].inbox == []


def test_delivery_does_not_expose_or_retroactively_mutate_shared_ledger():
    rs, hh, w, ix = setup()
    mid = propose(ix, rs, 1, 5)
    received = deepcopy(rs["b"].inbox)
    assert "recipient_states" not in received[0]
    ix.messages[mid]["payload"]["route_id"] = "changed-in-ledger"
    ix.messages[mid]["recipient_states"]["c"]["disposition"] = "accepted"
    assert rs["b"].inbox == received


def test_duplicate_receipts_and_messages_do_not_reset_processing():
    rs, hh, w, ix = setup()
    r = OfficialInformationReceipt("receipt1", "a", "event1", "mandatory", "official_direct", 1, 1, None)
    rs["a"].deliver_receipt(r)
    rs["a"].process_inbox(step=2)
    rs["a"].deliver_receipt(r)
    assert not rs["a"].inbox and rs["a"]._receipts["receipt1"].processed_step == 2
    with pytest.raises(ValueError, match="another resident"):
        rs["b"].deliver_receipt(r)
    message = {"message_id": "m", "kind": "notice", "content": "hello", "delivered_step": 1}
    rs["a"].deliver_message(message)
    rs["a"].process_inbox(step=2)
    rs["a"].deliver_message(message)
    assert not rs["a"].inbox


def test_existing_agreement_id_cannot_authorize_new_terms():
    rs, hh, w, ix = setup()
    mid = propose(ix, rs, 1, 5)
    accept(ix, rs, "b", mid, 2)
    accept(ix, rs, "c", mid, 2)
    original = hh.v2_commitments["commit:" + mid]
    changed = replace(original, party=replace(original.party, route_id="alternate"))
    result = hh.try_accept_commitment_v2(commitment=changed, decision_capable={r: True for r in rs},
        care_requirements={}, earliest_depart_step=3, party_origin=("home", "H"))
    assert result.reason_code == "commitment_id_reused"
    assert hh.v2_commitments[original.id] == original


def test_nonparticipant_cannot_replace_someone_elses_agreement():
    rs, hh, w, ix = setup()
    old = HouseholdCommitmentV2("old", "e1_party_v2",
        DepartureParty(frozenset({"a", "b"}), frozenset(), (), "v", "primary", 5),
        frozenset({"a", "b"}), 1)
    hh.v2_commitments[old.id] = old
    new = replace(old, id="new", accepted_by=frozenset({"c"}), supersedes_id="old",
                  party=replace(old.party, traveler_ids=frozenset({"c"})))
    result = hh.try_accept_commitment_v2(commitment=new, decision_capable={r: True for r in rs},
        care_requirements={}, earliest_depart_step=3, party_origin=("home", "H"))
    assert result.reason_code == "supersession_not_authorized"
    assert hh.v2_commitments == {"old": old}


def test_rejected_request_has_no_executed_action_or_physical_resource_delta():
    rs, hh, w, ix = setup()
    out = apply(w, rs, 3, {"a": decision(action="evacuate", departure_mode="solo",
                route_id="primary", vehicle_id="v", depart_step=3)})["3:a"]
    assert out.requested_action == "evacuate" and out.executed_action is None
    assert out.status == "rejected" and out.reason == "route_closed"
    assert out.resource_allocations == {}
    assert out.state_delta["physical_before"] == out.state_delta["physical_after"]
    assert rs["a"].recent_execution_feedback[-1]["executed_action"] is None
    assert rs["a"].recent_execution_feedback[-1]["requested_action"] == "evacuate"


def test_successful_request_links_actual_resource_and_member_changes():
    rs, hh, w, ix = setup()
    out = apply(w, rs, 2, {"a": decision(action="evacuate", departure_mode="solo",
                route_id="primary", vehicle_id="v", depart_step=2)})["2:a"]
    assert out.executed_action == "evacuate" and out.resource_allocations["vehicle_id"] == "v"
    assert out.state_delta["physical_before"]["member_locations"]["a"] == ("home", "H")
    assert out.state_delta["physical_after"]["member_locations"]["a"] == "safe"
    assert out.state_delta["physical_after"]["route_usage"] == {"primary": 1}


def test_observations_are_sourced_and_do_not_reveal_closed_routes():
    rs, hh, w, ix = setup()
    w.update(Clock(30, 3))
    payload = rs["a"]._prompt_payload(world=w, step=3)
    observed = payload["observed_now"]
    source = w.observation_records[observed["observation_id"]]
    assert source["resident_id"] == "a" and source["step"] == 3
    assert observed["hazard_distance_m"] == source["content"]["hazard_distance_m"]
    assert observed["perceived_routes"]["primary"]["open"] is True
    before = w.snapshot()
    w.route_state["alternate"]["open"] = False
    hh.vehicles["v"].location = "elsewhere"
    assert before["route_state"]["alternate"]["open"] is True
    assert before["vehicles"]["H"]["v"]["location"] == ("home", "H")


@pytest.mark.asyncio
async def test_notice_delivered_after_decision_waits_for_next_processing_step(tmp_path):
    from tests.conftest import make_gateway
    from ds.llm.backends import MockBackend
    rs, hh, w, ix = setup()
    gw = make_gateway(tmp_path, backends={"mock": MockBackend(policy=lambda *args: {"action": "prepare"})})
    gw.run_seed, gw.decision_model, gw.temperature = 7, "mock", 0
    a = rs["a"]
    a.deliver_message({"message_id": "early", "kind": "notice", "delivered_step": 1})
    try:
        d = await a.decide(events=[], world=w, gateway=gw, step=2)
        a.deliver_message({"message_id": "late", "kind": "notice", "delivered_step": 2})
        ix.process(a, d, Clock(30, 2))
        assert [m["message_id"] for m in a.inbox] == ["late"]
        assert not any(m.get("message_id") == "late" for m in a.memories)
        d = await a.decide(events=[], world=w, gateway=gw, step=3)
        ix.process(a, d, Clock(30, 3))
        assert a.inbox == []
        assert next(m for m in a.memories if m.get("message_id") == "late")["processed_step"] == 3
    finally:
        await gw.aclose()
        gw.cache.close()


@pytest.mark.asyncio
async def test_aborted_step_cancels_siblings_and_reports_last_completed_step(tmp_path):
    import asyncio
    from tests.conftest import make_gateway
    from ds.kernel.engine import Engine
    from ds.kernel.logger import RunLogger
    from ds.llm.gateway import LLMBackendUnavailable
    from experiments.carr.empirical_v2_runner import E1EventSource
    rs, hh, w, ix = setup()
    w.config["initial_distance_m"] = 1000
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def fail(**kw):
        if kw["step"] == 1:
            return decision()
        await started.wait()
        raise LLMBackendUnavailable("offline injected failure")

    async def pending(**kw):
        if kw["step"] == 1:
            return decision()
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    rs["a"].decide, rs["b"].decide = fail, pending
    gw = make_gateway(tmp_path)
    logger = RunLogger(tmp_path / "events")
    engine = Engine(run_seed=7, total_steps=3, step_minutes=30, world=w,
        agents=[rs["a"], rs["b"]], interaction=ix, events=E1EventSource([]), gateway=gw, logger=logger)
    try:
        result = await engine.run()
        assert result["status"] == "ABORTED" and cancelled.is_set()
        assert result["completed_steps"] == result["last_completed_step"] == 1
        assert len(logger.read_events()) == 1
    finally:
        logger.close()
        gw.close()
        gw.cache.close()
