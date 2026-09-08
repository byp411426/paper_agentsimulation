"""Audit r5 batches through the frozen v8 summarizer without renaming data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from experiments.carr.runner import CONDITIONS
from scripts.summarize_carr_e2_v8_formal import build_summary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_formal_r5.yaml"
DEFAULT_RESULTS = PROJECT_ROOT / "experiments/carr/results"
DEFAULT_RUNS = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = DEFAULT_RESULTS / "carr_s_e2_v8_formal_r5_cumulative_summary.json"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output = _resolve(args.output).resolve()
    with tempfile.TemporaryDirectory(
        prefix="carr-e2-r5-audit-", dir=results_dir
    ) as temporary:
        audit_dir = Path(temporary)
        for source in results_dir.glob(
            "carr_s_e2_v8_formal_r5_seed*_summary.json"
        ):
            seed = source.stem.removeprefix(
                "carr_s_e2_v8_formal_r5_seed"
            ).removesuffix("_summary")
            target = audit_dir / f"carr_s_e2_v8_formal_seed{seed}_summary.json"
            os.symlink(source.resolve(), target)
        summary = build_summary(
            config_path=config_path,
            results_dir=audit_dir,
            runs_dir=runs_dir,
        )
    if summary["completion"]["planned_runs"] != (
        len(summary["completion"]["declared_seeds"]) * len(CONDITIONS)
    ):
        raise ValueError("r5 audit planned-run count violates E2 contract")
    output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
