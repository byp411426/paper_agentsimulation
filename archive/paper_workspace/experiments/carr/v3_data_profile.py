"""E0-V3 empirical event-history profile for the Carr survey.

This is not a simulator result. It establishes the distributions that a V3
simulation may later be evaluated against and detects impossible/ambiguous
records before any model is run.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("eventpacks/carr_2018/behavior/v3")
RESULTS = Path("experiments/carr/results")


def load() -> dict[str, pd.DataFrame]:
    names = {
        "respondents": "respondents.csv",
        "warnings": "warning_events.csv",
        "channels": "channel_receipts.csv",
        "households": "household_constraints.csv",
        "cognition": "predecision_cognition.csv",
        "departures": "departure_events.csv",
    }
    return {key: pd.read_csv(DATA / name) for key, name in names.items()}


def cumulative_departure_curve(
    respondents: pd.DataFrame,
    departures: pd.DataFrame,
    step_hours: float = 0.5,
) -> pd.DataFrame:
    """Empirical cumulative incidence; stayers remain in the denominator."""
    eligible = respondents.loc[respondents["evacuated"].notna(), "respondent_id"]
    dep = departures[
        departures["respondent_id"].isin(eligible)
        & departures["departure_hours_since_fire"].notna()
    ]
    valid_times = dep["departure_hours_since_fire"]
    start = np.floor(min(0.0, valid_times.min()) / step_hours) * step_hours
    end = np.ceil(valid_times.max() / step_hours) * step_hours
    grid = np.arange(start, end + step_hours, step_hours)
    denominator = len(eligible)
    return pd.DataFrame(
        {
            "hours_since_fire": grid,
            "departed_count": [(valid_times <= t).sum() for t in grid],
            "departed_share": [(valid_times <= t).sum() / denominator for t in grid],
            "denominator_q9_answered": denominator,
        }
    )


def warning_departure_delays(
    warnings: pd.DataFrame, departures: pd.DataFrame
) -> pd.DataFrame:
    first_warning = (
        warnings.loc[
            warnings["received"].eq(1) & warnings["order_datetime"].notna(),
            ["respondent_id", "order_datetime"],
        ]
        .assign(order_datetime=lambda x: pd.to_datetime(x["order_datetime"]))
        .groupby("respondent_id", as_index=False)["order_datetime"]
        .min()
        .rename(columns={"order_datetime": "first_warning_datetime"})
    )
    dep = departures.loc[
        departures["departure_datetime"].notna(),
        ["respondent_id", "departure_datetime"],
    ].copy()
    dep["departure_datetime"] = pd.to_datetime(dep["departure_datetime"])
    joined = dep.merge(first_warning, on="respondent_id", how="inner")
    joined["warning_to_departure_hours"] = (
        joined["departure_datetime"] - joined["first_warning_datetime"]
    ).dt.total_seconds() / 3600
    joined["departure_before_reported_warning"] = (
        joined["warning_to_departure_hours"] < 0
    ).astype(int)
    return joined


def subgroup_summary(
    respondents: pd.DataFrame,
    households: pd.DataFrame,
    departures: pd.DataFrame,
) -> pd.DataFrame:
    frame = respondents[["respondent_id", "evacuated"]].merge(
        households, on="respondent_id", how="left"
    ).merge(
        departures[["respondent_id", "departure_hours_since_fire"]],
        on="respondent_id",
        how="left",
    )
    groups = {
        "vehicle_access": pd.cut(
            frame["vehicle_count"],
            bins=[-np.inf, 0, 1, np.inf],
            labels=["no_vehicle", "one_vehicle", "two_plus"],
        ),
        "children": frame["children_under_18"].gt(0).map(
            {True: "has_children", False: "no_children"}
        ),
        "older_adults": frame["adults_65_plus"].gt(0).map(
            {True: "has_65_plus", False: "no_65_plus"}
        ),
        "disability": frame["members_with_disability"].gt(0).map(
            {True: "has_disability", False: "no_disability"}
        ),
        "pets": frame["has_pets"].map({1.0: "has_pets", 0.0: "no_pets"}),
        "livestock": frame["has_livestock"].map(
            {1.0: "has_livestock", 0.0: "no_livestock"}
        ),
    }
    rows: list[dict] = []
    for variable, labels in groups.items():
        for label in labels.dropna().unique():
            sub = frame.loc[labels.eq(label) & frame["evacuated"].notna()]
            observed_times = sub["departure_hours_since_fire"].dropna()
            rows.append(
                {
                    "variable": variable,
                    "group": str(label),
                    "n": int(len(sub)),
                    "evacuation_share": float(sub["evacuated"].mean()),
                    "n_departure_times": int(len(observed_times)),
                    "median_departure_hours_since_fire": (
                        float(observed_times.median())
                        if len(observed_times)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def cognition_summary(
    respondents: pd.DataFrame, cognition: pd.DataFrame
) -> pd.DataFrame:
    frame = respondents[["respondent_id", "evacuated"]].merge(
        cognition, on="respondent_id", how="left"
    )
    score_cols = [
        c
        for c in cognition.columns
        if c.endswith("_score") and (c.startswith("worry_") or c.startswith("belief_"))
    ]
    rows: list[dict] = []
    for column in score_cols:
        for outcome, label in [(0.0, "stayed"), (1.0, "evacuated")]:
            values = frame.loc[frame["evacuated"].eq(outcome), column].dropna()
            rows.append(
                {
                    "construct": column,
                    "outcome_group": label,
                    "n": int(len(values)),
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "std": float(values.std(ddof=1)) if len(values) > 1 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    tables = load()
    curve = cumulative_departure_curve(
        tables["respondents"], tables["departures"]
    )
    delays = warning_departure_delays(tables["warnings"], tables["departures"])
    subgroups = subgroup_summary(
        tables["respondents"], tables["households"], tables["departures"]
    )
    cognition = cognition_summary(tables["respondents"], tables["cognition"])

    channel_counts = (
        tables["channels"]
        .groupby(["order_type", "channel", "channel_family"], observed=True)
        .size()
        .rename("count")
        .reset_index()
    )
    summary = {
        "schema_version": 3,
        "artifact_type": "empirical_data_profile_not_simulation",
        "q9_answered": int(tables["respondents"]["evacuated"].notna().sum()),
        "evacuation_share": float(tables["respondents"]["evacuated"].mean()),
        "complete_departure_times": int(
            tables["departures"]["departure_datetime"].notna().sum()
        ),
        "warning_departure_pairs": int(len(delays)),
        "departure_before_reported_warning": int(
            delays["departure_before_reported_warning"].sum()
        ),
        "warning_to_departure_hours_nonnegative": {
            "n": int(delays["warning_to_departure_hours"].ge(0).sum()),
            "median": float(
                delays.loc[
                    delays["warning_to_departure_hours"].ge(0),
                    "warning_to_departure_hours",
                ].median()
            ),
        },
        "measurement_notes": [
            "warning channels are multi-label, not first-channel observations",
            "stayers have no observed departure time and remain in the cumulative-incidence denominator",
            "negative warning-to-departure delays are retained as an empirical sequence diagnostic",
            "Q13.6 departure perceptions are excluded from pre-decision cognition",
        ],
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    curve.to_csv(RESULTS / "v3_empirical_departure_curve.csv", index=False)
    delays.to_csv(RESULTS / "v3_warning_departure_delays.csv", index=False)
    subgroups.to_csv(RESULTS / "v3_subgroup_event_history.csv", index=False)
    cognition.to_csv(RESULTS / "v3_predecision_cognition_summary.csv", index=False)
    channel_counts.to_csv(RESULTS / "v3_channel_multilabel_counts.csv", index=False)
    (RESULTS / "v3_data_profile.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
