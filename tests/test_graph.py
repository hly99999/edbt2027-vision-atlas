from dataclasses import replace

import pytest

import db_theory_atlas.graph as graph_module

from db_theory_atlas.graph import (
    EdgeRelation,
    EvidenceBackedGraph,
    GraphEdge,
    GraphEvidence,
    NodeKind,
    TopicRecord,
    claim_for_graph_relation,
)
from db_theory_atlas.model import (
    EvidenceType,
    OpenProblemRecord,
    OpenStatus,
    ReadDepth,
    TheoremRecord,
)
from test_model import paper as legacy_paper_record
from test_problems import (
    RESOLUTION_METADATA,
    SOURCE_METADATA,
    general_scope,
    original_problem,
    problem_note,
    resolution_theorem,
    result,
    metadata,
)
from db_theory_atlas.sources import canonical_paper_id
from db_theory_atlas.serialization import freeze_json
from test_theorems import pointer


def relation_evidence(source_id: str, relation: EdgeRelation, target_id: str, *, note=None):
    source_kind = NodeKind(source_id.split(":", 1)[0].upper().replace("PROBLEM", "OPEN_PROBLEM"))
    target_kind = NodeKind(target_id.split(":", 1)[0].upper().replace("PROBLEM", "OPEN_PROBLEM"))
    problem = original_problem()
    theorem, theorem_note = resolution_theorem(
        theorem_scope=general_scope(), theorem_result=result()
    )
    note = note or (theorem_note if relation is EdgeRelation.SOLVES else problem_note())
    binding = {}
    if relation is EdgeRelation.OPEN_PROBLEM_SOLVED_BY:
        binding = {
            "source_record_id": problem.problem_id,
            "target_record_id": theorem.theorem_id,
            "source_results": (problem.requested_result,),
            "target_results": theorem.results,
        }
    elif relation is EdgeRelation.SOLVES:
        binding = {
            "source_record_id": theorem.theorem_id,
            "target_record_id": problem.problem_id,
            "source_results": theorem.results,
            "target_results": (problem.requested_result,),
        }
    evidence = pointer(
        EvidenceType.GRAPH_RELATION,
        9,
        "Limitations",
        "Within the stated scope, the related-work discussion records the exact scientific relation.",
        claim=claim_for_graph_relation(
            source_id,
            source_kind,
            relation,
            target_id,
            target_kind,
            **binding,
        ),
        paper_id=note.paper_id,
        version_id=note.version_id,
        source_hash=note.source_hash,
    )
    note = replace(note, evidence=note.evidence + (evidence,))
    return GraphEvidence(evidence, note)


def citing_relation_evidence(source_id: str, target_id: str):
    note = problem_note()
    if note.paper_id != source_id:
        _theorem, note = resolution_theorem(
            theorem_scope=general_scope(),
            theorem_result=result(),
        )
    return relation_evidence(source_id, EdgeRelation.CITES, target_id, note=note)


def graph_records():
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    return problem, theorem


def test_node_kind_and_edge_relation_are_exact_controlled_taxonomies() -> None:
    assert {item.value for item in NodeKind} == {
        "PAPER", "VERSION", "THEOREM", "OPEN_PROBLEM", "PRIMITIVE", "TOPIC"
    }


def test_topic_record_validates_deduplicates_and_canonicalizes_graph_evidence() -> None:
    problem, theorem = graph_records()
    first = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )
    second_pointer = replace(
        first.pointer,
        paraphrase="Within the stated scope, a distinct passage supports the same controlled topic.",
    )
    second = GraphEvidence(
        second_pointer,
        replace(first.note, evidence=first.note.evidence + (second_pointer,)),
    )

    with pytest.raises(ValueError, match="GraphEvidence|topic.*evidence"):
        TopicRecord("topic:invalid-evidence", "Invalid evidence", (object(),))
    with pytest.raises(ValueError, match="duplicate"):
        TopicRecord("topic:duplicate-evidence", "Duplicate evidence", (first, first))

    forward = TopicRecord("topic:canonical-order", "Canonical order", (first, second))
    reverse = TopicRecord("topic:canonical-order", "Canonical order", (second, first))
    expected = tuple(sorted((first.identity, second.identity)))
    assert tuple(item.identity for item in forward.source_evidence) == expected
    assert tuple(item.identity for item in reverse.source_evidence) == expected


