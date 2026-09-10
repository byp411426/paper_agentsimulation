"""Household-level population synthesis with whole-donor member preservation.

The first paper fits household marginals only.  PUMS household weights initialise
IPF, and an integerised draw copies every person record belonging to the selected
donor household.  Person-level distributions are diagnostics, not fitted claims;
joint household-person IPU is deliberately outside this module's scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ds.kernel.rng import stream_seed


@dataclass(frozen=True)
class IPFResult:
    weights: pd.Series
    converged: bool
    iterations: int
    max_abs_error: float
    marginal_errors: dict[str, float]


@dataclass(frozen=True)
class DonorTables:
    """De-identified modelling tables plus restricted source linkage."""

    households: pd.DataFrame
    persons: pd.DataFrame
    restricted_linkage: pd.DataFrame


@dataclass(frozen=True)
class SyntheticPopulation:
    households: pd.DataFrame
    persons: pd.DataFrame
    restricted_sample_provenance: pd.DataFrame
    qa: dict[str, Any]


INCOME_BINS = [
    -np.inf,
    9_999,
    14_999,
    19_999,
    24_999,
    29_999,
    34_999,
    39_999,
    44_999,
    49_999,
    59_999,
    74_999,
    99_999,
    124_999,
    149_999,
    199_999,
    np.inf,
]
INCOME_LABELS = [
    "lt_10000",
    "10000_14999",
    "15000_19999",
    "20000_24999",
    "25000_29999",
    "30000_34999",
    "35000_39999",
    "40000_44999",
    "45000_49999",
    "50000_59999",
    "60000_74999",
    "75000_99999",
    "100000_124999",
    "125000_149999",
    "150000_199999",
    "200000_plus",
]
FITTED_HOUSEHOLD_ATTRIBUTES = (
    "household_income",
    "vehicle_count",
    "household_structure",
    "household_older_adult_presence",
)


def fit_ipf(
    seed: pd.DataFrame,
    targets: dict[str, pd.Series],
    *,
    base_weights: pd.Series | None = None,
    max_iter: int = 200,
    tol: float = 1e-6,
) -> IPFResult:
    """Fit exhaustive household marginals and return an auditable result.

    Positive target mass in a category absent from the donor pool is a structural
    zero and raises immediately.  Target totals must agree across attributes.
    """
    _validate_ipf_inputs(seed, targets, base_weights)
    if base_weights is None:
        w = pd.Series(1.0, index=seed.index, dtype=float)
    else:
        w = base_weights.reindex(seed.index).astype(float).copy()

    errors: dict[str, float] = {}
    max_error = float("inf")
    for iteration in range(1, max_iter + 1):
        for attr, raw_target in targets.items():
            target = raw_target.astype(float)
            current = (
                w.groupby(seed[attr]).sum().reindex(target.index).fillna(0.0)
            )
            impossible = (target > 0) & (current <= 0)
            if impossible.any():
                cats = [str(x) for x in target.index[impossible]]
                raise ValueError(
                    f"{attr}: positive targets became unreachable for {cats}"
                )
            ratio = pd.Series(1.0, index=target.index, dtype=float)
            positive_current = current > 0
            ratio.loc[positive_current] = (
                target.loc[positive_current] / current.loc[positive_current]
            )
            mapped = seed[attr].map(ratio)
            if mapped.isna().any():
                raise ValueError(f"{attr}: target categories are not exhaustive")
            w *= mapped.astype(float)

        errors = _marginal_errors(seed, w, targets)
        max_error = max(errors.values(), default=0.0)
        if max_error <= tol:
            return IPFResult(w, True, iteration, max_error, errors)

    return IPFResult(w, False, max_iter, max_error, errors)


def ipf(
    seed: pd.DataFrame,
    targets: dict[str, pd.Series],
    max_iter: int = 200,
    tol: float = 1e-6,
    base_weights: pd.Series | None = None,
) -> pd.Series:
    """Backward-compatible weight-only wrapper around :func:`fit_ipf`."""
    return fit_ipf(
        seed,
        targets,
        base_weights=base_weights,
        max_iter=max_iter,
        tol=tol,
    ).weights


def _validate_ipf_inputs(
    seed: pd.DataFrame,
    targets: dict[str, pd.Series],
    base_weights: pd.Series | None,
) -> None:
    if seed.empty:
        raise ValueError("IPF seed must contain at least one donor household")
    if not targets:
        raise ValueError("IPF requires at least one target marginal")

    totals: dict[str, float] = {}
    for attr, raw_target in targets.items():
        if attr not in seed:
            raise ValueError(f"missing seed attribute: {attr}")
        target = raw_target.astype(float)
        if target.index.has_duplicates:
            raise ValueError(f"{attr}: target categories must be unique")
        if not np.isfinite(target.to_numpy()).all() or (target < 0).any():
            raise ValueError(f"{attr}: target counts must be finite and non-negative")

        donor_categories = set(seed[attr].dropna().unique())
        target_categories = set(target.index)
        absent = {
            category for category in target.index[target > 0]
            if category not in donor_categories
        }
        if absent:
            raise ValueError(
                f"{attr}: positive target has structural-zero categories "
                f"{sorted(map(str, absent))}"
            )
        unspecified = donor_categories - target_categories
        if unspecified:
            raise ValueError(
                f"{attr}: donor categories missing from target "
                f"{sorted(map(str, unspecified))}"
            )
        if seed[attr].isna().any():
            raise ValueError(f"{attr}: donor category contains missing values")
        totals[attr] = float(target.sum())

    reference_total = next(iter(totals.values()))
    inconsistent = {
        attr: total for attr, total in totals.items()
        if not np.isclose(total, reference_total, rtol=0.0, atol=1e-8)
    }
    if inconsistent:
        raise ValueError(f"target marginal totals disagree: {totals}")

    if base_weights is not None:
        aligned = base_weights.reindex(seed.index)
        if aligned.isna().any():
            raise ValueError("base_weights must align with every donor row")
        values = aligned.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("base_weights must be finite and strictly positive")


def _marginal_errors(
    seed: pd.DataFrame,
    weights: pd.Series,
    targets: dict[str, pd.Series],
) -> dict[str, float]:
    errors: dict[str, float] = {}
    for attr, raw_target in targets.items():
        target = raw_target.astype(float)
        fitted = (
            weights.groupby(seed[attr]).sum().reindex(target.index).fillna(0.0)
        )
        errors[attr] = float((fitted - target).abs().max())
    return errors


def effective_sample_size(weights: pd.Series) -> float:
    values = weights.to_numpy(dtype=float)
    denominator = float(np.square(values).sum())
    return float(values.sum() ** 2 / denominator) if denominator else 0.0


def sample_households(
    seed: pd.DataFrame,
    weights: pd.Series,
    n_households: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Weighted household draw with replacement (household rows only)."""
    if n_households < 0:
        raise ValueError("n_households must be non-negative")
    aligned = weights.reindex(seed.index).astype(float)
    if aligned.isna().any() or (aligned < 0).any() or aligned.sum() <= 0:
        raise ValueError("sampling weights must be aligned, non-negative, and nonzero")
    probabilities = (aligned / aligned.sum()).to_numpy()
    indices = rng.choice(
        seed.index.to_numpy(), size=n_households, replace=True, p=probabilities
    )
    return seed.loc[indices].reset_index(drop=True)


