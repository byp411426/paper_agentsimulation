# Manuscript QA report

Final QA snapshot: 2026-08-14 04:11 CST.

## Build

- Command: `latexmk -pdf -interaction=nonstopmode -halt-on-error disastersociety_fg2026.tex`
- Exit status: 0.
- Output: `disastersociety_fg2026.pdf`.
- PDF: 12 A4 pages, unencrypted, PDF 1.7.
- Fonts: all listed fonts are embedded Type 1 subsets.
- Undefined citations/references: 0.
- BibTeX warnings: 0.
- Overfull boxes: 0.
- Remaining messages: template class-name warning and underfull box notices only;
  visual inspection found no clipping or overlap.

## Content inventory

- Body text: 6,151 words; 6,619 including headers/captions and auxiliary text.
- Introduction: approximately 871 body words plus Figure 1 caption.
- Related Work: approximately 994 body words.
- Method: approximately 4,067 body words plus tables/figure captions.
- Figures: 3 double-column figures.
- Tables: 2 double-column method/evaluation tables.
- Unique cited works: 35; all resolve in the bibliography.

## Visual inspection

All 12 pages were rendered at 150 dpi and inspected. Figure 1, Figure 2, and
Figure 3 are legible at full-page review scale, remain within the text block, and
have no visible crop or neighboring-source artifacts. Both tables fit the page
width and retain readable row separation. The reference list begins only after
the evaluation table because a float barrier is applied.

## Figure/source integrity

- Publication PNGs are the clean original 1672×941 images.
- Editable sources are retained separately as Draw.io files.
- No SVG is referenced by the LaTeX source.
- SHA-256 values at this snapshot:
  - TeX: `99194284b14bb4b8aa8dbd2e84291cb8853fc60dc9c29f39dc1060212ddee460`
  - Bib: `107b8ba804ec28b907b7b86669ec106be01e51ffd4d1798a512d32c100c9091b`
  - PDF: `bd30cde0d43e0b2b40f4b5d475db4b0c920d34a427f6e0039e035970ae31c251`

Regenerate the hashes whenever the TeX, bibliography, or figures change.

## Citation audit

Independent read-only regression reported PASS: 59 citation-key occurrences,
35 unique cited works, 35/35 resolvable, no duplicate key, and no high-severity
claim/source mismatch. SOTOPIA, Reflexion, RESPOND, the Ye/IPU paper, and the Pel
and Murray-Tuite evacuation references were specifically rechecked against
formal publication records.

## Scientific boundaries retained

- No quantitative Results are invented in this pre-experiment draft.
- Carr is described as Carr-informed and controlled, not historical
  reconstruction.
- E1 and E2 implementation contracts are separate.
- Mock/testing evidence is not called behavioral evidence.
- The opened Carr-R test split is not described as an untouched holdout.
- E1 publication metrics must be recomputed from ledgers and locations before
  Results are drafted, after the terminal wake/repeat-departure contracts are
  fixed and E1 is rerun. Current E1 artifacts remain diagnostic because later
  messages already changed the social trajectory and cannot be repaired by a
  summary-only filter.

The authoritative project evidence ledger was updated on 2026-08-14 with this
E1 downgrade and with the current full-suite status (129 passed, 2 failed).

## Submission work still required

- Supply the real paper ID, authors, affiliations, funding, and any mandatory
  ethics/data statements.
- Confirm the venue page limit and compress the current detailed method if
  needed; 12 pages before Results is a working draft, not a camera-ready length.
- Resolve the blockers in `KNOWN_IMPLEMENTATION_BLOCKERS.md` and perform a
  separate evidence-state synchronization before writing Results, Discussion,
  and Conclusions.
