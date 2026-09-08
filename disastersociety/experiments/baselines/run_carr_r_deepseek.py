"""Run the leakage-controlled DeepSeek Carr-R validation pilot.

The script exits before any network call if none of ``PACKY_API_KEY``,
``LLM_API_KEY``, or the legacy-compatible ``OPENAI_API_KEY`` is available.
Run from ``disastersociety/``:

    uv run --extra ml python experiments/baselines/run_carr_r_deepseek.py

Use ``--connectivity-limit 1`` only for endpoint connectivity; the connectivity
output goes to the ignored run directory and never overwrites the 66-record
validation result.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, Field

from ds.eval.carr_protocol import file_sha256
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMCallFailed, LLMGateway
from ds.kernel.rng import derive
from experiments.baselines.train_carr_r_frozen import (
    classification_metrics,
    conditional_stratified_bootstrap,
    load_model_table,
    resolve_project_path,
    stable_seed,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/baselines/configs/carr_r_deepseek_validation.yaml"
)
MODELS_CONFIG = PROJECT_ROOT / "configs/models.yaml"

AGE_MAP = {
    1: "under 18",
    2: "18-24",
    3: "25-34",
    4: "35-44",
    5: "45-54",
    6: "55-64",
    7: "65-74",
    8: "75-84",
    9: "85 or older",
}
INCOME_MAP = {
    1: "less than $10,000",
    2: "$10,000-$14,999",
    3: "$15,000-$24,999",
    4: "$25,000-$34,999",
    5: "$35,000-$49,999",
    6: "$50,000-$74,999",
    7: "$75,000-$99,999",
    8: "$100,000-$149,999",
    9: "$150,000-$199,999",
    10: "$200,000 or more",
}


class StaticEvacuationEstimate(BaseModel):
    decision: Literal["evacuate", "stay"]
    probability_evacuated: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=240)


def display_code(value: Any, mapping: dict[int, str]) -> str:
    if pd.isna(value):
        return "not reported"
    return mapping.get(int(value), "not reported")


def display_count(value: Any) -> str:
    if pd.isna(value):
        return "not reported"
    return str(int(value))


def build_messages(
    row: pd.Series,
    *,
    scenario_context: list[str] | None = None,
) -> list[dict[str, str]]:
    system = (
        "You are a component in a controlled disaster-behavior simulation. "
        "Estimate the requested outcome using only the supplied fields. Do not "
        "invent warnings, locations, household composition, or later events. "
        "Return only a JSON object matching the requested schema."
    )
    context = ""
    if scenario_context:
        context = "\nCommon pre-outcome scenario context:\n" + "\n".join(
            f"- {line}" for line in scenario_context
        )
    user = f"""Case: 2018 Carr Fire near Redding, California.
Outcome to estimate: whether this resident evacuates at any time during the fire.
{context}

Resident information:
- age group: {display_code(row["age_group"], AGE_MAP)}
- household size: {display_count(row["household_size"])}
- household vehicles: {display_count(row["vehicle_count"])}
- annual household income: {display_code(row["income_bracket"], INCOME_MAP)}

Return:
- decision: "evacuate" or "stay"
- probability_evacuated: number from 0 to 1
- rationale: at most 30 words, mentioning no facts beyond the supplied fields"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def available_credential(model_spec: dict[str, Any]) -> str | None:
    candidates = list(model_spec.get("api_key_env_candidates", []))
    if model_spec.get("api_key_env"):
        candidates.insert(0, model_spec["api_key_env"])
    return next((name for name in candidates if os.environ.get(name)), None)


