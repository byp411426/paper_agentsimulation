"""Carr E1 v2 profile assembly tests (W3 contract)."""

from __future__ import annotations

import pandas as pd
import pytest

from ds.population.e1_profiles import (
    assemble_e1_profiles,
    to_e1_matching_bands,
)


def _households():
    return pd.DataFrame(
        {
            "synthetic_household_id": ["syn_t001_h0000001", "syn_t001_h0000002"],
            "household_size": [2, 3],
            "vehicle_count": [1, 0],
            "household_income": ["40000_44999", "missing_income"],
            "household_structure": ["married_couple", "nonfamily_living_alone"],
            "TEN_label": ["Owned with mortgage or loan (include home equity loans)", "Rented"],
            "BLD_label": ["One-family house detached", "2 Apartments"],
            "ACCESS_label": [
                "Yes, by paying a cell phone company or Internet service provider",
                "No access to the Internet at this house, apartment, or mobile home",
            ],
        }
    )


def _persons():
    return pd.DataFrame(
        [
            {
                "synthetic_household_id": "syn_t001_h0000001",
                "resident_id": "syn_t001_h0000001_r001",
                "SPORDER": 1,
                "AGEP": 45,
                "SEX_label": "Male",
                "RELP": 0,
                "RELP_label": "Reference person",
                "SCHL_label": "Bachelor's degree",
                "ESR_label": "Civilian employed, at work",
                "WKW_label": "50 to 52 weeks worked during past 12 months",
                "WKHP": 40,
                "JWTR_label": "Car, truck, or van",
                "JWMNP": 20,
                "DEAR": 2,
                "DEYE": 2,
                "DREM": 2,
                "DPHY": 1,
                "DOUT": 2,
                "DDRS": 2,
                "DRAT": None,
            },
            {
                "synthetic_household_id": "syn_t001_h0000001",
                "resident_id": "syn_t001_h0000001_r002",
                "SPORDER": 2,
                "AGEP": 10,
                "SEX_label": "Female",
                "RELP": 3,
                "RELP_label": "Adopted son or daughter",
                "SCHL_label": "Grade 4",
                "ESR_label": None,
                "WKW_label": None,
                "WKHP": None,
                "JWTR_label": None,
                "JWMNP": None,
                "DEAR": 2,
                "DEYE": 2,
                "DREM": 2,
                "DPHY": 2,
                "DOUT": None,
                "DDRS": 2,
                "DRAT": None,
            },
            {
                "synthetic_household_id": "syn_t001_h0000002",
                "resident_id": "syn_t001_h0000002_r001",
                "SPORDER": 1,
                "AGEP": 80,
                "SEX_label": "Female",
                "RELP": 0,
                "RELP_label": "Reference person",
                "SCHL_label": "Regular high school diploma",
                "ESR_label": "Not in labor force",
                "WKW_label": None,
                "WKHP": None,
                "JWTR_label": None,
                "JWMNP": None,
                "DEAR": 1,
                "DEYE": 2,
                "DREM": 2,
                "DPHY": 2,
                "DOUT": 1,
                "DDRS": 1,
                "DRAT": None,
            },
        ]
    )


def _trait_donors():
    household = pd.DataFrame(
        [
            {
                "trait_donor_id": f"carr_hh_donor_{i:04d}",
                "pet_owned": True,
                "livestock_owned": False,
                "age_band": "45_54",
                "household_band": "2",
                "vehicle_band": "1",
                "income_band": "25_49k",
            }
            for i in range(1, 21)
        ]
    )
    person = pd.DataFrame(
        [
            {
                "trait_donor_id": f"carr_p_donor_{i:04d}",
                "hazard_worry": 0.5,
                "evacuation_friction": 0.25,
                "home_person_threat": 0.75,
                "infrastructure_rescue": 0.5,
                "property_security": 0.0,
                "work_obligation": 1.0,
                "trust_item_1": 0.5,
                "trust_item_2": 0.5,
                "trust_item_3": 0.5,
                "trust_item_4": 0.5,
                "trust_item_5": 0.5,
                "trust_item_6": 0.5,
                "trust_item_7": 0.5,
                "trust_item_8": 0.5,
                "trust_item_9": 0.5,
                "trust_item_10": 0.5,
                "trust_item_11": 0.5,
                "trust_item_12": 0.5,
                "general_trust": 1.0,
                "helping_tendency": 0.8,
                "prior_evacuation_count_capped": 1,
                "prior_evacuation_topcoded": False,
                "decision_participation_propensity": 0.75,
                "age_band": "45_54",
                "household_band": "2",
                "vehicle_band": "1",
                "income_band": "25_49k",
            }
            for i in range(1, 41)
        ]
    )
    return household, person


