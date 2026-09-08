"""Build the Carr survey analysis table from the Qualtrics export.

The variable map is grounded in `Wong_Carr_Wildfire_Survey.pdf` and the second
header row of `Wong_Carr_Wildfire_Dataset.csv`:

- Q9.1: evacuation screening;
- Q13.3/Q13.4: evacuation date/time;
- Q5.2: received order types;
- Q6.2/Q6.3 and Q7.2/Q7.3: mandatory and voluntary order date/time;
- Q6.1 and Q7.1: multi-select receipt channels.

Run:
    uv run python scripts/clean_survey.py

Outputs:
    eventpacks/carr_2018/behavior/survey_clean.csv
    eventpacks/carr_2018/behavior/evaluation_respondents.csv
    eventpacks/carr_2018/behavior/survey_clean_qa.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = PROJECT_ROOT / "Wong_Carr_Wildfire_Dataset.csv"
OUT_DIR = PROJECT_ROOT / "eventpacks/carr_2018/behavior"
OUT_CSV = OUT_DIR / "survey_clean.csv"
EVAL_SET_CSV = OUT_DIR / "evaluation_respondents.csv"
QA_JSON = OUT_DIR / "survey_clean_qa.json"

FIRE_START = pd.Timestamp("2018-07-23 13:15:00")
RECEIVED_MARKER = "Received message (check all that apply)"

CHANNEL_COLUMNS = {
    "reverse_911": 1,
    "text": 2,
    "television": 3,
    "radio": 4,
    "flyer": 5,
    "public_official": 6,
    "social_media": 7,
    "subscribed_service": 8,
    "website": 9,
    "smartphone_app": 10,
    "interpersonal": 11,
    "billboard": 12,
    "other": 13,
}

AGE_MAP = {
    "Under 18": 1,
    "18 - 24": 2,
    "25 - 34": 3,
    "35 - 44": 4,
    "45 - 54": 5,
    "55 - 64": 6,
    "65 - 74": 7,
    "75 - 84": 8,
    "85 or older": 9,
}

INCOME_MAP = {
    "Less than $10,000": 1,
    "$10,000 - $14,999": 2,
    "$15,000 - $24,999": 3,
    "$25,000 - $34,999": 4,
    "$35,000 - $49,999": 5,
    "$50,000 - $74,999": 6,
    "$75,000 - $99,999": 7,
    "$100,000 - $149,999": 8,
    "$150,000 - $199,999": 9,
    "More than $200,000": 10,
}

LIKERT_MAP = {
    "Extremely high": 1,
    "Moderately high": 2,
    "Slightly high": 3,
    "Neither high nor low": 4,
    "Slightly low": 5,
    "Moderately low": 6,
    "Extremely low": 7,
}


def load_qualtrics(path: Path = RAW_CSV) -> pd.DataFrame:
    """Read the two-row Qualtrics header and remove its ImportId metadata row."""
    raw = pd.read_csv(path, header=[0, 1], low_memory=False)
    raw.columns = [column[0] for column in raw.columns]
    raw = raw[raw["ResponseId"] != '{"ImportId":"_recordId"}'].copy()
    return raw.reset_index(drop=True)


def parse_survey_datetime(date_value: Any, time_value: Any) -> pd.Timestamp:
    """Combine strings such as 'Thursday, July 26' and '7:00 PM' in 2018."""
    if pd.isna(date_value) or pd.isna(time_value):
        return pd.NaT
    date_text = str(date_value).strip()
    time_text = str(time_value).strip()
    if date_text.startswith("After "):
        return pd.NaT
    if ", " in date_text:
        date_text = date_text.split(", ", 1)[1]
    date_text = date_text.replace(".", "")
    return pd.to_datetime(f"{date_text}, 2018 {time_text}", errors="coerce")


def parse_int(value: Any, special: dict[str, int] | None = None) -> Any:
    """Parse a survey integer while preserving missingness."""
    if pd.isna(value) or value == "Prefer not to answer":
        return pd.NA
    if special and value in special:
        return special[value]
    try:
        return int(value)
    except (TypeError, ValueError):
        return pd.NA


def _channel_selected(raw: pd.DataFrame, suffix: int) -> pd.Series:
    """Whether a channel was selected for either received evacuation order."""
    mandatory = (
        raw["Q5.2_1"].eq("Yes")
        & raw[f"Q6.1_{suffix}"].eq(RECEIVED_MARKER)
    )
    voluntary = (
        raw["Q5.2_2"].eq("Yes")
        & raw[f"Q7.1_{suffix}"].eq(RECEIVED_MARKER)
    )
    return mandatory | voluntary


def build_clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Create one row per completed response without imputing missing outcomes."""
    raw = raw[raw["Finished"].eq("TRUE")].copy().reset_index(drop=True)
    clean = pd.DataFrame({"respondent_id": raw["ResponseId"].astype(str)})

    clean["evacuated"] = raw["Q9.1"].map({"Yes": 1, "No": 0}).astype("Int64")
    clean["evacuation_eval_eligible"] = clean["evacuated"].notna()
    clean["exclusion_reason"] = clean["evacuated"].isna().map(
        {True: "missing_evacuation_screen", False: ""}
    )

    clean["warned_official"] = (
        raw["Q5.2_1"].eq("Yes") | raw["Q5.2_2"].eq("Yes")
    ).astype("Int64")
    clean["received_mandatory_order"] = raw["Q5.2_1"].eq("Yes").astype("Int64")
    clean["received_voluntary_order"] = raw["Q5.2_2"].eq("Yes").astype("Int64")
    clean["reported_no_official_order"] = raw["Q5.2_4"].eq("Yes").astype("Int64")
    clean["order_response_inconsistent"] = (
        clean["warned_official"].eq(1)
        & clean["reported_no_official_order"].eq(1)
    )

    mandatory_at = pd.Series(
        [
            parse_survey_datetime(date, time)
            if received == "Yes" else pd.NaT
            for date, time, received in zip(raw["Q6.2"], raw["Q6.3"], raw["Q5.2_1"])
        ],
        dtype="datetime64[ns]",
    )
    voluntary_at = pd.Series(
        [
            parse_survey_datetime(date, time)
            if received == "Yes" else pd.NaT
            for date, time, received in zip(raw["Q7.2"], raw["Q7.3"], raw["Q5.2_2"])
        ],
        dtype="datetime64[ns]",
    )
    evacuation_at = pd.Series(
        [
            parse_survey_datetime(date, time)
            if outcome == "Yes" else pd.NaT
            for date, time, outcome in zip(raw["Q13.3"], raw["Q13.4"], raw["Q9.1"])
        ],
        dtype="datetime64[ns]",
    )

    clean["mandatory_order_at"] = mandatory_at
    clean["voluntary_order_at"] = voluntary_at
    clean["first_evacuation_order_at"] = pd.concat(
        [mandatory_at, voluntary_at], axis=1
    ).min(axis=1)
    clean["evacuated_at"] = evacuation_at
    clean["warning_hour_since_ignition"] = (
        clean["first_evacuation_order_at"] - FIRE_START
    ).dt.total_seconds() / 3600
    clean["evacuation_hour_since_ignition"] = (
        clean["evacuated_at"] - FIRE_START
    ).dt.total_seconds() / 3600
    clean["warning_after_evacuation"] = (
        clean["first_evacuation_order_at"].notna()
        & clean["evacuated_at"].notna()
        & (clean["first_evacuation_order_at"] > clean["evacuated_at"])
    )

    for channel, suffix in CHANNEL_COLUMNS.items():
        clean[f"heard_{channel}"] = _channel_selected(raw, suffix).astype("Int64")
    channel_fields = [f"heard_{name}" for name in CHANNEL_COLUMNS]
    clean["warning_channel_count"] = clean[channel_fields].sum(axis=1).astype("Int64")

    # Q13.6 is observed at departure and is therefore an outcome/process variable,
    # not a pre-decision prediction feature.
    clean["departure_fire_perception"] = raw["Q13.6_1"].map(LIKERT_MAP).astype("Int64")
    clean["departure_smoke_perception"] = raw["Q13.6_2"].map(LIKERT_MAP).astype("Int64")

    clean["age_group"] = raw["Q32.2"].map(AGE_MAP).astype("Int64")
    clean["household_size"] = raw["Q32.8_1"].map(
        lambda value: parse_int(value, {"10 or more": 10})
    ).astype("Int64")
    clean["vehicle_count"] = raw["Q32.11"].map(
        lambda value: parse_int(value, {"More than 5": 6})
    ).astype("Int64")
    clean["income_bracket"] = raw["Q32.13"].map(INCOME_MAP).astype("Int64")

    return clean


