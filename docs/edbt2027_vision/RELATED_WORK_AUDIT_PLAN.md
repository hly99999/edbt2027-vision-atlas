# Related-Work Audit Plan

## Purpose

Determine whether the proposed vision has a defensible contribution and produce the evidence required for the Novelty Kill Gate. This file defines the future audit; it does not contain search results or novelty conclusions.

## System families to audit

- scholarly knowledge graphs;
- Open Research Knowledge Graph and closely related infrastructure;
- mathematical knowledge graphs;
- theorem-oriented knowledge bases and proof-library metadata systems;
- scientific claim extraction and claim representation;
- evidence- and provenance-aware scholarly systems;
- systematic-review infrastructure;
- theorem retrieval and mathematical knowledge management.

## Search and screening protocol

1. Define queries and venues for each system family before searching.
2. Record every candidate with title, authors, year, venue, stable identifier, access route, and screening decision.
3. Read primary system papers and current technical documentation for all close candidates; do not rely on abstracts or secondary descriptions for capability judgments.
4. Separate implemented capability, proposed capability, and inferred possibility.
5. Preserve exact evidence pointers for every comparison-cell judgment.
6. Search backward references and forward citations for each closest system.
7. Ask whether a combination of systems—not only one system—substantially eliminates the proposed gap.
8. Have a second reviewer check the closest-prior-system set and all negative capability judgments.

## Comparison matrix

For each candidate, record:

| Dimension | Required judgment |
|---|---|
| Primary unit | paper, passage, claim, theorem, proof, or other |
| Formal scope axes | which axes are explicit and queryable |
| Assumptions/restrictions | claim-level, paper-level, inferred, or absent |
| Complexity regimes | structured, textual, or absent |
| Evidence grounding | exact source location, document-level link, or none |
| Version lineage | paper and theorem evolution support |
| Proof techniques | structured and evidence-bound or not |
| Typed relations | relation vocabulary and justification mechanism |
| Uncertainty model | unknown/not stated/not applicable/review state |
| Promotion governance | automated, open, curated, fail-closed, author-verified |
| Domain specificity | database theory, mathematics broadly, scholarship broadly |
| Evaluation evidence | what was actually evaluated |

Each cell must carry a source pointer and confidence label. “Not found” is not evidence of absence until the defined primary materials have been checked.

## Decision procedure

- Identify the three to five closest systems by capability overlap, not popularity.
- Write the strongest possible “already solved” case for each.
- Test each candidate differentiator against those systems.
- Remove or narrow every unsupported novelty claim.
- Record a `GO`, `CONDITIONAL_GO`, or `NO_GO` verdict with reviewer sign-off.

## Deliverables for the next phase

- search log and inclusion/exclusion ledger;
- primary-source evidence packet;
- completed comparison matrix;
- closest-prior-system briefs;
- adversarial novelty assessment;
- signed Novelty Kill Gate verdict;
- revised thesis and contributions consistent with the verdict.
