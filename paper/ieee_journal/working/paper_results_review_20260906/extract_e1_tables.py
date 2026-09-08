"""Read accepted E1 logs and prepare review tables; no simulation or API calls."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import statistics

OUT = Path(__file__).resolve().parent
BATCH = OUT.parent / "main_experiments_20260905"
PROVENANCE = []

def read_json(path):
    raw = path.read_bytes()
    PROVENANCE.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    return json.loads(raw)

def read_jsonl(path):
    raw = path.read_bytes()
    PROVENANCE.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    return [json.loads(line) for line in raw.splitlines() if line.strip()]

def write_csv(name, rows):
    with (OUT / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

run_rows, time_rows, household_rows, commitment_rows = [], [], [], []
safe = "controlled_safe_zone"
for accepted_path in sorted((BATCH / "runs").glob("*/accepted.json")):
    accepted = read_json(accepted_path)
    run = Path(accepted["run_dir"])
    analysis = read_json(Path(accepted["analysis"]) / "results.json")
    assert analysis["software_check_passed"]
    events = read_jsonl(run / "events/events.jsonl")
    assert [e["step"] for e in events] == list(range(1, 26))
    profiles = read_jsonl(run / "selected_profiles.jsonl")
    initial = read_json(run / "initial_state.json")
    deciders = {m["resident_id"] for h in profiles for m in h["member_profiles"] if m["decision_capable"]}
    multi = {h["household_id"] for h in profiles if sum(m["decision_capable"] for m in h["member_profiles"]) >= 2}
    seed = int(accepted_path.parent.name.split("seed")[1])
    n = len(profiles)
    prev = initial["world"]["member_locations"]
    departures, received, joint, joint_executed = set(), set(), set(), set()
    commitments = {}
    for event in events:
        locations = event["world"]["member_locations"]
        newly_safe = {r for r in deciders if locations[r] == safe and prev[r] != safe}
        executed = {d["agent"] for d in event["decisions"] if d["decision"]["action"] == "evacuate" and d["outcome"]["status"] == "executed"}
        assert newly_safe == executed and not departures.intersection(executed)
        departures.update(executed)
        received.update(r["resident_id"] for r in event["interaction"]["receipts"] if r["delivered_step"] <= event["step"])
        for hid, records in event["world"]["household_commitments"].items():
            for cid, commitment in records.items():
                commitments[cid] = (hid, commitment)
                if len(commitment["party"]["traveler_ids"]) >= 2:
                    assert hid in multi
                    joint.add(hid)
                    if commitment["status"] == "executed":
                        joint_executed.add(hid)
        all_safe = sum(all(locations[m["resident_id"]] == safe for m in h["member_profiles"]) for h in profiles)
        time_rows.append({"households": n, "seed": seed, "step": event["step"], "hours": event["sim_minutes"] / 60,
                          "official_recipient_share": len(received) / len(deciders),
                          "first_departure_share": len(departures) / len(deciders),
                          "all_safe_household_share": all_safe / n,
                          "joint_agreement_household_share": len(joint) / len(multi) if multi else None,
                          "joint_execution_household_share": len(joint_executed) / len(multi) if multi else None})
        prev = locations
    last = time_rows[-1]
    for key in ["first_departure_share", "all_safe_household_share", "joint_agreement_household_share", "joint_execution_household_share"]:
        assert abs(last[key] - analysis["metrics"][key]) < 1e-12
    for profile in profiles:
        hid = profile["household_id"]
        members = profile["member_profiles"]
        safe_count = sum(prev[m["resident_id"]] == safe for m in members)
        terminal = "all_safe" if safe_count == len(members) else "partly_safe" if safe_count else "none_safe"
        mode = ("all_safe_with_joint" if hid in joint_executed else "all_safe_without_joint") if terminal == "all_safe" else terminal
        household_rows.append({"households": n, "seed": seed, "household_id": hid,
                               "members": len(members), "decision_members": sum(m["decision_capable"] for m in members),
                               "multi_decision": hid in multi, "safe_members": safe_count,
                               "terminal": terminal, "mode": mode, "ever_joint_agreement": hid in joint,
                               "ever_joint_execution": hid in joint_executed})
    for cid, (hid, commitment) in commitments.items():
        if len(commitment["party"]["traveler_ids"]) >= 2:
            commitment_rows.append({"households": n, "seed": seed, "household_id": hid, "commitment_id": cid,
                                    "status": commitment["status"], "planned_departure_step": commitment["party"]["depart_step"],
                                    "scheduled_beyond_window": commitment["party"]["depart_step"] > 25})
    run_rows.append({"households": n, "seed": seed, "decision_residents": len(deciders), "multi_decision_households": len(multi),
                     **{k: last[k] for k in ["first_departure_share", "all_safe_household_share", "joint_agreement_household_share", "joint_execution_household_share"]}})

summary = []
for n in sorted({r["households"] for r in run_rows}):
    group = [r for r in run_rows if r["households"] == n]
    for metric in ["first_departure_share", "all_safe_household_share", "joint_agreement_household_share", "joint_execution_household_share"]:
        values = [r[metric] for r in group]
        summary.append({"households": n, "runs": len(group), "metric": metric, "mean": statistics.mean(values),
                        "sample_sd": statistics.stdev(values) if len(values) > 1 else None,
                        "minimum": min(values), "maximum": max(values)})

time_summary = []
for n, step in sorted({(r["households"], r["step"]) for r in time_rows}):
    group = [r for r in time_rows if r["households"] == n and r["step"] == step]
    for metric in ["official_recipient_share", "first_departure_share", "all_safe_household_share", "joint_agreement_household_share", "joint_execution_household_share"]:
        values = [r[metric] for r in group]
        time_summary.append({"households": n, "step": step, "hours": group[0]["hours"], "metric": metric,
                             "runs": len(values), "mean": statistics.mean(values), "minimum": min(values), "maximum": max(values)})

write_csv("e1_run_summary.csv", run_rows)
write_csv("e1_scale_summary.csv", summary)
write_csv("e1_time_by_run.csv", time_rows)
write_csv("e1_time_summary.csv", time_summary)
write_csv("e1_household_outcomes.csv", household_rows)
write_csv("e1_joint_commitments.csv", commitment_rows)
report = {"accepted_runs": len(run_rows), "complete_steps": len(time_rows), "household_run_records": len(household_rows),
          "multi_household_modes": dict(collections.Counter(r["mode"] for r in household_rows if r["multi_decision"])),
          "joint_commitment_statuses": dict(collections.Counter(r["status"] for r in commitment_rows)),
          "pending_beyond_window": sum(r["status"] == "accepted" and r["scheduled_beyond_window"] for r in commitment_rows),
          "all_four_final_metrics_match_existing_analysis": True,
          "note": "New descriptive cross-tabulation of existing logs, not a new confirmatory endpoint; only accepted complete runs included.",
          "input_files": PROVENANCE}
(OUT / "extraction_checks.json").write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != "input_files"}, indent=2))
print(json.dumps(summary, indent=2))
