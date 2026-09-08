# DisasterSociety Analysis Plan

**Status**: method architecture decided; Carr-R reduced to an auxiliary diagnostic and its former test split is `OPENED_FOR_DIAGNOSTIC`; E2 v8 publication-facing DeepSeek matrix is running under the frozen r4 recovery; E1 v1 was superseded before paid execution and E1 v2, human review, prompt sensitivity, final cross-model checks and scale experiments remain open
**Updated**: 2026-08-02
**Scope**: first framework paper, Carr-informed controlled case

This plan replaces the former E0–E6 accuracy-centered plan. The core Carr label
and time audit passed on 2026-07-31. The experiment codes and their current
states are summarized in `docs/EXPERIMENT_MASTER_PLAN.md`; version numbers such
as v5/v6/v8 identify protocol history, not different paper contributions.

## 1. General rules

- Every experiment names the paper claim it tests.
- Every claim records both its analysis scale (individual, household/network,
  group, or system operation) and evidence type (system verification,
  empirical/behavioral validity, mechanism ablation, or robustness/efficiency).
- These are two independent dimensions; a complete 4-by-4 matrix is not required.
- Calibration data and evaluation targets are recorded separately.
- Carr-R respondent evaluation and Carr-S synthetic social-process evaluation
  are separate tracks and are never forced into one-to-one correspondence.
- Every Carr-R field is assigned exactly one role within an experiment:
  runtime input, calibration, evaluation-only, or excluded. The same variable
  cannot be both runtime input and evaluation target in that experiment.
- Formal comparisons use the same agents, data split, event inputs, and exclusion rules.
- Multi-run comparisons use paired random seeds and component-isolated common
  exogenous random streams. Condition names are not part of common stream keys.
- Report the full condition matrix, including null and unfavorable results.
- The independent replication unit is a seed-by-condition run, not a resident,
  household, or resident-step. Within-run records are nested observations.
- Completed runs are classified `VALID` or `INVALID`; incomplete runs are
  `ABORTED`. Every terminal state writes a summary and retains its artifacts.
- Logical fallback rate is
  `n_fallback / (n_ok + n_cache + n_fallback)`. Backend `n_failed` is a
  separate reliability diagnostic. The final 1% gate is a project engineering
  threshold, not a universal scientific standard and not an early-step stop rule.
- Accuracy, Macro-F1, Brier, and ECE are auxiliary unless the explicit task is
  individual evacuation prediction.
- No metric may be introduced after seeing results solely to rescue a module claim.

## 2. S0: system verification

**Claim**: the framework executes disaster-agent experiments reproducibly and
records enough information for audit.

**Primary analysis scale**: system operation.

**Evidence type**: system verification.

Primary evidence:

- unit and integration test pass rate;
- deterministic replay under mock or cached conditions;
- event-order and state invariants;
- LLM request success, failure, fallback, and cache counts;
- run configuration, model, seed, prompt version, and data provenance;
- wall-clock time, tokens, and cost.

Passing S0 establishes software reliability only. It does not establish behavioral realism.

## 3. R0: Carr-R respondent diagnostic

**Claim**: the available respondent information has a measurable but limited
ability to distinguish individual evacuation outcomes.

**Analysis scale**: individual.

**Evidence type**: auxiliary empirical diagnostic.

### R0a. Respondent-conditioned information-sufficiency evaluation

Carr-R is now an auxiliary information-sufficiency diagnostic, not a formal
test gate. The two completed validation-only DeepSeek runs used the same 66
respondents and four coarse demographic inputs; both failed to identify any of
the seven non-evacuees. A subsequent full-data feature audit showed that Carr
contains additional structural, order-exposure and retrospective pre-decision
belief fields, so the four-field result supports only the claim that those four
inputs are insufficient. Because that audit examined feature-outcome relations
for all 330 eligible respondents, the former 66-person test split is now
`OPENED_FOR_DIAGNOSTIC` and may not be described as untouched holdout evidence.

