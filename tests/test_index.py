from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from db_theory_atlas.collision import (
    NoveltyPrimitive,
    PrimitiveStatus,
    assess_collision,
)
from db_theory_atlas.graph import (
    EdgeRelation,
    EvidenceBackedGraph,
    GraphEdge,
    GraphEvidence,
    NodeKind,
    TopicRecord,
)
import db_theory_atlas.index as index_module
from db_theory_atlas.index import (
    FIELD_WEIGHTS,
    InvalidIndex,
    IndexRecord,
    AtlasIndex,
    QueryError,
    RecordNotFound,
    build_index,
    load_index,
    load_index_text,
)
from db_theory_atlas.model import OpenStatus
from db_theory_atlas.problems import validate_open_problem
from db_theory_atlas.ranking import rank_open_directions
from db_theory_atlas.sources import canonical_paper_id
from test_collision import (
    RESOLUTION_METADATA,
    SOURCE_METADATA,
    general_scope,
    primitive_membership_evidence,
    result,
    resolution_theorem,
)
from test_problems import explicit_extraction, original_problem, problem_note
from test_ranking import direction, score
from test_theorems import deep_note, extraction, validate
from test_graph import citing_relation_evidence


def atlas_index(*, reverse: bool = False, audited: bool = True):
    direction_seed = direction("minimal-db", score(), verified_open=audited)
    problem = direction_seed.problem
    theorem_note = deep_note()
    theorem = validate(extraction(theorem_note), theorem_note)
    prior, _ = resolution_theorem(theorem_scope=general_scope(), theorem_result=result())
    phrase = "minimal distinguishing database"
    primitive = NoveltyPrimitive(
        "primitive:minimal-distinguishing-database",
        phrase,
        (problem.paper_id,),
        (),
        (2026,),
        PrimitiveStatus.ACTIVE,
        (primitive_membership_evidence(
            "primitive:minimal-distinguishing-database",
            phrase,
            problem.paper_id,
            NodeKind.PAPER,
            (2026,),
            PrimitiveStatus.ACTIVE,
        ),),
    )
    topic = TopicRecord(
        "topic:arity-frontier",
        "Arity frontier",
        (GraphEvidence(problem.evidence, problem_note()),),
    )
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA, problem, theorem, prior, primitive, topic))
    collision = assess_collision(problem, prior, graph=graph, token_overlap=True)
    ranked = rank_open_directions((replace(direction_seed, collision=collision),))
    papers = (SOURCE_METADATA, RESOLUTION_METADATA)
    theorems = (theorem, prior)
    records = {
        "papers": tuple(reversed(papers)) if reverse else papers,
        "theorems": tuple(reversed(theorems)) if reverse else theorems,
        "open_problems": (problem,),
        "collisions": (collision,),
        "rankings": ranked,
        "primitives": (primitive,),
        "topics": (topic,),
        "graph": graph,
    }
    return build_index(**records)


