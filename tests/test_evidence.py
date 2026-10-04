from __future__ import annotations

from dataclasses import replace

import pytest

from db_theory_atlas.evidence import (
    EvidenceType,
    authorize_complete_theorem,
    build_evidence_pointer,
    validate_evidence_membership,
    validate_evidence_pointer,
)
from db_theory_atlas.model import EvidencePointer, ReadDepth, TheoremRecord
from db_theory_atlas.reading import CoverageEntry, CoverageKind, NoteRecord, ReadingState
from claim_fixtures import theorem_claim


def note(*, source_hash: str = "a" * 64, read_depth: ReadingState = ReadingState.DEEP_READ) -> NoteRecord:
    def pointer(kind: EvidenceType, page: int, heading: str, paraphrase: str) -> EvidencePointer:
        return EvidencePointer(
            paper_id="paper:query-containment-2024", version_id="version:query-containment-v1",
            source_hash=source_hash, page=page, heading=heading, evidence_type=kind,
            paraphrase=paraphrase, verified=True,
            claim=theorem_claim() if kind is EvidenceType.THEOREM else None,
        )
    return NoteRecord(
        paper_id="paper:query-containment-2024",
        version_id="version:query-containment-v1",
        source_hash=source_hash,
        read_depth=read_depth,
        sections=("Introduction", "Formal Scope", "Theorems", "Limitations", "Conclusion"),
        pages=(1, 4, 7, 9),
        headings=("Introduction", "Formal Scope", "Theorem 1", "Limitations", "Conclusion"),
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
        extractor_status="complete",
        reviewer_status="reviewed",
        coverage=(
            CoverageEntry(CoverageKind.INTRODUCTION, 1, "Introduction"),
            CoverageEntry(CoverageKind.CONCLUSION, 9, "Conclusion"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 1, "Introduction"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 4, "Formal Scope"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 7, "Theorem 1"),
            CoverageEntry(CoverageKind.PROBLEM_DEFINITION, 1, "Introduction"),
            CoverageEntry(CoverageKind.FORMAL_SCOPE_ASSUMPTIONS, 4, "Formal Scope"),
            CoverageEntry(CoverageKind.THEOREM_RESULTS, 7, "Theorem 1"),
            CoverageEntry(CoverageKind.LIMITATIONS_FUTURE_WORK, 9, "Limitations"),
        ),
        evidence=(
            pointer(EvidenceType.METADATA, 1, "Introduction", "For the stated paper, the metadata identifies the source."),
            pointer(EvidenceType.ABSTRACT, 1, "Introduction", "For the stated fragment, the abstract summarizes the result."),
            pointer(EvidenceType.PROBLEM_DEFINITION, 1, "Introduction", "For the stated fragment, the paper defines the problem."),
            pointer(EvidenceType.PROBLEM_DEFINITION, 4, "Formal Scope", "Under the listed assumptions, the formal scope is explicit."),
            pointer(EvidenceType.THEOREM, 7, "Theorem 1", "For the stated query fragment, the theorem gives the claimed lower bound under its assumptions."),
            pointer(EvidenceType.LIMITATION, 9, "Limitations", "Within the stated scope, the paper records a limitation."),
        ),
    )


def test_evidence_pointer_is_bound_to_canonical_note_and_inspected_location() -> None:
    record = note()
    pointer = build_evidence_pointer(
        record,
        evidence_type=EvidenceType.THEOREM,
        page=7,
        heading="Theorem 1",
        paraphrase="For the stated query fragment, the theorem gives the claimed lower bound under its assumptions.",
    )

    assert pointer.paper_id == record.paper_id
    assert validate_evidence_pointer(pointer, record) is pointer
    authorization = authorize_complete_theorem(record, pointer)
    theorem = TheoremRecord(
        theorem_id="theorem:containment-bound", paper_id=record.paper_id, version_id=record.version_id,
        paraphrase="Under the stated assumptions, containment has the lower bound.", complete=True,
        read_depth=ReadDepth.DEEP_READ, evidence_pointers=(pointer,), authorization=authorization,
    )

    assert theorem.authorization == authorization


def test_pointer_rejects_hash_mismatch_and_uninspected_location() -> None:
    record = note()
    pointer = build_evidence_pointer(
        record,
        evidence_type=EvidenceType.ABSTRACT,
        page=1,
        heading="Introduction",
        paraphrase="The abstract describes the stated query fragment and its scope.",
    )

    with pytest.raises(ValueError, match="source hash"):
        validate_evidence_pointer(pointer, note(source_hash="b" * 64))


def test_evidence_membership_rejects_same_location_pointer_not_in_note() -> None:
    record = note()
    member = record.evidence[4]
    altered = replace(member, paraphrase="For the stated fragment, a different theorem claim is asserted.")

    assert validate_evidence_membership(member, record) is member
    with pytest.raises(ValueError, match="exact member"):
        validate_evidence_membership(altered, record)
    with pytest.raises(ValueError, match="inspected"):
        build_evidence_pointer(
            record,
            evidence_type=EvidenceType.ABSTRACT,
            page=3,
            heading="Introduction",
            paraphrase="The abstract describes the stated query fragment and its scope.",
        )


def test_pointer_location_must_match_an_exact_inspected_pair() -> None:
    record = note()

    with pytest.raises(ValueError, match="inspected location"):
        build_evidence_pointer(
            record,
            evidence_type=EvidenceType.THEOREM,
            page=1,
            heading="Theorem 1",
            paraphrase="For the stated fragment, the theorem gives the lower bound.",
        )


