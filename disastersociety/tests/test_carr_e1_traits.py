"""Carr E1 v2 trait donor tests (W2 contract)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    path = PROJECT_ROOT / "scripts/build_carr_e1_trait_donors.py"
    spec = importlib.util.spec_from_file_location("build_carr_e1_trait_donors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


@pytest.fixture(scope="module")
def codebook():
    path = PROJECT_ROOT / "experiments/carr/protocol/carr_s_e1_v2_trait_codebook.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_worry_scale_literals(builder, codebook):
    mapping = codebook["encoding"]["Q29.3_worry"]
    assert builder.encode_value("Not at all worried", mapping, "q") == 0.00
    assert builder.encode_value("Slightly worried", mapping, "q") == 0.25
    assert builder.encode_value("Moderately worried", mapping, "q") == 0.50
    assert builder.encode_value("Very worried", mapping, "q") == 0.75
    assert builder.encode_value("Extremely worried", mapping, "q") == 1.00


def test_likelihood_scale_literals(builder, codebook):
    mapping = codebook["encoding"]["Q29.4_likelihood"]
    assert builder.encode_value("Extremely unlikely", mapping, "q") == 0.00
    assert builder.encode_value("Somewhat unlikely", mapping, "q") == 0.25
    assert builder.encode_value("Neither likely nor unlikely", mapping, "q") == 0.50
    assert builder.encode_value("Somewhat likely", mapping, "q") == 0.75
    assert builder.encode_value("Extremely likely", mapping, "q") == 1.00


def test_yes_no_booleans(builder, codebook):
    mapping = codebook["encoding"]["Q32.9_Q32.10"]
    assert builder.encode_value("Yes", mapping, "q") is True
    assert builder.encode_value("No", mapping, "q") is False


def test_trust_and_helping_literals(builder, codebook):
    trust_map = codebook["encoding"]["Q35.3_trustworthiness"]
    assert builder.encode_value("Almost never trustworthy", trust_map, "q") == 0.00
    assert builder.encode_value("Almost always trustworthy", trust_map, "q") == 1.00
    helping_map = codebook["encoding"]["Q35.6_helping"]
    assert builder.encode_value("1 (not at all true)", helping_map, "q") == 0.00
    assert builder.encode_value("5 (very true)", helping_map, "q") == 1.00
    general_map = codebook["encoding"]["Q35.4_general_trust"]
    assert builder.encode_value(
        "We can never be too cautious in our dealings with other people.",
        general_map,
        "q",
    ) == 0.00
    assert builder.encode_value("It is possible to trust most people.", general_map, "q") == 1.00


def test_prefer_not_to_answer_is_null(builder, codebook):
    mapping = codebook["encoding"]["Q34.4_decision_participation"]
    assert builder.encode_value("Prefer not to answer", mapping, "q") is None
    assert builder.is_null("")
    assert builder.is_null(" ")
    assert builder.is_null(float("nan"))


def test_unknown_literal_fails_fast(builder, codebook):
    mapping = codebook["encoding"]["Q29.3_worry"]
    with pytest.raises(ValueError, match="unknown literal"):
        builder.encode_value("Totally worried", mapping, "Q29.3_1")


def test_prior_evacuation_topcode(builder, codebook):
    mapping = codebook["encoding"]["Q34.2_prior_evacuation"]
    assert builder.encode_value("0", mapping, "q") == 0
    assert builder.encode_value("5", mapping, "q") == 5
    assert builder.encode_value("More than 5", mapping, "q") == 6


def test_factor_minimum_valid(builder, codebook):
    factors = codebook["factors"]
    assert builder.compute_factor([0.5, 0.25], factors["hazard_worry"]["minimum_valid"]) == pytest.approx(0.375)
    assert builder.compute_factor([0.5, None], factors["hazard_worry"]["minimum_valid"]) == pytest.approx(0.5)
    assert builder.compute_factor([None, None], factors["hazard_worry"]["minimum_valid"]) is None
    assert builder.compute_factor(
        [0.0, None, None, None], factors["evacuation_friction"]["minimum_valid"]
    ) is None


def test_matching_bands(builder):
    bands = builder.to_matching_bands("65_74", 2, 1, "50_75k")
    assert bands == {
        "age_band": "65_74",
        "household_band": "2",
        "vehicle_band": "1",
        "income_band": "50_99k",
    }
    bands = builder.to_matching_bands("18_24", 6, 4, None)
    assert bands["household_band"] == "5_plus"
    assert bands["vehicle_band"] == "3_plus"
    assert bands["income_band"] is None


def test_train_connection_is_198(builder):
    """Integration: frozen inputs must produce exactly 198 train donors."""
    raw = PROJECT_ROOT / "Wong_Carr_Wildfire_Dataset.csv"
    evaluation = PROJECT_ROOT / "eventpacks/carr_2018/behavior/evaluation_respondents.csv"
    split = PROJECT_ROOT / "experiments/carr/protocol/carr_r_split.csv"
    if not (raw.exists() and evaluation.exists() and split.exists()):
        pytest.skip("raw survey inputs not present")
    roles = (
        PROJECT_ROOT / "experiments/carr/protocol/carr_s_e1_v2_field_roles.yaml"
    )
    codebook_path = (
        PROJECT_ROOT / "experiments/carr/protocol/carr_s_e1_v2_trait_codebook.yaml"
    )
    import pandas as pd

    roles_cfg = yaml.safe_load(roles.read_text(encoding="utf-8"))
    codebook_cfg = yaml.safe_load(codebook_path.read_text(encoding="utf-8"))
    raw_df = builder.load_qualtrics(raw)
    allowed = {"ResponseId", *roles_cfg["raw_matching_inputs"],
               *roles_cfg["raw_household_trait_inputs"],
               *roles_cfg["raw_person_trait_inputs"]}
    frame = raw_df[[column for column in allowed if column in raw_df.columns]]
    evaluation_df = pd.read_csv(evaluation)[["evaluation_index", "respondent_id"]]
    split_df = pd.read_csv(split)
    joined = (
        frame.reset_index()
        .merge(evaluation_df, left_on="ResponseId", right_on="respondent_id", how="inner")
        .merge(split_df, on="evaluation_index", how="inner")
    )
    train = joined[joined["split"] == "train"]
    assert len(train) == 198
    assert train["evaluation_index"].nunique() == 198
    assert train["respondent_id"].nunique() == 198


def test_q34_4_not_coordinator_truth(codebook):
    assert codebook["notes"]["q34.4_not_coordinator_truth"] is True
    assert codebook["notes"]["q29_retrospective_pre_event_report"] is True
