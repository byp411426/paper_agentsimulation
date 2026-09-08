"""Configuration system (spec M0-M3 §1).

Config + seed = the unique identity of an experiment. Everything is read from a
single YAML file via pydantic. We keep typed sub-models for the fields the kernel
touches directly, plus permissive extra sections so EventPack / experiment configs
can carry their own keys without a schema change.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RunCfg(BaseModel):
    run_id: str
    seed: int = 0
    total_steps: int = 48
    step_minutes: int = 30


class LLMCfg(BaseModel):
    decision_model: str = "mock"
    temperature: float = 0.7
    max_concurrency: int = 16
    budget_usd: float = 2.0
    fallback_threshold: float = 0.01
    # path to the price/backend table; resolved relative to repo root
    models_file: str = "configs/models.yaml"


class Cfg(BaseModel):
    run: RunCfg
    llm: LLMCfg = Field(default_factory=LLMCfg)
    # permissive sections — validated by their own consumers (world/pop/interaction)
    world: dict[str, Any] = Field(default_factory=dict)
    population: dict[str, Any] = Field(default_factory=dict)
    interaction: dict[str, Any] = Field(default_factory=dict)
    experiment: dict[str, Any] = Field(default_factory=dict)

    def override(self, **kwargs: Any) -> "Cfg":
        """Return a deep copy with run-level fields overridden.

        Used by the multi-seed / ablation runner: cfg.override(run_id=..., seed=...).
        Nested overrides use dotted keys, e.g. override(**{"world.fire_spread_prob": 0.4}).
        """
        data = copy.deepcopy(self.model_dump())
        for key, val in kwargs.items():
            if "." in key:
                section, field = key.split(".", 1)
                data.setdefault(section, {})
                if isinstance(data[section], dict):
                    data[section][field] = val
                else:
                    setattr_nested(data[section], field, val)
            elif key in ("run_id", "seed", "total_steps", "step_minutes"):
                data["run"][key] = val
            else:
                data[key] = val
        return Cfg(**data)


def setattr_nested(d: dict, dotted: str, val: Any) -> None:
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = val


def load(path: str | Path) -> Cfg:
    """Load a run config from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        return Cfg(**yaml.safe_load(f))


def load_models(path: str | Path) -> dict[str, Any]:
    """Load the model price/backend table (configs/models.yaml)."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
