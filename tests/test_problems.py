from dataclasses import fields, replace
from datetime import date

import pytest

from db_theory_atlas.evidence import authorize_complete_theorem
from db_theory_atlas.model import EvidencePointer, EvidenceType, OpenStatus
from db_theory_atlas.problems import (
    FollowupQuery,
    FollowupSearchRecord,
    OpenProblemExplicitness,
    OpenProblemExtraction,
    ResolutionClaim,
    ReviewerConclusion,
    SearchCandidate,
    SearchCandidateDisposition,
    SearchConfidence,
    SearchManifestEntry,
    SearchQueryCategory,
    SearchSource,
    OpenStatusEvidence,
    claim_for_open_problem,
    problem_fingerprint,
    search_manifest_hash,
    validate_open_problem,
    validate_resolution,
)
from db_theory_atlas.sources import SourceKind, SourceObservation, canonical_paper_id, verify_metadata
from db_theory_atlas.techniques import ProofTechnique, ProofTechniqueProfile, ProofTechniqueSignature
from db_theory_atlas.theorems import (
    ComplexityMeasure,
    ParameterDimension,
    ParameterSpec,
    ParameterRole,
    QueryProblemScope,
    QuestionType,
    ResultDirection,
    TheoremExtraction,
    TheoremResult,
    validate_theorem,
)
from db_theory_atlas.versions import (
    LineageEvidenceKind,
    VersionKind,
    VersionLineage,
    VersionObservation,
    VersionRelation,
    resolve_version_family,
)
from test_theorems import deep_note, pointer, result, scope


def metadata(title: str, year: int, *, source: SourceKind = SourceKind.PUBLISHER):
    slug = title.lower().replace(" ", "-")
    observation = SourceObservation(
        source=source,
        observed_title=title,
        authors=("Ada Author", "Bert Author"),
        year=year,
        observed_at=date(2026, 8, 18),
        evidence_url=f"https://evidence.example/{slug}/{source.value.lower()}",
        venue="ICDT",
        doi=f"10.1000/{slug}",
        official_url=f"https://publisher.example/{slug}" if source is SourceKind.PUBLISHER else None,
    )
    return verify_metadata((observation,))


SOURCE_METADATA = metadata("Original Scope Result", 2025)
RESOLUTION_METADATA = metadata("Resolution Scope Result", 2026)
SOURCE_PAPER_ID = canonical_paper_id(SOURCE_METADATA)
RESOLUTION_PAPER_ID = canonical_paper_id(RESOLUTION_METADATA)
SOURCE_VERSION_ID = "version:original-v1"
RESOLUTION_VERSION_ID = "version:resolution-v1"
SOURCE_HASH = "c" * 64
RESOLUTION_HASH = "d" * 64


def general_scope() -> QueryProblemScope:
    return scope(constraints=("relational instances",))


def problem_note(*, future_restricted: QueryProblemScope | None = None,
                 future_remaining: QueryProblemScope | None = None,
                 paper_id: str = SOURCE_PAPER_ID,
                 version_id: str = SOURCE_VERSION_ID,
                 source_hash: str = SOURCE_HASH):
    restricted = future_restricted or scope()
    remaining = future_remaining or general_scope()
    note = deep_note(
        theorem_scope=restricted,
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
    )
    explicit = pointer(
        EvidenceType.OPEN_PROBLEM,
        9,
        "Limitations",
        "Within the stated relational scope, the paper explicitly asks whether the upper bound extends beyond bounded arity.",
        claim=claim_for_open_problem(remaining, result()),
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
    )
    future = pointer(
        EvidenceType.FUTURE_WORK,
        9,
        "Limitations",
        "Within the stated scope, the bounded-arity theorem leaves the general relational case as explicit future work.",
        claim=claim_for_open_problem(
            remaining,
            result(),
            restricted_scope=restricted,
            remaining_scope=remaining,
        ),
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
    )
    return replace(note, evidence=note.evidence + (explicit, future))


