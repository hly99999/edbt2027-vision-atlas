# Frozen Prototype Statistics

Generated: 2026-09-11  
Commit: `8ab8229c8dab5fe8697c0c04a9e781aba7d20509`  
Recompute: `python scripts/recompute_edbt2027_statistics.py`

| Measure | Value | Definition |
|---|---:|---|
| raw observations | 3,737 | Nonblank provider-observation rows before canonical family deduplication. |
| canonical paper families | 3,356 | Rows in data/papers/papers.jsonl, each representing one canonical paper family. |
| relevant paper families | 309 | Canonical families whose deterministic screening record has relevant=true. |
| full scan papers | 125 | Source-verified papers counted as FULL_SCAN by the frozen read-depth ledger; includes DEEP_READ. |
| deep read papers | 80 | Source-verified papers counted as DEEP_READ by the frozen read-depth ledger. |
| audited theorem papers | 20 | Coverage rows in coverage-001-020.jsonl. |
| audited theorem records | 127 | Rows with record_type=theorem in batch-001-020.jsonl. |
| records with source locations | 127 | Audited theorem rows containing a nonempty source_location object. |
| audited version families | 20 | Distinct version_id values among audited theorem rows. |

## Evidence boundary

Every value above is computed from an input whose SHA-256 is recorded in `prototype_statistics.json`. The admissible theorem evidence is exactly batch 001-020. These counts establish bounded construction feasibility and auditability only.
