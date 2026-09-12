# Published architecture comparison: implementation and frozen pilot protocol

This branch implements an eight-household, single-seed paired pilot of DisasterSociety,
Generative Agents (disaster adaptation), and AgentSociety (legacy cityagent architecture,
disaster adaptation). A successful software check is not a behavioral result. Private
run artifacts and independent judgments are delivered separately; this document does
not supply invented scores or imply that a pilot establishes publication readiness.

## What actually executes

| Arm | Retained implementation | Explicit adaptation and limits |
|---|---|---|
| Generative Agents | Author `new_retrieve` function, including its recency, importance and cosine-relevance ranking; importance-rated event memory, reflection with cited memory IDs, broad planning, decomposition and reaction | Only retrieval is executed verbatim. Reflection/scheduling control flow is our disaster-domain port, not the complete Smallville simulator. Reflection threshold 150; received conversation messages also trigger reflection. Synthesized thoughts and schedule nodes receive importance 5. The calendar uses 25 half-hour disaster steps and four-step planning windows. |
| AgentSociety | Author `NeedsBlock`, `PlanBlock`, `CognitionBlock` and JSON utility class/function bodies; hierarchical needs, satisfaction decay, TPB guidance, multi-step plans, emotion updates, plan-completion needs evaluation | Local implementations bridge environment, memory and model interfaces. Native urban mobility, economy and dialogue execution blocks are replaced by a common disaster action translator. Workday is false in this emergency episode. Guidance options become supported disaster actions. Stream retrieval uses the local embedding provider. The native daily cognition condition remains; a single-day episode does not exercise cross-day cognition. |
| DisasterSociety | Existing E1 resident, private memory, protective plan, information receipt and execution-feedback processing | Common action-schema instructions clarify that no plan update is JSON null, not an empty step list. |

Upstream sources:

