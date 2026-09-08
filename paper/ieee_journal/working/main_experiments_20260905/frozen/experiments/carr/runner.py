"""Active Carr-S controlled mechanism runner using the common kernel.

The configured backend may be the transparent zero-cost mock or a declared
publication-facing model. Controlled scenarios are not historical road-closure
reconstructions, and every output carries its configured evidence-status label.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ds.agents.carr import (
    CarrResident,
    MechanismFlags,
    carr_controlled_policy,
)
from ds.agents.state import StaticAttrs
from ds.eventpack import ListEventSource, load_eventpack, load_warning_events
from ds.eval.carr_protocol import file_sha256
from ds.households import (
    DependentMemberState,
    Household,
    VehicleResource,
)
from ds.interaction.delivery import (
    DeterministicDeliveryModel,
    FixedProbabilityDeliveryModel,
)
from ds.interaction.engine import InteractionEngine
from ds.interaction.messages import Event
from ds.kernel.engine import Engine
from ds.kernel.logger import RunLogger
from ds.kernel.rng import stream_seed
from ds.llm.backends import MockBackend
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from ds.provenance import write_provenance
from ds.world.carr import CarrWorld, RouteState


CONDITIONS = (
    "full",
    "full_minus_memory",
    "full_minus_feedback",
    "full_minus_planning",
    "full_minus_interaction",
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS_CONFIG = PROJECT_ROOT / "configs/models.yaml"
PRIMARY_MECHANISM_METRICS = {
    "memory": "warning_retention_rate",
    "feedback": "primary_to_alternate_update_rate",
    "planning": "successful_replan_rate",
    "interaction": "compatible_commitment_rate",
}
PRIMARY_MECHANISM_METRICS_V6 = {
    "memory": "conditional_warning_retention_rate",
    "feedback": "primary_to_alternate_update_rate",
    "planning": "successful_replan_rate",
    "interaction": "post_closure_feasible_commitment_rate",
}
PRIMARY_MECHANISM_METRICS_V7 = {
    "memory": "conditional_warning_retention_rate",
    "feedback": (
        "preclosure_primary_to_postclosure_alternate_update_rate"
    ),
    "planning": "successful_postclosure_replan_rate",
    "interaction": "post_closure_feasible_commitment_rate",
}
PRIMARY_MECHANISM_METRICS_V8 = dict(PRIMARY_MECHANISM_METRICS_V7)

# These outcomes are deliberately downstream of the module switches.  The
# module-specific metrics above remain manipulation checks; the outcomes below
# prevent a disabled module's structurally-zero internal state from being the
# only evidence reported for a mechanism contrast.
PRIMARY_DOWNSTREAM_METRICS_V8 = {
    "memory": {
        "metric": "complete_household_safe_departure_rate",
        "predicted_direction": "higher",
    },
    "feedback": {
        "metric": "closed_route_rejections_per_household",
        "predicted_direction": "lower",
    },
    "planning": {
        "metric": "complete_household_safe_departure_rate",
        "predicted_direction": "higher",
    },
    "interaction": {
        "metric": "coordinated_departure_rate",
        "predicted_direction": "higher",
    },
}


@dataclass
class CarrPilotResult:
    condition: str
    seed: int
    summary: dict
    metrics: dict
    world: CarrWorld
    agents: list[CarrResident]
    households: dict[str, Household]
    interaction: InteractionEngine
    run_dir: Path


def run_carr_condition(
    cfg: dict,
    *,
    condition: str,
    seed: int,
    runs_dir: str | Path,
) -> CarrPilotResult:
    mechanisms = MechanismFlags.from_condition(condition)
    run_cfg = cfg["run"]
    experiment_cfg = cfg["experiment"]
    eventpack_root = Path(experiment_cfg["eventpack_root"])
    if not eventpack_root.is_absolute():
        eventpack_root = Path(__file__).resolve().parents[2] / eventpack_root
    eventpack_root = eventpack_root.resolve()
    pack = load_eventpack(eventpack_root)
    population = _load_controlled_cohort(
        eventpack_root=eventpack_root,
        seed=seed,
        n_households=int(experiment_cfg["n_households"]),
        min_dependents=int(experiment_cfg.get("min_dependents", 1)),
        max_household_size=int(experiment_cfg.get("max_household_size", 4)),
    )
    parts = _build_parts(
        population=population,
        mechanisms=mechanisms,
        seed=seed,
        cfg=cfg,
        eventpack_root=eventpack_root,
    )

    base_run_id = str(run_cfg.get("run_id", "carr_s_mechanism_pilot"))
    run_id = f"{base_run_id}_{condition}_seed{seed}"
    run_dir = Path(runs_dir) / run_id
    llm_cfg = cfg.get("llm", {})
    decision_model = str(llm_cfg.get("decision_model", "mock"))
    models_cfg, models_config_path, credential_name = _gateway_configuration(
        llm_cfg=llm_cfg,
        decision_model=decision_model,
    )
    backends = (
        {"mock": MockBackend(policy=carr_controlled_policy)}
        if decision_model == "mock"
        else None
    )
    cache = LLMCache(run_dir / "cache.sqlite")
    gateway = LLMGateway(
        run_id=run_id,
        models_cfg=models_cfg,
        budget_usd=float(llm_cfg.get("budget_usd", 1.0)),
        max_concurrency=int(llm_cfg.get("max_concurrency", 16)),
        log_dir=runs_dir,
        cache=cache,
        backends=backends,
        abort_on_call_failure=bool(
            llm_cfg.get("abort_on_call_failure", False)
        ),
    )
    logger = RunLogger(run_dir)
    run_snapshot = {
        **cfg,
        "run": {**run_cfg, "seed": seed, "run_id": run_id},
        "experiment": {
            **experiment_cfg,
            "condition": condition,
            "evidence_status": str(
                experiment_cfg.get("evidence_status", "PILOT")
            ),
        },
    }
    write_provenance(
        run_dir,
        config=run_snapshot,
        models=[decision_model],
        extra={
            "eventpack_id": pack.manifest.event_id,
            "case_semantics": str(
                experiment_cfg.get(
                    "case_semantics",
                    "Carr-informed controlled mechanism scenario",
                )
            ),
            "models_config": (
                {
                    "path": str(models_config_path.relative_to(PROJECT_ROOT)),
                    "sha256": file_sha256(models_config_path),
                }
                if models_config_path is not None
                else {"path": None, "sha256": None}
            ),
            "credential_environment_name": credential_name,
            "credential_value_recorded": False,
            "source_files": {
                name: {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "sha256": file_sha256(path),
                }
                for name, path in {
                    "carr_runner": Path(__file__),
                    "resident_adapter": PROJECT_ROOT / "ds/agents/carr.py",
                    "kernel_engine": PROJECT_ROOT / "ds/kernel/engine.py",
                    "llm_gateway": PROJECT_ROOT / "ds/llm/gateway.py",
                }.items()
            },
        },
    )
    engine = Engine(
        run_seed=seed,
        total_steps=int(run_cfg["total_steps"]),
        step_minutes=int(run_cfg["step_minutes"]),
        world=parts["world"],
        agents=parts["agents"],
        interaction=parts["interaction"],
        events=parts["events"],
        gateway=gateway,
        logger=logger,
        decision_model=decision_model,
        temperature=float(llm_cfg.get("temperature", 0.0)),
        fallback_threshold=float(
            llm_cfg.get("fallback_threshold", 0.01)
        ),
    )
    async def run_and_close_gateway() -> dict:
        try:
            return await engine.run()
        finally:
            await gateway.aclose()

    try:
        summary = asyncio.run(run_and_close_gateway())
    finally:
        logger.close()
        cache.close()

    metrics = _mechanism_metrics(
        condition=condition,
        seed=seed,
        agents=parts["agents"],
        households=parts["households"],
        world=parts["world"],
        interaction=parts["interaction"],
        summary=summary,
        primary_route_id=experiment_cfg["primary_route_id"],
        alternate_route_id=experiment_cfg["alternate_route_id"],
        depart_step=int(experiment_cfg["depart_step"]),
        evidence_status=str(
            experiment_cfg.get("evidence_status", "PILOT")
        ),
        metric_protocol_version=str(
            experiment_cfg.get("metric_protocol_version", "legacy")
        ),
    )
    (run_dir / "mechanism_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return CarrPilotResult(
        condition=condition,
        seed=seed,
        summary=summary,
        metrics=metrics,
        world=parts["world"],
        agents=parts["agents"],
        households=parts["households"],
        interaction=parts["interaction"],
        run_dir=run_dir,
    )


def run_carr_pilot_matrix(
    cfg: dict,
    *,
    seeds: list[int],
    conditions: tuple[str, ...] = CONDITIONS,
    runs_dir: str | Path,
) -> dict:
    results: list[CarrPilotResult] = []
    aborted_early = False
    stop_on_nonvalid = bool(
        cfg.get("experiment", {}).get(
            "abort_matrix_on_nonvalid_run", False
        )
    )
    for seed in seeds:
        for condition in conditions:
            result = run_carr_condition(
                cfg,
                condition=condition,
                seed=seed,
                runs_dir=runs_dir,
            )
            results.append(result)
            if stop_on_nonvalid and result.summary["status"] != "VALID":
                aborted_early = True
                break
        if aborted_early:
            break
    rows = [
        {
            "condition": result.condition,
            "seed": result.seed,
            **{
                key: value
                for key, value in result.metrics.items()
                if isinstance(value, (int, float, str, bool))
            },
        }
        for result in results
    ]
    table = pd.DataFrame(rows)
    metric_protocol_version = str(
        cfg["experiment"].get("metric_protocol_version", "legacy")
    )
    metric_map = {
        "legacy": PRIMARY_MECHANISM_METRICS,
        "v6": PRIMARY_MECHANISM_METRICS_V6,
        "v7": PRIMARY_MECHANISM_METRICS_V7,
        "v8": PRIMARY_MECHANISM_METRICS_V8,
    }.get(metric_protocol_version)
    if metric_map is None:
        raise ValueError(
            f"unknown Carr metric protocol: {metric_protocol_version}"
        )
    paired, paired_summary = paired_mechanism_analysis(
        rows,
        metric_map=metric_map,
    )
    downstream_paired: list[dict[str, Any]] = []
    downstream_summary: list[dict[str, Any]] = []
    if metric_protocol_version == "v8":
        downstream_paired, downstream_summary = paired_directional_analysis(
            rows,
            metric_specs=PRIMARY_DOWNSTREAM_METRICS_V8,
        )
    variance_informative = all(
        item["variance_informative"] for item in paired_summary
    )
    decision_model = str(
        cfg.get("llm", {}).get("decision_model", "mock")
    )
    evidence_status = str(
        cfg["experiment"].get("evidence_status", "PILOT")
    )
    output = {
        "status": evidence_status,
        "activity_type": str(
            cfg["experiment"].get("activity_type", "MECHANISM_PILOT")
        ),
        "case_semantics": "Carr-informed controlled mechanism scenario",
        "decision_model": decision_model,
        "metric_protocol_version": metric_protocol_version,
        "n_households": int(cfg["experiment"]["n_households"]),
        "seeds": seeds,
        "conditions": list(conditions),
        "runs": rows,
        "paired_primary_differences": paired,
        "paired_summary": paired_summary,
        "paired_downstream_differences": downstream_paired,
        "paired_downstream_summary": downstream_summary,
        "pilot_gate_assessment": {
            "mechanism_paths_directionally_distinguishable": all(
                item["positive_direction_fraction"] == 1.0
                for item in paired_summary
            ),
            "seed_variance_informative": variance_informative,
            "next_action": _pilot_next_action(
                decision_model=decision_model,
                variance_informative=variance_informative,
            ),
        },
        "aborted_early": aborted_early,
        "limitations": [
            (
                "Uses the deterministic mock policy, not a publication-facing LLM backend."
                if decision_model == "mock"
                else (
                    f"Uses declared backend {decision_model}; this backend pilot "
                    "does not by itself constitute formal evidence."
                )
            ),
            "Uses a controlled two-route closure, not the historical Carr road timeline.",
            (
                "The cohort is selected for mechanism identification and is "
                "not population-representative."
            ),
            "No formal interval or significance claim is made from this pilot.",
            "Perfect 0/1 contrasts are wiring evidence and may be variance-uninformative.",
        ],
    }
    matrix_dir = Path(runs_dir) / str(
        cfg["run"].get("run_id", "carr_s_mechanism_pilot")
    )
    matrix_dir.mkdir(parents=True, exist_ok=True)
    (matrix_dir / "pilot_matrix.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    table.to_csv(matrix_dir / "pilot_runs.csv", index=False)
    return output


def paired_mechanism_analysis(
    rows: list[dict[str, Any]],
    *,
    require_valid: bool = True,
    metric_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute one full-minus-drop-one contrast per seed and module."""
    table = pd.DataFrame(rows)
    paired: list[dict[str, Any]] = []
    full = table[table["condition"] == "full"].set_index("seed")
    metric_map = metric_map or PRIMARY_MECHANISM_METRICS
    for module, metric in metric_map.items():
        drop_name = f"full_minus_{module}"
        drop = table[table["condition"] == drop_name].set_index("seed")
        for seed in sorted(set(full.index) & set(drop.index)):
            if require_valid:
                full_status = str(
                    full.loc[seed].get("run_terminal_status", "VALID")
                )
                drop_status = str(
                    drop.loc[seed].get("run_terminal_status", "VALID")
                )
                if full_status != "VALID" or drop_status != "VALID":
                    continue
            paired.append(
                {
                    "module": module,
                    "metric": metric,
                    "seed": int(seed),
                    "full": float(full.loc[seed, metric]),
                    "drop_one": float(drop.loc[seed, metric]),
                    "paired_difference": float(
                        full.loc[seed, metric] - drop.loc[seed, metric]
                    ),
                    "predicted_direction": "positive",
                }
            )
    if not paired:
        return [], []
    paired_summary: list[dict[str, Any]] = []
    for (module, metric), group in pd.DataFrame(paired).groupby(
        ["module", "metric"],
        sort=True,
    ):
        differences = [
            float(value) for value in group["paired_difference"]
        ]
        sd = statistics.stdev(differences) if len(differences) > 1 else 0.0
        paired_summary.append(
            {
                "module": module,
                "metric": metric,
                "n_seeds": len(differences),
                "mean_paired_difference": statistics.mean(differences),
                "sd_paired_difference": sd,
                "mcse": sd / math.sqrt(len(differences)),
                "positive_direction_fraction": sum(
                    value > 0 for value in differences
                )
                / len(differences),
                "variance_informative": len(set(differences)) > 1,
            }
        )
    return paired, paired_summary


