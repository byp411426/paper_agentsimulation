"""M1.5 mechanism pre-check test (spec §5.5). Pure rule agents, no LLM."""

from __future__ import annotations

from experiments.toy.sir_check import run_sir_check


def test_diffusion_matches_reference_supercritical():
    """Agent forwarding reproduces the analytic cascade curve when it spreads."""
    r = run_sir_check(n=400, seed=1, p=0.25, steps=30, trials=30, degree=10)
    assert r["r0"] > 1.0                       # supercritical regime
    assert r["spread_ok"]                       # diffusion actually spread (>=50%)
    assert r["rmse_cascade"] < r["threshold"]   # matches the reference curve


def test_subcritical_dies_out():
    """Below the epidemic threshold the cascade fizzles — a sanity floor."""
    r = run_sir_check(n=400, seed=2, p=0.03, steps=30, trials=30, degree=6)
    assert r["r0"] < 1.0
    assert r["final_agent"] < 0.2               # stays small
    # even in the trivial regime the two code paths must agree
    assert r["rmse_cascade"] < r["threshold"]


def test_diffusion_is_deterministic():
    r1 = run_sir_check(n=300, seed=7, p=0.25, steps=20, trials=10)
    r2 = run_sir_check(n=300, seed=7, p=0.25, steps=20, trials=10)
    assert r1["agent_curve"] == r2["agent_curve"]