def explicit_extraction(*, status: OpenStatus = OpenStatus.LIKELY_OPEN,
                        followup_search: FollowupSearchRecord | None = None,
                        problem_scope: QueryProblemScope | None = None,
                        requested_result: TheoremResult | None = None) -> OpenProblemExtraction:
    note = problem_note()
    return OpenProblemExtraction(
        problem_id="problem:unrestricted-arity",
        paraphrase="For conjunctive-query evaluation under set semantics, does the PTIME data-complexity upper bound extend beyond bounded arity?",
        scope=problem_scope or general_scope(),
        requested_result=requested_result or result(),
        explicitness=OpenProblemExplicitness.EXPLICIT,
        evidence=note.evidence[-2],
        status=status,
        followup_search=followup_search,
    )


def complete_search(*, problem_id: str = "problem:unrestricted-arity", fingerprint: str | None = None,
                    confidence: SearchConfidence = SearchConfidence.HIGH,
                    reviewer_verified: bool = True,
                    reviewer_conclusion: ReviewerConclusion = ReviewerConclusion.NO_RESOLUTION_AFTER_DESCENDANT_AUDIT,
                    reviewer_rationale: str = "Reviewer checked descendants, citations, later venues, authors, and exact-scope matches; no resolving theorem survived verification.",
                    queries: tuple[FollowupQuery, ...] | None = None,
                    sources: tuple[SearchSource, ...] = (SearchSource.PUBLISHER, SearchSource.DBLP, SearchSource.OPENALEX),
                    candidates: tuple[SearchCandidate, ...] | None = None,
                    status_evidence: tuple[OpenStatusEvidence, ...] | None = None) -> FollowupSearchRecord:
    query_records = queries or tuple(
        FollowupQuery(category, f"unrestricted arity query for {category.value.lower()}")
        for category in SearchQueryCategory
    )
    candidate_records = candidates
    evidence_records = status_evidence
    if candidate_records is None or evidence_records is None:
        later_note = problem_note(
            paper_id=RESOLUTION_PAPER_ID,
            version_id=RESOLUTION_VERSION_ID,
            source_hash=RESOLUTION_HASH,
        )
        candidate_records = candidate_records if candidate_records is not None else (
            SearchCandidate(
                RESOLUTION_PAPER_ID,
                SearchCandidateDisposition.OPEN_STATUS_CONFIRMED,
                "The later paper explicitly restates the exact scoped problem as open after checking its theorem section.",
            ),
        )
        evidence_records = evidence_records if evidence_records is not None else (
            OpenStatusEvidence(later_note, later_note.evidence[-2], RESOLUTION_METADATA),
        )
    manifests = []
    for index, query in enumerate(query_records):
        source = sources[index % len(sources)]
        returned = tuple(item.candidate_id for item in candidate_records)
        checked = returned
        manifests.append(SearchManifestEntry(
            query.category,
            query.text,
            source,
            returned,
            checked,
            search_manifest_hash(query.category, query.text, source, returned, checked),
        ))
    for source in sources:
        if source not in {item.source for item in manifests}:
            query = query_records[0]
            returned = tuple(item.candidate_id for item in candidate_records)
            checked = returned
            manifests.append(SearchManifestEntry(
                query.category,
                query.text,
                source,
                returned,
                checked,
                search_manifest_hash(query.category, query.text, source, returned, checked),
            ))
    return FollowupSearchRecord(
        problem_id=problem_id,
        query_fingerprint=fingerprint or problem_fingerprint(problem_id, general_scope(), result()),
        queries=query_records,
        sources=sources,
        audit_date="2026-08-18",
        through_year=2026,
        result_candidates=candidate_records,
        manifests=tuple(manifests),
        source_metadata=SOURCE_METADATA,
        open_status_evidence=evidence_records,
        completed=True,
        reviewer_verified=reviewer_verified,
        reviewer_conclusion=reviewer_conclusion,
        reviewer_rationale=reviewer_rationale,
        confidence=confidence,
    )


