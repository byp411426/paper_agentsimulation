#!/usr/bin/env python3
"""Read-only pilot audit of the archived E1 run. No project/model imports or API calls.

This is an evaluator development check, not a formal five-metric benchmark.
PyYAML is the sole external dependency. Inputs are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

import yaml


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8").splitlines() if s.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def agents(snapshot):
    return {a["id"]: a for a in snapshot["agents"]}


def commitments(world):
    return {cid: (hid, c) for hid, cs in world["household_commitments"].items() for cid, c in cs.items()}


def metric(records, scope, limitations=()):
    checked = [r for r in records if r.get("status") != "unverifiable"]
    errors = sum(bool(r["issues"]) for r in checked)
    return {
        "scope": scope,
        "status": "computed_for_stated_scope" if checked else "no_check_opportunity",
        "errors": errors if checked else None,
        "checked": len(checked),
        "rate": errors / len(checked) if checked else None,
        "unverifiable": len(records) - len(checked),
        "limitations": list(limitations),
    }


def expected_orders(profiles, cfg, calibration, seed):
    """Reconstruct the archived input assignment, independently of receipt outputs.

    Preserve the original allocation, including its unnormalised proportions.
    This audits receipt handling; it does not validate the allocation model.
    """
    props = calibration["calibration"]["main_excluding_15_contradictions"]["proportions"]
    raw = {k: v * len(profiles) for k, v in props.items()}
    quotas = {k: math.floor(v) for k, v in raw.items()}
    ranking = sorted(props, key=lambda k: (raw[k] - quotas[k], k), reverse=True)
    for k in ranking[:len(profiles) - sum(quotas.values())]:
        quotas[k] += 1
    if sum(quotas.values()) != len(profiles):
        raise ValueError("Archived allocation cannot be reconstructed with this protocol")
    tag = f"{seed}|stream|e1_order_assignment||0|0"
    rng = random.Random(int(hashlib.sha256(tag.encode()).hexdigest(), 16) % (2**32))
    ids = sorted(p["household_id"] for p in profiles)
    rng.shuffle(ids)
    by_h = {p["household_id"]: p for p in profiles}
    result, cursor, index = {}, 0, 0
    for seq, n in quotas.items():
        for _ in range(n):
            p = by_h[ids[cursor]]
            cursor += 1
            focal = p.get("focal_resident_id") or p["coordinator_id"]
            for level, prefix, eligible in [
                ("voluntary", "v", ("voluntary_only", "voluntary_then_mandatory")),
                ("mandatory", "m", ("mandatory_only", "voluntary_then_mandatory")),
            ]:
                if seq not in eligible:
                    continue
                index += 1
                event_id = f"order_{prefix}_{index}"
                step = cfg["experiment"]["orders"][level + "_step"]
                result[event_id] = {"source_event_id": event_id, "resident_id": focal,
                                    "severity": level, "issued_step": step,
                                    "receipt_id": f"receipt_{event_id}_{focal}"}
    return result


class Audit:
    def __init__(self, run, batch):
        self.run, self.batch = Path(run), Path(batch)
        self.events = read_jsonl(self.run / "events/events.jsonl")
        self.initial = read_json(self.run / "initial_state.json")
        self.profiles = read_jsonl(self.run / "selected_profiles.jsonl")
        self.status = read_json(self.run / "execution_status.json")
        self.provenance = read_json(self.run / "provenance.json")
        self.cfg = yaml.safe_load((self.run / "execution_config.yaml").read_text())
        inputs = read_jsonl(self.run / "decision_inputs.jsonl")
        self.inputs = {(x["step"], x["resident_id"]): x for x in inputs}
        if len(self.inputs) != len(inputs):
            raise ValueError("Duplicate decision inputs; do not silently choose one")
        planned = self.status["planned_steps"]
        if self.status["completed_steps"] != planned or [e["step"] for e in self.events] != list(range(1, planned + 1)):
            raise ValueError("This pilot requires one complete, contiguous attempt")
        if len({d["decision_id"] for e in self.events for d in e["decisions"]}) != sum(len(e["decisions"]) for e in self.events):
            raise ValueError("Duplicate decisions; possible attempt mixing")
        self.member_h = {m["resident_id"]: p["household_id"] for p in self.profiles for m in p["member_profiles"]}
        self.profile_h = {p["household_id"]: p for p in self.profiles}
        self.decisions = {(e["step"], d["agent"]): d for e in self.events for d in e["decisions"]}
        self.raw_messages = {}
        for (step, rid), d in self.decisions.items():
            for i, msg in enumerate(d["decision"].get("messages", [])):
                self.raw_messages[f"m{step}:{rid}:{i}"] = {"step": step, "sender": rid,
                    "message": msg, "decision_id": d["decision_id"]}
        self.messages = self.events[-1]["interaction"]["messages"]
        self.notices = {x["message_id"]: x for x in self.events[-1]["interaction"]["commitment_notifications"]}
        self.receipts = {x["receipt_id"]: x for x in self.events[-1]["interaction"]["receipts"]}
        self.orders = expected_orders(self.profiles, self.cfg, read_json(self.batch / "inputs/order_calibration.json"), self.provenance["seed"])
        self.graph = {}
        for a, b in read_json(self.run / "input_graph.json")["edges"]:
            self.graph.setdefault(a, set()).add(b)
            self.graph.setdefault(b, set()).add(a)
        self.evidence, self.extras = {}, {}

    def source_identity(self):
        original_hash = self.provenance["freeze_sha256"]
        matches = [p for p in self.batch.rglob("*freeze*.json") if digest(p) == original_hash]
        if not matches:
            raise ValueError("Cannot locate the manifest hash recorded by this attempt")
        original = matches[0]
        manifest = read_json(original)
        core = ["frozen/experiments/carr/empirical_v2_runner.py", "frozen/ds/kernel/engine.py",
                "frozen/ds/kernel/rng.py", "frozen/ds/agents/carr_empirical_v2.py",
                "frozen/ds/interaction/carr_empirical_v2.py", "frozen/ds/households/state.py",
                "frozen/ds/world/carr_empirical_v2.py", "inputs/profiles.jsonl", "inputs/order_calibration.json", "configs/24.yaml"]
        failures = [p for p in core if digest(self.batch / p) != manifest["files_sha256"][p]]
        if failures:
            raise ValueError("Audited source/input differs from original run: " + repr(failures))
        changed = [p for p, h in manifest["files_sha256"].items() if digest(self.batch / p) != h]
        return {"original_manifest": str(original.relative_to(self.batch)),
                "original_manifest_sha256": original_hash,
                "checked_original_core_files": core, "original_core_mismatches": failures,
                "later_changed_files_not_used_as_original_behavior_code": changed,
                "run_config_matches_original": digest(self.run / "execution_config.yaml") == manifest["files_sha256"]["configs/24.yaml"]}

    def allowed_recipients(self, raw):
        rid, msg = raw["sender"], raw["message"]
        target = msg["to"]
        if target in ("household", "family"):
            allowed = set(self.profile_h[self.member_h[rid]]["decision_resident_ids"]) - {rid}
        elif target in ("community", "neighbors"):
            allowed = self.graph.get(rid, set())
        else:
            allowed = {target} & self.graph.get(rid, set())
        if msg["kind"] == "proposal" and "traveler_ids" in msg.get("payload", {}):
            allowed = allowed & (set(msg["payload"]["traveler_ids"]) - {rid})
        return allowed

    def audit_information(self):
        """One fact = recipient + source identity, deduplicated across snapshots."""
        facts = {}

        def inspect(rid, item, step, phase, location):
            kind = item.get("kind")
            if kind not in ("official_receipt", "message"):
                return
            source = item.get("source_event_id") if kind == "official_receipt" else item.get("message_id")
            key = f"{rid}|{kind}|{source}"
            row = facts.setdefault(key, {"record_id": key, "resident_id": rid, "kind": kind,
                "source_id": source, "first_seen_step": step, "evidence": [], "issues": []})
            ref = (f"decision_inputs.jsonl#step={step}/resident={rid}/{location}"
                   if location.startswith("payload/") else
                   f"events/events.jsonl#step={step}/{phase}/{rid}/{location}")
            row["evidence"].append(ref)
            issues = []
            if kind == "official_receipt":
                expected = self.orders.get(source)
                if expected is None:
                    issues.append("unknown_official_source")
                else:
                    if expected["resident_id"] != rid:
                        issues.append("official_source_belongs_to_another_resident")
                    for field in ("severity", "issued_step", "receipt_id", "resident_id"):
                        if field in item and item[field] != expected[field]:
                            issues.append("official_" + field + "_mismatch")
                    if step < expected["issued_step"]:
                        issues.append("official_record_before_issue")
                    if item.get("delivered_step") is not None and item["delivered_step"] != expected["issued_step"]:
                        issues.append("official_delivery_step_mismatch")
                    actual = self.receipts.get(expected["receipt_id"])
                    if actual is None:
                        issues.append("receipt_absent_from_delivery_ledger")
                    if item.get("processed_step") is not None:
                        if item["processed_step"] < expected["issued_step"] or item["processed_step"] > step:
                            issues.append("official_processing_time_mismatch")
                        if (item["processed_step"], rid) not in self.decisions:
                            issues.append("processed_without_processing_cycle")
            else:
                msg = self.messages.get(source)
                notice = self.notices.get(source)
                if msg is not None:
                    raw = self.raw_messages.get(source)
                    state = msg.get("recipient_states", {}).get(rid)
                    if raw is None:
                        issues.append("message_without_sending_decision")
                    else:
                        if rid not in self.allowed_recipients(raw):
                            issues.append("message_outside_addressed_recipients")
                        if msg["sender_id"] != raw["sender"] or msg["issued_step"] != raw["step"]:
                            issues.append("message_origin_mismatch")
                        if "content" in item and item["content"] != raw["message"]["content"]:
                            issues.append("received_content_differs_from_sent_content")
                    if not state or state.get("delivered_step") is None:
                        issues.append("recorded_receipt_without_delivery")
                    else:
                        delivered = state["delivered_step"]
                        if delivered > step or (phase == "before" and delivered >= step):
                            issues.append("message_record_before_delivery_phase")
                        if "delivered_step" in item and item["delivered_step"] != delivered:
                            issues.append("recipient_delivery_time_mismatch")
                        if item.get("processed_step") is not None and state.get("processed_step") != item["processed_step"]:
                            issues.append("recipient_processing_time_mismatch")
                elif notice is not None:
                    if notice["recipient_id"] != rid:
                        issues.append("protocol_notice_belongs_to_another_resident")
                    if notice["delivered_step"] > step or (phase == "before" and notice["delivered_step"] >= step):
                        issues.append("protocol_notice_before_delivery")
                    if "content" in item and item["content"] != notice["content"]:
                        issues.append("protocol_notice_content_mismatch")
                else:
                    issues.append("message_source_not_in_event_ledger")
            row["issues"] = sorted(set(row["issues"] + issues))

        for event in self.events:
            for phase, snapshot in [("before", event["state_before_decisions"]), ("after", event)]:
                for a in snapshot["agents"]:
                    for name in ("inbox", "memories"):
                        for i, item in enumerate(a[name]):
                            inspect(a["id"], item, event["step"], phase, f"{name}/{i}")
                    for i, receipt in enumerate(a["receipts"]):
                        inspect(a["id"], {**receipt, "kind": "official_receipt"}, event["step"], phase, f"receipts/{i}")
        for (step, rid), item in self.inputs.items():
            payload = item["payload"]
            for i, record in enumerate(payload.get("observed_now", {}).get("inbox", [])):
                inspect(rid, record, step, "before", f"payload/observed_now/inbox/{i}")
            for i, record in enumerate(payload.get("private_process", {}).get("memories", [])):
                inspect(rid, record, step, "before", f"payload/private_process/memories/{i}")
        records = sorted(facts.values(), key=lambda r: r["record_id"])
        self.evidence["information"] = records
        self.extras["information_categories"] = dict(Counter(
            "official" if r["kind"] == "official_receipt" else "protocol_notice" if r["source_id"] in self.notices else "resident_message"
            for r in records))
        self.extras["official_input_reconstruction"] = {"expected": len(self.orders), "logged": len(self.receipts),
            "expected_receipt_ids_missing": sorted({o["receipt_id"] for o in self.orders.values()} - set(self.receipts))}
        return metric(records, "居民快照中唯一的结构化接收事实：居民×信息来源；跨步重复保存只计一次。",
            ["直接警报由原始初始化配置和种子重建输入分配；不是外部真实居民标签。",
             "居民消息对照发送决策、收件人交付状态及实际收件箱；协议通知对照协议通知记录。",
             "不评价自由文本中的所有事实命题，也不把私人信念与世界真相不一致直接判错。",
             "当前没有独立的局部观察事件表；本数值限于结构化接收记录，不冒充所有观察来源的全量评价。"])

    def audit_consensus(self):
        previous, records, creations = {}, [], set()
        for event in self.events:
            step = event["step"]
            current = commitments(event["world"])
            for cid, (hid, c) in current.items():
                old = previous.get(cid)
                if old == c or len(c["party"]["traveler_ids"]) < 2:
                    continue
                if old is None:
                    creations.add(cid)
                issues, refs = [], [f"events/events.jsonl#step={step}/world/household_commitments/{hid}/{cid}"]
                mid = cid.removeprefix("commit:")
                raw, sent = self.raw_messages.get(mid), self.messages.get(mid)
                if raw is None or sent is None:
                    issues.append("shared_agreement_without_proposal")
                else:
                    refs.append(raw["decision_id"])
                    p = raw["message"].get("payload", {})
                    for field in ("traveler_ids", "accompanying_member_ids", "route_id", "vehicle_id", "depart_step"):
                        left, right = c["party"].get(field), p.get(field)
                        if isinstance(left, list):
                            left, right = sorted(left), sorted(right or [])
                        if left != right:
                            issues.append("proposal_content_mismatch:" + field)
                    if c.get("supersedes_id") != p.get("supersedes_id"):
                        issues.append("proposal_version_mismatch")
                    authorized = {raw["sender"]}
                    for (t, rid), d in sorted(self.decisions.items()):
                        if t > c["created_step"]:
                            continue
                        for reply in d["decision"].get("message_responses", []):
                            if reply["message_id"] != mid:
                                continue
                            evidence = self.inputs.get((t, rid), {}).get("payload", {})
                            known = evidence.get("observed_now", {}).get("inbox", []) + evidence.get("private_process", {}).get("memories", [])
                            has_seen = any(m.get("message_id") == mid for m in known)
                            rs = sent.get("recipient_states", {}).get(rid, {})
                            delivered = rs.get("delivered_step")
                            if has_seen and delivered is not None and delivered < t:
                                refs.append(d["decision_id"])
                                if reply["disposition"] == "accepted":
                                    authorized.add(rid)
                                else:
                                    authorized.discard(rid)
                    travelers = set(c["party"]["traveler_ids"])
                    if set(c["accepted_by"]) != travelers or not travelers <= authorized:
                        issues.append("agreement_without_matching_member_authorization")
                    if not travelers <= set(self.profile_h[hid]["decision_resident_ids"]):
                        issues.append("agreement_uses_nondecision_traveler")
                    if c["created_step"] < raw["step"] or c["created_step"] > step:
                        issues.append("agreement_creation_time_mismatch")
                if c["status"] in ("executed", "rejected"):
                    matches = [d for d in event["decisions"] if d["outcome"].get("state_delta", {}).get("commitment_id") == cid]
                    if not matches or not all(d["outcome"]["status"] == c["status"] for d in matches):
                        issues.append("terminal_agreement_state_without_matching_outcome")
                    refs.extend(d["decision_id"] for d in matches)
                elif c["status"] == "cancelled":
                    explicit = any(cid in d["decision"].get("cancel_commitment_ids", []) and d["agent"] in c["accepted_by"] for d in event["decisions"])
                    expired = old is not None and old["status"] == "accepted" and old["party"]["depart_step"] < step
                    superseded = any(x.get("supersedes_id") == cid and x["created_step"] == step for _, x in current.values())
                    if not (explicit or expired or superseded):
                        issues.append("cancellation_without_effective_event")
                elif c["status"] != "accepted":
                    issues.append("unsupported_agreement_state")
                if old is not None and any(c[k] != old[k] for k in ("party", "accepted_by", "created_step", "supersedes_id")):
                    issues.append("same_agreement_identity_changed_its_terms")
                records.append({"record_id": f"{cid}@{step}", "commitment_id": cid, "household_id": hid,
                    "step": step, "status_before": old["status"] if old else None, "status_after": c["status"],
                    "issues": sorted(set(issues)), "evidence": sorted(set(refs))})
            previous = {cid: c for cid, (_, c) in current.items()}
        self.evidence["consensus"] = records
        self.extras["joint_agreements"] = len(creations)
        self.extras["solo_records_excluded_from_joint_consensus"] = sum(len(c["party"]["traveler_ids"]) < 2 for _, c in commitments(self.events[-1]["world"]).values())
        return metric(records, "多人共同方案的可见创建／状态变更；单人自动出发记录不充当家庭共识样本。",
            ["核验日志中实际出现的状态变化，不证明尚未出现的情景也会正确。",
             "使用逐步前后记录和原始接受／撤回决策；同一步内部全部临时状态未逐项持久化。"])

    def audit_execution(self):
        records, other, global_checks = [], [], []
        safe = self.cfg["experiment"]["safe_zone"]
        departures = read_jsonl(self.run / "household_departure_ledger.jsonl")
        previous_locations = self.initial["world"]["member_locations"]
        for event in self.events:
            step = event["step"]
            before, after = agents(event["state_before_decisions"]), agents(event)
            preloc = event["state_before_decisions"]["world"]["member_locations"]
            postloc = event["world"]["member_locations"]
            cs = commitments(event["world"])
            allowed_moves = set()
            for d in event["decisions"]:
                rid, a, o = d["agent"], d["decision"], d["outcome"]
                issues = []
                if o["decision_id"] != d["decision_id"] or o["agent_id"] != rid:
                    issues.append("outcome_identity_mismatch")
                if o["status"] not in ("executed", "rejected"):
                    issues.append("unknown_outcome_status")
                moved = postloc.get(rid) != preloc.get(rid)
                if a["action"] == "evacuate" and o["status"] == "executed":
                    cid = o.get("state_delta", {}).get("commitment_id")
                    entry = cs.get(cid)
                    if not moved or postloc.get(rid) != safe:
                        issues.append("executed_departure_without_matching_location_change")
                    if not after[rid]["evacuating"] or after[rid]["evac_step"] != step:
                        issues.append("resident_execution_state_mismatch")
                    if entry is None:
                        issues.append("executed_departure_without_party_record")
                    else:
                        hid, c = entry
                        p = c["party"]
                        party_members = set(p["traveler_ids"]) | set(p["accompanying_member_ids"])
                        allowed_moves.update(party_members)
                        if c["status"] != "executed" or rid not in p["traveler_ids"]:
                            issues.append("executed_party_state_mismatch")
                        for field in ("route_id", "vehicle_id", "depart_step"):
                            if a.get(field) != p[field]:
                                issues.append("request_party_mismatch:" + field)
                        if p["depart_step"] != step:
                            issues.append("departure_executed_at_wrong_step")
                        if any(postloc.get(m) != safe or preloc.get(m) == safe for m in party_members):
                            issues.append("party_members_not_transferred_exactly_once")
                        matching = [x for x in departures if x["commitment_id"] == cid and x["step"] == step]
                        if len(matching) != 1 or matching[0]["outcome"] != "executed":
                            issues.append("departure_ledger_mismatch")
                        elif set(matching[0]["traveler_ids"]) | set(matching[0]["accompanying_member_ids"]) != party_members:
                            issues.append("departure_ledger_member_mismatch")
                        for traveler in p["traveler_ids"]:
                            td = self.decisions.get((step, traveler))
                            if td is None or td["decision"]["action"] != "evacuate" or td["outcome"]["status"] != "executed" or td["outcome"].get("state_delta", {}).get("commitment_id") != cid:
                                issues.append("party_executed_without_each_traveler_intent")
                else:
                    if moved:
                        issues.append("nonexecuted_departure_changed_location")
                    if (after[rid]["evacuating"], after[rid]["evac_step"]) != (before[rid]["evacuating"], before[rid]["evac_step"]):
                        issues.append("nonexecuted_departure_changed_resident_execution_state")
                    cid = o.get("state_delta", {}).get("commitment_id")
                    if o["status"] == "rejected" and cid in cs and cs[cid][1]["status"] == "executed":
                        issues.append("rejected_request_recorded_as_executed_party")
                # In this archive, executed_action also names rejected requests.
                # It is never sufficient on its own to infer that an action happened.
                feedback = [f for f in after[rid]["recent_execution_feedback"] if f["step"] == step]
                if len(feedback) != 1 or feedback[0]["status"] != o["status"] or feedback[0]["reason"] != o.get("reason"):
                    issues.append("execution_feedback_mismatch")
                row = {"record_id": d["decision_id"], "household_id": self.member_h[rid], "resident_id": rid,
                    "step": step, "action": a["action"], "outcome": o["status"], "reason": o.get("reason"),
                    "issues": sorted(set(issues)), "evidence": [f"events/events.jsonl#step={step}/decisions/{d['decision_id']}",
                        f"events/events.jsonl#step={step}/state_before_decisions", f"events/events.jsonl#step={step}/world/member_locations/{rid}"]}
                (records if a["action"] == "evacuate" else other).append(row)
            actual_moves = {rid for rid in set(preloc) | set(postloc) if preloc.get(rid) != postloc.get(rid)}
            global_issues = [] if actual_moves == allowed_moves else ["global_location_change_has_missing_or_extra_members"]
            if preloc != previous_locations:
                global_issues.append("unexplained_location_change_before_decision_phase")
            global_checks.append({"step": step, "expected_moved_members": sorted(allowed_moves), "actual_moved_members": sorted(actual_moves),
                "issues": global_issues})
            previous_locations = postloc
        self.evidence["execution"] = records
        self.evidence["nondeparture_execution_checks"] = other
        self.evidence["all_member_transition_checks"] = global_checks
        self.extras["nondeparture_checks"] = metric(other, "非出发行动不能被记作人员已经出发；求助成功不等于接送完成。")
        self.extras["all_member_transition_checks"] = metric(global_checks, "每步全体成员位置变化集合与成功执行队伍一致。")
        self.extras["departure_outcomes"] = dict(Counter(r["outcome"] for r in records))
        return metric(records, "每个撤离请求与其执行结果、成员位置、居民执行状态及反馈的一致性。",
            ["这是可计算的出发状态部分：每个 decision_id 计一次；被拒绝请求本身不计错。",
             "没有逐步完整车辆／占用／道路用量快照；不能据此声称全部资源副作用均已核验。",
             "另检验全部非出发决策及每步全体成员的位置变化，结果单独保存，避免用大量非出发动作稀释分母。"])

    def input_checks(self):
        contradictions = []
        for p in self.profiles:
            structure = p["shared_attributes"].get("household_structure")
            count = len(p["member_profiles"])
            issue = ("多人住户被标注为独居" if structure == "nonfamily_living_alone" and count > 1 else
                     "单人住户被标注为非独居" if structure == "nonfamily_not_living_alone" and count == 1 else None)
            if issue:
                contradictions.append({"household_id": p["household_id"], "member_count": len(p["member_profiles"]),
                    "household_structure": p["shared_attributes"]["household_structure"],
                    "source": "selected_profiles.jsonl", "issue": issue})
        payload_hits = []
        for (step, rid), x in self.inputs.items():
            hh = x["payload"].get("household_profile", {})
            structure = hh.get("housing", {}).get("household_structure")
            count = len(hh.get("members", []))
            if ((structure == "nonfamily_living_alone" and count > 1) or
                    (structure == "nonfamily_not_living_alone" and count == 1)):
                payload_hits.append({"step": step, "resident_id": rid})
        return {"household_description_contradictions": contradictions, "contradictory_decision_inputs": payload_hits,
                "note": "输入矛盾单独报告，不混入三项状态错误率；程序核验不修改原始输入，行为评分另行保留这些矛盾。"}

    def audit_exports(self):
        """Terminal ledgers must agree with their recorded final-step sources."""
        final = self.events[-1]
        records = []
        for filename, field, expected in [
            ("official_receipts.jsonl", "receipt_id", final["interaction"]["receipts"]),
            ("message_ledger.jsonl", "message_id", list(final["interaction"]["messages"].values())),
            ("resident_state_timeline.jsonl", "id", final["agents"]),
        ]:
            actual = read_jsonl(self.run / filename)
            a = {x[field]: x for x in actual}
            b = {x[field]: x for x in expected}
            issues = []
            if len(a) != len(actual):
                issues.append("duplicate_export_identity")
            if a != b:
                issues.append("terminal_export_differs_from_final_step")
            records.append({"record_id": filename, "records": len(actual), "issues": issues})
        self.evidence["terminal_export_checks"] = records
        return records

    def household_trace(self, household_id=None):
        # Choose by initial household structure/ID, before inspecting outcomes.
        p = (self.profile_h[household_id] if household_id is not None else
             next(p for p in sorted(self.profiles, key=lambda p: p["household_id"]) if len(p["decision_resident_ids"]) >= 2))
        hid = p["household_id"]
        mids = {m["resident_id"] for m in p["member_profiles"]}
        rows = []
        for e in self.events:
            step = e["step"]
            messages = []
            for mid, m in e["interaction"]["messages"].items():
                if m["sender_id"] in mids and m["issued_step"] == step:
                    messages.append({"stage": "sent", "record_id": mid, "data": m})
                for rid in mids & set(m["recipient_states"]):
                    s = m["recipient_states"][rid]
                    for field, stage in [("delivered_step", "delivered"), ("processed_step", "processed"), ("response_step", "responded")]:
                        if s[field] == step:
                            messages.append({"stage": stage, "record_id": mid, "recipient_id": rid, "data": m})
            notices = [n for n in e["interaction"]["commitment_notifications"] if n["recipient_id"] in mids and n["delivered_step"] == step]
            decisions = [d for d in e["decisions"] if d["agent"] in mids]
            rows.append({"step": step, "sim_minutes": e["sim_minutes"],
                "source": f"events/events.jsonl#step={step}",
                "official_receipts_delivered": [r for r in e["interaction"]["receipts"] if r["resident_id"] in mids and r["delivered_step"] == step],
                "message_events": messages, "protocol_notices": notices,
                "decision_inputs": [self.inputs[(step, d["agent"])] for d in decisions if (step, d["agent"]) in self.inputs],
                "decisions": decisions,
                "agents_before": [a for a in e["state_before_decisions"]["agents"] if a["id"] in mids],
                "agents_after": [a for a in e["agents"] if a["id"] in mids],
                "world_locations_before": {m: e["state_before_decisions"]["world"]["member_locations"][m] for m in sorted(mids)},
                "world_locations_after": {m: e["world"]["member_locations"][m] for m in sorted(mids)},
                "world_routes": e["world"]["route_state"],
                "household_commitments": e["world"]["household_commitments"][hid]})
        return {"selection_rule": "按初始化 household_id 升序选择首个具有至少两名决策成员的住户；不按结果选。",
                "household_id": hid, "profile": p, "steps": rows, "formal_behavior_score": None}

    def run_checks(self):
        identity = self.source_identity()
        result = {"audit_version": "one-run-development-v1", "new_simulations": 0, "new_model_requests": 0,
            "formal_behavior_score": None, "formal_scenario_pass_rate": None,
            "source_identity": identity, "seed": self.provenance["seed"], "model_recorded_by_run": self.provenance["model"],
            "completed_steps": len(self.events), "households": len(self.profiles), "members": len(self.member_h),
            "decision_residents": len(self.initial["agents"]), "decision_count": len(self.decisions),
            "metrics": {"information": self.audit_information(), "consensus": self.audit_consensus(), "execution": self.audit_execution()},
            "additional_checks": self.extras, "input_checks": self.input_checks(),
            "terminal_export_checks": self.audit_exports()}
        result["metrics"]["information"]["full_spec_coverage"] = "partial: structured receipt facts only"
        result["metrics"]["consensus"]["full_spec_coverage"] = "logged joint state changes; no claim about unobserved intrastep states"
        result["metrics"]["execution"]["full_spec_coverage"] = "partial: departure states; complete resource-side-effect audit unavailable"
        return result


def render_trace(trace):
    members = trace["profile"]["member_profiles"]
    names = {m["resident_id"]: chr(65 + i) for i, m in enumerate(members)}
    action_names = {"stay": "等待／留守", "prepare": "准备", "seek_help": "求助", "offer_help": "提出帮助", "evacuate": "申请出发"}
    lines = ["# 一个家庭的完整运行过程", "", "这是开发检查样例，没有进行正式行为评分。", "",
        f"原始家庭编号：`{trace['household_id']}`。", "", trace["selection_rule"], "",
        "## 初始化", "", "| 代号 | 原始编号 | 年龄 | 日志中的关系 |", "| --- | --- | --- | --- |"]
    for m in members:
        lines.append(f"| {names[m['resident_id']]} | {m['resident_id']} | {m['age']} | {m['relationship']} |")
    lines += ["", f"共享车辆数：{trace['profile']['shared_attributes']['vehicle_count']}。关系名称按原始记录保留，不能擅自改写为夫妻。",
        "", (f"输入问题：成员表有 {len(members)} 人，但该家庭的 household_structure 标注为 nonfamily_living_alone（独居）。原始材料保持原样；该矛盾需要在正式行为评阅前处理。"
               if len(members) > 1 and trace['profile']['shared_attributes'].get('household_structure') == 'nonfamily_living_alone'
               else "家庭成员及结构字段按原始输入保留。"),
        "", "## 全部时间步", "", "‘没有决策’表示该步没有调用该居民决策，不等于他明确选择留守。求助动作被接受，不等于已经完成接送。",
        "", "| 步／累计小时 | 信息与沟通 | 居民决策及执行结果 | 步末人员位置 |", "| --- | --- | --- | --- |"]
    for e in trace["steps"]:
        info = [f"{names[r['resident_id']]} 收到{'强制' if r['severity']=='mandatory' else '建议'}撤离通知（{r['source_event_id']}）" for r in e["official_receipts_delivered"]]
        for msg in e["message_events"]:
            who = names.get(msg.get("recipient_id", msg["data"]["sender_id"]), msg["data"]["sender_id"])
            verb = {"sent": "发送", "delivered": "收到", "processed": "处理", "responded": "回应"}[msg["stage"]]
            info.append(f"{who} {verb}消息 {msg['record_id']}")
        actions = []
        for d in e["decisions"]:
            o = d["outcome"]
            outcome = "被拒绝：" + str(o.get("reason")) if o["status"] == "rejected" else "执行接受"
            if d["decision"]["action"] == "evacuate" and o["status"] == "executed":
                outcome = "实际出发，世界将其置于安全区"
            actions.append(f"{names[d['agent']]}：{action_names[d['decision']['action']]}，{outcome}")
        locations = [f"{names[m]}：{'安全区' if loc=='controlled_safe_zone' else '原住处'}" for m, loc in e["world_locations_after"].items()]
        lines.append(f"| {e['step']}／{e['sim_minutes']/60:g} | {'；'.join(info) or '没有新增信息事件'} | {'；'.join(actions) or '两人均无本步决策'} | {'；'.join(locations)} |")
    lines += ["", "## 原始沟通与行动内容", "", "以下内容逐条取自日志，不补写动机；完整决策输入、计划、状态和记录定位见同目录 household_trace.json。", ""]
    for e in trace["steps"]:
        for d in e["decisions"]:
            lines += [f"### 第 {e['step']} 步，{names[d['agent']]}", "", f"记录：`{d['decision_id']}`。", "",
                "模型当时输出的简短评估（原文；不作为已经核实的事实）：", "", "> " + d["decision"].get("assessment", "").replace("\n", "\n> "), ""]
            for msg in d["decision"].get("messages", []):
                lines += [f"发送目标 `{msg['to']}`，类型 `{msg['kind']}`：", "", "> " + msg["content"].replace("\n", "\n> "), ""]
            for reply in d["decision"].get("message_responses", []):
                lines.append(f"回应 `{reply['message_id']}`：`{reply['disposition']}`。")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    batch = args.repo.resolve() / "paper/ieee_journal/working/main_experiments_20260905"
    # Accepted run first, by numeric seed; not by outcomes or existing scores.
    accepted = sorted(batch.glob("runs/24hh_seed*/accepted.json"), key=lambda p: int(p.parent.name.split("seed")[1]))[0]
    accepted_data = read_json(accepted)
    attempt = accepted.parent / f"attempt{accepted_data['attempt']}"
    run = attempt / Path(accepted_data["run_dir"]).name
    audit = Audit(run, batch)
    paths = sorted(p for p in run.rglob("*") if p.is_file())
    before_hashes = {str(p.relative_to(run)): digest(p) for p in paths}
    results = audit.run_checks()
    trace = audit.household_trace()
    household_id = trace["household_id"]
    member_ids = {m["resident_id"] for m in trace["profile"]["member_profiles"]}
    results["sample_household_checks"] = {
        kind: metric([r for r in audit.evidence[kind] if r.get("household_id") == household_id or r.get("resident_id") in member_ids],
                     results["metrics"][kind]["scope"])
        for kind in ("information", "consensus", "execution")
    }
    after_hashes = {str(p.relative_to(run)): digest(p) for p in paths}
    if before_hashes != after_hashes:
        raise RuntimeError("Original run changed during the read-only audit")
    if args.output.resolve() == run.resolve() or run.resolve() in args.output.resolve().parents:
        raise ValueError("Write audit outputs outside the immutable original run")
    args.output.mkdir(parents=True, exist_ok=True)
    dump(args.output / "audit_results.json", results)
    dump(args.output / "check_records.json", audit.evidence)
    dump(args.output / "household_trace.json", trace)
    (args.output / "家庭全过程样例.md").write_text(render_trace(trace), encoding="utf-8")
    dump(args.output / "input_manifest.json", {"repository": "https://github.com/byp411426/paper_agentsimulation",
        "run_path_relative_to_repo": str(run.relative_to(args.repo.resolve())),
        "selection": "数值最小种子的 accepted.json 所指向的单个 attempt；家庭按初始化编号及决策成员数选择。",
        "accepted_attempt": accepted_data["attempt"], "source_files_sha256": before_hashes,
        "read_only_hashes_unchanged": True, "evaluator_sha256": digest(__file__)})
    print(json.dumps({"seed": results["seed"], "steps": results["completed_steps"], "metrics": results["metrics"],
        "input_contradiction_households": len(results["input_checks"]["household_description_contradictions"]),
        "output": str(args.output.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
