"""Agent data-layer tests: memory eviction (v2 fix) + trust direction."""

from __future__ import annotations

from types import SimpleNamespace

from ds.agents.decide import Decision
from ds.agents.memory import Memory, MemoryItem
from ds.agents.state import Resident
from ds.agents.trust import Trust


def test_memory_evicts_low_importance_old_first():
    m = Memory(capacity=4)
    # fill with low-importance observations across increasing steps
    for s in range(4):
        m.write_text(step=s, text=f"obs{s}", kind="observation")  # importance 2
    # one more -> must evict the OLDEST low-importance (obs0), keep obs1..obs3
    m.write_text(step=4, text="obs4", kind="observation")
    texts = {i.text for i in m.items}
    assert "obs0" not in texts
    assert {"obs1", "obs2", "obs3", "obs4"} == texts


def test_memory_never_evicts_protected():
    m = Memory(capacity=3)
    m.write_text(step=0, text="WARNING issued", kind="warning")   # protected
    m.write_text(step=1, text="family unsafe", kind="family")     # protected
    m.write_text(step=2, text="injury", kind="injury")            # protected
    # add many low-importance observations; capacity is 3 but protected must survive
    for s in range(3, 10):
        m.write_text(step=s, text=f"obs{s}", kind="observation")
    kinds = [i.kind for i in m.items]
    assert kinds.count("warning") == 1
    assert kinds.count("family") == 1
    assert kinds.count("injury") == 1


def test_memory_recall_orders_by_importance_and_recency():
    m = Memory(capacity=50)
    m.write_text(step=0, text="old low", kind="observation")       # imp 2
    m.write_text(step=10, text="fresh warning", kind="warning")    # imp 5
    top = m.recall(step=10, k=1)
    assert top == ["fresh warning"]


def test_trust_moves_toward_verified():
    t = Trust(prior=0.5, lr=0.2)
    before = t.get("official")
    t.update("official", verified=True)
    assert t.get("official") > before  # verified -> up
    t2 = Trust(prior=0.5, lr=0.2)
    t2.update("social", verified=False)
    assert t2.get("social") < 0.5      # refuted -> down


def test_trust_converges_to_one_with_repeated_verification():
    t = Trust(prior=0.5, lr=0.3)
    for _ in range(50):
        t.update("neighbor", verified=True)
    assert t.get("neighbor") > 0.99


def test_rejected_intent_does_not_commit_evacuation():
    resident = Resident("r1")
    decision = Decision(
        action="evacuate",
        remember=["I intended to leave but the route was blocked."],
    )
    rejected = SimpleNamespace(
        status="rejected", executed_action=None, reason="closed road"
    )

    resident.commit_execution(decision, rejected, step=4)

    assert resident.state.last_intent == "evacuate"
    assert resident.state.last_action == "stay"
    assert resident.state.last_outcome == "rejected"
    assert resident.state.evacuating is False
    assert resident.state.evac_step == -1
    assert resident.memory.items[-1].kind == "reflection"


def test_executed_evacuation_commits_after_world_outcome():
    resident = Resident("r1")
    decision = Decision(action="evacuate")
    executed = SimpleNamespace(status="executed", executed_action="evacuate")

    resident.commit_execution(decision, executed, step=4)

    assert resident.state.evacuating is True
    assert resident.state.evac_step == 4
    assert resident.state.last_action == "evacuate"
