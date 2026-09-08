"""Sequentially recheck the three diagnosed Carr-S v3 backend failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import run_carr_condition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/"
    "carr_s_deepseek_backend_reliability_v4.yaml"
)
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/"
    "carr_s_deepseek_backend_reliability_v4_summary.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def run_reliability_checks(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    runs_dir: Path,
) -> dict[str, Any]:
    protocol = cfg["experiment"]["reliability_protocol"]
    if not protocol.get("execute_sequentially"):
        raise ValueError("v4 reliability checks must execute sequentially")

    rows: list[dict[str, Any]] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0.0
    total_wall_clock = 0.0
    terminal_status_counts: dict[str, int] = {}
    for check in protocol["checks"]:
        seed = int(check["seed"])
        condition = str(check["condition"])
        result = run_carr_condition(
            cfg,
            condition=condition,
            seed=seed,
            runs_dir=runs_dir,
        )
        gateway = result.summary["gateway"]
        status = str(result.summary["status"])
        terminal_status_counts[status] = (
            terminal_status_counts.get(status, 0) + 1
        )
        prompt_tokens = int(gateway["live_prompt_tokens"])
        completion_tokens = int(gateway["live_completion_tokens"])
        wall_clock = float(result.summary["wall_clock_seconds"])
        cost = float(gateway["spent"])
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_wall_clock += wall_clock
        total_cost += cost
        rows.append(
            {
                "seed": seed,
                "condition": condition,
                "diagnosed_v3_failure": check["diagnosed_failure"],
                "terminal_status": status,
                "n_ok": int(gateway["n_ok"]),
                "n_failed": int(gateway["n_failed"]),
                "n_fallback": int(gateway["n_fallback"]),
                "fallback_rate": float(gateway["fallback_rate"]),
                "live_prompt_tokens": prompt_tokens,
                "live_completion_tokens": completion_tokens,
                "estimated_cost_usd": cost,
                "wall_clock_seconds": wall_clock,
                "run_dir": str(result.run_dir.relative_to(PROJECT_ROOT)),
                "summary_sha256": file_sha256(result.run_dir / "summary.json"),
                "provenance_sha256": file_sha256(
                    result.run_dir / "provenance.json"
                ),
            }
        )

    all_valid = terminal_status_counts == {"VALID": len(rows)}
    return {
        "status": cfg["experiment"].get("evidence_status", "PILOT"),
        "activity_type": cfg["experiment"].get(
            "activity_type", "BACKEND_RELIABILITY_CHECK"
        ),
        "prompt_version": cfg["experiment"]["prompt_version"],
        "decision_model": cfg["llm"]["decision_model"],
        "source": {
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "config_sha256": file_sha256(config_path),
        },
        "protocol": {
            "execute_sequentially": True,
            "test_split_opened": False,
            "substitute_for_v3_scientific_pairs": False,
            "n_checks": len(rows),
        },
        "completion": {
            "terminal_status_counts": terminal_status_counts,
            "all_checks_valid": all_valid,
        },
        "usage": {
            "live_prompt_tokens": total_prompt_tokens,
            "live_completion_tokens": total_completion_tokens,
            "estimated_cost_usd": round(total_cost, 6),
        },
        "runtime": {
            "sum_run_wall_clock_seconds": round(total_wall_clock, 3),
        },
        "checks": rows,
        "gate_interpretation": (
            "Every declared engineering check completed VALID with zero "
            "fallback; this does not convert any earlier INVALID run into a "
            "scientific observation."
            if all_valid
            else (
                "At least one check was INVALID, so backend reliability remains "
                "open. Inspect its preserved call log to distinguish a diagnosed "
                "interface/runtime recurrence from an external provider failure; "
                "formal mechanism runs must not start."
            )
        ),
        "claim_boundary": (
            "Engineering reliability/availability evidence only. These checks "
            "are not eligible for paired mechanism estimates or Carr empirical "
            "claims."
        ),
    }


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output_path = _resolve(args.output).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    summary = run_reliability_checks(
        cfg,
        config_path=config_path,
        runs_dir=runs_dir,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