def build_donor_tables(
    housing: pd.DataFrame,
    persons: pd.DataFrame,
    *,
    serial_col: str = "SERIALNO",
    household_size_col: str = "NP",
    member_order_col: str = "SPORDER",
    relationship_col: str = "RELP",
    reference_value: int | str = 0,
) -> DonorTables:
    """Join raw PUMS records and replace source serials with internal donor IDs."""
    required_housing = {serial_col, household_size_col}
    required_person = {serial_col, member_order_col, relationship_col}
    if missing := required_housing - set(housing.columns):
        raise ValueError(f"housing columns missing: {sorted(missing)}")
    if missing := required_person - set(persons.columns):
        raise ValueError(f"person columns missing: {sorted(missing)}")
    if housing[serial_col].isna().any() or housing[serial_col].duplicated().any():
        raise ValueError("housing SERIALNO must be present and unique")

    household_serials = set(housing[serial_col])
    linked_persons = persons[persons[serial_col].isin(household_serials)].copy()
    counts = linked_persons.groupby(serial_col).size().reindex(housing[serial_col])
    if counts.isna().any():
        missing_serials = housing.loc[counts.isna().to_numpy(), serial_col].tolist()
        raise ValueError(f"households without person records: {missing_serials[:5]}")
    expected = pd.to_numeric(housing[household_size_col], errors="raise").to_numpy()
    if not np.array_equal(expected.astype(int), counts.to_numpy(dtype=int)):
        raise ValueError("NP does not match linked person count")
    if linked_persons.duplicated([serial_col, member_order_col]).any():
        raise ValueError("SPORDER must be unique within each household")
    if linked_persons[relationship_col].isna().any():
        raise ValueError("RELP must be present for every linked person")

    relationship_text = linked_persons[relationship_col].astype(str).str.strip()
    reference_mask = relationship_text.isin(
        {str(reference_value), str(reference_value).zfill(2)}
    )
    reference_counts = (
        linked_persons.assign(_reference=reference_mask)
        .groupby(serial_col)["_reference"]
        .sum()
        .reindex(housing[serial_col])
    )
    if not (reference_counts == 1).all():
        raise ValueError("each household must have exactly one reference person")

    ordered_serials = sorted(household_serials, key=str)
    mapping = {
        source: f"donor_h{position:07d}"
        for position, source in enumerate(ordered_serials, start=1)
    }
    linkage = pd.DataFrame(
        {
            "donor_id": [mapping[source] for source in ordered_serials],
            serial_col: ordered_serials,
        }
    )

    public_households = housing.copy()
    public_households.insert(
        0, "donor_id", public_households[serial_col].map(mapping)
    )
    public_households = public_households.drop(columns=[serial_col])

    public_persons = linked_persons.copy()
    public_persons.insert(
        0, "donor_id", public_persons[serial_col].map(mapping)
    )
    public_persons = public_persons.drop(columns=[serial_col])

    return DonorTables(
        households=public_households.reset_index(drop=True),
        persons=public_persons.reset_index(drop=True),
        restricted_linkage=linkage,
    )


