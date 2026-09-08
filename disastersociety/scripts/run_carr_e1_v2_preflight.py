#!/usr/bin/env python3
"""Run the Carr E1 v2 preflight (mock or real backend)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import hashlib
from pathlib import Path

import yaml

from ds.llm.backends import MockBackend
from ds.llm.cache import LLMCache
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
    parser.add_argument("--total-steps", type=int, default=None)
    parser.add_argument("--keychain-service", default=None)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.total_steps is not None:
        if args.total_steps < 1: raise ValueError("total_steps must be positive")
        cfg["run"]["total_steps"] = args.total_steps
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
    run_dir = out_dir / cfg["run"]["run_id"]
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Existing run is protected; choose a new --out-dir: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.backend == "real" and os.environ.get("PYTHONHASHSEED") != "0":
        raise ValueError("Launch with PYTHONHASHSEED=0 to freeze the existing spatial hash convention")
    if args.backend == "real" and args.keychain_service:
        key = subprocess.run(["security", "find-generic-password", "-s", args.keychain_service, "-w"],
                             capture_output=True, text=True, timeout=15)
        if key.returncode or not key.stdout.strip(): raise RuntimeError("Cannot read requested credential")
        spec = models_cfg['models'][cfg['llm']['decision_model']]
        env_name = spec.get('api_key_env') or spec.get('api_key_env_candidates', ['PACKY_API_KEY'])[0]
        os.environ[env_name] = key.stdout.strip()
    cache = LLMCache(run_dir / (args.backend + "_cache.sqlite"))
    (run_dir / "execution_config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    source_files = ["ds/agents/e1_contracts.py", "ds/agents/carr_empirical_v2.py",
                    "ds/world/carr_empirical_v2.py", "ds/interaction/carr_empirical_v2.py",
                    "ds/households/state.py", "ds/kernel/engine.py", "experiments/carr/empirical_v2_runner.py"]
    (run_dir / "provenance.json").write_text(json.dumps({
        "seed": args.seed, "backend": args.backend, "n_households": n_households,
        "python_hash_seed": os.environ.get('PYTHONHASHSEED'),
        "code_sha256": {f: hashlib.sha256((PROJECT_ROOT/f).read_bytes()).hexdigest() for f in source_files},
        "profiles_sha256": hashlib.sha256(profiles_path.read_bytes()).hexdigest(),
        "model_registry_sha256": hashlib.sha256((PROJECT_ROOT/cfg['llm']['models_config']).read_bytes()).hexdigest()
    }, indent=2))
    if args.backend == "mock":
        gateway = LLMGateway(
            run_id=cfg["run"]["run_id"],
            models_cfg=models_cfg,
            budget_usd=float(cfg["llm"]["budget_usd"]),
            max_concurrency=int(cfg["llm"]["max_concurrency"]),
            log_dir=out_dir,
            cache=cache,
            backends={cfg["llm"]["decision_model"]: MockBackend()},
        )
    else:
        gateway = LLMGateway(
            run_id=cfg["run"]["run_id"],
            models_cfg=models_cfg,
            budget_usd=float(cfg["llm"]["budget_usd"]),
            max_concurrency=int(cfg["llm"]["max_concurrency"]),
            log_dir=out_dir,
            cache=cache,
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
    cache.close()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
