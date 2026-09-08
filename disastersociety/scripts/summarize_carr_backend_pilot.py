"""Create a tracked, claim-bounded summary from preserved Carr-S run artifacts."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import paired_mechanism_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = (
    PROJECT_ROOT
    / "experiments/carr/runs/carr_s_deepseek_backend_pilot_v3/pilot_matrix.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/carr_s_deepseek_backend_pilot_v3_summary.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--additional-matrix",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def build_summary(matrix_paths: list[Path]) -> dict[str, Any]:
    matrices = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in matrix_paths
    ]
    reference = matrices[0]
    for matrix in matrices[1:]:
        for key in ("case_semantics", "decision_model", "n_households"):
            if matrix[key] != reference[key]:
                raise ValueError(f"matrix invariant differs: {key}")
        if matrix["conditions"] != reference["conditions"]:
            raise ValueError("matrix condition order differs")
    rows = [row for matrix in matrices for row in matrix["runs"]]
    paired, paired_summary = paired_mechanism_analysis(
        rows,
        require_valid=True,
    )
    paired_exclusions: list[dict[str, Any]] = []
    by_key = {
        (str(row["condition"]), int(row["seed"])): row
        for row in rows
    }
    for seed in sorted({int(row["seed"]) for row in rows}):
        full_row = by_key[("full", seed)]
        for module in ("memory", "feedback", "planning", "interaction"):
            drop_row = by_key[(f"full_minus_{module}", seed)]
            full_status = str(
                full_row.get("run_terminal_status", "VALID")
            )
            drop_status = str(
                drop_row.get("run_terminal_status", "VALID")
            )
            if full_status != "VALID" or drop_status != "VALID":
                paired_exclusions.append(
                    {
                        "seed": seed,
                        "module": module,
                        "full_status": full_status,
                        "drop_one_status": drop_status,
                        "reason": "paired estimate requires two VALID runs",
                    }
                )
    expected = {
        (str(row["condition"]), int(row["seed"])) for row in rows
    }
    if len(expected) != len(rows):
        raise ValueError("matrix contains duplicate seed-condition rows")

    summaries: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    start_times: list[float] = []
    end_times: list[float] = []
    for matrix_path, matrix in zip(matrix_paths, matrices):
        base_run_id = matrix_path.parent.name
        runs_root = matrix_path.parent.parent
        for row in matrix["runs"]:
            condition = str(row["condition"])
            seed = int(row["seed"])
            run_dir = runs_root / f"{base_run_id}_{condition}_seed{seed}"
            summary_path = run_dir / "summary.json"
            metrics_path = run_dir / "mechanism_metrics.json"
            provenance_path = run_dir / "provenance.json"
            for required in (summary_path, metrics_path, provenance_path):
                if not required.exists():
                    raise FileNotFoundError(required)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summaries.append(summary)
            start_times.append(provenance_path.stat().st_mtime)
            end_times.append(summary_path.stat().st_mtime)
            artifacts.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
                    "summary_sha256": file_sha256(summary_path),
                    "mechanism_metrics_sha256": file_sha256(metrics_path),
                    "provenance_sha256": file_sha256(provenance_path),
                }
            )

    statuses: dict[str, int] = {}
    for summary in summaries:
        status = str(summary["status"])
        statuses[status] = statuses.get(status, 0) + 1
    counter_keys = (
        "n_ok",
        "n_cache",
        "n_failed",
        "n_fallback",
        "live_prompt_tokens",
        "live_completion_tokens",
        "logical_prompt_tokens",
        "logical_completion_tokens",
    )
    totals = {
        key: sum(int(summary["gateway"][key]) for summary in summaries)
        for key in counter_keys
    }
    totals["estimated_cost_usd"] = round(
        sum(float(summary["gateway"]["spent"]) for summary in summaries),
        6,
    )
    directionally_consistent = all(
        item["positive_direction_fraction"] == 1.0
        for item in paired_summary
    )
    variance_informative = all(
        item["variance_informative"] for item in paired_summary
    )
    all_runs_valid = statuses == {"VALID": len(rows)}
    if not all_runs_valid:
        next_action = (
            "Preserve every INVALID run and exclude its scientific pair; "
            "repair backend reliability under a new prompt/run identifier "
            "before Gate D or any formal mechanism matrix."
        )
    elif not directionally_consistent:
        next_action = (
            "Retain the null and mixed contrasts; use the observed paired "
            "variance to design Gate D without selecting seeds by direction."
        )
    else:
        next_action = (
            "Use the complete pilot variance to freeze the Gate D precision "
            "target and formal seed count."
        )
    wall_clock_values = [
        float(summary["wall_clock_seconds"])
        for summary in summaries
        if summary.get("wall_clock_seconds") is not None
    ]
    return {
        "status": "PILOT",
        "activity_type": "BACKEND_PILOT_DERIVED_SUMMARY",
        "case_semantics": reference["case_semantics"],
        "decision_model": reference["decision_model"],
        "cohort": {
            "n_households_per_run": reference["n_households"],
            "n_decision_residents_per_run": 4,
            "seeds": sorted({int(row["seed"]) for row in rows}),
            "conditions": reference["conditions"],
            "n_runs": len(rows),
        },
        "source": {
            "matrices": [
                {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "sha256": file_sha256(path),
                }
                for path in matrix_paths
            ],
            "run_artifacts": artifacts,
        },
        "analysis_correction": {
            "reason": (
                "The preserved raw matrix mapped interaction to "
                "coordinated_departure_rate, while the method decision and "
                "analysis plan had predeclared compatible commitment formation."
            ),
            "raw_matrix_preserved": True,
            "corrected_interaction_primary_metric": "compatible_commitment_rate",
            "post_hoc_metric_selection": False,
        },
        "completion": {
            "terminal_status_counts": statuses,
            "all_runs_valid": all_runs_valid,
            "test_split_opened": False,
        },
        "usage": totals,
        "runtime": {
            "n_runs_with_wall_clock": len(wall_clock_values),
            "sum_run_wall_clock_seconds": (
                round(sum(wall_clock_values), 3)
                if wall_clock_values
                else None
            ),
            "median_run_wall_clock_seconds": (
                round(statistics.median(wall_clock_values), 3)
                if wall_clock_values
                else None
            ),
            "max_run_wall_clock_seconds": (
                round(max(wall_clock_values), 3)
                if wall_clock_values
                else None
            ),
            "observed_artifact_timestamp_span_seconds": round(
                max(end_times) - min(start_times), 3
            ),
            "timestamp_span_is_formal_timing_metric": False,
            "all_future_runner_runs_record_wall_clock_seconds": True,
        },
        "paired_primary_differences": paired,
        "paired_summary": paired_summary,
        "paired_exclusions": paired_exclusions,
        "pilot_gate_assessment": {
            "mechanism_paths_positive_in_every_seed": directionally_consistent,
            "seed_variance_informative_for_every_module": variance_informative,
            "formal_seed_count_frozen": False,
            "formal_results_eligible": False,
            "next_action": next_action,
        },
        "claim_boundary": (
            f"This is a {len(set(int(row['seed']) for row in rows))}-seed "
            "backend behavior and engineering pilot. It "
            "supports endpoint/schema/cost/fallback feasibility and diagnoses "
            "mechanism variance; it is not formal E2 or Carr empirical evidence."
        ),
    }


def main() -> None:
    args = parse_args()
    matrix_paths = [
        _resolve(path).resolve()
        for path in [args.matrix, *args.additional_matrix]
    ]
    output_path = _resolve(args.output).resolve()
    summary = build_summary(matrix_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
