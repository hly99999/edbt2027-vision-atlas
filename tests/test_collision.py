from dataclasses import replace

import pytest

from db_theory_atlas.collision import (
    CollisionRecord,
    CollisionSeverity,
    NoveltyPrimitive,
    PrimitiveStatus,
    assess_collision,
)
from db_theory_atlas.evidence import authorize_complete_theorem
from db_theory_atlas.graph import (
    EdgeRelation,
    EvidenceBackedGraph,
    GraphEdge,
    GraphEvidence,
    NodeKind,
    claim_for_graph_relation,
)
from db_theory_atlas.model import EvidenceType
from db_theory_atlas.serialization import freeze_json
from test_graph import relation_evidence
from test_problems import (
    RESOLUTION_METADATA,
    SOURCE_METADATA,
    general_scope,
    explicit_extraction,
    original_problem,
    problem_note,
    resolution_theorem,
    result,
    validate_open_problem,
)
from test_theorems import pointer, scope
from db_theory_atlas.theorems import TheoremExtraction, validate_theorem


def primitive_membership_evidence(
    primitive_id: str,
    phrase: str,
    member_id: str,
    member_kind: NodeKind,
    years: tuple[int, ...],
    status: PrimitiveStatus,
    *,
    note=None,
) -> GraphEvidence:
    note = note or problem_note()
    evidence = pointer(
        EvidenceType.GRAPH_RELATION,
        9,
        "Limitations",
        "Within the stated scope, the inspected passage records this exact primitive membership.",
        claim=freeze_json({
            "claim_type": "NOVELTY_PRIMITIVE_MEMBERSHIP",
            "primitive_id": primitive_id,
            "phrase": " ".join(phrase.casefold().split()),
            "member_id": member_id,
            "member_kind": member_kind.value,
            "years": years,
            "status": status.value,
        }),
        paper_id=note.paper_id,
        version_id=note.version_id,
        source_hash=note.source_hash,
    )
    note = replace(note, evidence=note.evidence + (evidence,))
    return GraphEvidence(evidence, note)


def bound_solution_evidence(problem, theorem) -> GraphEvidence:
    note = problem_note()
    evidence = pointer(
        EvidenceType.GRAPH_RELATION,
        9,
        "Limitations",
        "Within the stated scope, the inspected passage binds the exact problem to the exact resolving theorem.",
        claim=claim_for_graph_relation(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            theorem.paper_id,
            NodeKind.PAPER,
            source_record_id=problem.problem_id,
            target_record_id=theorem.theorem_id,
            source_results=(problem.requested_result,),
            target_results=theorem.results,
        ),
        paper_id=note.paper_id,
        version_id=note.version_id,
        source_hash=note.source_hash,
    )
    return GraphEvidence(evidence, replace(note, evidence=note.evidence + (evidence,)))


def same_paper_theorem_with_id(theorem_id: str):
    base, note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    extraction = TheoremExtraction(
        theorem_id,
        base.paraphrase,
        base.scope,
        base.results,
        base.assumptions,
        base.techniques,
        base.evidence,
    )
    return validate_theorem(
        extraction,
        note,
        authorize_complete_theorem(note, base.evidence),
    ), note


def collision_graph(problem, theorem):
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    evidence = bound_solution_evidence(problem, theorem)
    graph.add_edges((GraphEdge(
        problem.problem_id,
        NodeKind.OPEN_PROBLEM,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
        NodeKind.PAPER,
        (evidence,),
    ),))
    return graph