Any retained Carr-R result reports Macro-F1, Brier, ECE and the fixed-label
confusion matrix together, explicitly states the decision-time information set,
and is labelled development diagnostic or cross-validation unless a genuinely
new external holdout is obtained. Carr-R does not evaluate household
coordination, and the framework is not required to outperform every predictive
baseline.

## 4. E1: Carr-S empirical reasonableness and social-process evidence

**Claim**: the simulation produces behavior processes and group patterns that
are compatible with available empirical references and executable domain
constraints.

**Analysis scales**: individual, household/network, and group.

**Evidence type**: empirical and behavioral validity.

### E1a. Empirical references and group patterns

Where independent data are available:

| Quantity | Candidate metric |
|---|---|
| evacuation proportion | absolute error and confidence interval |
| departure-time distribution | Wasserstein distance and distribution plot |
| cumulative evacuation curve | KS distance and RMSE |
| warning-channel prevalence | per-channel percentage-point error and interval; mean absolute percentage-point error |
| subgroup differences | signed gap error with uncertainty |

Carr `Q6.1/Q7.1` is multi-select prevalence, not an exclusive probability
distribution or first-heard share. Do not normalize it and compute L1/JS.
The current delivery calibration target cannot also serve as independent
channel validation. Until sampling design, weights, target population and
estimand are aligned, Carr survey patterns are respondent-sample references.

### E1b. Carr-S process validity

| Process property | Metric |
|---|---|
| temporal legality | proportion of actions violating event order |
| state-action consistency | contradiction rate |
| resource feasibility | vehicle, household, shelter, and route constraint violations |
| household coordination | incompatible commitments, resource conflicts, dependent left behind; departure-time gap is descriptive |
| network communication | sent/delivered/processed/accepted reach, delay, help-response rate |
| narrative plausibility | blinded human or expert rating with inter-rater agreement |

Plausibility ratings use blinded review and inter-rater agreement. They
supplement rather than replace empirical and executable-constraint evidence.

### E1c. Current protocol status

Carr-S E1 aggregate survey references are frozen under protocol v1.1. The
Q9.1 respondent-sample evacuation rate is 0.8879 (Wilson 95% CI
0.8493–0.9176). The main nonnegative, internally consistent first-order-to-
departure lag cohort has n=186, median 1 hour, and 0.7742 departing within five
hours; the affirmative-order-priority sensitivity cohort has n=194 and 0.7732
within five hours. Age, household-size, and income gaps are estimable with
bootstrap intervals crossing zero. The declared zero-vehicle contrast is
unavailable because its group has n=0 and was not replaced. These are reference
construction results, not Carr-S behavioral-validity results.

The Carr-S E1 natural-timing v1 code and freeze are retained but classified
`SUPERSEDED_BEFORE_PAID_EXECUTION`. It was never run on a paid backend. Its
resident state contains only age, disability, household size, vehicles, income
and structure; the first adult is automatically coordinator, vehicle capacity
is at least household size, and all households share one hazard trajectory and
a step-1 mandatory order. That design cannot support an overall Carr empirical-
reasonableness claim and must not be executed merely because it is runnable.

E1 v2 is the active empirical design. A new whole-household PUMS donor retains
predeclared static employment, education/commute, housing, access, relationship
and disability fields. Carr train-only records supply complete, non-outcome-
conditioned latent trait blocks (for example retrospective pre-decision risk and
friction factors, prior experience, pets, decision role and trust). Orders,
channels, hazard, roads and messages enter only as time-stamped dynamic events.
Q9.1, Q10/Q11 branches, departure fields, Q13.6, post-event behavior, identity,
addresses and free text never enter the resident prompt. After offline lineage
and leakage QA, E1 v2 receives a small real DeepSeek preflight, then a newly
frozen full-only formal design whose cohort and model/delivery seeds both vary.
Paid E1 work must not overlap E2 r4.

## 5. E2: mechanism contribution