def test_explicit_problem_is_bound_to_exact_member_scope_and_requested_result() -> None:
    note = problem_note()
    problem = validate_open_problem(explicit_extraction(), note)

    assert problem.scope == general_scope()
    assert problem.requested_result == result()
    assert problem.problem_fingerprint == problem_fingerprint(problem.problem_id, problem.scope, problem.requested_result)


def test_same_location_nonmember_pointer_cannot_validate_open_problem() -> None:
    note = problem_note()
    altered_pointers = (
        replace(note.evidence[-2], paraphrase="Within the stated scope, an altered problem paraphrase is supplied."),
        replace(note.evidence[-2], claim=claim_for_open_problem(scope(), result())),
    )

    for altered in altered_pointers:
        with pytest.raises(ValueError, match="exact member"):
            validate_open_problem(replace(explicit_extraction(), evidence=altered), note)


def test_open_problem_scope_and_requested_result_must_match_pointer_claim() -> None:
    note = problem_note()
    with pytest.raises(ValueError, match="scope"):
        validate_open_problem(explicit_extraction(problem_scope=scope()), note)
    wrong = result(complexity_class="LOGSPACE")
    with pytest.raises(ValueError, match="requested result"):
        validate_open_problem(explicit_extraction(requested_result=wrong), note)


def test_valid_implicit_gap_requires_explicit_narrower_to_broader_relation() -> None:
    note = problem_note()
    item = replace(
        explicit_extraction(),
        explicitness=OpenProblemExplicitness.IMPLICIT_GAP,
        evidence=note.evidence[-1],
        restricted_case_evidence=note.evidence[4],
        unresolved_case_evidence=note.evidence[-1],
    )

    problem = validate_open_problem(item, note)

    assert problem.scope == general_scope()
    assert problem.restricted_case_evidence == note.evidence[4]


@pytest.mark.parametrize(
    "wrong",
    [
        result(complexity_class="LOGSPACE"),
        result(complexity_class="NP-HARD", direction=ResultDirection.LOWER_BOUND),
        result(measure=ComplexityMeasure.PREPROCESSING),
        result(direction=ResultDirection.ALGORITHMIC, question_type=QuestionType.ALGORITHM),
    ],
)
def test_implicit_gap_restricted_theorem_must_prove_exact_requested_result_signature(
    wrong: TheoremResult,
) -> None:
    note = problem_note()
    restricted_note = deep_note(
        theorem_scope=scope(),
        theorem_results=(wrong,),
        paper_id=SOURCE_PAPER_ID,
        version_id=SOURCE_VERSION_ID,
        source_hash=SOURCE_HASH,
    )
    combined = replace(note, evidence=note.evidence[:4] + (restricted_note.evidence[4],) + note.evidence[5:])
    item = replace(
        explicit_extraction(),
        explicitness=OpenProblemExplicitness.IMPLICIT_GAP,
        evidence=combined.evidence[-1],
        restricted_case_evidence=combined.evidence[4],
        unresolved_case_evidence=combined.evidence[-1],
    )

    with pytest.raises(ValueError, match="requested result|exact.*signature"):
        validate_open_problem(item, combined)


def test_implicit_gap_rejects_unrelated_or_equal_scopes() -> None:
    unrelated = scope(constraints=("graph databases", "bounded degree"))
    unrelated_note = problem_note(future_restricted=unrelated)
    unrelated_item = replace(
        explicit_extraction(),
        explicitness=OpenProblemExplicitness.IMPLICIT_GAP,
        evidence=unrelated_note.evidence[-1],
        restricted_case_evidence=unrelated_note.evidence[4],
        unresolved_case_evidence=unrelated_note.evidence[-1],
    )
    with pytest.raises(ValueError, match="restricted scope|NARROWER|generalization"):
        validate_open_problem(unrelated_item, unrelated_note)

    equal_note = problem_note(future_restricted=general_scope())
    equal_item = replace(
        unrelated_item,
        evidence=equal_note.evidence[-1],
        restricted_case_evidence=equal_note.evidence[4],
        unresolved_case_evidence=equal_note.evidence[-1],
    )
    with pytest.raises(ValueError, match="NARROWER|generalization"):
        validate_open_problem(equal_item, equal_note)