def prepare_carr_donor_features(
    donors: DonorTables,
    *,
    income_column: str = "HINCP",
    missing_income_fill: float | None = 0,
) -> DonorTables:
    """Derive the four frozen household margins and member decision roles."""
    households = donors.households.copy()
    persons = donors.persons.copy()
    required_household = {"donor_id", "WGTP", "NP", income_column, "VEH", "HHT"}
    required_person = {"donor_id", "AGEP"}
    if missing := required_household - set(households.columns):
        raise ValueError(f"household feature columns missing: {sorted(missing)}")
    if missing := required_person - set(persons.columns):
        raise ValueError(f"person feature columns missing: {sorted(missing)}")

    income = pd.to_numeric(households[income_column], errors="coerce")
    if missing_income_fill is not None:
        income = income.fillna(missing_income_fill)
    households["household_income"] = pd.cut(
        income,
        bins=INCOME_BINS,
        labels=INCOME_LABELS,
        include_lowest=True,
    ).astype("object")
    households["household_income"] = households["household_income"].map(
        lambda value: "missing_income" if pd.isna(value) else str(value)
    )
    vehicles = pd.to_numeric(households["VEH"], errors="coerce").fillna(0).astype(int)
    households["vehicle_count"] = vehicles.map(
        lambda value: str(value) if value < 4 else "4_plus"
    )
    from ds.population.profile_validation import HHT_STRUCTURE

    structure_map = HHT_STRUCTURE
    household_type = pd.to_numeric(households["HHT"], errors="raise").astype(int)
    households["household_structure"] = household_type.map(structure_map)
    if households["household_structure"].isna().any():
        unknown = sorted(household_type[households["household_structure"].isna()].unique())
        raise ValueError(f"unsupported HHT categories: {unknown}")

    ages = pd.to_numeric(persons["AGEP"], errors="raise").astype(int)
    older = (
        persons.assign(_older=ages >= 65)
        .groupby("donor_id")["_older"]
        .any()
        .reindex(households["donor_id"])
        .fillna(False)
        .to_numpy()
    )
    households["household_older_adult_presence"] = np.where(
        older, "has_65_plus", "no_65_plus"
    )
    households["weight"] = pd.to_numeric(
        households["WGTP"], errors="raise"
    ).astype(float)
    households["household_size"] = pd.to_numeric(
        households["NP"], errors="raise"
    ).astype(int)

    persons["person_age_group"] = pd.cut(
        ages,
        bins=[-np.inf, 17, 34, 64, np.inf],
        labels=["0_17", "18_34", "35_64", "65_plus"],
    ).astype(str)
    persons["decision_capable"] = ages >= 18
    persons["decision_policy"] = np.where(
        persons["decision_capable"], "generative", "dependent"
    )
    return DonorTables(
        households=households,
        persons=persons,
        restricted_linkage=donors.restricted_linkage.copy(),
    )


