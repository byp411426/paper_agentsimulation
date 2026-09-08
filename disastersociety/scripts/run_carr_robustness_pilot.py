"""Run the zero-cost Carr-S mechanism robustness scenario grid."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import CONDITIONS, run_carr_pilot_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/carr_s_robustness_pilot.yaml"
)


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def build_scenario_config(
    base: dict[str, Any],
    *,
    scenario_name: str,
    controls: dict[str, Any],
) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg["run"]["run_id"] = f"carr_s_robustness_pilot_{scenario_name}"
    for name in (
        "official_warning_delivery_probability",
        "social_message_delivery_probability",
        "route_capacity_per_step",
    ):
        if name not in controls:
            raise ValueError(f"{scenario_name}: missing control {name}")
        cfg["experiment"][name] = controls[name]
    cfg["experiment"]["robustness_scenario"] = scenario_name
    cfg["experiment"]["evidence_status"] = "PILOT"
    return cfg


def run_grid(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    protocol = load_yaml(config_path)
    base_path = resolve_path(protocol["base_config"])
    base = load_yaml(base_path)
    seeds = [int(seed) for seed in protocol["seeds"]]
    runs_dir = resolve_path(protocol["reporting"]["runs_dir"])
    scenario_outputs: dict[str, Any] = {}

    for scenario_name, controls in protocol["scenarios"].items():
        cfg = build_scenario_config(
            base,
            scenario_name=scenario_name,
            controls=controls,
        )
        output = run_carr_pilot_matrix(
            cfg,
            seeds=seeds,
            conditions=CONDITIONS,
            runs_dir=runs_dir,
        )
        matrix_path = (
            runs_dir / cfg["run"]["run_id"] / "pilot_matrix.json"
        )
        scenario_outputs[scenario_name] = {
            "controls": controls,
            "n_runs": len(output["runs"]),
            "all_runs_valid": all(
                row["run_terminal_status"] == "VALID"
                for row in output["runs"]
            ),
            "maximum_fallback_rate": max(
                float(row["fallback_rate"])
                for row in output["runs"]
            ),
            "total_estimated_cost_usd": sum(
                float(row["cost_usd"])
                for row in output["runs"]
            ),
            "paired_summary": output["paired_summary"],
            "ignored_matrix": {
                "path": str(matrix_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(matrix_path),
            },
        }

    cross_scenario = []
    modules = sorted(
        {
            item["module"]
            for scenario in scenario_outputs.values()
            for item in scenario["paired_summary"]
        }
    )
    for module in modules:
        values = []
        for scenario_name, scenario in scenario_outputs.items():
            item = next(
                row
                for row in scenario["paired_summary"]
                if row["module"] == module
            )
            values.append(
                {
                    "scenario": scenario_name,
                    "mean_paired_difference": float(
                        item["mean_paired_difference"]
                    ),
                    "positive_direction_fraction": float(
                        item["positive_direction_fraction"]
                    ),
                    "variance_informative": bool(
                        item["variance_informative"]
                    ),
                }
            )
        means = [row["mean_paired_difference"] for row in values]
        cross_scenario.append(
            {
                "module": module,
                "scenario_results": values,
                "minimum_mean_paired_difference": min(means),
                "maximum_mean_paired_difference": max(means),
                "positive_in_every_scenario": all(
                    row["positive_direction_fraction"] == 1.0
                    for row in values
                ),
                "seed_variance_informative_in_every_scenario": all(
                    row["variance_informative"] for row in values
                ),
            }
        )

    result = {
        "status": "PILOT",
        "activity_type": "ROBUSTNESS_DEVELOPMENT_GRID",
        "track": "Carr-S",
        "case_semantics": (
            "Carr-informed controlled robustness scenario grid"
        ),
        "n_households_per_run": int(base["experiment"]["n_households"]),
        "n_seeds": len(seeds),
        "n_conditions": len(CONDITIONS),
        "n_scenarios": len(scenario_outputs),
        "n_runs": sum(item["n_runs"] for item in scenario_outputs.values()),
        "seeds": seeds,
        "conditions": list(CONDITIONS),
        "scenarios": scenario_outputs,
        "cross_scenario": cross_scenario,
        "claim_boundary": (
            "Controlled zero-cost robustness evidence only. The grid is not "
            "calibrated to Carr observations and does not establish empirical "
            "mechanism effects or formal sensitivity intervals."
        ),
        "provenance": {
            "protocol": {
                "path": str(config_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(config_path),
            },
            "base_config": {
                "path": str(base_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(base_path),
            },
            "runner": {
                "path": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(Path(__file__)),
            },
            "common_runner": {
                "path": "experiments/carr/runner.py",
                "sha256": file_sha256(
                    PROJECT_ROOT / "experiments/carr/runner.py"
                ),
            },
            "resident_adapter": {
                "path": "ds/agents/carr.py",
                "sha256": file_sha256(PROJECT_ROOT / "ds/agents/carr.py"),
            },
            "kernel_engine": {
                "path": "ds/kernel/engine.py",
                "sha256": file_sha256(
                    PROJECT_ROOT / "ds/kernel/engine.py"
                ),
            },
            "llm_gateway": {
                "path": "ds/llm/gateway.py",
                "sha256": file_sha256(
                    PROJECT_ROOT / "ds/llm/gateway.py"
                ),
            },
            "command": (
                "uv run python scripts/run_carr_robustness_pilot.py"
            ),
        },
    }
    result_path = resolve_path(protocol["reporting"]["result_json"])
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config_path = (
        args.config
        if args.config.is_absolute()
        else PROJECT_ROOT / args.config
    )
    result = run_grid(config_path)
    print(
        json.dumps(
            {
                "status": result["status"],
                "n_runs": result["n_runs"],
                "cross_scenario": result["cross_scenario"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