def paired_directional_analysis(
    rows: list[dict[str, Any]],
    *,
    metric_specs: dict[str, dict[str, str]],
    require_valid: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute positive-is-better paired contrasts for downstream outcomes."""
    table = pd.DataFrame(rows)
    paired: list[dict[str, Any]] = []
    full = table[table["condition"] == "full"].set_index("seed")
    for module, spec in metric_specs.items():
        metric = spec["metric"]
        direction = spec["predicted_direction"]
        if direction not in {"higher", "lower"}:
            raise ValueError(
                f"unknown predicted direction for {module}: {direction}"
            )
        drop_name = f"full_minus_{module}"
        drop = table[table["condition"] == drop_name].set_index("seed")
        for seed in sorted(set(full.index) & set(drop.index)):
            if require_valid:
                full_status = str(
                    full.loc[seed].get("run_terminal_status", "VALID")
                )
                drop_status = str(
                    drop.loc[seed].get("run_terminal_status", "VALID")
                )
                if full_status != "VALID" or drop_status != "VALID":
                    continue
            full_value = float(full.loc[seed, metric])
            drop_value = float(drop.loc[seed, metric])
            raw_difference = full_value - drop_value
            directional_difference = (
                raw_difference if direction == "higher" else -raw_difference
            )
            paired.append(
                {
                    "module": module,
                    "metric": metric,
                    "seed": int(seed),
                    "full": full_value,
                    "drop_one": drop_value,
                    "raw_full_minus_drop": raw_difference,
                    "directional_difference": directional_difference,
                    "predicted_direction": direction,
                }
            )
    if not paired:
        return [], []
    summaries: list[dict[str, Any]] = []
    for (module, metric, direction), group in pd.DataFrame(paired).groupby(
        ["module", "metric", "predicted_direction"],
        sort=True,
    ):
        differences = [
            float(value) for value in group["directional_difference"]
        ]
        sd = statistics.stdev(differences) if len(differences) > 1 else 0.0
        summaries.append(
            {
                "module": module,
                "metric": metric,
                "predicted_direction": direction,
                "n_seeds": len(differences),
                "mean_directional_difference": statistics.mean(differences),
                "sd_directional_difference": sd,
                "mcse": sd / math.sqrt(len(differences)),
                "positive_direction_fraction": sum(
                    value > 0 for value in differences
                )
                / len(differences),
                "zero_difference_fraction": sum(
                    value == 0 for value in differences
                )
                / len(differences),
                "variance_informative": len(set(differences)) > 1,
            }
        )
    return paired, summaries


def _load_controlled_cohort(
    *,
    eventpack_root: Path,
    seed: int,
    n_households: int,
    min_dependents: int,
    max_household_size: int,
) -> dict[str, pd.DataFrame]:
    base = eventpack_root / "population/pilot_seed42_n1000"
    households = pd.read_csv(base / "synthetic_households.csv")
    persons = pd.read_csv(base / "synthetic_persons.csv")
    adult_counts = (
        persons["AGEP"].ge(18)
        .groupby(persons["synthetic_household_id"])
        .sum()
    )
    eligible_ids = set(adult_counts[adult_counts.eq(2)].index)
    eligible = households[
        households["synthetic_household_id"].isin(eligible_ids)
        & households["household_size"].between(
            2 + min_dependents, max_household_size
        )
        & households["vehicle_count"].astype(str).eq("1")
    ].copy()
    eligible["_order"] = eligible["synthetic_household_id"].map(
        lambda household_id: stream_seed(
            seed,
            "population",
            entity_id=str(household_id),
        )
    )
    eligible = eligible.sort_values(
        ["_order", "synthetic_household_id"]
    ).head(n_households)
    if len(eligible) < n_households:
        raise ValueError(
            f"controlled cohort needs {n_households} eligible households; "
            f"found {len(eligible)}"
        )
    eligible = eligible.drop(columns="_order").reset_index(drop=True)
    selected = set(eligible["synthetic_household_id"])
    selected_persons = persons[
        persons["synthetic_household_id"].isin(selected)
    ].copy()
    return {"households": eligible, "persons": selected_persons}


def _build_parts(
    *,
    population: dict[str, pd.DataFrame],
    mechanisms: MechanismFlags,
    seed: int,
    cfg: dict,
    eventpack_root: Path,
) -> dict[str, Any]:
    experiment_cfg = cfg["experiment"]
    households: dict[str, Household] = {}
    agents: list[CarrResident] = []
    for household_row in population["households"].to_dict(orient="records"):
        household_id = str(household_row["synthetic_household_id"])
        members = population["persons"][
            population["persons"]["synthetic_household_id"].eq(household_id)
        ].sort_values(["SPORDER", "resident_id"])
        adults = members[members["AGEP"].ge(18)]
        dependents = members[members["AGEP"].lt(18)]
        decision_ids = tuple(adults["resident_id"].astype(str))
        dependent_ids = tuple(dependents["resident_id"].astype(str))
        member_ids = decision_ids + dependent_ids
        vehicle_id = f"{household_id}:vehicle:1"
        household = Household(
            id=household_id,
            member_ids=member_ids,
            decision_member_ids=decision_ids,
            dependent_ids=dependent_ids,
            vehicles={
                vehicle_id: VehicleResource(
                    id=vehicle_id,
                    location="home",
                    capacity=max(5, len(member_ids)),
                )
            },
            dependent_states={
                dependent_id: DependentMemberState(
                    id=dependent_id,
                    location="home",
                    caregiver_id=decision_ids[0],
                )
                for dependent_id in dependent_ids
            },
        )
        households[household_id] = household
        for adult_index, (_, adult) in enumerate(adults.iterrows()):
            agent_id = str(adult["resident_id"])
            partner_id = decision_ids[1 - adult_index]
            limitations = {
                field.lower(): bool(adult.get(field) == 1)
                for field in ("DEAR", "DEYE", "DOUT", "DPHY", "DRAT", "DREM")
                if pd.notna(adult.get(field))
            }
            agents.append(
                CarrResident(
                    agent_id,
                    static=StaticAttrs(
                        age=int(adult["AGEP"]),
                        decision_capable=True,
                        decision_policy="generative",
                        functional_limitations=limitations,
                        household_id=household_id,
                        zone=str(experiment_cfg["controlled_zone"]),
                        home="home",
                    ),
                    household=household,
                    role="coordinator" if adult_index == 0 else "partner",
                    partner_id=partner_id,
                    vehicle_id=vehicle_id,
                    dependent_ids=dependent_ids,
                    mechanisms=mechanisms,
                    depart_step=int(experiment_cfg["depart_step"]),
                    primary_route_id=str(experiment_cfg["primary_route_id"]),
                    alternate_route_id=str(experiment_cfg["alternate_route_id"]),
                    persona=(
                        f"adult resident age {int(adult['AGEP'])} in a "
                        f"{len(member_ids)}-person household"
                    ),
                    prompt_version=str(
                        experiment_cfg.get(
                            "prompt_version",
                            "carr_s_controlled_resident_v3",
                        )
                    ),
                    coordination_deadline_step=(
                        int(experiment_cfg["coordination_deadline_step"])
                        if experiment_cfg.get("coordination_deadline_step")
                        is not None
                        else None
                    ),
                    route_observation_mode=str(
                        experiment_cfg.get(
                            "route_observation_mode",
                            "live_world",
                        )
                    ),
                )
            )

    world = CarrWorld(
        households=households,
        routes=_route_states(
            experiment_cfg=experiment_cfg,
            eventpack_root=eventpack_root,
        ),
        run_seed=seed,
        initial_hazard_distance_m=float(
            experiment_cfg["initial_hazard_distance_m"]
        ),
        hazard_approach_per_step_m=float(
            experiment_cfg["hazard_approach_per_step_m"]
        ),
    )
    metric_protocol_version = str(
        experiment_cfg.get("metric_protocol_version", "legacy")
    )
    seed_controlled_initial_plan = bool(
        experiment_cfg.get("seed_controlled_initial_plan", False)
    )
    route_observation_mode = str(
        experiment_cfg.get("route_observation_mode", "live_world")
    )
    if metric_protocol_version == "v7" and (
        route_observation_mode != "feedback_gated"
        or not seed_controlled_initial_plan
    ):
        raise ValueError(
            "Carr v7 requires feedback_gated route observation and a "
            "controlled initial plan"
        )
    if route_observation_mode == "feedback_gated":
        initial_routes = world.route_snapshot()
        for agent in agents:
            agent.initialize_route_observation(initial_routes, step=0)
    if seed_controlled_initial_plan:
        for agent in agents:
            agent.initialize_controlled_plan(
                route_id=str(experiment_cfg["primary_route_id"]),
                vehicle_id=agent.vehicle_id,
                depart_step=int(experiment_cfg["depart_step"]),
                dependent_ids=(
                    agent.dependent_ids
                    if agent.role == "coordinator"
                    else ()
                ),
                created_step=0,
            )
    world.bind_agents(agents)
    interaction = InteractionEngine(
        {agent.id: agent for agent in agents},
        delivery=(
            DeterministicDeliveryModel()
            if float(
                experiment_cfg.get(
                    "official_warning_delivery_probability",
                    1.0,
                )
            )
            == 1.0
            else FixedProbabilityDeliveryModel(
                float(
                    experiment_cfg[
                        "official_warning_delivery_probability"
                    ]
                )
            )
        ),
        households_by_id=households,
        social_enabled=mechanisms.interaction,
        run_seed=seed,
        message_delivery_probability=float(
            experiment_cfg.get(
                "social_message_delivery_probability",
                1.0,
            )
        ),
        dm_delivery_probability=float(
            experiment_cfg.get(
                "household_dm_delivery_probability",
                experiment_cfg.get(
                    "social_message_delivery_probability",
                    1.0,
                ),
            )
        ),
        community_delivery_probability=float(
            experiment_cfg.get(
                "community_message_delivery_probability",
                experiment_cfg.get(
                    "social_message_delivery_probability",
                    1.0,
                ),
            )
        ),
    )
    coordinator_ids = [
        agent.id for agent in agents if agent.role == "coordinator"
    ]
    source = load_warning_events(
        eventpack_root / "warnings/warnings_multi.csv"
    )
    mandatory = next(
        event
        for event in source.events
        if event.payload.get("severity") == "mandatory"
    )
    closure_step = _controlled_closure_step(experiment_cfg, seed)
    events = ListEventSource(
        [
            Event(
                step=int(experiment_cfg["warning_step"]),
                kind="warning",
                text=mandatory.text,
                zone=str(experiment_cfg["controlled_zone"]),
                recipients=coordinator_ids,
                payload={
                    **mandatory.payload,
                    "scenario_control": "coordinator-only initial information",
                    "source_event_step": mandatory.step,
                },
            ),
            Event(
                step=closure_step,
                kind="road_closed",
                text="Controlled primary-route obstruction.",
                recipients="all",
                payload={
                    "route_id": str(experiment_cfg["primary_route_id"]),
                    "scenario_control": True,
                },
            ),
        ]
    )
    return {
        "world": world,
        "agents": agents,
        "households": households,
        "interaction": interaction,
        "events": events,
        "closure_step": closure_step,
    }


def _mechanism_metrics(
    *,
    condition: str,
    seed: int,
    agents: list[CarrResident],
    households: dict[str, Household],
    world: CarrWorld,
    interaction: InteractionEngine,
    summary: dict,
    primary_route_id: str,
    alternate_route_id: str,
    depart_step: int,
    evidence_status: str,
    metric_protocol_version: str = "legacy",
) -> dict:
    coordinators = [agent for agent in agents if agent.role == "coordinator"]
    warning_exposed = [agent for agent in coordinators if agent.state.warned]
    warning_retained = [
        any(item.kind == "warning" for item in agent.memory.items)
        for agent in coordinators
    ]
    warning_retained_if_exposed = [
        any(item.kind == "warning" for item in agent.memory.items)
        for agent in warning_exposed
    ]
    realized_closure_step = int(
        world.route_closures[0]["step"]
        if world.route_closures
        else -1
    )
    planned_primary = [
        agent
        for agent in agents
        if any(
            item["route_id"] == primary_route_id
            for item in agent.plan_history
        )
    ]
    updated_alternate = [
        agent
        for agent in planned_primary
        if any(
            item["route_id"] == alternate_route_id
            for item in agent.plan_history
        )
    ]
    preclosure_primary = [
        agent
        for agent in agents
        if any(
            item["route_id"] == primary_route_id
            and int(item["step"]) < realized_closure_step
            for item in agent.plan_history
        )
    ]
    postclosure_alternate = [
        agent
        for agent in preclosure_primary
        if any(
            item["route_id"] == alternate_route_id
            and int(item["step"]) >= realized_closure_step
            for item in agent.plan_history
        )
    ]
    replanned_households = {
        agent.static.household_id
        for agent in agents
        if agent.state.evac_step >= depart_step
        and any(
            item["route_id"] == alternate_route_id
            and item["status"] == "completed"
            for item in agent.plan_history
        )
    }
    postclosure_replanned_households = {
        agent.static.household_id
        for agent in agents
        if agent.state.evac_step >= max(depart_step, realized_closure_step)
        and any(
            item["route_id"] == alternate_route_id
            and item["status"] == "completed"
            and int(item["step"]) >= realized_closure_step
            for item in agent.plan_history
        )
    }
    compatible = [
        household.compatible_commitment(
            route_id=alternate_route_id,
            vehicle_id=next(iter(household.vehicles)),
            depart_step=depart_step,
        )
        is not None
        for household in households.values()
    ]
    feasible_formed = [
        household.has_feasible_commitment_formation()
        for household in households.values()
    ]
    post_closure_feasible = [
        household.has_feasible_commitment_formation(
            route_id=alternate_route_id,
            min_created_step=realized_closure_step,
        )
        for household in households.values()
    ]
    interaction_snapshot = interaction.snapshot()
    receipt_states = interaction_snapshot["receipt_states"]
    processed_receipts = sum(
        int(receipt_states.get(status, 0))
        for status in ("processed", "accepted", "rejected")
    )
    resource_rejections = sum(
        count
        for reason, count in world.rejections.items()
        if "vehicle" in reason or "allocated" in reason or "reserved" in reason
    )
    total_dependents = sum(
        len(household.dependent_ids) for household in households.values()
    )
    complete_safe_households = [
        set(household.decision_member_ids).issubset(world.evacuated)
        and set(household.dependent_ids).issubset(world.safe_dependents)
        for household in households.values()
    ]
    closed_route_rejections = int(world.rejections.get("route closed", 0))
    total_execution_rejections = int(sum(world.rejections.values()))
    total_decisions = (
        summary["gateway"]["n_ok"]
        + summary["gateway"]["n_cache"]
        + summary["gateway"]["n_fallback"]
    )
    return {
        "status": evidence_status,
        "condition": condition,
        "seed": seed,
        "metric_protocol_version": metric_protocol_version,
        "n_households": len(households),
        "n_decision_residents": len(agents),
        "warning_exposed_coordinator_count": len(warning_exposed),
        "warning_retained_coordinator_count": sum(
            warning_retained_if_exposed
        ),
        "conditional_warning_retention_rate": _mean_bool(
            warning_retained_if_exposed
        ),
        "warning_retention_rate": _mean_bool(warning_retained),
        "planned_primary_count": len(planned_primary),
        "updated_alternate_count": len(updated_alternate),
        "primary_to_alternate_update_rate": (
            len(updated_alternate) / len(planned_primary)
            if planned_primary
            else 0.0
        ),
        "preclosure_primary_plan_count": len(preclosure_primary),
        "preclosure_primary_plan_rate": (
            len(preclosure_primary) / len(agents)
        ),
        "postclosure_alternate_update_count": len(
            postclosure_alternate
        ),
        "preclosure_primary_to_postclosure_alternate_update_rate": (
            len(postclosure_alternate) / len(preclosure_primary)
            if preclosure_primary
            else 0.0
        ),
        "successful_replan_rate": len(replanned_households) / len(households),
        "replanned_household_count": len(replanned_households),
        "successful_postclosure_replan_rate": (
            len(postclosure_replanned_households) / len(households)
        ),
        "postclosure_replanned_household_count": len(
            postclosure_replanned_households
        ),
        "compatible_commitment_rate": _mean_bool(compatible),
        "feasible_commitment_formation_count": sum(feasible_formed),
        "feasible_commitment_formation_rate": _mean_bool(feasible_formed),
        "post_closure_feasible_commitment_count": sum(
            post_closure_feasible
        ),
        "post_closure_feasible_commitment_rate": _mean_bool(
            post_closure_feasible
        ),
        "coordinated_departure_rate": (
            world.coordinated_movements / len(households)
        ),
        "decision_resident_evacuation_rate": (
            len(world.evacuated) / len(agents)
        ),
        "dependent_safety_rate": (
            len(world.safe_dependents) / total_dependents
            if total_dependents
            else 1.0
        ),
        "complete_household_safe_departure_rate": _mean_bool(
            complete_safe_households
        ),
        "uncoordinated_departure_rate": (
            world.uncoordinated_movements / len(households)
        ),
        "closed_route_rejections_per_household": (
            closed_route_rejections / len(households)
        ),
        "execution_rejections_per_household": (
            total_execution_rejections / len(households)
        ),
        "resource_conflict_rejections_per_household": (
            resource_rejections / len(households)
        ),
        "dependent_left_behind_rejections": int(
            world.rejections.get("dependent member would be left behind", 0)
        ),
        "dependent_left_behind_rejections_per_household": (
            world.rejections.get("dependent member would be left behind", 0)
            / len(households)
        ),
        "accepted_message_receipts": sum(
            receipt.status == "accepted"
            for receipt in interaction.receipts.values()
        ),
        "delivered_message_receipts": len(interaction.receipts),
        "processed_message_receipts": processed_receipts,
        "rejected_message_receipts": int(
            receipt_states.get("rejected", 0)
        ),
        "unprocessed_message_receipts": int(
            receipt_states.get("delivered", 0)
        ),
        "messages_sent": interaction.msg_count,
        "dropped_message_deliveries": int(
            interaction_snapshot["dropped"]
        ),
        "invalid_proposal_attempts": int(
            interaction.invalid_proposal_attempts
        ),
        "invalid_acceptance_attempts": int(
            interaction.invalid_acceptance_attempts
        ),
        "realized_closure_step": realized_closure_step,
        "route_observation_update_count": sum(
            event.get("kind") == "route_observation_update"
            for agent in agents
            for event in agent.feedback_events
        ),
        "n_logical_decisions": int(total_decisions),
        "run_terminal_status": summary["status"],
        "fallback_rate": summary["gateway"]["fallback_rate"],
        "cost_usd": summary["gateway"]["spent"],
    }


def _mean_bool(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def _controlled_closure_step(experiment_cfg: dict, seed: int) -> int:
    choices = experiment_cfg.get("closure_step_choices")
    if choices is None:
        return int(experiment_cfg["closure_step"])
    choices = [int(value) for value in choices]
    if not choices:
        raise ValueError("closure_step_choices must not be empty")
    index = stream_seed(
        seed,
        "scenario_perturbation",
        entity_id="primary_route_closure_step",
    ) % len(choices)
    return choices[index]


def _gateway_configuration(
    *,
    llm_cfg: dict[str, Any],
    decision_model: str,
) -> tuple[dict[str, Any], Path | None, str | None]:
    """Resolve a declared backend without recording credential values."""
    if decision_model == "mock" and not llm_cfg.get("models_config"):
        return (
            {
                "models": {
                    "mock": {
                        "backend": "mock",
                        "input_per_m": 0.0,
                        "output_per_m": 0.0,
                    }
                }
            },
            None,
            None,
        )

    config_path = Path(
        str(llm_cfg.get("models_config", DEFAULT_MODELS_CONFIG))
    )
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config_path = config_path.resolve()
    models_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(models_cfg, dict) or not isinstance(
        models_cfg.get("models"), dict
    ):
        raise ValueError(f"invalid model registry: {config_path}")
    if decision_model not in models_cfg["models"]:
        raise ValueError(
            f"decision model {decision_model!r} is absent from {config_path}"
        )
    model_spec = models_cfg["models"][decision_model]
    if decision_model == "mock":
        return models_cfg, config_path, None

    candidates = list(model_spec.get("api_key_env_candidates", []))
    if model_spec.get("api_key_env"):
        candidates.insert(0, model_spec["api_key_env"])
    credential_name = next(
        (name for name in candidates if os.environ.get(name)),
        None,
    )
    if candidates and credential_name is None:
        raise RuntimeError(
            "No model credential is available. Set one of: "
            + ", ".join(candidates)
        )
    if "YOUR_" in str(model_spec.get("base_url", "")):
        raise ValueError(
            f"decision model {decision_model!r} still has a placeholder base URL"
        )
    return models_cfg, config_path, credential_name


def _pilot_next_action(
    *,
    decision_model: str,
    variance_informative: bool,
) -> str:
    if decision_model != "mock":
        if variance_informative:
            return (
                "Review schema adherence, fallback, cost, and paired variance; "
                "then freeze the formal seed count and prompt before Gate D."
            )
        return (
            "Do not freeze the formal seed count; diagnose the declared "
            "backend pilot or add predeclared seeds before Gate D."
        )
    if variance_informative:
        return (
            "Use the controlled-mock variance to size the next declared-backend "
            "pilot; do not freeze the formal seed count until that backend "
            "pilot is complete."
        )
    return (
        "Do not freeze formal seed count from this saturated mock pilot; add "
        "non-saturated perturbations or a declared model backend pilot first."
    )


def _route_states(
    *,
    experiment_cfg: dict,
    eventpack_root: Path,
) -> dict[str, RouteState]:
    primary_id = str(experiment_cfg["primary_route_id"])
    alternate_id = str(experiment_cfg["alternate_route_id"])
    capacity = int(experiment_cfg["route_capacity_per_step"])
    route_asset_value = experiment_cfg.get("route_asset")
    if route_asset_value is None:
        return {
            primary_id: RouteState(primary_id, capacity),
            alternate_id: RouteState(alternate_id, capacity),
        }

    route_asset_path = Path(str(route_asset_value))
    if not route_asset_path.is_absolute():
        route_asset_path = eventpack_root / route_asset_path
    asset = json.loads(route_asset_path.read_text(encoding="utf-8"))
    if asset.get("status") != "CONTROLLED_DERIVED_ASSET":
        raise ValueError("Carr route asset has an unexpected evidence status")
    if asset["controlled_obstruction"]["historical_closure_observed"]:
        raise ValueError("controlled route asset must not claim observed closure")
    if asset["controlled_obstruction"]["closed_route_id"] != primary_id:
        raise ValueError("route asset obstruction does not match primary route")
    routes = asset.get("routes", {})
    missing = {primary_id, alternate_id} - set(routes)
    if missing:
        raise ValueError(f"route asset is missing configured routes: {missing}")

    return {
        route_id: RouteState(
            id=route_id,
            capacity_per_step=capacity,
            length_m=float(routes[route_id]["length_m"]),
            edge_source_linearids=tuple(
                str(value)
                for value in routes[route_id]["edge_source_linearids"]
            ),
            asset_status=str(asset["status"]),
        )
        for route_id in (primary_id, alternate_id)
    }