def _linkages():
    household_linkage = pd.DataFrame(
        {
            "synthetic_household_id": ["syn_t001_h0000001", "syn_t001_h0000002"],
            "donor_id": ["donor_h0000001", "donor_h0000002"],
        }
    )
    donor_persons = pd.DataFrame(
        [
            {"donor_id": "donor_h0000001", "SPORDER": 1},
            {"donor_id": "donor_h0000001", "SPORDER": 2},
            {"donor_id": "donor_h0000002", "SPORDER": 1},
        ]
    )
    return household_linkage, donor_persons


def test_matching_bands_pums_side():
    bands = to_e1_matching_bands(
        age=45, household_size=2, vehicle_count=1, household_income="40000_44999"
    )
    assert bands == {
        "age_band": "45_54",
        "household_band": "2",
        "vehicle_band": "1",
        "income_band": "25_49k",
    }
    assert to_e1_matching_bands(
        age=10, household_size=3, vehicle_count=4, household_income="missing_income"
    )["income_band"] == "missing"


def test_profiles_cover_all_members_and_roles():
    household_linkage, donor_persons = _linkages()
    household_traits, person_traits = _trait_donors()
    result = assemble_e1_profiles(
        households=_households(),
        persons=_persons(),
        household_traits=household_traits,
        person_traits=person_traits,
        donor_persons=donor_persons,
        pums_household_linkage=household_linkage,
        profile_seed=4201,
    )
    assert len(result.households) == 2
    h1 = result.households[0]
    assert len(h1.member_profiles) == 2
    assert h1.coordinator_id == "syn_t001_h0000001_r001"
    assert h1.focal_resident_id == h1.coordinator_id
    assert h1.decision_resident_ids == ("syn_t001_h0000001_r001",)
    assert h1.nondecision_member_ids == ("syn_t001_h0000001_r002",)
    # Adult r001 has DPHY=1 (execution assistance) and child r002 needs care.
    assert h1.care_recipient_ids == (
        "syn_t001_h0000001_r001",
        "syn_t001_h0000001_r002",
    )
    assert h1.shared_attributes["pet_owned"] is True

    h2 = result.households[1]
    assert h2.coordinator_id == "syn_t001_h0000002_r001"
    adult = h2.member_profiles[0]
    assert adult.decision_capable is True
    assert adult.needs_execution_assistance is True  # DOUT/DDRS yes
    assert adult.decision_policy == "generative"
    assert "carr_train_person_hotdeck_retrospective" in adult.source_by_field.values()
    assert "pums_person_observed" in adult.source_by_field.values()


def test_profiles_deterministic():
    household_linkage, donor_persons = _linkages()
    household_traits, person_traits = _trait_donors()
    kwargs = dict(
        households=_households(),
        persons=_persons(),
        household_traits=household_traits,
        person_traits=person_traits,
        donor_persons=donor_persons,
        pums_household_linkage=household_linkage,
        profile_seed=4201,
    )
    first = assemble_e1_profiles(**kwargs)
    second = assemble_e1_profiles(**kwargs)
    assert first.households == second.households
    assert first.qa == second.qa


def test_qa_reports_tiers_and_reuse():
    household_linkage, donor_persons = _linkages()
    household_traits, person_traits = _trait_donors()
    result = assemble_e1_profiles(
        households=_households(),
        persons=_persons(),
        household_traits=household_traits,
        person_traits=person_traits,
        donor_persons=donor_persons,
        pums_household_linkage=household_linkage,
        profile_seed=4201,
    )
    assert sum(result.qa["household_match_tiers"].values()) == 2
    assert sum(result.qa["person_match_tiers"].values()) == 3
    assert result.qa["person_donor_reuse_count"] >= 0
    assert "PUMS whole-household static structure" in result.qa["method_name"]
