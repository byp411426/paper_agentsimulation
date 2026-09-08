"""Offline protocol checks for the natural-timing Carr-S E1 scenario."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from experiments.carr.empirical_runner import build_empirical_parts


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/carr/configs/carr_s_e1_empirical_deepseek_v1.yaml"
EVENTPACK = ROOT / "eventpacks/carr_2018"


def test_e1_config_requires_real_backend_and_keeps_carr_r_test_sealed():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["llm"]["decision_model"] == "packy-deepseek-v4-flash"
    assert cfg["experiment"]["formal_protocol"]["use_mock_for_behavior_evidence"] is False
    assert cfg["experiment"]["formal_protocol"]["carr_r_test_split_opened"] is False
    assert cfg["experiment"]["maximum_decision_adults_per_household"] == 2
    assert cfg["experiment"]["n_households"] == 50
    assert len(cfg["experiment"]["formal_protocol"]["seeds"]) == 5


def test_e1_preflight_has_natural_timing_households_and_network():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parts = build_empirical_parts(
        cfg=cfg,
        seed=3109,
        eventpack_root=EVENTPACK,
    )
    assert len(parts["households"]) == 50
    assert 50 <= len(parts["agents"]) <= 100
    assert all(
        1 <= len(household.decision_member_ids) <= 2
        for household in parts["households"].values()
    )
    assert parts["social_graph"].number_of_nodes() == len(parts["agents"])
    assert parts["social_graph"].number_of_edges() > len(parts["agents"])
    assert len(parts["events"].events) == 1
    assert parts["events"].events[0].step == cfg["experiment"]["order_step"]
    assert not any(agent.plan is not None for agent in parts["agents"])


def test_e1_prompt_contains_no_controlled_departure_target():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parts = build_empirical_parts(
        cfg=cfg,
        seed=3109,
        eventpack_root=EVENTPACK,
    )
    agent = parts["agents"][0]
    messages = agent._carr_messages(world=parts["world"], step=1)
    state_text = messages[1]["content"].removeprefix("EMPIRICAL_STATE_JSON=")
    state = json.loads(state_text)
    assert "controlled_depart_step" not in state
    assert state["current_plan"] is None
    assert state["accepted_commitments"] == []
    assert state["earliest_proposal_depart_step"] == 2
    assert "There is no preset departure time" in messages[0]["content"]
