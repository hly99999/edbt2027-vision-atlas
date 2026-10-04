from dataclasses import fields, replace

import pytest

from db_theory_atlas.evidence import authorize_complete_theorem
from db_theory_atlas.model import EvidencePointer, EvidenceType
from db_theory_atlas.reading import CoverageEntry, CoverageKind, NoteRecord, ReadingState
from db_theory_atlas.techniques import (
    ProofTechnique,
    ProofTechniqueProfile,
    ProofTechniqueSignature,
    validate_techniques,
)
from db_theory_atlas.theorems import (
    ComplexityMeasure,
    ParameterDimension,
    ParameterRole,
    ParameterSpec,
    QueryProblemScope,
    QuerySemantics,
    QuestionType,
    ResultDirection,
    ScopeRelation,
    TheoremExtraction,
    TheoremResult,
    claim_for_theorem,
    compare_scopes,
    result_payload,
    scope_payload,
    validate_measure_roles,
    validate_theorem,
)


PAPER_ID = "paper:scope-result-2025"
VERSION_ID = "version:scope-result-v1"
SOURCE_HASH = "a" * 64


def scope(
    *,
    semantics: QuerySemantics = QuerySemantics.SET,
    query_role: ParameterRole = ParameterRole.FIXED,
    data_role: ParameterRole = ParameterRole.INPUT,
    constraints: tuple[str, ...] = ("relational instances", "bounded arity"),
    extra_parameters: tuple[ParameterSpec, ...] = (),
) -> QueryProblemScope:
    return QueryProblemScope(
        input="finite relational database",
        output="query answers",
        query_language="conjunctive queries",
        semantics=semantics,
        constraints=constraints,
        parameters=(
            ParameterSpec("query", query_role, ParameterDimension.QUERY),
            ParameterSpec("database", data_role, ParameterDimension.DATA),
        ) + extra_parameters,
    )


def result(
    *,
    complexity_class: str = "PTIME",
    direction: ResultDirection = ResultDirection.UPPER_BOUND,
    measure: ComplexityMeasure = ComplexityMeasure.DATA_COMPLEXITY,
    question_type: QuestionType = QuestionType.COMPLEXITY_BOUND,
) -> TheoremResult:
    return TheoremResult(complexity_class, direction, measure, question_type)


def pointer(
    kind: EvidenceType,
    page: int,
    heading: str,
    paraphrase: str,
    *,
    claim=None,
    verified: bool = True,
    paper_id: str = PAPER_ID,
    version_id: str = VERSION_ID,
    source_hash: str = SOURCE_HASH,
) -> EvidencePointer:
    return EvidencePointer(
        paper_id=paper_id,
        version_id=version_id,
        page=page,
        heading=heading,
        evidence_type=kind,
        paraphrase=paraphrase,
        source_hash=source_hash,
        verified=verified,
        claim=claim,
    )