**Claim**: memory, feedback, planning, and interaction change the processes they
are designed to represent.

**Analysis scales**: individual, household/network, and group, depending on module.

**Evidence type**: mechanism ablation.

Core conditions:

1. static one-shot decision (auxiliary reference, not a module ablation);
2. full;
3. full minus memory;
4. full minus feedback;
5. full minus planning;
6. full minus interaction;
7. optional full minus household coordination.

Each drop-one condition estimates the conditional effect of removing that
module while the remaining full-system modules are present. It does not identify
a universal independent module effect or module interactions.

| Module | Primary construct | Candidate metrics |
|---|---|---|
| memory | controlled cross-time retention | retention of predeclared relevant events; unsupported contradiction under unchanged evidence |
| feedback | adaptation to a predeclared perturbation | directionally correct update within a fixed latency window |
| planning | constrained multi-step action | after obstruction, a new plan passes deterministic feasibility checks and enters execution |
| interaction | transmission and coordination | after the controlled disruption and delivered/processed messages, a temporally feasible commitment forms without shared-resource conflict |

Analysis:

- paired seeds;
- common initial population, hazard input and component-isolated exogenous
  streams derived from `(run_seed, stream_name, entity_id, step, draw_index)`;
- effect estimate with 95% interval;
- paired test appropriate to the outcome;
- standardized effect size where meaningful;
- no universal “number of modules that must be significant” threshold.

A module claim is supported only if its target metric changes consistently in
the predicted direction. Improvement in F1 is neither necessary nor sufficient.

For each seed, first compute one run-level metric for full and the paired
drop-one condition, then analyze the paired difference across independent seeds.
Resident and household records are descriptive or enter a model with run and
household clustering. The formal seed count is frozen after pilot variance using
Monte Carlo standard error or a predeclared target interval half-width.

### Paused E2 v5 protocol and frozen v6 repair (2026-08-01)

E2 v5 stopped after the complete seed-101 and seed-202 batches, with all ten raw
runs and summaries preserved. The administrative pause is not based on interim
effect direction. A read-only audit found three design-validity failures:

- one 0.15 delivery probability was applied to both household direct messages
  and community propagation, so the household mechanism rarely received its
  intended exposure;
- messages delivered after one decision phase entered recipient cognition only
  in a later phase, while v5 permitted proposals whose departure time was
  already past when processed;
- the interaction metric required one exact route, vehicle, and fixed departure
  step instead of measuring validated commitment formation after an opportunity.

Across the two v5 full runs the observable funnel was 62 sent, 12 delivered, 7
processed, 1 accepted, and 0 accepted-and-feasible/current-compatible. Five
delivered messages remained unprocessed at the run endpoint. These facts make
the v5 matrix unsuitable for the intended interaction-effect claim. The other
14 v5 seeds will not be run, and v5 outcomes will not be pooled with v6.

The replacement E2 v6 contract is frozen as follows:

- `Resident` remains the decision unit and `Household` the resource/coordination
  unit; sender and recipient must be decision-capable members of that household;
- household direct-message delivery and community propagation have separate
  probabilities; the controlled mechanism-identification episode sets household
  DM to 1.0 and community delivery to 0.15;
- a proposal must schedule departure no earlier than the recipient processing
  phase, and an in-flight proposal cannot be replaced during that window;
- acceptance is checked against membership, vehicle ownership, non-empty route,
  and time feasibility; revisions cancel but retain the earlier commitment;
- primary metrics are conditional warning retention, primary-to-alternate plan
  update, successful replan, and post-closure feasible commitment formation;
- full and four drop-one conditions retain paired component-isolated seeds;
- the obstruction remains a controlled perturbation rather than a historical
  closure reconstruction. The Carr-R split was sealed when this E2 contract
  was frozen; its later diagnostic opening does not change E2's fixed cohort,
  inputs, conditions, metrics or seeds.