async def run_async(
    config_path: Path,
    *,
    connectivity_limit: int | None,
) -> dict[str, Any]:
    config = load_yaml(config_path)
    experiment = config["experiment"]
    evaluation_splits = list(experiment["evaluation_splits"])
    sealed_splits = set(experiment.get("sealed_splits", []))
    if sealed_splits & set(evaluation_splits) or "test" in evaluation_splits:
        raise ValueError("DeepSeek validation pilot must not open test")

    table, features = load_model_table(config)
    evaluation = table.loc[
        table["split"].isin(evaluation_splits)
    ].sort_values("evaluation_index")
    scenario_context = experiment.get("scenario_context")
    if scenario_context is not None:
        if not isinstance(scenario_context, list) or not scenario_context:
            raise ValueError("scenario_context must be a non-empty list")
        if not all(
            isinstance(line, str) and line.strip()
            for line in scenario_context
        ):
            raise ValueError("scenario_context lines must be non-empty strings")
    if len(evaluation) > int(experiment["max_calls"]):
        raise ValueError("evaluation rows exceed the configured call fuse")
    if connectivity_limit is not None:
        if connectivity_limit < 1:
            raise ValueError("connectivity limit must be positive")
        evaluation = evaluation.head(connectivity_limit)

    models_config = load_yaml(MODELS_CONFIG)
    model_alias = experiment["model_alias"]
    model_spec = models_config["models"][model_alias]
    credential_name = available_credential(model_spec)
    if credential_name is None:
        candidates = model_spec.get("api_key_env_candidates", [])
        raise RuntimeError(
            "No proxy credential is available. Set one of: "
            + ", ".join(candidates)
        )
    if not str(model_spec["model_id"]).startswith("openai/"):
        raise ValueError(
            "custom OpenAI-compatible LiteLLM model needs openai/ prefix"
        )

    mode = (
        "connectivity_check"
        if connectivity_limit is not None
        else "validation"
    )
    run_id = (
        f"carr-r-deepseek-{experiment['prompt_version']}-{mode}"
    )
    run_root = resolve_project_path(config["reporting"]["run_root"])
    cache = LLMCache(resolve_project_path(config["reporting"]["cache"]))
    gateway = LLMGateway(
        run_id=run_id,
        models_cfg=models_config,
        budget_usd=float(experiment["estimated_budget_usd"]),
        max_concurrency=int(experiment["max_concurrency"]),
        log_dir=run_root,
        cache=cache,
    )

    async def decide(row: pd.Series) -> dict[str, Any]:
        index = int(row["evaluation_index"])
        messages = build_messages(
            row,
            scenario_context=scenario_context,
        )
        try:
            output = await gateway.complete(
                step=0,
                agent_id=f"evaluation-{index}",
                model=model_alias,
                messages=messages,
                schema=StaticEvacuationEstimate,
                seed=derive(int(experiment["base_seed"]), index),
                temperature=float(experiment["temperature"]),
            )
            return {
                "evaluation_index": index,
                "status": "ok",
                "decision": output.decision,
                "probability_evacuated": output.probability_evacuated,
            }
        except LLMCallFailed as error:
            return {
                "evaluation_index": index,
                "status": "failed",
                "error": str(error),
            }

    try:
        outputs = await asyncio.gather(
            *(decide(row) for _, row in evaluation.iterrows())
        )
        gateway.flush()
        gateway_stats = gateway.stats()
    finally:
        await gateway.aclose()
        cache.close()

    output_table = pd.DataFrame(outputs)
    failures = output_table["status"].ne("ok")
    if failures.any():
        status = "INVALID_BACKEND_FAILURE"
        metrics = None
    else:
        status = (
            "CONNECTIVITY_CHECK"
            if connectivity_limit is not None
            else config["status"]
        )
        merged = evaluation[
            ["evaluation_index", "split", "evacuated"]
        ].merge(
            output_table,
            on="evaluation_index",
            validate="one_to_one",
        )
        y_true = merged["evacuated"].to_numpy(dtype=int)
        probability = merged["probability_evacuated"].to_numpy(dtype=float)
        y_pred = merged["decision"].eq("evacuate").to_numpy(dtype=int)
        consistency = (
            (y_pred == 1) & (probability >= 0.5)
        ) | ((y_pred == 0) & (probability < 0.5))
        metrics = classification_metrics(
            y_true,
            probability,
            threshold=float(experiment["decision_threshold"]),
            ece_bins=int(experiment["ece_bins"]),
            predictions=y_pred,
        )
        metrics["decision_probability_consistency_rate"] = float(
            consistency.mean()
        )
        if connectivity_limit is None:
            metrics["conditional_stratified_bootstrap_95pct"] = (
                conditional_stratified_bootstrap(
                    y_true,
                    probability,
                    threshold=float(experiment["decision_threshold"]),
                    ece_bins=int(experiment["ece_bins"]),
                    replicates=int(experiment["bootstrap_replicates"]),
                    seed=stable_seed(
                        int(experiment["bootstrap_seed"]),
                        model_alias,
                        "validation",
                    ),
                    predictions=y_pred,
                )
            )

    prompt_template_hash = hashlib.sha256(
        json.dumps(
            build_messages(
                pd.Series(
                    {
                        "age_group": 2,
                        "household_size": 2,
                        "vehicle_count": 1,
                        "income_bracket": 5,
                    }
                ),
                scenario_context=scenario_context,
            ),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    result = {
        "status": status,
        "track": "Carr-R",
        "mode": mode,
        "test_split_opened": False,
        "model_alias": model_alias,
        "model_id": model_spec["model_id"],
        "prompt_version": experiment["prompt_version"],
        "prompt_template_sha256": prompt_template_hash,
        "features": features,
        "n_requested": int(len(evaluation)),
        "n_failed": int(failures.sum()),
        "metrics": metrics,
        "gateway": gateway_stats,
        "pricing_status": model_spec.get("pricing_status", "unspecified"),
        "claim_boundary": experiment.get(
            "claim_boundary",
            (
                "Validation-only static demographic baseline. This is auxiliary "
                "Carr-R evidence, not a multi-step social simulation result and "
                "not a platform-validity claim."
            ),
        ),
        "provenance": {
            "runner": {
                "path": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(Path(__file__)),
            },
            "configuration": {
                "path": str(config_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(config_path),
            },
            "models_config_sha256": file_sha256(MODELS_CONFIG),
            "respondent_id_exported": False,
            "credential_environment_name": credential_name,
            "credential_value_recorded": False,
            "python": platform.python_version(),
            "litellm": importlib.metadata.version("litellm"),
            "command": (
                "uv run --extra ml python "
                "experiments/baselines/run_carr_r_deepseek.py"
            ),
        },
    }
    if connectivity_limit is None:
        result_path = resolve_project_path(
            config["reporting"]["result_json"]
        )
        predictions_path = resolve_project_path(
            config["reporting"]["predictions_csv"]
        )
        result_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if not failures.any():
            merged[
                [
                    "evaluation_index",
                    "split",
                    "evacuated",
                    "decision",
                    "probability_evacuated",
                ]
            ].rename(columns={"evacuated": "y_true"}).to_csv(
                predictions_path,
                index=False,
            )
    else:
        connectivity_path = run_root / run_id / "connectivity_summary.json"
        connectivity_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    parser.add_argument("--connectivity-limit", type=int)
    args = parser.parse_args()
    config_path = (
        args.config
        if args.config.is_absolute()
        else PROJECT_ROOT / args.config
    )
    result = asyncio.run(
        run_async(
            config_path,
            connectivity_limit=args.connectivity_limit,
        )
    )
    print(
        f"status={result['status']} n={result['n_requested']} "
        f"failed={result['n_failed']} test_opened={result['test_split_opened']}"
    )
    if result["metrics"]:
        print(
            f"macro_f1={result['metrics']['macro_f1']:.3f} "
            f"brier={result['metrics']['brier']:.3f} "
            f"ece={result['metrics']['ece']:.3f}"
        )


if __name__ == "__main__":
    main()