def sample_whole_households(
    donors: DonorTables,
    weights: pd.Series,
    n_households: int,
    rng: np.random.Generator,
    *,
    household_prefix: str = "syn_h",
    member_order_col: str = "SPORDER",
) -> SyntheticPopulation:
    """Draw donors and atomically copy all members with fresh synthetic IDs."""
    households = donors.households
    if "donor_id" not in households or "donor_id" not in donors.persons:
        raise ValueError("donor tables must contain donor_id")
    if households["donor_id"].duplicated().any():
        raise ValueError("donor household IDs must be unique")

    aligned = weights.reindex(households.index).astype(float)
    sampled_indices = _truncate_replicate_sample(
        aligned, n_households, rng
    )
    sampled = households.loc[sampled_indices].reset_index(drop=True)
    public_households: list[dict[str, Any]] = []
    public_persons: list[dict[str, Any]] = []
    provenance: list[dict[str, str]] = []
    draw_counts: dict[str, int] = {}

    person_groups = {
        donor_id: group.sort_values(member_order_col)
        for donor_id, group in donors.persons.groupby("donor_id", sort=False)
    }
    for draw_index, (_, donor_row) in enumerate(sampled.iterrows(), start=1):
        donor_id = str(donor_row["donor_id"])
        if donor_id not in person_groups:
            raise ValueError(f"donor {donor_id} has no person records")
        synthetic_household_id = f"{household_prefix}{draw_index:07d}"
        household_record = donor_row.drop(labels=["donor_id"]).to_dict()
        household_record["synthetic_household_id"] = synthetic_household_id
        public_households.append(household_record)
        provenance.append(
            {
                "synthetic_household_id": synthetic_household_id,
                "donor_id": donor_id,
            }
        )
        draw_counts[donor_id] = draw_counts.get(donor_id, 0) + 1

        for member_index, (_, person_row) in enumerate(
            person_groups[donor_id].iterrows(), start=1
        ):
            person_record = person_row.drop(labels=["donor_id"]).to_dict()
            person_record["synthetic_household_id"] = synthetic_household_id
            person_record["resident_id"] = (
                f"{synthetic_household_id}_r{member_index:03d}"
            )
            public_persons.append(person_record)

    counts = list(draw_counts.values())
    qa = {
        "n_households": n_households,
        "n_persons": len(public_persons),
        "unique_donors": len(draw_counts),
        "repeated_donor_fraction": (
            1.0 - len(draw_counts) / n_households if n_households else 0.0
        ),
        "max_donor_copies": max(counts, default=0),
        "fractional_weight_ess": effective_sample_size(aligned),
        "integerization_method": "truncate_replicate_sample",
    }
    return SyntheticPopulation(
        households=pd.DataFrame(public_households),
        persons=pd.DataFrame(public_persons),
        restricted_sample_provenance=pd.DataFrame(provenance),
        qa=qa,
    )


