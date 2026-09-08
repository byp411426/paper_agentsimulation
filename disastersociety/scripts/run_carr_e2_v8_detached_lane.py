"""Run one detached lane of immutable Carr-S E2 v8 seed batches.

The lane never retries a failed seed. It stops immediately after a non-zero
subprocess exit or a seed batch that is not five-for-five VALID, preserving all
artifacts for audit. Scientific execution remains delegated to the frozen
single-seed runner.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SINGLE_SEED_RUNNER = PROJECT_ROOT / "scripts/run_carr_e2_v8_formal.py"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    config = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    status_path = (
        results_dir / f"carr_s_e2_v8_formal_r3_lane_{args.lane}_status.json"
    )
    state: dict[str, Any] = {
        "protocol_id": "carr_s_e2_v8_formal_r3",
        "lane": args.lane,
        "pid": os.getpid(),
        "config": str(config.relative_to(PROJECT_ROOT)),
        "declared_seeds": args.seeds,
        "completed_seeds": [],
        "current_seed": None,
        "state": "STARTED",
        "stop_reason": None,
    }
    _write_status(status_path, state)

    for seed in args.seeds:
        state.update(current_seed=seed, state="RUNNING")
        _write_status(status_path, state)
        command = [
            sys.executable,
            str(SINGLE_SEED_RUNNER),
            "--config",
            str(config),
            "--seed",
            str(seed),
        ]
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if completed.returncode != 0:
            state.update(
                state="STOPPED_SUBPROCESS_ERROR",
                stop_reason=f"seed {seed} exited {completed.returncode}",
            )
            _write_status(status_path, state)
            return completed.returncode

        batch_path = (
            results_dir / f"carr_s_e2_v8_formal_seed{seed}_summary.json"
        )
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
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
            _write_status(status_path, state)
            return 2

        state["completed_seeds"].append(seed)
        state["current_seed"] = None
        state["state"] = "SEED_COMPLETE"
        _write_status(status_path, state)

    state.update(state="COMPLETE", current_seed=None)
    _write_status(status_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
