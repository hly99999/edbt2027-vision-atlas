# Running Example Audit

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
