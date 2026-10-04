# Public Artifact Candidate File Index

This index describes the local staging candidate. The public package is under `package/`; the ZIP is a convenience archive only.

## Key public candidates

- `package/src/`: deterministic Python library and data model.
- `package/scripts/`: corpus assembly, figure generation, statistics recomputation, and EDBT validator scripts.
- `package/tests/`: regression tests with synthetic path-validation fixtures only.
- `package/data/papers/papers.jsonl`: canonical bibliographic paper-family metadata.
- `package/data/theorems/fragments/batch-001-020.jsonl`: formally audited theorem records; the release boundary stops here.
- `package/data/theorems/fragments/claim-inventory-001-020.jsonl`: audited claim inventory.
- `package/data/theorems/fragments/coverage-001-020.jsonl`: coverage dispositions for the audited batch.
- `package/literature/source_registry/`: source URLs, provider manifests, and deterministic screening metadata; provider response caches are omitted.
- `package/literature/fulltext_ledgers/read_depth_2026_08_30.json`: read-depth counts and hashes without PDF bytes.
- `package/artifacts/edbt2027/`: artifact statement, claim registry, and frozen statistics.
- `package/docs/edbt2027_vision/`: scope, evidence, and official-requirement notes.
- `package/reports/edbt2027/`: novelty, citation, running-example, claim-evidence, and submission audits.
- `package/paper/edbt2027_vision/main.tex` and `references.bib`: manuscript source context.
- `package/paper/edbt2027_vision/figures/`: original generated SVG/PDF figures.
- `MANIFEST.json` and `SHA256SUMS.txt`: per-file bytes and SHA-256 hashes.

## Intentionally absent

Source PDFs, extracted full-text notes/audits, provider payload caches, unreviewed theorem batches, official template files, build logs, candidate manuscript PDFs, and any credentials are absent. See `RELEASE_AUDIT.md` for the legal and publication checks still required.
