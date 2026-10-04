# EDBT 2027 Vision Paper Requirements

## Submission identity

- Target: EDBT 2027 Vision Paper.
- Main text target: at most six pages, subject to confirmation against the official call and template before submission.
- Contribution type: problem framing, vision, model, bounded prototype feasibility, and research agenda.
- Not a theorem paper, tool/demo paper, systematic review, or benchmark paper.

## Required reviewer answers

The final manuscript must make clear:

1. what current database-theory knowledge infrastructure lacks;
2. why scope and evidence loss are especially consequential in database theory;
3. why existing scholarly KG, search, literature, and mathematical-knowledge systems are insufficient for the narrowed claim;
4. what scope-preserving theorem infrastructure means;
5. why theorem scope must be first-class data;
6. what a useful Atlas stores;
7. what the current prototype actually demonstrates;
8. what remains unsolved;
9. what research agenda follows;
10. why the EDBT community should care.

## Narrative order

`Problem → information loss in existing infrastructure → vision → Scoped Theorem Record model → prototype feasibility → research agenda → risks and governance`

Task chronology, tests, commits, hashes, and repository engineering belong only where needed to establish artifact reliability or reproducibility.

## Main-text budget

- One audited running example only.
- At most one architecture figure.
- At most one compact scope/example table or figure.
- Do not enumerate every Atlas capability.
- Keep implementation details and extended audit material in the artifact or appendix if permitted.

## Contributions ceiling

The paper may contain at most the four contribution classes defined in `VISION_POSITIONING.md`: problem identification, vision/model, bounded feasibility evidence, and research agenda. Claims must comply with `CLAIM_BOUNDARY.md` and `EVIDENCE_BOUNDARY.md`.

## Required sections or content blocks

- motivation and database-specific failure cases;
- related-work distinction backed by the completed audit;
- Scoped Theorem Record and quality principles;
- one audited scope-loss example;
- prototype feasibility with canonical counts and explicit limitations;
- future research agenda;
- risks, failure modes, and human/AI governance;
- artifacts and reproducibility;
- limitations.

## Artifact requirements

Prioritize code, schemas, audited derived records, scripts, and reproducibility instructions. Include metadata, DOI/source pointers, and hashes when source PDFs cannot lawfully be redistributed. State the runtime and distinguish reproducibility engineering from scientific validation.

## Mandatory pre-drafting gates

- complete the related-work audit;
- issue `GO`, `CONDITIONAL_GO`, or `NO_GO` at the Novelty Kill Gate;
- revise the thesis and contributions to match that verdict;
- select and human-verify one eligible running example;
- regenerate every reported number from canonical artifacts;
- confirm the official EDBT 2027 vision-paper call, page limit, formatting, and artifact rules.

Full-paper drafting must not begin before these gates are satisfied.