def committed_index_repo(tmp_path: Path, monkeypatch, index=None) -> tuple[Path, str]:
    root = tmp_path / "repo"
    indexes = root / "indexes"
    indexes.mkdir(parents=True)
    text = (index or atlas_index()).to_json()
    path = indexes / "frontier-atlas.json"
    path.write_text(text, encoding="utf-8", newline="")
    manifest = {
        "schema_version": 1,
        "indexes": {
            "frontier-atlas": {
                "path": "indexes/frontier-atlas.json",
                "sha256": sha256(text.encode("utf-8")).hexdigest(),
            },
        },
    }
    (indexes / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setattr(index_module, "REPOSITORY_ROOT", root)
    monkeypatch.setattr(index_module, "INDEXES_ROOT", indexes)
    monkeypatch.setattr(index_module, "INDEX_MANIFEST_PATH", indexes / "manifest.json")
    return path, "frontier-atlas"


def test_build_and_serialization_are_deterministic_and_hash_checked() -> None:
    first = atlas_index()
    second = atlas_index(reverse=True)

    assert first.to_json() == second.to_json()
    assert first.scientific_hash == second.scientific_hash
    assert load_index_text(first.to_json()).to_json() == first.to_json()

    tampered = first.to_json().replace("minimal distinguishing database", "invented claim")
    with pytest.raises(InvalidIndex, match="hash|integrity"):
        load_index_text(tampered)


def test_search_uses_token_scores_field_weights_and_exact_filters() -> None:
    index = atlas_index()

    result = index.search("minimal distinguishing database")
    assert result[0].record_id == "primitive:minimal-distinguishing-database"
    assert result[0].score > 0
    assert index.search("homomorphism", record_type="theorem")[0].record_type == "THEOREM"
    assert index.search("homomorphism", record_type="theorem", year=1901) == ()

    with pytest.raises(QueryError, match="empty"):
        index.search("   ")
    with pytest.raises(QueryError, match="no indexed record"):
        index.search("unfindable-token-never-indexed")


def test_search_filter_matrix_and_field_weights_are_explicit() -> None:
    index = atlas_index()
    theorem_id = "theorem:resolution-2"

    filters = {
        "identifier": theorem_id,
        "record_type": "theorem",
        "year": 2026,
        "year_min": 2025,
        "year_max": 2026,
        "venue": "ICDT",
        "complexity": "PTIME",
        "taxonomy": "SET",
        "proof_technique": "DYNAMIC_PROGRAMMING",
    }
    assert index.search("relational", **filters)[0].record_id == theorem_id
    assert index.search("structured", collision_severity="PARTIAL")[0].record_type == "COLLISION"
    assert index.search("direction", ranking_category="HIGH_VALUE_FEASIBLE")[0].record_type == "RANKING"
    assert index.search("arity frontier", topic="topic:arity-frontier")[0].record_type == "TOPIC"
    assert index.search("original", status="VERIFIED")[0].record_type == "PAPER"
    assert FIELD_WEIGHTS == {
        "identifier": 12, "title": 8, "label": 8, "paraphrase": 7, "phrase": 7,
        "authors": 4, "venue": 4, "complexity": 5, "proof_technique": 4,
        "scope": 3, "reasons": 3, "taxonomy": 2, "other": 1,
    }


def test_exact_lookup_never_guesses_partial_ids() -> None:
    index = atlas_index()
    problem = original_problem()
    assert index.open(problem.problem_id)["problem_id"] == problem.problem_id
    with pytest.raises(RecordNotFound):
        index.open(problem.problem_id.removeprefix("problem:"))


def test_descendants_are_cycle_safe_and_apply_exact_relation_and_type_filters() -> None:
    index = atlas_index()
    root = original_problem().problem_id
    # The graph is valid and traversal of an isolated root is deterministic.
    assert index.descendants(root) == ()
    assert index.descendants(root, relation="SOLVES") == ()
    assert index.descendants(root, node_type="PAPER") == ()
    with pytest.raises(RecordNotFound):
        index.descendants("problem:missing")


def test_unresolved_includes_status_source_audit_and_ranking_category() -> None:
    index = atlas_index()
    rows = index.unresolved()
    assert rows
    assert rows[0]["status"] != OpenStatus.RESOLVED.value
    assert {"category", "status", "source", "audit_through_year"} <= rows[0].keys()
    assert rows[0]["category"]
    assert rows[0]["audit_through_year"] >= 2026
    assert rows[0]["source"]["source_hash"]


def test_unresolved_excludes_missing_ranking_and_incomplete_task5_audits() -> None:
    assert build_index(open_problems=(original_problem(),)).unresolved() == ()
    assert atlas_index(audited=False).unresolved() == ()


def test_build_index_recomputes_rankings_and_rejects_forged_outputs() -> None:
    seed = direction("canonical", score(), verified_open=True)
    generated = build_index(rankings=(seed,))
    payload = next(item.payload for item in generated.records if item.record_type == "RANKING")
    assert payload["category"] == "HIGH_VALUE_FEASIBLE"
    assert payload["top_50_eligible"] is True
    assert payload["recommended"] is True
    assert payload["rank"] == 1

    canonical = rank_open_directions((seed,))[0]
    for forged in (
        replace(canonical, category=canonical.category.__class__.HIGH_VALUE_HARD),
        replace(canonical, top_50_eligible=False),
        replace(canonical, recommended=False),
        replace(canonical, rank=99),
    ):
        with pytest.raises(ValueError, match="canonical|forged|ranking"):
            build_index(rankings=(forged,))


def test_rejects_unvalidated_records_instead_of_indexing_caller_claims() -> None:
    with pytest.raises(ValueError, match="unsupported|unvalidated"):
        build_index(papers=({"paper_id": "paper:invented", "title": "Invented"},))

    with pytest.raises((ValueError, InvalidIndex), match="validated|builder|loader"):
        IndexRecord(
            "paper:invented",
            "PAPER",
            {"title": "Invented"},
            {"title": "Invented"},
            {},
            "0" * 64,
        )


def test_indexed_payloads_are_deeply_immutable() -> None:
    record = atlas_index().open(original_problem().problem_id)
    with pytest.raises((AttributeError, TypeError)):
        record["scope"]["constraints"].append("caller-authored")


def test_loaded_graph_snapshot_rejects_wrong_endpoint_kinds_and_missing_inverses() -> None:
    nodes = (
        {"id": "paper:a", "kind": "PAPER"},
        {"id": "paper:b", "kind": "PAPER"},
        {"id": "problem:p", "kind": "OPEN_PROBLEM"},
    )
    with pytest.raises(InvalidIndex, match="endpoint kinds|direction"):
        AtlasIndex((), nodes, ({
            "source_id": "paper:a", "source_kind": "PAPER", "relation": "CITES",
            "target_id": "problem:p", "target_kind": "OPEN_PROBLEM",
        },))
    with pytest.raises(InvalidIndex, match="inverse"):
        AtlasIndex((), nodes, ({
            "source_id": "paper:a", "source_kind": "PAPER", "relation": "SOLVES",
            "target_id": "problem:p", "target_kind": "OPEN_PROBLEM",
        },))


@pytest.mark.parametrize("graph", [
    {"nodes": [{"kind": "PAPER"}], "edges": []},
    {"nodes": "not-a-list", "edges": []},
    {"nodes": [{"id": "paper:a", "kind": "PAPER"}], "edges": [{"source_id": "paper:a"}]},
])
def test_malformed_graph_shapes_are_always_wrapped_as_invalid_index(graph) -> None:
    payload = json.loads(build_index().to_json())
    payload["graph"] = graph
    payload["index_hash"] = "0" * 64
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(InvalidIndex):
        load_index_text(text)


def test_loader_trusts_only_manifest_allowlisted_repository_indexes(tmp_path, monkeypatch) -> None:
    path, name = committed_index_repo(tmp_path, monkeypatch)
    assert load_index(name).scientific_hash == atlas_index().scientific_hash
    assert load_index("indexes/frontier-atlas.json").scientific_hash == atlas_index().scientific_hash

    forged = path.parent / "forged.json"
    forged.write_text(build_index().to_json(), encoding="utf-8", newline="")
    outside = tmp_path / "outside.json"
    outside.write_text(atlas_index().to_json(), encoding="utf-8", newline="")
    for selector in (str(forged), "indexes/forged.json", str(outside), "../outside.json"):
        with pytest.raises(InvalidIndex, match="manifest|allowlist|committed|selector"):
            load_index(selector)


def test_manifest_hash_blocks_self_consistent_payload_substitution(tmp_path, monkeypatch) -> None:
    path, name = committed_index_repo(tmp_path, monkeypatch)
    path.write_text(build_index().to_json(), encoding="utf-8", newline="")
    with pytest.raises(InvalidIndex, match="SHA-256|hash|manifest"):
        load_index(name)


def test_descendants_terminate_on_a_validated_cycle() -> None:
    first = canonical_paper_id(SOURCE_METADATA)
    second = canonical_paper_id(RESOLUTION_METADATA)
    graph = EvidenceBackedGraph((SOURCE_METADATA, RESOLUTION_METADATA), (
        GraphEdge(first, NodeKind.PAPER, EdgeRelation.CITES, second, NodeKind.PAPER,
                  (citing_relation_evidence(first, second),)),
        GraphEdge(second, NodeKind.PAPER, EdgeRelation.CITES, first, NodeKind.PAPER,
                  (citing_relation_evidence(second, first),)),
    ))
    index = build_index(papers=(SOURCE_METADATA, RESOLUTION_METADATA), graph=graph)

    assert index.descendants(first) == (second,)
    assert index.descendants(first, relation="CITES", node_type="PAPER") == (second,)
