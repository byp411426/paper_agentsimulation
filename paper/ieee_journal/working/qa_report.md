# IEEE journal manuscript QA — 2026-08-14

## Active package

- Main source: `../source/main.tex`
- Bibliography: `../source/references.bib`
- Review PDF: `../source/main.pdf`
- Template: `\documentclass[journal]{IEEEtran}` with local `IEEEtran.cls` and `IEEEtran.bst`

## Build validation

- Command: `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`
- Result: PASS
- PDF: 12 pages, US Letter, two-column IEEE journal layout
- Undefined citations: 0
- Undefined cross-references: 0
- Overfull boxes: 0
- Embedded fonts: PASS

## Figure validation

- Figure 1: `../figures/fig1_running_example.png`
- Figure 2: `../figures/fig2_system_architecture.png`
- Figure 3: `../figures/fig3_dynamic_loop.png`
- All three publication rasters are 1672×941 RGB PNG files.
- All three editable Draw.io sources are under `../figures/editable/`.
- Full-document contact-sheet review and full-page checks of pages 2, 5, and 7 found no clipping, missing figure, or unreadable placement at the PDF page level.

## Content boundary

- Present sections: Abstract, Introduction, Related Work, Method, and Evaluation Methodology.
- Experiments, Results, Discussion, and Conclusion are intentionally withheld pending a separate evidence-state and metric audit.
- Current E1 behavior, communication, departure, and efficiency artifacts remain diagnostic until the safe-state wake/duplicate-departure defects are fixed and the affected runs are repeated.
- The Carr setting is described as Carr-informed and controlled, not as a historical reconstruction.

## Migration record

- The pre-rebuild IEEE exploration source, bibliography, PDF, and legacy figures are preserved under `../archive/pre_20260814_ieee_rebuild/`.
- The unrelated conference-template package previously created under `agentPaper/manuscript/` was removed from the active project after its current prose, bibliography, PNG figures, Draw.io sources, and working notes were migrated here.
