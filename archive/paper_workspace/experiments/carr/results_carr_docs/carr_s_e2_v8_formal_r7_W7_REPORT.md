# Carr-S E2 v8 r7 — W7 mechanism report (2026-08-03)

## Audit status

- Matrix: 60/60 cells `VALID`; 12/12 seed batches complete; 0 failures; 0 fallback.
- Publication audit: `COMPLETE_VALID` (keyset, frozen hashes, terminal consistency, opportunity denominators).
- Model: `packy-deepseek-v4-flash` thinking-high, prompt `carr_s_controlled_resident_v8`, 8 households, 10 steps.
- Evidence label: matrix audit complete; claim boundaries below still apply.

## Manipulation checks (paired full − drop, n = 12 seeds)

| Module | Metric | mean diff | SD | MCSE | 95% t CI | direction 12/12 |
|---|---|---:|---:|---:|---|---|
| memory | conditional_warning_retention_rate | 1.0000 | 0.0000 | 0.0000 | [1.000, 1.000] | 12/12 (variance uninformative) |
| feedback | preclosure_primary_to_postclosure_alternate_update_rate | 0.9635 | 0.0496 | 0.0143 | [0.932, 0.995] | 12/12 |
| planning | successful_postclosure_replan_rate | 0.9063 | 0.0942 | 0.0272 | [0.846, 0.966] | 12/12 |
| interaction | post_closure_feasible_commitment_rate | 0.9375 | 0.0843 | 0.0243 | [0.884, 0.991] | 12/12 |

All four manipulation checks move in the predeclared direction with 95% intervals
excluding 0 (memory is structurally saturated in this controlled scenario).

## Predeclared downstream outcomes

| Module | Outcome (predicted direction) | mean diff | SD | MCSE | 95% t CI | direction |
|---|---|---:|---:|---:|---|---|
| feedback | closed_route_rejections per household (lower) | 6.5417 | 0.6707 | 0.1936 | [6.116, 6.968] | 12/12 |
| interaction | coordinated_departure_rate (higher) | 0.8125 | 0.1554 | 0.0449 | [0.714, 0.911] | 12/12 |
| memory | complete_household_safe_departure_rate (higher) | −0.1042 | 0.1671 | 0.0482 | [−0.210, 0.002] | 2/12, 25% zero |
| planning | complete_household_safe_departure_rate (higher) | 0.0104 | 0.1355 | 0.0391 | [−0.076, 0.096] | 5/12, 17% zero |

## Interpretation (per frozen W7 rules)

- **feedback**: manipulation check and downstream both support the conditional
  removal effect — removing feedback sharply increases attempts to use the
  closed route (≈6.5 more rejections per household) and eliminates replanning.
- **interaction**: manipulation check and downstream both support the effect —
  removing interaction eliminates feasible post-closure commitments and
  coordinated departures.
- **memory**: the manipulation check confirms removal eliminates warning
  retention, but the downstream interval for complete household safe departure
  crosses zero (slightly negative point estimate). Claim scope: memory changes
  the internal process; downstream consequences are **undetermined** in this
  controlled scenario.
- **planning**: manipulation check confirms removal eliminates post-closure
  replanning, but the downstream interval crosses zero. Claim scope: planning
  changes the internal process; downstream consequences are **undetermined**
  in this controlled scenario.

## Claim boundary

- Estimates are conditional removal effects in this controlled 8-household,
  TIGER-route scenario; not a universal module-independence claim.
- Not Carr empirical validation; not historical reconstruction; not population
  representativeness.
- Carr-R test split remains unopened for E2 purposes.
- Full paired values, exclusions, and provenance are in
  `carr_s_e2_v8_formal_r7_cumulative_summary.json` and
  `carr_s_e2_v8_formal_r7_publication_audit.json`.
