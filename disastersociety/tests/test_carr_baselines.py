"""Offline checks for the frozen Carr-R validation baseline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from ds.eval.individual import (
    decision_confidence_to_positive_probability,
    ece,
)
from experiments.baselines.run_carr_r_deepseek import build_messages


ROOT = Path(__file__).resolve().parents[1]


def test_ece_uses_outcome_frequency_not_classifier_accuracy():
    y_true = np.array([0, 0, 1, 1])
    probability = np.array([0.1, 0.2, 0.8, 0.9])
    assert ece(y_true, probability, n_bins=2) == pytest.approx(0.15)


def test_carr_r_validation_config_keeps_test_sealed():
    path = (
        ROOT
        / "experiments/baselines/configs/carr_r_validation_pilot.yaml"
    )
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    experiment = config["experiment"]
    assert experiment["evaluation_splits"] == ["validation"]
    assert experiment["sealed_splits"] == ["test"]
    assert config["reporting"]["export_respondent_id"] is False

    live_path = (
        ROOT
        / "experiments/baselines/configs/carr_r_deepseek_validation.yaml"
    )
    live = yaml.safe_load(live_path.read_text(encoding="utf-8"))
    assert live["experiment"]["evaluation_splits"] == ["validation"]
    assert live["experiment"]["sealed_splits"] == ["test"]
    assert live["experiment"]["max_calls"] == 66
    assert live["reporting"]["export_respondent_id"] is False

    context_path = (
        ROOT
        / "experiments/baselines/configs/carr_r_deepseek_context_validation.yaml"
    )
    context = yaml.safe_load(context_path.read_text(encoding="utf-8"))
    assert context["experiment"]["evaluation_splits"] == ["validation"]
    assert context["experiment"]["sealed_splits"] == ["test"]
    assert context["experiment"]["max_calls"] == 66
    assert context["reporting"]["export_respondent_id"] is False


def test_carr_r_context_prompt_is_common_and_preoutcome_only():
    row = pd.Series(
        {
            "age_group": 7,
            "household_size": 3,
            "vehicle_count": 1,
            "income_bracket": 6,
        }
    )
    scenario = [
        "An active wildfire is threatening communities in the Redding area.",
        "Fire, smoke, and road conditions may change quickly.",
    ]
    prompt = build_messages(row, scenario_context=scenario)[1]["content"]
    assert all(line in prompt for line in scenario)
    assert "65-74" in prompt
    assert "household size: 3" in prompt
    assert "household vehicles: 1" in prompt
    assert "$50,000-$74,999" in prompt
    forbidden = (
        "respondent_id",
        "warned_official",
        "received_mandatory_order",
        "received_voluntary_order",
        "departure_fire_perception",
        "departure_smoke_perception",
        "evacuated_at",
        "Q9.1",
    )
    assert all(field not in prompt for field in forbidden)


def test_decision_confidence_is_converted_to_positive_probability():
    probability = decision_confidence_to_positive_probability(
        predictions=[0, 1],
        confidence=[0.8, 0.7],
    )
    assert probability.tolist() == pytest.approx([0.2, 0.7])