The frozen zero-cost validation used 20 households, five conditions, and ten
paired seeds. All 50 runs were `VALID`, with 12,520 logical decisions, zero
failures/fallback/cost, and no invalid proposal or acceptance attempt. Two
independent output directories produced the same complete matrix SHA-256. Every
full run formed feasible post-closure commitments and completed coordinated
household departures. All four mock drop-one differences were nevertheless
saturated at 1.0 with zero seed variance. Therefore the v6 software/metric
contract is frozen, but the formal seed count and formal paid matrix are not.

The subsequent DeepSeek V4 Flash thinking-high pilot used two households, five
conditions and paired seeds 101/202. Its selected ten cells were all `VALID`,
with 184 successful logical decisions and no failure or fallback. Mean paired
differences were memory 1.0, feedback 0.375, planning 0.5 and interaction 1.0;
both seed-specific differences were positive for every module. This remains a
`PILOT`: two-household proportions are coarse, and memory, planning and
interaction had zero observed paired-difference variance, so the result cannot
freeze a formal seed count.

A bounded E3 pilot then repeated the same two-seed, five-condition contract on
Qwen3.5-Plus, GLM-5 and MiniMax-M2.7 and combined them with the DeepSeek cells.
The final selected 40 cells were all `VALID`, comprising 944 successful logical
decisions with no failure or fallback. Across the eight descriptive
model-by-seed pairs, positive directions occurred for memory 8/8, feedback
3/8, planning 6/8 and interaction 6/8. MiniMax formed no primary-route plan in
either full run, so its zero feedback and planning contrasts also lack the
intended adaptation opportunity. These results identify model sensitivity;
they do not establish universal model independence. All four named model
families were accessed through one Packy proxy.

This freeze applies only to E2 protocol mechanics. E1 empirical targets,
blinded review, and the full E3 robustness matrix remain open Gate D items.

## 6. E3: robustness and efficiency

**Claim**: conclusions are not artifacts of one random seed, model endpoint, or
prompt wording, and the framework has a measurable operating envelope.

**Analysis scales**: every scale used by the repeated E1/E2 result, plus system operation.

**Evidence type**: robustness and efficiency.

Minimum matrix:

- multiple paired seeds;
- at least two model backends or model classes when budget permits;
- at least two semantically equivalent prompt formulations;
- 100, 500, and 1,000-agent scale points for system measurements.

### 6.1 Current E3 status

Current E3 status: the bounded backend-class component is complete as a
two-household `PILOT`; prompt sensitivity, final-design limited cross-model
confirmation and publication-facing scale points remain open. The old v6
cross-model matrix is diagnostic only and must not be promoted into final
model-independence evidence.

### 6.2 E2 development chain used to freeze the final design

That opportunity-eligible step is now complete as Carr-S v7: every condition
starts with the same private primary-route plan, resident route perception is
copied from rather than aliased to the true World, and only feedback-enabled
residents refresh that perception after the controlled closure. The DeepSeek
thinking-high pilot used four households, five conditions and three paired
seeds. All 15 selected runs were `VALID` (796 successful logical decisions,
zero failure/fallback). Mean paired differences were memory 1.000, feedback
0.958, planning 0.750 and interaction 0.917, positive in all three seeds.
This remains `PILOT`: three seeds are not a formal interval, several drop-side
metrics are structurally zero, and full-condition execution exposed commitment
adherence, vehicle-conflict and care-responsibility failures. The next gate was
therefore an execution-feedback repair plus a real-backend development recheck,
not immediate promotion to the formal E2 matrix.

The execution-feedback repair has now passed that development gate. The v8
prompt exposes the last plan failure, recent execution feedback and household
vehicle state, and clarifies that an accepted commitment must be executed with
the exact shared route/vehicle/departure signature. The diagnosed seed101 and
two subsequently frozen confirmation seeds (404/505) produced three `VALID`
full runs, 125 successful decisions, zero failure/fallback, mean coordinated
departure 0.917 and mean post-closure replanning 1.0. One confirmation seed
still produced one dependent-left-behind rejection and one resource conflict,
so execution is improved rather than mechanically perfect. This remains a
development `PILOT`; those development observations are not reused as
confirmatory seeds.

