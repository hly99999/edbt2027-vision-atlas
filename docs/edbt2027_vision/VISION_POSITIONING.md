# EDBT 2027 Vision Positioning

## Project status

`EDBT2027_VISION_PAPER_PREPARATION`

The repository is no longer being driven toward completion of a comprehensive Database Theory Frontier Atlas. The submission target is an EDBT 2027 Vision Paper. Existing Atlas assets are retained as a prototype, feasibility witness, source of one audited running example, and artifact foundation.

Corpus Tasks 5–7 are paused. Unfinished Corpus Task 4 expansion is not a submission prerequisite. A narrowly scoped data addition is permitted only when a specific paper claim cannot otherwise be supported.

## Community problem

Database-theory results are unusually vulnerable to two forms of information loss when they move from papers into search systems, surveys, citation graphs, or machine-generated summaries:

1. **Scope loss:** the result becomes detached from query class, complexity regime, parameter roles, structural restrictions, preprocessing assumptions, randomness, semantics, domain, and other qualifiers that determine what the theorem actually says.
2. **Evidence loss:** the claim becomes detached from its exact source location, assumptions, version lineage, provenance, and the justification for typed relations to other results.

The dangerous endpoint is a portable but misleading sentence such as “Problem X is tractable,” with the conditions that make it true no longer represented.

## Working thesis

> Database theory needs scope-preserving, evidence-grounded knowledge infrastructure in which theorem claims, assumptions, complexity regimes, structural restrictions, version lineage, proof techniques, typed relations, and source provenance are first-class machine-actionable objects rather than information flattened into papers, abstracts, and citation edges.

This wording is a working thesis and may be tightened after the related-work audit. Its novelty must not be asserted before the Novelty Kill Gate.

## Proposed knowledge unit

The primary unit is a **Scoped Theorem Record**, not merely a paper or free-standing theorem sentence:

`Theorem + Scope + Assumptions + Complexity regime + Structural restrictions + Version + Evidence pointer + Proof technique + Typed relations`

The key design commitment is that scope is structured data that can be queried, compared, audited, and withheld when evidence is insufficient.

## Track positioning

The submission is a **Vision Paper**. It is not positioned as a traditional theorem paper, tool paper, demo paper, systematic literature review, benchmark paper, literature search engine, bibliography manager, generic scholarly knowledge graph, AI literature assistant, or automatic theorem prover.

## Four contribution claims under consideration

- **C1 — Problem identification:** identify scope loss and evidence loss as central obstacles to cumulative and machine-actionable database-theory knowledge.
- **C2 — Vision and model:** propose an evidence-grounded, scope-preserving theorem atlas, together with its data model and quality principles.
- **C3 — Feasibility evidence:** use the audited prototype to show that scoped, source-located theorem records can be constructed and audited on real database-theory literature.
- **C4 — Research agenda:** frame open research on theorem extraction, scope verification, relation inference, version evolution, open-problem tracking, evaluation, community maintenance, and human/AI governance.

These are ceilings, not established novelty findings. C1–C2 remain conditional on related-work audit; C3 is limited by the evidence boundary; C4 proposes future work rather than completed capabilities.

## Why EDBT should care

Database research depends on distinctions—data versus combined complexity, fixed versus input queries, restricted versus general classes, preprocessing versus online cost—that can reverse the meaning and applicability of a result. Infrastructure that preserves these distinctions can support safer synthesis, theorem retrieval, comparison, teaching, survey construction, and machine-assisted research without pretending that automated extraction replaces author or expert verification.
