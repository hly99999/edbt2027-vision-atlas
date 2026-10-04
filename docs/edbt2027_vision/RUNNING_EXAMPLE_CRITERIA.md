# Running Example Criteria

## Objective

Select one real, formally audited theorem record that makes scope loss visible within the six-page paper budget.

## Eligibility gate

The example must come exclusively from the reviewed 20-paper batch represented by:

- `data/theorems/fragments/batch-001-020.jsonl`;
- `data/theorems/fragments/claim-inventory-001-020.jsonl`;
- `data/theorems/fragments/coverage-001-020.jsonl`.

The selected paper must have `COMPLETE_THEOREM_EXTRACTION`, and the theorem/proposition record must have an exact source location and matching source identity. Batch 21–40, papers 41–80, handwritten examples, synthetic theorems, and unverified paraphrases are ineligible.

## Preferred content

Prefer a result whose correct interpretation depends on at least three of the following, ideally four:

- query class or fragment;
- data versus combined complexity, or another explicit complexity regime;
- fixed versus input parameter roles;
- structural restrictions such as acyclicity, width, self-join freedom, arity, or guardedness;
- preprocessing versus query/delay/access time;
- deterministic versus randomized execution;
- finite versus unrestricted domain or semantics;
- algorithmic model or resource assumption.

## Required presentation

The paper should show a four-step chain:

1. **Original result:** a concise, source-faithful rendering with citation and exact evidence pointer.
2. **Flattened statement:** a plausible secondary summary that omits material scope.
3. **Scope-lost statement:** the misleading conclusion produced by further flattening, such as an unconditional tractability claim.
4. **Scoped record:** the structured fields that restore the theorem's meaning and expose what is known, not stated, or not applicable.

## Selection rubric

Score eligible candidates on:

- severity of meaning change after scope removal;
- number and clarity of material scope axes;
- compactness within one table or figure;
- accessibility to a broad EDBT audience;
- exactness and stability of the source evidence;
- absence of interpretive controversy;
- ability to motivate the general infrastructure rather than only one subfield.

The winning example must be rechecked against the source by a human author before use. Selection is a next-phase task; no example is designated by this pivot.