- [Generative Agents](https://github.com/joonspk-research/generative_agents/tree/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4), commit `fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4`.
- [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety/tree/670c94fff7c64c4f79b632125f2ccf968155e746/packages/agentsociety), commit `670c94fff7c64c4f79b632125f2ccf968155e746`. This selects the legacy `packages/agentsociety` cityagent modules, not AgentSociety 2. The repository snapshot is not claimed to be an untouched 2025 release.

Exact source paths, original hashes and import changes are in
`disastersociety/ds/baselines/vendor/UPSTREAM.json`; licenses accompany the copies.
Native class/function ASTs are checked against the pinned upstream files. GA's added
local `print` override only suppresses upstream debug output.

Both adaptations use local `sentence-transformers/all-MiniLM-L6-v2` embeddings
(384 dimensions). This replaces the original embedding backend and is a reproducible
adaptation choice, not evidence of equivalence to the original models.

## Scope of the comparison

All three arms share the same household commitment protocol, road and vehicle physics,
warning-delivery rules, wake gate, action schema and episode horizon. Every resident
receives only its local observations and actual received messages. Different actions
can create different subsequent messages and locations; those endogenous differences
are expected.

Consequently this comparison tests resident cognitive architectures **within the shared
DisasterSociety environment**. It cannot demonstrate that the shared household/state
architecture itself is superior to the original platforms. The two baseline labels
must retain “disaster adaptation” in a paper. Humanoid Agents is not implemented in
this pilot and must not appear as a completed comparison.

## Frozen small-run configuration

- First eight corrected public synthetic household profiles; seed 7201, 25 steps,
  30 minutes per step, no outcome-based household selection.
- Packy `deepseek-v4-flash`, temperature 0, thinking enabled, 16384 output tokens per
  call, forced function output for the common action contract, at most two schema
  corrections and two provider attempts. AgentSociety's native cognitive blocks retain
  their author-requested JSON-object interface; this is the same backbone and sampling,
  not another model. A generic dictionary must not be forced through an empty function schema.
- Three concurrent calls per arm; three arms can execute concurrently. Each arm may
  make its own normal internal module calls. A call count is not a resident decision count.
- Internal accounting cap USD 5 per arm at USD 1/M input and output tokens. These rates
  are internal estimates, not verified Packy charges; in-flight calls may overshoot a cap.
- Initial failed development attempts remain separate. A change in schema guidance or
  provider output mode creates a new attempt for all three arms, without splicing logs.
- Earlier thinking-disabled attempts exposed repeated malformed optional plans and missing
  conditional departure fields. They remain development failures, including their costs.
  The final paired attempt restores reasoning uniformly; its higher call budget is frozen
  before scoring and is not adjusted per method's behavioral outcome.
- Provider outages and unparseable outputs abort the run; there is no rule-generated
  behavior fallback. A parsed but incomplete departure intention is instead rejected
  by the environment, recorded without physical execution, and returned as feedback.
  Such semantic request rejection must not be mislabeled as a provider outage.
- `E1ActionRequest` is the model-to-world request contract. If a resident explicitly
  cites an accepted commitment that is present in its actual input, omitted copies of
  vehicle/route/time can resolve from that exact record. The original model request,
  referenced source and copied fields are logged. Explicit conflicting fields remain
  unchanged and are rejected by the world; the bridge never selects a party or grants consent.
- Literal string `"null"` in declared nullable request fields can normalize to JSON null.
  This narrow wire-format conversion is logged; actions and free text are untouched.

Each run saves configuration, source and model-registry hashes, input hashes, upstream
versions, embedding artifact hashes, model usage, complete event history and native
cognitive calls. Real input files were verified against the already-public GitHub
snapshot; the model payload contains synthetic profiles/state, not original questionnaires,
private chat history or the paper PDF.

## Evaluation and paper placement

Primary: complete-household behavioral plausibility, one 1–5 score per household under
the frozen existing rubric. Report scored/total households, the within-run mean, all
individual scores and explanatory evidence. With one social world per arm there is no
independent-run uncertainty estimate. Household observations are socially dependent.

Relative presentation: DisasterSociety versus each adapted baseline, paired on initial
household and scenario. Independent Codex sessions choose A, B, tie or unjudgeable.
Reverse A/B presentation is independently evaluated; average both order preferences per
underlying pair, then average households. A win contributes 1, tie 0.5, loss 0. Cases
unjudgeable in either order remain missing and are counted explicitly. The 32 judgments
are 16 underlying household pairs, not 32 independent simulations. Report order disagreement.

Method/model identifiers and architecture-specific internal cognition are removed from
review copies. External inputs, all 25 steps, complete messages, decisions, assessments,
outcomes and world facts remain. Original logs retain everything. The evaluator sees the
whole history but must distinguish its world knowledge from what residents knew. This
reduces explicit method cues; it does not establish perfect evaluator blindness.

Forward reviewers also score the absolute 1–5 rubric. Reverse reviewers repeat absolute
scores on households 1 and 5 fixed before judging. Repeated scores diagnose disagreement;
they do not replace the primary scores. The judge is an independent Codex session, not a
fictional callable “GPT 6 Astra” API. An unknown underlying model snapshot remains unknown.

Three structured-state audits and the 20 developer process cases belong in implementation
verification, not in the method-superiority table. Common-engine zero errors are common
reliability evidence. No eligible consensus/departure event means N/A, not zero errors.
Evacuation, joint travel, waiting, disagreement and help requests are descriptive process
statistics; none has an automatic higher-is-better interpretation.

The main result table combines behavioral plausibility and actual computational cost.
Pairwise preferences and representative evidence explain the difference. This pilot can
support an explicitly labeled preliminary comparative experiment, not population realism,
optimal evacuation, statistical superiority, or a claim that all paper experiments are done.

## Commands

From `disastersociety/`, install `pip install -e '.[published-baselines]'`, then use
a separate writable embedding cache (`DS_EMBEDDING_CACHE`). The execution environment
used Python 3.12.14, LiteLLM 1.100.1, FastEmbed 0.8.0 and json-repair 0.63.4.

```bash
python -m scripts.run_published_comparison --output /absolute/new/offline_directory
python -m scripts.run_published_comparison --run --output /absolute/new/real_directory
python -m scripts.evaluate_published_comparison prepare \
  --runs /absolute/new/real_directory --output /absolute/new/evaluation_directory
python -m scripts.evaluate_published_comparison collect \
  --output /absolute/new/evaluation_directory --judgments /absolute/judgment_directory
```

The real runner reads `PACKY_API_KEY` from the environment or a hidden prompt. Do not
place the key in a shell command, configuration, log, paper or commit. Outputs refuse to
overwrite existing attempts. `prepare` requires three complete valid runs with identical
external input hashes and the recorded source version. `collect` rejects missing, duplicate,
changed or invalidly referenced judgments. No command fabricates behavioral ratings.
