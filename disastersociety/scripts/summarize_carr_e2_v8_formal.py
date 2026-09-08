"""Audit completed Carr-S E2 v8 seed batches and derive paired estimates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import t as student_t

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import (
    PRIMARY_DOWNSTREAM_METRICS_V8,
    PRIMARY_MECHANISM_METRICS_V8,
    paired_directional_analysis,
    paired_mechanism_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_formal.yaml"
)
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = DEFAULT_RESULTS_DIR / "carr_s_e2_v8_formal_cumulative_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _intervals(
    rows: list[dict[str, Any]], *, mean_key: str, sd_key: str
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        n = int(row["n_seeds"])
        mean = float(row[mean_key])
        sd = float(row[sd_key])
        mcse = float(row["mcse"])
        if n >= 2:
            half_width = float(student_t.ppf(0.975, df=n - 1)) * mcse
            row["paired_t_95_ci"] = [mean - half_width, mean + half_width]
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


def build_summary(
    *, config_path: Path, results_dir: Path, runs_dir: Path
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    seeds = [int(value) for value in protocol["seeds"]]
    conditions = [str(value) for value in protocol["conditions"]]
    config_hash = file_sha256(config_path)
    seen: set[int] = set()
    metric_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for batch_path in sorted(
        results_dir.glob("carr_s_e2_v8_formal_seed*_summary.json")
    ):
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        if batch["source"]["config_sha256"] != config_hash:
            raise ValueError(f"config hash mismatch: {batch_path}")
        batch_seed = int(batch["protocol"]["executed_seed_batch"][0])
        if batch_seed not in seeds or batch_seed in seen:
            raise ValueError(f"invalid or duplicate seed batch: {batch_path}")
        seen.add(batch_seed)
        sources.append(
            {
                "seed": batch_seed,
                "path": str(batch_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(batch_path),
            }
        )
        for row in batch["runs"]:
            seed = int(row["seed"])
            condition = str(row["condition"])
            if seed != batch_seed or condition not in conditions:
                raise ValueError(f"batch row violates protocol: {batch_path}")
            run_dir = runs_dir / f"{cfg['run']['run_id']}_{condition}_seed{seed}"
            paths = {
                "summary": run_dir / "summary.json",
                "mechanism_metrics": run_dir / "mechanism_metrics.json",
                "provenance": run_dir / "provenance.json",
            }
            for name, path in paths.items():
                if not path.exists() or file_sha256(path) != row[f"{name}_sha256"]:
                    raise ValueError(f"{name} artifact mismatch: {path}")
            metrics = json.loads(
                paths["mechanism_metrics"].read_text(encoding="utf-8")
            )
            metric_rows.append(metrics)
            run_rows.append(row)
            status = str(row["terminal_status"])
            status_counts[status] = status_counts.get(status, 0) + 1

    primary, primary_summary = paired_mechanism_analysis(
        metric_rows,
        require_valid=True,
        metric_map=PRIMARY_MECHANISM_METRICS_V8,
    )
    downstream, downstream_summary = paired_directional_analysis(
        metric_rows,
        require_valid=True,
        metric_specs=PRIMARY_DOWNSTREAM_METRICS_V8,
    )
    completed_keys = {
        (int(row["seed"]), str(row["condition"])) for row in run_rows
    }
    planned_runs = len(seeds) * len(conditions)
    return {
        "status": (
            "READY_FOR_LEDGER_AUDIT"
            if len(completed_keys) == planned_runs
            else "PILOT_IN_PROGRESS"
        ),
        "activity_type": "PUBLICATION_FACING_E2_MATRIX_CUMULATIVE_AUDIT",
        "decision_model": cfg["llm"]["decision_model"],
        "prompt_version": cfg["experiment"]["prompt_version"],
        "metric_protocol_version": cfg["experiment"]["metric_protocol_version"],
        "source": {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "config_sha256": config_hash,
            "seed_batches": sources,
        },
        "completion": {
            "declared_seeds": seeds,
            "completed_seed_batches": sorted(seen),
            "remaining_seed_batches": [seed for seed in seeds if seed not in seen],
            "planned_runs": planned_runs,
            "completed_terminal_runs": len(completed_keys),
            "terminal_status_counts": status_counts,
            "matrix_complete": len(completed_keys) == planned_runs,
            "carr_r_test_split_opened": False,
        },
        "paired_primary_differences": primary,
        "paired_primary_summary": _intervals(
            primary_summary,
            mean_key="mean_paired_difference",
            sd_key="sd_paired_difference",
        ),
        "paired_downstream_differences": downstream,
        "paired_downstream_summary": _intervals(
            downstream_summary,
            mean_key="mean_directional_difference",
            sd_key="sd_directional_difference",
        ),
        "runs": sorted(
            run_rows,
            key=lambda row: (int(row["seed"]), conditions.index(row["condition"])),
        ),
        "claim_boundary": (
            "The matrix estimates conditional full-minus-drop-one effects in a "
            "Carr-informed controlled scenario. It does not by itself establish "
            "Carr empirical validity, historical reconstruction, or universal "
            "model independence."
        ),
    }


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output_path = _resolve(args.output).resolve()
    summary = build_summary(
        config_path=config_path,
        results_dir=results_dir,
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
