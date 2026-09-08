# DisasterSociety

Disaster-native generative-agent social simulation framework.

The active research direction is defined in:

- `../AGENTS.md`
- `../docs/PAPER_STRATEGY.md`
- `../docs/EVIDENCE_LEDGER.md`
- `../docs/METHOD_DESIGN_DECISIONS.md`
- `experiments/analysis_plan.md`

## Status

Research prototype under active validation:

- [x] LLM gateway (cache / budget fuse / provenance / structured output)
- [x] Toy village end-to-end smoke test
- [x] Rule-agent diffusion vs reference mechanism pre-check
- [x] Carr data assets, manifest, and historical baseline artifacts
- [x] Archived simplified Carr runs, including a 1,000-agent pilot
- [x] Correct Carr evacuation and timing labels; freeze 330-person evaluation set
- [x] Separate intention from executed state; isolate component RNG streams
- [x] Correct logical fallback accounting and write VALID/INVALID/ABORTED summaries
- [x] Implement tested WGTP/tract/whole-donor population-synthesis foundations
- [x] Implement Household vehicle, commitment, batch, and message-state foundations
- [x] Run and verify the canonical Carr raw donor build and tract QA
- [x] Validate EventPack manifests/assets and load warning/control events
- [x] Freeze the non-identifying Carr-R split, field roles, and inconsistency rule
- [x] Run Carr-R traditional validation baselines while keeping test sealed
- [x] Re-evaluate stored demographic-only DeepSeek responses on corrected validation labels
- [ ] Run the new gateway-controlled DeepSeek validation pilot (credential not loaded)
- [x] Run a zero-cost controlled Carr-S full/drop-one development pilot
- [x] Run a paired non-saturated Carr-S mock pilot with informative seed variance
- [x] Run a three-scenario Carr-S mock robustness development grid
- [x] Integrate sourced TIGER route candidates into the common Carr World
- [x] Add a declared DeepSeek backend path with credential, cache, budget, and provenance gates
- [ ] Run the DeepSeek Carr-S connectivity check and backend pilot (credential not loaded)
- [ ] Freeze formal Carr-S prompt, seed count, and controlled obstruction protocol
- [x] Implement and validate the EventPack schema/loader foundation
- [x] Integrate the controlled Carr case with the full multi-step kernel
- [ ] Run claim-aligned ablations, robustness, and efficiency experiments

Existing Carr F1 and group-distance results are development artifacts, not
publication-grade validation. The old Carr-specific engine and misleading
`e1_dynamic.py` entry point are preserved under `../archive/legacy_2026-07-31/`;
they are not active implementation paths. See `../docs/EVIDENCE_LEDGER.md`.

## Design red lines

1. Physics is formula, cognition is LLM — **no LLM call inside the world engine**.
2. No in-simulation judge rewriting answers; residents do not self-evolve weights.
3. Failures are never silent — completed runs are `VALID` or `INVALID`, incomplete
   runs are `ABORTED`, and every terminal state retains a summary. Logical fallback
   rate is `n_fallback/(n_ok+n_cache+n_fallback)`; 1% is the final project gate.
4. Initialization, calibration, and evaluation targets remain explicitly separated.
5. Agent-facing prompts are English (simulating US residents; aligned with FLARE).
6. Everything random is reproducible and component-isolated; condition names do
   not enter common exogenous random stream keys.
7. Platform value is evaluated through system, behavioral, mechanism, robustness,
   and efficiency evidence; individual prediction accuracy is auxiliary.

## Quickstart

```bash
uv venv --python 3.13
uv pip install -e ".[ml,dev,analysis]"

# run the offline test suite (mock backend, zero cost, no network)
uv run --extra dev --extra ml pytest -q

# run frozen Carr-R traditional validation baselines; test remains sealed
uv run --extra ml python experiments/baselines/train_carr_r_frozen.py

# after setting PACKY_API_KEY, LLM_API_KEY, or OPENAI_API_KEY, check connectivity
uv run --extra ml python experiments/baselines/run_carr_r_deepseek.py --connectivity-limit 1

# check the declared DeepSeek backend on one full-loop Carr-S household
uv run python scripts/run_carr_backend_pilot.py --connectivity-check --seeds 101

# after the connectivity gate passes, run the small Carr-S backend pilot
uv run python scripts/run_carr_backend_pilot.py --seeds 101 202

# run the toy village with the deterministic mock backend
uv run ds run --config configs/toy_village.yaml

# mechanism pre-check: rule-agent diffusion vs a matched reference
uv run ds sir-check --n 500 --seed 1
```

## Layout

```
ds/
  llm/          gateway, cache, backends, pricing
  kernel/       clock, rng, logger, engine
  agents/       state, memory, trust, decide
  interaction/  messages, delivery, engine
  world/        toy world and queue model
  population/   IPF and tested whole-donor household/person synthesis
  eventpack/    validated manifest/assets and event loaders
  eval/         individual, group, mechanism, cost, report
  cli.py
configs/        yaml run configs + models.yaml price table
experiments/    toy / baselines / Carr diagnostics / run artifacts
tests/          offline CI suite (mock backend)
```