The publication-facing E2 v8 protocol was frozen on 2026-08-02 before new
outcomes were observed. It uses eight households, five full/drop-one
conditions and twelve new independent seeds (60 seed-condition runs) with the
DeepSeek V4 Flash thinking-high backend. The seed count starts from the v7
interaction paired-difference SD of 0.144338: nine runs meet MCSE 0.05, and
twelve were frozen conservatively for the prompt/cohort change. Module-specific
retention, update, replan and commitment metrics are reported as manipulation
checks. Predeclared downstream outcomes are complete safe household departure,
closed-route rejections, complete safe departure for planning, and coordinated
departure for interaction, with resource and care rejections as supporting
outcomes. This prevents a structurally-zero disabled-module state from being
the only mechanism evidence. All raw runs remain `PILOT` until the complete
matrix, exclusions, provenance and intervals pass the ledger audit. The later
Carr-R full-field diagnostic does not alter this already-frozen E2 design.

The first `r1` execution was interrupted by the Codex host after each of seeds
1103 and 1201 had a terminal full run but before its following minus-memory run
wrote a terminal summary. Before inspecting mechanism metrics, a recovery
amendment excluded all `r1` artifacts and froze `r2` to rerun all five
conditions for all twelve seeds. The scientific configuration is unchanged;
cross-version pairing is prohibited.

The r2 attempt was likewise interrupted by a task switch before either full
run wrote a terminal summary. A second outcome-blind amendment excludes all r1
and r2 artifacts and runs the unchanged r3 matrix through two detached lanes.
Each lane stops on its first subprocess error or non-five-for-five-VALID batch
and never retries automatically.

The r3 detached attempt is excluded in full. Seed 1103/full was `VALID`, but
seed 1201/full aborted at step 7 after two requests reached the frozen
240-second timeout; the concurrent seed 1103/minus-memory run was stopped
without a terminal summary. The r4 recovery keeps every scientific field
unchanged, reduces each lane from 12 to 6 in-flight requests, extends the
request timeout to 600 seconds, and prohibits overlap with another paid job.
All 60 r4 cells must be rerun and audited together; no r3/r4 pairing is allowed.

Report:

- variance of every primary E1/E2 effect;
- sign stability and rank stability;
- run completion and fallback rates;
- `VALID/INVALID/ABORTED` rates and reason codes;
- wall-clock time, tokens, and estimated cost;
- throughput by agent-step;
- maximum tested stable scale.

## 7. H1: blinded human or expert evaluation

**Claim**: observable trajectories are temporally coherent, use only available
information, respect household/resource constraints, and adapt plausibly to
execution feedback.

**Analysis scales**: individual and household/network.

**Evidence type**: empirical/behavioral validity from independent observers.

H1 uses only completed E1 v2 real-backend trajectories. A predeclared sample
covers evacuation outcome, one/multiple decision adults, dependent presence and
constraint complexity. Packets remove model name, seed, internal condition and
identity, and expose observable information, messages, plans, intents,
execution/rejection outcomes and final household state—not hidden chain of
thought. At least two independent raters score information grounding, cross-time
consistency, plan feasibility, household coordination, response to failure and
overall plausibility. Report item distributions, disagreement cases and an
agreement statistic suitable for the scale (for example weighted kappa or ICC).
LLM-as-judge may be a separate automation diagnostic but cannot be called human
or expert evidence.

Current H1 status is `PLANNED`: no rubric, blind packet or independent rating
result has yet been frozen or executed.

## 8. Data repair gate

Core mapping status:

