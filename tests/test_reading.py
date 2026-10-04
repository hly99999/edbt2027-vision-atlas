from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from db_theory_atlas.reading import (
    CoverageEntry,
    CoverageKind,
    NoteRecord,
    ReadingEvent,
    ReadingHistory,
    ReadingState,
    coverage_certificate,
    parse_note_frontmatter,
    promote_read_depth,
    validate_note,
    validate_reading_history,
)
from db_theory_atlas.evidence import EvidenceType
from db_theory_atlas.model import EvidencePointer
from claim_fixtures import default_result, default_scope, default_technique_signature, open_problem_claim, theorem_claim
from db_theory_atlas.theorems import claim_for_theorem


PAPER_ID = "paper:query-containment-2024"
VERSION_ID = "version:query-containment-v1"
SOURCE_HASH = "a" * 64


def pointer(
    kind: EvidenceType,
    page: int,
    heading: str,
    paraphrase: str | None = None,
    *,
    verified: bool = True,
) -> EvidencePointer:
    return EvidencePointer(
        paper_id=PAPER_ID,
        version_id=VERSION_ID,
        source_hash=SOURCE_HASH,
        page=page,
        heading=heading,
        evidence_type=kind,
        paraphrase=paraphrase or f"For the stated fragment, the paper records the scoped {kind.value.lower()} claim.",
        verified=verified,
        claim=(
            theorem_claim()
            if kind is EvidenceType.THEOREM
            else open_problem_claim()
            if kind in {EvidenceType.OPEN_PROBLEM, EvidenceType.FUTURE_WORK}
            else None
        ),
    )


def coverage() -> tuple[CoverageEntry, ...]:
    return (
        CoverageEntry(CoverageKind.INTRODUCTION, 1, "Introduction"),
        CoverageEntry(CoverageKind.CONCLUSION, 9, "Conclusion"),
        CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 1, "Introduction"),
        CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 4, "Formal Scope"),
        CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 7, "Theorem 1"),
        CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 9, "Limitations"),
        CoverageEntry(CoverageKind.PROBLEM_DEFINITION, 1, "Introduction"),
        CoverageEntry(CoverageKind.FORMAL_SCOPE_ASSUMPTIONS, 4, "Formal Scope"),
        CoverageEntry(CoverageKind.THEOREM_RESULTS, 7, "Theorem 1"),
        CoverageEntry(CoverageKind.LIMITATIONS_FUTURE_WORK, 9, "Limitations"),
    )


def note(state: ReadingState = ReadingState.DEEP_READ, *, evidence: tuple[EvidencePointer, ...] | None = None,
         note_coverage: tuple[CoverageEntry, ...] | None = None) -> NoteRecord:
    body_evidence = evidence or (
        pointer(EvidenceType.METADATA, 1, "Introduction"),
        pointer(EvidenceType.ABSTRACT, 1, "Introduction"),
        pointer(EvidenceType.PROBLEM_DEFINITION, 1, "Introduction"),
        pointer(EvidenceType.PROBLEM_DEFINITION, 4, "Formal Scope", "Under the listed assumptions, the formal scope is the stated query fragment."),
        pointer(EvidenceType.THEOREM, 7, "Theorem 1"),
        pointer(EvidenceType.LIMITATION, 9, "Limitations"),
    )
    return NoteRecord(
        paper_id=PAPER_ID,
        version_id=VERSION_ID,
        source_hash=SOURCE_HASH,
        read_depth=state,
        sections=("Introduction", "Formal Scope", "Theorems", "Limitations", "Conclusion"),
        pages=(1, 4, 7, 9),
        headings=("Introduction", "Formal Scope", "Theorem 1", "Limitations", "Conclusion"),
        created_at="2026-08-17T00:00:00Z",
        updated_at="2026-08-17T00:00:00Z",
        extractor_status="complete",
        reviewer_status="reviewed",
        coverage=note_coverage or coverage(),
        evidence=body_evidence,
    )


def event(state: ReadingState, *evidence_type: EvidenceType, locations: tuple[tuple[int, str], ...] = ()) -> ReadingEvent:
    pointers = tuple(pointer(kind, *(locations[index] if locations else (1, "Introduction"))) for index, kind in enumerate(evidence_type))
    return ReadingEvent(state=state, evidence=pointers)


def metadata_history() -> ReadingHistory:
    return ReadingHistory(
        paper_id=PAPER_ID,
        version_id=VERSION_ID,
        source_hash=SOURCE_HASH,
        full_text_available=True,
        events=(event(ReadingState.METADATA, EvidenceType.METADATA),),
    )


