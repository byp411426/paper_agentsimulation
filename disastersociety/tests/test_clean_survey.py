from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from ds.eval.carr_protocol import (
    freeze_stratified_split,
    load_field_roles,
    validate_field_roles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/clean_survey.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("clean_survey", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_survey_datetime():
    module = _load_module()
    assert module.parse_survey_datetime(
        "Thursday, July 26", "7:00 PM"
    ) == pd.Timestamp("2018-07-26 19:00:00")
    assert pd.isna(module.parse_survey_datetime(None, "7:00 PM"))
    assert pd.isna(module.parse_survey_datetime("After Sunday, Aug. 5", "7:00 PM"))


def test_carr_cleaning_matches_questionnaire_branches():
    module = _load_module()
    raw = module.load_qualtrics()
    clean = module.build_clean(raw)
    finished = raw[raw["Finished"].eq("TRUE")].reset_index(drop=True)

    assert len(clean) == 335
    assert clean["respondent_id"].is_unique
    assert int(clean["evacuation_eval_eligible"].sum()) == 330
    assert int(clean["evacuated"].eq(1).sum()) == 293
    assert int(clean["evacuated"].eq(0).sum()) == 37
    assert int(clean["evacuated_at"].notna().sum()) == 292
    assert not (
        clean["evacuated"].fillna(-1).astype(int)
        == clean["warned_official"].astype(int)
    ).all()

    # The PDF/CSV header maps interpersonal receipt to suffix 11, not suffix 9.
    assert int(clean["heard_interpersonal"].sum()) > 0
    assert "risk_perception" not in clean.columns
    assert "heard_from" not in clean.columns

    # Q13.6_1 is visual fire level and Q13.6_2 is smoke level.  Both are
    # measured at departure and remain excluded from prediction inputs.
    expected_fire = finished["Q13.6_1"].map(module.LIKERT_MAP).astype("Int64")
    expected_smoke = finished["Q13.6_2"].map(module.LIKERT_MAP).astype("Int64")
    assert clean["departure_fire_perception"].equals(expected_fire)
    assert clean["departure_smoke_perception"].equals(expected_smoke)

    observed_evac_times = clean["evacuated_at"].dropna()
    assert (observed_evac_times >= module.FIRE_START).all()


def test_carr_protocol_roles_and_split_are_complete_and_deterministic():
    module = _load_module()
    clean = module.build_clean(module.load_qualtrics())
    evaluation = (
        clean.loc[clean["evacuation_eval_eligible"], ["evacuated"]]
        .reset_index(drop=True)
        .rename_axis("evaluation_index")
        .reset_index()
    )
    roles_path = (
        PROJECT_ROOT / "experiments/carr/protocol/field_roles.yaml"
    )
    roles = load_field_roles(roles_path)
    validate_field_roles(roles, set(clean.columns))

    first = freeze_stratified_split(evaluation, seed=20260731)
    second = freeze_stratified_split(evaluation, seed=20260731)
    assert first.equals(second)
    assert first.groupby("split").size().to_dict() == {
        "test": 66,
        "train": 198,
        "validation": 66,
    }
    assert list(first.columns) == ["evaluation_index", "split"]
