# Known implementation and evidence blockers

Snapshot date: 2026-08-14. This is a manuscript-safety record, not a substitute
for the authoritative project ledgers.

## E1 social-message semantics

- Official orders have recipient receipts, but E1 social messages store one
  message-level status and timestamps for a recipient list.
- One response can mark a shared message accepted before party feasibility is
  known, and `accepted_by` can contain all addressed recipients rather than only
  explicit accepting recipients.
- Current artifacts therefore cannot establish recipient-level mutual
  acknowledgment or multi-adult message-mediated coordination from the social
  message ledger alone.

## E1 summary estimands

- `complete_safe_household_departure` currently labels any household with an
  executed party rather than requiring all initialized members in the safe zone.
- `coordinated_household` can count a one-decision-adult solo auto-party.
- Publication metrics must be recomputed from member locations, party traveler
  IDs, party execution steps, and explicit multi-adult opportunity denominators.

## E1 arbitration and reproducibility

- E1's wake gate does not exclude residents already in the safe zone. Recent
  execution feedback is appended after every decision and is not consumed, so a
  resident can remain awake after first arrival and continue calling the model
  or sending messages.
- Party execution does not recheck traveler origin or prior safe arrival;
  repeated executed departure records for the same already-safe resident exist
  in current artifacts. They invalidate behavioral, communication, departure,
  split, and efficiency interpretation of those runs.
- Unknown route IDs can abort instead of yielding a typed rejection.
- Audited code paths have unresolved capacity bookkeeping after rejected parties
  and out-of-party intent matching risks.
- Graph fallback coordinates and delivery counters use Python process hashes;
  the exact graph edge list and `PYTHONHASHSEED` are not preserved.
- E1 domain ledgers do not yet match E2's configuration/selected-source
  provenance bundle.

## Evidence-status boundaries

- E1-v2 artifacts require a dedicated scientific/metric audit before promotion.
- Carr-R's former test split was opened for development diagnosis and is not an
  untouched holdout.
- Overall official-warning reception is calibrated and cannot be reused as
  independent validation.
- Blinded human or expert review remains planned.

## Test status observed during the method audit

The full project test run was repeated on 2026-08-14 and was not all green: 129
tests passed and 2 failed in 11.47 seconds. The
failures concerned an E2 frozen-source hash guard after a recorded reconstruction
amendment and PUMS NA decoding (`NaN` versus expected `None`). These failures do
not arise from the manuscript edits, but the paper must not claim that the full
current suite passes.

## Required gate before Results

1. Add a terminal safe-state wake exclusion, consume/clear feedback correctly,
   and reject repeat departure by travelers no longer at origin.
2. Fix or freeze the E1 message/commitment semantics.
3. Implement and independently test the E1 publication metrics and denominators
   described in the manuscript; current prose is a specification, not an
   already executed recomputation.
4. Resolve or explicitly exclude the remaining E1 arbitration defects.
5. Rerun E1 and regenerate formal summaries and provenance where required; the
   current E1 artifacts remain engineering/diagnostic material.
6. Reconcile every result with `docs/EVIDENCE_LEDGER.md` and preserve its status
   label (`VERIFIED`, `ENGINEERING_VALIDATION`, `PILOT`, and so on).