def deep_note(
    *,
    theorem_scope: QueryProblemScope | None = None,
    theorem_results: tuple[TheoremResult, ...] | None = None,
    paper_id: str = PAPER_ID,
    version_id: str = VERSION_ID,
    source_hash: str = SOURCE_HASH,
    assumptions: tuple[str, ...] = ("finite relational structures",),
    technique_signature: ProofTechniqueSignature | None = None,
) -> NoteRecord:
    supported_scope = theorem_scope or scope()
    supported_results = theorem_results or (result(),)
    evidence = (
        pointer(EvidenceType.METADATA, 1, "Introduction", "For the stated paper, the metadata identifies the source.", paper_id=paper_id, version_id=version_id, source_hash=source_hash),
        pointer(EvidenceType.ABSTRACT, 1, "Introduction", "For the stated fragment, the abstract summarizes the result.", paper_id=paper_id, version_id=version_id, source_hash=source_hash),
        pointer(EvidenceType.PROBLEM_DEFINITION, 1, "Introduction", "For the stated fragment, the paper defines query evaluation.", paper_id=paper_id, version_id=version_id, source_hash=source_hash),
        pointer(EvidenceType.PROBLEM_DEFINITION, 4, "Formal Scope", "Under the stated assumptions, the scope fixes the query and treats the database as input.", paper_id=paper_id, version_id=version_id, source_hash=source_hash),
        pointer(
            EvidenceType.THEOREM,
            7,
            "Theorem 1",
            "For fixed conjunctive queries under set semantics, the theorem gives a PTIME data-complexity upper bound.",
            claim=claim_for_theorem(
                supported_scope,
                supported_results,
                assumptions,
                technique_signature or default_technique_signature(),
            ),
            paper_id=paper_id,
            version_id=version_id,
            source_hash=source_hash,
        ),
        pointer(EvidenceType.LIMITATION, 9, "Limitations", "Within the stated scope, the paper records its limitations.", paper_id=paper_id, version_id=version_id, source_hash=source_hash),
    )
    return NoteRecord(
        paper_id=paper_id,
        version_id=version_id,
        source_hash=source_hash,
        read_depth=ReadingState.DEEP_READ,
        sections=("Introduction", "Formal Scope", "Theorems", "Limitations", "Conclusion"),
        pages=(1, 4, 7, 9),
        headings=("Introduction", "Formal Scope", "Theorem 1", "Limitations", "Conclusion"),
        created_at="2026-08-18T00:00:00Z",
        updated_at="2026-08-18T00:00:00Z",
        extractor_status="complete",
        reviewer_status="reviewed",
        coverage=(
            CoverageEntry(CoverageKind.INTRODUCTION, 1, "Introduction"),
            CoverageEntry(CoverageKind.CONCLUSION, 9, "Conclusion"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 1, "Introduction"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 7, "Theorem 1"),
            CoverageEntry(CoverageKind.FULL_SCAN_SECTION, 9, "Limitations"),
            CoverageEntry(CoverageKind.PROBLEM_DEFINITION, 1, "Introduction"),
            CoverageEntry(CoverageKind.FORMAL_SCOPE_ASSUMPTIONS, 4, "Formal Scope"),
            CoverageEntry(CoverageKind.THEOREM_RESULTS, 7, "Theorem 1"),
            CoverageEntry(CoverageKind.LIMITATIONS_FUTURE_WORK, 9, "Limitations"),
        ),
        evidence=evidence,
    )


def default_technique_signature() -> ProofTechniqueSignature:
    return ProofTechniqueSignature(
        primary=ProofTechnique.HOMOMORPHISM,
        secondary=(ProofTechnique.CANONICAL_DATABASE,),
        technical_obstacle="Preserving the stated bounded-arity restriction during the homomorphism construction.",
        restriction_preservation_trick="Use the canonical database only within the stated fragment.",
    )


def profile(note: NoteRecord, signature: ProofTechniqueSignature | None = None) -> ProofTechniqueProfile:
    supported = signature or default_technique_signature()
    return ProofTechniqueProfile(
        primary=supported.primary,
        secondary=supported.secondary,
        technical_obstacle=supported.technical_obstacle,
        restriction_preservation_trick=supported.restriction_preservation_trick,
        evidence=note.evidence[4],
    )


def extraction(note: NoteRecord, *, claimed_scope: QueryProblemScope | None = None,
               claimed_results: tuple[TheoremResult, ...] | None = None,
               assumptions: tuple[str, ...] = ("finite relational structures",),
               technique_signature: ProofTechniqueSignature | None = None) -> TheoremExtraction:
    return TheoremExtraction(
        theorem_id="theorem:scope-result-1",
        paraphrase="For fixed conjunctive queries under set semantics and bounded arity, evaluation is in PTIME in data complexity.",
        scope=claimed_scope or scope(),
        results=claimed_results or (result(),),
        assumptions=assumptions,
        techniques=profile(note, technique_signature),
        evidence=note.evidence[4],
    )


