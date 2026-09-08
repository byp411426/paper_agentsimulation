"""Run the declared DeepSeek Carr-S backend gate on the common kernel."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import yaml

from experiments.carr.runner import (
    CONDITIONS,
    run_carr_condition,
    run_carr_pilot_matrix,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/carr_s_deepseek_backend_pilot.yaml"
)
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument(
        "--connectivity-check",
        action="store_true",
        help=(
            "Run one full-loop household solely to verify endpoint, schema, "
            "logging, cost accounting, and fallback behavior."
        ),
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[101, 202],
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=CONDITIONS,
        default=list(CONDITIONS),
    )
    parser.add_argument(
        "--decision-model",
        help="Override llm.decision_model; the resolved value is saved in provenance.",
    )
    parser.add_argument(
        "--run-id",
        help="Override run.run_id; use a new value for every backend attempt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = (
        args.config
        if args.config.is_absolute()
        else PROJECT_ROOT / args.config
    )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if args.decision_model:
        cfg["llm"]["decision_model"] = args.decision_model
    if args.run_id:
        cfg["run"]["run_id"] = args.run_id
    if args.connectivity_check:
        check_cfg = copy.deepcopy(cfg)
        prompt_version = check_cfg["experiment"]["prompt_version"]
        check_cfg["run"]["run_id"] += (
            f"_connectivity_check_{prompt_version}"
        )
        check_cfg["experiment"]["n_households"] = 1
        check_cfg["experiment"]["evidence_status"] = "PILOT"
        check_cfg["experiment"]["activity_type"] = "CONNECTIVITY_CHECK"
        check_cfg["experiment"][
            "official_warning_delivery_probability"
        ] = 1.0
        check_cfg["experiment"][
            "social_message_delivery_probability"
        ] = 1.0
        check_cfg["experiment"]["closure_step"] = 3
        check_cfg["experiment"].pop("closure_step_choices", None)
        result = run_carr_condition(
            check_cfg,
            condition="full",
            seed=int(args.seeds[0]),
            runs_dir=args.runs_dir,
        )
        output = {
            "status": "PILOT",
            "activity_type": "CONNECTIVITY_CHECK",
            "terminal_status": result.summary["status"],
            "gateway": result.summary["gateway"],
            "metrics": result.metrics,
            "run_dir": str(result.run_dir),
            "claim_boundary": (
                "Engineering connectivity evidence only; not a scientific "
                "experiment and not eligible for a paper result."
            ),
        }
    else:
        output = run_carr_pilot_matrix(
            cfg,
            seeds=[int(seed) for seed in args.seeds],
            conditions=tuple(args.conditions),
            runs_dir=args.runs_dir,
        )
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
