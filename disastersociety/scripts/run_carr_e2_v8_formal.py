"""Execute one immutable seed batch from the frozen Carr-S E2 v8 matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import CONDITIONS, run_carr_condition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_formal.yaml"
)
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _artifact_row(
    *, seed: int, condition: str, run_dir: Path, summary: dict[str, Any]
) -> dict[str, Any]:
    paths = {
        "summary": run_dir / "summary.json",
        "mechanism_metrics": run_dir / "mechanism_metrics.json",
        "provenance": run_dir / "provenance.json",
    }
    gateway = summary["gateway"]
    return {
        "seed": seed,
        "condition": condition,
        "terminal_status": summary["status"],
        "n_ok": int(gateway["n_ok"]),
        "n_cache": int(gateway["n_cache"]),
        "n_failed": int(gateway["n_failed"]),
        "n_fallback": int(gateway["n_fallback"]),
        "fallback_rate": float(gateway["fallback_rate"]),
        "wall_clock_seconds": float(summary["wall_clock_seconds"]),
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        **{
            f"{name}_sha256": file_sha256(path)
            for name, path in paths.items()
        },
    }


def run_seed_batch(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    runs_dir: Path,
    seed: int,
) -> dict[str, Any]:
    protocol = cfg["experiment"]["formal_protocol"]
    declared_seeds = [int(value) for value in protocol["seeds"]]
    if seed not in declared_seeds:
        raise ValueError(f"seed {seed} is not in the frozen v8 protocol")
    conditions = tuple(str(value) for value in protocol["conditions"])
    if conditions != CONDITIONS:
        raise ValueError("frozen v8 conditions do not match the runner contract")
    if cfg["experiment"]["metric_protocol_version"] != "v8":
        raise ValueError("formal v8 execution requires metric protocol v8")
    if cfg["experiment"]["prompt_version"] != "carr_s_controlled_resident_v8":
        raise ValueError("formal v8 execution requires the frozen v8 prompt")
    if not protocol["execute_all_seeds_regardless_of_interim_direction"]:
        raise ValueError("formal v8 protocol must forbid direction-based stopping")
    if protocol["carr_r_test_split_opened"]:
        raise ValueError("Carr-R test must remain sealed during Carr-S E2")

    rows: list[dict[str, Any]] = []
    reused = 0
    aborted_early = False
    for condition in conditions:
        run_dir = runs_dir / f"{cfg['run']['run_id']}_{condition}_seed{seed}"
        required = (
            run_dir / "summary.json",
            run_dir / "mechanism_metrics.json",
            run_dir / "provenance.json",
        )
        if run_dir.exists():
            missing = [str(path) for path in required if not path.exists()]
            if missing:
                raise RuntimeError(
                    "partial formal artifact must not be overwritten; "
                    f"new protocol amendment required: {missing}"
                )
            summary = json.loads(required[0].read_text(encoding="utf-8"))
            reused += 1
        else:
            result = run_carr_condition(
                cfg,
                condition=condition,
                seed=seed,
                runs_dir=runs_dir,
            )
            summary = result.summary
            run_dir = result.run_dir
        rows.append(
            _artifact_row(
                seed=seed,
                condition=condition,
                run_dir=run_dir,
                summary=summary,
            )
        )
        if summary["status"] != "VALID":
            aborted_early = True
            break

    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["terminal_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "status": "PILOT_PENDING_COMPLETE_MATRIX_AUDIT",
        "activity_type": cfg["experiment"]["activity_type"],
        "decision_model": cfg["llm"]["decision_model"],
        "prompt_version": cfg["experiment"]["prompt_version"],
        "metric_protocol_version": cfg["experiment"]["metric_protocol_version"],
        "source": {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "config_sha256": file_sha256(config_path),
        },
        "protocol": {
            "declared_seeds": declared_seeds,
            "executed_seed_batch": [seed],
            "conditions": list(conditions),
            "carr_r_test_split_opened": False,
        },
        "completion": {
            "completed_runs": len(rows),
            "planned_runs": len(conditions),
            "reused_terminal_artifacts": reused,
            "aborted_early": aborted_early,
            "terminal_status_counts": status_counts,
        },
        "runs": rows,
        "claim_boundary": (
            "One immutable seed batch from the publication-facing Carr-S E2 "
            "matrix. It remains PILOT until all predeclared seeds are complete "
            "and the full matrix, exclusions, provenance, and intervals are audited."
        ),
    }


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = run_seed_batch(
        cfg,
        config_path=config_path,
        runs_dir=runs_dir,
        seed=int(args.seed),
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"carr_s_e2_v8_formal_seed{args.seed}_summary.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
