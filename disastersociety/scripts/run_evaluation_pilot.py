"""Run one fixed 8-household pilot, audit it, and export Codex review materials.

No key is written to disk. The model endpoint is called only by --run.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from scripts.evaluate_e1_run import evaluate
from scripts.run_carr_e1_v2_preflight import main as run_preflight


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "experiments/carr/configs/evaluation_pilot_8hh_20260910.yaml"
PROFILES = ROOT / "experiments/carr/inputs/evaluation_repair_20260909/profiles.jsonl"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="Call the configured real model endpoint")
    ap.add_argument("--output", type=Path, required=True, help="A new empty directory")
    args = ap.parse_args()
    import sys
    if not args.run:
        sys.argv = ["preflight", "--config", str(CFG), "--profiles", str(PROFILES), "--n-households", "8", "--validate-only"]
        run_preflight()
        print("Validated only. Add --run to generate a real-model simulation.")
        return
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError("Use a new empty output directory; prior attempts are preserved")
    if not os.environ.get("PACKY_API_KEY"):
        os.environ["PACKY_API_KEY"] = getpass.getpass("Packy API key (hidden): ").strip()
    if not os.environ["PACKY_API_KEY"]:
        raise ValueError("No API key supplied")
    sys.argv = ["preflight", "--config", str(CFG), "--profiles", str(PROFILES),
        "--backend", "real", "--n-households", "8", "--seed", "7201", "--out-dir", str(args.output)]
    run_preflight()
    run = args.output / "e1_pilot_8hh_20260910"
    status = json.loads((run / "execution_status.json").read_text())
    if status["status"] != "VALID" or status["completed_steps"] != status["planned_steps"]:
        raise SystemExit("Run incomplete/invalid; preserved its logs and did not manufacture evaluation scores.")
    result = evaluate(run, ROOT.parent, args.output / "evaluation")
    print(json.dumps({"metrics": result["metrics"],
        "codex_review_directory": str((args.output / "evaluation/review_inputs").resolve()),
        "behavior_score": None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
