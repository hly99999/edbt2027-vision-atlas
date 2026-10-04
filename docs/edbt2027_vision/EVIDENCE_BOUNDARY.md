# Evidence Boundary

## Canonical evidence snapshot

Counts below were recomputed on 2026-09-11 from committed canonical artifacts in this branch, rather than copied from narrative reports.

| Stage | Recomputed count | Canonical artifact |
|---|---:|---|
| Raw source observations | 3,737 | `literature/source_registry/venue_census_observations_2023_2026.jsonl` |
| Canonical paper families | 3,356 unique rows / paper IDs | `literature/source_registry/venue_census_2023_2026.jsonl` |
| Relevance-screened families | 3,356 | `literature/source_registry/relevance_screening_2023_2026.jsonl` |
| Relevant families | 309 | same screening ledger, `relevant=true` |
| FULL_SCAN or deeper | 125 | `literature/fulltext_ledgers/read_depth_2026_08_30.json` |
| DEEP_READ | 80 | same reading ledger |
| Formally audited prototype papers | 20 | `data/theorems/fragments/coverage-001-020.jsonl` |
| Complete audited coverage dispositions | 20 | same coverage artifact |
| Source-located theorem/proposition records | 127 unique theorem IDs | `data/theorems/fragments/batch-001-020.jsonl`, `record_type=theorem` |
| Claim-inventory rows | 127 | `data/theorems/fragments/claim-inventory-001-020.jsonl` |

The 125 FULL_SCAN count includes the 80 DEEP_READ records. The publishable theorem-level feasibility evidence is limited to the reviewed 20-paper batch and its 127 theorem/proposition records.

## What this evidence supports

- The project can represent version-aware paper identities and source-bound theorem records.
- A bounded set of real database-theory papers can be converted into structured scope records with exact source locations and audited coverage dispositions.
- The workflow can preserve explicit scope fields and evidence provenance and can reject some incomplete or inconsistent records.
- The artifact can be rebuilt and audited using schemas, code, ledgers, and hashes, subject to the documented runtime and source availability.

## What this evidence does not support

- coverage completeness for database theory or even all 80 DEEP_READ papers;
- correctness or completeness of unreviewed batch 21–40;
- any claim about papers 41–80 having completed theorem extraction;
- extraction accuracy, recall, throughput, usability, research impact, or community adoption;
- final relation graphs, research-direction rankings, or open-problem status;
- novelty relative to existing infrastructure;
- redistribution rights for source PDFs;
- the correctness of all theory merely because software tests pass.

## Artifact publication boundary

The intended artifact may publish code, schemas, audited derived records, build/audit scripts, metadata, DOI and source pointers, and provenance/hash metadata. Source PDFs may be redistributed only when permission is explicitly established. Otherwise the artifact must omit PDF bytes while retaining lawful metadata and evidence pointers.

## Recount rule

Every numerical statement in the submission must be generated or checked directly from canonical artifacts at paper-build time. Narrative reports are secondary cross-checks, not counting authorities.
