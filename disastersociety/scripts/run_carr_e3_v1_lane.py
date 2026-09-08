"""Run one E3 model lane (bounded cross-model replication)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.run_carr_e2_v8_formal import (
    _artifact_row,
    file_sha256,
    run_carr_condition,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_e3_seed_batch(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    runs_dir: Path,
    seed: int,
) -> dict[str, Any]:
    """Seed batch for the bounded E3 protocol (3 conditions)."""
    protocol = cfg["experiment"]["formal_protocol"]
    declared_seeds = [int(value) for value in protocol["seeds"]]
    if seed not in declared_seeds:
        raise ValueError(f"seed {seed} is not in the frozen E3 protocol")
    conditions = tuple(str(value) for value in protocol["conditions"])
    if len(conditions) != 3:
        raise ValueError("E3 protocol requires exactly three conditions")
    if cfg["experiment"]["metric_protocol_version"] != "v8":
        raise ValueError("E3 requires metric protocol v8")
    if cfg["experiment"]["prompt_version"] != "carr_s_controlled_resident_v8":
        raise ValueError("E3 requires the frozen v8 prompt")
    if not protocol["execute_all_seeds_regardless_of_interim_direction"]:
        raise ValueError("E3 must forbid direction-based stopping")
    if protocol["carr_r_test_split_opened"]:
        raise ValueError("Carr-R test must remain sealed")

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
                    "partial E3 artifact must not be overwritten; "
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
        "status": "PILOT_PENDING_AUDIT",
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
        "claim_boundary": "Bounded same-proxy model-family replication; PILOT until audited.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    args = parser.parse_args()

    config_path = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol_id = str(cfg["experiment"]["formal_protocol"]["protocol_id"])
    if not protocol_id.startswith("carr_s_e3_v1_"):
        raise ValueError("E3 lane runner requires an E3 protocol")

    status_path = results_dir / f"{protocol_id}_lane_{args.lane}_status.json"
    state: dict[str, Any] = {
        "protocol_id": protocol_id,
        "lane": args.lane,
        "pid": os.getpid(),
        "config": str(config_path.relative_to(PROJECT_ROOT)),
        "declared_seeds": args.seeds,
        "completed_seeds": [],
        "current_seed": None,
        "state": "STARTED",
        "stop_reason": None,
    }
    _write_json(status_path, state)

    for seed in args.seeds:
        state.update(current_seed=seed, state="RUNNING")
        _write_json(status_path, state)
        try:
            batch = run_e3_seed_batch(
                cfg,
                config_path=config_path,
                runs_dir=runs_dir,
                seed=seed,
            )
        except BaseException as error:
            state.update(
                state="STOPPED_SUBPROCESS_ERROR",
                stop_reason=f"seed {seed}: {type(error).__name__}: {error}",
            )
            _write_json(status_path, state)
            return 1

        batch_path = results_dir / f"{protocol_id}_seed{seed}_summary.json"
        _write_json(batch_path, batch)
        completion = batch["completion"]
        valid = completion["terminal_status_counts"].get("VALID", 0)
        if (
            completion["completed_runs"] != 3
            or completion["planned_runs"] != 3
            or valid != 3
            or completion["aborted_early"]
        ):
            state.update(
                state="STOPPED_NONVALID_BATCH",
                stop_reason=f"seed {seed} did not finish three-for-three VALID",
            )
            _write_json(status_path, state)
            return 2

        state["completed_seeds"].append(seed)
        state.update(current_seed=None, state="SEED_COMPLETE")
        _write_json(status_path, state)

    state.update(current_seed=None, state="COMPLETE")
    _write_json(status_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