def test_promote_sequentially_with_required_evidence() -> None:
    history = metadata_history()
    abstract = promote_read_depth(history, ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    intro = promote_read_depth(
        abstract,
        ReadingState.INTRO_CONCLUSION,
        event(
            ReadingState.INTRO_CONCLUSION,
            EvidenceType.PROBLEM_DEFINITION,
            EvidenceType.LIMITATION,
            locations=((1, "Introduction"), (9, "Conclusion")),
        ).evidence,
    )

    assert intro.current_state is ReadingState.INTRO_CONCLUSION
    assert validate_reading_history(intro) is intro


def test_rejects_skipped_promotion_and_downgrade() -> None:
    history = metadata_history()

    with pytest.raises(ValueError, match="sequential"):
        promote_read_depth(history, ReadingState.DEEP_READ, ())
    with pytest.raises(ValueError, match="downgrade"):
        promote_read_depth(history, ReadingState.METADATA, ())


def test_allows_explicit_intermediate_events_for_multi_step_promotion() -> None:
    promoted = promote_read_depth(
        metadata_history(),
        ReadingState.INTRO_CONCLUSION,
        (
            event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT),
            event(
                ReadingState.INTRO_CONCLUSION,
                EvidenceType.PROBLEM_DEFINITION,
                EvidenceType.LIMITATION,
                locations=((1, "Introduction"), (9, "Conclusion")),
            ),
        ),
    )

    assert [item.state for item in promoted.events] == [
        ReadingState.METADATA,
        ReadingState.ABSTRACT,
        ReadingState.INTRO_CONCLUSION,
    ]