def test_implicit_gap_rejects_agent_created_limitation_without_open_claim() -> None:
    note = problem_note()
    invented = replace(
        explicit_extraction(),
        explicitness=OpenProblemExplicitness.IMPLICIT_GAP,
        evidence=note.evidence[5],
        restricted_case_evidence=note.evidence[4],
        unresolved_case_evidence=note.evidence[5],
    )

    with pytest.raises(ValueError, match="structured claim|OPEN_PROBLEM|FUTURE_WORK"):
        validate_open_problem(invented, note)


def test_open_verified_requires_problem_bound_complete_category_source_manifest() -> None:
    note = problem_note()
    good = complete_search()
    assert validate_open_problem(
        explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=good), note
    ).status is OpenStatus.OPEN_VERIFIED

    missing_category = tuple(query for query in good.queries if query.category is not SearchQueryCategory.LATER_VENUE)
    with pytest.raises(ValueError, match="query categories"):
        validate_open_problem(
            explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=complete_search(queries=missing_category)),
            note,
        )
    with pytest.raises(ValueError, match="primary.*metadata|source coverage"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=complete_search(sources=(SearchSource.DBLP, SearchSource.OPENALEX)),
            ),
            note,
        )


def test_open_verified_rejects_wrong_binding_low_confidence_and_weak_review() -> None:
    note = problem_note()
    bad_records = (
        complete_search(problem_id="problem:other"),
        complete_search(fingerprint="f" * 64),
        complete_search(confidence=SearchConfidence.LOW),
        complete_search(reviewer_verified=False),
    )
    for record in bad_records:
        with pytest.raises(ValueError, match="problem|fingerprint|confidence|reviewer"):
            validate_open_problem(
                explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=record), note
            )
    with pytest.raises(ValueError, match="reviewer conclusion"):
        replace(complete_search(), reviewer_conclusion="no result found")
    with pytest.raises(ValueError, match="rationale"):
        complete_search(reviewer_rationale="x")
    with pytest.raises(ValueError, match="through 2026"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(complete_search(), through_year=2025),
            ),
            note,
        )


def test_open_verified_rejects_plausible_resolution_candidate() -> None:
    note = problem_note()
    candidate = SearchCandidate(
        candidate_id="paper:possible-resolution-2026",
        disposition=SearchCandidateDisposition.PLAUSIBLE_RESOLUTION,
        rationale="The abstract appears to claim the exact unrestricted result and still requires theorem verification.",
    )
    record = complete_search(candidates=(candidate,))

    with pytest.raises(ValueError, match="plausible resolution"):
        validate_open_problem(explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=record), note)


def test_open_verified_requires_positive_later_exact_status_evidence_and_nonempty_candidates() -> None:
    note = problem_note()
    empty = complete_search(candidates=(), status_evidence=())
    with pytest.raises(ValueError, match="positive|candidate|status evidence"):
        validate_open_problem(explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=empty), note)

    good = complete_search()
    status = good.open_status_evidence[0]
    nonmember = replace(
        status,
        evidence=replace(
            status.evidence,
            paraphrase="Within the exact stated relational scope, a caller-authored open-status paraphrase is supplied.",
        ),
    )
    with pytest.raises(ValueError, match="exact member|status evidence"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, open_status_evidence=(nonmember,)),
            ),
            note,
        )
    older = replace(status, metadata=metadata("Resolution Scope Result", 2025))
    with pytest.raises(ValueError, match="later|publication year"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, open_status_evidence=(older,)),
            ),
            note,
        )
    theorem_status = replace(status, evidence=status.note.evidence[4])
    with pytest.raises(ValueError, match="OPEN_PROBLEM|FUTURE_WORK|status evidence"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, open_status_evidence=(theorem_status,)),
            ),
            note,
        )
    wrong_scope_note = problem_note(
        future_remaining=scope(),
        paper_id=RESOLUTION_PAPER_ID,
        version_id=RESOLUTION_VERSION_ID,
        source_hash=RESOLUTION_HASH,
    )
    wrong_scope_status = OpenStatusEvidence(
        wrong_scope_note,
        wrong_scope_note.evidence[-2],
        RESOLUTION_METADATA,
    )
    with pytest.raises(ValueError, match="exact problem scope|requested result"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, open_status_evidence=(wrong_scope_status,)),
            ),
            note,
        )


