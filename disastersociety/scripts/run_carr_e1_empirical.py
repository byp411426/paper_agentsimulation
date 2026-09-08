"""Execute frozen Carr-S E1 real-backend seeds without automatic retries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from experiments.carr.empirical_runner import run_empirical_seed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/carr/configs/carr_s_e1_empirical_deepseek_v1.yaml"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seeds", type=int, nargs="+")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    declared = [int(seed) for seed in protocol["seeds"]]
    seeds = declared if args.seeds is None else [int(seed) for seed in args.seeds]
    if any(seed not in declared for seed in seeds):
        raise ValueError("requested E1 seed is outside the frozen protocol")
    runs_dir = _resolve(Path(cfg["reporting"]["runs_dir"]))
    results_dir = _resolve(Path(cfg["reporting"]["results_dir"]))
    status_path = results_dir / "carr_s_e1_empirical_v1_execution_status.json"
    state: dict[str, Any] = {
        "protocol_id": protocol["protocol_id"],
        "pid": os.getpid(),
        "declared_seeds": declared,
        "requested_seeds": seeds,
        "completed_seeds": [],
        "current_seed": None,
        "state": "STARTED",
        "stop_reason": None,
    }
    _write(status_path, state)
    for seed in seeds:
        state.update(current_seed=seed, state="RUNNING")
        _write(status_path, state)
        try:
            result = run_empirical_seed(
                cfg,
                config_path=config_path,
                seed=seed,
                runs_dir=runs_dir,
            )
        except BaseException as error:
            state.update(
                state="STOPPED_EXCEPTION",
                stop_reason=f"seed {seed}: {type(error).__name__}: {error}",
            )
            _write(status_path, state)
            return 1
        payload = {
            "protocol_id": protocol["protocol_id"],
            "seed": seed,
            "terminal_status": result.summary["status"],
            "summary": result.summary,
            "metrics": result.metrics,
            "run_dir": str(result.run_dir.relative_to(PROJECT_ROOT)),
        }
        _write(results_dir / f"carr_s_e1_empirical_v1_seed{seed}.json", payload)
        if result.summary["status"] != "VALID":
            state.update(
                state="STOPPED_NONVALID_RUN",
                stop_reason=f"seed {seed} terminal status {result.summary['status']}",
            )
            _write(status_path, state)
            return 2
        state["completed_seeds"].append(seed)
        state.update(current_seed=None, state="SEED_COMPLETE")
        _write(status_path, state)
    state.update(current_seed=None, state="COMPLETE")
    _write(status_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