def test_intro_conclusion_allows_a_declared_unavailable_location() -> None:
    history = promote_read_depth(metadata_history(), ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    introduction = event(ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION).evidence

    promoted = promote_read_depth(
        history,
        ReadingState.INTRO_CONCLUSION,
        (ReadingEvent(ReadingState.INTRO_CONCLUSION, introduction, unavailable_locations=("Conclusion",)),),
    )

    assert promoted.current_state is ReadingState.INTRO_CONCLUSION


def test_metadata_only_or_unavailable_full_text_cannot_be_promoted() -> None:
    unavailable = ReadingHistory(
        paper_id=PAPER_ID,
        version_id=VERSION_ID,
        source_hash=SOURCE_HASH,
        full_text_available=False,
        events=(event(ReadingState.METADATA, EvidenceType.METADATA),),
    )

    with pytest.raises(ValueError, match="full text"):
        promote_read_depth(unavailable, ReadingState.ABSTRACT, ())


def test_full_scan_and_deep_read_require_coverage() -> None:
    history = promote_read_depth(metadata_history(), ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    history = promote_read_depth(history, ReadingState.INTRO_CONCLUSION, event(
        ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION, EvidenceType.LIMITATION,
        locations=((1, "Introduction"), (9, "Conclusion")),
    ).evidence)

    with pytest.raises(ValueError, match="NoteRecord or CoverageCertificate"):
        promote_read_depth(history, ReadingState.FULL_SCAN, event(ReadingState.FULL_SCAN, EvidenceType.METADATA).evidence)

    scanned = promote_read_depth(history, ReadingState.FULL_SCAN, note(ReadingState.FULL_SCAN))
    with pytest.raises(ValueError, match="NoteRecord or CoverageCertificate"):
        promote_read_depth(scanned, ReadingState.DEEP_READ, event(scanned.current_state, EvidenceType.THEOREM).evidence)


def test_full_scan_rejects_repeated_same_heading_and_requires_validated_note() -> None:
    history = promote_read_depth(metadata_history(), ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    history = promote_read_depth(history, ReadingState.INTRO_CONCLUSION, event(
        ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION, EvidenceType.LIMITATION,
        locations=((1, "Introduction"), (9, "Conclusion")),
    ).evidence)
    same_heading = tuple(
        CoverageEntry(CoverageKind.FULL_SCAN_SECTION, page, "Introduction") for page in (1, 4, 7)
    ) + (
        CoverageEntry(CoverageKind.INTRODUCTION, 1, "Introduction"),
        CoverageEntry(CoverageKind.CONCLUSION, 9, "Conclusion"),
    )
    same_heading_evidence = (
        pointer(EvidenceType.METADATA, 1, "Introduction"),
        pointer(EvidenceType.ABSTRACT, 1, "Introduction"),
        pointer(EvidenceType.PROBLEM_DEFINITION, 4, "Introduction"),
        pointer(EvidenceType.THEOREM, 7, "Introduction"),
        pointer(EvidenceType.LIMITATION, 9, "Conclusion"),
    )

    with pytest.raises(ValueError, match="distinct.*headings"):
        promote_read_depth(history, ReadingState.FULL_SCAN, note(
            ReadingState.FULL_SCAN, evidence=same_heading_evidence, note_coverage=same_heading
        ))


def test_under_covered_self_declared_deep_read_note_is_rejected() -> None:
    missing_scope = tuple(item for item in coverage() if item.kind is not CoverageKind.FORMAL_SCOPE_ASSUMPTIONS)

    with pytest.raises(ValueError, match="formal scope"):
        validate_note(note(note_coverage=missing_scope))


def test_history_deep_promotion_binds_certificate_and_evidence_hash() -> None:
    history = metadata_history()
    history = promote_read_depth(history, ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    history = promote_read_depth(history, ReadingState.INTRO_CONCLUSION, event(
        ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION, EvidenceType.LIMITATION,
        locations=((1, "Introduction"), (9, "Conclusion")),
    ).evidence)
    history = promote_read_depth(history, ReadingState.FULL_SCAN, note(ReadingState.FULL_SCAN))
    promoted = promote_read_depth(history, ReadingState.DEEP_READ, note())
    changed_note = note(evidence=note().evidence[:-1] + (
        pointer(EvidenceType.LIMITATION, 9, "Limitations", "Within the stated scope, future work excludes a different boundary case."),
    ))
    changed = promote_read_depth(history, ReadingState.DEEP_READ, changed_note)

    assert promoted.events[-1].certificate is not None
    assert promoted.scientific_hash != changed.scientific_hash


def test_raw_arbitrary_pointers_cannot_promote_full_scan() -> None:
    history = metadata_history()
    history = promote_read_depth(history, ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    history = promote_read_depth(history, ReadingState.INTRO_CONCLUSION, event(
        ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION, EvidenceType.LIMITATION,
        locations=((1, "Introduction"), (9, "Conclusion")),
    ).evidence)

    with pytest.raises(ValueError, match="NoteRecord or CoverageCertificate"):
        promote_read_depth(history, ReadingState.FULL_SCAN, (
            pointer(EvidenceType.METADATA, 1, "Introduction"),
            pointer(EvidenceType.THEOREM, 7, "Theorem 1"),
            pointer(EvidenceType.LIMITATION, 9, "Limitations"),
        ))


def test_frontmatter_parser_is_deterministic_and_validates_required_coverage() -> None:
    text = """---
paper_id: paper:query-containment-2024
version_id: version:query-containment-v1
source_hash: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
read_depth: DEEP_READ
sections: Introduction | Theorems | Limitations | Conclusion
pages: 1, 7, 9
headings: Introduction | Theorem 1 | Limitations | Conclusion
created_at: 2026-08-17T00:00:00Z
updated_at: 2026-08-17T00:00:00Z
extractor_status: complete
reviewer_status: reviewed
---
{"coverage":"INTRODUCTION","page":1,"heading":"Introduction"}
{"coverage":"CONCLUSION","page":9,"heading":"Conclusion"}
{"coverage":"FULL_SCAN_SECTION","page":1,"heading":"Introduction"}
{"coverage":"FULL_SCAN_SECTION","page":7,"heading":"Theorem 1"}
{"coverage":"FULL_SCAN_SECTION","page":9,"heading":"Limitations"}
{"coverage":"PROBLEM_DEFINITION","page":1,"heading":"Introduction"}
{"coverage":"FORMAL_SCOPE_ASSUMPTIONS","page":7,"heading":"Theorem 1"}
{"coverage":"THEOREM_RESULTS","page":7,"heading":"Theorem 1"}
{"coverage":"LIMITATIONS_FUTURE_WORK","page":9,"heading":"Limitations"}
{"evidence_type":"METADATA","page":1,"heading":"Introduction","paraphrase":"For the stated paper, the metadata identifies the source.","verified":true}
{"evidence_type":"ABSTRACT","page":1,"heading":"Introduction","paraphrase":"For the stated fragment, the abstract summarizes the result.","verified":true}
{"evidence_type":"PROBLEM_DEFINITION","page":1,"heading":"Introduction","paraphrase":"For the stated fragment, the paper defines the problem.","verified":true}
{"evidence_type":"PROBLEM_DEFINITION","page":7,"heading":"Theorem 1","paraphrase":"Under the listed assumptions, the formal scope is explicit.","verified":true}
{"evidence_type":"THEOREM","page":7,"heading":"Theorem 1","paraphrase":"For the stated fragment, the theorem gives the result.","verified":true,"claim":{"claim_type":"THEOREM","scope":{"input":"finite relational database","output":"query answers","query_language":"conjunctive queries","semantics":"SET","constraints":["relational instances","bounded arity"],"parameters":[{"name":"query","role":"FIXED","dimension":"QUERY"},{"name":"database","role":"INPUT","dimension":"DATA"}]},"results":[{"complexity_class":"PTIME","direction":"UPPER_BOUND","measure":"DATA_COMPLEXITY","question_type":"COMPLEXITY_BOUND"}],"assumptions":["finite relational structures"],"proof_technique":{"primary":"HOMOMORPHISM","secondary":["CANONICAL_DATABASE"],"technical_obstacle":"Preserving the stated bounded-arity restriction during the homomorphism construction.","restriction_preservation_trick":"Use the canonical database only within the stated fragment."}}}
{"evidence_type":"LIMITATION","page":9,"heading":"Limitations","paraphrase":"Within the stated scope, the paper records a limitation.","verified":true}
"""
    note = parse_note_frontmatter(text)

    assert note.read_depth is ReadingState.DEEP_READ
    assert validate_note(note) is note
    assert note.scientific_hash == note.with_operational_dates(
        datetime(2027, 1, 1, tzinfo=timezone.utc), datetime(2027, 1, 2, tzinfo=timezone.utc)
    ).scientific_hash


def test_note_hash_binds_scientific_body_evidence() -> None:
    original = note()
    changed = note(evidence=original.evidence[:-1] + (
        pointer(EvidenceType.LIMITATION, 9, "Limitations", "Within the stated scope, the limitation changes materially."),
    ))

    assert original.scientific_hash != changed.scientific_hash


def test_note_and_certificate_hashes_bind_structured_claim_payload() -> None:
    original = note()
    changed_scope = replace(default_scope(), constraints=("relational instances",))
    changed_theorem = replace(
        original.evidence[4],
        claim=claim_for_theorem(
            changed_scope,
            (default_result(),),
            ("finite relational structures",),
            default_technique_signature(),
        ),
    )
    changed = replace(original, evidence=original.evidence[:4] + (changed_theorem,) + original.evidence[5:])

    assert original.scientific_hash != changed.scientific_hash
    assert coverage_certificate(original).note_hash != coverage_certificate(changed).note_hash


@pytest.mark.parametrize("evidence_index", [2, 3, 4, 5])
def test_unverified_required_evidence_cannot_satisfy_deep_read_coverage(evidence_index: int) -> None:
    baseline = note()
    body = list(baseline.evidence)
    body[evidence_index] = replace(body[evidence_index], verified=False)

    with pytest.raises(ValueError, match="verified"):
        note(evidence=tuple(body))


def test_unverified_section_evidence_cannot_satisfy_full_scan_coverage() -> None:
    baseline = note(ReadingState.FULL_SCAN)
    body = list(baseline.evidence)
    body[3] = replace(body[3], verified=False)

    with pytest.raises(ValueError, match="verified"):
        note(ReadingState.FULL_SCAN, evidence=tuple(body))


def test_mixed_note_retains_unverified_entry_but_certificate_and_promotion_use_verified_evidence() -> None:
    unverified = pointer(
        EvidenceType.OPEN_PROBLEM,
        9,
        "Limitations",
        "Within the stated scope, an additional boundary case may remain open.",
        verified=False,
    )
    mixed = note(evidence=note().evidence + (unverified,))
    certificate = coverage_certificate(mixed)
    history = metadata_history()
    history = promote_read_depth(history, ReadingState.ABSTRACT, event(ReadingState.ABSTRACT, EvidenceType.ABSTRACT).evidence)
    history = promote_read_depth(history, ReadingState.INTRO_CONCLUSION, event(
        ReadingState.INTRO_CONCLUSION, EvidenceType.PROBLEM_DEFINITION, EvidenceType.LIMITATION,
        locations=((1, "Introduction"), (9, "Conclusion")),
    ).evidence)
    history = promote_read_depth(history, ReadingState.FULL_SCAN, note(ReadingState.FULL_SCAN))
    promoted = promote_read_depth(history, ReadingState.DEEP_READ, mixed)

    assert unverified in mixed.evidence
    assert unverified not in certificate.evidence
    assert all(item.verified for item in promoted.events[-1].evidence)
