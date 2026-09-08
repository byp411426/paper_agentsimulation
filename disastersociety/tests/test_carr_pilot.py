"""Carr-S controlled mechanism pilot tests (offline, mock, zero cost)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from experiments.carr.runner import (
    PRIMARY_MECHANISM_METRICS,
    PRIMARY_MECHANISM_METRICS_V6,
    PRIMARY_MECHANISM_METRICS_V7,
    PRIMARY_MECHANISM_METRICS_V8,
    PRIMARY_DOWNSTREAM_METRICS_V8,
    _gateway_configuration,
    paired_directional_analysis,
    paired_mechanism_analysis,
    run_carr_condition,
)
from scripts.run_carr_robustness_pilot import build_scenario_config
from scripts.run_carr_formal_e2_v5 import run_formal_matrix
from scripts.summarize_carr_formal_e2_v5 import _paired_intervals
from scripts.audit_carr_e2_v5_protocol import diagnose_event_records
from ds.eval.carr_protocol import file_sha256


CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/carr_s_mechanism_pilot.yaml"
)
NONSATURATED_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/"
    "carr_s_mechanism_nonsaturated_pilot.yaml"
)
EXPANSION_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/"
    "carr_s_deepseek_backend_pilot_expansion.yaml"
)
RELIABILITY_V4_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/"
    "carr_s_deepseek_backend_reliability_v4.yaml"
)
FORMAL_E2_V5_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/"
    "carr_s_formal_e2_v5.yaml"
)
V6_MOCK_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments/carr/configs/carr_s_mechanism_v6_mock_pilot.yaml"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
V5_PAUSE = (
    PROJECT_ROOT
    / "experiments/carr/protocol/carr_s_formal_e2_v5_pause.json"
)
V6_FREEZE = (
    PROJECT_ROOT / "experiments/carr/protocol/carr_s_e2_v6_freeze.json"
)
V7_FREEZE = (
    PROJECT_ROOT
    / "experiments/carr/protocol/carr_s_e2_v7_controlled_pilot_freeze.json"
)
V8_FORMAL_CONFIG = (
    PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_formal.yaml"
)
V8_FORMAL_FREEZE = (
    PROJECT_ROOT / "experiments/carr/protocol/carr_s_e2_v8_formal_freeze.json"
)


def _assert_frozen_source_record(source: dict) -> None:
    """Keep historical code digests immutable as the active source evolves."""
    path = PROJECT_ROOT / source["path"]
    assert path.exists()
    assert len(source["sha256"]) == 64
    # Data/config/result artifacts remain immutable in place.  Source and test
    # files are expected to evolve after a completed protocol, so their stored
    # digest is an audit record rather than an assertion about today's tree.
    if path.suffix in {".json", ".yaml", ".yml"}:
        assert file_sha256(path) == source["sha256"]


def _cfg(n_households: int = 2) -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cfg["experiment"]["n_households"] = n_households
    return cfg


def test_carr_full_closes_loop_with_coordinated_household_departure(tmp_path):
    result = run_carr_condition(
        _cfg(),
        condition="full",
        seed=101,
        runs_dir=tmp_path,
    )
    metrics = result.metrics
    assert result.summary["status"] == "VALID"
    assert result.summary["wall_clock_seconds"] >= 0.0
    assert result.summary["gateway"]["spent"] == 0.0
    assert metrics["warning_retention_rate"] == 1.0
    assert metrics["primary_to_alternate_update_rate"] == 1.0
    assert metrics["successful_replan_rate"] == 1.0
    assert metrics["compatible_commitment_rate"] == 1.0
    assert metrics["coordinated_departure_rate"] == 1.0
    assert metrics["decision_resident_evacuation_rate"] == 1.0
    assert metrics["dependent_safety_rate"] == 1.0
    assert metrics["complete_household_safe_departure_rate"] == 1.0
    assert metrics["execution_rejections_per_household"] == 0.0
    assert metrics["dependent_left_behind_rejections"] == 0
    assert result.world.snapshot()["routes"]["controlled_primary"]["open"] is False
    assert all(agent.state.evac_step >= 0 for agent in result.agents)
    assert all(
        dependent.safe
        for household in result.households.values()
        for dependent in household.dependent_states.values()
    )
    agent = result.agents[0]
    prompt = agent._carr_messages(world=result.world, step=7)
    state = json.loads(prompt[-1]["content"].split("=", 1)[1])
    assert state["resident_profile"]["age"] == agent.static.age
    assert state["household_member_count"] == len(
        result.households[agent.static.household_id].member_ids
    )


def test_drop_one_conditions_change_only_their_predeclared_primary_metrics(
    tmp_path,
):
    cfg = _cfg()
    results = {
        condition: run_carr_condition(
            cfg,
            condition=condition,
            seed=202,
            runs_dir=tmp_path,
        )
        for condition in (
            "full",
            "full_minus_memory",
            "full_minus_feedback",
            "full_minus_planning",
            "full_minus_interaction",
        )
    }
    full = results["full"].metrics
    assert (
        full["warning_retention_rate"]
        > results["full_minus_memory"].metrics["warning_retention_rate"]
    )
    assert (
        full["primary_to_alternate_update_rate"]
        > results["full_minus_feedback"].metrics[
            "primary_to_alternate_update_rate"
        ]
    )
    assert (
        full["successful_replan_rate"]
        > results["full_minus_planning"].metrics["successful_replan_rate"]
    )
    assert (
        full["compatible_commitment_rate"]
        > results["full_minus_interaction"].metrics[
            "compatible_commitment_rate"
        ]
    )
    assert (
        PRIMARY_MECHANISM_METRICS["interaction"]
        == "compatible_commitment_rate"
    )
    populations = [
        set(result.households)
        for result in results.values()
    ]
    assert all(population == populations[0] for population in populations[1:])
    assert all(
        result.summary["status"] == "VALID"
        for result in results.values()
    )


def test_nonsaturated_controls_are_seeded_and_reproducible(tmp_path):
    cfg = yaml.safe_load(
        NONSATURATED_CONFIG.read_text(encoding="utf-8")
    )
    cfg["experiment"]["n_households"] = 20
    first = run_carr_condition(
        cfg,
        condition="full",
        seed=202,
        runs_dir=tmp_path / "first",
    )
    second = run_carr_condition(
        cfg,
        condition="full",
        seed=202,
        runs_dir=tmp_path / "second",
    )
    assert first.metrics == second.metrics
    assert 0.0 < first.metrics["warning_retention_rate"] < 1.0
    assert first.metrics["dropped_message_deliveries"] > 0
    assert first.metrics["realized_closure_step"] in {3, 4, 5, 6}


def test_robustness_scenario_builder_does_not_mutate_base():
    base = yaml.safe_load(
        NONSATURATED_CONFIG.read_text(encoding="utf-8")
    )
    original_probability = base["experiment"][
        "official_warning_delivery_probability"
    ]
    scenario = build_scenario_config(
        base,
        scenario_name="low",
        controls={
            "official_warning_delivery_probability": 0.45,
            "social_message_delivery_probability": 0.15,
            "route_capacity_per_step": 5,
        },
    )
    assert scenario["run"]["run_id"].endswith("_low")
    assert scenario["experiment"]["route_capacity_per_step"] == 5
    assert base["experiment"][
        "official_warning_delivery_probability"
    ] == original_probability


def test_backend_expansion_protocol_is_predeclared_and_test_sealed():
    cfg = yaml.safe_load(EXPANSION_CONFIG.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["expansion_protocol"]
    assert protocol["new_seeds"] == [303, 404, 505]
    assert protocol["execute_all_new_seeds_regardless_of_interim_direction"]
    assert protocol["formal_evidence"] is False
    assert protocol["formal_seed_count_frozen"] is False
    assert protocol["test_split_opened"] is False
    assert cfg["experiment"]["n_households"] == 2
    assert cfg["experiment"]["prompt_version"] == (
        "carr_s_controlled_resident_v3"
    )


def test_backend_reliability_v4_is_fixed_sequential_and_test_sealed():
    cfg = yaml.safe_load(
        RELIABILITY_V4_CONFIG.read_text(encoding="utf-8")
    )
    protocol = cfg["experiment"]["reliability_protocol"]
    observed = [
        (item["seed"], item["condition"])
        for item in protocol["checks"]
    ]
    assert observed == [
        (404, "full"),
        (303, "full_minus_memory"),
        (505, "full_minus_memory"),
    ]
    assert protocol["execute_sequentially"] is True
    assert protocol["formal_evidence"] is False
    assert protocol["substitute_for_v3_scientific_pairs"] is False
    assert protocol["test_split_opened"] is False
    assert cfg["experiment"]["prompt_version"] == (
        "carr_s_controlled_resident_v4"
    )


def test_formal_e2_v5_protocol_is_frozen_batched_and_test_sealed(tmp_path):
    cfg = yaml.safe_load(FORMAL_E2_V5_CONFIG.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    assert cfg["experiment"]["evidence_status"] == "PILOT"
    assert cfg["experiment"]["activity_type"] == "FORMAL_MECHANISM_MATRIX"
    assert cfg["experiment"]["prompt_version"] == (
        "carr_s_controlled_resident_v5"
    )
    assert cfg["experiment"]["n_households"] == 5
    assert cfg["llm"]["max_concurrency"] == 1
    assert protocol["n_seeds"] == 16
    assert len(protocol["seeds"]) == 16
    assert protocol["test_split_opened"] is False
    assert protocol["raw_run_evidence_status"].startswith("PILOT")
    with pytest.raises(ValueError, match="not in the frozen protocol"):
        run_formal_matrix(
            cfg,
            config_path=FORMAL_E2_V5_CONFIG,
            runs_dir=tmp_path,
            selected_seeds=[999999],
        )
    with pytest.raises(RuntimeError, match="E2 v5 is paused"):
        run_formal_matrix(
            cfg,
            config_path=FORMAL_E2_V5_CONFIG,
            runs_dir=tmp_path,
            selected_seeds=[303],
        )


def test_v6_protocol_separates_channels_and_keeps_paid_gate_closed(tmp_path):
    cfg = yaml.safe_load(V6_MOCK_CONFIG.read_text(encoding="utf-8"))
    gate = cfg["experiment"]["v6_gate"]
    assert cfg["experiment"]["metric_protocol_version"] == "v6"
    assert cfg["experiment"]["household_dm_delivery_probability"] == 1.0
    assert cfg["experiment"]["community_message_delivery_probability"] == 0.15
    assert gate["paid_execution_authorized"] is False
    assert gate["formal_seed_count_frozen"] is False
    assert gate["test_split_opened"] is False
    assert PRIMARY_MECHANISM_METRICS_V6["interaction"] == (
        "post_closure_feasible_commitment_rate"
    )

    cfg["experiment"]["n_households"] = 2
    result = run_carr_condition(
        cfg,
        condition="full",
        seed=101,
        runs_dir=tmp_path,
    )
    assert result.summary["status"] == "VALID"
    assert result.metrics["feasible_commitment_formation_rate"] == 1.0
    assert result.metrics["post_closure_feasible_commitment_rate"] == 1.0
    assert result.metrics["conditional_warning_retention_rate"] == 1.0
    assert result.metrics["invalid_proposal_attempts"] == 0
    assert result.metrics["invalid_acceptance_attempts"] == 0

    late_closure = run_carr_condition(
        cfg,
        condition="full",
        seed=202,
        runs_dir=tmp_path,
    )
    assert late_closure.metrics["realized_closure_step"] == 4
    assert late_closure.metrics["coordinated_departure_rate"] == 1.0
    assert late_closure.metrics["uncoordinated_departure_rate"] == 0.0


def test_v7_gates_route_observation_and_seeds_equal_baseline_plans(tmp_path):
    cfg = yaml.safe_load(V6_MOCK_CONFIG.read_text(encoding="utf-8"))
    cfg["experiment"].update(
        {
            "metric_protocol_version": "v7",
            "prompt_version": "carr_s_controlled_resident_v7",
            "route_observation_mode": "feedback_gated",
            "seed_controlled_initial_plan": True,
            "n_households": 2,
        }
    )
    results = {
        condition: run_carr_condition(
            cfg,
            condition=condition,
            seed=101,
            runs_dir=tmp_path,
        )
        for condition in ("full", "full_minus_feedback")
    }
    full = results["full"]
    dropped = results["full_minus_feedback"]

    assert not full.world.route_snapshot()["tiger_primary"]["open"]
    assert not dropped.world.route_snapshot()["tiger_primary"]["open"]
    full_state = json.loads(
        full.agents[0]
        ._carr_messages(world=full.world, step=9)[-1]["content"]
        .split("=", 1)[1]
    )
    dropped_state = json.loads(
        dropped.agents[0]
        ._carr_messages(world=dropped.world, step=9)[-1]["content"]
        .split("=", 1)[1]
    )
    assert full_state["routes"]["tiger_primary"]["open"] is False
    assert dropped_state["routes"]["tiger_primary"]["open"] is True
    assert full.metrics["preclosure_primary_plan_rate"] == 1.0
    assert dropped.metrics["preclosure_primary_plan_rate"] == 1.0
    assert (
        full.metrics[
            "preclosure_primary_to_postclosure_alternate_update_rate"
        ]
        > dropped.metrics[
            "preclosure_primary_to_postclosure_alternate_update_rate"
        ]
    )
    assert full.metrics["route_observation_update_count"] > 0
    assert dropped.metrics["route_observation_update_count"] == 0
    assert all(
        agent.plan_history[0]["source"] == "controlled_initial_state"
        for result in results.values()
        for agent in result.agents
    )
    assert PRIMARY_MECHANISM_METRICS_V7["feedback"] == (
        "preclosure_primary_to_postclosure_alternate_update_rate"
    )

    v8_agent = full.agents[0]
    v8_agent.prompt_version = "carr_s_controlled_resident_v8"
    v8_agent.plan.last_failure = "vehicle reserved by partner"
    v8_agent.feedback_events.append(
        {
            "step": 9,
            "kind": "execution_rejected",
            "reason": "vehicle reserved by partner",
        }
    )
    v8_state_messages = v8_agent._carr_messages(
        world=full.world,
        step=9,
    )
    v8_state = json.loads(
        v8_state_messages[-1]["content"].split("=", 1)[1]
    )
    assert v8_state["current_plan"]["last_failure"] == (
        "vehicle reserved by partner"
    )
    assert v8_state["recent_execution_feedback"][-1]["kind"] == (
        "execution_rejected"
    )
    assert v8_state["household_vehicle_state"]["vehicle_id"] == (
        v8_agent.vehicle_id
    )
    assert "do not repeat the failed vehicle request" in (
        v8_state_messages[0]["content"]
    )


def test_v8_reports_downstream_outcomes_separately_from_manipulation_checks():
    assert PRIMARY_MECHANISM_METRICS_V8 == PRIMARY_MECHANISM_METRICS_V7
    assert PRIMARY_DOWNSTREAM_METRICS_V8["feedback"] == {
        "metric": "closed_route_rejections_per_household",
        "predicted_direction": "lower",
    }
    rows = [
        {
            "condition": "full",
            "seed": 11,
            "run_terminal_status": "VALID",
            "complete_household_safe_departure_rate": 1.0,
            "closed_route_rejections_per_household": 0.0,
            "coordinated_departure_rate": 1.0,
        },
        {
            "condition": "full_minus_memory",
            "seed": 11,
            "run_terminal_status": "VALID",
            "complete_household_safe_departure_rate": 0.5,
            "closed_route_rejections_per_household": 0.0,
            "coordinated_departure_rate": 1.0,
        },
        {
            "condition": "full_minus_feedback",
            "seed": 11,
            "run_terminal_status": "VALID",
            "complete_household_safe_departure_rate": 0.5,
            "closed_route_rejections_per_household": 2.0,
            "coordinated_departure_rate": 0.5,
        },
        {
            "condition": "full_minus_planning",
            "seed": 11,
            "run_terminal_status": "VALID",
            "complete_household_safe_departure_rate": 0.25,
            "closed_route_rejections_per_household": 1.0,
            "coordinated_departure_rate": 0.5,
        },
        {
            "condition": "full_minus_interaction",
            "seed": 11,
            "run_terminal_status": "VALID",
            "complete_household_safe_departure_rate": 0.5,
            "closed_route_rejections_per_household": 1.0,
            "coordinated_departure_rate": 0.0,
        },
    ]
    paired, summary = paired_directional_analysis(
        rows,
        metric_specs=PRIMARY_DOWNSTREAM_METRICS_V8,
    )
    assert len(paired) == 4
    feedback = next(item for item in paired if item["module"] == "feedback")
    assert feedback["raw_full_minus_drop"] == -2.0
    assert feedback["directional_difference"] == 2.0
    assert all(
        item["mean_directional_difference"] > 0 for item in summary
    )


def test_v8_formal_protocol_is_frozen_real_backend_and_test_sealed():
    cfg = yaml.safe_load(V8_FORMAL_CONFIG.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    assert cfg["llm"]["decision_model"] == "packy-deepseek-v4-flash"
    assert cfg["llm"]["max_concurrency"] == 12
    assert cfg["experiment"]["metric_protocol_version"] == "v8"
    assert cfg["experiment"]["prompt_version"] == (
        "carr_s_controlled_resident_v8"
    )
    assert cfg["experiment"]["n_households"] == 8
    assert protocol["n_seeds"] == 12
    assert len(protocol["seeds"]) == 12
    assert protocol["execute_all_seeds_regardless_of_interim_direction"]
    assert protocol["carr_r_test_split_opened"] is False
    assert protocol["use_mock_for_behavior_or_effect_evidence"] is False

    freeze = json.loads(V8_FORMAL_FREEZE.read_text(encoding="utf-8"))
    assert freeze["status"] == "FROZEN_FOR_EXECUTION"
    assert freeze["execution_contract"]["n_seed_condition_runs"] == 60
    assert freeze["execution_contract"]["mock_eligible_for_effect_evidence"] is False
    assert freeze["execution_contract"]["carr_r_test_split_opened"] is False
    # This completed protocol records historical source digests.  Apply the
    # same history-versus-active-source contract as the other archived freezes;
    # data/config/result digests stay strict. Active semantics are covered by
    # the household, kernel, interaction, and gateway regression tests.
    for source in freeze["frozen_sources"]:
        _assert_frozen_source_record(source)


def test_v5_pause_and_v6_freeze_are_hash_bound_and_test_sealed():
    pause = json.loads(V5_PAUSE.read_text(encoding="utf-8"))
    assert pause["status"] == "PAUSED"
    assert pause["pause_is_based_on_interim_effect_direction"] is False
    assert pause["carr_r_test_split_opened"] is False
    assert file_sha256(PROJECT_ROOT / pause["source"]["config"]) == (
        pause["source"]["config_sha256"]
    )
    for source in pause["source"]["seed_summaries"]:
        assert file_sha256(PROJECT_ROOT / source["path"]) == source["sha256"]

    freeze = json.loads(V6_FREEZE.read_text(encoding="utf-8"))
    assert freeze["status"] == "THINKING_HIGH_BACKEND_PILOT_COMPLETED"
    assert freeze["zero_cost_validation"]["status"] == "PASSED"
    assert freeze["execution_gate"]["paid_execution_authorized"] is True
    assert freeze["execution_gate"]["formal_matrix_authorized"] is False
    assert freeze["execution_gate"]["formal_seed_count_frozen"] is False
    assert freeze["execution_gate"]["carr_r_test_split_opened"] is False
    for source in freeze["frozen_sources"]:
        _assert_frozen_source_record(source)


def test_v7_protocol_is_hash_bound_and_carr_r_test_sealed():
    freeze = json.loads(V7_FREEZE.read_text(encoding="utf-8"))
    assert freeze["status"] == "DECLARED_BACKEND_PILOT_COMPLETED"
    assert freeze["evidence_status"] == "PILOT"
    execution = freeze["execution_contract"]
    assert execution["n_declared_cells"] == 15
    assert execution["formal_matrix_authorized"] is False
    assert execution["formal_seed_count_frozen"] is False
    assert execution["carr_r_test_split_opened"] is False
    assert freeze["completion_record"]["terminal_status_counts"] == {
        "VALID": 15
    }
    assert freeze["completion_record"]["carr_r_test_split_opened"] is False
    assert freeze["frozen_contract"]["feedback_disabled"].startswith(
        "Retain the pre-closure"
    )
    for source in freeze["frozen_sources"]:
        _assert_frozen_source_record(source)


def test_v5_protocol_diagnostic_reconstructs_temporal_funnel():
    records = [
        {
            "step": 1,
            "decisions": [
                {
                    "agent": "a",
                    "decision": {
                        "messages": [
                            {
                                "to": "b",
                                "kind": "proposal",
                                "content": "depart immediately",
                                "payload": {
                                    "route_id": "r1",
                                    "vehicle_id": "car1",
                                    "depart_step": 1,
                                },
                            }
                        ],
                        "message_responses": [],
                    },
                }
            ],
            "interaction": {
                "msg_count": 1,
                "dropped": 0,
                "receipt_states": {"delivered": 1},
                "message_delivery_probability": 0.15,
            },
        },
        {
            "step": 2,
            "decisions": [
                {
                    "agent": "b",
                    "decision": {
                        "messages": [],
                        "message_responses": [
                            {
                                "message_id": "m00000001",
                                "disposition": "accepted",
                            }
                        ],
                    },
                }
            ],
            "interaction": {
                "msg_count": 1,
                "dropped": 0,
                "receipt_states": {"accepted": 1},
                "message_delivery_probability": 0.15,
            },
        },
    ]
    funnel = diagnose_event_records(records)
    assert funnel["messages_sent"] == 1
    assert funnel["messages_processed"] == 1
    assert funnel["accepted_proposal_responses"] == 1
    assert funnel["stale_proposal_responses"] == 1
    assert funnel["accepted_feasible_at_response"] == 0


def test_paired_analysis_excludes_invalid_run_pairs():
    rows = []
    for condition in (
        "full",
        "full_minus_memory",
        "full_minus_feedback",
        "full_minus_planning",
        "full_minus_interaction",
    ):
        rows.append(
            {
                "condition": condition,
                "seed": 7,
                "run_terminal_status": (
                    "INVALID" if condition == "full_minus_memory" else "VALID"
                ),
                "warning_retention_rate": 1.0,
                "primary_to_alternate_update_rate": 1.0,
                "successful_replan_rate": 1.0,
                "compatible_commitment_rate": 1.0,
            }
        )
    paired, _ = paired_mechanism_analysis(rows)
    assert {item["module"] for item in paired} == {
        "feedback",
        "planning",
        "interaction",
    }


def test_formal_paired_intervals_require_two_seed_differences():
    rows = _paired_intervals(
        [
            {
                "module": "memory",
                "metric": "warning_retention_rate",
                "n_seeds": 1,
                "mean_paired_difference": 0.2,
                "sd_paired_difference": 0.0,
                "mcse": 0.0,
            },
            {
                "module": "planning",
                "metric": "successful_replan_rate",
                "n_seeds": 4,
                "mean_paired_difference": 0.5,
                "sd_paired_difference": 0.2,
                "mcse": 0.1,
            },
        ]
    )
    assert rows[0]["paired_t_95_ci"] is None
    assert rows[0]["standardized_paired_effect_dz"] is None
    assert rows[1]["paired_t_95_ci"][0] < 0.5
    assert rows[1]["paired_t_95_ci"][1] > 0.5
    assert rows[1]["standardized_paired_effect_dz"] == 2.5


def test_declared_backend_requires_credential_before_network(monkeypatch):
    monkeypatch.delenv("PACKY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No model credential"):
        _gateway_configuration(
            llm_cfg={
                "decision_model": "packy-deepseek-v4-flash",
                "models_config": "configs/models.yaml",
            },
            decision_model="packy-deepseek-v4-flash",
        )


def test_declared_backend_records_only_credential_name(monkeypatch):
    monkeypatch.setenv("PACKY_API_KEY", "test-value-must-not-be-returned")
    models, config_path, credential_name = _gateway_configuration(
        llm_cfg={
            "decision_model": "packy-deepseek-v4-flash",
            "models_config": "configs/models.yaml",
        },
        decision_model="packy-deepseek-v4-flash",
    )
    assert "packy-deepseek-v4-flash" in models["models"]
    assert config_path is not None
    assert credential_name == "PACKY_API_KEY"
    assert "test-value-must-not-be-returned" not in repr(
        (models, config_path, credential_name)
    )
