"""End-to-end evaluation plus fault injection; all model calls are scripted."""
from pathlib import Path

import pytest

from scripts.audit_archived_run import read_json
from scripts.check_e1_process import run_check
from scripts.collect_behavior_scores import collect
from scripts.evaluate_e1_run import CurrentRunAudit, evaluate


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def complete_run(tmp_path_factory):
    output = tmp_path_factory.mktemp("evaluation_fixture")
    assert run_check(output)["all_checks_passed"]
    return output / "offline_process"


def test_complete_run_evaluates_read_only_and_preserves_empty_opportunities(complete_run, tmp_path):
    result = evaluate(complete_run, REPO, tmp_path / "audit")
    assert [(x["errors"], x["checked"]) for x in result["metrics"].values()] == [(0, 24), (0, 4), (0, 5)]
    assert result["additional_checks"]["resource_state_checks"]["errors"] == 0
    formation = result['additional_checks']['consensus_formation_opportunities']
    assert formation['errors'] == 0
    assert formation['positive']['checked'] == 2
    assert formation['negative']['checked'] == 2
    assert not any(r["issues"] for r in result["terminal_export_checks"])
    assert result["formal_behavior_score"] is None
    assert read_json(tmp_path / "audit/source_manifest.json")["read_only"]
    with pytest.raises(FileExistsError):
        evaluate(complete_run, REPO, tmp_path / "audit")


def test_missing_agreement_is_detected_even_if_acceptance_output_claims_success(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    cid = next(cid for cid in audit.events[1]['world']['household_commitments']['fixture_A'])
    # Simulate a persistence bug; leave all proposal/response/acceptance records
    # unchanged, so an oracle that trusts acceptance output would miss it.
    for event in audit.events:
        event['world']['household_commitments']['fixture_A'].pop(cid, None)
        event['state_before_decisions']['world']['household_commitments']['fixture_A'].pop(cid, None)
    audit.audit_consensus()
    assert any('effective_acceptance_without_recorded_agreement' in r['issues']
               for r in audit.evidence['consensus_formation_opportunities'])


def test_recorded_agreement_without_actual_acceptance_is_detected(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    for (step, _), decision in audit.decisions.items():
        if step == 2:
            decision['decision']['message_responses'] = []
    audit.audit_consensus()
    assert any('agreement_created_without_valid_formation' in r['issues']
               for r in audit.evidence['consensus_formation_opportunities'])


def test_tampered_observation_input_is_detected(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    row = next(iter(audit.inputs.values()))
    row["payload"]["observed_now"]["hazard_distance_m"] = -100
    assert audit.audit_information()["errors"] > 0


def test_wrong_observation_and_matching_wrong_input_still_fail_world_check(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    row = next(iter(audit.inputs.values()))
    observed = row["payload"]["observed_now"]
    source = next(o for o in audit.events[-1]["world"]["observations"] if o["observation_id"] == observed["observation_id"])
    observed["hazard_distance_m"] = source["content"]["hazard_distance_m"] = 123456
    assert audit.audit_information()["errors"] > 0


def test_rejected_request_with_executed_action_is_detected(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    d = next(d for d in audit.decisions.values() if d["outcome"]["status"] == "rejected")
    d["outcome"]["executed_action"] = "evacuate"
    assert audit.audit_execution()["errors"] > 0


def test_phantom_vehicle_move_without_departure_is_detected_separately(complete_run):
    audit = CurrentRunAudit(complete_run, REPO)
    next(iter(audit.events[0]["world"]["vehicles"]["fixture_A"].values()))["location"] = "safe"
    audit.audit_execution()
    assert audit.extras["resource_state_checks"]["errors"] > 0


def test_missing_input_or_unfinished_run_is_rejected(complete_run, tmp_path):
    import json
    import shutil
    run = tmp_path / "copy"
    shutil.copytree(complete_run, run)
    path = run / "decision_inputs.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[1:]) + "\n")
    with pytest.raises(ValueError, match="identities"):
        CurrentRunAudit(run, REPO)
    status = read_json(run / "execution_status.json")
    status["status"] = "INVALID"
    (run / "execution_status.json").write_text(json.dumps(status))
    with pytest.raises(ValueError, match="complete"):
        CurrentRunAudit(run, REPO)


def test_behavior_collection_keeps_all_cases_and_rejects_duplicates(complete_run, tmp_path):
    import json
    folder = tmp_path / "audit"
    evaluate(complete_run, REPO, folder)
    manifest = read_json(folder / "review_manifest.json")
    paths = []
    for entry in manifest["cases"]:
        case = read_json(folder / "review_inputs" / entry["file"])
        rid = case["profile"]["member_profiles"][0]["resident_id"]
        # Deliberately arbitrary values for parser validation, not behavioral results.
        row = {"case_id": entry["case_id"], "score": 2, "confidence": "low",
               "rationale_zh": "Artificial parser fixture only", "input_issues": [], "limitations": [],
               "evidence": [{"step": step, "resident_id": rid, "assessment_zh": "Fixture reference"} for step in (1, 2)]}
        path = folder / (entry["case_id"] + "_score.json")
        path.write_text(json.dumps([row]))
        paths.append(path)
    summary = collect(folder / "review_inputs", folder / "review_manifest.json", paths)
    assert summary["scored_households"] == 2 and summary["mean"] == 2
    with pytest.raises(ValueError, match="Missing cases"):
        collect(folder / "review_inputs", folder / "review_manifest.json", paths[:1])
    with pytest.raises(ValueError, match="duplicate"):
        collect(folder / "review_inputs", folder / "review_manifest.json", paths + paths[:1])