def _truncate_replicate_sample(
    weights: pd.Series,
    target_n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Low-variance integerisation of fractional household weights.

    Weights are first scaled to ``target_n``. Integer parts are replicated;
    remaining households are drawn without replacement from fractional
    remainders. This preserves the total exactly and avoids the extra variance of
    drawing the entire population multinomially with replacement.
    """
    if target_n < 0:
        raise ValueError("target_n must be non-negative")
    if weights.isna().any() or (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("integerization weights must be non-negative and nonzero")
    scaled = weights.astype(float) * (target_n / float(weights.sum()))
    integer = np.floor(scaled.to_numpy()).astype(int)
    selected = np.repeat(weights.index.to_numpy(), integer)
    remaining = target_n - len(selected)
    if remaining:
        fractions = scaled.to_numpy() - integer
        eligible = np.flatnonzero(fractions > 1e-12)
        if len(eligible) < remaining:
            raise RuntimeError(
                "not enough positive fractional weights for TRS remainder"
            )
        probabilities = fractions[eligible] / fractions[eligible].sum()
        extra_positions = rng.choice(
            eligible,
            size=remaining,
            replace=False,
            p=probabilities,
        )
        selected = np.concatenate(
            [selected, weights.index.to_numpy()[extra_positions]]
        )
    rng.shuffle(selected)
    return selected


def controlled_two_adult_cohort(
    population: SyntheticPopulation,
    *,
    age_col: str = "AGEP",
) -> SyntheticPopulation:
    """Select synthetic households with exactly two adult members.

    Both adults remain generative decision members; younger members remain
    dependent execution members. Functional limitation columns are preserved
    and never used here to cancel adult decision capability.
    """
    persons = population.persons.copy()
    ages = pd.to_numeric(persons[age_col], errors="raise")
    adult_counts = (
        persons.assign(_adult=ages >= 18)
        .groupby("synthetic_household_id")["_adult"]
        .sum()
    )
    selected_ids = set(adult_counts[adult_counts == 2].index)
    households = population.households[
        population.households["synthetic_household_id"].isin(selected_ids)
    ].copy()
    selected_persons = persons[
        persons["synthetic_household_id"].isin(selected_ids)
    ].copy()
    selected_ages = pd.to_numeric(selected_persons[age_col], errors="raise")
    selected_persons["decision_capable"] = selected_ages >= 18
    selected_persons["decision_policy"] = np.where(
        selected_persons["decision_capable"], "generative", "dependent"
    )
    provenance = population.restricted_sample_provenance[
        population.restricted_sample_provenance[
            "synthetic_household_id"
        ].isin(selected_ids)
    ].copy()
    qa = dict(population.qa)
    qa.update(
        {
            "cohort": "exactly_two_adults",
            "cohort_households": len(households),
            "cohort_persons": len(selected_persons),
        }
    )
    return SyntheticPopulation(households, selected_persons, provenance, qa)


def synthesize_by_tract(
    donors: DonorTables,
    acs_marginals: pd.DataFrame,
    *,
    target_n: int,
    run_seed: int,
    attributes: tuple[str, ...] = FITTED_HOUSEHOLD_ATTRIBUTES,
    geoid_col: str = "geoid",
) -> SyntheticPopulation:
    """Fit the frozen household margins per tract and copy whole donors.

    ``target_n`` is allocated across tracts in proportion to the ACS household
    totals using a deterministic largest-remainder allocation.
    """
    required = {geoid_col, "attribute", "category", "estimate"}
    if missing := required - set(acs_marginals.columns):
        raise ValueError(f"ACS marginal columns missing: {sorted(missing)}")
    if target_n < 0:
        raise ValueError("target_n must be non-negative")
    household_rows = acs_marginals[
        acs_marginals["attribute"].isin(attributes)
    ].copy()
    if household_rows.empty:
        raise ValueError("no fitted household attributes found in ACS marginals")
    household_rows["category"] = household_rows["category"].astype(str)
    household_rows["estimate"] = pd.to_numeric(
        household_rows["estimate"], errors="raise"
    ).astype(float)

    tract_totals: dict[str, float] = {}
    for geoid, tract_rows in household_rows.groupby(geoid_col, sort=True):
        attribute_totals = tract_rows.groupby("attribute")["estimate"].sum()
        if set(attribute_totals.index) != set(attributes):
            missing = set(attributes) - set(attribute_totals.index)
            raise ValueError(f"{geoid}: fitted attributes missing: {sorted(missing)}")
        if not np.allclose(
            attribute_totals.to_numpy(),
            attribute_totals.iloc[0],
            rtol=0.0,
            atol=1e-8,
        ):
            raise ValueError(
                f"{geoid}: household marginal totals disagree "
                f"{attribute_totals.to_dict()}"
            )
        tract_totals[str(geoid)] = float(attribute_totals.iloc[0])

    allocations = _largest_remainder_allocation(tract_totals, target_n)
    public_households: list[pd.DataFrame] = []
    public_persons: list[pd.DataFrame] = []
    provenance: list[pd.DataFrame] = []
    tract_qa: dict[str, Any] = {}
    donor_households = donors.households.copy()
    for attr in attributes:
        donor_households[attr] = donor_households[attr].astype(str)

    for tract_index, geoid in enumerate(sorted(allocations), start=1):
        n_households = allocations[geoid]
        if n_households == 0:
            continue
        tract_rows = household_rows[
            household_rows[geoid_col].astype(str) == geoid
        ]
        targets: dict[str, pd.Series] = {}
        for attr in attributes:
            rows = tract_rows[tract_rows["attribute"] == attr]
            raw = rows.set_index("category")["estimate"].astype(float)
            targets[attr] = raw * (n_households / raw.sum())

        result = fit_ipf(
            donor_households,
            targets,
            base_weights=donor_households["weight"],
            max_iter=1000,
            tol=1e-7,
        )
        if not result.converged:
            raise RuntimeError(
                f"{geoid}: IPF did not converge; max error "
                f"{result.max_abs_error:.6g}"
            )
        rng = np.random.default_rng(
            stream_seed(
                run_seed,
                "population",
                entity_id=geoid,
            )
        )
        tract_donors = DonorTables(
            donor_households,
            donors.persons,
            donors.restricted_linkage,
        )
        sample = sample_whole_households(
            tract_donors,
            result.weights,
            n_households,
            rng,
            household_prefix=f"syn_t{tract_index:03d}_h",
        )
        sample.households.insert(0, geoid_col, geoid)
        sample.persons.insert(0, geoid_col, geoid)
        sample.restricted_sample_provenance.insert(0, geoid_col, geoid)
        public_households.append(sample.households)
        public_persons.append(sample.persons)
        provenance.append(sample.restricted_sample_provenance)

        integer_errors = _integerized_marginal_errors(
            sample.households, targets
        )
        tract_qa[geoid] = {
            "n_households": n_households,
            "ipf_converged": result.converged,
            "ipf_iterations": result.iterations,
            "fractional_max_abs_error": result.max_abs_error,
            "fractional_errors": result.marginal_errors,
            "integerized_errors": integer_errors,
            "fractional_weight_ess": effective_sample_size(result.weights),
            "unique_donors": sample.qa["unique_donors"],
            "repeated_donor_fraction": sample.qa["repeated_donor_fraction"],
            "max_donor_copies": sample.qa["max_donor_copies"],
            "integerization_method": sample.qa["integerization_method"],
        }

    combined_households = (
        pd.concat(public_households, ignore_index=True)
        if public_households else pd.DataFrame()
    )
    combined_persons = (
        pd.concat(public_persons, ignore_index=True)
        if public_persons else pd.DataFrame()
    )
    combined_provenance = (
        pd.concat(provenance, ignore_index=True)
        if provenance else pd.DataFrame()
    )
    person_diagnostics = _person_age_diagnostics(
        combined_persons,
        acs_marginals,
        geoid_col=geoid_col,
    )
    return SyntheticPopulation(
        households=combined_households,
        persons=combined_persons,
        restricted_sample_provenance=combined_provenance,
        qa={
            "n_households": len(combined_households),
            "n_persons": len(combined_persons),
            "n_tracts": len(tract_qa),
            "tracts": tract_qa,
            "fitted_household_attributes": list(attributes),
            "person_level_fit": False,
            "person_age_diagnostic": person_diagnostics,
        },
    )


def _largest_remainder_allocation(
    totals: dict[str, float],
    target_n: int,
) -> dict[str, int]:
    if not totals or sum(totals.values()) <= 0:
        raise ValueError("tract household totals must be positive")
    grand_total = sum(totals.values())
    exact = {
        geoid: target_n * total / grand_total
        for geoid, total in totals.items()
    }
    allocated = {
        geoid: int(np.floor(value)) for geoid, value in exact.items()
    }
    remainder = target_n - sum(allocated.values())
    order = sorted(
        totals,
        key=lambda geoid: (-(exact[geoid] - allocated[geoid]), geoid),
    )
    for geoid in order[:remainder]:
        allocated[geoid] += 1
    return allocated


def _integerized_marginal_errors(
    sampled_households: pd.DataFrame,
    targets: dict[str, pd.Series],
) -> dict[str, float]:
    errors: dict[str, float] = {}
    for attr, target in targets.items():
        observed = (
            sampled_households[attr]
            .astype(str)
            .value_counts()
            .reindex(target.index.astype(str))
            .fillna(0.0)
        )
        errors[attr] = float((observed - target).abs().max())
    return errors


def _person_age_diagnostics(
    persons: pd.DataFrame,
    acs_marginals: pd.DataFrame,
    *,
    geoid_col: str,
) -> dict[str, Any]:
    """Compare, but never fit, tract person-age shares."""
    if persons.empty or "person_age_group" not in persons:
        return {"used_in_fit": False, "tracts": {}}
    target_rows = acs_marginals[
        acs_marginals["attribute"] == "person_age_group"
    ].copy()
    if target_rows.empty:
        return {"used_in_fit": False, "tracts": {}}
    target_rows["category"] = target_rows["category"].astype(str)
    target_rows["estimate"] = pd.to_numeric(
        target_rows["estimate"], errors="raise"
    ).astype(float)
    diagnostics: dict[str, Any] = {}
    for geoid, observed_rows in persons.groupby(geoid_col, sort=True):
        targets = target_rows[
            target_rows[geoid_col].astype(str) == str(geoid)
        ].set_index("category")["estimate"]
        if targets.empty or targets.sum() <= 0:
            continue
        observed = (
            observed_rows["person_age_group"]
            .astype(str)
            .value_counts()
            .reindex(targets.index)
            .fillna(0.0)
        )
        observed_share = observed / max(float(observed.sum()), 1.0)
        target_share = targets / float(targets.sum())
        errors = (observed_share - target_share) * 100.0
        diagnostics[str(geoid)] = {
            "n_persons": len(observed_rows),
            "observed_share": observed_share.to_dict(),
            "target_share": target_share.to_dict(),
            "percentage_point_error": errors.to_dict(),
            "mean_absolute_percentage_point_error": float(errors.abs().mean()),
            "max_absolute_percentage_point_error": float(errors.abs().max()),
        }
    return {"used_in_fit": False, "tracts": diagnostics}


def run_ipf(
    pums: pd.DataFrame,
    acs_marginals: pd.DataFrame,
    target_n: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """Compatibility entry point, now refusing to fake a fitted population.

    The existing ``pums.csv`` contains household rows only, so this function
    cannot satisfy the whole-donor household-person protocol.  Formal Carr-S
    code must build :class:`DonorTables`, fit each tract with :func:`fit_ipf`,
    and call :func:`sample_whole_households`.
    """
    del pums, acs_marginals, target_n, seed
    raise NotImplementedError(
        "run_ipf household-only compatibility loader is retired; build donor "
        "household/person tables and use fit_ipf + sample_whole_households"
    )