def test_task6_public_exports_preserve_legacy_graph_edge_name() -> None:
    import db_theory_atlas as public

    assert public.NodeKind is NodeKind
    assert public.EdgeRelation is EdgeRelation
    assert public.EvidenceGraphEdge is GraphEdge
    assert public.EvidenceBackedGraph is EvidenceBackedGraph
    assert {item.value for item in EdgeRelation} == {
        "CITES", "EXTENDS", "GENERALIZES", "SPECIALIZES", "REFINES",
        "CONTRADICTS", "SOLVES", "THEOREM_GENERALIZES", "OPEN_PROBLEM_SOLVED_BY",
    }


def test_rejects_dangling_nodes_wrong_direction_and_evidenceless_strong_edges() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph()
    graph.add_nodes((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    evidence = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )

    with pytest.raises(ValueError, match="dangling|registered"):
        graph.add_edges((GraphEdge(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            "paper:missing",
            NodeKind.PAPER,
            (evidence,),
        ),))
    with pytest.raises(ValueError, match="direction|OPEN_PROBLEM_SOLVED_BY"):
        graph.add_edges((GraphEdge(
            theorem.paper_id,
            NodeKind.PAPER,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            (evidence,),
        ),))
    with pytest.raises(ValueError, match="evidence"):
        graph.add_edges((GraphEdge(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            theorem.paper_id,
            NodeKind.PAPER,
            (),
        ),))


def test_exact_note_membership_and_structured_relation_claim_are_required() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    member = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )
    altered = GraphEvidence(replace(member.pointer, paraphrase="Within the scope, altered evidence."), member.note)
    with pytest.raises(ValueError, match="exact member"):
        graph.add_edges((GraphEdge(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            theorem.paper_id,
            NodeKind.PAPER,
            (altered,),
        ),))


def test_graph_relation_claim_type_cannot_be_relabelled() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    member = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )
    forged_claim = dict(member.pointer.claim)
    forged_claim["claim_type"] = "UNRELATED_SCIENTIFIC_CLAIM"
    forged_pointer = replace(member.pointer, claim=freeze_json(forged_claim))
    forged = GraphEvidence(
        forged_pointer,
        replace(member.note, evidence=member.note.evidence + (forged_pointer,)),
    )

    with pytest.raises(ValueError, match="GRAPH_RELATION|structured graph relation"):
        graph.add_edges((GraphEdge(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            theorem.paper_id,
            NodeKind.PAPER,
            (forged,),
        ),))

    wrong_claim = relation_evidence(
        problem.paper_id,
        EdgeRelation.CITES,
        theorem.paper_id,
    )
    with pytest.raises(ValueError, match="structured.*claim|compatible"):
        graph.add_edges((GraphEdge(
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            theorem.paper_id,
            NodeKind.PAPER,
            (wrong_claim,),
        ),))


def test_duplicate_conservation_and_inverse_pair_evidence_identity() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    evidence = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )
    solved_by = GraphEdge(
        problem.problem_id,
        NodeKind.OPEN_PROBLEM,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
        NodeKind.PAPER,
        (evidence,),
    )
    graph.add_edges((solved_by, solved_by))
    report = graph.conservation_report()
    assert (report.input_edges, report.unique_edges, report.duplicate_edges) == (2, 1, 1)

    inverse_evidence = relation_evidence(
        theorem.paper_id,
        EdgeRelation.SOLVES,
        problem.problem_id,
    )
    with pytest.raises(ValueError, match="inverse.*same evidence|evidence.*inverse"):
        graph.add_edges((GraphEdge(
            theorem.paper_id,
            NodeKind.PAPER,
            EdgeRelation.SOLVES,
            problem.problem_id,
            NodeKind.OPEN_PROBLEM,
            (inverse_evidence,),
        ),))


def test_inverse_pairs_compare_complete_corroborating_evidence_sets() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    first = relation_evidence(
        problem.problem_id,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        theorem.paper_id,
    )
    second_pointer = replace(
        first.pointer,
        paraphrase="Within the stated scope, a second exact passage corroborates the scientific relation.",
    )
    second_note = replace(first.note, evidence=first.note.evidence + (second_pointer,))
    second = GraphEvidence(second_pointer, second_note)
    graph.add_edges((
        GraphEdge(problem.problem_id, NodeKind.OPEN_PROBLEM, EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
                  theorem.paper_id, NodeKind.PAPER, (first,)),
        GraphEdge(problem.problem_id, NodeKind.OPEN_PROBLEM, EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
                  theorem.paper_id, NodeKind.PAPER, (second,)),
        GraphEdge(theorem.paper_id, NodeKind.PAPER, EdgeRelation.SOLVES,
                  problem.problem_id, NodeKind.OPEN_PROBLEM, (first,)),
        GraphEdge(theorem.paper_id, NodeKind.PAPER, EdgeRelation.SOLVES,
                  problem.problem_id, NodeKind.OPEN_PROBLEM, (second,)),
    ))
    assert graph.validate_graph() is graph


