"""Read-only evaluation of one complete E1 evaluation-v1 run. No model API."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path

import yaml

from scripts.audit_archived_run import Audit, agents, commitments, digest, dump, metric, read_json, read_jsonl
from scripts.export_behavior_review import export_review


class CurrentRunAudit(Audit):
    def __init__(self, run: Path, repo: Path):
        self.run, self.repo = Path(run).resolve(), Path(repo).resolve()
        self.events = read_jsonl(self.run / "events/events.jsonl")
        self.initial = read_json(self.run / "initial_state.json")
        self.profiles = read_jsonl(self.run / "selected_profiles.jsonl")
        self.status = read_json(self.run / "execution_status.json")
        self.provenance = read_json(self.run / "provenance.json")
        self.provenance.setdefault("kind", "scripted_software_check" if self.provenance.get("backend") == "mock"
                                   else "real_model_preflight")
        self.cfg = yaml.safe_load((self.run / "execution_config.yaml").read_text())
        planned = self.status["planned_steps"]
        if (self.status["status"] != "VALID" or self.status["completed_steps"] != planned
                or [e["step"] for e in self.events] != list(range(1, planned + 1))):
            raise ValueError("Evaluation requires one VALID, complete, contiguous run")
        if any(e["world"].get("log_schema_version") != "e1_evaluation_v1" for e in self.events):
            raise ValueError("Use audit_archived_run for the archived schema")
        inputs = read_jsonl(self.run / "decision_inputs.jsonl")
        self.inputs = {(x["step"], x["resident_id"]): x for x in inputs}
        self.decisions = {(e["step"], d["agent"]): d for e in self.events for d in e["decisions"]}
        count = sum(len(e["decisions"]) for e in self.events)
        if (len(self.inputs) != len(inputs) or len(self.decisions) != count
                or len({d["decision_id"] for d in self.decisions.values()}) != count
                or set(self.inputs) != set(self.decisions)):
            raise ValueError("Duplicate or missing decision/input identities; do not mix attempts")
        self.member_h = {m["resident_id"]: p["household_id"] for p in self.profiles for m in p["member_profiles"]}
        self.profile_h = {p["household_id"]: p for p in self.profiles}
        self.raw_messages = {
            f"m{step}:{rid}:{i}": {"step": step, "sender": rid, "message": msg, "decision_id": d["decision_id"]}
            for (step, rid), d in self.decisions.items() for i, msg in enumerate(d["decision"].get("messages", []))}
        last = self.events[-1]["interaction"]
        self.messages = last["messages"]
        self.notices = {n["message_id"]: n for n in last["commitment_notifications"]}
        self.receipts = {r["receipt_id"]: r for r in last["receipts"]}
        self.orders = {}
        for event in read_jsonl(self.run / "input_events.jsonl"):
            if event["kind"] == "official_order":
                rid, eid = event["recipient_id"], event["event_id"]
                if rid is None:
                    raise ValueError("Broadcast official orders require a different audit contract")
                self.orders[eid] = {"source_event_id": eid, "resident_id": rid,
                    "severity": event["severity"], "issued_step": event["issued_step"],
                    "receipt_id": f"receipt_{eid}_{rid}"}
        self.graph = {}
        for a, b in read_json(self.run / "input_graph.json")["edges"]:
            self.graph.setdefault(a, set()).add(b)
            self.graph.setdefault(b, set()).add(a)
        self.evidence, self.extras = {}, {}

    def source_identity(self):
        recorded = self.provenance.get("code_sha256", {})
        missing, mismatched = [], []
        for relative, expected in recorded.items():
            path = self.repo / "disastersociety" / relative
            if not path.exists():
                missing.append(relative)
            elif digest(path) != expected:
                mismatched.append(relative)
        return {"recorded_source_files": len(recorded), "missing": missing, "mismatched": mismatched,
                "verified": bool(recorded) and not missing and not mismatched,
                "run_kind": self.provenance.get("kind", "real_model_preflight")}

    def allowed_recipients(self, raw):
        rid, msg = raw["sender"], raw["message"]
        household = set(self.profile_h[self.member_h[rid]]["decision_resident_ids"]) - {rid}
        if msg["to"] in household:
            return {msg["to"]}
        return super().allowed_recipients(raw)

    def audit_information(self):
        super().audit_information()
        records = self.evidence["information"]
        observations = {o["observation_id"]: o for o in self.events[-1]["world"]["observations"]}
        for (step, rid), row in sorted(self.inputs.items()):
            observed = row["payload"]["observed_now"]
            oid = observed.get("observation_id")
            source, issues = observations.get(oid), []
            pre = self.events[step - 1]["state_before_decisions"]["world"]
            hid = self.member_h[rid]
            if source is None:
                issues.append("observation_has_no_source_record")
            else:
                if source["resident_id"] != rid or source["step"] != step or source["phase"] != "before_decision":
                    issues.append("observation_source_identity_mismatch")
                for key, value in source["content"].items():
                    if observed.get(key) != value:
                        issues.append("observed_content_mismatch:" + key)
                hazard = self.cfg["experiment"]["hazard"]
                expected_distance = max(0, float(hazard.get("initial_distance_m", 9000))
                    + pre["hazard_offsets"][hid] - float(hazard.get("approach_per_step_m", 250)) * step)
                if source["content"].get("hazard_distance_m") != expected_distance:
                    issues.append("local_hazard_differs_from_configured_world")
                expected_resources = [{"vehicle_id": v["id"], "reserved_by": v["reserved_by"],
                    "location": v["location"], "occupied": len(v["occupied_by"]), "capacity": v["capacity"]}
                    for v in pre["vehicles"][hid].values()]
                if source["content"].get("shared_resource_reservations") != expected_resources:
                    issues.append("observed_resources_differ_from_decision_phase")
            records.append({"record_id": f"{rid}|local_observation|{oid}", "resident_id": rid,
                "household_id": hid, "step": step, "kind": "local_observation", "source_id": oid,
                "issues": issues, "evidence": [f"decision_inputs.jsonl#step={step}/resident={rid}",
                                               f"events/events.jsonl#step={step}/world/observations/{oid}"]})
        self.extras["information_categories"] = dict(Counter(r["kind"] for r in records))
        return metric(records, "唯一居民×信息来源：结构化接收事实，以及实际输入的局部观察。",
            ["局部观察覆盖危险距离和共享资源可见状态；不评价全部自由文本事实。",
             "核验的是仿真记录与输入条件的一致性，不是真实人群预测准确率。",
             "观察与接收种类分别报告数量，不能将不同覆盖版本的错误率直接合并。"])

    def audit_execution(self):
        super().audit_execution()
        index = {r["record_id"]: r for r in self.evidence["execution"] + self.evidence["nondeparture_execution_checks"]}
        for d in self.decisions.values():
            outcome, row = d["outcome"], index[d["decision_id"]]
            requested = d["decision"]["action"]
            if outcome.get("requested_action") != requested:
                row["issues"].append("requested_action_mismatch")
            expected = requested if outcome["status"] == "executed" else None
            if outcome["executed_action"] != expected:
                row["issues"].append("executed_action_mismatch")
            if outcome["status"] == "rejected":
                if outcome["resource_allocations"]:
                    row["issues"].append("rejected_request_has_allocated_resources")
                delta = outcome["state_delta"]
                if "physical_before" in delta and delta["physical_before"] != delta.get("physical_after"):
                    row["issues"].append("rejected_request_changes_physical_resources")
        resource_checks = []
        for event in self.events:
            pre, post = event["state_before_decisions"]["world"], event["world"]
            expected_vehicles = deepcopy(pre["vehicles"])
            expected_usage = deepcopy(pre["route_usage"])
            seen = set()
            for d in event["decisions"]:
                if d["decision"]["action"] != "evacuate" or d["outcome"]["status"] != "executed":
                    continue
                cid = d["outcome"]["state_delta"].get("commitment_id")
                if cid in seen:
                    continue
                seen.add(cid)
                entry = commitments(post).get(cid)
                if entry is None:
                    continue  # already counted by the execution audit
                hid, c = entry
                party = c["party"]
                vehicle = expected_vehicles[hid].get(party["vehicle_id"])
                if vehicle is not None:
                    vehicle["location"] = self.cfg["experiment"]["safe_zone"]
                expected_usage[party["route_id"]] = expected_usage.get(party["route_id"], 0) + 1
            issues = []
            if expected_vehicles != post["vehicles"]:
                issues.append("vehicle_changes_do_not_match_executed_parties")
            if expected_usage != post["route_usage"]:
                issues.append("route_usage_does_not_match_executed_parties")
            resource_checks.append({"record_id": f"resources@{event['step']}", "step": event["step"], "issues": issues})
        self.evidence["resource_state_checks"] = resource_checks
        self.extras["resource_state_checks"] = metric(resource_checks, "逐步车辆、占用／预留及道路使用量与已执行队伍一致。")
        return metric(self.evidence["execution"], "每个撤离请求、执行状态、位置变化、反馈及相关资源记录。",
            ["无法归属某个请求的全局资源变化另报逐步检查；不能隐藏在零请求错误率后。",
             "单次完整运行不是正式方法对比。"])

    def audit_exports(self):
        final, checks = self.events[-1], []
        for filename, expected in (
            ("resident_terminal_states.jsonl", final["agents"]),
            ("official_receipts.jsonl", final["interaction"]["receipts"]),
            ("message_ledger.jsonl", list(final["interaction"]["messages"].values())),
        ):
            actual = read_jsonl(self.run / filename)
            checks.append({"record_id": filename, "issues": [] if actual == expected else ["terminal_export_mismatch"]})
        expected = [{"step": e["step"], "phase": "after_step", **a} for e in self.events for a in e["agents"]]
        checks.append({"record_id": "resident_state_timeline.jsonl", "issues": []
            if read_jsonl(self.run / "resident_state_timeline.jsonl") == expected else ["timeline_mismatch"]})
        self.evidence["terminal_export_checks"] = checks
        return checks

    def run_checks(self):
        result = {"audit_version": "e1_evaluation_v1", "source_identity": self.source_identity(),
            "seed": self.provenance["seed"], "households": len(self.profiles), "completed_steps": len(self.events),
            "decision_count": len(self.decisions), "formal_behavior_score": None,
            "formal_scenario_pass_rate": None,
            "metrics": {"information": self.audit_information(), "consensus": self.audit_consensus(),
                        "execution": self.audit_execution()},
            "additional_checks": self.extras, "input_checks": self.input_checks(),
            "terminal_export_checks": self.audit_exports()}
        return result


def evaluate(run: Path, repo: Path, output: Path):
    run, output = run.resolve(), output.resolve()
    if output == run or run in output.parents or output in run.parents:
        raise ValueError("Evaluation outputs must be separate from the original run")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Existing evaluation is protected: {output}")
    paths = sorted(p for p in run.rglob("*") if p.is_file())
    before = {str(p.relative_to(run)): digest(p) for p in paths}
    audit = CurrentRunAudit(run, repo)
    result = audit.run_checks()
    output.mkdir(parents=True, exist_ok=True)
    manifest = export_review(audit, output / "review_inputs", sorted(audit.profile_h))
    dump(output / "audit_results.json", result)
    dump(output / "check_records.json", audit.evidence)
    dump(output / "review_manifest.json", manifest)
    assert before == {str(p.relative_to(run)): digest(p) for p in paths}, "Original run changed"
    dump(output / "source_manifest.json", {"files_sha256": before, "read_only": True})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = evaluate(args.run, args.repo, args.output)
    print({"households": result["households"], "metrics": result["metrics"]})


if __name__ == "__main__":
    main()
