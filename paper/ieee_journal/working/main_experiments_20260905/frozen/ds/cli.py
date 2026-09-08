"""DisasterSociety CLI (spec §0, cli.py).

    ds run --config configs/toy_village.yaml     # run a simulation
    ds sir-check --n 500 --seed 1                 # diffusion mechanism pre-check
    ds report experiments/runs/<run_dir>          # (re)build the HTML report
    ds selftest                                   # quick offline sanity run
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich import print as rprint

app = typer.Typer(add_completion=False, help="DisasterSociety simulation CLI")


@app.command()
def run(
    config: str = typer.Option(..., "--config", "-c", help="run config yaml"),
    seed: int = typer.Option(None, "--seed", help="override seed"),
    runs_dir: str = typer.Option("experiments/runs", help="output root"),
    report: bool = typer.Option(True, help="emit HTML report"),
):
    """Run a simulation from a config file."""
    import ds.config as config_mod
    from experiments.toy.runner import run_toy

    cfg = config_mod.load(config)
    if seed is not None:
        cfg = cfg.override(seed=seed)
    cfg_d = cfg.model_dump()
    world_type = cfg_d.get("world", {}).get("type", "toy_grid")
    if world_type != "toy_grid":
        rprint(f"[red]world type '{world_type}' is not implemented.[/red]")
        raise typer.Exit(1)

    res = run_toy(cfg_d, runs_dir=runs_dir)
    rprint(f"[green]run complete[/green] -> {res.run_dir}")
    rprint(res.summary["world_final"])
    rprint(res.summary["gateway"])
    if report:
        from ds.eval.report import build_report

        out = build_report(res.run_dir)
        rprint(f"report: {out}")


@app.command("sir-check")
def sir_check(
    n: int = typer.Option(500, help="number of nodes"),
    seed: int = typer.Option(1, help="rng seed"),
    p: float = typer.Option(0.25, help="per-edge transmission prob"),
    steps: int = typer.Option(30, help="diffusion steps"),
):
    """Rule-agent information diffusion vs a matched reference curve."""
    from experiments.toy.sir_check import run_sir_check

    result = run_sir_check(n=n, seed=seed, p=p, steps=steps)
    rprint(f"[bold]diffusion mechanism pre-check[/bold]  n={n} p={p} R0={result['r0']:.2f}")
    rprint(f"  cascade RMSE (agents vs independent-cascade): {result['rmse_cascade']:.4f}")
    rprint(f"  final informed fraction — agents: {result['final_agent']:.3f}, "
           f"reference: {result['final_ref']:.3f}")
    rmse_ok = result["rmse_cascade"] < result["threshold"]
    spread_ok = result["spread_ok"]
    ok = rmse_ok and spread_ok
    rprint(f"  spread reached {result['final_agent']:.0%} "
           f"(need ≥{result['min_spread']:.0%}): "
           f"[{'green' if spread_ok else 'red'}]{'OK' if spread_ok else 'TOO WEAK'}[/]")
    rprint(f"  [{'green' if ok else 'red'}]{'PASS' if ok else 'FAIL'}[/] "
           f"(RMSE threshold {result['threshold']})")


@app.command()
def report(run_dir: str = typer.Argument(..., help="a run output directory")):
    """(Re)build the one-page HTML report for a finished run."""
    from ds.eval.report import build_report

    out = build_report(run_dir)
    rprint(f"report: {out}")


@app.command()
def selftest():
    """Quick offline sanity run (mock backend, 50 agents)."""
    import ds.config as config_mod
    from experiments.toy.runner import run_toy

    cfg = config_mod.load("configs/toy_village.yaml").model_dump()
    res = run_toy(cfg, runs_dir="experiments/runs")
    gw = res.summary["gateway"]
    assert gw["fallback_rate"] == 0.0
    rprint(f"[green]selftest OK[/green] evac_all={res.evac_rate():.2f} "
           f"cost=${gw['spent']} calls={gw['n_ok']}")


if __name__ == "__main__":
    app()