def collision_for_severity(severity: CollisionSeverity):
    problem = original_problem()
    if severity is CollisionSeverity.DIRECT:
        theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
        return assess_collision(problem, theorem, graph=collision_graph(problem, theorem))
    if severity is CollisionSeverity.STRONG:
        theorem, _note = resolution_theorem(
            theorem_scope=scope(constraints=("relational instances", "acyclic queries")),
            theorem_result=result(),
        )
        graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
        primitive = NoveltyPrimitive(
            "primitive:ranking-overlap",
            "ranking overlap witness",
            (problem.paper_id,),
            (theorem.theorem_id,),
            (2025, 2026),
            PrimitiveStatus.ACTIVE,
            (
                primitive_membership_evidence(
                    "primitive:ranking-overlap",
                    "ranking overlap witness",
                    problem.paper_id,
                    NodeKind.PAPER,
                    (2025, 2026),
                    PrimitiveStatus.ACTIVE,
                ),
                primitive_membership_evidence(
                    "primitive:ranking-overlap",
                    "ranking overlap witness",
                    theorem.theorem_id,
                    NodeKind.THEOREM,
                    (2025, 2026),
                    PrimitiveStatus.ACTIVE,
                    note=_note,
                ),
            ),
        )
        graph.add_nodes((primitive,))
        return assess_collision(problem, theorem, graph=graph, primitives=(primitive,))
    theorem, _note = resolution_theorem(
        theorem_scope=scope(constraints=("graph databases",)),
        theorem_result=result(complexity_class="LOGSPACE"),
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    return assess_collision(problem, theorem, graph=graph)


def test_collision_severity_is_exact_controlled_taxonomy() -> None:
    assert {item.value for item in CollisionSeverity} == {"DIRECT", "STRONG", "PARTIAL", "WEAK", "NONE"}


def test_collision_records_cannot_be_caller_forged_or_replaced() -> None:
    valid = collision_for_severity(CollisionSeverity.DIRECT)
    with pytest.raises(ValueError, match="only be created by assess_collision"):
        replace(valid, severity=CollisionSeverity.NONE)
    with pytest.raises(ValueError, match="only be created by assess_collision"):
        CollisionRecord(
            valid.left_id,
            valid.right_id,
            CollisionSeverity.DIRECT,
            valid.reasons,
            valid.evidence,
            valid.shared_primitive_ids,
            True,
            True,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        )


def test_failed_primitive_registration_is_atomic() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    dangling = NoveltyPrimitive(
        "primitive:dangling-membership",
        "dangling membership witness",
        ("paper:missing",),
        (),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (primitive_membership_evidence(
            "primitive:dangling-membership",
            "dangling membership witness",
            "paper:missing",
            NodeKind.PAPER,
            (2026,),
            PrimitiveStatus.ACTIVE,
            note=problem_note(
                paper_id="paper:missing",
                version_id="version:missing-v1",
                source_hash="f" * 64,
            ),
        ),),
    )
    with pytest.raises(ValueError, match="memberships.*registered"):
        graph.add_nodes((dangling,))
    assert dangling.primitive_id not in graph.node_ids(NodeKind.PRIMITIVE)


def test_direct_collision_requires_exact_scope_result_and_solution_relation() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    collision = assess_collision(problem, theorem, graph=collision_graph(problem, theorem))

    assert collision.severity is CollisionSeverity.DIRECT
    assert collision.exact_scope is True
    assert collision.exact_result_signature is True
    assert collision.exact_relation is EdgeRelation.OPEN_PROBLEM_SOLVED_BY


def test_direct_solution_relation_cannot_be_borrowed_by_another_record_in_same_paper() -> None:
    problem = original_problem()
    matching, _matching_note = resolution_theorem(
        theorem_scope=general_scope(), theorem_result=result()
    )
    other, _other_note = same_paper_theorem_with_id("theorem:resolution-other")
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, matching, other))
    graph.add_edges((GraphEdge(
        problem.problem_id,
        NodeKind.OPEN_PROBLEM,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        matching.paper_id,
        NodeKind.PAPER,
        (bound_solution_evidence(problem, matching),),
    ),))

    assert assess_collision(problem, matching, graph=graph).severity is CollisionSeverity.DIRECT
    assert assess_collision(problem, other, graph=graph).severity is not CollisionSeverity.DIRECT


def test_collision_keeps_only_solution_evidence_bound_to_the_assessed_records() -> None:
    problem = original_problem()
    matching, _matching_note = resolution_theorem(
        theorem_scope=general_scope(), theorem_result=result()
    )
    other, _other_note = same_paper_theorem_with_id("theorem:resolution-corroborating-other")
    matching_evidence = bound_solution_evidence(problem, matching)
    other_evidence = bound_solution_evidence(problem, other)
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, matching, other))
    graph.add_edges((GraphEdge(
        problem.problem_id,
        NodeKind.OPEN_PROBLEM,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        matching.paper_id,
        NodeKind.PAPER,
        (other_evidence, matching_evidence),
    ),))

    collision = assess_collision(problem, matching, graph=graph)

    assert collision.severity is CollisionSeverity.DIRECT
    assert collision.evidence == (matching_evidence,)
    assert other_evidence.identity not in {item.identity for item in collision.evidence}


def test_exact_primitive_overlap_without_solution_edge_is_never_direct() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    primitive_id = "primitive:exact-overlap-only"
    phrase = "exact overlap witness"
    years = (2026,)
    status = PrimitiveStatus.ACTIVE
    primitive = NoveltyPrimitive(
        primitive_id,
        phrase,
        (problem.paper_id,),
        (theorem.theorem_id,),
        years,
        status,
        (
            primitive_membership_evidence(
                primitive_id, phrase, problem.paper_id, NodeKind.PAPER, years, status
            ),
            primitive_membership_evidence(
                primitive_id, phrase, theorem.theorem_id, NodeKind.THEOREM, years, status,
                note=_note,
            ),
        ),
    )
    graph.add_nodes((primitive,))

    collision = assess_collision(problem, theorem, graph=graph, primitives=(primitive,))

    assert collision.severity is CollisionSeverity.STRONG
    assert collision.exact_relation is None


