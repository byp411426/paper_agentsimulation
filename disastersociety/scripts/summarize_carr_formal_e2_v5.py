"""Audit and summarize completed Carr-S E2 v5 seed batches.

The formal runner writes one immutable seed-batch summary at a time.  This
script verifies those summaries against their raw run artifacts and derives
the predeclared full-minus-drop-one contrasts without opening Carr-R test data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import t as student_t

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import paired_mechanism_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "experiments/carr/configs/carr_s_formal_e2_v5.yaml"
)
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = (
    DEFAULT_RESULTS_DIR / "carr_s_formal_e2_v5_cumulative_summary.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _paired_intervals(
    paired_summary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in paired_summary:
        row = dict(item)
        n = int(row["n_seeds"])
        mean = float(row["mean_paired_difference"])
        sd = float(row["sd_paired_difference"])
        mcse = float(row["mcse"])
        if n >= 2:
            critical = float(student_t.ppf(0.975, df=n - 1))
            half_width = critical * mcse
            row["paired_t_95_ci"] = [
                mean - half_width,
                mean + half_width,
            ]
            row["paired_t_95_half_width"] = half_width
            row["standardized_paired_effect_dz"] = (
                mean / sd if sd > 0 else None
            )
        else:
            row["paired_t_95_ci"] = None
            row["paired_t_95_half_width"] = None
            row["standardized_paired_effect_dz"] = None
        output.append(row)
    return output


def build_cumulative_summary(
    *,
    config_path: Path,
    batch_paths: list[Path],
    runs_dir: Path,
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    declared_seeds = [int(seed) for seed in protocol["seeds"]]
    conditions = [str(value) for value in protocol["conditions"]]
    config_hash = file_sha256(config_path)

    seen_batches: set[int] = set()
    run_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    usage_keys = (
        "n_ok",
        "n_cache",
        "n_failed",
        "n_fallback",
        "live_prompt_tokens",
        "live_completion_tokens",
    )
    usage = {key: 0 for key in usage_keys}
    total_cost = 0.0
    total_wall_clock = 0.0

    for batch_path in sorted(batch_paths):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if batch["source"]["config_sha256"] != config_hash:
            raise ValueError(f"config hash mismatch: {batch_path}")
        batch_seeds = [
            int(seed) for seed in batch["protocol"]["executed_seed_batch"]
        ]
        if len(batch_seeds) != 1:
            raise ValueError(f"expected one seed per batch: {batch_path}")
        seed = batch_seeds[0]
        if seed not in declared_seeds:
            raise ValueError(f"undeclared seed {seed}: {batch_path}")
        if seed in seen_batches:
            raise ValueError(f"duplicate seed batch {seed}")
        seen_batches.add(seed)
        sources.append(
            {
                "seed": seed,
                "path": str(batch_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(batch_path),
            }
        )

        for row in batch["runs"]:
            condition = str(row["condition"])
            row_seed = int(row["seed"])
            if row_seed != seed or condition not in conditions:
                raise ValueError(f"batch row violates protocol: {batch_path}")
            run_dir = runs_dir / f"{cfg['run']['run_id']}_{condition}_seed{seed}"
            artifact_paths = {
                "summary": run_dir / "summary.json",
                "mechanism_metrics": run_dir / "mechanism_metrics.json",
                "provenance": run_dir / "provenance.json",
            }
            for name, path in artifact_paths.items():
                expected = row[f"{name}_sha256"]
                if not path.exists() or file_sha256(path) != expected:
                    raise ValueError(f"{name} artifact mismatch: {path}")
            metrics = json.loads(
                artifact_paths["mechanism_metrics"].read_text(encoding="utf-8")
            )
            raw_summary = json.loads(
                artifact_paths["summary"].read_text(encoding="utf-8")
            )
            if (
                int(metrics["seed"]) != seed
                or str(metrics["condition"]) != condition
            ):
                raise ValueError(f"mechanism metric identity mismatch: {run_dir}")
            metric_rows.append(metrics)
            run_rows.append(dict(row))
            status = str(row["terminal_status"])
            status_counts[status] = status_counts.get(status, 0) + 1
            for key in usage_keys:
                usage[key] += int(raw_summary["gateway"][key])
            total_cost += float(raw_summary["gateway"]["spent"])
            total_wall_clock += float(raw_summary["wall_clock_seconds"])

    run_keys = {
        (int(row["seed"]), str(row["condition"])) for row in run_rows
    }
    if len(run_keys) != len(run_rows):
        raise ValueError("duplicate seed-condition run")

    paired, paired_summary = paired_mechanism_analysis(
        metric_rows,
        require_valid=True,
    )
    paired_summary = _paired_intervals(paired_summary)
    exclusions: list[dict[str, Any]] = []
    by_key = {
        (int(row["seed"]), str(row["condition"])): row
        for row in metric_rows
    }
    for seed in sorted(seen_batches):
        full = by_key.get((seed, "full"))
        for module in ("memory", "feedback", "planning", "interaction"):
            drop = by_key.get((seed, f"full_minus_{module}"))
            if full is None or drop is None:
                exclusions.append(
                    {
                        "seed": seed,
                        "module": module,
                        "reason": "paired run missing from completed seed batch",
                    }
                )
                continue
            if (
                full["run_terminal_status"] != "VALID"
                or drop["run_terminal_status"] != "VALID"
            ):
                exclusions.append(
                    {
                        "seed": seed,
                        "module": module,
                        "full_status": full["run_terminal_status"],
                        "drop_one_status": drop["run_terminal_status"],
                        "reason": "paired estimate requires two VALID runs",
                    }
                )

    planned_runs = len(declared_seeds) * len(conditions)
    matrix_complete = len(run_keys) == planned_runs
    remaining_seeds = [seed for seed in declared_seeds if seed not in seen_batches]
    usage["estimated_cost_usd"] = round(total_cost, 6)
    n_decisions = usage["n_ok"] + usage["n_cache"] + usage["n_fallback"]
    usage["fallback_rate"] = (
        usage["n_fallback"] / n_decisions if n_decisions else 0.0
    )
    return {
        "status": "PILOT",
        "activity_type": "FORMAL_MECHANISM_MATRIX_CUMULATIVE_AUDIT",
        "decision_model": cfg["llm"]["decision_model"],
        "prompt_version": cfg["experiment"]["prompt_version"],
        "source": {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "config_sha256": config_hash,
            "seed_batches": sources,
        },
        "completion": {
            "declared_seeds": declared_seeds,
            "completed_seed_batches": sorted(seen_batches),
            "remaining_seed_batches": remaining_seeds,
            "conditions": conditions,
            "planned_runs": planned_runs,
            "completed_terminal_runs": len(run_rows),
            "terminal_status_counts": status_counts,
            "matrix_complete": matrix_complete,
            "test_split_opened": False,
        },
        "usage": usage,
        "runtime": {
            "sum_run_wall_clock_seconds": round(total_wall_clock, 3),
        },
        "runs": sorted(
            run_rows,
            key=lambda row: (
                int(row["seed"]),
                conditions.index(row["condition"]),
            ),
        ),
        "paired_primary_differences": paired,
        "paired_summary": paired_summary,
        "paired_exclusions": exclusions,
        "audit": {
            "all_batch_config_hashes_match": True,
            "all_listed_artifact_hashes_match": True,
            "eligible_for_complete_matrix_ledger_audit": matrix_complete,
        },
        "claim_boundary": (
            "Cumulative publication-facing E2 execution record. It remains "
            "PILOT until all predeclared seed batches are terminal and the "
            "complete matrix, exclusions, provenance, and paired analysis are "
            "audited in the evidence ledger. A one-seed contrast has no "
            "paired-t interval and is not a paper-level mechanism conclusion."
        ),
    }


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output_path = _resolve(args.output).resolve()
    batch_paths = sorted(
        results_dir.glob("carr_s_formal_e2_v5_seed*_summary.json")
    )
    if not batch_paths:
        raise FileNotFoundError("no completed formal E2 v5 seed batches")
    summary = build_cumulative_summary(
        config_path=config_path,
        batch_paths=batch_paths,
        runs_dir=runs_dir,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
