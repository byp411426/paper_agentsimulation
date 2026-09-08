"""Offline evaluation of the existing, accepted E1 runs.

No simulator, model backend, or frozen implementation is imported. The checks
below use saved inputs, original cached structured responses, event snapshots,
and independently stated event/resource predicates. Outputs are new derived
artifacts; the original experiments and manuscript remain untouched.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import ast
import csv
import hashlib
import json
import sqlite3
import yaml

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent / "main_experiments_20260905"
SOURCES = {}


def read(path):
    p = Path(path)
    raw = p.read_bytes()
    SOURCES[str(p)] = hashlib.sha256(raw).hexdigest()
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def location(value):
    if isinstance(value, str) and value.startswith("("):
        return list(ast.literal_eval(value))
    return list(value) if isinstance(value, tuple) else value


def write_csv(name, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def pr_counts(predicted, expected):
    tp, fp, fn = len(predicted & expected), len(predicted - expected), len(expected - predicted)
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def membership_errors(party, sender, household, profiles):
    members = {p["resident_id"]: p for p in profiles[household]["member_profiles"]}
    travelers = set(party["traveler_ids"])
    companions = set(party.get("accompanying_member_ids", []))
    adults = {m for m, p in members.items() if p["decision_capable"]}
    dependents = set(members) - adults
    errors = []
    if not travelers or not travelers <= adults or sender not in travelers:
        errors.append("invalid_travelers")
    if not companions <= dependents:
        errors.append("invalid_dependents")
    return errors


def physical_party_errors(party, household, profiles, pre_locations, used_vehicles, capacities):
    errors = []
    member_profiles = {p["resident_id"]: p for p in profiles[household]["member_profiles"]}
    travelers = set(party["traveler_ids"])
    companions = set(party.get("accompanying_member_ids", []))
    all_members = travelers | companions
    if not all_members <= set(member_profiles):
        errors.append("foreign_member")
    if any(location(pre_locations.get(m)) != ["home", household] for m in all_members):
        errors.append("member_not_at_origin")
    vehicle = party["vehicle_id"]
    if vehicle not in capacities or capacities[vehicle][0] != household:
        errors.append("vehicle_unknown")
    elif len(all_members) > capacities[vehicle][1]:
        errors.append("vehicle_capacity")
    if vehicle in used_vehicles:
        errors.append("vehicle_not_at_origin")
    caregivers = dict(party.get("caregiver_by_member", {}))
    assisted = {m for m in companions if member_profiles.get(m, {}).get("needs_execution_assistance")}
    if not assisted <= set(caregivers) or any(v not in travelers for v in caregivers.values()):
        errors.append("accompanying_member_caregiver")
    return errors


def input_errors(inp, before, receipts, messages, notices, prior_outcomes, initial_routes):
    p, rid, step = inp["payload"], inp["resident_id"], inp["step"]
    a = before[rid]
    errors = []
    if p["resident_id"] != rid or p["household_id"] != a["household_id"]:
        errors.append("identity_scope")
    expected_private = {"memories": a["memories"][-12:], "current_plan": a["current_plan"],
                        "my_accepted_commitments": a["my_commitments"],
                        "recent_execution_feedback": a["recent_execution_feedback"]}
    if p["private_process"] != expected_private:
        errors.append("private_state_owner_or_content")
    for item in p["observed_now"]["inbox"] + p["private_process"]["memories"]:
        if item["kind"] == "official_receipt":
            available = [r for r in receipts if r["resident_id"] == rid
                         and r["source_event_id"] == item.get("source_event_id")
                         and r["severity"] == item.get("severity") and r["delivered_step"] <= step]
            if not available:
                errors.append("official_receipt_without_owned_source")
        elif item["kind"] == "message":
            mid = item.get("message_id")
            if mid in messages:
                m = messages[mid]
                rs = m["recipient_states"].get(rid, {})
                delivered = rs.get("delivered_step")
                if delivered is None or delivered > step or item.get("content") != m["content"]:
                    errors.append("message_without_owned_delivery")
            elif mid in notices:
                n = notices[mid]
                if n["recipient_id"] != rid or n["delivered_step"] > step or item.get("content") != n["content"]:
                    errors.append("protocol_notice_without_owned_delivery")
            else:
                errors.append("message_source_missing")
        elif item["kind"] == "execution":
            previous = prior_outcomes.get((item["step"], rid))
            if not previous or item["step"] >= step or (item["status"], item["action"], item.get("reason")) != (
                    previous["status"], previous["executed_action"], previous.get("reason")):
                errors.append("execution_memory_without_own_outcome")
    routes = deepcopy(initial_routes[rid])
    for (past_step, owner), past in prior_outcomes.items():
        if owner == rid and past_step < step and "closed" in str(past.get("reason") or ""):
            route = past.get("attempted_route")
            if route in routes:
                routes[route]["open"] = False
    if p["observed_now"]["perceived_routes"] != routes:
        errors.append("route_belief_without_logged_update")
    # This is an audit of structured ownership/source references. Statements in
    # natural-language plans, reflections, rumors, and assessments are not scored.
    return sorted(set(errors))


def world_step_errors(event, expected_moves, successful_parties, capacities, profiles, used_vehicles):
    errors = []
    pre = event["state_before_decisions"]["world"]["member_locations"]
    post = event["world"]["member_locations"]
    if set(pre) != set(post):
        errors.append("member_keys_changed")
    changed = {m for m in set(pre) | set(post) if pre.get(m) != post.get(m)}
    if changed != expected_moves or any(post.get(m) != "controlled_safe_zone" for m in changed):
        errors.append("location_delta_without_matching_execution")
    route_counts = Counter()
    batch_members, batch_vehicles = set(), set()
    for hid, party in successful_parties:
        all_members = set(party["traveler_ids"]) | set(party.get("accompanying_member_ids", []))
        errors.extend(physical_party_errors(party, hid, profiles, pre, used_vehicles, capacities))
        if all_members & batch_members or party["vehicle_id"] in batch_vehicles:
            errors.append("duplicate_member_or_vehicle_execution")
        batch_members |= all_members
        batch_vehicles.add(party["vehicle_id"])
        route = event["world"]["route_state"].get(party["route_id"])
        if not route or not route["open"]:
            errors.append("executed_on_unavailable_route")
        route_counts[party["route_id"]] += 1
    for rid, n in route_counts.items():
        if n > event["world"]["route_state"].get(rid, {}).get("capacity_per_step", 0):
            errors.append("route_capacity_exceeded")
    return sorted(set(errors))


def analyze(ap):
    run = Path(read(ap)["run_dir"])
    tag = ap.parent.name
    es = read(run / "events/events.jsonl")
    inputs = read(run / "decision_inputs.jsonl")
    calls = read(run / "llm_calls.jsonl")
    initial = read(run / "initial_state.json")
    profiles = {p["household_id"]: p for p in read(run / "selected_profiles.jsonl")}
    ms = {m["message_id"]: m for m in read(run / "message_ledger.jsonl")}
    cs = {c["id"]: c for c in read(run / "commitment_ledger.jsonl")}
    receipts = read(run / "official_receipts.jsonl")
    notices = {n["message_id"]: n for n in es[-1]["interaction"]["commitment_notifications"]}
    by_step = {e["step"]: e for e in es}
    member_hh = {m["resident_id"]: h for h, p in profiles.items() for m in p["member_profiles"]}
    config_path = run / "execution_config.yaml"
    config_bytes = config_path.read_bytes()
    SOURCES[str(config_path)] = hashlib.sha256(config_bytes).hexdigest()
    config = yaml.safe_load(config_bytes)
    vehicle_capacity = config["experiment"]["vehicles"]["capacity"]
    capacities = {f"{hid}:vehicle:{i}": (hid, vehicle_capacity)
                  for hid, profile in profiles.items()
                  for i in range(1, int(profile["shared_attributes"]["vehicle_count"]) + 1)}
    ds = {(e["step"], d["agent"]): d for e in es for d in e["decisions"]}
    assert [e["step"] for e in es] == list(range(1, 26))
    assert len(inputs) == len(ds) == len(calls)
    assert {(i["step"], i["resident_id"]) for i in inputs} == set(ds)
    cache_path = run.parent / "cache.sqlite"
    SOURCES[str(cache_path)] = hashlib.sha256(cache_path.read_bytes()).hexdigest()
    cache = sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True)
    original = {}
    for call in calls:
        row = cache.execute("SELECT response FROM cache WHERE key=?", (call["key"],)).fetchone()
        assert row, "Missing cached original structured response"
        raw = json.loads(row[0])
        key = (call["step"], call["agent_id"])
        original[key] = raw
        for field in ("action", "departure_mode", "depart_step", "route_id", "vehicle_id", "commitment_id",
                      "accompany_dependents", "message_responses", "cancel_commitment_ids"):
            assert raw.get(field) == ds[key]["decision"].get(field), (key, field)
    cache.close()
    outcomes = {(t, r): {**d["outcome"], "attempted_route": d["decision"].get("route_id")}
                for (t, r), d in ds.items()}
    initial_routes = {a["id"]: a["perceived_routes"] for a in initial["agents"]}
    info_rows = []
    for inp in inputs:
        before = {a["id"]: a for a in by_step[inp["step"]]["state_before_decisions"]["agents"]}
        errors = input_errors(inp, before, receipts, ms, notices, outcomes, initial_routes)
        info_rows.append({"run": tag, "step": inp["step"], "resident_id": inp["resident_id"],
                          "structural_source_violations": len(errors), "reasons": "|".join(errors)})

    # Recipient delivery/processing events are reconstructed from resident
    # snapshots and decision occurrence, not from message-ledger timestamps.
    expected_delivery, expected_processing = set(), set()
    seen_delivery = set()
    for e in es:
        for phase in (e["state_before_decisions"]["agents"], e["agents"]):
            for a in phase:
                for item in a["inbox"]:
                    mid = item.get("message_id")
                    if mid in ms and (mid, a["id"]) not in seen_delivery:
                        expected_delivery.add((mid, a["id"], e["step"]))
                        seen_delivery.add((mid, a["id"]))
        for a in e["state_before_decisions"]["agents"]:
            if (e["step"], a["id"]) not in ds:
                continue
            for item in a["inbox"]:
                if item.get("message_id") in ms:
                    expected_processing.add((item["message_id"], a["id"], e["step"]))
    predicted_delivery = {(m["message_id"], rid, s["delivered_step"]) for m in ms.values()
                          for rid, s in m["recipient_states"].items() if s["delivered_step"] is not None}
    predicted_processing = {(m["message_id"], rid, s["processed_step"]) for m in ms.values()
                            for rid, s in m["recipient_states"].items() if s["processed_step"] is not None}

    # Proposal-level oracle. Each row is a proposal version, not a household.
    # Agreement requires matching explicit replies; capacity/availability then
    # determine whether it may be registered as a feasible shared commitment.
    proposals = []
    expected_agreements, predicted_agreements = set(), set()
    response_order = {}
    for e in es:
        for decision_index, d in enumerate(e["decisions"]):
            for reply_index, reply in enumerate(original[(e["step"], d["agent"])]["message_responses"]):
                if reply["disposition"] == "accepted":
                    response_order[reply["message_id"]] = (e["step"], decision_index, reply_index)
    # This batch processes replies in the saved decision order. Proposal
    # emission order is different and is not a valid arbitration oracle.
    # This ordering check applies to this frozen protocol, not to all possible
    # legal schedules of a future external-framework comparison.
    ordered_messages = sorted(ms.items(), key=lambda item: response_order.get(
        item[0], (item[1]["issued_step"], -1, -1)))
    for mid, m in ordered_messages:
        if m["kind"] != "proposal":
            continue
        p = m["payload"]
        hid, issued = member_hh[m["sender_id"]], m["issued_step"]
        declared = original[(issued, m["sender_id"])]["party_proposal"]
        assert declared is not None
        for f in ("traveler_ids", "accompanying_member_ids", "caregiver_by_member", "vehicle_id", "route_id", "depart_step"):
            assert declared[f] == p[f], (mid, f)
        errors = membership_errors(p, m["sender_id"], hid, profiles)
        if p["depart_step"] < issued + 2:
            errors.append("insufficient_coordination_time")
        if m["channel"] != "household_dm":
            errors.append("wrong_proposal_channel")
        accepts, declined = {m["sender_id"]: issued}, False
        consent_step = None
        for (t, rid), raw in sorted(original.items()):
            if rid not in set(p["traveler_ids"]) - {m["sender_id"]}:
                continue
            for response in raw["message_responses"]:
                if response["message_id"] != mid:
                    continue
                assert any(x[0] == mid and x[1] == rid and x[2] <= t for x in expected_processing)
                if response["disposition"] == "rejected":
                    declined = True
                    break
                accepts[rid] = t
            if declined:
                break
            if set(p["traveler_ids"]) <= set(accepts):
                consent_step = max(accepts.values())
                break
        if set(p["traveler_ids"]) == {m["sender_id"]}:
            consent_step = issued
        stage = "invalid_membership" if errors else "declined" if declined else "pending_response" if consent_step is None else "consented"
        if stage == "consented":
            event = by_step[consent_step]
            context = event["state_before_decisions"]["world"]
            already_used = {d["outcome"]["state_delta"].get("commitment_id") for e in es if e["step"] < consent_step
                            for d in e["decisions"] if d["outcome"]["status"] == "executed" and d["decision"]["action"] == "evacuate"}
            used_v = {cs[cid]["party"]["vehicle_id"] for cid in already_used if cid in cs}
            errors.extend(physical_party_errors(p, hid, profiles, context["member_locations"], used_v, capacities))
            if p["depart_step"] < consent_step + 1:
                errors.append("departure_before_coordination_ready")
            if p["route_id"] not in context["route_state"]:
                errors.append("unknown_route")
            cancelled_now = {cid for (t, _), raw in original.items() if t == consent_step for cid in raw["cancel_commitment_ids"]}
            all_party = set(p["traveler_ids"]) | set(p["accompanying_member_ids"])
            active = dict(context["household_commitments"][hid])
            # Prior consensual proposals in the same decision phase are also
            # visible for resource arbitration; this prevents double promises.
            for prev in proposals:
                if prev["household_id"] == hid and prev["expected_formed_step"] == consent_step and prev["expected_feasible"]:
                    active["commit:" + prev["message_id"]] = {"status": "accepted", "party": ms[prev["message_id"]]["payload"]}
            for cid, c in active.items():
                cp = c["party"]
                if c["status"] != "accepted" or cid in cancelled_now or cid == p.get("supersedes_id"):
                    continue
                if cp["vehicle_id"] == p["vehicle_id"] or (set(cp["traveler_ids"]) | set(cp["accompanying_member_ids"])) & all_party:
                    errors.append("active_party_resource_conflict")
            if p.get("supersedes_id") and p["supersedes_id"] not in context["household_commitments"][hid]:
                errors.append("unknown_superseded_commitment")
            stage = "resource_conflict" if errors else "feasible_agreement"
        expected = stage == "feasible_agreement"
        predicted = bool(m.get("acceptance", {}).get("accepted"))
        if expected:
            expected_agreements.add(mid)
        if predicted:
            predicted_agreements.add(mid)
        cid = m.get("acceptance", {}).get("commitment_id")
        record_errors = []
        if predicted:
            c = cs.get(cid)
            if c is None:
                record_errors.append("missing_commitment_object")
            else:
                for f in ("vehicle_id", "route_id", "depart_step"):
                    if c["party"][f] != p[f]:
                        record_errors.append("party_" + f)
                for f in ("traveler_ids", "accompanying_member_ids"):
                    if set(c["party"][f]) != set(p[f]):
                        record_errors.append("party_" + f)
                if dict(c["party"]["caregiver_by_member"]) != p["caregiver_by_member"]:
                    record_errors.append("party_caregivers")
                if c["created_step"] != consent_step or m["acceptance"].get("formed_step") != consent_step:
                    record_errors.append("formation_time")
                if set(c["accepted_by"]) != set(accepts):
                    record_errors.append("accepting_members")
            if record_errors:
                predicted_agreements.discard(mid)
                predicted_agreements.add(mid + ":record_mismatch")
        terminal = cs[cid]["status"] if cid in cs else "not_formed"
        terminal_step = None
        if cid in cs and terminal != "accepted":
            terminal_step = next((e["step"] for e in es
                                  if e["world"]["household_commitments"][hid].get(cid, {}).get("status") == terminal), None)
        proposals.append({"run": tag, "message_id": mid, "household_id": hid, "issued_step": issued,
                          "expected_formed_step": consent_step, "expected_stage": stage, "expected_feasible": expected,
                          "recorded_feasible": predicted, "oracle_reasons": "|".join(sorted(set(errors))),
                          "record_consistency_errors": "|".join(record_errors),
                          "planned_departure_step": p["depart_step"], "route_id": p["route_id"],
                          "terminal_commitment_status": terminal, "terminal_step": terminal_step,
                          "outside_window": p["depart_step"] > 25})

    for cid in cs:
        if cid.startswith("commit:") and cid.removeprefix("commit:") not in {p["message_id"] for p in proposals if p["recorded_feasible"]}:
            predicted_agreements.add(cid.removeprefix("commit:"))

    world_rows = []
    used_vehicles = set()
    for e in es:
        step = e["step"]
        expected_moves, parties = set(), {}
        extra_errors = []
        for d in e["decisions"]:
            if d["decision"]["action"] != "evacuate" or d["outcome"]["status"] != "executed":
                continue
            decision = d["decision"]
            cid = d["outcome"]["state_delta"].get("commitment_id")
            c = cs[cid]
            party = c["party"]
            hid = member_hh[d["agent"]]
            if (decision["depart_step"] != step or party["depart_step"] != step
                    or decision["route_id"] != party["route_id"] or decision["vehicle_id"] != party["vehicle_id"]):
                extra_errors.append("executed_intent_time_or_resource_mismatch")
            if decision["departure_mode"] == "commitment":
                if decision["commitment_id"] != cid or cid.removeprefix("commit:") not in expected_agreements:
                    extra_errors.append("joint_execution_without_supported_agreement")
                matching = {x["agent"] for x in e["decisions"] if x["decision"]["action"] == "evacuate"
                            and x["decision"].get("commitment_id") == cid and x["decision"].get("depart_step") == step
                            and x["decision"].get("route_id") == party["route_id"] and x["decision"].get("vehicle_id") == party["vehicle_id"]}
                if not set(party["traveler_ids"]) <= matching:
                    extra_errors.append("joint_execution_without_all_matching_intents")
            elif set(party["traveler_ids"]) != {d["agent"]} or set(party["accompanying_member_ids"]) != set(decision["accompany_dependents"]):
                extra_errors.append("solo_party_not_matching_intent")
            expected_moves |= set(party["traveler_ids"]) | set(party["accompanying_member_ids"])
            parties[cid] = (hid, party)
        errs = world_step_errors(e, expected_moves, list(parties.values()), capacities, profiles, used_vehicles) + extra_errors
        for _, p in parties.values():
            used_vehicles.add(p["vehicle_id"])
        world_rows.append({"run": tag, "step": step, "decisions": len(e["decisions"]),
                           "departure_attempts": sum(d["decision"]["action"] == "evacuate" for d in e["decisions"]),
                           "executed_parties": len(parties), "moved_members": len(expected_moves),
                           "state_conflicts": len(set(errs)), "reasons": "|".join(sorted(set(errs)))})
    recs = {"delivery": pr_counts(predicted_delivery, expected_delivery),
            "processing": pr_counts(predicted_processing, expected_processing),
            "feasible_agreement": pr_counts(predicted_agreements, expected_agreements)}
    terminal_locations = es[-1]["world"]["member_locations"]
    household_states = Counter()
    for hid, profile in profiles.items():
        n_safe = sum(terminal_locations[m["resident_id"]] == "controlled_safe_zone" for m in profile["member_profiles"])
        household_states["all_safe" if n_safe == len(profile["member_profiles"]) else "partly_safe" if n_safe else "none_safe"] += 1
    result = {"run": tag, "source_dir": str(run), "households": len(profiles), "members": len(member_hh),
              "steps": len(es), "decisions": len(ds), "original_cached_responses_checked": len(original),
              "input_packets_with_structural_source_violation": sum(r["structural_source_violations"] > 0 for r in info_rows),
              "event_records": recs, "steps_with_world_conflict": sum(r["state_conflicts"] > 0 for r in world_rows),
              "proposals": len(proposals), "proposal_stages": dict(Counter(r["expected_stage"] for r in proposals)),
              "agreement_outcomes": dict(Counter(r["terminal_commitment_status"] for r in proposals if r["recorded_feasible"])),
              "action_outcomes": {f"{a}/{s}": n for (a, s), n in Counter((d["decision"]["action"], d["outcome"]["status"]) for d in ds.values()).items()},
              "departure_attempts": sum(r["departure_attempts"] for r in world_rows),
              "executed_departure_parties": sum(r["executed_parties"] for r in world_rows),
              "moved_members": sum(r["moved_members"] for r in world_rows),
              "household_terminal_counts": dict(household_states)}
    # Negative controls alter copies only. They check the evaluator can expose
    # source leakage, invented agreement, omitted agreement, and fake movement.
    first = inputs[0]
    b = {a["id"]: a for a in by_step[first["step"]]["state_before_decisions"]["agents"]}
    mutated = deepcopy(first)
    mutated["payload"]["observed_now"]["inbox"].append({"kind": "official_receipt", "source_event_id": "NONEXISTENT_EVENT", "severity": "mandatory"})
    fake_input_detected = "official_receipt_without_owned_source" in input_errors(mutated, b, receipts, ms, notices, outcomes, initial_routes)
    invalid_mid = next(r["message_id"] for r in proposals if r["expected_stage"] == "declined")
    invented = pr_counts(predicted_agreements | {invalid_mid}, expected_agreements)
    removed = pr_counts(predicted_agreements - {next(iter(expected_agreements))}, expected_agreements)
    empty = pr_counts(set(), set())
    event = deepcopy(es[0])
    member = next(iter(event["world"]["member_locations"]))
    event["world"]["member_locations"][member] = "controlled_safe_zone"
    fake_movement_detected = "location_delta_without_matching_execution" in world_step_errors(event, set(), [], capacities, profiles, set())
    controls = {"run": tag, "foreign_receipt_detected": fake_input_detected,
                "invented_agreement_adds_false_positive": invented["fp"] == recs["feasible_agreement"]["fp"] + 1,
                "omitted_agreement_adds_false_negative": removed["fn"] == recs["feasible_agreement"]["fn"] + 1,
                "empty_event_set_is_not_full_score": empty["precision"] is None and empty["recall"] is None,
                "unexecuted_member_transfer_detected": fake_movement_detected,
                "valid_quiet_step_passes": not world_step_errors(es[0], set(), [], capacities, profiles, set())}
    assert all(v for k, v in controls.items() if k != "run"), controls
    return result, info_rows, proposals, world_rows, controls


def main():
    reports, info, proposals, world, controls = [], [], [], [], []
    for ap in sorted((BATCH / "runs").glob("*/accepted.json")):
        r, i, p, w, c = analyze(ap)
        reports.append(r); info.extend(i); proposals.extend(p); world.extend(w); controls.append(c)
    totals = {k: sum(r[k] for r in reports) for k in ("steps", "decisions", "original_cached_responses_checked",
              "input_packets_with_structural_source_violation", "steps_with_world_conflict", "proposals",
              "departure_attempts", "executed_departure_parties", "moved_members")}
    totals["proposal_stages"] = dict(Counter(p["expected_stage"] for p in proposals))
    totals["agreement_outcomes"] = dict(Counter(p["terminal_commitment_status"] for p in proposals if p["recorded_feasible"]))
    totals["event_records"] = {}
    for kind in ("delivery", "processing", "feasible_agreement"):
        c = {k: sum(r["event_records"][kind][k] for r in reports) for k in ("tp", "fp", "fn")}
        c["precision"] = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        c["recall"] = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        totals["event_records"][kind] = c
    report = {"method": "DisasterSociety", "status": "OFFLINE_RESULTS_FOR_REVIEW",
              "new_model_calls": 0, "new_simulation_runs": 0,
              "evaluation_scope": "Structured source provenance, recorded social event fidelity, and logged physical-state invariants; not human behavioral realism or comparative superiority",
              "aggregation": "All three previously accepted 24-household runs; event counts are descriptive pooled exposure, not independent populations or hypothesis tests",
              "totals": totals, "runs": reports, "negative_and_positive_controls": controls, "sources": SOURCES}
    (HERE / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_csv("information_input_checks.csv", info)
    write_csv("proposal_event_checks.csv", proposals)
    write_csv("world_step_checks.csv", world)
    write_csv("evaluator_controls.csv", controls)
    table = [{"method": "DisasterSociety", "metric": "structured_information_source_violation_rate",
              "numerator": totals["input_packets_with_structural_source_violation"], "denominator": totals["decisions"],
              "value": totals["input_packets_with_structural_source_violation"] / totals["decisions"], "direction": "lower"}]
    for kind, c in totals["event_records"].items():
        for stat, denom in (("precision", c["tp"] + c["fp"]), ("recall", c["tp"] + c["fn"])):
            table.append({"method": "DisasterSociety", "metric": kind + "_record_" + stat,
                          "numerator": c["tp"], "denominator": denom, "value": c[stat], "direction": "higher"})
    table.append({"method": "DisasterSociety", "metric": "logged_world_state_conflict_step_rate",
                  "numerator": totals["steps_with_world_conflict"], "denominator": totals["steps"],
                  "value": totals["steps_with_world_conflict"] / totals["steps"], "direction": "lower"})
    write_csv("method_result_table.csv", table)
    print(json.dumps({"totals": totals, "controls": controls, "new_model_calls": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
