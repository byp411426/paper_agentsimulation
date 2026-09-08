"""Read preserved Carr-S E2 v5 batches; new v5 execution is paused.

Sequential seed-major execution: for each seed, run the full condition first
and then the four drop-one conditions, so a backend outage aborts before
burning further paid runs. Each condition uses its own budget gate from the
config. INVALID runs are preserved and never rerun under the same run ID.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import run_carr_condition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "experiments/carr/configs/carr_s_formal_e2_v5.yaml"
)
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
V5_PAUSE_MARKER = (
    PROJECT_ROOT
    / "experiments/carr/protocol/carr_s_formal_e2_v5_pause.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Run exactly one seed from the frozen formal protocol.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def run_formal_matrix(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    runs_dir: Path,
    selected_seeds: list[int] | None = None,
) -> dict[str, Any]:
    protocol = cfg["experiment"]["formal_protocol"]
    if not protocol.get("execute_sequentially"):
        raise ValueError("the formal v5 matrix must execute sequentially")
    declared_seeds = [int(seed) for seed in protocol["seeds"]]
    seeds = (
        [int(seed) for seed in selected_seeds]
        if selected_seeds is not None
        else declared_seeds
    )
    undeclared = sorted(set(seeds) - set(declared_seeds))
    if undeclared:
        raise ValueError(f"seeds are not in the frozen protocol: {undeclared}")
    if (
        str(cfg.get("run", {}).get("run_id")) == "carr_s_formal_e2_v5"
        and V5_PAUSE_MARKER.exists()
    ):
        pause = json.loads(V5_PAUSE_MARKER.read_text(encoding="utf-8"))
        raise RuntimeError(
            "Carr-S E2 v5 is paused; preserved artifacts remain readable, "
            "but new v5 seed execution is disabled. Reason codes: "
            + ", ".join(pause["pause_reason_codes"])
        )
    conditions = [str(condition) for condition in protocol["conditions"]]

    rows: list[dict[str, Any]] = []
    terminal_status_counts: dict[str, int] = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0.0
    total_wall_clock = 0.0
    n_ok = n_failed = n_fallback = 0
    reused_terminal_artifacts = 0

    for seed in seeds:
        for condition in conditions:
            run_dir = (
                runs_dir
                / f"{cfg['run']['run_id']}_{condition}_seed{seed}"
            )
            summary_path = run_dir / "summary.json"
            metrics_path = run_dir / "mechanism_metrics.json"
            provenance_path = run_dir / "provenance.json"
            if run_dir.exists():
                missing = [
                    path
                    for path in (summary_path, metrics_path, provenance_path)
                    if not path.exists()
                ]
                if missing:
                    raise RuntimeError(
                        "partial formal artifact must not be overwritten; "
                        f"new run namespace required: {run_dir}"
                    )
                summary = json.loads(
                    summary_path.read_text(encoding="utf-8")
                )
                reused_terminal_artifacts += 1
            else:
                result = run_carr_condition(
                    cfg,
                    condition=condition,
                    seed=seed,
                    runs_dir=runs_dir,
                )
                summary = result.summary
                run_dir = result.run_dir
                summary_path = run_dir / "summary.json"
                metrics_path = run_dir / "mechanism_metrics.json"
                provenance_path = run_dir / "provenance.json"

            gateway = summary["gateway"]
            status = str(summary["status"])
            terminal_status_counts[status] = (
                terminal_status_counts.get(status, 0) + 1
            )
            total_prompt_tokens += int(gateway["live_prompt_tokens"])
            total_completion_tokens += int(
                gateway["live_completion_tokens"]
            )
            total_cost += float(gateway["spent"])
            total_wall_clock += float(summary["wall_clock_seconds"])
            n_ok += int(gateway["n_ok"])
            n_failed += int(gateway["n_failed"])
            n_fallback += int(gateway["n_fallback"])
            rows.append(
                {
                    "seed": seed,
                    "condition": condition,
                    "terminal_status": status,
                    "n_ok": int(gateway["n_ok"]),
                    "n_failed": int(gateway["n_failed"]),
                    "n_fallback": int(gateway["n_fallback"]),
                    "fallback_rate": float(gateway["fallback_rate"]),
                    "estimated_cost_usd": float(gateway["spent"]),
                    "wall_clock_seconds": float(
                        summary["wall_clock_seconds"]
                    ),
                    "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
                    "summary_sha256": file_sha256(summary_path),
                    "mechanism_metrics_sha256": file_sha256(metrics_path),
                    "provenance_sha256": file_sha256(provenance_path),
                }
            )
            if status == "ABORTED":
                # Provider outage: stop the paid matrix; preserve everything.
                return _output(
                    cfg,
                    config_path=config_path,
                    declared_seeds=declared_seeds,
                    seeds=seeds,
                    conditions=conditions,
                    rows=rows,
                    terminal_status_counts=terminal_status_counts,
                    total_prompt_tokens=total_prompt_tokens,
                    total_completion_tokens=total_completion_tokens,
                    total_cost=total_cost,
                    total_wall_clock=total_wall_clock,
                    n_ok=n_ok,
                    n_failed=n_failed,
                    n_fallback=n_fallback,
                    reused_terminal_artifacts=reused_terminal_artifacts,
                    aborted_early=True,
                )

    return _output(
        cfg,
        config_path=config_path,
        declared_seeds=declared_seeds,
        seeds=seeds,
        conditions=conditions,
        rows=rows,
        terminal_status_counts=terminal_status_counts,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        total_cost=total_cost,
        total_wall_clock=total_wall_clock,
        n_ok=n_ok,
        n_failed=n_failed,
        n_fallback=n_fallback,
        reused_terminal_artifacts=reused_terminal_artifacts,
        aborted_early=False,
    )


def _output(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    declared_seeds: list[int],
    seeds: list[int],
    conditions: list[str],
    rows: list[dict[str, Any]],
    terminal_status_counts: dict[str, int],
    total_prompt_tokens: int,
    total_completion_tokens: int,
    total_cost: float,
    total_wall_clock: float,
    n_ok: int,
    n_failed: int,
    n_fallback: int,
    reused_terminal_artifacts: int,
    aborted_early: bool,
) -> dict[str, Any]:
    planned = len(seeds) * len(conditions)
    completed = len(rows)
    return {
        "status": cfg["experiment"]["evidence_status"],
        "activity_type": cfg["experiment"]["activity_type"],
        "prompt_version": cfg["experiment"]["prompt_version"],
        "decision_model": cfg["llm"]["decision_model"],
        "source": {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "config_sha256": file_sha256(config_path),
        },
        "protocol": {
            "execute_sequentially": True,
            "test_split_opened": False,
            "declared_seeds": declared_seeds,
            "executed_seed_batch": seeds,
            "conditions": conditions,
            "planned_runs": planned,
        },
        "completion": {
            "completed_runs": completed,
            "aborted_early": aborted_early,
            "reused_terminal_artifacts": reused_terminal_artifacts,
            "terminal_status_counts": terminal_status_counts,
        },
        "usage": {
            "n_ok": n_ok,
            "n_failed": n_failed,
            "n_fallback": n_fallback,
            "live_prompt_tokens": total_prompt_tokens,
            "live_completion_tokens": total_completion_tokens,
            "estimated_cost_usd": round(total_cost, 6),
        },
        "runtime": {
            "sum_run_wall_clock_seconds": round(total_wall_clock, 3),
        },
        "runs": rows,
        "claim_boundary": (
            "Publication-facing E2 raw run record with PILOT evidence status "
            "pending complete-matrix audit. Mechanism effect estimates are computed "
            "only from VALID full/drop-one pairs with the predeclared "
            "exclusion rule; INVALID runs are preserved and excluded, and an "
            "early ABORTED stop leaves the remaining matrix unexecuted."
        ),
    }


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output_path = (
        _resolve(args.output).resolve()
        if args.output is not None
        else (
            PROJECT_ROOT
            / "experiments/carr/results/"
            f"carr_s_formal_e2_v5_seed{args.seed}_summary.json"
        )
    )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    summary = run_formal_matrix(
        cfg,
        config_path=config_path,
        runs_dir=runs_dir,
        selected_seeds=[int(args.seed)],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