def test_open_verified_manifest_hash_is_recomputed_from_canonical_payload() -> None:
    note = problem_note()
    good = complete_search()
    forged = replace(good.manifests[0], manifest_hash="f" * 64)
    with pytest.raises(ValueError, match="manifest.*hash|recompute|canonical"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, manifests=(forged,) + good.manifests[1:]),
            ),
            note,
        )
    wrong_text = replace(good.manifests[0], query_text="a different exact query text")
    wrong_text = replace(
        wrong_text,
        manifest_hash=search_manifest_hash(
            wrong_text.query_category,
            wrong_text.query_text,
            wrong_text.source,
            wrong_text.returned_ids,
            wrong_text.checked_ids,
        ),
    )
    with pytest.raises(ValueError, match="exact query text|declared query"):
        validate_open_problem(
            explicit_extraction(
                status=OpenStatus.OPEN_VERIFIED,
                followup_search=replace(good, manifests=(wrong_text,) + good.manifests[1:]),
            ),
            note,
        )


def resolution_note(*, theorem_scope: QueryProblemScope, theorem_result: TheoremResult,
                    paper_id: str = RESOLUTION_PAPER_ID,
                    version_id: str = RESOLUTION_VERSION_ID,
                    source_hash: str = RESOLUTION_HASH):
    signature = ProofTechniqueSignature(
        ProofTechnique.DYNAMIC_PROGRAMMING,
        (),
        "Extending the stated decomposition beyond bounded arity.",
        "NOT_APPLICABLE",
    )
    return deep_note(
        theorem_scope=theorem_scope,
        theorem_results=(theorem_result,),
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
        technique_signature=signature,
    )


def resolution_theorem(*, theorem_scope: QueryProblemScope, theorem_result: TheoremResult,
                       paper_id: str = RESOLUTION_PAPER_ID,
                       version_id: str = RESOLUTION_VERSION_ID,
                       source_hash: str = RESOLUTION_HASH):
    signature = ProofTechniqueSignature(
        ProofTechnique.DYNAMIC_PROGRAMMING,
        (),
        "Extending the stated decomposition beyond bounded arity.",
        "NOT_APPLICABLE",
    )
    note = resolution_note(
        theorem_scope=theorem_scope,
        theorem_result=theorem_result,
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
    )
    techniques = ProofTechniqueProfile(
        primary=ProofTechnique.DYNAMIC_PROGRAMMING,
        secondary=(),
        technical_obstacle="Extending the stated decomposition beyond bounded arity.",
        restriction_preservation_trick="NOT_APPLICABLE",
        evidence=note.evidence[4],
    )
    item = TheoremExtraction(
        theorem_id="theorem:resolution-2",
        paraphrase="For conjunctive queries under set semantics, the theorem proves the claimed result for the stated relational scope.",
        scope=theorem_scope,
        results=(theorem_result,),
        assumptions=("finite relational structures",),
        techniques=techniques,
        evidence=note.evidence[4],
    )
    authorization = authorize_complete_theorem(note, note.evidence[4])
    return validate_theorem(item, note, authorization), note


def claim(explanation: str = "The later theorem proves the PTIME data-complexity upper bound requested by the original problem.") -> ResolutionClaim:
    theorem_note = resolution_note(theorem_scope=general_scope(), theorem_result=result())
    return ResolutionClaim(
        resolution_paper_id=RESOLUTION_PAPER_ID,
        resolution_version_id=RESOLUTION_VERSION_ID,
        explanation=explanation,
        evidence=theorem_note.evidence[4],
    )