def test_token_or_cooccurrence_alone_is_capped_at_weak() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(
        theorem_scope=scope(constraints=("graph databases",)),
        theorem_result=result(complexity_class="LOGSPACE"),
    )
    empty = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))

    collision = assess_collision(problem, theorem, graph=empty, token_overlap=True)
    assert collision.severity is CollisionSeverity.WEAK
    assert collision.reasons == (
        "Only token or co-occurrence overlap is established; severity is conservatively capped.",
    )


def test_structured_scope_overlap_takes_precedence_over_token_overlap() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(
        theorem_scope=general_scope(),
        theorem_result=result(complexity_class="LOGSPACE"),
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))

    collision = assess_collision(problem, theorem, graph=graph, token_overlap=True)

    assert collision.severity is CollisionSeverity.PARTIAL
    assert collision.reasons == (
        "A structured component overlaps, but no verified exact resolving relation is present.",
    )


def test_substantial_structured_overlap_with_verified_primitive_is_strong_not_direct() -> None:
    problem = original_problem()
    narrow_scope = scope(constraints=("relational instances", "acyclic queries"))
    theorem, _note = resolution_theorem(theorem_scope=narrow_scope, theorem_result=result())
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    primitive = NoveltyPrimitive(
        "primitive:bounded-decomposition",
        "bounded decomposition witness",
        (problem.paper_id,),
        (theorem.theorem_id,),
        (2025, 2026),
        PrimitiveStatus.ACTIVE,
        (
            primitive_membership_evidence(
                "primitive:bounded-decomposition",
                "bounded decomposition witness",
                problem.paper_id,
                NodeKind.PAPER,
                (2025, 2026),
                PrimitiveStatus.ACTIVE,
            ),
            primitive_membership_evidence(
                "primitive:bounded-decomposition",
                "bounded decomposition witness",
                theorem.theorem_id,
                NodeKind.THEOREM,
                (2025, 2026),
                PrimitiveStatus.ACTIVE,
                note=_note,
            ),
        ),
    )
    graph.add_nodes((primitive,))

    collision = assess_collision(problem, theorem, graph=graph, primitives=(primitive,))
    assert collision.severity is CollisionSeverity.STRONG


def test_unrelated_valid_graph_evidence_cannot_support_primitive_membership() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    unrelated = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )

    with pytest.raises(ValueError, match="primitive membership|structured claim"):
        NoveltyPrimitive(
            "primitive:unsupported-membership",
            "unsupported membership witness",
            (problem.paper_id,),
            (theorem.theorem_id,),
            (2026,),
            PrimitiveStatus.ACTIVE,
            (unrelated,),
        )


def test_primitive_membership_note_must_belong_to_each_declared_member() -> None:
    problem = original_problem()
    theorem, theorem_note = resolution_theorem(
        theorem_scope=general_scope(), theorem_result=result()
    )

    with pytest.raises(ValueError, match="member paper|membership.*paper|paper.*membership"):
        NoveltyPrimitive(
            "primitive:wrong-paper-note",
            "wrong paper witness",
            (theorem.paper_id,),
            (),
            (2026,),
            PrimitiveStatus.ACTIVE,
            (primitive_membership_evidence(
                "primitive:wrong-paper-note",
                "wrong paper witness",
                theorem.paper_id,
                NodeKind.PAPER,
                (2026,),
                PrimitiveStatus.ACTIVE,
            ),),
        )

    theorem_primitive = NoveltyPrimitive(
        "primitive:wrong-theorem-note",
        "wrong theorem witness",
        (),
        (theorem.theorem_id,),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (primitive_membership_evidence(
            "primitive:wrong-theorem-note",
            "wrong theorem witness",
            theorem.theorem_id,
            NodeKind.THEOREM,
            (2026,),
            PrimitiveStatus.ACTIVE,
        ),),
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    with pytest.raises(ValueError, match="theorem.*paper|membership.*theorem"):
        graph.add_nodes((theorem_primitive,))

    valid_theorem_primitive = NoveltyPrimitive(
        "primitive:right-theorem-note",
        "right theorem witness",
        (),
        (theorem.theorem_id,),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (primitive_membership_evidence(
            "primitive:right-theorem-note",
            "right theorem witness",
            theorem.theorem_id,
            NodeKind.THEOREM,
            (2026,),
            PrimitiveStatus.ACTIVE,
            note=theorem_note,
        ),),
    )
    graph.add_nodes((valid_theorem_primitive,))


def test_collision_derives_complete_shared_primitives_and_rejects_omission() -> None:
    problem = original_problem()
    theorem, theorem_note = resolution_theorem(
        theorem_scope=general_scope(), theorem_result=result()
    )
    primitive = NoveltyPrimitive(
        "primitive:auto-derived-overlap",
        "auto derived overlap",
        (problem.paper_id,),
        (theorem.theorem_id,),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (
            primitive_membership_evidence(
                "primitive:auto-derived-overlap",
                "auto derived overlap",
                problem.paper_id,
                NodeKind.PAPER,
                (2026,),
                PrimitiveStatus.ACTIVE,
            ),
            primitive_membership_evidence(
                "primitive:auto-derived-overlap",
                "auto derived overlap",
                theorem.theorem_id,
                NodeKind.THEOREM,
                (2026,),
                PrimitiveStatus.ACTIVE,
                note=theorem_note,
            ),
        ),
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem, primitive))

    collision = assess_collision(problem, theorem, graph=graph)
    assert collision.severity is CollisionSeverity.STRONG
    assert collision.shared_primitive_ids == (primitive.primitive_id,)
    with pytest.raises(ValueError, match="complete.*primitive|primitive.*complete"):
        assess_collision(problem, theorem, graph=graph, primitives=())