def validate(item: TheoremExtraction, note: NoteRecord | None = None):
    source = note or deep_note()
    authorization = authorize_complete_theorem(source, source.evidence[4])
    return validate_theorem(item, source, authorization)


def test_theorem_extraction_has_no_caller_authored_evidence_support_fields() -> None:
    assert {field.name for field in fields(TheoremExtraction)}.isdisjoint({"evidence_scope", "evidence_results"})


def test_validates_claims_derived_from_authorized_pointer_payload() -> None:
    note = deep_note()
    theorem = validate(extraction(note), note)

    assert theorem.scope == scope()
    assert theorem.results == (result(),)
    assert theorem.evidence.claim == claim_for_theorem(
        scope(), (result(),), ("finite relational structures",), default_technique_signature()
    )


def test_theorem_payload_and_measure_helpers_are_public() -> None:
    assert scope_payload(scope())["semantics"] == QuerySemantics.SET.value
    assert result_payload(result())["measure"] == ComplexityMeasure.DATA_COMPLEXITY.value
    validate_measure_roles(result(), scope())


def test_paired_scope_result_mutation_cannot_replace_note_bound_support() -> None:
    note = deep_note()
    combined_scope = scope(query_role=ParameterRole.INPUT)
    combined_lower = result(
        complexity_class="NP-HARD",
        direction=ResultDirection.LOWER_BOUND,
        measure=ComplexityMeasure.COMBINED_COMPLEXITY,
    )
    mutated = extraction(note, claimed_scope=combined_scope, claimed_results=(combined_lower,))

    with pytest.raises(ValueError, match="evidence-supported|authorized"):
        validate(mutated, note)


def test_rejects_internally_inconsistent_upper_lower_class_combinations() -> None:
    with pytest.raises(ValueError, match="direction|class"):
        result(complexity_class="PTIME", direction=ResultDirection.LOWER_BOUND)
    with pytest.raises(ValueError, match="direction|class"):
        result(complexity_class="NP-HARD", direction=ResultDirection.UPPER_BOUND)


def test_complexity_roles_are_dimension_specific() -> None:
    unrelated_fixed = ParameterSpec("unrelated", ParameterRole.FIXED, ParameterDimension.PARAMETER)
    with pytest.raises(ValueError, match="QUERY.*FIXED|query.*FIXED"):
        deep_note(
            theorem_scope=scope(
                query_role=ParameterRole.INPUT,
                data_role=ParameterRole.INPUT,
                extra_parameters=(unrelated_fixed,),
            ),
            theorem_results=(result(),),
        )
    with pytest.raises(ValueError, match="DATA.*INPUT|data.*INPUT"):
        deep_note(theorem_scope=scope(data_role=ParameterRole.FIXED), theorem_results=(result(),))
    with pytest.raises(ValueError, match="QUERY.*INPUT|query.*INPUT"):
        deep_note(
            theorem_scope=scope(query_role=ParameterRole.FIXED, data_role=ParameterRole.INPUT),
            theorem_results=(result(measure=ComplexityMeasure.COMBINED_COMPLEXITY),),
        )
    with pytest.raises(ValueError, match="DATA.*FIXED|data.*FIXED"):
        deep_note(
            theorem_scope=scope(query_role=ParameterRole.INPUT, data_role=ParameterRole.INPUT),
            theorem_results=(result(measure=ComplexityMeasure.QUERY_COMPLEXITY),),
        )
    with pytest.raises(ValueError, match="named.*PARAMETER|PARAMETER.*dimension"):
        deep_note(
            theorem_scope=scope(),
            theorem_results=(
                result(
                    direction=ResultDirection.PARAMETERIZED,
                    measure=ComplexityMeasure.PARAMETERIZED_COMPLEXITY,
                    question_type=QuestionType.PARAMETERIZED,
                ),
            ),
        )


