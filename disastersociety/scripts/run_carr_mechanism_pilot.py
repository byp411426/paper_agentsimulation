"""Run the zero-cost paired Carr-S mechanism pilot matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from experiments.carr.runner import CONDITIONS, run_carr_pilot_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/carr_s_mechanism_pilot.yaml"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[101, 202, 303, 404, 505],
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments/carr/runs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = run_carr_pilot_matrix(
        cfg,
        seeds=args.seeds,
        conditions=CONDITIONS,
        runs_dir=args.runs_dir,
    )
    print(
        json.dumps(
            {
                "status": output["status"],
                "n_households": output["n_households"],
                "seeds": output["seeds"],
                "conditions": output["conditions"],
                "paired_primary_differences": output[
                    "paired_primary_differences"
                ],
                "paired_summary": output["paired_summary"],
                "pilot_gate_assessment": output["pilot_gate_assessment"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