def test_collision_rejects_shadow_primitive_record_with_registered_id() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    primitive_id = "primitive:shadow-record"
    phrase = "shadow record witness"
    years = (2026,)
    status = PrimitiveStatus.ACTIVE
    registered = NoveltyPrimitive(
        primitive_id,
        phrase,
        (problem.paper_id,),
        (),
        years,
        status,
        (primitive_membership_evidence(
            primitive_id, phrase, problem.paper_id, NodeKind.PAPER, years, status
        ),),
    )
    shadow = NoveltyPrimitive(
        primitive_id,
        phrase,
        (problem.paper_id,),
        (theorem.theorem_id,),
        years,
        status,
        (
            primitive_membership_evidence(
                primitive_id, phrase, problem.paper_id, NodeKind.PAPER, years, status
            ),
            primitive_membership_evidence(
                primitive_id, phrase, theorem.theorem_id, NodeKind.THEOREM, years, status
            ),
        ),
    )
    graph.add_nodes((registered,))

    with pytest.raises(ValueError, match="registered.*record|shadow primitive"):
        assess_collision(problem, theorem, graph=graph, primitives=(shadow,))


def test_collision_rejects_shadow_candidate_and_prior_graph_records() -> None:
    note = problem_note()
    registered_candidate = original_problem()
    shadow_candidate = validate_open_problem(
        replace(
            explicit_extraction(),
            paraphrase="The same supported problem is presented through a different caller-owned candidate record.",
        ),
        note,
    )
    registered_prior, _registered_note = resolution_theorem(
        theorem_scope=general_scope(),
        theorem_result=result(),
    )
    shadow_prior, _shadow_note = resolution_theorem(
        theorem_scope=scope(constraints=("graph databases",)),
        theorem_result=result(complexity_class="LOGSPACE"),
    )
    graph = EvidenceBackedGraph((
        SOURCE_METADATA,
        RESOLUTION_METADATA,
        registered_candidate,
        registered_prior,
    ))

    with pytest.raises(ValueError, match="registered.*record|shadow candidate"):
        assess_collision(shadow_candidate, registered_prior, graph=graph)
    with pytest.raises(ValueError, match="registered.*record|shadow prior"):
        assess_collision(registered_candidate, shadow_prior, graph=graph)


def test_partial_overlap_and_disjoint_records_are_not_overstated() -> None:
    problem = original_problem()
    wrong_result = result(complexity_class="LOGSPACE")
    partial, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=wrong_result)
    partial_graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, partial))
    assert assess_collision(problem, partial, graph=partial_graph).severity is CollisionSeverity.PARTIAL

    disjoint, _note = resolution_theorem(
        theorem_scope=scope(constraints=("graph databases",)),
        theorem_result=result(),
    )
    disjoint_graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, disjoint))
    assert assess_collision(problem, disjoint, graph=disjoint_graph).severity is CollisionSeverity.NONE


def test_novelty_primitives_normalize_concepts_without_making_novelty_claims() -> None:
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    primitive = NoveltyPrimitive(
        "primitive:canonical-witness",
        "  Canonical   Witness  ",
        (problem.paper_id,),
        (),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (primitive_membership_evidence(
            "primitive:canonical-witness",
            "canonical witness",
            problem.paper_id,
            NodeKind.PAPER,
            (2026,),
            PrimitiveStatus.ACTIVE,
        ),),
    )
    assert primitive.phrase == "canonical witness"

    with pytest.raises(ValueError, match="novelty claim|novel"):
        replace(primitive, phrase="novel canonical witness")
    with pytest.raises(ValueError, match="concise|phrase"):
        replace(primitive, phrase=" ".join(f"token{i}" for i in range(20)))