def test_requires_set_bag_or_not_applicable_semantics() -> None:
    with pytest.raises(ValueError, match="semantics"):
        scope(semantics="UNKNOWN")


def test_scope_relation_is_explicit_and_conservative() -> None:
    general = scope(constraints=("relational instances",))
    narrow = scope(constraints=("relational instances", "bounded arity"))
    other = scope(constraints=("graph databases",))
    unknown = scope(constraints=("UNKNOWN",))

    assert compare_scopes(general, general) is ScopeRelation.EQUAL
    assert compare_scopes(narrow, general) is ScopeRelation.NARROWER
    assert compare_scopes(general, narrow) is ScopeRelation.BROADER
    assert compare_scopes(other, general) is ScopeRelation.DISJOINT
    assert compare_scopes(unknown, general) is ScopeRelation.UNKNOWN


def test_rejects_unsupported_broadened_scope() -> None:
    note = deep_note()
    broader = scope(constraints=("relational instances",))

    with pytest.raises(ValueError, match="broader"):
        validate(extraction(note, claimed_scope=broader), note)


def test_rejects_narrower_scope_as_unlabeled_derived_specialization() -> None:
    evidence_scope = scope(constraints=("relational instances",))
    note = deep_note(theorem_scope=evidence_scope)
    narrower = scope(constraints=("relational instances", "acyclic queries"))

    with pytest.raises(ValueError, match="EQUAL|derived specialization|exact"):
        validate(extraction(note, claimed_scope=narrower), note)


def test_assumptions_and_proof_technique_must_match_authorized_claim() -> None:
    note = deep_note()
    with pytest.raises(ValueError, match="assumptions"):
        validate(extraction(note, assumptions=("finite ordered structures",)), note)

    changed = replace(default_technique_signature(), primary=ProofTechnique.CHASE)
    with pytest.raises(ValueError, match="proof technique|primary"):
        validate(extraction(note, technique_signature=changed), note)

    changed_obstacle = replace(default_technique_signature(), technical_obstacle="A caller-authored unsupported obstacle.")
    with pytest.raises(ValueError, match="proof technique|obstacle"):
        validate(extraction(note, technique_signature=changed_obstacle), note)


def test_proof_technique_taxonomy_has_exact_task_j_members() -> None:
    expected = {
        "HOMOMORPHISM", "CANONICAL_DATABASE", "CHASE", "TREE_DECOMPOSITION",
        "HYPERTREE_DECOMPOSITION", "DYNAMIC_PROGRAMMING", "AUTOMATA", "GAMES",
        "FINITE_MODEL_ARGUMENTS", "CSP_REDUCTION", "SAT_REDUCTION", "QSAT_REDUCTION",
        "GRAPH_GADGET", "HITTING_SET", "SET_COVER", "VERTEX_COVER", "EXACT_COVER",
        "PARAMETERIZED_REDUCTION", "KERNELIZATION", "ENUMERATION_DELAY", "DUALITY",
        "FRONTIER", "TEACHING_SET", "WITNESS_CONSTRUCTION", "CANONICAL_FORM",
        "SMALL_MODEL", "DESCRIPTIVE_COMPLEXITY",
    }
    assert {item.value for item in ProofTechnique} == expected


def test_proof_technique_secondary_is_distinct_and_source_bound() -> None:
    note = deep_note()
    with pytest.raises(ValueError, match="taxonomy"):
        replace(profile(note), primary="INDUCTION")
    with pytest.raises(ValueError, match="secondary"):
        replace(profile(note), secondary=(ProofTechnique.HOMOMORPHISM,))

    item = profile(note)
    assert validate_techniques(item, note) is item


def test_validated_theorem_cannot_be_forged_by_dataclass_replacement() -> None:
    note = deep_note()
    theorem = validate(extraction(note), note)

    with pytest.raises(ValueError, match="only be created by validate_theorem"):
        replace(theorem, scope=scope(constraints=("UNKNOWN",)))
