"""Audit saved evidence using the standard library only. No simulation or API use.

These are availability and cross-record checks, not new scientific endpoints.
Original runs, caches, and manuscript files are never modified.
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import hashlib
import json

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BATCH = OUT.parent / "main_experiments_20260905"
CODE = Path("/Users/linnuo/Documents/agentSimulation/disastersociety")
SOURCES = {}


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    SOURCES[str(path)] = hashlib.sha256(raw).hexdigest()
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def audit_e1(accepted_path):
    accepted = read(accepted_path)
    run = Path(accepted["run_dir"])
    events = read(run / "events/events.jsonl")
    inputs = read(run / "decision_inputs.jsonl")
    calls = read(run / "llm_calls.jsonl")
    profiles = read(run / "selected_profiles.jsonl")
    messages = read(run / "message_ledger.jsonl")
    commitments = read(run / "commitment_ledger.jsonl")
    departures = read(run / "household_departure_ledger.jsonl")
    receipts = read(run / "official_receipts.jsonl")
    final_residents = read(run / "resident_state_timeline.jsonl")
    initial = read(run / "initial_state.json")
    decisions = {(e["step"], d["agent"]): d for e in events for d in e["decisions"]}
    payloads = {(i["step"], i["resident_id"]): i["payload"] for i in inputs}
    call_ids = {(c["step"], c["agent_id"]) for c in calls}
    before = {(e["step"], a["id"]): a for e in events for a in e["state_before_decisions"]["agents"]}
    members = {m["resident_id"] for h in profiles for m in h["member_profiles"]}
    hh_members = {h["household_id"]: {m["resident_id"] for m in h["member_profiles"]} for h in profiles}
    issues = []
    if set(decisions) != set(payloads) or set(decisions) != call_ids:
        issues.append({"kind": "input_decision_call_key_mismatch"})
    if len(payloads) != len(inputs):
        issues.append({"kind": "duplicate_input_keys"})
    private_matches = 0
    inbox_matches = 0
    household_matches = 0
    for key, p in payloads.items():
        a = before.get(key)
        if a is None:
            issues.append({"kind": "missing_predecision_snapshot", "at": key})
            continue
        expected = {"memories": a["memories"][-12:], "current_plan": a["current_plan"],
                    "my_accepted_commitments": a["my_commitments"],
                    "recent_execution_feedback": a["recent_execution_feedback"]}
        if p["private_process"] == expected:
            private_matches += 1
        else:
            issues.append({"kind": "private_input_snapshot_mismatch", "at": key})
        inbox_fields = ("kind", "message_kind", "message_id", "severity", "content", "payload",
                        "source_event_id", "source_message_id", "channel")
        expected_inbox = [{k: item.get(k) for k in inbox_fields} for item in a["inbox"]]
        if p["observed_now"]["inbox"] == expected_inbox:
            inbox_matches += 1
        else:
            issues.append({"kind": "inbox_snapshot_mismatch", "at": key})
        if (p["resident_id"] == a["id"] and p["household_id"] == a["household_id"]
                and {m["resident_id"] for m in p["household_profile"]["members"]} == hh_members[a["household_id"]]):
            household_matches += 1
        else:
            issues.append({"kind": "identity_or_household_scope_mismatch", "at": key})

    raw_responses = defaultdict(list)
    for (step, rid), d in decisions.items():
        for response in d["decision"]["message_responses"]:
            raw_responses[(response["message_id"], rid)].append((step, response["disposition"]))
    c_by_id = {c["id"]: c for c in commitments}
    accepted_messages = [m for m in messages if m.get("acceptance", {}).get("accepted")]
    response_links = 0
    supported_agreements = 0
    for m in accepted_messages:
        ok = True
        ac = m["acceptance"]
        c = c_by_id.get(ac["commitment_id"])
        if not c:
            ok = False
            issues.append({"kind": "accepted_message_missing_commitment", "message_id": m["message_id"]})
        elif any(c["party"].get(k) != m["payload"].get(k)
                 for k in ("vehicle_id", "route_id", "depart_step")):
            ok = False
            issues.append({"kind": "commitment_party_mismatch", "message_id": m["message_id"]})
        for rid in set(m["payload"]["traveler_ids"]) - {m["sender_id"]}:
            state = m["recipient_states"].get(rid, {})
            response = (state.get("response_step"), "accepted")
            timeline = [m["issued_step"], state.get("delivered_step"), state.get("processed_step"),
                        state.get("response_step"), ac.get("formed_step")]
            if (response in raw_responses[(m["message_id"], rid)]
                    and all(v is not None for v in timeline) and timeline == sorted(timeline)):
                response_links += 1
            else:
                ok = False
                issues.append({"kind": "agreement_missing_timed_raw_acceptance", "message_id": m["message_id"], "resident_id": rid})
        supported_agreements += int(ok)

    executed_departures = [d for d in departures if d["outcome"] == "executed"]
    dep_by_step = defaultdict(list)
    for d in executed_departures:
        dep_by_step[d["step"]].append(d)
    checked_steps = 0
    moved_members = 0
    missing_member_steps = 0
    duplicate_departures = 0
    seen_departed = set()
    prev = initial["world"]["member_locations"]
    for e in events:
        step = e["step"]
        pre = e["state_before_decisions"]["world"]["member_locations"]
        post = e["world"]["member_locations"]
        if set(pre) != members or set(post) != members:
            missing_member_steps += 1
        if pre != prev:
            issues.append({"kind": "between_step_location_difference", "step": step})
        changed = {m for m in members if pre.get(m) != post.get(m)}
        expected_moves = set()
        for d in dep_by_step[step]:
            party = set(d["traveler_ids"]) | set(d["accompanying_member_ids"])
            expected_moves.update(party)
            if not e["world"]["route_state"][d["route_id"]]["open"]:
                issues.append({"kind": "executed_departure_on_closed_route", "step": step, "party_id": d["party_id"]})
        if changed != expected_moves or any(post.get(m) != "controlled_safe_zone" for m in changed):
            issues.append({"kind": "departure_location_change_mismatch", "step": step})
        else:
            checked_steps += 1
        decider_moves = {d["agent"] for d in e["decisions"] if d["outcome"].get("executed_action") == "evacuate"
                         and d["outcome"]["status"] == "executed"}
        duplicate_departures += len(seen_departed & decider_moves)
        seen_departed.update(decider_moves)
        moved_members += len(changed)
        prev = post
    return {
        "run": accepted_path.parent.name, "run_dir": str(run), "steps": len(events),
        "households": len(profiles), "members": len(members), "decisions": len(decisions),
        "saved_inputs": len(inputs), "input_call_decision_keys_match": set(decisions) == set(payloads) == call_ids,
        "private_input_snapshot_matches": private_matches, "inbox_snapshot_matches": inbox_matches,
        "identity_and_household_scope_matches": household_matches,
        "messages": len(messages), "proposals": sum(m["kind"] == "proposal" for m in messages),
        "recorded_acceptances": sum(s.get("disposition") == "accepted" for m in messages for s in m["recipient_states"].values()),
        "recorded_rejections": sum(s.get("disposition") == "rejected" for m in messages for s in m["recipient_states"].values()),
        "formed_social_agreements": len(accepted_messages), "agreements_with_checked_raw_response_links": supported_agreements,
        "checked_raw_acceptance_links": response_links, "all_commitment_versions": len(commitments),
        "official_receipts": len(receipts), "resident_snapshots_in_events": sum(len(e["agents"]) for e in events),
        "member_location_observations": sum(len(e["world"]["member_locations"]) for e in events),
        "misnamed_timeline_file_is_terminal_snapshot": len(final_residents) == len(events[-1]["agents"]),
        "executed_departure_parties": len(executed_departures), "individual_member_moves": moved_members,
        "steps_with_departure_location_agreement": checked_steps, "steps_with_incomplete_member_keys": missing_member_steps,
        "duplicate_successful_resident_departures": duplicate_departures, "issues": issues,
    }


def audit_legacy():
    docs = ROOT / "experiments/carr/results_carr_docs"
    e3_models = [r["model"] for r in read(docs / "carr_s_e3_paper_effect_table.json")["rows"]
                 if r["model"] != "All models (pooled)"]
    manifests = [("E2", p) for p in sorted(docs.glob("carr_s_e2_v8_formal_r7_seed*_summary.json"))]
    for model in e3_models:
        manifests.extend(("E3", p) for p in sorted(docs.glob(f"carr_s_e3_v1_{model}_seed*_summary.json")))
    result = []
    seen = set()
    for family, manifest in manifests:
        for run in read(manifest)["runs"]:
            rel = Path(run["run_dir"])
            path = next((base / rel for base in (CODE, ROOT) if (base / rel).exists()), None)
            if str(path or rel) in seen:
                continue
            seen.add(str(path or rel))
            row = {"family": family, "run_dir": str(path or rel), "exists": bool(path),
                   "condition": run["condition"], "terminal_status": run["terminal_status"]}
            ep = path / "events.jsonl" if path else None
            if ep and ep.exists():
                es = read(ep)
                row.update(steps=len(es), decisions=sum(len(e.get("decisions", [])) for e in es),
                           saved_decision_inputs=(path / "decision_inputs.jsonl").exists(),
                           predecision_snapshots=all("state_before_decisions" in e for e in es),
                           interaction_records=all("interaction" in e for e in es),
                           individual_member_locations=all("member_locations" in e.get("world", {}) for e in es),
                           original_metrics_present=(path / "mechanism_metrics.json").exists())
            result.append(row)
    return result


if __name__ == "__main__":
    runs = [audit_e1(p) for p in sorted((BATCH / "runs").glob("*/accepted.json"))]
    legacy = audit_legacy()
    status = read(BATCH / "runs/100hh_seed101/attempt3/status.json")
    partial_dir = Path(status["run_dir"])
    partial_events = read(partial_dir / "events/events.jsonl")
    partial = {"run_dir": str(partial_dir), "status": status["status"],
               "planned_steps": status["planned_steps"], "logged_steps": [e["step"] for e in partial_events],
               "decisions_in_complete_step_logs": sum(len(e["decisions"]) for e in partial_events),
               "saved_inputs": len(read(partial_dir / "decision_inputs.jsonl")),
               "included_in_complete_run_metrics": False}
    report = {"purpose": "Existing-evidence availability and cross-record checks; not a new scientific metric result",
              "new_model_calls": 0, "simulation_runs_started": 0, "accepted_e1": runs,
              "legacy_e2_e3": legacy, "partial_100hh": partial,
              "limits": ["Matching the recorded private input to a resident snapshot is not a full semantic information-leakage audit.",
                         "Agreement checks link accepted records to raw responses; they do not compute complete independent precision/recall.",
                         "World checks cover member transfers and closed routes, not every vehicle resource transition.",
                         "Earlier E2/E3 logs have a different schema; missing E1-v2 fields cannot be assumed reconstructible.",
                         "All checks are offline; existing data do not contain newly proposed external method runs."],
              "sources": SOURCES}
    (OUT / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "e1_inventory.csv").open("w", newline="") as f:
        fields = [k for k in runs[0] if k != "issues"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        w.writerows({k: r[k] for k in fields} for r in runs)
    families = {}
    for family in ("E2", "E3"):
        rows = [r for r in legacy if r["family"] == family]
        families[family] = {"runs_found": sum(r["exists"] for r in rows), "runs_listed": len(rows),
                            "steps": sum(r.get("steps", 0) for r in rows),
                            "decisions": sum(r.get("decisions", 0) for r in rows),
                            "with_saved_inputs": sum(r.get("saved_decision_inputs", False) for r in rows),
                            "with_full_member_locations": sum(r.get("individual_member_locations", False) for r in rows),
                            "with_original_metrics": sum(r.get("original_metrics_present", False) for r in rows)}
    print(json.dumps({"accepted_e1": [{k: v for k, v in r.items() if k != "run_dir"} for r in runs],
                      "legacy": families, "partial_100hh": partial, "new_model_calls": 0}, ensure_ascii=False, indent=2))