def original_problem(problem_scope: QueryProblemScope | None = None):
    note = problem_note()
    return validate_open_problem(explicit_extraction(problem_scope=problem_scope), note)


def resolve(problem, theorem, note, resolution_claim=None, *, source_metadata=SOURCE_METADATA,
            resolution_metadata=RESOLUTION_METADATA):
    return validate_resolution(
        problem,
        resolution_claim or claim(),
        note,
        theorem,
        source_metadata=source_metadata,
        resolution_metadata=resolution_metadata,
    )


def test_resolution_claim_has_no_caller_only_year_or_scope_fields() -> None:
    assert {field.name for field in fields(ResolutionClaim)}.isdisjoint({"resolution_year", "scope"})


def test_resolved_requires_validated_theorem_and_verified_later_metadata() -> None:
    problem = original_problem()
    theorem, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())

    with pytest.raises(ValueError, match="validated theorem"):
        resolve(problem, None, note)
    unverified = metadata("Resolution Scope Result", 2026, source=SourceKind.DBLP)
    with pytest.raises(ValueError, match="verified metadata"):
        resolve(problem, theorem, note, resolution_metadata=unverified)
    not_later = metadata("Resolution Scope Result", 2025)
    with pytest.raises(ValueError, match="later publication"):
        resolve(problem, theorem, note, resolution_metadata=not_later)


def test_resolution_classifies_equal_scope_as_resolved_and_narrower_as_partial() -> None:
    problem = original_problem()
    exact, exact_note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    assert resolve(problem, exact, exact_note).status is OpenStatus.RESOLVED

    narrower_scope = scope(constraints=("relational instances", "acyclic queries"))
    narrower, narrower_note = resolution_theorem(theorem_scope=narrower_scope, theorem_result=result())
    partial_claim = replace(claim(), evidence=narrower_note.evidence[4])
    assert resolve(problem, narrower, narrower_note, partial_claim).status is OpenStatus.PARTIALLY_RESOLVED


def test_shared_constraint_string_without_subset_relation_is_not_partial() -> None:
    original_scope = scope(constraints=("relational instances", "ordered structures"))
    note = problem_note(future_remaining=original_scope)
    extraction = replace(
        explicit_extraction(problem_scope=original_scope),
        evidence=note.evidence[-2],
    )
    problem = validate_open_problem(extraction, note)
    incomparable = scope(constraints=("relational instances", "acyclic queries"))
    theorem, theorem_note = resolution_theorem(theorem_scope=incomparable, theorem_result=result())
    resolution_claim = replace(claim(), evidence=theorem_note.evidence[4])

    with pytest.raises(ValueError, match="DISJOINT|scope"):
        resolve(problem, theorem, theorem_note, resolution_claim)


@pytest.mark.parametrize(
    "wrong_result",
    [
        result(complexity_class="NP-HARD", direction=ResultDirection.LOWER_BOUND),
        result(measure=ComplexityMeasure.PREPROCESSING),
        result(complexity_class="LOGSPACE"),
        result(
            direction=ResultDirection.ALGORITHMIC,
            question_type=QuestionType.ALGORITHM,
        ),
    ],
)
def test_same_scope_wrong_result_signature_cannot_resolve(wrong_result: TheoremResult) -> None:
    problem = original_problem()
    theorem, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=wrong_result)
    resolution_claim = replace(claim(), evidence=note.evidence[4])

    with pytest.raises(ValueError, match="requested result"):
        resolve(problem, theorem, note, resolution_claim)


def test_resolution_explanation_must_name_matched_result() -> None:
    problem = original_problem()
    theorem, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    weak = replace(claim(), explanation="The later theorem answers the question.")

    with pytest.raises(ValueError, match="matched result|explanation"):
        resolve(problem, theorem, note, weak)


def test_validated_problem_and_resolution_cannot_be_replaced() -> None:
    problem = original_problem()
    with pytest.raises(ValueError, match="only be created by validate_open_problem"):
        replace(problem, status=OpenStatus.OPEN_VERIFIED)

    theorem, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    resolution = resolve(problem, theorem, note)
    with pytest.raises(ValueError, match="only be created by validate_resolution"):
        replace(resolution, status=OpenStatus.PARTIALLY_RESOLVED)


