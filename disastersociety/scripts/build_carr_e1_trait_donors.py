#!/usr/bin/env python3
"""Build Carr E1 v2 train-only household/person trait donors.

Connects the 198 Carr-R train respondents one-to-one, encodes the frozen
literal-value codebook, computes Q29 factors, and writes separate household
and person donor tables with provenance.  Q9/Q10/Q11/Q13 and all outcome
fields are never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from scripts.clean_survey import load_qualtrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NULL_VALUES = {"", " ", "Prefer not to answer"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_null(value: object) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return True
    return str(value).strip() in NULL_VALUES


def encode_value(value: object, mapping: dict, field: str):
    if is_null(value):
        return None
    text = str(value).strip()
    if text not in mapping:
        raise ValueError(f"unknown literal for {field}: {text!r}")
    return mapping[text]


def to_matching_bands(age_code, household_size, vehicle_count, income_code):
    household_band = (
        "1"
        if household_size == 1
        else "2"
        if household_size == 2
        else "3_4"
        if household_size in (3, 4)
        else "5_plus"
        if household_size is not None and household_size >= 5
        else None
    )
    vehicle_band = (
        str(vehicle_count)
        if vehicle_count is not None and vehicle_count <= 2
        else "3_plus"
        if vehicle_count is not None
        else None
    )
    income_band = (
        "lt_25k"
        if income_code in ("lt_10k", "10_15k", "15_25k")
        else "25_49k"
        if income_code in ("25_35k", "35_50k")
        else "50_99k"
        if income_code in ("50_75k", "75_100k")
        else "100k_plus"
        if income_code in ("100_150k", "150_200k", "200k_plus")
        else None
    )
    return {
        "age_band": age_code,
        "household_band": household_band,
        "vehicle_band": vehicle_band,
        "income_band": income_band,
    }


def compute_factor(item_values: list, minimum_valid: int) -> float | None:
    valid = [value for value in item_values if value is not None]
    if len(valid) < minimum_valid:
        return None
    return float(np.mean(valid))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-survey", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--field-roles", type=Path, required=True)
    parser.add_argument("--trait-codebook", type=Path, required=True)
    parser.add_argument("--restricted-dir", type=Path, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    args = parser.parse_args()

    roles = yaml.safe_load(args.field_roles.read_text(encoding="utf-8"))
    codebook = yaml.safe_load(args.trait_codebook.read_text(encoding="utf-8"))
    allowed = {
        "ResponseId",
        *roles["raw_matching_inputs"],
        *roles["raw_household_trait_inputs"],
        *roles["raw_person_trait_inputs"],
    }

    raw = load_qualtrics(args.raw_survey)
    # Strict allowlist: we only ever select `allowed` columns.
    used_columns = [column for column in allowed if column in raw.columns]
    missing_columns = sorted(allowed - set(raw.columns) - {"ResponseId"})
    if missing_columns:
        raise ValueError(f"raw survey missing allowlisted columns: {missing_columns}")
    frame = raw[used_columns].copy()

    evaluation = pd.read_csv(args.evaluation)
    if set(evaluation.columns) != {"evaluation_index", "respondent_id", "evacuated"}:
        raise ValueError("evaluation_respondents.csv schema changed")
    evaluation = evaluation[["evaluation_index", "respondent_id"]].copy()
    split = pd.read_csv(args.split)
    if set(split.columns) != {"evaluation_index", "split"}:
        raise ValueError("carr_r_split.csv schema changed")

    joined = (
        frame.reset_index()
        .merge(evaluation, left_on="ResponseId", right_on="respondent_id", how="inner")
        .merge(split, on="evaluation_index", how="inner")
    )
    train = joined[joined["split"] == "train"].copy()
    n_train = len(train)
    if n_train != 198:
        raise ValueError(f"expected 198 train respondents, got {n_train}")
    if train["evaluation_index"].nunique() != 198:
        raise ValueError("train evaluation_index not unique")
    if train["respondent_id"].nunique() != 198:
        raise ValueError("train respondent_id not unique")
    if train["ResponseId"].isna().any():
        raise ValueError("unmatched respondent rows present")
    train = train.sort_values("evaluation_index").reset_index(drop=True)

    enc = codebook["encoding"]
    worry = enc["Q29.3_worry"]
    likelihood = enc["Q29.4_likelihood"]
    trust = enc["Q35.3_trustworthiness"]
    helping = enc["Q35.6_helping"]
    participation = enc["Q34.4_decision_participation"]
    prior_evac = enc["Q34.2_prior_evacuation"]
    household_size_map = enc["Q32.8_household_size"]
    vehicle_map = enc["Q32.11_vehicle_count"]
    age_map = enc["Q32.2_age_band"]
    income_map = enc["Q32.13_income_band"]

    person_rows: list[dict] = []
    household_rows: list[dict] = []
    for position, (_, row) in enumerate(train.iterrows(), start=1):
        person_id = f"carr_p_donor_{position:04d}"
        household_id = f"carr_hh_donor_{position:04d}"

        q29_3 = [
            encode_value(row[f"Q29.3_{i}"], worry, f"Q29.3_{i}")
            for i in range(1, 10)
        ]
        q29_4 = [
            encode_value(row[f"Q29.4_{i}"], likelihood, f"Q29.4_{i}")
            for i in range(1, 10)
        ]
        q35_3 = [
            encode_value(row[f"Q35.3_{i}"], trust, f"Q35.3_{i}")
            for i in range(1, 13)
        ]
        q35_6 = [
            encode_value(row[f"Q35.6_{i}"], helping, f"Q35.6_{i}")
            for i in range(1, 6)
        ]
        factors = codebook["factors"]
        factor_values = {
            "hazard_worry": compute_factor(
                [q29_3[0], q29_3[1]], factors["hazard_worry"]["minimum_valid"]
            ),
            "evacuation_friction": compute_factor(
                q29_3[2:], factors["evacuation_friction"]["minimum_valid"]
            ),
            "home_person_threat": compute_factor(
                [q29_4[0], q29_4[1], q29_4[3], q29_4[4]],
                factors["home_person_threat"]["minimum_valid"],
            ),
            "infrastructure_rescue": compute_factor(
                [q29_4[2], q29_4[6], q29_4[7]],
                factors["infrastructure_rescue"]["minimum_valid"],
            ),
            "property_security": compute_factor(
                [q29_4[5]], factors["property_security"]["minimum_valid"]
            ),
            "work_obligation": compute_factor(
                [q29_4[8]], factors["work_obligation"]["minimum_valid"]
            ),
        }
        valid_helping = [value for value in q35_6 if value is not None]
        helping_tendency = (
            float(np.mean(valid_helping))
            if len(valid_helping) >= codebook["helping_tendency"]["minimum_valid"]
            else None
        )
        prior_raw = row["Q34.2"]
        prior_count = encode_value(prior_raw, prior_evac, "Q34.2")
        household_size = encode_value(
            row["Q32.8_1"], household_size_map, "Q32.8_1"
        )
        vehicle_count = encode_value(row["Q32.11"], vehicle_map, "Q32.11")
        age_code = encode_value(row["Q32.2"], age_map, "Q32.2")
        income_code = encode_value(row["Q32.13"], income_map, "Q32.13")
        bands = to_matching_bands(age_code, household_size, vehicle_count, income_code)

        person_rows.append(
            {
                "trait_donor_id": person_id,
                **factor_values,
                "trust_item_1": q35_3[0],
                "trust_item_2": q35_3[1],
                "trust_item_3": q35_3[2],
                "trust_item_4": q35_3[3],
                "trust_item_5": q35_3[4],
                "trust_item_6": q35_3[5],
                "trust_item_7": q35_3[6],
                "trust_item_8": q35_3[7],
                "trust_item_9": q35_3[8],
                "trust_item_10": q35_3[9],
                "trust_item_11": q35_3[10],
                "trust_item_12": q35_3[11],
                "general_trust": encode_value(row["Q35.4"], enc["Q35.4_general_trust"], "Q35.4"),
                "helping_tendency": helping_tendency,
                "prior_evacuation_count_capped": prior_count,
                "prior_evacuation_topcoded": bool(not is_null(prior_raw) and str(prior_raw).strip() == "More than 5"),
                "decision_participation_propensity": encode_value(
                    row["Q34.4"], participation, "Q34.4"
                ),
                **bands,
            }
        )
        household_rows.append(
            {
                "trait_donor_id": household_id,
                "pet_owned": encode_value(row["Q32.9"], enc["Q32.9_Q32.10"], "Q32.9"),
                "livestock_owned": encode_value(
                    row["Q32.10"], enc["Q32.9_Q32.10"], "Q32.10"
                ),
                **bands,
            }
        )

    person_donors = pd.DataFrame(person_rows)
    household_donors = pd.DataFrame(household_rows)
    args.restricted_dir.mkdir(parents=True, exist_ok=True)
    args.public_dir.mkdir(parents=True, exist_ok=True)
    person_path = args.restricted_dir / "carr_person_trait_donors_v1.csv"
    household_path = args.restricted_dir / "carr_household_trait_donors_v1.csv"
    person_donors.to_csv(person_path, index=False)
    household_donors.to_csv(household_path, index=False)

    qa = {
        "n_train_respondents": n_train,
        "unique_evaluation_index": int(train["evaluation_index"].nunique()),
        "unique_respondent_id": int(train["respondent_id"].nunique()),
        "unmatched_rows": 0,
        "raw_columns_read": sorted(used_columns),
        "forbidden_prefixes_checked": roles["raw_evaluation_only_prefixes"],
        "raw_survey_sha256": sha256(args.raw_survey),
        "split_sha256": sha256(args.split),
        "field_roles_sha256": sha256(args.field_roles),
        "trait_codebook_sha256": sha256(args.trait_codebook),
        "output_sha256": {
            "carr_household_trait_donors_v1.csv": sha256(household_path),
            "carr_person_trait_donors_v1.csv": sha256(person_path),
        },
        "factor_valid_counts": {
            factor: int(person_donors[factor].notna().sum())
            for factor in codebook["factors"]
        },
        "missing_rate": {
            column: float(person_donors[column].isna().mean())
            for column in person_donors.columns
            if column != "trait_donor_id"
        },
        "raw_category_counts": {
            column: frame[column].fillna("<missing>").value_counts().to_dict()
            for column in frame.columns
            if column != "ResponseId"
        },
    }
    qa_path = args.public_dir / "carr_e1_trait_qa_v1.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False), encoding="utf-8")

    item_texts = {}
    header = pd.read_csv(args.raw_survey, header=[0, 1], nrows=0, low_memory=False)
    for column in used_columns:
        if column == "ResponseId":
            continue
        texts = [str(text) for text in header[column].columns if str(text) != "nan"]
        item_texts[column] = texts[0] if texts else None
    codebook_output = {
        "encoding": enc,
        "factors": factors,
        "helping_tendency": codebook["helping_tendency"],
        "item_text_mapping": item_texts,
        "lineage": roles["derived_field_lineage"],
        "source_tag": roles["source_tag"],
        "notes": codebook["notes"],
    }
    (args.public_dir / "carr_e1_trait_codebook_v1.json").write_text(
        json.dumps(codebook_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(qa, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
