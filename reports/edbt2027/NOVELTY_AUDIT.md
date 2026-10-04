# Novelty Audit

## Verdict: CONDITIONAL_GO

The literature does not support a broad claim that claim-level graphs, theorem objects, provenance, versioning, or machine-actionable relations are individually new. ORKG, micropublications, nanopublications, PAV, semantic publishing, OntoMath/OMDoc/MMT, Mizar, and scientific-claim verification each cover substantial components. The defensible delta is narrower and compositional:

> We argue for treating theorem scope and source evidence as first-class objects in scholarly infrastructure for database theory, using a prescribed scope contract, exact evidence binding, version identity, typed theorem relations, and fail-closed human promotion.

## Search and audit coverage

- 32 serious candidates across scholarly KGs, research graphs, mathematical knowledge management, theorem retrieval, evidence graphs, scientific-claim verification, systematic-review infrastructure, and formalized mathematics.
- 12 primary-source deep comparisons: ORKG, ORKG requirements, nanopublications, micropublications, PAV, OntoMath, Mizar, S2ORC, SciFact, SciFact-Open, MultiVerS, and ASReview.
- Direct threats: ORKG; micropublications; nanopublications; OntoMath/OMDoc/MMT; Mizar/formal libraries; PAV as a version/provenance component.

## Threat-by-threat result

1. **ORKG.** Already supports machine-actionable research contributions, flexible domain vocabularies, comparisons, provenance, and versions. It does not require a theorem record to enumerate database-theory scope axes such as query fragment, structural restriction, data/combined complexity, preprocessing, delay/access/load, randomness, and fixed/input/parameter roles; nor does its generic contribution model impose exact theorem-evidence and fail-closed promotion.
2. **Micropublications.** Already models natural-language claims, data, methods, evidence, support/challenge relations, attribution, and evolving claim networks. It is the closest evidence-graph threat. Its unit is a general scientific argument rather than a formal theorem whose validity domain is decomposed into complexity and structural axes.
3. **Nanopublications/PAV.** These provide fine-grained assertion provenance, immutable identifiers, publication information, authorship, derivation, and versioning. They are reusable foundations, not substitutes for the proposed theorem-scope semantics.
4. **OntoMath/OMDoc/MMT/Mizar.** These make mathematical concepts, theorems, proofs, imports, and dependencies machine-actionable—often more formally than this vision. Their cost model presumes formalization or formal-library membership. The proposed target is the large informal theorem literature, where exact source evidence, explicit unknowns, and human audit state remain essential.
5. **S2ORC/SciFact/MultiVerS/ASReview.** These provide document structure, evidence spans, verification labels, or human-in-the-loop screening. They can supply extraction substrates and benchmarks, but do not define a persistent version-aware scoped theorem object.

## Why database theory is structurally special

A database-theory result can reverse meaning when any of several interacting axes is dropped: data versus combined complexity; fixed versus input query; query fragment; self-joins; acyclicity/treewidth/free-connexity; preprocessing; delay or direct-access time; communication rounds and per-server load; deterministic versus randomized guarantees; and conditional lower-bound hypotheses. These axes are not decorative metadata. Together they delimit the proposition being asserted and determine which theorem-to-theorem relations are logically admissible.

## Kill-gate conditions

The paper must not claim a first theorem KG, universal completeness, extraction accuracy, automated correctness, maintained open-problem truth, or demonstrated community utility. Novelty remains conditional on (i) retaining the prescribed formal-scope contract, (ii) binding every promoted record to source/version evidence, (iii) explicitly building on—not displacing—ORKG, nanopublication/PAV, and formal-math standards, and (iv) presenting the prototype only as bounded feasibility evidence.
