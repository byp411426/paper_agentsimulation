#!/usr/bin/env python3
"""Run a small SCRIPTED, offline process check. Never calls a model service.

This is software verification, not an autonomous simulation or a paper score.
Usage from disastersociety/: python -m scripts.check_e1_process --output /new/path
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from ds.llm.backends import MockBackend
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from experiments.carr.empirical_v2_runner import run_e1_v2


def write_fixture_inputs(folder: Path) -> tuple[dict, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    profiles = []
    for hid, adults, children in [("fixture_A", 2, 1), ("fixture_B", 1, 0)]:
        members = []
        for index in range(adults + children):
            capable = index < adults
            members.append({"resident_id": f"{hid}_r{index + 1}", "household_id": hid,
                "age": 35 if capable else 8, "decision_capable": capable,
                "decision_policy": "generative" if capable else "dependent",
                "needs_execution_assistance": not capable,
                "relationship": "reference person" if index == 0 else "household member",
                "pums_static": {}, "latent_traits": {}, "functional_limitations": {}})
        decision_ids = [m["resident_id"] for m in members if m["decision_capable"]]
        dependent_ids = [m["resident_id"] for m in members if not m["decision_capable"]]
        profiles.append({"household_id": hid, "shared_attributes": {"vehicle_count": 1,
            "household_structure": "other_female_householder" if children else "nonfamily_living_alone"},
            "member_profiles": members, "decision_resident_ids": decision_ids,
            "nondecision_member_ids": dependent_ids, "care_recipient_ids": dependent_ids,
            "focal_resident_id": decision_ids[0], "coordinator_id": decision_ids[0]})
    path = folder / "profiles.jsonl"
    path.write_text("".join(json.dumps(p) + "\n" for p in profiles), encoding="utf-8")
    calibration = folder / "orders.json"
    calibration.write_text(json.dumps({"calibration": {"main_excluding_15_contradictions": {
        "proportions": {"voluntary_then_mandatory": 1.0}}}}), encoding="utf-8")
    cfg = {"run": {"run_id": "offline_process", "total_steps": 8, "step_minutes": 30},
        "llm": {"decision_model": "scripted", "temperature": 0, "fallback_threshold": 0},
        "experiment": {"order_calibration": str(calibration.resolve()),
            "social_graph": {"radius_m": 1500, "k_neighbors": 2, "k_friends": 0, "rewire_p": 0},
            "vehicles": {"capacity": 4},
            "hazard": {"initial_distance_m": 2000, "approach_per_step_m": 50},
            "routes": {"primary_route_id": "primary", "alternate_route_id": "alternate",
                       "closure_step": 3, "route_capacity_per_step": 2},
            "orders": {"voluntary_step": 1, "mandatory_step": 4},
            "delivery": {"household_dm_probability": 1, "community_message_probability": 1},
            "safe_zone": "safe"}}
    return cfg, path


def scripted_policy(messages, seed, schema):
    p = json.loads(messages[-1]["content"])
    rid, step = p["resident_id"], p["current_step"]
    d = {"action": "prepare", "assessment": "Scripted process fixture, not model behavior."}
    if rid == "fixture_A_r1" and step in (1, 4):
        d["party_proposal"] = {"traveler_ids": ["fixture_A_r1", "fixture_A_r2"],
            "accompanying_member_ids": ["fixture_A_r3"],
            "caregiver_by_member": {"fixture_A_r3": "fixture_A_r1"},
            "vehicle_id": "fixture_A:vehicle:1", "route_id": "primary" if step == 1 else "alternate",
            "depart_step": step + 2, "content": "Please agree to this exact trip."}
    if rid == "fixture_A_r2":
        d["message_responses"] = [{"message_id": m["message_id"], "disposition": "accepted"}
            for m in p["observed_now"]["inbox"] if m.get("message_kind") == "proposal"]
    for c in p["own_commitment_statuses"]:
        if c["status"] == "accepted" and c["depart_step"] == step:
            d.update(action="evacuate", departure_mode="commitment", commitment_id=c["commitment_id"],
                     vehicle_id=c["vehicle_id"], route_id=c["route_id"], depart_step=step)
    if rid == "fixture_B_r1" and step == 2:
        d.update(action="evacuate", departure_mode="solo", vehicle_id="fixture_B:vehicle:1",
                 route_id="alternate", depart_step=step)
    return d


def verify_process(run: Path) -> dict:
    def rows(name):
        return [json.loads(s) for s in (run / name).read_text().splitlines() if s.strip()]
    events = rows("events/events.jsonl")
    if len(events) != 8:
        return {"kind": "scripted_software_check", "checks": {"complete_eight_steps": False},
                "all_checks_passed": False, "model_service_requests": 0,
                "formal_behavior_score": None, "formal_scenario_pass_rate": None}
    decisions = [d for e in events for d in e["decisions"]]
    closed = [d for d in decisions if d["outcome"]["reason"] == "route_closed"]
    checks = {
        "complete_eight_steps": len(events) == 8,
        "joint_trip_waits_for_acceptance": not events[0]["world"]["household_commitments"]["fixture_A"],
        "closed_route_rejects_both_requests": len(closed) == 2,
        "rejection_has_no_executed_action": bool(closed) and all(d["outcome"]["executed_action"] is None for d in closed),
        "rejection_preserves_physical_resources": bool(closed) and all(
            d["outcome"]["state_delta"]["physical_before"] == d["outcome"]["state_delta"]["physical_after"] for d in closed),
        "revised_trip_moves_all_three_members": all(events[5]["world"]["member_locations"][f"fixture_A_r{i}"] == "safe" for i in (1, 2, 3)),
        "independent_trip_moves_resident": events[1]["world"]["member_locations"]["fixture_B_r1"] == "safe",
        "timeline_covers_every_resident_every_step": len(rows("resident_state_timeline.jsonl")) == 24,
        "terminal_export_has_three_residents": len(rows("resident_terminal_states.jsonl")) == 3,
    }
    inputs = rows("decision_inputs.jsonl")
    observed = {r["observation_id"]: r for r in events[-1]["world"]["observations"]}
    checks["decision_observations_have_matching_sources"] = bool(inputs) and all(
        (source := observed.get(row["payload"]["observed_now"]["observation_id"])) is not None
        and source["resident_id"] == row["resident_id"] and source["step"] == row["step"]
        and all(row["payload"]["observed_now"][key] == value for key, value in source["content"].items())
        for row in inputs)
    return {"kind": "scripted_software_check", "checks": checks,
            "all_checks_passed": all(checks.values()), "model_service_requests": 0,
            "formal_behavior_score": None, "formal_scenario_pass_rate": None}


def run_check(output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Choose a new output directory: {output}")
    cfg, profiles = write_fixture_inputs(output / "inputs")
    run = output / cfg["run"]["run_id"]
    run.mkdir(parents=True)
    cache = LLMCache(run / "cache.sqlite")
    registry = {"models": {"scripted": {"backend": "mock", "input_per_m": 0, "output_per_m": 0}}}
    gateway = LLMGateway(run_id=cfg["run"]["run_id"], models_cfg=registry, budget_usd=1,
        max_concurrency=3, log_dir=output, cache=cache,
        backends={"scripted": MockBackend(policy=scripted_policy)}, abort_on_call_failure=True)
    (run / "execution_config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (run / "provenance.json").write_text(json.dumps({"kind": "scripted_software_check", "seed": 7,
        "profiles_sha256": hashlib.sha256(profiles.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}), encoding="utf-8")
    try:
        status = run_e1_v2(cfg=cfg, out_dir=output, gateway=gateway, run_seed=7,
                           n_households=2, profiles_path=profiles)
    finally:
        gateway.close()
        cache.close()
    result = verify_process(run)
    result["run_status"] = status["status"]
    result["all_checks_passed"] &= status["status"] == "VALID"
    (output / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = run_check(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
