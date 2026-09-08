#!/usr/bin/env python3
"""Run the Carr E1 v2 preflight (mock or real backend)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from ds.llm.backends import MockBackend
from ds.llm.gateway import LLMGateway
from experiments.carr.empirical_v2_runner import run_e1_v2


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--backend", choices=("mock", "real"), default="mock")
    parser.add_argument("--n-households", type=int, default=None)
    parser.add_argument("--seed", type=int, default=4201)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--households-csv", type=Path, default=None)
    parser.add_argument("--tracts", type=Path, default=None)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    exp = cfg["experiment"]
    profiles_path = (
        PROJECT_ROOT / exp["profiles_dir"] / exp["profiles_file"]
    )
    n_households = args.n_households or int(exp["n_households"])
    out_dir = args.out_dir or (
        PROJECT_ROOT / "experiments/carr/runs"
    )
    models_cfg = yaml.safe_load(
        (PROJECT_ROOT / cfg["llm"]["models_config"]).read_text(
            encoding="utf-8"
        )
    )
    if args.backend == "mock":
        gateway = LLMGateway(
            run_id=cfg["run"]["run_id"],
            models_cfg=models_cfg,
            budget_usd=float(cfg["llm"]["budget_usd"]),
            max_concurrency=int(cfg["llm"]["max_concurrency"]),
            log_dir=out_dir,
            backends={cfg["llm"]["decision_model"]: MockBackend()},
        )
    else:
        gateway = LLMGateway(
            run_id=cfg["run"]["run_id"],
            models_cfg=models_cfg,
            budget_usd=float(cfg["llm"]["budget_usd"]),
            max_concurrency=int(cfg["llm"]["max_concurrency"]),
            log_dir=out_dir,
            abort_on_call_failure=True,
        )
    result = run_e1_v2(
        cfg=cfg,
        out_dir=out_dir,
        gateway=gateway,
        run_seed=args.seed,
        n_households=n_households,
        profiles_path=profiles_path,
        households_csv=args.households_csv,
        tracts_geojson=args.tracts,
    )
    gateway.flush()
    gateway.close()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
