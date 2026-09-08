# Pre-experiment claim–evidence map

This map records what the current manuscript is allowed to say. Workspace code
and project ledgers remain authoritative if this note becomes stale.

| Manuscript claim | Primary local evidence | External framing | Boundary retained in prose |
|---|---|---|---|
| Resident intention cannot directly mutate physical state | `disastersociety/ds/kernel/engine.py`; `ds/kernel/actions.py`; `ds/agents/state.py`; `ds/world/carr.py` | ReAct; Reflexion | Language feedback may revise a proposal; deterministic code owns physical execution |
| Resident cognition, household state, and world state are distinct | `ds/agents/state.py`; `ds/households/state.py`; `docs/METHOD_DESIGN_DECISIONS.md` | ODD documentation protocol | Household is not a unified LLM; co-residence does not synchronize private cognition |
| Kernel follows an explicit event/decision/interaction/arbitration order | `ds/kernel/engine.py` | ABM verification literature | Adapter-specific message timing is disclosed; only verified invariants are generalized |
| EventPack is a reusable scenario interface | `ds/eventpack/schema.py`; `ds/eventpack/loader.py`; Carr manifest | — | Current E1 and E2 adapters do not both use an identical loader path; checksums are not yet enforced |
| Population construction preserves whole donor households | `ds/population/synth.py`; population QA | Beckman; Ye; Pritchard; Guo and Bhat | Only selected household margins are fitted; person distributions are diagnostics |
| E1 defines a richer Carr-informed process adapter | `experiments/carr/empirical_v2_runner.py`; `ds/agents/carr_empirical_v2.py`; `ds/world/carr_empirical_v2.py` | Protective-action and household literature | Controlled scenario, not historical reconstruction; current formal artifacts are diagnostic because terminal wake/repeat-departure, message, arbitration, and summary defects require correction and rerun |
| E2 provides switchable memory, feedback, planning, and interaction | `ds/agents/carr.py`; `ds/interaction/engine.py`; `experiments/carr/runner.py` | Generative Agents | Manipulations are scenario-specific; memory is warning-history retention, not general semantic recall |
| Commitments are distinct from messages and execution | `ds/households/state.py`; `ds/interaction/engine.py`; world adapters | Household coordination literature | E1 social messages are message-level, so mutual acknowledgment is not inferred |
| Evaluation separates scale from evidence type | `disastersociety/experiments/analysis_plan.md`; `docs/PAPER_STRATEGY.md` | Sargent; Klügl; pattern-oriented modeling; sensitivity/DOE literature | Engineering validation, empirical reasonableness, mechanism ablation, and robustness are not interchangeable |
| Carr evidence is bounded | `docs/EVIDENCE_LEDGER.md`; `docs/EXPERIMENT_MASTER_PLAN.md`; Carr protocol files | Carr survey studies | Opened diagnostic split is not an untouched holdout; calibrated warning reception is not independent validation |

## Figure-to-claim linkage

- Figure 1 motivates the problem and illustrates a controlled running example;
  it is not empirical evidence about the historical Carr Fire.
- Figure 2 describes the target/shared platform contracts; text and the adapter
  table identify which parts are currently E1-specific or E2-specific.
- Figure 3 visualizes the shared causal loop; the detailed recipient receipt
  chain corresponds to E2, while E1 social messages currently use a message-level
  record.

## Result-writing gate

Do not draft quantitative Results from filenames or old prose. Current E1 runs
contain post-safe-arrival decisions/messages and repeated departure records, so
filtering summaries after the fact cannot recover an unaffected social trajectory;
fix and rerun that path. For every experiment, first synchronize
the current evidence ledger, terminal summaries, exclusions, model/call logs,
provenance, and metric denominators. Any E1 outcome must be recomputed from
member locations and party ledgers rather than trusting the current convenience
labels.
