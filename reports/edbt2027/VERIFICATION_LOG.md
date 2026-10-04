# Verification Log

Date: 2026-09-11.

## Package checks

- `scripts/recompute_edbt2027_statistics.py`: PASS; frozen counts regenerated from five SHA-256-bound inputs.
- `scripts/validate_edbt2027_package.py`: PASS; 20 bound claims, 32 serious related works, 9 direct threats, six reviewer personas with 15 questions each, five mock reviews, and a seven-page PDF consisting of six labeled body pages plus one references page.
- Python syntax compilation for the three EDBT scripts: PASS.
- PDF render inspection: PASS for clipping/overlap; all seven pages rendered. The fallback PDF is intentionally marked as a submission candidate, not the final official-template build.
- Figure inspection: PASS; architecture and running-example figures are readable in editable SVG and vector PDF form.
- Forbidden novelty wording scan: PASS after removing priority/exclusivity language.
- Unreviewed-corpus leakage scan: PASS; batch 021–040 and papers 041–080 occur only in explicit exclusion statements, not as evidence or claims.

## Repository regression suite

The suite requires `PYTHONPATH=src` and an in-workspace pytest temp directory in this environment. With those settings, collection succeeds, but the pre-existing frozen-corpus byte-identity test fails because regenerated provider/report hashes differ from the checked-in recovered artifacts. This failure is outside the EDBT package changes; no corpus artifact was rewritten to hide it. Package-level validation is therefore the controlling verification for this branch.

## Typesetting status

The official CFP template archive was downloaded and extracted under `paper/edbt2027_vision/official-template/`, and `main.tex` now uses its `acmart` class, A4 geometry, EDBT macros, and ACM bibliography style. No LaTeX engine is installed locally, so the official-class PDF compilation and its final page count remain a named pre-submission blocker. The included seven-page fallback PDF is for scientific and visual review only.