- [x] Carr evacuation screening identified as Q9.1;
- [x] departure and warning times mapped and checked;
- [x] outcome missingness recorded without imputation;
- [x] 330-person evaluation respondent set saved;
- [x] Q13.6 post-outcome perceptions removed from prediction inputs.
- [x] Q13.6 raw mapping corrected to `_1=visual fire`, `_2=smoke`,
  `_3=official pressure`, with exact regression tests and an impact amendment.

Before publication-facing channel or prediction comparisons:

1. [x] freeze a common train/validation/test split when a split is required;
2. [x] pre-declare treatment of 15 internally inconsistent order responses;
3. audit every final prompt/feature set for outcome and post-outcome leakage.

The Carr-R split uses only `evaluation_index`: 198 train, 66 validation and 66
former-test records, stratified by Q9.1. It remains useful for reproducing the
historical validation runs, but the former test is now
`OPENED_FOR_DIAGNOSTIC`. For order-channel prevalence, the main analysis
excludes the 15 inconsistent records; the sensitivity analysis uses affirmative-
order priority. These records remain in otherwise eligible Q9.1 outcome
analyses.

The demographic-only traditional validation pilot ran on the frozen 198/66
train/validation records while the former 66-record test was still sealed.
Because validation contains only seven non-evacuees, accuracy is reported only
beside Macro-F1, Brier, ECE and the fixed-label confusion matrix. A corrected
reanalysis of historical DeepSeek responses is labelled
`PILOT_LEGACY_REANALYSIS`; it does not replace a new gateway-controlled run.
The new live four-field DeepSeek run completed 66/66 calls with Macro-F1 0.463,
Brier 0.127, ECE 0.178 and confusion matrix `[[0,7],[2,57]]`; a common-context
sensitivity kept the same Macro-F1 and confusion matrix while worsening Brier
to 0.145 and ECE to 0.197. These are `PILOT_VALIDATION_ONLY`, not platform
validation. The live runner exits before network access when neither
`PACKY_API_KEY` nor `LLM_API_KEY` is present.

All historical results produced before the repair remain development artifacts.

### Carr-S population gate

Before a formal synthetic social-process run:

1. connect PUMS housing and all person records by `SERIALNO`, keeping the raw
   identifier only in restricted provenance;
2. initialize donor household weights with `WGTP`;
3. fit tract household margins for income, vehicles, household structure and
   older-adult presence;
4. integerize/sample whole donor households and assign new synthetic household
   and resident IDs;
5. report fractional and integerized fit, effective sample size, extreme
   weights, donor repetition and structural QA;
6. use person age, relationship and disability only as non-fitted diagnostic
   margins. Household size becomes a fitted target only after a sourced ACS
   target and provenance are added.

The controlled household mechanism cohort initially uses donor households with
exactly two adults. Both adults are decision-capable and use the generative
policy when awake; dependent members retain execution and care state. Disability
components affect information, mobility and care constraints but do not
automatically cancel adult decision capability.

### Development verification and paid-pilot status

A 20-household, five-condition, five-seed deterministic-mock engineering check verifies
that the common kernel can execute the controlled warning → proposal →
acceptance → route obstruction → replanning → household movement chain. All 25
runs were `VALID`, zero-cost and zero-fallback. Every full-minus-module contrast
changed its predeclared primary metric in the predicted direction, but all
paired differences equalled 1.0 and therefore had zero seed variance. This is a
wiring/invariant integration only, not a behavioral pilot or formal E2 evidence. Gate D seed count must wait
for a non-saturated perturbation or declared model-backend pilot.

A second 20-household, five-condition, ten-seed mock engineering diagnostic introduced paired
Bernoulli warning reception (0.65), household-message delivery (0.25),
seed-selected primary-route closure steps (3–6), and route capacity. All 50 runs
were `VALID`, zero-cost and zero-fallback. Mean paired full-minus-drop
differences (SD; MCSE) were memory 0.580 (0.170; 0.054), feedback 0.975
(0.079; 0.025), planning 0.455 (0.249; 0.079), and interaction 0.480
(0.220; 0.070). This historical mock variance was used only to design a later
declared-backend pilot. It does not freeze the formal seed count because
the disabled module's proximal metric is structurally zero and the decision
policy remains deterministic mock.

