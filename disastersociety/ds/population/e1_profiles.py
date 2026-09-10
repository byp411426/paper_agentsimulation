"""Carr E1 v2 empirical profile assembly (W3 contract).

Combines PUMS whole-household static structure with independently imputed
Carr train household/person traits.  Focal/coordinator baselines are fixed;
Q34.4 never selects them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from ds.kernel.rng import stream_rng
from ds.population.profile_validation import validate_e1_profiles


@dataclass(frozen=True)
class MemberEmpiricalProfile:
    resident_id: str
    household_id: str
    age: int
    relationship: str
    pums_static: dict[str, Any]
    functional_limitations: dict[str, bool | None]
    veteran_service_connected_rating: int | None
    decision_capable: bool
    decision_policy: Literal["generative", "rule", "dependent"]
    needs_execution_assistance: bool
    latent_traits: dict[str, float | bool | int | None]
    source_by_field: dict[str, str]


@dataclass(frozen=True)
class HouseholdEmpiricalProfile:
    household_id: str
    shared_attributes: dict[str, Any]
    member_profiles: tuple[MemberEmpiricalProfile, ...]
    decision_resident_ids: tuple[str, ...]
    nondecision_member_ids: tuple[str, ...]
    care_recipient_ids: tuple[str, ...]
    focal_resident_id: str
    coordinator_id: str
    source_by_field: dict[str, str]


@dataclass(frozen=True)
class ProfileAssemblyResult:
    households: tuple[HouseholdEmpiricalProfile, ...]
    qa: dict[str, Any]
    restricted_linkage: pd.DataFrame


INCOME_FINE_TO_BAND = {
    "lt_10000": "lt_25k",
    "10000_14999": "lt_25k",
    "15000_19999": "lt_25k",
    "20000_24999": "lt_25k",
    "25000_29999": "25_49k",
    "30000_34999": "25_49k",
    "35000_39999": "25_49k",
    "40000_44999": "25_49k",
    "45000_49999": "25_49k",
    "50000_59999": "50_99k",
    "60000_74999": "50_99k",
    "75000_99999": "50_99k",
    "100000_124999": "100k_plus",
    "125000_149999": "100k_plus",
    "150000_199999": "100k_plus",
    "200000_plus": "100k_plus",
    "missing_income": "missing",
}

DRAT_CODE_TO_RATING = {
    1: 0,
    2: 15,
    3: 35,
    4: 55,
    5: 85,
    6: None,
}


def to_e1_matching_bands(
    *,
    age: int | None = None,
    household_size: int | None = None,
    vehicle_count: int | None = None,
    household_income: str | None = None,
) -> dict[str, str | None]:
    """Canonical E1 matching bands shared by PUMS and trait-donor sides."""
    if age is None:
        age_band = None
    elif 18 <= age <= 24:
        age_band = "18_24"
    elif 25 <= age <= 34:
        age_band = "25_34"
    elif 35 <= age <= 44:
        age_band = "35_44"
    elif 45 <= age <= 54:
        age_band = "45_54"
    elif 55 <= age <= 64:
        age_band = "55_64"
    elif 65 <= age <= 74:
        age_band = "65_74"
    elif 75 <= age <= 84:
        age_band = "75_84"
    elif age >= 85:
        age_band = "85_plus"
    else:
        age_band = None
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
        INCOME_FINE_TO_BAND.get(household_income)
        if household_income is not None
        else None
    )
    return {
        "age_band": age_band,
        "household_band": household_band,
        "vehicle_band": vehicle_band,
        "income_band": income_band,
    }


def _pick_tier_candidates(
    trait_frame: pd.DataFrame,
    *,
    bands: dict[str, str | None],
    tier: int,
    person: bool,
) -> pd.DataFrame:
    """Return trait donors matching tier Pn/Hn, sorted by donor id."""
    candidates = trait_frame
    keys = [
        "age_band",
        "household_band",
        "vehicle_band",
        "income_band",
    ]
    if person:
        required = {
            0: ["age_band", "household_band", "vehicle_band", "income_band"],
            1: ["age_band", "household_band", "vehicle_band"],
            2: ["age_band", "household_band"],
            3: ["age_band"],
            4: [],
        }[tier]
    else:
        required = {
            0: ["household_band", "vehicle_band", "income_band"],
            1: ["household_band", "vehicle_band"],
            2: ["household_band"],
            3: [],
        }[tier]
    for key in required:
        candidates = candidates[candidates[key] == bands.get(key)]
    return candidates.sort_values("trait_donor_id").reset_index(drop=True)


def assemble_e1_profiles(
    *,
    households: pd.DataFrame,
    persons: pd.DataFrame,
    household_traits: pd.DataFrame,
    person_traits: pd.DataFrame,
    donor_persons: pd.DataFrame,
    profile_seed: int,
    pums_household_linkage: pd.DataFrame,
) -> ProfileAssemblyResult:
    """Assemble empirical profiles for every synthetic household member."""
    profiles: list[HouseholdEmpiricalProfile] = []
    linkage_rows: list[dict] = []
    member_trait_linkage: dict[str, tuple[str, str]] = {}
    qa_household_tiers = {f"H{tier}": 0 for tier in range(4)}
    qa_person_tiers = {f"P{tier}": 0 for tier in range(5)}
    qa_person_reuse = 0
    donor_usage: dict[str, int] = {}
    person_trait_index = person_traits.set_index("trait_donor_id")
    household_trait_index = household_traits.set_index("trait_donor_id")

    households_by_id = households.set_index("synthetic_household_id")
    persons_by_household = {
        household_id: group.sort_values("SPORDER")
        for household_id, group in persons.groupby("synthetic_household_id")
    }
    household_linkage_index = pums_household_linkage.set_index(
        "synthetic_household_id"
    )["donor_id"]

    for household_id in sorted(households_by_id.index):
        household_row = households_by_id.loc[household_id]
        member_rows = persons_by_household[household_id]
        household_size = int(household_row["household_size"])
        if household_size != len(member_rows):
            raise ValueError(f"{household_id}: household_size disagrees with member count")
        raw_vehicle = household_row["vehicle_count"]
        vehicle_count = (
            4 if str(raw_vehicle).strip() == "4_plus" else int(raw_vehicle)
        )
        income_fine = str(household_row["household_income"])
        bands = to_e1_matching_bands(
            household_size=household_size,
            vehicle_count=vehicle_count,
            household_income=income_fine,
        )

        # Household trait donor: H0 -> H3 fallback.
        household_match = None
        household_tier = None
        for tier in range(4):
            candidates = _pick_tier_candidates(
                household_traits, bands=bands, tier=tier, person=False
            )
            if len(candidates):
                rng = stream_rng(
                    profile_seed,
                    "e1_household_trait_match",
                    entity_id=household_id,
                )
                household_match = candidates["trait_donor_id"].iloc[
                    rng.randrange(len(candidates))
                ]
                household_tier = f"H{tier}"
                break
        if household_match is None:
            raise RuntimeError(f"no household trait donor for {household_id}")
        qa_household_tiers[household_tier] += 1
        household_trait = household_trait_index.loc[household_match]

        # Person trait donors: P0 -> P4 fallback; no replacement inside household.
        member_profiles: list[MemberEmpiricalProfile] = []
        used_person_donors: set[str] = set()
        for _, member in member_rows.iterrows():
            resident_id = str(member["resident_id"])
            age = int(member["AGEP"])
            member_bands = to_e1_matching_bands(
                age=age,
                household_size=household_size,
                vehicle_count=vehicle_count,
                household_income=income_fine,
            )
            person_match = None
            person_tier = None
            for tier in range(5):
                candidates = _pick_tier_candidates(
                    person_traits, bands=member_bands, tier=tier, person=True
                )
                unused = candidates[
                    ~candidates["trait_donor_id"].isin(used_person_donors)
                ]
                pool = unused if len(unused) else candidates
                if len(pool):
                    rng = stream_rng(
                        profile_seed,
                        "e1_person_trait_match",
                        entity_id=resident_id,
                    )
                    person_match = pool["trait_donor_id"].iloc[
                        rng.randrange(len(pool))
                    ]
                    person_tier = f"P{tier}"
                    if len(unused) == 0:
                        qa_person_reuse += 1
                    break
            if person_match is None:
                raise RuntimeError(f"no person trait donor for {resident_id}")
            qa_person_tiers[person_tier] += 1
            used_person_donors.add(person_match)
            member_trait_linkage[resident_id] = (person_match, person_tier)
            donor_usage[person_match] = donor_usage.get(person_match, 0) + 1
            person_trait = person_trait_index.loc[person_match]

            drat_code = member["DRAT"]
            drat_value = (
                DRAT_CODE_TO_RATING.get(int(drat_code))
                if pd.notna(drat_code)
                else None
            )
            functional = {
                field: (
                    bool(int(member[field]) == 1)
                    if pd.notna(member[field])
                    else None
                )
                for field in ("DEAR", "DEYE", "DREM", "DPHY", "DOUT", "DDRS")
            }
            needs_execution_assistance = age < 18 or any(
                functional.get(field)
                for field in ("DPHY", "DDRS", "DOUT")
            )
            pums_static = {
                "sex": str(member["SEX_label"]) if pd.notna(member["SEX_label"]) else None,
                "education": (
                    str(member["SCHL_label"])
                    if pd.notna(member["SCHL_label"])
                    else None
                ),
                "employment": (
                    str(member["ESR_label"])
                    if pd.notna(member["ESR_label"])
                    else None
                ),
                "weeks_worked": (
                    str(member["WKW_label"])
                    if pd.notna(member["WKW_label"])
                    else None
                ),
                "hours_worked": (
                    int(member["WKHP"])
                    if pd.notna(member["WKHP"])
                    else None
                ),
                "commute_mode": (
                    str(member["JWTR_label"])
                    if pd.notna(member["JWTR_label"])
                    else None
                ),
                "commute_minutes": (
                    int(member["JWMNP"])
                    if pd.notna(member["JWMNP"])
                    else None
                ),
                "relationship": (
                    str(member["RELP_label"])
                    if pd.notna(member["RELP_label"])
                    else None
                ),
            }
            latent_traits = {
                column: (
                    None
                    if pd.isna(person_trait[column])
                    else (
                        bool(person_trait[column])
                        if isinstance(person_trait[column], (np.bool_, bool))
                        else (
                            float(person_trait[column])
                            if isinstance(person_trait[column], (np.floating, float))
                            else person_trait[column]
                        )
                    )
                )
                for column in person_traits.columns
                if column != "trait_donor_id"
            }
            member_profiles.append(
                MemberEmpiricalProfile(
                    resident_id=resident_id,
                    household_id=household_id,
                    age=age,
                    relationship=(
                        str(member["RELP_label"])
                        if pd.notna(member["RELP_label"])
                        else str(member["RELP"])
                    ),
                    pums_static=pums_static,
                    functional_limitations=functional,
                    veteran_service_connected_rating=drat_value,
                    decision_capable=age >= 18,
                    decision_policy=(
                        "generative" if age >= 18 else "dependent"
                    ),
                    needs_execution_assistance=needs_execution_assistance,
                    latent_traits=latent_traits,
                    source_by_field={
                        **{
                            key: "pums_person_observed"
                            for key in pums_static
                        },
                        **{
                            key: "carr_train_person_hotdeck_retrospective"
                            for key in latent_traits
                        },
                        "decision_capable": "derived",
                        "decision_policy": "derived",
                        "needs_execution_assistance": "derived",
                    },
                )
            )

        adults = [
            member for member in member_profiles if member.decision_capable
        ]
        if not adults:
            raise RuntimeError(f"no adult member in {household_id}")
        coordinator_candidates = [
            member
            for member in adults
            if member.pums_static.get("relationship", "").lower()
            in ("reference person", "reference person ")
        ]
        if not coordinator_candidates:
            coordinator_candidates = adults
        coordinator = min(coordinator_candidates, key=lambda m: m.resident_id)
        focal = coordinator
        shared_attributes = {
            "household_income_band": bands["income_band"],
            "household_band": bands["household_band"],
            "vehicle_band": bands["vehicle_band"],
            "vehicle_count": vehicle_count,
            "household_structure": (
                str(household_row["household_structure"])
                if pd.notna(household_row["household_structure"])
                else None
            ),
            "tenure": (
                str(household_row["TEN_label"])
                if pd.notna(household_row["TEN_label"])
                else None
            ),
            "building": (
                str(household_row["BLD_label"])
                if pd.notna(household_row["BLD_label"])
                else None
            ),
            "internet_access": (
                str(household_row["ACCESS_label"])
                if pd.notna(household_row["ACCESS_label"])
                else None
            ),
            "pet_owned": (
                bool(household_trait["pet_owned"])
                if pd.notna(household_trait["pet_owned"])
                else None
            ),
            "livestock_owned": (
                bool(household_trait["livestock_owned"])
                if pd.notna(household_trait["livestock_owned"])
                else None
            ),
        }
        profiles.append(
            HouseholdEmpiricalProfile(
                household_id=household_id,
                shared_attributes=shared_attributes,
                member_profiles=tuple(member_profiles),
                decision_resident_ids=tuple(
                    member.resident_id for member in adults
                ),
                nondecision_member_ids=tuple(
                    member.resident_id
                    for member in member_profiles
                    if not member.decision_capable
                ),
                care_recipient_ids=tuple(
                    member.resident_id
                    for member in member_profiles
                    if member.needs_execution_assistance
                ),
                focal_resident_id=focal.resident_id,
                coordinator_id=coordinator.resident_id,
                source_by_field={
                    **{
                        key: "pums_household_observed"
                        for key in (
                            "household_income_band",
                            "household_band",
                            "vehicle_band",
                            "vehicle_count",
                            "household_structure",
                            "tenure",
                            "building",
                            "internet_access",
                        )
                    },
                    "pet_owned": "carr_train_household_hotdeck_retrospective",
                    "livestock_owned": "carr_train_household_hotdeck_retrospective",
                    "coordinator_id": "derived",
                    "focal_resident_id": "derived",
                },
            )
        )

        donor_household_id = str(household_linkage_index[household_id])
        linkage_rows.append(
            {
                "household_id": household_id,
                "pums_household_donor_id": donor_household_id,
                "household_trait_donor_id": household_match,
                "household_match_level": household_tier,
            }
        )
        for member in member_profiles:
            donor_row = donor_persons[
                (donor_persons["donor_id"] == donor_household_id)
                & (donor_persons["SPORDER"].astype(int) == int(
                    persons_by_household[household_id]
                    .set_index("resident_id")
                    .loc[member.resident_id, "SPORDER"]
                ))
            ]
            linkage_rows.append(
                {
                    "resident_id": member.resident_id,
                    "pums_person_donor_id": (
                        str(donor_row.iloc[0]["donor_id"])
                        if len(donor_row)
                        else donor_household_id
                    ),
                    "pums_person_sporder": (
                        int(donor_row.iloc[0]["SPORDER"])
                        if len(donor_row)
                        else None
                    ),
                    "person_trait_donor_id": (
                        member_trait_linkage[member.resident_id][0]
                    ),
                    "person_match_level": member_trait_linkage[member.resident_id][1],
                }
            )

    validate_e1_profiles([asdict(profile) for profile in profiles])
    linkage = pd.DataFrame(linkage_rows)
    qa = {
        "n_households": len(profiles),
        "n_members": sum(len(p.member_profiles) for p in profiles),
        "household_match_tiers": qa_household_tiers,
        "person_match_tiers": qa_person_tiers,
        "person_donor_reuse_count": qa_person_reuse,
        "person_donor_usage": dict(
            sorted(donor_usage.items(), key=lambda item: -item[1])[:10]
        ),
        "profile_seed": profile_seed,
        "method_name": (
            "PUMS whole-household static structure + Carr-informed "
            "independently imputed household/person traits"
        ),
    }
    return ProfileAssemblyResult(
        households=tuple(profiles),
        qa=qa,
        restricted_linkage=linkage,
    )