def test_resolution_rejects_certificate_and_source_mismatches() -> None:
    problem = original_problem()
    theorem, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    changed_limitation = replace(
        note.evidence[5],
        paraphrase="Within the stated scope, a materially different limitation is recorded.",
    )
    changed_note = replace(note, evidence=note.evidence[:5] + (changed_limitation,))
    with pytest.raises(ValueError, match="certificate|authorization"):
        resolve(problem, theorem, changed_note)

    mismatched_claim = replace(claim(), resolution_version_id="version:other-v1")
    with pytest.raises(ValueError, match="same source"):
        resolve(problem, theorem, note, mismatched_claim)


def version_family(*, source_year: int = 2025, target_year: int = 2026,
                   relation: VersionRelation = VersionRelation.JOURNAL_EXTENSION_OF):
    source_observation = SourceObservation(
        source=SourceKind.PUBLISHER,
        observed_title="Versioned Scope Result",
        authors=("Ada Author", "Bert Author"),
        year=source_year,
        observed_at=date(2026, 8, 18),
        evidence_url="https://evidence.example/versioned/source",
        venue="ICDT",
        doi="10.1000/versioned-scope-result",
        official_url="https://publisher.example/versioned/source",
    )
    target_observation = replace(
        source_observation,
        year=target_year,
        evidence_url="https://evidence.example/versioned/target",
        official_url="https://publisher.example/versioned/target",
    )
    verified = verify_metadata((source_observation,))
    source_version = VersionObservation(
        "version:versioned-source",
        VersionKind.CONFERENCE,
        source_observation,
        "https://versions.example/versioned-source",
    )
    target_version = VersionObservation(
        "version:versioned-target",
        VersionKind.JOURNAL,
        target_observation,
        "https://versions.example/versioned-target",
    )
    lineage = VersionLineage(
        source_version.version_id,
        target_version.version_id,
        relation,
        (target_observation.evidence_url,),
        LineageEvidenceKind.EXPLICIT_VERSION_STATEMENT,
    )
    return resolve_version_family(verified, (source_version, target_version), (lineage,))


def validate_same_paper_lineage_resolution(family):
    source_note = problem_note(
        paper_id=family.paper_id,
        version_id="version:versioned-source",
        source_hash="e" * 64,
    )
    problem = validate_open_problem(
        replace(explicit_extraction(), evidence=source_note.evidence[-2]),
        source_note,
    )
    theorem, theorem_note = resolution_theorem(
        theorem_scope=general_scope(),
        theorem_result=result(),
        paper_id=family.paper_id,
        version_id="version:versioned-target",
        source_hash="f" * 64,
    )
    resolution_claim = ResolutionClaim(
        resolution_paper_id=family.paper_id,
        resolution_version_id="version:versioned-target",
        explanation="The later theorem proves the PTIME data-complexity upper bound requested by the original problem.",
        evidence=theorem_note.evidence[4],
    )
    return validate_resolution(
        problem,
        resolution_claim,
        theorem_note,
        theorem,
        source_metadata=family.metadata,
        resolution_metadata=family.metadata,
        version_family=family,
    )


def test_same_paper_resolution_requires_forward_dated_validated_lineage() -> None:
    assert validate_same_paper_lineage_resolution(version_family()).status is OpenStatus.RESOLVED

    with pytest.raises(ValueError, match="later|publication year|chronology"):
        validate_same_paper_lineage_resolution(version_family(source_year=2026, target_year=2025))

    with pytest.raises(ValueError, match="strictly later|publication year|verified dates"):
        validate_same_paper_lineage_resolution(version_family(source_year=2026, target_year=2026))

    for relation in (VersionRelation.SAME_WORK, VersionRelation.UNKNOWN_RELATED):
        with pytest.raises(ValueError, match="chronological|non-temporal|later"):
            validate_same_paper_lineage_resolution(version_family(relation=relation))