A third mock engineering grid crossed three controlled reception/capacity scenarios,
five mechanism conditions, and ten paired seeds (150 mock runs). All four
module-specific paired differences remained positive in every scenario, with
informative seed variance. Its evidence status is `ENGINEERING_VALIDATION` and
its activity type is `ROBUSTNESS_DEVELOPMENT_GRID`, not behavioral or formal E3
evidence: the same transparent mock policy generated every decision.

The active Carr-S runner now loads two 2018 TIGER/Line-derived west-Redding
route candidates through the common Carr World. The route geometry, source
LINEARIDs, final-perimeter anchors, builder, configuration, and hashes are
recorded. The selected primary-route obstruction is an algorithmic controlled
perturbation and is explicitly not an observed Carr road closure. The one-run
mock execution using this asset is an `INTEGRATION_CHECK`, not an experiment.

The same runner switches by configuration to
`packy-deepseek-v4-flash`, using the common gateway, per-run cache, budget,
concurrency limit, fallback gate, and provenance. Before any network request it
requires `PACKY_API_KEY`, `LLM_API_KEY`, or the legacy-compatible
`OPENAI_API_KEY` and records only the selected variable name. The one-household
v2 check subsequently passed with 9/9 valid decisions and zero fallback. The
first five-household full run completed `INVALID` after one semantically empty
message used `payload: null`; it also established that five-household backend
runs are too slow for the development gate. The v3 interface normalizes null
empty payloads, uses a new run ID, and reduces only the backend pilot to
2 households × 5 conditions × 2 seeds.

The complete v3 backend pilot produced 10/10 `VALID` runs, 119 logical
decisions, no backend failure or fallback, and an internal cost estimate of
$0.493576. The predeclared full-minus-drop primary differences were memory
0.25, feedback 0.083, planning 0.50, and interaction 0.25 on average; for every
module one seed was positive and one was zero. Interaction is computed from
compatible commitment formation as predeclared above; the preserved raw matrix
incorrectly used coordinated departure and is not overwritten. Two seeds are
insufficient to freeze a formal count or interval. The source run also exposed
unclosed LiteLLM async-client warnings; cleanup and explicit wall-clock
instrumentation were added before any expanded pilot. A post-fix one-household
connectivity run then completed 9/9 decisions with no fallback in 218.138 wall-
clock seconds and exited without an unclosed-session warning. It remains an
engineering check, not an E2 observation.

The predeclared v3 expansion then executed all three additional seeds
(303/404/505), irrespective of interim effect direction. Across the original
and expanded matrices, 22/25 runs were `VALID`; three were `INVALID`, with 332
successful decisions and three failed/fallback decisions. Total internal cost
was $1.349111. Pairs containing any invalid run are excluded, leaving 2 memory
pairs and 4 pairs for each other module. Mean paired differences (SD; positive
fraction) are memory 0.25 (0.354; 0.50), feedback 0.0417 (0.0833; 0.25),
planning 0.75 (0.50; 0.75), and interaction 0.375 (0.25; 0.75). These are pilot
diagnostics, not formal E2 estimates or a basis for selecting favorable seeds.

A separate v4 engineering protocol sequentially rechecked the three diagnosed
failures under new run identifiers. Seed 404 full and seed 303 minus-memory
completed `VALID` with zero fallback. Seed 505 minus-memory completed
`INVALID`: the proxy returned `Insufficient Balance` for three decisions at
steps 7–8, producing a 17.65% fallback rate. The three checks cost an internally
estimated $0.185326 and used 1,218.780 summed run wall-clock seconds. They do not
replace v3 observations. Paid formal runs remain blocked until provider credit
is restored and a new-ID minimal backend-availability check succeeds. The
fail-fast `BACKEND_UNAVAILABLE` abort path is covered offline and need not be
induced on a funded account.
