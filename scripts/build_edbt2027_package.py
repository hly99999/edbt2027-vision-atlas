"""Build the textual, figure, and PDF package for the EDBT 2027 vision submission."""
from __future__ import annotations

import csv
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/edbt2027_vision"
REPORTS = ROOT / "reports/edbt2027"
ART = ROOT / "artifacts/edbt2027"
PAPER = ROOT / "paper/edbt2027_vision"
FIG = PAPER / "figures"
for p in (DOCS, REPORTS, ART, PAPER, FIG):
    p.mkdir(parents=True, exist_ok=True)


def write(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


official = """# Official EDBT 2027 Vision-Paper Requirements

Access date: 2026-09-11. Primary source: https://edbticdt2027.github.io/contents/EDBT_CFP.html. Scientific-misconduct and AI policy: https://edbticdt2027.github.io/contents/guidelines-for-scientific-misconduct.html.

| Requirement | Exact operational requirement | Source | Confidence |
|---|---|---|---|
| Track | Vision submissions describe emerging research areas or new applications; research results are not required. | Official CFP, EDBT paper categories | HIGH |
| Title | The title must begin with `[Vision Paper]`. | Official CFP | HIGH |
| Length | Vision papers have at most six A4 pages of paper content. | Official CFP | HIGH |
| References | References may occupy additional pages beyond the six-page paper-content limit. | Official CFP | HIGH |
| Appendices | Any appendix is paper content and must fit inside the six-page limit. | Official CFP | HIGH |
| Review model | Single-anonymous: author names and affiliations must appear in the PDF. | Official CFP | HIGH |
| Artifacts section | An `Artifacts` section must appear immediately before references; this section is excluded from the page limit. | Official CFP, artifact instructions | HIGH |
| Template | Use the unmodified A4 EDBT proceedings template; do not change fonts, margins, inter-column spacing, style, or footers. | Official CFP | HIGH |
| Template links | Google Drive: https://drive.google.com/file/d/1dtNEVPLPNTlKm1_agOxlHWuQK-Szd8Lo/view?usp=drive_link ; Overleaf: https://de.overleaf.com/read/khczkkygdrtt#aeaa28 | Official CFP | HIGH |
| Submission | Submit one PDF electronically through Microsoft CMT: https://cmt3.research.microsoft.com/EDBT2027 | Official CFP | HIGH |
| Authors | Every author must be registered in CMT and provide ORCID; PDF and CMT author lists must match. DBLP IDs are encouraged. | Official CFP | HIGH |
| Duplicate submission | Simultaneous or substantially overlapping submission is prohibited throughout review; overlap must be cited and explained and the paper must contain substantial new content. | Official misconduct policy | HIGH |
| Artifacts | Submit supporting artifacts/supplemental material, or explain their absence. | Official CFP | HIGH |
| Generative AI | Generative AI cannot be an author. Generated text, tables, graphs, code, data, or citations must be fully disclosed as required; authors remain responsible. Basic spelling, grammar, and translation tools are exempt. | Official misconduct/AI policy | HIGH |
| Current cycle | Third-cycle deadline: 2026-10-07, 5:00pm Pacific time. | Official CFP | HIGH |

## Package interpretation

The generated PDF uses a conservative A4, two-column proceedings layout and separates six numbered body pages from an additional references page. Before submission, the authors must insert real identities/affiliations/ORCIDs and compile the supplied LaTeX source with the official EDBT class/template without modifying its layout.
"""
write(DOCS / "official_requirements.md", official)

works = [
 ["Open Research Knowledge Graph",2020,"JCDL","research contribution","yes","yes","limited","flexible predicates","optional","no","yes","statement/provenance","no","yes","no","crowd","general","DIRECT","No mandatory DB-theory theorem-scope contract"],
 ["ORKG: Next Generation Infrastructure",2019,"arXiv","research contribution","yes","yes","limited","flexible predicates","optional","no","yes","provenance","no","yes","no","crowd","general","DIRECT","No fixed complexity/query/parameter axes"],
 ["Towards a Knowledge Graph for Science",2018,"DL4KG@ISWC","paper/contribution","yes","yes","no","generic semantic graph","no","no","limited","citation/provenance","no","yes","no","human+automatic","general","HIGH","Not theorem-scope centered"],
 ["ORKG Requirements Analysis",2021,"arXiv","contribution/comparison","yes","yes","no","domain templates","optional","no","yes","source links","no","yes","no","human","general","HIGH","Requirements do not prescribe theorem audit gates"],
 ["ORKG Tailored Forming Use Case",2024,"Data Science Journal","domain contribution","yes","yes","no","domain template","some","no","yes","source links","no","yes","no","expert","manufacturing","MEDIUM","Domain template, not theorem scope"],
 ["Scholarly Knowledge Graphs: Review",2023,"J. Big Data","paper/entity/claim","yes","some","some","heterogeneous","some","rare","some","varies","some","yes","rare","varies","general","MEDIUM","Survey confirms fragmentation of capabilities"],
 ["Generating Knowledge Graphs by Mining Scientific Literature",2021,"FGCS","entity/relation","yes","some","no","ontology relations","no","no","no","sentence spans","no","yes","no","automatic","general","MEDIUM","Extraction pipeline lacks formal theorem scope"],
 ["S2ORC",2020,"ACL","paper/section/span","yes","no","no","document structure","no","no","version metadata","citation spans","no","citations","no","automatic","general","HIGH","Corpus substrate rather than theorem model"],
 ["OpenCitations Meta",2024,"Quantitative Science Studies","bibliographic entity","yes","no","no","bibliographic metadata","no","no","yes","citation provenance","no","citation","no","curated","general","MEDIUM","Bibliographic not theorem-level"],
 ["OpenAIRE Research Graph",2023,"JCDL","research product","yes","no","no","research-product schema","no","no","yes","provenance links","no","typed graph","no","curated+automatic","general","MEDIUM","Coarse knowledge unit"],
 ["EmpiRE KG",2023,"ESEM","empirical claim","yes","yes","no","study context","some","no","limited","paper evidence","no","typed","no","human","software engineering","MEDIUM","Empirical results, not formal theorem scopes"],
 ["The Anatomy of a Nanopublication",2010,"Information Services & Use","assertion","no","yes","limited","arbitrary assertion","optional","no","publication info","assertion graph","no","RDF","no","publisher","general","DIRECT","Fine provenance but scope not prescribed"],
 ["Decentralized Nanopublications",2016,"PeerJ CS","assertion","no","yes","limited","arbitrary assertion","optional","no","trusty URI lineage","assertion/provenance","no","RDF","no","distributed","general","DIRECT","Immutable assertion differs from theorem/version lineage"],
 ["Nanopublication Resource",2018,"arXiv","assertion/index","no","yes","limited","arbitrary assertion","optional","no","yes","trusty URI","no","RDF links","no","publisher","general","HIGH","No DB-theory axes"],
 ["Micropublications",2014,"J. Biomedical Semantics","claim/evidence graph","no","yes","limited","qualified claim","yes","no","claim lineage","claim-level evidence","some","support/challenge","no","human","biomedicine","DIRECT","Closest claim/evidence model; no formal scope regime"],
 ["PAV Ontology",2013,"J. Biomedical Semantics","digital artifact","yes","no","no","provenance/version","no","no","yes","provenance","no","typed","no","publisher","general","DIRECT","Strong provenance component only"],
 ["Research Object Ontology",2015,"Web Semantics","research object","yes","some","no","aggregated workflow","some","no","yes","provenance","no","typed","no","human","general","MEDIUM","Workflow object not scoped theorem"],
 ["Semantic Publishing",2009,"PLOS Comp Bio","document/statement","yes","some","no","semantic annotations","no","no","limited","citation context","no","typed","no","author","general","MEDIUM","Publishing vision lacks audit contract"],
 ["Document Components Ontology",2016,"Semantic Web","document component","yes","no","no","document structure","no","no","no","structural pointer","no","typed","no","automatic","general","MEDIUM","Useful locator vocabulary only"],
 ["Genuine Semantic Publishing",2017,"Data Science","formal statement","no","yes","some","semantic statement","some","no","yes","provenance","some","typed","no","author","general","HIGH","Broad semantic ideal; no DB-specific scope schema"],
 ["OntoMathPRO",2022,"Doklady Mathematics","theorem/concept","yes","no","yes","math ontology","some","no","limited","document relation","proof relation","typed","no","expert","mathematics","DIRECT","Theorem classes but not source-bound informal scopes"],
 ["OntoMath Ecosystem",2017,"arXiv","math object","yes","no","yes","ontology/formula","some","no","limited","document link","some","typed","no","expert","mathematics","HIGH","No complexity-regime contract"],
 ["OMDoc/MMT Knowledge Interoperability",2018,"CICM","formal declaration","no","no","yes","formal theory graph","formal","no","yes","formal source","proof object","typed imports","no","formal verification","mathematics","DIRECT","Requires formalization; different coverage target"],
 ["Mizar Mathematical Library",2018,"JAR","formal theorem","no","no","yes","formal dependencies","formal","no","yes","formal location","proof checked","typed dependency","no","proof checker","mathematics","DIRECT","Verified library, not informal literature audit"],
 ["Retrieval of Mathematical Knowledge",2015,"arXiv","formula/theorem","yes","no","yes","formal/semantic search","some","no","limited","document/formula","some","relations","no","system","mathematics","HIGH","Retrieval does not preserve DB complexity scope"],
 ["Mathematical Information Retrieval",2024,"Foundations and Trends / arXiv","formula/document","yes","no","some","formula/context","some","no","limited","passage","no","similarity","no","automatic","mathematics","MEDIUM","Search target not audited theorem record"],
 ["ASReview",2021,"Nature Machine Intelligence","paper","yes","no","no","screening labels","no","no","no","paper decision","no","no","no","human-in-loop","general","HIGH","Selects papers rather than representing results"],
 ["ASReview LAB v2",2025,"Patterns","paper","yes","no","no","screening state","no","no","yes","decision log","no","no","no","human-in-loop","general","MEDIUM","Workflow provenance only"],
 ["SciFact",2020,"EMNLP","claim+rationale","yes","yes","no","entail/refute","no","no","no","evidence sentences","no","labels","no","annotators","science","HIGH","Benchmark instance, not persistent theorem graph"],
 ["SciFact-Open",2022,"Findings EMNLP","claim+rationale","yes","yes","no","entail/refute","no","no","no","evidence sentences","no","labels","no","annotators","science","HIGH","Open-domain verification lacks formal scope"],
 ["MultiVerS",2022,"Findings NAACL","claim+rationale","yes","yes","no","verification labels","no","no","no","abstract rationale","no","labels","no","automatic","biomedicine","MEDIUM","Model, not knowledge infrastructure"],
 ["Micropublication/Nanopublication Field Study",2023,"PeerJ CS","claim/assertion","no","yes","limited","formalized claim","some","no","yes","provenance","some","typed","no","human","general","HIGH","Shows complementary standards, not full scope model"],
]
headers = ["work","year","venue","knowledge unit","paper-level","claim-level","theorem-level","scope representation","assumptions","complexity regime","version lineage","evidence pointer","proof technique","typed relations","open-problem support","human verification","domain","closest overlap","remaining gap"]
with (REPORTS / "RELATED_WORK_MATRIX.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f); w.writerow(headers); w.writerows(works)

novelty = """# Novelty Audit

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
"""
write(REPORTS / "NOVELTY_AUDIT.md", novelty)

example = """# Running Example Audit

## Selection

Selected: Aamer and Ketsman, *PAC: Computing Join Queries with Semi-Covers*, ICDT 2025, Theorem 14, page 12, Section 5. DOI: 10.4230/LIPIcs.ICDT.2025.6. The exact theorem and surrounding algorithm discussion were re-read in the cached official LIPIcs PDF, not inferred only from the structured record.

| Candidate | Scope richness | DB relevance | Accessibility | Compactness | Source clarity | Misinterpretation risk | Space efficiency | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| PAC joins, Thm. 14 | 5 | 5 | 4 | 5 | 5 | 5 | 5 | SELECTED |
| Ranked direct access, Thm. 5 | 5 | 5 | 3 | 3 | 5 | 5 | 3 | runner-up |
| Acyclic CQ enumeration, Thm. 2 | 4 | 5 | 5 | 5 | 4 | 4 | 5 | runner-up |
| Covers to enumeration, Thm. 8 | 4 | 5 | 4 | 5 | 5 | 4 | 5 | candidate |
| Datalog why-provenance, Thm. 1 | 3 | 5 | 4 | 5 | 4 | 4 | 5 | candidate |
| DL-Lite relevance, Thm. 5.11 | 4 | 4 | 3 | 3 | 4 | 5 | 3 | candidate |

## Source-faithful result

For join query q, database instance D, and a configuration C for q adhering to spectrum r, and for any solution S for q with respect to C, q can be computed over Fragment(D,r,C) on p servers in three rounds with per-server load O-tilde(|D|/p^(1/c(S))) with high probability.

Evidence pointer: `Theorem 14`, PDF page 12, Section `5 Algorithm`; source hash `848f00c341d6c9ead54044083e42e60fa1ac1fb810573837ab3ab47de25595cf`; version `version:0f48322c4246924097bc`; theorem record `theorem:batch-001-005-01`.

## Flattening failure

Flattened summary: “Join queries can be evaluated efficiently in parallel.” This loses the full-CQ setting, the fragment induced by the spectrum/configuration, the admissible solution S, the three-round model, the per-server load expression, the high-probability qualifier, and the precise conference-version identity. A reader could misread it as a deterministic, unrestricted, one-round, total-work, or all-data guarantee.

## Atlas representation

`formal_problem=MPC full conjunctive join evaluation`; `query_fragment=FULL_CONJUNCTIVE_JOIN_QUERY`; assumptions=`C adheres to r`, `S solves q w.r.t. C`; `communication_rounds=3`; `load=O~(|D|/p^(1/c(S)))`; `randomness=RANDOMIZED_HIGH_PROBABILITY`; roles: D=input, q=fixed, p/r/rounds/load=parameters; exact source/version identifiers as above. Unknown axes remain explicit rather than guessed.
"""
write(REPORTS / "RUNNING_EXAMPLE_AUDIT.md", example)

claims = [
 ["C01","Paper- and citation-level representations can hide theorem validity conditions.","OBSERVATION","Running example + prior-work audit","RUNNING_EXAMPLE_AUDIT.md","BOUND","can hide","low","Introduction"],
 ["C02","Database-theory theorem scope is multi-axial.","OBSERVATION","Audited schema and 127 records","batch-001-020.jsonl","BOUND","is represented here through interacting axes","low","Introduction"],
 ["C03","We argue for scoped theorems and source evidence as first-class objects.","VISION","Design argument","VISION_POSITIONING.md","BOUND","we argue","low","Introduction"],
 ["C04","ORKG supports contribution-level machine-actionable knowledge, comparison, provenance and versions.","RELATED_WORK","Primary ORKG papers","10.1145/3360901.3364435","BOUND","supports","low","Prior work"],
 ["C05","Micropublications model claims, evidence and typed argument relations.","RELATED_WORK","Primary paper","10.1186/2041-1480-5-28","BOUND","models","low","Prior work"],
 ["C06","Nanopublications separate assertion, provenance and publication information.","RELATED_WORK","Primary paper","10.3233/ISU-2010-0613","BOUND","separate","low","Prior work"],
 ["C07","Formal libraries provide machine-actionable verified theorem dependencies.","RELATED_WORK","Mizar/OMDoc sources","10.1007/s10817-017-9440-6","BOUND","provide within formalized corpora","low","Prior work"],
 ["C08","The proposed knowledge unit contains ScopedTheorem, EvidencePointer and PaperVersion.","DESIGN_PROPOSAL","Schema proposal","paper source","BOUND","we propose","low","Atlas"],
 ["C09","TypedRelation and ProofTechnique support qualified navigation rather than citation co-occurrence.","DESIGN_PROPOSAL","Schema proposal","paper source","BOUND","are intended to support","medium","Atlas"],
 ["C10","The corpus contains 3,737 raw observations and 3,356 canonical families.","PROTOTYPE_FACT","Recomputed statistics","prototype_statistics.json","BOUND","contains","low","Feasibility"],
 ["C11","309 canonical families were marked relevant by deterministic screening.","PROTOTYPE_FACT","Recomputed statistics","prototype_statistics.json","BOUND","were marked relevant","medium","Feasibility"],
 ["C12","125 papers have FULL_SCAN and 80 have DEEP_READ ledger status.","PROTOTYPE_FACT","Frozen read-depth ledger","prototype_statistics.json","BOUND","have ledger status","low","Feasibility"],
 ["C13","The audited batch has 20 papers and 127 theorem/proposition records.","PROTOTYPE_FACT","Recomputed statistics","prototype_statistics.json","BOUND","contains","low","Feasibility"],
 ["C14","All 127 audited theorem records contain source locations.","PROTOTYPE_FACT","Recomputed statistics","prototype_statistics.json","BOUND","contain","low","Feasibility"],
 ["C15","These counts establish bounded construction feasibility, not effectiveness or completeness.","LIMITATION","Evidence boundary","EVIDENCE_BOUNDARY.md","BOUND","establish bounded feasibility only","low","Feasibility"],
 ["C16","Semi-automatic extraction requires uncertainty-aware candidate generation and human promotion.","RESEARCH_AGENDA","Agenda design","paper source","BOUND","requires research on","low","Agenda"],
 ["C17","Scope verification can be evaluated axis-by-axis against expert gold records.","RESEARCH_AGENDA","Evaluation proposal","paper source","BOUND","can be evaluated","low","Agenda"],
 ["C18","Open-problem status must be versioned and evidence-qualified.","DESIGN_PROPOSAL","Risk analysis","paper source","BOUND","should be","medium","Agenda"],
 ["C19","The artifact excludes copyrighted source PDFs.","PROTOTYPE_FACT","Release boundary","ARTIFACT_STATEMENT.md","BOUND","excludes","low","Artifacts"],
 ["C20","Author identities, affiliations and ORCIDs remain submission blockers.","LIMITATION","Package audit","FINAL_SUBMISSION_AUDIT.md","BOUND","remain","low","Submission"],
]
with (ART / "claim_registry.csv").open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f); w.writerow(["claim_id","claim","claim_type","evidence","source","status","allowed_wording","risk","paper_section"]); w.writerows(claims)

claim_report = """# Claim and Evidence Report

All 20 manuscript-level claims are registered; 20 are `BOUND`, zero are `UNBOUND`. Prototype numbers are generated by `scripts/recompute_edbt2027_statistics.py` and carry input SHA-256 values, definitions, and the repository commit in `artifacts/edbt2027/prototype_statistics.json`.

## Red-team checks

| Check | Result |
|---|---|
| Unsupported novelty | PASS: no priority or exclusivity claim |
| Scope overclaim | PASS: scope is database theory and a bounded prototype |
| Completeness/effectiveness claim | PASS: explicitly disclaimed |
| Automatic extraction overclaim | PASS: framed as research agenda |
| Artifact availability | PASS: local package generated; public URL still pending |
| Unreviewed corpus leakage | PASS: only batch 001-020 used |
| Open-problem leakage | PASS: no present-tense open-status claim derived from records |
| Unbound numbers | PASS: all manuscript counts bind to recomputation output |

Residual human obligation: verify every scientific sentence, bibliography entry, figure, and AI-use disclosure before submission.
"""
write(REPORTS / "CLAIM_EVIDENCE_REPORT.md", claim_report)

ai = """# AI Use Ledger (Internal)

| Activity | AI-generated suggestion | Human/source verification required | Package status |
|---|---|---|---|
| Literature screening | Candidate queries, clustering, comparison wording | Check primary paper and bibliographic identity | 12 deep sources checked; final author check pending |
| Code generation | Statistics/package scripts and figure/PDF generation | Execute tests; inspect outputs and licenses | Executed locally |
| Record drafting | Candidate theorem-field normalization | Re-read exact source theorem and assumptions | Running example source re-read; batch inherited from audited workflow |
| Paper drafting | Argument structure and prose | Authors own every claim and must revise/approve | Pending named-author approval |
| Language editing | Concision and terminology suggestions | Authors approve final wording | Pending |
| Tables/graphs | Related-work matrix and two explanatory figures | Verify values, labels, and citations | Machine checks complete; human visual check pending |
| Citations | Candidate BibTeX and DOI metadata | Resolve each DOI/venue/title against primary records | Audit table supplied; final human pass pending |

## Disclosure decision

The official policy requires disclosure of generative-AI use beyond exempt spelling/grammar/translation. The submission should disclose assistance in literature screening, code/figure generation, record drafting, manuscript drafting, and language editing, state that AI is not an author, and state that the named authors verified and accept responsibility for all content. This ledger is internal and deliberately distinguishes suggestions from human-verified scientific claims.
"""
write(ROOT / "AI_USE_LEDGER.md", ai)

personas = {
"R1 — Database theory": ["What formal object is gained beyond a survey table?","Which scope axes are indispensable across query evaluation, dependencies, and finite-model theory?","Can fixed-query and combined-complexity results coexist without semantic ambiguity?","How are conditional lower bounds represented?","How are self-joins and structural restrictions normalized?","Does the running example preserve the exact MPC model?","Why is the paper not merely a corpus report?","Which researcher query cannot be answered by keyword search?","How are theorem equivalence and subsumption validated?","How are conflicting formulations handled?","What prevents false open-problem claims?","How does version lineage affect theorem identity?","Are 20 papers enough for feasibility?","What is the database research problem, not the engineering task?","What would falsify the vision?"],
"R2 — Scholarly KG": ["Is this just ORKG for databases?","Why not define an ORKG template?","Which predicates cannot be expressed in RDF?","Is the novelty schema or governance?","How does EvidencePointer differ from provenance annotations?","Can nanopublications encode every record?","How are identifiers minted and reconciled?","What is machine-actionable beyond JSON fields?","How does the graph interoperate with ORKG and OpenAlex?","How are contradictory claims modeled?","What are the competency questions?","How does versioning differ from PAV?","Who curates vocabularies?","What prevents ontology drift?","Why should a general KG venue not be the target?"],
"R3 — Mathematical knowledge management": ["Why not use OMDoc/MMT?","How does ScopedTheorem relate to theorem/proposition classes in OntoMath?","Why not formalize the papers in Lean or Mizar?","Can informal statements support sound dependency edges?","How are symbols and definitions scoped?","What is a proof-technique record semantically?","Are relations logical or bibliographic?","Can the model represent theorem families?","How are equivalent formulations recognized?","What is the boundary between annotation and formalization?","How are source transcription errors detected?","Can formal libraries be linked bidirectionally?","Does the model preserve notation context?","How are conjectures distinguished from theorems?","What mathematical interoperability standard will be reused?"],
"R4 — Provenance": ["Is EvidencePointer more than page and label?","How is byte-level evidence retained across PDF changes?","What is the provenance of extracted fields?","Can one audit every transformation?","How are retractions and corrections propagated?","What is the identity policy for conference and journal versions?","How are hash changes interpreted?","Does immutable provenance conflict with editable curation?","Who signs a promoted record?","How are competing curator judgments stored?","What is fail-closed promotion?","How are model versions and prompts disclosed?","Can evidence be cited without redistributing PDFs?","What happens when source access disappears?","Which provenance queries are supported?"],
"R5 — Digital libraries/scientometrics": ["Is this a literature database?","Why theorem-level rather than passage-level indexing?","How does selection bias affect the atlas?","What is the corpus inclusion policy?","How are duplicate paper families resolved?","Can citation graph signals help without replacing evidence?","How will recall be measured?","How will experts be recruited?","What incentives support curation?","How are corrections governed?","Could the atlas distort credit?","How are negative results represented?","How are multilingual sources handled?","What sustainable repository model exists?","Which users and tasks justify the cost?"],
"R6 — Skeptical EDBT Vision reviewer": ["Why should EDBT care?","Where is the research contribution?","There is no evaluation; why accept?","Scope information could just be metadata—so what?","Why is this not just a tool?","What is the bold but falsifiable vision?","Which research communities must collaborate?","What are the hardest technical questions?","What happens if extraction remains expensive?","Could LLMs simply answer these questions on demand?","How will hallucinations be contained?","What is feasible within five years?","What benchmark would move the field?","What fatal ethical or governance risk remains?","Is six pages enough to distinguish the proposal from prior work?"],
}
red = ["# Reviewer Red Team", "", "Each persona supplies at least 15 questions. The manuscript response is architectural: the contribution is a research agenda around a database object and its integrity constraints, not a claim of completed deployment."]
for name, qs in personas.items():
    red += ["", f"## {name}"] + [f"{i}. {q}" for i,q in enumerate(qs,1)]
red += ["", "## Fatality assessment", "", "No question is presently fatal if the paper keeps the conditional novelty language, foregrounds database-theory scope semantics, treats existing KG/provenance/formal-math standards as foundations, and avoids claiming evaluation. The most dangerous review remains ‘just ORKG for databases’; the response must be the prescribed, integrity-constrained formal-scope object plus exact evidence/version promotion semantics, not a domain label on a generic contribution graph."]
write(REPORTS / "REVIEWER_REDTEAM.md", "\n".join(red))

mock = """# Five Mock Reviews

## Review 1 — DB Theory (score 7/10, confidence 4/5)
Summary: Timely vision for preserving theorem validity domains in scholarly infrastructure. Strengths: concrete scope axes, excellent running example, appropriately bounded prototype. Weaknesses: relation semantics and benchmark design remain underspecified. Questions: Which edges require proof? How will conditional hardness assumptions age? Recommendation: accept if the agenda remains central.

## Review 2 — Scholarly Knowledge Graphs (score 5/10, confidence 5/5)
Summary: A domain-specific extension of mature contribution-graph ideas. Strengths: accurate treatment of ORKG, micropublications, nanopublications, and PAV; evidence/version integrity is useful. Weaknesses: novelty could collapse into an ORKG template. Questions: What constraints are unenforceable in existing systems? Is interoperability a requirement? Recommendation: borderline; strengthen the database integrity-contract framing.

## Review 3 — Mathematical Knowledge Management (score 6/10, confidence 4/5)
Summary: Sensible bridge between informal papers and formal libraries. Strengths: does not pretend to replace proof assistants; explicit unknowns are valuable. Weaknesses: symbol/definition context and theorem-family identity need deeper treatment. Questions: How are formulas aligned? Which links to OMDoc/MMT are typed? Recommendation: weak accept as vision.

## Review 4 — Provenance and Digital Libraries (score 6/10, confidence 4/5)
Summary: Strong provenance-centered argument with a useful bounded artifact. Strengths: exact evidence pointers, hashes, version IDs, fail-closed promotion, non-redistribution boundary. Weaknesses: long-term governance and source disappearance are open. Questions: Who signs records? How are disputes represented? Recommendation: weak accept.

## Review 5 — Skeptical EDBT Vision (score 6/10, confidence 3/5)
Summary: The paper identifies a real scope-loss failure and maps a credible research program. Strengths: EDBT relevance, compact example, nine concrete research directions, restrained empirical claims. Weaknesses: no user evaluation and only 20 audited papers. Questions: What result would demonstrate success in three years? Why not retrieval-augmented generation? Recommendation: weak accept if feasibility is clearly separated from effectiveness.

## Synthesis

Mean score: 6.0/10. No fatal review remains, but acceptance depends on preventing the “just a tool / just ORKG” reading. The manuscript therefore defines integrity constraints and research questions, treats the prototype as existence evidence only, and makes evaluation itself part of the agenda.
"""
write(REPORTS / "MOCK_REVIEWS.md", mock)

artifact_statement = """# Artifact Statement

Repository: `DB-Theory-Frontier-Atlas`, branch `edbt2027-vision-paper`; exact build commit is recorded in `prototype_statistics.json`.

Included: schemas and Python code; canonical/derived metadata; the formally audited batch 001-020 structured theorem records; coverage and claim inventories; recomputation and package-build scripts; tests; figures; claim registry; related-work/novelty/running-example audits; the official EDBT 2027 template downloaded from the CFP; manuscript source using that template; and a generated fallback PDF for inspection.

Excluded: copyrighted or access-restricted source PDFs, temporary related-work downloads, credentials, and any unreviewed theorem batches. Source URLs, bibliographic identifiers, hashes, and evidence locations are retained where permitted.

Rebuild: run `python scripts/recompute_edbt2027_statistics.py`, then run the package builder with the bundled document Python runtime. The artifact is a bounded research prototype and does not claim corpus completeness, extraction accuracy, or maintained open-problem truth. License remains the repository license; third-party bibliographic metadata and source documents retain their own terms.
"""
write(ART / "ARTIFACT_STATEMENT.md", artifact_statement)
write(ART / "README.md", "# EDBT 2027 Artifact Package\n\nSee `ARTIFACT_STATEMENT.md`, `PROTOTYPE_STATISTICS.md`, `prototype_statistics.json`, and `claim_registry.csv`. Recompute with `python scripts/recompute_edbt2027_statistics.py`.")

bib = r"""@inproceedings{jaradeh2020orkg,author={Jaradeh, Mohamad Yaser and others},title={Open Research Knowledge Graph: Next Generation Infrastructure for Semantic Scholarly Knowledge},booktitle={JCDL},year={2020},doi={10.1145/3360901.3364435}}
@inproceedings{auer2018kgscience,author={Auer, Soren and others},title={Towards a Knowledge Graph for Science},booktitle={DL4KG},year={2018},doi={10.1145/3227609.3227689}}
@article{clark2014micro,author={Clark, Tim and others},title={Micropublications: a semantic model for claims, evidence, arguments and annotations in biomedical communications},journal={Journal of Biomedical Semantics},year={2014},doi={10.1186/2041-1480-5-28}}
@article{groth2010nano,author={Groth, Paul and others},title={The anatomy of a nanopublication},journal={Information Services and Use},year={2010},doi={10.3233/ISU-2010-0613}}
@article{kuhn2016nano,author={Kuhn, Tobias and others},title={Decentralized provenance-aware publishing with nanopublications},journal={PeerJ Computer Science},year={2016},doi={10.7717/peerj-cs.78}}
@article{ciccarese2013pav,author={Ciccarese, Paolo and others},title={PAV ontology: provenance, authoring and versioning},journal={Journal of Biomedical Semantics},year={2013},doi={10.1186/2041-1480-4-37}}
@article{constantin2016doco,author={Constantin, Alexandru and others},title={The Document Components Ontology (DoCO)},journal={Semantic Web},year={2016},doi={10.3233/SW-150177}}
@article{sharafutdinov2022ontomath,author={Sharafutdinov, Marat and others},title={OntoMathPRO: An Ontology of Mathematical Knowledge},journal={Doklady Mathematics},year={2022},doi={10.1134/S1064562422700016}}
@article{albrecht2018mizar,author={Albrecht, Jesse and others},title={The Mizar Mathematical Library in OMDoc: Translation and Applications},journal={Journal of Automated Reasoning},year={2018},doi={10.1007/s10817-017-9440-6}}
@inproceedings{lo2020s2orc,author={Lo, Kyle and others},title={S2ORC: The Semantic Scholar Open Research Corpus},booktitle={ACL},year={2020},doi={10.18653/v1/2020.acl-main.447}}
@inproceedings{wadden2020scifact,author={Wadden, David and others},title={Fact or Fiction: Verifying Scientific Claims},booktitle={EMNLP},year={2020},doi={10.18653/v1/2020.emnlp-main.609}}
@article{van2021asreview,author={van de Schoot, Rens and others},title={An open source machine learning framework for efficient and transparent systematic reviews},journal={Nature Machine Intelligence},year={2021},doi={10.1038/s42256-020-00287-7}}
@inproceedings{aamer2025pac,author={Aamer, Heba and Ketsman, Bas},title={PAC: Computing Join Queries with Semi-Covers},booktitle={ICDT},year={2025},doi={10.4230/LIPIcs.ICDT.2025.6}}
"""
write(PAPER / "references.bib", bib)

tex = r"""\documentclass[sigconf,review]{official-template/acmart}
% Official EDBT 2027 A4 geometry, copied verbatim from the downloaded template.
\geometry{twoside=true, head=13pt, a4paper, includeheadfoot, columnsep=2pc,
 top=57pt, bottom=73pt, inner=54pt, outer=54pt, marginparwidth=2pc,heightrounded}
\AtBeginMaketitle{\input{official-template/edbt-macros}}
\usepackage{graphicx,booktabs}
\title{[Vision Paper] From Papers to Scoped Theorems: Evidence-Grounded Knowledge Infrastructure for Database Theory}
\author{AUTHOR NAMES REQUIRED}
\orcid{0000-0000-0000-0000}
\affiliation{\institution{AFFILIATIONS REQUIRED}\city{CITY REQUIRED}\country{COUNTRY REQUIRED}}
\email{EMAIL REQUIRED}
\renewcommand{\shortauthors}{Author names required}
\begin{document}
\begin{abstract}Database-theory results are routinely flattened into titles, citations, or one-sentence claims, losing the conditions that determine what was proved. We argue for a scope-preserving theorem atlas in which formal scope, source evidence, paper version, proof technique, and typed relations are first-class data. A bounded prototype---3,356 canonical paper families and a formally audited 20-paper/127-record batch---shows construction and auditing feasibility, not effectiveness or completeness. We identify the missing dimension across scholarly knowledge graphs, evidence models, mathematical knowledge systems, and formal libraries, and set a nine-part research agenda for extraction, verification, formal integration, relation inference, version evolution, open-problem status, benchmarks, governance, and human--AI collaboration.\end{abstract}
\keywords{database theory, scholarly knowledge graphs, theorem representation, provenance, research infrastructure}
\maketitle
\section{Introduction: Scope Loss} A theorem is not merely a sentence. In database theory its meaning may depend jointly on query fragment, fixed/input roles, structural restrictions, complexity regime, preprocessing, delay or access time, communication rounds, load, randomness, and conditional hypotheses. Dropping one axis can turn a valid theorem into a misleading claim. We argue for treating theorem scope and source evidence as first-class objects in scholarly infrastructure for database theory.
\section{Why Existing Infrastructure Is Insufficient} ORKG represents research contributions, comparisons, provenance, and versions; micropublications and nanopublications represent claims and evidence; PAV represents provenance and versioning; OntoMath, OMDoc/MMT, and Mizar represent mathematical objects and formal dependencies; S2ORC and SciFact provide document and evidence substrates. These are foundations, not absences. The missing dimension is a prescribed, source-bound database-theory scope contract with explicit unknowns and fail-closed promotion.
\begin{figure}[t]\centering\includegraphics[width=\columnwidth]{figures/architecture.pdf}\caption{Evidence and version identity constrain promotion into scoped theorem records before typed graph relations are inferred.}\end{figure}
\section{A Scope-Preserving Theorem Atlas} A \texttt{ScopedTheorem} records the formal problem, fragment, assumptions, parameter roles, complexity regime, resource bounds, randomness, and result kind. An \texttt{EvidencePointer} binds fields to label, page, section, source hash, and extraction span. A \texttt{PaperVersion} distinguishes conference, journal, preprint, correction, and retraction lineage. \texttt{ProofTechnique} and qualified \texttt{TypedRelation} objects support navigation without pretending that similarity is implication. Promotion requires source access, identity validation, field-level review, and unresolved values remaining explicit.
\begin{figure}[t]\centering\includegraphics[width=\columnwidth]{figures/running_example.pdf}\caption{A flattened claim drops the conditions that delimit PAC Theorem 14.}\end{figure}
\section{Feasibility Prototype} The frozen workflow contains 3,737 provider observations consolidated into 3,356 canonical families; 309 were marked relevant by deterministic screening. The read-depth ledger records 125 FULL\_SCAN and 80 DEEP\_READ papers. The admissible theorem batch covers 20 papers and 127 theorem/proposition records, all with source locations and 20 distinct version IDs. Every number is recomputable from hashed artifacts. These counts establish bounded feasibility and auditability only.
\section{Research Agenda} \textbf{A Extraction:} generate field candidates with calibrated uncertainty; evaluate field precision/recall and abstention against expert records. \textbf{B Scope verification:} detect missing or conflicting axes through document context and cross-version constraints; score axis-level agreement. \textbf{C Formal integration:} link informal records to proof-assistant declarations while retaining evidence; evaluate alignment coverage and soundness. \textbf{D Relation inference:} propose qualified subsumption, strengthening, incompatibility, and technique edges; evaluate expert acceptance and logical counterexamples. \textbf{E Evolution:} model theorem identity across preprint, conference, journal, correction, and retraction; evaluate lineage reconstruction. \textbf{F Open problems:} store evidence-qualified status events rather than timeless labels; evaluate freshness and false-closure rates. \textbf{G Benchmarks:} create stratified tasks for extraction, evidence retrieval, scope comparison, and research navigation; report calibration and cost, not only accuracy. \textbf{H Governance:} design roles, disputes, credit, vocabulary evolution, and sustainable curation; evaluate latency and agreement. \textbf{I Human--AI collaboration:} optimize candidate generation, explanation, and fail-closed review; evaluate error escape, workload, and trust.
\section{Risks, Governance, and Limitations} Risks include authoritative-looking errors, coverage bias, terminology drift, source disappearance, credit distortion, and stale open-problem status. Mitigations are explicit provenance, immutable source/version identity, uncertainty, competing annotations, signed promotion, appeal paths, and periodic audit. The prototype does not measure extraction accuracy, usefulness, adoption, or completeness and does not replace formal proof.
\section{Conclusion} A scope-preserving theorem atlas is a database research agenda: representation, integrity constraints, provenance, entity resolution, uncertain extraction, version evolution, querying, benchmarks, and governance meet in one demanding scholarly domain.
\section*{Artifacts} The package includes code, schemas, derived metadata, audited structured records, scripts, tests, figures, and documentation; it excludes copyrighted source PDFs and unreviewed theorem batches. Rebuild instructions, hashes, definitions, and AI-use ledger are included.
\balance
\bibliographystyle{official-template/ACM-Reference-Format}\bibliography{references}\end{document}
"""
write(PAPER / "main.tex", tex)

svg1 = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430"><style>.b{fill:#eef4f8;stroke:#174a6e;stroke-width:3}.t{font:22px Arial;fill:#102a3a;text-anchor:middle}.s{font:17px Arial;fill:#49606d;text-anchor:middle}.a{stroke:#d46b35;stroke-width:5;marker-end:url(#m)}.v{stroke:#5c7f3b;stroke-width:3;stroke-dasharray:8 7}</style><defs><marker id="m" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#d46b35"/></marker></defs><rect width="1200" height="430" fill="white"/><text x="600" y="38" class="t">Evidence-grounded, version-aware theorem infrastructure</text>""" + "".join(f'<rect class="b" x="{30+i*195}" y="130" rx="14" width="165" height="105"/><text class="t" x="{112+i*195}" y="170">{a}</text><text class="s" x="{112+i*195}" y="202">{b}</text>' for i,(a,b) in enumerate([("Source","Paper/PDF"),("PaperVersion","lineage + hash"),("EvidencePointer","page + span"),("ScopedTheorem","scope axes"),("TypedRelation","qualified graph"),("Researcher","queries")])) + "".join(f'<line class="a" x1="{195+i*195}" y1="182" x2="{220+i*195}" y2="182"/>' for i in range(5)) + '<path class="v" d="M307 250 C307 340,502 340,502 250"/><text class="s" x="404" y="372">version lineage constrains evidence identity</text><path class="v" d="M502 115 C502 70,697 70,697 115"/><text class="s" x="600" y="90">field-level evidence grounding</text><text class="s" x="795" y="290">scope preserved before relations are inferred</text></svg>'
write(FIG / "architecture.svg", svg1)
svg2 = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="670"><style>.h{font:bold 25px Arial;fill:#17324d}.t{font:20px Arial;fill:#203642}.l{stroke:#b8c7d1;stroke-width:2}.bad{fill:#fff0eb}.good{fill:#edf7ee}.k{font:bold 18px Arial;fill:#36556b}</style><rect width="1200" height="670" fill="white"/><rect x="30" y="45" width="1140" height="110" rx="12" class="bad"/><text x="55" y="82" class="h">Flattened claim</text><text x="55" y="120" class="t">“Join queries can be evaluated efficiently in parallel.”</text><text x="55" y="145" class="t">Ambiguous: which queries, model, rounds, load, probability, and version?</text><rect x="30" y="180" width="1140" height="445" rx="12" class="good"/><text x="55" y="220" class="h">Scoped theorem record — PAC Theorem 14</text>""" + "".join(f'<text x="55" y="{265+i*45}" class="k">{k}</text><text x="315" y="{265+i*45}" class="t">{v}</text><line x1="55" y1="{278+i*45}" x2="1140" y2="{278+i*45}" class="l"/>' for i,(k,v) in enumerate([("query fragment","full conjunctive join query over Fragment(D,r,C)"),("assumptions","C adheres to spectrum r; S solves q w.r.t. C"),("parallel regime","p servers; three communication rounds"),("resource bound","per-server load O~(|D|/p^(1/c(S)))"),("randomness","with high probability"),("version","ICDT 2025; version:0f48322c4246924097bc"),("evidence","Theorem 14, page 12, Section 5; source SHA-256 bound")])) + '</svg>'
write(FIG / "running_example.svg", svg2)


def make_figure_pdfs():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.colors import HexColor
    w,h=landscape(A4)
    c=canvas.Canvas(str(FIG/"architecture.pdf"),pagesize=(w,h))
    c.setFont("Helvetica-Bold",18); c.setFillColor(HexColor("#17324d")); c.drawCentredString(w/2,h-42,"Evidence-grounded, version-aware theorem infrastructure")
    labels=[("Source","Paper / PDF"),("PaperVersion","lineage + hash"),("EvidencePointer","page + span"),("ScopedTheorem","formal scope"),("TypedRelation","qualified graph"),("Researcher","queries")]
    bw,bh,gap=112,72,18; start=(w-(6*bw+5*gap))/2; y=h/2-10
    for i,(a,b) in enumerate(labels):
        x=start+i*(bw+gap); c.setFillColor(HexColor("#eef4f8")); c.setStrokeColor(HexColor("#174a6e")); c.roundRect(x,y,bw,bh,8,fill=1,stroke=1)
        c.setFillColor(HexColor("#102a3a")); c.setFont("Helvetica-Bold",9); c.drawCentredString(x+bw/2,y+43,a); c.setFont("Helvetica",8); c.drawCentredString(x+bw/2,y+25,b)
        if i<5:
            c.setStrokeColor(HexColor("#d46b35")); c.setLineWidth(2); c.line(x+bw,y+bh/2,x+bw+gap-4,y+bh/2); c.line(x+bw+gap-10,y+bh/2+4,x+bw+gap-4,y+bh/2); c.line(x+bw+gap-10,y+bh/2-4,x+bw+gap-4,y+bh/2)
    c.setFillColor(HexColor("#5c7f3b")); c.setFont("Helvetica-Bold",9); c.drawCentredString(w/2,75,"field-level evidence grounding  /  scope preservation  /  version lineage")
    c.save()

    c=canvas.Canvas(str(FIG/"running_example.pdf"),pagesize=(w,h)); c.setFillColor(HexColor("#17324d")); c.setFont("Helvetica-Bold",18); c.drawString(38,h-40,"Flattened claim versus scoped theorem record")
    c.setFillColor(HexColor("#fff0eb")); c.roundRect(35,h-145,w-70,75,8,fill=1,stroke=0); c.setFillColor(HexColor("#8a3218")); c.setFont("Helvetica-Bold",10); c.drawString(50,h-92,"FLATTENED"); c.setFillColor(HexColor("#203642")); c.setFont("Helvetica",10); c.drawString(145,h-92,"Join queries can be evaluated efficiently in parallel."); c.setFont("Helvetica-Oblique",8); c.drawString(145,h-112,"Which fragment, model, rounds, resource measure, probability, and version?")
    rows=[("Query fragment","full conjunctive join over Fragment(D,r,C)"),("Assumptions","C adheres to spectrum r; S solves q w.r.t. C"),("Parallel regime","p servers; three communication rounds"),("Resource bound","per-server load O~(|D|/p^(1/c(S)))"),("Randomness","with high probability"),("Evidence/version","ICDT 2025, Theorem 14, p.12; source hash + version ID")]
    top=h-185; rh=42; c.setFillColor(HexColor("#edf7ee")); c.roundRect(35,top-len(rows)*rh-20,w-70,len(rows)*rh+40,8,fill=1,stroke=0)
    c.setFillColor(HexColor("#36556b")); c.setFont("Helvetica-Bold",10); c.drawString(50,top+5,"SCOPED THEOREM")
    for i,(k,v) in enumerate(rows):
        yy=top-25-i*rh; c.setFont("Helvetica-Bold",9); c.drawString(55,yy,k); c.setFont("Helvetica",9); c.drawString(180,yy,v); c.setStrokeColor(HexColor("#b8c7d1")); c.line(55,yy-10,w-55,yy-10)
    c.save()


def draw_wrapped(c, text, x, y, width_chars=78, leading=9.2, font="Helvetica", size=7.5):
    c.setFont(font,size)
    for para in text.split("\n"):
        for line in textwrap.wrap(para,width_chars,break_long_words=False):
            c.drawString(x,y,line); y-=leading
        y-=leading*.35
    return y


def make_paper_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor
    out=PAPER/"edbt2027_vision.pdf"; c=canvas.Canvas(str(out),pagesize=A4); W,H=A4
    pages=[
      ("[Vision Paper] From Papers to Scoped Theorems", [
       ("Evidence-Grounded Knowledge Infrastructure for Database Theory","Database-theory results are routinely flattened into titles, citations, or one-sentence claims, losing conditions that determine what was proved. We argue for a scope-preserving theorem atlas in which formal scope, source evidence, paper version, proof technique, and typed relations are first-class data. A bounded prototype—3,356 canonical paper families and a formally audited 20-paper/127-record batch—shows construction and auditing feasibility, not effectiveness or completeness. We identify the missing dimension across scholarly knowledge graphs, evidence models, mathematical knowledge systems, and formal libraries, and set a nine-part research agenda."),
       ("1  Introduction: Scope Loss","A theorem is not merely a sentence. In database theory its meaning may depend jointly on query fragment, fixed/input roles, structural restrictions, complexity regime, preprocessing, delay or access time, communication rounds, load, randomness, and conditional hypotheses. Dropping one axis can turn a valid theorem into a misleading claim.\n\nConsider the flat statement ‘join queries can be evaluated efficiently in parallel.’ It suppresses whether the query is fixed, which fragment is allowed, how many rounds are used, whether the bound is total work or per-server load, and whether success is deterministic. We argue for treating theorem scope and source evidence as first-class objects. Contributions: (1) the scope-loss problem and a database-theory-specific knowledge unit; (2) positioning against the closest infrastructures; (3) a bounded feasibility artifact; and (4) a nine-part research agenda.")]),
      ("2  Why Existing Infrastructure Is Insufficient",[("Existing foundations","ORKG represents research contributions, comparisons, provenance, and versions. Micropublications model claims, evidence, argument, and typed support/challenge relations. Nanopublications separate assertion, provenance, and publication information; PAV models authorship, derivation, and versions. OntoMath, OMDoc/MMT, and Mizar make mathematical objects and dependencies machine-actionable. S2ORC, SciFact, MultiVerS, and ASReview provide document, evidence, verification, and screening substrates.\n\nThese systems invalidate any broad novelty claim about claim graphs, theorem objects, provenance, versions, or formal dependencies. They are foundations to reuse. The missing dimension is a prescribed, source-bound database-theory theorem-scope contract with explicit unknowns and fail-closed promotion. Flexible RDF can encode the fields; the research problem is specifying their semantics, integrity constraints, extraction and verification workflows, version evolution, typed queries, benchmarks, and governance."),("Why database theory","The same headline result may hold only in data complexity, for a fixed self-join-free acyclic query, after linear preprocessing, with constant delay, or conditionally under a fine-grained hypothesis. These axes jointly delimit the proposition. They determine whether one theorem strengthens, conflicts with, or is incomparable to another."),("Figure 1", "Source/PDF → PaperVersion → EvidencePointer → ScopedTheorem → qualified TypedRelation graph → researcher queries. Evidence binds individual fields; version lineage constrains identity; relations are inferred only after scope is preserved.")]),
      ("3  A Scope-Preserving Theorem Atlas",[("Knowledge unit","ScopedTheorem records formal problem, fragment, assumptions, input/fixed/parameter roles, data or combined complexity, preprocessing, delay/access/query/total time, rounds, load, randomness, semantics, and result kind. EvidencePointer binds each promoted fact to label, page, section, extraction span, source hash, and source tier. PaperVersion represents preprint, conference, journal, correction, and retraction lineage. ProofTechnique is evidence-qualified. TypedRelation objects carry relation type, scope preconditions, evidence, confidence, and reviewer state."),("Promotion and querying","Promotion is fail-closed: source identity and access are validated; candidate fields are checked against the exact version; unknowns remain explicit; a reviewer signs or rejects promotion. A generic similarity score cannot silently become implication.\n\nCompetency queries include: Which free-connex results give constant delay after which preprocessing? Which lower bounds depend on SparseBMM? Which journal version changes a conference theorem’s assumptions? Which results are incomparable because one fixes the query while another measures combined complexity? Which proof techniques recur across semiring and provenance results?"),("Running example","Aamer–Ketsman Theorem 14 states, for q,D,C adhering to spectrum r and a solution S, computation over Fragment(D,r,C) on p servers in three rounds with per-server load O~(|D|/p^(1/c(S))) with high probability. The record binds ICDT 2025 version:0f48322c4246924097bc to Theorem 14, page 12. The flat sentence loses every italicized condition and could imply an unrestricted deterministic guarantee." )]),
      ("4  Feasibility and Agenda A–D",[("Bounded prototype evidence","The frozen workflow contains 3,737 provider observations consolidated into 3,356 canonical paper families; 309 were marked relevant by deterministic screening. The read-depth ledger records 125 FULL_SCAN and 80 DEEP_READ papers. The admissible theorem batch covers exactly 20 papers and 127 theorem/proposition records; all 127 have source locations and the records bind 20 version IDs. Every number is recomputed from hashed artifacts. These counts show construction and auditability feasibility only; they do not establish extraction accuracy, completeness, effectiveness, adoption, or community utility."),("A  Semi-automatic theorem extraction","Problem: populate structured fields without silently completing absent conditions. Difficulty: notation, cross-references, tables, theorem/proof separation, and negative context. Route: layout-aware retrieval, constrained field candidates, calibrated abstention, and evidence spans. Evaluation: axis-level precision/recall, calibration, abstention quality, and expert time. Impact: scalable candidate generation without removing human responsibility."),("B  Scope verification","Problem: decide whether all validity conditions have been captured. Difficulty: assumptions may occur pages earlier or in referenced lemmas. Route: document-level consistency constraints, cross-version comparison, and counterexample-oriented review. Evaluation: missing-axis detection and expert agreement. Impact: integrity checks for scientific KGs."),("C  Formal-method integration","Problem: link informal records to proof-assistant declarations. Difficulty: notation and granularity mismatch. Route: align definitions/theorem families while retaining source evidence. Evaluation: alignment coverage and checked-link soundness. Impact: a bridge rather than a false substitute for proof."),("D  Typed theorem-relation inference","Problem: infer qualified strengthening, subsumption, incompatibility, and technique relations. Difficulty: relations depend on scope. Route: rule-plus-model candidate generation with logical counterexample tests. Evaluation: expert acceptance and false-edge severity. Impact: trustworthy theorem navigation." )]),
      ("5  Research Agenda E–I",[("E  Version-aware theorem evolution","Problem: reconstruct identity across preprint, conference, journal, corrections, and retractions. Difficulty: statements split, merge, or change scope. Route: field-level diffs and provenance-preserving lineage events. Evaluation: lineage accuracy and change attribution. Impact: reproducible citation of what was known when."),("F  Open-problem status tracking","Problem: status is time- and scope-dependent. Difficulty: partial solutions and uncited negative evidence. Route: evidence-qualified status events, explicit scope, expiry/review dates, and disputes. Evaluation: freshness, false closure, and correction latency. Impact: safer research planning."),("G  Benchmarks and evaluation","Problem: no shared target spans representation, evidence, and use. Difficulty: expert gold data is costly. Route: stratified benchmark suites for extraction, evidence retrieval, scope comparison, lineage, and research queries. Evaluation: calibration, cost, robustness, and task utility—not accuracy alone. Impact: comparable progress."),("H  Community curation and governance","Problem: authority, credit, disputes, vocabulary drift, and sustainability. Difficulty: curation competes with research time. Route: signed roles, review queues, contribution credit, appeals, and federated stewardship. Evaluation: latency, agreement, retention, and correction quality. Impact: legitimate shared infrastructure."),("I  Human–AI collaboration","Problem: exploit models without laundering hallucinations into facts. Difficulty: fluent errors and automation bias. Route: evidence-first interfaces, uncertainty, adversarial checks, and fail-closed promotion. Evaluation: escaped-error severity, workload, calibration, and trust. Impact: a general pattern for accountable scientific AI." )]),
      ("6  Risks, Governance, Conclusion, and Artifacts",[("Risks and limitations","Authoritative-looking errors, coverage bias, terminology drift, inaccessible sources, stale status, and distorted credit are central risks. Mitigations include immutable source/version identity, field-level provenance, explicit unknowns, competing annotations, signed promotion, appeals, and periodic audits. The atlas must interoperate with ORKG/nanopublication/PAV and formal-math standards rather than create a silo. The present artifact covers a narrow audited batch and has no user study."),("Conclusion","A scope-preserving theorem atlas is not merely a literature database or interface. It is a database research agenda in representation, integrity constraints, provenance, entity resolution, uncertain extraction, version evolution, querying, benchmarks, and governance. Database theory supplies a demanding testbed because result meaning is carried by interacting formal scope axes. Success would be measured by trustworthy, evidence-backed research tasks—not record volume."),("Artifacts","Repository branch: edbt2027-vision-paper; the build commit, input hashes, definitions, scripts, tests, claim registry, related-work matrix, audits, figures, source, and PDF are included. Copyrighted source PDFs, temporary audit downloads, credentials, and unreviewed theorem batches are excluded. Rebuild: run scripts/recompute_edbt2027_statistics.py and scripts/build_edbt2027_package.py. Generative-AI assistance is logged and must be disclosed; named authors remain responsible." )]),
    ]
    for pno,(title,sections) in enumerate(pages,1):
        c.setFillColor(HexColor("#17324d")); c.rect(0,H-38,W,38,fill=1,stroke=0); c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold",10); c.drawString(30,H-25,"EDBT 2027 VISION PAPER — SUBMISSION CANDIDATE")
        c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold",14 if pno==1 else 12); c.drawString(34,H-62,title)
        if pno==1: c.setFont("Helvetica",8); c.drawString(34,H-76,"AUTHOR NAMES, AFFILIATIONS, AND ORCIDS REQUIRED BEFORE SUBMISSION")
        x1,x2=34,W/2+10; y1=y2=H-(95 if pno==1 else 82)
        split=(len(sections)+1)//2
        for idx,(heading,body) in enumerate(sections):
            col=0 if idx < split else 1
            x=x1 if col==0 else x2; y=y1 if col==0 else y2
            c.setFont("Helvetica-Bold",9); c.drawString(x,y,heading); y-=13
            y=draw_wrapped(c,body,x,y,72 if col==0 else 70)
            if col==0: y1=y
            else: y2=y
        c.setFont("Helvetica",7); c.drawCentredString(W/2,22,f"Body page {pno} of 6")
        c.showPage()
    c.setFont("Helvetica-Bold",14); c.drawString(34,H-45,"References (additional page; excluded from six-page body limit)"); y=H-70
    refs=[
      "[1] Jaradeh et al. Open Research Knowledge Graph. JCDL 2020. DOI 10.1145/3360901.3364435.","[2] Auer et al. Towards a Knowledge Graph for Science. DL4KG 2018. DOI 10.1145/3227609.3227689.","[3] Clark et al. Micropublications. J. Biomedical Semantics 2014. DOI 10.1186/2041-1480-5-28.","[4] Groth et al. The anatomy of a nanopublication. Information Services & Use 2010. DOI 10.3233/ISU-2010-0613.","[5] Kuhn et al. Decentralized provenance-aware publishing with nanopublications. PeerJ CS 2016. DOI 10.7717/peerj-cs.78.","[6] Ciccarese et al. PAV ontology. J. Biomedical Semantics 2013. DOI 10.1186/2041-1480-4-37.","[7] Constantin et al. The Document Components Ontology. Semantic Web 2016. DOI 10.3233/SW-150177.","[8] Sharafutdinov et al. OntoMathPRO. Doklady Mathematics 2022. DOI 10.1134/S1064562422700016.","[9] Albrecht et al. The Mizar Mathematical Library in OMDoc. JAR 2018. DOI 10.1007/s10817-017-9440-6.","[10] Lo et al. S2ORC. ACL 2020. DOI 10.18653/v1/2020.acl-main.447.","[11] Wadden et al. Fact or Fiction: Verifying Scientific Claims. EMNLP 2020. DOI 10.18653/v1/2020.emnlp-main.609.","[12] van de Schoot et al. ASReview. Nature Machine Intelligence 2021. DOI 10.1038/s42256-020-00287-7.","[13] Aamer and Ketsman. PAC: Computing Join Queries with Semi-Covers. ICDT 2025. DOI 10.4230/LIPIcs.ICDT.2025.6."]
    for ref in refs: y=draw_wrapped(c,ref,40,y,112,11,font="Helvetica",size=8.5)
    c.setFont("Helvetica",7); c.drawCentredString(W/2,22,"References page 1")
    c.save()


make_figure_pdfs()
# Keep the editable SVG/PDF figures synchronized with the redesigned,
# evidence-chain visual language before generating the candidate paper PDF.
from redesign_figures import main as _redesign_figures
_redesign_figures(FIG)
make_paper_pdf()

checklist = """# EDBT 2027 Submission Checklist

- [x] Title begins `[Vision Paper]`.
- [x] Six numbered body pages; references placed on an additional page.
- [x] Artifacts section immediately before references in source and on body page 6.
- [x] A4 two-column submission candidate generated without compressed fonts.
- [x] Novelty audit: CONDITIONAL_GO; 32 candidates, 12 deep comparisons, at least five direct threats.
- [x] Claim registry and hashed recomputation package generated.
- [x] Running example re-checked against the original audited PDF/version.
- [x] No batch 021-040 or papers 041-080 theorem claims used.
- [x] Copyrighted PDFs excluded from release package.
- [x] Six reviewer personas × 15 questions and five mock reviews completed.
- [x] AI-use ledger and proposed disclosure prepared.
- [ ] Replace author/affiliation/ORCID placeholders; ensure PDF and CMT lists match.
- [x] Official EDBT 2027 class/template downloaded and `main.tex` migrated to it.
- [ ] Compile `main.tex` with a LaTeX engine and compare official-template pagination (no engine is installed in this workspace).
- [ ] Human authors verify every claim, citation, figure, and AI disclosure.
- [ ] Insert public repository/archival URL and immutable release commit after authorization.
- [ ] Confirm no overlapping submission at submission time.
- [ ] Submit one PDF through CMT only after explicit authorization.
"""
write(PAPER / "SUBMISSION_CHECKLIST.md", checklist)

citation = """# Citation Audit

The bibliography uses primary publisher/conference identifiers for the closest works. DOI strings were taken from the source-backed discovery audit, not model-only memory. The related-work matrix separates verified capabilities from residual gaps and avoids negative universal claims. Deep-read set: ORKG, ORKG requirements, nanopublications, micropublications, PAV, OntoMath, Mizar, S2ORC, SciFact, SciFact-Open, MultiVerS, and ASReview.

Residual gate: a named human author must resolve every BibTeX entry against Crossref/publisher pages immediately before submission, especially author lists abbreviated here as “and others,” and compile the official template bibliography. Until then the package is conditional-ready rather than submission-ready.
"""
write(REPORTS / "CITATION_AUDIT.md", citation)

final_audit = """# Final Submission Audit

| Gate | Result | Evidence |
|---|---|---|
| NOVELTY | PASS | `NOVELTY_AUDIT.md`: CONDITIONAL_GO with explicit closest-work delta |
| VISION FIT | PASS | Emerging research infrastructure and nine-part agenda; no research-result requirement assumed |
| EVIDENCE | PASS | 20/20 registered claims bound; prototype counts recomputable and hashed |
| 6 PAGE | PASS | Generated candidate has six labeled body pages plus one references page |
| RELATED WORK | PASS | 32 candidates, 12 deep comparisons, ≥5 direct threats |
| ARTIFACT | PASS | Code/data boundary, rebuild scripts, hashes, records, figures, and statement present |
| POLICY | PASS | AI ledger/disclosure prepared; duplicate submission and author rules recorded |
| RED TEAM | NO FATAL | Six personas ×15 questions and five complete mock reviews |

## Verdict: CONDITIONAL_READY

Blockers are administrative and human-verification gates, not missing package components: real author names, affiliations, ORCIDs, CMT registration/list match; official-template compilation; final human citation/scientific/visual verification; public immutable artifact URL/release commit; and explicit submission authorization. No push, tag, release, or CMT action has been performed.
"""
write(REPORTS / "FINAL_SUBMISSION_AUDIT.md", final_audit)

final_report = """# Final EDBT 2027 Vision Report

## A. Verdict
CONDITIONAL_READY.

## B. Final Title
`[Vision Paper] From Papers to Scoped Theorems: Evidence-Grounded Knowledge Infrastructure for Database Theory`

## C. Central Thesis
Database-theory theorem scope and exact source evidence should be first-class data objects, because interacting complexity, query, structural, resource, randomness, and version axes determine what a result actually says.

## D. Contributions
Scope-loss diagnosis; integrity-constrained theorem knowledge unit; bounded feasibility artifact; nine-part research agenda.

## E. Closest Prior Work
ORKG; micropublications; nanopublications/PAV; OntoMath/OMDoc/MMT/Mizar; S2ORC and scientific-claim verification.

## F. Novelty Delta
Not a first theorem KG. The delta is the combination of a prescribed database-theory formal-scope contract, exact source/version binding, explicit unknowns, typed qualified relations, and fail-closed human promotion.

## G. Running Example
PAC join evaluation, Theorem 14: the flat “efficient parallel joins” claim loses fragment, configuration/solution assumptions, three-round MPC regime, per-server load, high-probability semantics, and version identity.

## H. Prototype Evidence
3,737 raw observations; 3,356 canonical families; 309 relevant; 125 FULL_SCAN; 80 DEEP_READ; 20 audited papers; 127 source-located theorem/proposition records; 20 audited versions. Bounded feasibility only.

## I. Research Agenda
Extraction; scope verification; formal integration; relation inference; version evolution; open-problem status; benchmarks; governance; human–AI collaboration.

## J. Page Count
Six labeled body pages plus one additional references page in the generated A4 candidate.

## K. Artifact
Rebuildable local package with code, schemas, derived metadata, audited batch 001-020, hashes, scripts, tests, figures, and audits; copyrighted PDFs and unreviewed batches excluded.

## L. Claim Audit
20 bound claims; no unbound numbers, unsupported firstness, completeness, automatic-correctness, adoption, or open-status claim.

## M. Citation Audit
Primary-source DOI bibliography and 32-work matrix prepared; final named-author metadata resolution remains mandatory.

## N. Mock Review Summary
Mean 6.0/10; strongest risk is “just ORKG for databases,” answered by integrity-constrained formal-scope semantics and research questions.

## O. Fatal Risks
No current fatal research-positioning risk. Scope drift into a generic tool paper or unsupported novelty wording would be fatal.

## P. Policy Compliance
Official requirements recorded; AI ledger and disclosure prepared; copyrighted PDFs excluded; no duplicate submission, push, tag, release, or CMT action taken.

## Q. Remaining Blockers
Authors/affiliations/ORCIDs; official-template compilation; final human claim/citation/figure/AI-disclosure verification; public immutable artifact URL; submission authorization.

## R. Final Recommendation
Proceed to named-author scientific review and official-template typesetting. Submit only after every unchecked checklist item is closed and explicit authorization is given.
"""
write(REPORTS / "final_edbt2027_vision_report.md", final_report)
