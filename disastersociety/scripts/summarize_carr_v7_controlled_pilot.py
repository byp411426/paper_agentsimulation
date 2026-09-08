"""Build the auditable summary for the Carr-S v7 DeepSeek pilot.

The paid matrix was scheduled across multiple non-overlapping worker processes.
This script selects exactly one VALID raw run for each frozen seed-condition
cell, verifies identities, records artifact hashes, and recomputes all paired
contrasts from the selected raw metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import (
    CONDITIONS,
    PRIMARY_MECHANISM_METRICS_V7,
    paired_mechanism_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "experiments/carr/runs"
OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/carr_s_deepseek_v7_controlled_pilot_summary.json"
)


SELECTED_RUNS: dict[tuple[int, str], str] = {}
for seed in (101, 202, 303):
    SELECTED_RUNS[(seed, "full_minus_memory")] = (
        f"carr_s_deepseek_v7_controlled_pilot_r3a_full_minus_memory_seed{seed}"
    )
    SELECTED_RUNS[(seed, "full_minus_planning")] = (
        f"carr_s_deepseek_v7_controlled_pilot_r3a_full_minus_planning_seed{seed}"
    )
    SELECTED_RUNS[(seed, "full_minus_feedback")] = (
        f"carr_s_deepseek_v7_controlled_pilot_r3b_full_minus_feedback_seed{seed}"
    )
    SELECTED_RUNS[(seed, "full_minus_interaction")] = (
        f"carr_s_deepseek_v7_controlled_pilot_r3b_full_minus_interaction_seed{seed}"
    )
SELECTED_RUNS[(101, "full")] = (
    "carr_s_deepseek_v7_controlled_pilot_r2_full_seed101"
)
for seed in (202, 303):
    SELECTED_RUNS[(seed, "full")] = (
        f"carr_s_deepseek_v7_controlled_pilot_r3c_full_seed{seed}"
    )


def _load_cell(
    seed: int,
    condition: str,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_dir = RUNS_ROOT / run_id
    paths = {
        "summary": run_dir / "summary.json",
        "metrics": run_dir / "mechanism_metrics.json",
        "provenance": run_dir / "provenance.json",
    }
    for path in paths.values():
        if not path.exists():
            raise FileNotFoundError(path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    provenance = json.loads(paths["provenance"].read_text(encoding="utf-8"))
    if summary["status"] != "VALID":
        raise ValueError(f"selected run is not VALID: {run_id}")
    if metrics["run_terminal_status"] != "VALID":
        raise ValueError(f"selected metrics are not VALID: {run_id}")
    if int(metrics["seed"]) != seed or metrics["condition"] != condition:
        raise ValueError(f"selected run identity mismatch: {run_id}")
    if metrics["metric_protocol_version"] != "v7":
        raise ValueError(f"selected run is not v7: {run_id}")
    if provenance["config"]["experiment"]["prompt_version"] != (
        "carr_s_controlled_resident_v7"
    ):
        raise ValueError(f"selected prompt mismatch: {run_id}")

    artifact = {
        "seed": seed,
        "condition": condition,
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        **{
            f"{name}_sha256": file_sha256(path)
            for name, path in paths.items()
        },
    }
    return metrics, summary, artifact


def build_summary() -> dict[str, Any]:
    expected = {
        (seed, condition)
        for seed in (101, 202, 303)
        for condition in CONDITIONS
    }
    if set(SELECTED_RUNS) != expected:
        raise ValueError("selected run map does not cover the frozen 3x5 matrix")

    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for (seed, condition), run_id in sorted(SELECTED_RUNS.items()):
        metrics, summary, artifact = _load_cell(seed, condition, run_id)
        rows.append(metrics)
        summaries.append(summary)
        artifacts.append(artifact)

    paired, paired_summary = paired_mechanism_analysis(
        rows,
        metric_map=PRIMARY_MECHANISM_METRICS_V7,
        require_valid=True,
    )
    gateway_totals = {
        key: sum(int(summary["gateway"][key]) for summary in summaries)
        for key in ("n_ok", "n_cache", "n_failed", "n_fallback")
    }
    gateway_totals["internal_estimated_cost_usd"] = sum(
        float(summary["gateway"]["spent"]) for summary in summaries
    )
    gateway_totals["aggregate_run_wall_clock_seconds"] = sum(
        float(summary["wall_clock_seconds"]) for summary in summaries
    )

    full_rows = {
        int(row["seed"]): row for row in rows if row["condition"] == "full"
    }
    feedback_drop_rows = {
        int(row["seed"]): row
        for row in rows
        if row["condition"] == "full_minus_feedback"
    }
    controlled_opportunity_checks = {
        "all_cells_preclosure_primary_plan_rate_one": all(
            float(row["preclosure_primary_plan_rate"]) == 1.0
            for row in rows
        ),
        "full_route_observation_updates_by_seed": {
            str(seed): int(row["route_observation_update_count"])
            for seed, row in sorted(full_rows.items())
        },
        "drop_feedback_route_observation_updates_by_seed": {
            str(seed): int(row["route_observation_update_count"])
            for seed, row in sorted(feedback_drop_rows.items())
        },
        "drop_feedback_updates_all_zero": all(
            int(row["route_observation_update_count"]) == 0
            for row in feedback_drop_rows.values()
        ),
    }
    positive_by_module = {
        item["module"]: (
            item["positive_direction_fraction"] == 1.0
            and item["n_seeds"] == 3
        )
        for item in paired_summary
    }
    return {
        "status": "PILOT",
        "activity_type": "V7_CONTROLLED_MECHANISM_BACKEND_PILOT_DERIVED_SUMMARY",
        "case_semantics": "Carr-informed controlled mechanism scenario",
        "decision_model": "packy-deepseek-v4-flash",
        "backend_mode": "thinking enabled, reasoning effort high",
        "metric_protocol_version": "v7",
        "n_households_per_run": 4,
        "n_decision_residents_per_run": 8,
        "seeds": [101, 202, 303],
        "conditions": list(CONDITIONS),
        "selected_runs": artifacts,
        "run_status_counts": {"VALID": len(summaries)},
        "gateway_totals": gateway_totals,
        "controlled_opportunity_checks": controlled_opportunity_checks,
        "paired_primary_differences": paired,
        "paired_summary": paired_summary,
        "pilot_assessment": {
            "all_declared_cells_valid": len(summaries) == 15,
            "all_modules_positive_in_all_three_seeds": all(
                positive_by_module.values()
            ),
            "positive_direction_by_module": positive_by_module,
            "formal_seed_count_frozen": False,
            "reason": (
                "The repaired design eliminates the feedback bypass and equalizes "
                "the initial planning opportunity. Three seeds support direction "
                "and initial variance diagnosis but remain too few for a formal "
                "confirmatory interval."
            ),
        },
        "technical_exclusions": [
            {
                "run_dir": (
                    "experiments/carr/runs/"
                    "carr_s_deepseek_v7_controlled_pilot_r1_full_seed101"
                ),
                "reason": "ABORTED before any model call because the wrong Python environment lacked litellm.",
            },
            {
                "run_dir": (
                    "experiments/carr/runs/"
                    "carr_s_deepseek_v7_controlled_pilot_r2_full_minus_memory_seed101"
                ),
                "reason": "Interrupted at a worker-boundary rescheduling attempt; never selected for scientific pairing.",
            },
        ],
        "limitations": [
            "PILOT only; no formal interval or significance claim is made.",
            "The four-household controlled cohort is not population-representative.",
            "The route obstruction is controlled, not a historical Carr closure.",
            "Drop-one estimates are conditional removal effects, not universal standalone module effects.",
            "Several drop-side primary metrics are structurally zero by design; observed variance is therefore driven mainly by full-condition performance.",
            "The internal cost field uses configured proxy estimates and is not a provider invoice.",
        ],
    }


def main() -> None:
    payload = build_summary()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