@pytest.mark.parametrize(
    "paraphrase",
    [
        "TODO",
        "[insert summary]",
        "This theorem certainly proves the definitive result.",
        "The authors prove that this is a long copied block from the paper and this is a long copied block from the paper and this is a long copied block from the paper and this is a long copied block from the paper.",
    ],
)
def test_paraphrase_guard_rejects_placeholders_copied_blocks_and_unsupported_certainty(paraphrase: str) -> None:
    with pytest.raises(ValueError, match="paraphrase"):
        build_evidence_pointer(note(), evidence_type=EvidenceType.THEOREM, page=7, heading="Theorem 1", paraphrase=paraphrase)


def test_shallow_note_cannot_authorize_complete_theorem_and_unicode_math_is_accepted() -> None:
    pointer = build_evidence_pointer(
        note(read_depth=ReadingState.FULL_SCAN),
        evidence_type=EvidenceType.THEOREM,
        page=7,
        heading="Theorem 1",
        paraphrase="For α/β queries in the stated fragment, the theorem establishes an Ω(n²) bound under the listed assumptions.",
    )
    with pytest.raises(ValueError, match="DEEP_READ"):
        authorize_complete_theorem(note(read_depth=ReadingState.FULL_SCAN), pointer)


def test_raw_arbitrary_pointer_cannot_authorize_complete_theorem_record() -> None:
    arbitrary = EvidencePointer(
        paper_id="paper:query-containment-2024", version_id="version:query-containment-v1",
        page=7, heading="Theorem 1", evidence_type=EvidenceType.THEOREM,
        paraphrase="For the stated fragment, the theorem gives a bound.", source_hash="a" * 64, verified=True,
        claim=theorem_claim(),
    )

    with pytest.raises(ValueError, match="authorization"):
        TheoremRecord(
            theorem_id="theorem:containment-bound", paper_id=arbitrary.paper_id, version_id=arbitrary.version_id,
            paraphrase="Under the stated assumptions, containment has the lower bound.", complete=True,
            read_depth=ReadDepth.DEEP_READ, evidence_pointers=(arbitrary,),
        )


def test_excessive_quoted_copy_is_rejected_but_short_terms_and_math_are_allowed() -> None:
    with pytest.raises(ValueError, match="quoted|verbatim"):
        build_evidence_pointer(
            note(), evidence_type=EvidenceType.THEOREM, page=7, heading="Theorem 1",
            paraphrase='Under the stated assumptions, the paper says "for every conjunctive query in the fragment, containment is decidable exactly when the canonical database homomorphism exists between the two query bodies".',
        )

    short = build_evidence_pointer(
        note(), evidence_type=EvidenceType.THEOREM, page=7, heading="Theorem 1",
        paraphrase='For the stated α/β fragment, the “core” has size Ω(n²) under the assumptions.',
    )
    assert short.heading == "Theorem 1"


def test_unverified_theorem_evidence_cannot_authorize_complete_theorem() -> None:
    record = note()
    verified_theorem = next(item for item in record.evidence if item.evidence_type is EvidenceType.THEOREM)
    unverified_theorem = replace(
        verified_theorem,
        paraphrase="For the stated fragment, an unreviewed extraction reports the theorem result.",
        verified=False,
    )
    mixed = replace(record, evidence=record.evidence + (unverified_theorem,))

    with pytest.raises(ValueError, match="verified"):
        authorize_complete_theorem(mixed, unverified_theorem)


def test_complete_theorem_record_rejects_any_unverified_attached_evidence() -> None:
    record = note()
    theorem_pointer = next(item for item in record.evidence if item.evidence_type is EvidenceType.THEOREM)
    authorization = authorize_complete_theorem(record, theorem_pointer)
    unverified_context = replace(
        theorem_pointer,
        evidence_type=EvidenceType.PROBLEM_DEFINITION,
        paraphrase="Under the stated assumptions, an unreviewed extraction describes the problem scope.",
        verified=False,
    )

    with pytest.raises(ValueError, match="verified"):
        TheoremRecord(
            theorem_id="theorem:containment-bound",
            paper_id=record.paper_id,
            version_id=record.version_id,
            paraphrase="Under the stated assumptions, containment has the lower bound.",
            complete=True,
            read_depth=ReadDepth.DEEP_READ,
            evidence_pointers=(theorem_pointer, unverified_context),
            authorization=authorization,
        )


def test_unique_unquoted_long_prose_is_rejected_as_nonconcise() -> None:
    copied = (
        "Under the stated scope, the paper defines queries and compares finite structures. It covers syntax, "
        "semantics, maps, forms, guards, chase steps, obstructions, trees, width, games, preservation, locality, "
        "saturation, products, reductions, examples, counterexamples, cases, implementations, evaluations, "
        "benchmarks, optimizations, models, context, consequences, variants, and extensions. The authors then "
        "describe how each component affects the classification, explain why the constructions apply to the chosen "
        "language, outline the proof sequence, distinguish tractable cases from hard cases, summarize experiments, "
        "discuss practical use, note unresolved questions, and propose future directions for database theory."
    )

    with pytest.raises(ValueError, match="concise|words|characters"):
        build_evidence_pointer(
            note(),
            evidence_type=EvidenceType.PROBLEM_DEFINITION,
            page=1,
            heading="Introduction",
            paraphrase=copied,
        )
