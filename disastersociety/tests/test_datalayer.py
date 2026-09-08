"""Data-layer tests: IPF, SRMSE, BPR/point-queue (spec §5.4 CI matrix)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ds.eval.cost import srmse
from ds.eventpack import load_eventpack, load_warning_events
from ds.population.synth import (
    build_donor_tables,
    controlled_two_adult_cohort,
    fit_ipf,
    ipf,
    prepare_carr_donor_features,
    sample_households,
    sample_whole_households,
    synthesize_by_tract,
)
from ds.world.queue_model import PointQueueNetwork


def _load_build_pums_module():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts/build_pums_donors.py"
    spec = importlib.util.spec_from_file_location("build_pums_donors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mini_donors():
    housing = pd.DataFrame(
        {
            "SERIALNO": ["h1", "h2", "h3"],
            "NP": [2, 2, 2],
            "WGTP": [10.0, 20.0, 30.0],
            "HINCP": [50_000, 30_000, -2_000],
            "ADJINC": [1_100_000, None, 1_100_000],
            "VEH": [2, 0, 1],
            "HHT": [1, 4, 1],
        }
    )
    persons = pd.DataFrame(
        {
            "SERIALNO": ["h1", "h1", "h2", "h2", "h3", "h3"],
            "SPORDER": [1, 2, 1, 2, 1, 2],
            "RELP": [0, 1, 0, 2, 0, 1],
            "AGEP": [40, 38, 65, 10, 30, 5],
            "PWGTP": [10.0, 10.0, 20.0, 20.0, 30.0, 30.0],
        }
    )
    return housing, persons


def test_ipf_converges_to_marginals():
    # seed households with two attributes
    seed = pd.DataFrame({
        "age": ["young", "old", "young", "old", "young"],
        "car": ["yes", "yes", "no", "no", "yes"],
    })
    targets = {
        "age": pd.Series({"young": 60.0, "old": 40.0}),
        "car": pd.Series({"yes": 70.0, "no": 30.0}),
    }
    w = ipf(seed, targets, max_iter=500, tol=1e-9)
    # after fitting, weighted marginals must match targets
    age_fit = w.groupby(seed["age"]).sum()
    car_fit = w.groupby(seed["car"]).sum()
    assert abs(age_fit["young"] - 60.0) < 1e-3
    assert abs(age_fit["old"] - 40.0) < 1e-3
    assert abs(car_fit["yes"] - 70.0) < 1e-3
    assert abs(car_fit["no"] - 30.0) < 1e-3


def test_ipf_not_false_converge():
    """Regression: the old code 'converged' on iter 1. A seed with a repeated cell
    makes the two margins genuinely conflict, so one sweep is NOT enough."""
    # 3x 'young/yes' skews the joint table so margins can't be met in one pass
    seed = pd.DataFrame({
        "age": ["young", "young", "young", "young", "old", "old"],
        "car": ["yes",   "yes",   "yes",   "no",    "yes", "no"],
    })
    targets = {
        "age": pd.Series({"young": 60.0, "old": 40.0}),
        "car": pd.Series({"yes": 50.0, "no": 50.0}),
    }
    w1 = ipf(seed, targets, max_iter=1, tol=1e-12)
    age_fit1 = w1.groupby(seed["age"]).sum()
    assert abs(age_fit1["young"] - 60.0) > 1e-3  # first sweep does not yet satisfy age
    # full run converges
    w = ipf(seed, targets, max_iter=1000, tol=1e-12)
    age_fit = w.groupby(seed["age"]).sum()
    car_fit = w.groupby(seed["car"]).sum()
    assert abs(age_fit["young"] - 60.0) < 1e-3
    assert abs(car_fit["yes"] - 50.0) < 1e-3


def test_ipf_uses_base_weights_within_target_cells():
    seed = pd.DataFrame({"structure": ["couple", "couple", "single"]})
    targets = {"structure": pd.Series({"couple": 10.0, "single": 10.0})}
    base = pd.Series([9.0, 1.0, 1.0], index=seed.index)
    result = fit_ipf(seed, targets, base_weights=base)
    assert result.converged
    assert result.weights.iloc[0] / result.weights.iloc[1] == pytest.approx(9.0)


def test_ipf_rejects_structural_zero_and_inconsistent_totals():
    seed = pd.DataFrame(
        {"age": ["young", "old"], "car": ["yes", "no"]}
    )
    with pytest.raises(ValueError, match="structural-zero"):
        fit_ipf(
            seed,
            {"age": pd.Series({"young": 5.0, "middle": 5.0})},
        )
    with pytest.raises(ValueError, match="totals disagree"):
        fit_ipf(
            seed,
            {
                "age": pd.Series({"young": 5.0, "old": 5.0}),
                "car": pd.Series({"yes": 8.0, "no": 4.0}),
            },
        )


def test_sample_households_deterministic():
    seed = pd.DataFrame({"age": ["a", "b", "c"], "car": ["y", "n", "y"]})
    w = pd.Series([1.0, 1.0, 1.0], index=seed.index)
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    s1 = sample_households(seed, w, 10, rng1)
    s2 = sample_households(seed, w, 10, rng2)
    assert s1.equals(s2)


def test_whole_donor_sampling_preserves_members_and_hides_serialno():
    housing = pd.DataFrame(
        {
            "SERIALNO": [10, 20],
            "NP": [2, 1],
            "WGTP": [9, 1],
            "vehicle_count": [1, 0],
        }
    )
    persons = pd.DataFrame(
        {
            "SERIALNO": [10, 10, 20],
            "SPORDER": [1, 2, 1],
            "RELP": [0, 1, 0],
            "AGEP": [45, 12, 70],
        }
    )
    donors = build_donor_tables(housing, persons)
    assert "SERIALNO" not in donors.households
    assert "SERIALNO" not in donors.persons
    assert "SERIALNO" in donors.restricted_linkage
    population = sample_whole_households(
        donors,
        pd.Series([1.0, 0.0], index=donors.households.index),
        3,
        np.random.default_rng(7),
    )
    assert len(population.households) == 3
    assert len(population.persons) == 6
    assert population.households["synthetic_household_id"].is_unique
    assert population.persons["resident_id"].is_unique
    assert set(population.persons.groupby("synthetic_household_id").size()) == {2}
    assert "donor_id" not in population.households
    assert "donor_id" not in population.persons
    assert population.qa["unique_donors"] == 1
    assert population.qa["max_donor_copies"] == 3


def test_v2_adjusted_income_keeps_null_and_negative_rules():
    build = _load_build_pums_module()
    housing, _ = _mini_donors()
    adjusted = build.adjusted_income_2018(housing)
    # h1: 50_000 * 1_100_000 / 1_000_000 = 55_000
    assert adjusted.loc[0, "HINCP_ADJUSTED_2018"] == pytest.approx(55_000)
    assert bool(adjusted.loc[0, "negative_income"]) is False
    # h2: ADJINC missing -> null, not zero
    assert pd.isna(adjusted.loc[1, "HINCP_ADJUSTED_2018"])
    assert bool(adjusted.loc[1, "negative_income"]) is False
    # h3: negative income preserved
    assert adjusted.loc[2, "HINCP_ADJUSTED_2018"] == pytest.approx(-2_200)
    assert bool(adjusted.loc[2, "negative_income"]) is True


def test_v2_codebook_decodes_labels_and_na(tmp_path):
    build = _load_build_pums_module()
    codebook = {
        "fields": {
            "TEN": {
                "label": "Tenure",
                "na_code": "b",
                "codes": {"1": "Owned with mortgage", "2": "Owned free and clear"},
            },
            "WKHP": {
                "label": "Usual hours",
                "na_code": "bb",
                "numeric": True,
                "codes": {"99": "99 or more"},
            },
        }
    }
    frame = pd.DataFrame({"TEN": ["1", "2", "b", "1"], "WKHP": ["40", "99", "bb", None]})
    decoded, unknown = build.decode_coded_fields(frame, codebook, prefix="housing")
    assert unknown == {}
    assert decoded["TEN_label"].tolist() == [
        "Owned with mortgage",
        "Owned free and clear",
        None,
        "Owned with mortgage",
    ]
    assert decoded["WKHP_label"].tolist() == [None, "99 or more", None, None]


def test_v2_codebook_unknown_code_fails_fast(tmp_path):
    build = _load_build_pums_module()
    codebook = {
        "fields": {
            "TEN": {
                "label": "Tenure",
                "na_code": "b",
                "codes": {"1": "Owned"},
            }
        }
    }
    frame = pd.DataFrame({"TEN": ["1", "9"]})
    with pytest.raises(ValueError, match="unknown PUMS codes"):
        build.decode_coded_fields(frame, codebook, prefix="housing")


def test_v2_income_bin_marks_missing():
    build = _load_build_pums_module()
    binned = build.income_bin(pd.Series([8_000, 50_000, None]))
    assert binned.tolist() == ["lt_10000", "50000_59999", "missing_income"]


def test_v2_prepare_donor_features_uses_adjusted_income():
    housing, persons = _mini_donors()
    housing = _load_build_pums_module().adjusted_income_2018(housing)
    donors = build_donor_tables(housing, persons)
    prepared = prepare_carr_donor_features(
        donors,
        income_column="HINCP_ADJUSTED_2018",
        missing_income_fill=None,
    )
    incomes = prepared.households.set_index("donor_id")["household_income"]
    assert incomes.loc["donor_h0000001"] == "50000_59999"
    assert incomes.loc["donor_h0000002"] == "missing_income"


def test_donor_builder_rejects_invalid_member_structure():
    housing = pd.DataFrame({"SERIALNO": [10], "NP": [2]})
    duplicate_order = pd.DataFrame(
        {
            "SERIALNO": [10, 10],
            "SPORDER": [1, 1],
            "RELP": [0, 1],
        }
    )
    with pytest.raises(ValueError, match="SPORDER"):
        build_donor_tables(housing, duplicate_order)


def test_carr_features_and_two_adult_cohort_preserve_disability_fields():
    housing = pd.DataFrame(
        {
            "SERIALNO": [10, 20],
            "NP": [3, 1],
            "WGTP": [9, 1],
            "HINCP": [38_000, 8_000],
            "VEH": [1, 0],
            "HHT": [1, 4],
        }
    )
    persons = pd.DataFrame(
        {
            "SERIALNO": [10, 10, 10, 20],
            "SPORDER": [1, 2, 3, 1],
            "RELP": [0, 1, 2, 0],
            "AGEP": [45, 40, 12, 70],
            "DREM": [0, 1, 0, 0],
        }
    )
    donors = prepare_carr_donor_features(
        build_donor_tables(housing, persons)
    )
    assert donors.households.loc[0, "household_income"] == "35000_39999"
    assert donors.households.loc[0, "household_structure"] == "married_couple"
    assert donors.households.loc[1, "household_older_adult_presence"] == "has_65_plus"
    assert "DREM" in donors.persons

    population = sample_whole_households(
        donors,
        pd.Series([1.0, 0.0], index=donors.households.index),
        2,
        np.random.default_rng(4),
    )
    cohort = controlled_two_adult_cohort(population)
    assert len(cohort.households) == 2
    assert len(cohort.persons) == 6
    adults = cohort.persons["AGEP"] >= 18
    assert (cohort.persons.loc[adults, "decision_policy"] == "generative").all()
    assert (cohort.persons.loc[~adults, "decision_policy"] == "dependent").all()
    assert cohort.persons.loc[
        cohort.persons["DREM"] == 1, "decision_capable"
    ].all()


def test_tract_synthesis_fits_households_and_copies_all_members():
    household_rows = []
    person_rows = []
    serial = 10
    for income in (8_000, 38_000):
        for vehicles in (0, 1):
            for household_type in (1, 4):
                for age in (40, 70):
                    household_rows.append(
                        {
                            "SERIALNO": serial,
                            "NP": 1,
                            "WGTP": (serial % 5) + 1,
                            "HINCP": income,
                            "VEH": vehicles,
                            "HHT": household_type,
                        }
                    )
                    person_rows.append(
                        {
                            "SERIALNO": serial,
                            "SPORDER": 1,
                            "RELP": 0,
                            "AGEP": age,
                        }
                    )
                    serial += 1
    housing = pd.DataFrame(household_rows)
    persons = pd.DataFrame(person_rows)
    donors = prepare_carr_donor_features(
        build_donor_tables(housing, persons)
    )
    target_rows = []
    categories = {
        "household_income": ["35000_39999", "lt_10000"],
        "vehicle_count": ["0", "1"],
        "household_structure": [
            "married_couple",
            "nonfamily_living_alone",
        ],
        "household_older_adult_presence": [
            "has_65_plus",
            "no_65_plus",
        ],
    }
    for geoid in ("g1", "g2"):
        for attr, values in categories.items():
            for value in values:
                target_rows.append(
                    {
                        "geoid": geoid,
                        "attribute": attr,
                        "category": value,
                        "estimate": 3.0,
                    }
                )
        for value in ("35_64", "65_plus"):
            target_rows.append(
                {
                    "geoid": geoid,
                    "attribute": "person_age_group",
                    "category": value,
                    "estimate": 4.0,
                }
            )
    population = synthesize_by_tract(
        donors,
        pd.DataFrame(target_rows),
        target_n=8,
        run_seed=21,
    )
    assert len(population.households) == 8
    assert population.households["synthetic_household_id"].is_unique
    assert population.persons["resident_id"].is_unique
    assert population.households.groupby("geoid").size().to_dict() == {
        "g1": 4,
        "g2": 4,
    }
    expected_persons = population.households["household_size"].sum()
    assert len(population.persons) == expected_persons
    assert population.qa["person_level_fit"] is False
    assert population.qa["person_age_diagnostic"]["used_in_fit"] is False
    assert set(population.qa["person_age_diagnostic"]["tracts"]) == {"g1", "g2"}


def test_srmse_zero_for_identical():
    p = pd.Series({"a": 30.0, "b": 70.0})
    assert srmse(p, p.copy()) < 1e-9


def test_srmse_positive_for_mismatch():
    p = pd.Series({"a": 90.0, "b": 10.0})
    q = pd.Series({"a": 10.0, "b": 90.0})
    assert srmse(p, q) > 0.1


def test_bpr_congestion_slows_travel():
    net = PointQueueNetwork()
    net.add_edge("e", free_time=10.0, capacity=100.0)
    t_empty = net.edges["e"].travel_time()
    for i in range(200):  # load beyond capacity
        net.enqueue("e", vehicle=i)
    t_loaded = net.edges["e"].travel_time()
    assert t_loaded > t_empty  # fuller road = slower
    assert abs(t_empty - 10.0) < 1e-9


def test_point_queue_conserves_vehicles():
    net = PointQueueNetwork()
    net.add_edge("e", free_time=1.0, capacity=5.0)
    for i in range(23):
        net.enqueue("e", vehicle=i)
    total_released = 0
    for _ in range(10):
        rel = net.step()
        total_released += len(rel["e"])
    # 23 vehicles, 5/step -> all 23 released over 5 steps, none created/lost
    assert total_released == 23
    assert net.total_vehicles() == 0


def test_closed_edge_releases_nothing():
    net = PointQueueNetwork()
    net.add_edge("e", free_time=1.0, capacity=5.0)
    for i in range(10):
        net.enqueue("e", vehicle=i)
    net.close("e")
    rel = net.step()
    assert rel["e"] == []
    assert net.total_vehicles() == 10  # stuck behind the closure


def test_carr_eventpack_manifest_and_warning_loader():
    root = (
        Path(__file__).resolve().parents[1]
        / "eventpacks/carr_2018"
    )
    pack = load_eventpack(root)
    assert pack.manifest.event_id == "carr_2018"
    assert pack.manifest.simulation_step_minutes == 30
    assert pack.asset("hazard/perimeters.geojson").is_file()

    events = load_warning_events(root / "warnings/warnings_multi.csv")
    at_six = events.events_due(6)
    assert len(at_six) == 1
    assert at_six[0].kind == "warning"
    assert at_six[0].payload["severity"] == "mandatory"
