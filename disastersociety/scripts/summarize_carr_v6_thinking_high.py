"""Summarize the preserved Carr-S v6 thinking-high pilot attempts.

The pilot was completed under new run identifiers after two fail-fast backend
attempts.  This script selects exactly one VALID artifact for each predeclared
seed-condition cell and never rewrites a raw run directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import (
    PRIMARY_MECHANISM_METRICS_V6,
    paired_mechanism_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "experiments/carr/runs"
OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/carr_s_deepseek_v6_thinking_high_pilot_summary.json"
)

SELECTED_RUNS = {
    (101, "full"): "carr_s_deepseek_v6_thinking_high_pilot_r1_full_seed101",
    (101, "full_minus_memory"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r1_full_minus_memory_seed101"
    ),
    (101, "full_minus_feedback"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_feedback_seed101"
    ),
    (101, "full_minus_planning"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_planning_seed101"
    ),
    (101, "full_minus_interaction"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_interaction_seed101"
    ),
    (202, "full"): "carr_s_deepseek_v6_thinking_high_pilot_r2_full_seed202",
    (202, "full_minus_memory"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_memory_seed202"
    ),
    (202, "full_minus_feedback"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_feedback_seed202"
    ),
    (202, "full_minus_planning"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_planning_seed202"
    ),
    (202, "full_minus_interaction"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_interaction_seed202"
    ),
}


def _load_selected_run(
    seed: int,
    condition: str,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_dir = RUNS_ROOT / run_id
    summary_path = run_dir / "summary.json"
    metrics_path = run_dir / "mechanism_metrics.json"
    provenance_path = run_dir / "provenance.json"
    for path in (summary_path, metrics_path, provenance_path):
        if not path.exists():
            raise FileNotFoundError(path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if summary["status"] != "VALID":
        raise ValueError(f"selected run is not VALID: {run_id}")
    if int(metrics["seed"]) != seed or metrics["condition"] != condition:
        raise ValueError(f"selected run identity mismatch: {run_id}")
    row = dict(metrics)
    row["run_terminal_status"] = summary["status"]
    artifact = {
        "seed": seed,
        "condition": condition,
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        "summary_sha256": file_sha256(summary_path),
        "mechanism_metrics_sha256": file_sha256(metrics_path),
        "provenance_sha256": file_sha256(provenance_path),
    }
    return row, summary, artifact


def build_summary() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for (seed, condition), run_id in SELECTED_RUNS.items():
        row, summary, artifact = _load_selected_run(seed, condition, run_id)
        rows.append(row)
        summaries.append(summary)
        artifacts.append(artifact)

    paired, paired_summary = paired_mechanism_analysis(
        rows,
        metric_map=PRIMARY_MECHANISM_METRICS_V6,
        require_valid=True,
    )
    gateway_keys = ("n_ok", "n_cache", "n_failed", "n_fallback")
    gateway_totals = {
        key: sum(int(summary["gateway"][key]) for summary in summaries)
        for key in gateway_keys
    }
    module_means = {
        item["module"]: item["mean_paired_difference"]
        for item in paired_summary
    }
    module_sds = {
        item["module"]: item["sd_paired_difference"]
        for item in paired_summary
    }
    directionally_consistent = all(
        item["positive_direction_fraction"] == 1.0
        for item in paired_summary
    )
    variance_informative_modules = [
        item["module"]
        for item in paired_summary
        if item["variance_informative"]
    ]
    return {
        "status": "PILOT",
        "activity_type": "V6_THINKING_HIGH_BACKEND_PILOT_DERIVED_SUMMARY",
        "case_semantics": "Carr-informed controlled mechanism scenario",
        "decision_model": "packy-deepseek-v4-flash",
        "backend_mode": "thinking enabled, reasoning effort high",
        "metric_protocol_version": "v6",
        "n_households_per_run": 2,
        "seeds": [101, 202],
        "conditions": [
            "full",
            "full_minus_memory",
            "full_minus_feedback",
            "full_minus_planning",
            "full_minus_interaction",
        ],
        "selected_runs": artifacts,
        "run_status_counts": {"VALID": len(summaries)},
        "gateway_totals": gateway_totals,
        "paired_primary_differences": paired,
        "paired_summary": paired_summary,
        "module_mean_paired_differences": module_means,
        "module_sd_paired_differences": module_sds,
        "pilot_gate_assessment": {
            "all_predeclared_cells_valid": True,
            "directionally_consistent": directionally_consistent,
            "variance_informative_modules": variance_informative_modules,
            "formal_seed_count_frozen": False,
            "reason": (
                "Two seeds and two households per run yield coarse fractions; "
                "three of four module contrasts have zero observed seed variance."
            ),
            "next_action": (
                "Increase the controlled cohort before precision-based formal "
                "seed sizing; reuse the frozen v6 matrix for bounded cross-model "
                "robustness without treating this pilot as formal evidence."
            ),
        },
        "limitations": [
            "PILOT only; no formal interval or significance claim is made.",
            "The two-household controlled cohort is not population-representative.",
            "The route obstruction is controlled, not a historical Carr closure.",
            "Drop-one estimates are conditional removal effects, not universal module effects.",
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