def test_citation_requires_exact_note_backed_evidence_and_serializes_deterministically() -> None:
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA))
    source_id = graph.node_ids(NodeKind.PAPER)[0]
    target_id = graph.node_ids(NodeKind.PAPER)[1]
    edge = GraphEdge(
        source_id,
        NodeKind.PAPER,
        EdgeRelation.CITES,
        target_id,
        NodeKind.PAPER,
        (citing_relation_evidence(source_id, target_id),),
    )
    graph.add_edges((edge,))

    assert graph.to_json_rows() == graph.to_json_rows()
    assert graph.to_csv_rows() == graph.to_csv_rows()
    assert graph.to_json_text() == graph.to_json_text()
    assert graph.to_csv_text() == graph.to_csv_text()
    assert graph.validate_graph() is graph



def test_citation_evidence_cannot_be_forged_with_a_bare_verified_boolean() -> None:
    assert not hasattr(graph_module, "CitationEvidence")


def test_citation_note_evidence_must_belong_to_the_citing_source_paper() -> None:
    problem, theorem = graph_records()
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem))
    target_note_evidence = relation_evidence(
        theorem.paper_id,
        EdgeRelation.CITES,
        problem.paper_id,
    )

    with pytest.raises(ValueError, match="citing source paper|source paper.*note"):
        graph.add_edges((GraphEdge(
            theorem.paper_id,
            NodeKind.PAPER,
            EdgeRelation.CITES,
            problem.paper_id,
            NodeKind.PAPER,
            (target_note_evidence,),
        ),))


def test_strong_scientific_edge_rejects_evidence_from_unrelated_third_paper() -> None:
    unrelated_metadata = metadata("Unrelated Third Paper", 2026)
    unrelated_note = problem_note(
        paper_id=canonical_paper_id(unrelated_metadata),
        version_id="version:unrelated-v1",
        source_hash="e" * 64,
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA))
    evidence = relation_evidence(
        graph.node_ids(NodeKind.PAPER)[0],
        EdgeRelation.EXTENDS,
        graph.node_ids(NodeKind.PAPER)[1],
        note=unrelated_note,
    )

    with pytest.raises(ValueError, match="endpoint.*paper|paper.*endpoint|source paper"):
        graph.add_edges((GraphEdge(
            graph.node_ids(NodeKind.PAPER)[0],
            NodeKind.PAPER,
            EdgeRelation.EXTENDS,
            graph.node_ids(NodeKind.PAPER)[1],
            NodeKind.PAPER,
            (evidence,),
        ),))


def test_graph_rejects_caller_constructible_legacy_scientific_records() -> None:
    paper = legacy_paper_record()
    problem = original_problem()
    theorem, _note = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    legacy_problem = OpenProblemRecord(
        problem.problem_id,
        problem.paper_id,
        problem.version_id,
        problem.paraphrase,
        OpenStatus.LIKELY_OPEN,
        (problem.evidence,),
    )
    legacy_theorem = TheoremRecord(
        theorem.theorem_id,
        theorem.paper_id,
        theorem.version_id,
        theorem.paraphrase,
        True,
        ReadDepth.DEEP_READ,
        (theorem.evidence,),
        authorization=theorem.authorization,
    )

    for record in (paper, paper.versions[0], legacy_problem, legacy_theorem):
        with pytest.raises(ValueError, match="unsupported or unvalidated"):
            EvidenceBackedGraph((record,))


def test_typed_adjacency_and_traversal_terminate_on_cycles() -> None:
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA))
    first, second = graph.node_ids(NodeKind.PAPER)
    forward = GraphEdge(
        first, NodeKind.PAPER, EdgeRelation.CITES, second, NodeKind.PAPER,
        (citing_relation_evidence(first, second),),
    )
    backward = GraphEdge(
        second, NodeKind.PAPER, EdgeRelation.CITES, first, NodeKind.PAPER,
        (citing_relation_evidence(second, first),),
    )
    graph.add_edges((backward, forward))

    assert graph.descendants(first) == (second,)
    assert graph.ancestors(first) == (second,)
    assert graph.adjacent(first, target_kind=NodeKind.PAPER) == (second,)
    assert graph.typed_adjacency[(NodeKind.PAPER, first)][0][0] is EdgeRelation.CITES
