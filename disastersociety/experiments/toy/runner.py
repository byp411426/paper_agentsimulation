"""Toy-village runner (spec M1) — wires the pipeline and runs the engine.

Used by tests and the CLI. Deterministic given (config, seed): with the mock
backend the whole run is reproducible and free. Returns a small result object with
helpers the acceptance tests assert on (evac rate by warned/unwarned).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ds.agents.state import Resident, StaticAttrs
from ds.eventpack.loader import toy_warning_events
from ds.interaction.delivery import DeliveryModel
from ds.interaction.engine import InteractionEngine
from ds.kernel.engine import Engine
from ds.kernel.logger import RunLogger
from ds.kernel.rng import derive
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from ds.provenance import write_provenance
from ds.world.toy import ToyWorld


@dataclass
class ToyResult:
    summary: dict
    world: ToyWorld
    interaction: InteractionEngine
    agents: list
    run_dir: Path

    def evac_rate(self, warned: bool | None = None) -> float:
        if warned is None:
            pool = self.agents
        else:
            pool = [a for a in self.agents if a.state.warned == warned]
        if not pool:
            return 0.0
        return sum(a.state.evacuating for a in pool) / len(pool)

    def evac_rate_by_step(self, step: int, warned: bool | None = None) -> float:
        """Fraction who had STARTED evacuating by `step` (timing contrast)."""
        if warned is None:
            pool = self.agents
        else:
            pool = [a for a in self.agents if a.state.warned == warned]
        if not pool:
            return 0.0
        started = sum(1 for a in pool
                      if 0 <= a.state.evac_step <= step)
        return started / len(pool)

    def mean_evac_step(self, warned: bool | None = None) -> float:
        if warned is None:
            pool = self.agents
        else:
            pool = [a for a in self.agents if a.state.warned == warned]
        steps = [a.state.evac_step for a in pool if a.state.evac_step >= 0]
        return sum(steps) / len(steps) if steps else float("nan")


def build_toy(cfg: dict, run_seed: int, gateway: LLMGateway) -> dict:
    world_cfg = cfg.get("world", {})
    pop_cfg = cfg.get("population", {})
    ix_cfg = cfg.get("interaction", {})

    size = tuple(world_cfg.get("grid_size", [10, 10]))
    world = ToyWorld(
        size=size,
        fire_origin=tuple(world_cfg.get("fire_origin", [8, 8])),
        spread_prob=world_cfg.get("fire_spread_prob", 0.35),
        run_seed=run_seed,
    )

    n = pop_cfg.get("n_agents", 50)
    panic_frac = pop_cfg.get("trait_panic_prone", 0.3)
    agents: list[Resident] = []
    for i in range(n):
        rng = derive(run_seed, "spawn", i)
        # scatter homes across the grid deterministically
        hx = (rng % size[0])
        hy = ((rng // size[0]) % size[1])
        panic = (rng / (2**32)) < panic_frac
        a = Resident(
            agent_id=f"a{i:04d}",
            static=StaticAttrs(household_id=f"h{i:04d}", home=(hx, hy)),
            traits="panic-prone, acts fast" if panic else "cautious, trusts officials",
            persona=f"resident {i}",
            panic_prone=panic,
        )
        agents.append(a)
    world.bind_agents(agents)

    interaction = InteractionEngine(
        agents_by_id={a.id: a for a in agents},
        delivery=DeliveryModel(
            device_ownership=ix_cfg.get("device_ownership", 0.9),
            coverage=ix_cfg.get("coverage", 0.85),
        ),
    )
    events = toy_warning_events(ix_cfg.get("warning_step", 6))
    return {"world": world, "agents": agents, "interaction": interaction,
            "events": events}


def run_toy(cfg: dict, *, run_seed: int | None = None,
            runs_dir: str | Path = "experiments/runs") -> ToyResult:
    run = cfg.get("run", {})
    run_id = run.get("run_id", "toy")
    seed = run_seed if run_seed is not None else run.get("seed", 0)
    total_steps = run.get("total_steps", 48)
    step_minutes = run.get("step_minutes", 30)
    llm = cfg.get("llm", {})

    models_cfg = {"models": {"mock": {"backend": "mock", "input_per_m": 0.0,
                                      "output_per_m": 0.0}}}
    run_dir = Path(runs_dir) / f"{run_id}_seed{seed}"
    gateway = LLMGateway(
        run_id=f"{run_id}_seed{seed}",
        models_cfg=models_cfg,
        budget_usd=llm.get("budget_usd", 5.0),
        max_concurrency=llm.get("max_concurrency", 16),
        log_dir=runs_dir,
        cache=LLMCache(run_dir / "cache.sqlite"),
    )
    parts = build_toy(cfg, seed, gateway)
    logger = RunLogger(run_dir)
    write_provenance(run_dir, config=cfg, models=["mock"])

    engine = Engine(
        run_seed=seed, total_steps=total_steps, step_minutes=step_minutes,
        world=parts["world"], agents=parts["agents"],
        interaction=parts["interaction"], events=parts["events"],
        gateway=gateway, logger=logger, decision_model="mock",
        temperature=llm.get("temperature", 0.7),
        fallback_threshold=llm.get("fallback_threshold", 0.01),
    )
    try:
        summary = asyncio.run(engine.run())
    finally:
        logger.close()
        gateway.close()
    return ToyResult(summary=summary, world=parts["world"],
                     interaction=parts["interaction"], agents=parts["agents"],
                     run_dir=run_dir)
