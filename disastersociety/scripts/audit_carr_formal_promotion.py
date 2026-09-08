#!/usr/bin/env python3
"""Formal promotion audit for the Carr-S studies beyond the E2 v8 r7 matrix.

Covers four studies and writes one audit artifact pair (.json/.md) each:
  1. E1 v2 empirical-process formal minimal sample (3 seeds x 24 households)
  2. E3 v1 bounded cross-model replication (7 models x 4 seeds x 3 conditions)
  3. E3a equivalent-prompt sensitivity (2 variants x 4 seeds x 3 conditions)
  4. E3c scale-100 demonstration (2 seeds x 100 households)

Gates per study: expected cells present, terminal status VALID with complete
steps, zero failed and fallback rate below the 1% project gate, provenance
consistency across cells (git sha, source-file hashes, prompt identity,
decision-model identity where provenance.json exists), and recomputed
aggregates matching the recorded per-run summaries. Studies that pass every
gate are labeled COMPLETE_VALID following the E2 v8 r7 convention; otherwise
the audit lists the problems and the study keeps its current label.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "experiments/carr/results"
RUNS = PROJECT_ROOT / "experiments/carr/runs"
CONFIGS = PROJECT_ROOT / "experiments/carr/configs"

FALLBACK_GATE = 0.01


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def call_accounting(run_dir: Path) -> dict:
    counts: dict[str, int] = {}
    for call in load_jsonl(run_dir / "llm_calls.jsonl"):
        status = call.get("status")
        counts[status] = counts.get(status, 0) + 1
    ok = counts.get("ok", 0)
    cache = counts.get("cache_hit", 0)
    failed = counts.get("failed", 0)
    fallback = counts.get("fallback", 0)
    denom = ok + cache + fallback
    return {
        "status_counts": counts,
        "n_ok": ok,
        "n_cache": cache,
        "n_failed": failed,
        "n_fallback": fallback,
        "fallback_rate": (fallback / denom) if denom else 0.0,
    }


def provenance_consistency(
    cells: list[dict], allowed_source_hashes: dict[str, set] | None = None
) -> dict:
    """Check git sha, source-file hashes, prompt identity across cells.

    When allowed_source_hashes is given, each cell's source-file hash must be
    inside the per-file allowlist (used for the E3 v1 matrix, where the frozen
    reconstruction/re-freeze amendments sanction two documented builds of the
    resident adapter and the gateway); the per-hash cell counts are recorded.
    Without an allowlist, hashes must be identical across cells.
    """
    git_shas = set()
    source_hashes: dict[str, set] = {}
    hash_cell_counts: dict[str, dict[str, int]] = {}
    prompts = set()
    models = set()
    n_with_prov = 0
    violations = []
    for cell in cells:
        prov_path = cell["dir"] / "provenance.json"
        if not prov_path.exists():
            continue
        n_with_prov += 1
        prov = load_json(prov_path)
        git_shas.add(prov.get("git_sha"))
        for key, entry in (prov.get("source_files") or {}).items():
            digest = entry.get("sha256")
            source_hashes.setdefault(key, set()).add(digest)
            counts = hash_cell_counts.setdefault(key, {})
            counts[digest] = counts.get(digest, 0) + 1
            if allowed_source_hashes and key in allowed_source_hashes:
                if digest not in allowed_source_hashes[key]:
                    violations.append(
                        f"{cell['dir'].name}: {key} hash {digest[:12]} not sanctioned"
                    )
        exp = prov.get("config", {}).get("experiment", {})
        prompts.add(exp.get("prompt_version"))
        variant = exp.get("prompt_variant")
        if variant:
            prompts.add(f"{exp.get('prompt_version')}:{variant}")
        for model in prov.get("models") or []:
            models.add(model)
        decision_model = prov.get("config", {}).get("llm", {}).get(
            "decision_model"
        )
        if decision_model:
            models.add(decision_model)
    inconsistent = {
        key: sorted(values) for key, values in source_hashes.items() if len(values) > 1
    }
    if allowed_source_hashes:
        inconsistent = {
            key: value
            for key, value in inconsistent.items()
            if key not in allowed_source_hashes
        }
    return {
        "cells_with_provenance": n_with_prov,
        "git_shas": sorted(git_shas),
        "git_sha_consistent": len(git_shas) <= 1,
        "source_file_hashes_consistent": not inconsistent,
        "inconsistent_source_files": inconsistent,
        "sanctioned_hash_violations": violations,
        "hash_cell_counts": {
            key: {h[:12]: n for h, n in counts.items()}
            for key, counts in hash_cell_counts.items()
        },
        "prompt_identities": sorted(p for p in prompts if p),
        "decision_models": sorted(models),
    }


def summarize_e1_style(run_dir: Path) -> dict:
    """Recompute the frozen E1 v2 household metrics from raw ledgers."""
    departures = load_jsonl(run_dir / "household_departure_ledger.jsonl")
    receipts = load_jsonl(run_dir / "official_receipts.jsonl")
    messages = load_jsonl(run_dir / "message_ledger.jsonl")
    commitments = load_jsonl(run_dir / "commitment_ledger.jsonl")
    members = load_jsonl(run_dir / "member_profiles.jsonl")
    executed = [r for r in departures if r["outcome"] == "executed"]
    rejected = [r for r in departures if r["outcome"] == "rejected"]
    households = {m.get("household_id") for m in members}
    departed = {r["household_id"] for r in executed}
    coordinated = [r for r in executed if r.get("coordinated")]
    split = {
        h
        for h in departed
        if sum(1 for r in executed if r["household_id"] == h) > 1
    }
    return {
        "n_households": len(households),
        "n_executed_parties": len(executed),
        "n_rejected_parties": len(rejected),
        "complete_safe_household_departure_rate": (
            len(departed) / len(households) if households else 0.0
        ),
        "coordinated_household_rate": (
            len({r["household_id"] for r in coordinated}) / len(households)
            if households
            else 0.0
        ),
        "split_departure_household_rate": (
            len(split) / len(households) if households else 0.0
        ),
        "violation_counts": {
            "care_recipient_left_behind": sum(
                1
                for r in rejected
                if r.get("reason_code") == "missing_traveler_intent"
                and r["accompanying_member_ids"]
            ),
            "vehicle_conflict": sum(
                1 for r in rejected if r.get("reason_code") == "vehicle_in_use"
            ),
            "capacity_rejection": sum(
                1 for r in rejected if r.get("reason_code") == "vehicle_capacity"
            ),
            "caregiver_violation": sum(
                1
                for r in rejected
                if r.get("reason_code") == "caregiver_not_traveler"
            ),
        },
        "message_funnel": {
            "sent": len(messages),
            "delivered": sum(1 for m in messages if m.get("delivered_step") is not None),
            "processed": sum(1 for m in messages if m.get("processed_step") is not None),
            "accepted": sum(1 for m in messages if m.get("status") == "accepted"),
            "rejected": sum(1 for m in messages if m.get("status") == "rejected"),
        },
        "official_receipt_counts": {
            severity: sum(1 for r in receipts if r["severity"] == severity)
            for severity in ("voluntary", "mandatory")
        },
        "commitment_counts": {
            status: sum(1 for c in commitments if c["status"] == status)
            for status in ("accepted", "cancelled", "executed", "rejected")
        },
    }


# ---------------------------------------------------------------- E1 v2 formal


def audit_e1_v2() -> dict:
    seeds = [
        (7201, "e1_formal_r7_seed7201", "carr_s_e1_v2_formal_r7_seed7201_summary.json"),
        (8301, "e1_formal_r10_seed8301", "carr_s_e1_v2_formal_r10_seed8301_summary.json"),
        (9401, "e1_formal_r9_seed9401", "carr_s_e1_v2_formal_r9_seed9401_summary.json"),
    ]
    problems: list[str] = []
    rows = []
    for seed, dir_name, summary_name in seeds:
        run_dir = RUNS / dir_name / "carr_s_e1_v2_formal"
        if not run_dir.exists():
            problems.append(f"missing run dir {dir_name}")
            continue
        run_summary = load_json(run_dir / "run_summary.json")
        events_summary = load_json(run_dir / "events/summary.json")
        accounting = call_accounting(run_dir)
        recomputed = summarize_e1_style(run_dir)
        recorded = load_json(RESULTS / summary_name)
        mismatches = []
        for key in (
            "complete_safe_household_departure_rate",
            "coordinated_household_rate",
            "split_departure_household_rate",
            "n_executed_parties",
            "n_rejected_parties",
        ):
            if abs(recomputed[key] - recorded[key]) > 1e-9:
                mismatches.append(
                    f"{key}: recomputed {recomputed[key]} != recorded {recorded[key]}"
                )
        if run_summary["status"] != "VALID" or run_summary.get("reason_code"):
            problems.append(f"seed {seed}: terminal {run_summary['status']}")
        if events_summary["completed_steps"] != events_summary["planned_steps"]:
            problems.append(f"seed {seed}: steps incomplete")
        if accounting["n_failed"] or accounting["fallback_rate"] > FALLBACK_GATE:
            problems.append(
                f"seed {seed}: failed={accounting['n_failed']} "
                f"fallback_rate={accounting['fallback_rate']:.4f}"
            )
        problems.extend(f"seed {seed}: {m}" for m in mismatches)
        rows.append(
            {
                "seed": seed,
                "run_dir": dir_name,
                "status": run_summary["status"],
                "steps": f"{events_summary['completed_steps']}/{events_summary['planned_steps']}",
                "accounting": accounting,
                "metrics": recomputed,
                "matches_recorded_summary": not mismatches,
            }
        )
    config_ok = (CONFIGS / "carr_s_e1_empirical_v2_formal.yaml").exists()
    if not config_ok:
        problems.append("declared config carr_s_e1_empirical_v2_formal.yaml missing")
    safe = [r["metrics"]["complete_safe_household_departure_rate"] for r in rows]
    coord = [r["metrics"]["coordinated_household_rate"] for r in rows]
    passed = not problems and len(rows) == 3
    return {
        "study": "E1 v2 empirical-process formal minimal sample",
        "protocol_id": "carr_s_e1_v2_formal_minimal_sample",
        "runs": rows,
        "aggregate": {
            "n_runs": len(rows),
            "complete_safe_household_departure_rate_mean": mean(safe),
            "complete_safe_household_departure_rate_sd": sd(safe),
            "coordinated_household_rate_mean": mean(coord),
            "coordinated_household_rate_sd": sd(coord),
            "message_funnel_totals": {
                key: sum(r["metrics"]["message_funnel"][key] for r in rows)
                for key in ("sent", "delivered", "processed", "accepted", "rejected")
            },
            "violation_totals": {
                key: sum(r["metrics"]["violation_counts"][key] for r in rows)
                for key in (
                    "care_recipient_left_behind",
                    "vehicle_conflict",
                    "capacity_rejection",
                    "caregiver_violation",
                )
            },
        },
        "problems": problems,
        "all_gates_pass": passed,
        "evidence_label": "COMPLETE_VALID" if passed else "RUNNING_PENDING_AUDIT",
        "claim_boundary": (
            "Carr-informed controlled scenario; not historical reconstruction, "
            "not population representative, not individual-level validation."
        ),
    }


# ---------------------------------------------------- matrix studies (E3, E3a)


def audit_matrix(
    study: str,
    protocol_id: str,
    dir_prefixes: list[str],
    seeds: list[int],
    conditions: list[str],
    expected_prompt_fragments: list[str],
    allowed_source_hashes: dict[str, set] | None = None,
    provenance_note: str | None = None,
) -> dict:
    expected = {(s, c, p) for s in seeds for c in conditions for p in dir_prefixes}
    cells = []
    problems: list[str] = []
    found: set[tuple[int, str, str]] = set()
    for prefix in dir_prefixes:
        for condition in conditions:
            for seed in seeds:
                directory = RUNS / f"{prefix}_{condition}_seed{seed}"
                key = (seed, condition, prefix)
                if not directory.exists():
                    problems.append(f"missing cell {prefix}/{condition}/seed{seed}")
                    continue
                metrics_path = directory / "mechanism_metrics.json"
                summary_path = directory / "summary.json"
                if not metrics_path.exists() or not summary_path.exists():
                    problems.append(f"incomplete artifacts in {directory.name}")
                    continue
                metrics = load_json(metrics_path)
                summary = load_json(summary_path)
                accounting = call_accounting(directory)
                terminal = metrics.get("run_terminal_status") or summary.get("status")
                ok = terminal == "VALID"
                if not ok:
                    problems.append(f"{directory.name}: terminal {terminal}")
                if accounting["n_failed"] or accounting["fallback_rate"] > FALLBACK_GATE:
                    problems.append(
                        f"{directory.name}: failed={accounting['n_failed']} "
                        f"fallback={accounting['fallback_rate']:.4f}"
                    )
                found.add(key)
                cells.append(
                    {
                        "dir": directory,
                        "seed": seed,
                        "condition": condition,
                        "prefix": prefix,
                        "terminal": terminal,
                        "accounting": accounting,
                        "metrics": metrics,
                    }
                )
    missing = expected - found
    for seed, condition, prefix in sorted(missing):
        problems.append(f"cell not usable: {prefix}/{condition}/seed{seed}")

    prov = provenance_consistency(cells, allowed_source_hashes)
    if prov["cells_with_provenance"] != len(cells):
        problems.append(
            f"provenance.json on {prov['cells_with_provenance']}/{len(cells)} cells"
        )
    if not prov["git_sha_consistent"]:
        problems.append(f"git sha inconsistent: {prov['git_shas']}")
    if not prov["source_file_hashes_consistent"]:
        problems.append("source file hashes inconsistent across cells")
    for violation in prov.get("sanctioned_hash_violations", []):
        problems.append(violation)
    for fragment in expected_prompt_fragments:
        if not any(fragment in p for p in prov["prompt_identities"]):
            problems.append(f"expected prompt identity {fragment} not found")

    # Paired contrasts per lane: feedback and interaction downstream.
    contrasts = {}
    for prefix in dir_prefixes:
        fb_deltas, ia_deltas = [], []
        fb_checks, ia_checks = [], []
        for seed in seeds:
            by_cond = {
                c["condition"]: c
                for c in cells
                if c["seed"] == seed and c["prefix"] == prefix
            }
            if len(by_cond) != len(conditions):
                continue
            full = by_cond["full"]["metrics"]
            nofb = by_cond["full_minus_feedback"]["metrics"]
            noia = by_cond["full_minus_interaction"]["metrics"]
            fb_deltas.append(
                full["closed_route_rejections_per_household"]
                - nofb["closed_route_rejections_per_household"]
            )
            ia_deltas.append(
                full["coordinated_departure_rate"]
                - noia["coordinated_departure_rate"]
            )
            fb_checks.append(
                full["preclosure_primary_to_postclosure_alternate_update_rate"]
                - nofb["preclosure_primary_to_postclosure_alternate_update_rate"]
            )
            ia_checks.append(
                full["post_closure_feasible_commitment_rate"]
                - noia["post_closure_feasible_commitment_rate"]
            )
        contrasts[prefix] = {
            "feedback_downstream_delta_per_seed": fb_deltas,
            "feedback_downstream_mean": mean(fb_deltas),
            "feedback_downstream_direction_share": (
                sum(1 for d in fb_deltas if d < 0) / len(fb_deltas)
                if fb_deltas
                else None
            ),
            "interaction_downstream_delta_per_seed": ia_deltas,
            "interaction_downstream_mean": mean(ia_deltas),
            "interaction_downstream_direction_share": (
                sum(1 for d in ia_deltas if d > 0) / len(ia_deltas)
                if ia_deltas
                else None
            ),
            "feedback_check_direction_share": (
                sum(1 for d in fb_checks if d > 0) / len(fb_checks)
                if fb_checks
                else None
            ),
            "interaction_check_direction_share": (
                sum(1 for d in ia_checks if d > 0) / len(ia_checks)
                if ia_checks
                else None
            ),
        }
    total_ok = sum(c["accounting"]["n_ok"] for c in cells)
    total_cache = sum(c["accounting"]["n_cache"] for c in cells)
    total_failed = sum(c["accounting"]["n_failed"] for c in cells)
    total_fallback = sum(c["accounting"]["n_fallback"] for c in cells)
    passed = not problems
    return {
        "study": study,
        "protocol_id": protocol_id,
        "expected_cells": len(expected),
        "usable_cells": len(cells),
        "provenance": {
            key: value
            for key, value in prov.items()
            if key != "inconsistent_source_files"
        },
        "provenance_note": provenance_note,
        "lane_contrasts": contrasts,
        "gateway_totals": {
            "n_ok": total_ok,
            "n_cache": total_cache,
            "n_failed": total_failed,
            "n_fallback": total_fallback,
        },
        "problems": problems,
        "all_gates_pass": passed,
        "evidence_label": "COMPLETE_VALID" if passed else "PILOT_PENDING_AUDIT",
    }


# ------------------------------------------------------------------ E3c scale


def audit_e3c_scale() -> dict:
    runs = [
        (101, "e1_scale_100_packy_seed101_r5"),
        (202, "e1_scale_100_packy_seed202_r2"),
    ]
    problems: list[str] = []
    rows = []
    for seed, dir_name in runs:
        run_dir = RUNS / dir_name / "carr_s_e1_scale_100_packy"
        if not run_dir.exists():
            problems.append(f"missing run dir {dir_name}")
            continue
        run_summary = load_json(run_dir / "run_summary.json")
        events_summary = load_json(run_dir / "events/summary.json")
        accounting = call_accounting(run_dir)
        gateway = events_summary.get("gateway") or {}
        recomputed = summarize_e1_style(run_dir)
        if run_summary["status"] != "VALID" or run_summary.get("reason_code"):
            problems.append(f"seed {seed}: terminal {run_summary['status']}")
        if events_summary["completed_steps"] != events_summary["planned_steps"]:
            problems.append(f"seed {seed}: steps incomplete")
        if run_summary.get("n_households") != 100:
            problems.append(f"seed {seed}: n_households={run_summary.get('n_households')}")
        if accounting["n_failed"] or accounting["fallback_rate"] > FALLBACK_GATE:
            problems.append(
                f"seed {seed}: failed={accounting['n_failed']} "
                f"fallback={accounting['fallback_rate']:.4f}"
            )
        if gateway and abs(gateway.get("spent", 0.0)) < 1e-12:
            problems.append(f"seed {seed}: gateway spent is zero; accounting suspect")
        rows.append(
            {
                "seed": seed,
                "run_dir": dir_name,
                "status": run_summary["status"],
                "steps": f"{events_summary['completed_steps']}/{events_summary['planned_steps']}",
                "n_households": run_summary.get("n_households"),
                "n_residents": run_summary.get("n_residents"),
                "n_orders": run_summary.get("n_orders"),
                "wall_clock_seconds": events_summary.get("wall_clock_seconds"),
                "gateway": gateway,
                "accounting": accounting,
                "metrics": recomputed,
            }
        )
    config_ok = (CONFIGS / "carr_s_e1_scale_100_packy.yaml").exists()
    if not config_ok:
        problems.append("declared config carr_s_e1_scale_100_packy.yaml missing")
    passed = not problems and len(rows) == 2
    return {
        "study": "E3c scale-100 demonstration (2 seeds x 100 households)",
        "protocol_id": "carr_s_e3c_scale_efficiency",
        "scope_note": (
            "FROZEN_SCOPE_REDUCTION r5_scale_100_only_20260804: only the "
            "100-household point executed; no 500/1000 claims."
        ),
        "runs": rows,
        "aggregate": {
            "complete_safe_household_departure_rates": [
                r["metrics"]["complete_safe_household_departure_rate"] for r in rows
            ],
            "coordinated_household_rates": [
                r["metrics"]["coordinated_household_rate"] for r in rows
            ],
            "split_departure_household_rates": [
                r["metrics"]["split_departure_household_rate"] for r in rows
            ],
            "total_spent_usd": sum(
                (r["gateway"] or {}).get("spent", 0.0) for r in rows
            ),
            "total_calls": sum(
                r["accounting"]["n_ok"] + r["accounting"]["n_cache"] for r in rows
            ),
        },
        "problems": problems,
        "all_gates_pass": passed,
        "evidence_label": "COMPLETE_VALID" if passed else "PILOT_PENDING_AUDIT",
        "claim_boundary": (
            "Scale/efficiency claims limited to the 100-household envelope "
            "(2 seeds); no 500/1000 stability, throughput, or maximum-size claim."
        ),
    }


def render_md(audit: dict) -> str:
    lines = [
        f"# {audit['study']} — formal promotion audit",
        "",
        f"- protocol: `{audit['protocol_id']}`",
        f"- all gates pass: **{audit['all_gates_pass']}**",
        f"- evidence label: `{audit['evidence_label']}`",
        "",
    ]
    if audit.get("problems"):
        lines += ["## Problems", ""]
        lines += [f"- {p}" for p in audit["problems"]]
        lines.append("")
    if "lane_contrasts" in audit:
        lines += [
            "## Lane contrasts (feedback / interaction downstream)",
            "",
        ]
        for lane, c in audit["lane_contrasts"].items():
            lines.append(
                f"- {lane}: feedback mean {c['feedback_downstream_mean']:.3f} "
                f"(dir {c['feedback_downstream_direction_share']}), "
                f"interaction mean {c['interaction_downstream_mean']:.3f} "
                f"(dir {c['interaction_downstream_direction_share']})"
            )
        lines.append("")
    if "aggregate" in audit:
        lines += ["## Aggregate", "", "```json", json.dumps(audit["aggregate"], indent=1), "```", ""]
    return "\n".join(lines)


def main() -> None:
    audits = {
        "carr_s_e1_v2_formal_promotion_audit": audit_e1_v2(),
        "carr_s_e3_v1_cross_model_promotion_audit": audit_matrix(
            study="E3 v1 bounded cross-model replication",
            protocol_id="carr_s_e3_v1",
            dir_prefixes=[
                "carr_s_e3_v1_deepseek",
                "carr_s_e3_v1_qwen",
                "carr_s_e3_v1_glm",
                "carr_s_e3_v1_gpt54mini",
                "carr_s_e3_v1_qwen27b",
                "carr_s_e3_v1_gemma4",
                "carr_s_e3_v1_qwen36",
            ],
            seeds=[2107, 2209, 2303, 2411],
            conditions=["full", "full_minus_feedback", "full_minus_interaction"],
            expected_prompt_fragments=["carr_s_controlled_resident_v8"],
            allowed_source_hashes={
                "resident_adapter": {
                    "1a6b68a225ed4dc8b077b2ff4a3e1eac4667e29d4625ec9a1b65ff4e548a13ab",
                    "c2ebf7e50679d0ae5a7207170ed8aeb4a6a555e504989cc85b56ccfb4daf36b4",
                },
                "llm_gateway": {
                    "e3c2397b94695a89b1374f4e434044f27d25960b15081579dca7bd736a1cae4d",
                    "132b787e400d515c0c3f857c5d4a21a9b87d9743d24f8364935e9e7c57ae70c0",
                },
            },
            provenance_note=(
                "Two sanctioned builds per the frozen amendments "
                "carr_py_reconstruction_20260804 and carr_py_gateway_refreeze_20260815: "
                "resident adapter original (55 cells) vs reconstructed docstring-only "
                "(29 cells); gateway transport-hardening builds (26 vs 58 cells). "
                "Claude lane (10 partial cells) excluded by user decision and not "
                "part of the 84-cell matrix."
            ),
        ),
        "carr_s_e3a_prompt_sensitivity_promotion_audit": audit_matrix(
            study="E3a equivalent-prompt sensitivity (v8a, v8b)",
            protocol_id="carr_s_e3a_prompt_sensitivity",
            dir_prefixes=["carr_s_e3a_v8a", "carr_s_e3a_v8b_packy"],
            seeds=[2107, 2209, 2303, 2411],
            conditions=["full", "full_minus_feedback", "full_minus_interaction"],
            expected_prompt_fragments=["carr_s_controlled_resident_v8:v8a", "carr_s_controlled_resident_v8:v8b"],
        ),
        "carr_s_e3c_scale_100_promotion_audit": audit_e3c_scale(),
    }
    for name, audit in audits.items():
        (RESULTS / f"{name}.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        (RESULTS / f"{name}.md").write_text(render_md(audit), encoding="utf-8")
        print(
            f"{name}: gates={audit['all_gates_pass']} "
            f"label={audit['evidence_label']} problems={len(audit['problems'])}"
        )


if __name__ == "__main__":
    main()
