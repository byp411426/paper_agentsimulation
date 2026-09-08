"""Run one detached r4 lane without cross-attempt output-name collisions.

Each seed batch is written under the r4 protocol id.  The supervisor never
retries and stops before starting another paid batch after any exception or
non-five-for-five-VALID result.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.run_carr_e2_v8_formal import run_seed_batch


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol_id = str(cfg["experiment"]["formal_protocol"]["protocol_id"])
    if protocol_id != "carr_s_e2_v8_formal_r4":
        raise ValueError("r4 lane runner requires the frozen r4 protocol")

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
            batch = run_seed_batch(
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
            completion["completed_runs"] != 5
            or completion["planned_runs"] != 5
            or valid != 5
            or completion["aborted_early"]
        ):
            state.update(
                state="STOPPED_NONVALID_BATCH",
                stop_reason=f"seed {seed} did not finish five-for-five VALID",
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