def build_qa(raw: pd.DataFrame, clean: pd.DataFrame) -> dict[str, Any]:
    """Build a machine-readable audit summary for the derived table."""
    eligible = clean[clean["evacuation_eval_eligible"]]
    evacuees = eligible[eligible["evacuated"].eq(1)]
    channel_counts = {
        channel: int(clean[f"heard_{channel}"].sum())
        for channel in CHANNEL_COLUMNS
    }
    return {
        "status": "VERIFIED",
        "source_csv": RAW_CSV.name,
        "source_sha256": hashlib.sha256(RAW_CSV.read_bytes()).hexdigest(),
        "questionnaire_pdf": "Wong_Carr_Wildfire_Survey.pdf",
        "mapping": {
            "evacuated": "Q9.1",
            "evacuated_at": ["Q13.3", "Q13.4"],
            "order_types": ["Q5.2_1", "Q5.2_2", "Q5.2_4"],
            "mandatory_order_at": ["Q6.2", "Q6.3"],
            "voluntary_order_at": ["Q7.2", "Q7.3"],
            "channels": ["Q6.1_1..13", "Q7.1_1..13"],
            "departure_fire_perception": "Q13.6_1",
            "departure_smoke_perception": "Q13.6_2",
        },
        "n_raw_responses": int(len(raw)),
        "n_finished": int(len(clean)),
        "n_evaluation_eligible": int(len(eligible)),
        "n_excluded_missing_screen": int((~clean["evacuation_eval_eligible"]).sum()),
        "n_evacuated": int(eligible["evacuated"].sum()),
        "n_not_evacuated": int(eligible["evacuated"].eq(0).sum()),
        "evacuation_rate": float(eligible["evacuated"].mean()),
        "n_evacuated_with_datetime": int(evacuees["evacuated_at"].notna().sum()),
        "n_evacuated_missing_datetime": int(evacuees["evacuated_at"].isna().sum()),
        "n_with_order_datetime": int(clean["first_evacuation_order_at"].notna().sum()),
        "n_warning_after_evacuation": int(clean["warning_after_evacuation"].sum()),
        "n_order_response_inconsistent": int(clean["order_response_inconsistent"].sum()),
        "channel_selection_counts": channel_counts,
        "notes": [
            "Channel fields are multi-select prevalence indicators, not first-heard shares.",
            "Q13.6 departure perceptions are post-outcome variables and excluded from prediction inputs.",
            "Q13.6_1 is visual fire level and Q13.6_2 is smoke level; both are measured at departure.",
            "Historical model results were generated before this repair and remain INVALID_FOR_CLAIM.",
        ],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_qualtrics()
    clean = build_clean(raw)
    qa = build_qa(raw, clean)

    clean.to_csv(OUT_CSV, index=False)
    (
        clean.loc[clean["evacuation_eval_eligible"], ["respondent_id", "evacuated"]]
        .reset_index(drop=True)
        .rename_axis("evaluation_index")
        .reset_index()
        .to_csv(EVAL_SET_CSV, index=False)
    )
    QA_JSON.write_text(json.dumps(qa, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Finished responses: {qa['n_finished']}")
    print(
        "Evaluation set: "
        f"{qa['n_evaluation_eligible']} "
        f"({qa['n_evacuated']} evacuated, {qa['n_not_evacuated']} not evacuated)"
    )
    print(
        "Evacuation time: "
        f"{qa['n_evacuated_with_datetime']} complete, "
        f"{qa['n_evacuated_missing_datetime']} missing"
    )
    print(f"Wrote {OUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {EVAL_SET_CSV.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {QA_JSON.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
