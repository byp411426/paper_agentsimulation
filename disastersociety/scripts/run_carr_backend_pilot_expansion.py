"""Run one predeclared seed of the Carr-S backend-pilot expansion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from experiments.carr.runner import CONDITIONS, run_carr_pilot_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/"
    "carr_s_deepseek_backend_pilot_expansion.yaml"
)
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = (
        args.config
        if args.config.is_absolute()
        else PROJECT_ROOT / args.config
    )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    allowed = [
        int(seed)
        for seed in cfg["experiment"]["expansion_protocol"]["new_seeds"]
    ]
    if args.seed not in allowed:
        raise ValueError(
            f"seed {args.seed} is not in the predeclared expansion {allowed}"
        )
    cfg["run"]["run_id"] = (
        f"{cfg['run']['run_id']}_batch_seed{args.seed}"
    )
    output = run_carr_pilot_matrix(
        cfg,
        seeds=[args.seed],
        conditions=CONDITIONS,
        runs_dir=args.runs_dir,
    )
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
