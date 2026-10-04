"""Deterministic, typed, evidence-backed scientific graph primitives."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
import io
import json
from types import MappingProxyType
from typing import Iterable, Mapping

from .evidence import validate_evidence_membership
from .model import (
    EvidencePointer,
    EvidenceType,
)
from .problems import ValidatedOpenProblem
from .reading import NoteRecord, validate_note
from .serialization import freeze_json, scientific_hash
from .sources import VerifiedMetadata, canonical_paper_id, verify_metadata
from .theorems import TheoremResult, ValidatedTheorem, result_payload
from .versions import VersionFamily, VersionObservation, resolve_version_family


class NodeKind(str, Enum):
    PAPER = "PAPER"
    VERSION = "VERSION"
    THEOREM = "THEOREM"
    OPEN_PROBLEM = "OPEN_PROBLEM"
    PRIMITIVE = "PRIMITIVE"
    TOPIC = "TOPIC"


class EdgeRelation(str, Enum):
    CITES = "CITES"
    EXTENDS = "EXTENDS"
    GENERALIZES = "GENERALIZES"
    SPECIALIZES = "SPECIALIZES"
    REFINES = "REFINES"
    CONTRADICTS = "CONTRADICTS"
    SOLVES = "SOLVES"
    THEOREM_GENERALIZES = "THEOREM_GENERALIZES"
    OPEN_PROBLEM_SOLVED_BY = "OPEN_PROBLEM_SOLVED_BY"


_RELATION_KINDS: Mapping[EdgeRelation, tuple[NodeKind, NodeKind]] = MappingProxyType({
    EdgeRelation.CITES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.EXTENDS: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.GENERALIZES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.SPECIALIZES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.REFINES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.CONTRADICTS: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.SOLVES: (NodeKind.PAPER, NodeKind.OPEN_PROBLEM),
    EdgeRelation.THEOREM_GENERALIZES: (NodeKind.THEOREM, NodeKind.THEOREM),
    EdgeRelation.OPEN_PROBLEM_SOLVED_BY: (NodeKind.OPEN_PROBLEM, NodeKind.PAPER),
})
_INVERSES = {
    EdgeRelation.SOLVES: EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
    EdgeRelation.OPEN_PROBLEM_SOLVED_BY: EdgeRelation.SOLVES,
}


def _enum(value: object, enum_type: type[Enum], label: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the controlled taxonomy") from caught


def _canonical_id(value: object, prefix: str, label: str) -> str:
    if not isinstance(value, str) or not value.startswith(f"{prefix}:") or len(value) <= len(prefix) + 1:
        raise ValueError(f"{label} must be a canonical {prefix} ID")
    return value


def claim_for_graph_relation(
    source_id: str,
    source_kind: NodeKind,
    relation: EdgeRelation,
    target_id: str,
    target_kind: NodeKind,
    *,
    source_record_id: str | None = None,
    target_record_id: str | None = None,
    source_results: tuple[TheoremResult, ...] = (),
    target_results: tuple[TheoremResult, ...] = (),
) -> Mapping[str, object]:
    """Build the exact structured claim required by scientific relation evidence."""

    source_kind = _enum(source_kind, NodeKind, "source kind")
    target_kind = _enum(target_kind, NodeKind, "target kind")
    relation = _enum(relation, EdgeRelation, "edge relation")
    expected = _RELATION_KINDS[relation]
    if (source_kind, target_kind) != expected:
        raise ValueError(f"{relation.value} has incompatible endpoint kinds or direction")
    if source_record_id is None:
        source_record_id = source_id
    if target_record_id is None:
        target_record_id = target_id
    if not isinstance(source_record_id, str) or not isinstance(target_record_id, str):
        raise ValueError("graph relation record bindings must be canonical IDs")
    if not isinstance(source_results, tuple) or any(
        not isinstance(item, TheoremResult) for item in source_results
    ):
        raise ValueError("graph relation source results must be an immutable theorem-result tuple")
    if not isinstance(target_results, tuple) or any(
        not isinstance(item, TheoremResult) for item in target_results
    ):
        raise ValueError("graph relation target results must be an immutable theorem-result tuple")
    payload = freeze_json({
        "claim_type": "GRAPH_RELATION",
        "source_id": source_id,
        "source_kind": source_kind.value,
        "relation": relation.value,
        "target_id": target_id,
        "target_kind": target_kind.value,
        "source_record_id": source_record_id,
        "target_record_id": target_record_id,
        "source_results": tuple(result_payload(item) for item in source_results),
        "target_results": tuple(result_payload(item) for item in target_results),
    })
    assert isinstance(payload, Mapping)
    return payload


@dataclass(frozen=True, slots=True)
class GraphEvidence:
    pointer: EvidencePointer
    note: NoteRecord

    def __post_init__(self) -> None:
        if not isinstance(self.pointer, EvidencePointer) or not isinstance(self.note, NoteRecord):
            raise ValueError("graph evidence requires an EvidencePointer and its source NoteRecord")

    @property
    def identity(self) -> str:
        return scientific_hash(self.pointer)

    def validate_membership(self) -> None:
        validate_note(self.note)
        validate_evidence_membership(self.pointer, self.note)
        if not self.pointer.verified:
            raise ValueError("graph evidence must be verified")


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source_id: str
    source_kind: NodeKind
    relation: EdgeRelation
    target_id: str
    target_kind: NodeKind
    evidence: tuple[GraphEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", _enum(self.source_kind, NodeKind, "source kind"))
        object.__setattr__(self, "target_kind", _enum(self.target_kind, NodeKind, "target kind"))
        object.__setattr__(self, "relation", _enum(self.relation, EdgeRelation, "edge relation"))
        if not isinstance(self.source_id, str) or not isinstance(self.target_id, str):
            raise ValueError("graph endpoints must be canonical IDs")
        if self.source_id == self.target_id:
            raise ValueError("graph relations cannot be self-edges")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, GraphEvidence) for item in self.evidence
        ):
            raise ValueError("edge evidence must be an immutable tuple of exact note-backed graph evidence")
        identities = tuple(item.identity for item in self.evidence)
        if len(set(identities)) != len(identities):
            raise ValueError("edge evidence cannot contain duplicates")
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence, key=lambda item: item.identity)))

    @property
    def evidence_identity(self) -> tuple[str, ...]:
        return tuple(item.identity for item in self.evidence)

    @property
    def identity(self) -> tuple[object, ...]:
        return (
            self.source_kind.value,
            self.source_id,
            self.relation.value,
            self.target_kind.value,
            self.target_id,
            self.evidence_identity,
        )


@dataclass(frozen=True, slots=True)
class TopicRecord:
    topic_id: str
    label: str
    source_evidence: tuple[GraphEvidence, ...]

    def __post_init__(self) -> None:
        _canonical_id(self.topic_id, "topic", "topic_id")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("topic label must be nonempty")
        object.__setattr__(self, "label", " ".join(self.label.split()))
        if (
            not isinstance(self.source_evidence, tuple)
            or not self.source_evidence
            or any(not isinstance(evidence, GraphEvidence) for evidence in self.source_evidence)
        ):
            raise ValueError("topic record requires an immutable tuple of GraphEvidence source evidence")
        for evidence in self.source_evidence:
            evidence.validate_membership()
        identities = tuple(evidence.identity for evidence in self.source_evidence)
        if len(set(identities)) != len(identities):
            raise ValueError("topic source evidence cannot contain duplicates")
        object.__setattr__(
            self,
            "source_evidence",
            tuple(sorted(self.source_evidence, key=lambda evidence: evidence.identity)),
        )


@dataclass(frozen=True, slots=True)
class VersionRecordRef:
    family: VersionFamily
    version: VersionObservation


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: NodeKind
    record: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum(self.kind, NodeKind, "node kind"))


@dataclass(frozen=True, slots=True)
class GraphConservationReport:
    input_edges: int
    unique_edges: int
    duplicate_edges: int
    by_relation: Mapping[str, int]


def _validated_metadata(record: VerifiedMetadata) -> VerifiedMetadata:
    reproduced = verify_metadata(record.supporting_observations)
    if reproduced != record:
        raise ValueError("paper node must resolve to reproducible verified metadata")
    return record


def _node_for_record(record: object) -> tuple[GraphNode, ...]:
    if isinstance(record, GraphNode):
        expected = _node_for_record(record.record)
        if len(expected) != 1 or expected[0].node_id != record.node_id or expected[0].kind is not record.kind:
            raise ValueError("graph node ID/type does not resolve to its validated record")
        return (record,)
    if isinstance(record, VerifiedMetadata):
        validated = _validated_metadata(record)
        return (GraphNode(canonical_paper_id(validated), NodeKind.PAPER, validated),)
    if isinstance(record, VersionFamily):
        reproduced = resolve_version_family(record.metadata, record.versions, record.lineage)
        if reproduced != record:
            raise ValueError("version nodes require a reproducible validated version family")
        paper = GraphNode(record.paper_id, NodeKind.PAPER, record.metadata)
        versions = tuple(
            GraphNode(item.version_id, NodeKind.VERSION, VersionRecordRef(record, item))
            for item in record.versions
        )
        return (paper,) + versions
    if isinstance(record, VersionRecordRef):
        family = resolve_version_family(record.family.metadata, record.family.versions, record.family.lineage)
        if family != record.family or record.version not in family.versions:
            raise ValueError("version node is not an exact member of its validated family")
        return (GraphNode(record.version.version_id, NodeKind.VERSION, record),)
    if isinstance(record, ValidatedTheorem):
        return (GraphNode(record.theorem_id, NodeKind.THEOREM, record),)
    if isinstance(record, ValidatedOpenProblem):
        return (GraphNode(record.problem_id, NodeKind.OPEN_PROBLEM, record),)
    if isinstance(record, TopicRecord):
        return (GraphNode(record.topic_id, NodeKind.TOPIC, record),)
    # Local import avoids a graph/collision import cycle.
    from .collision import NoveltyPrimitive
    if isinstance(record, NoveltyPrimitive):
        return (GraphNode(record.primitive_id, NodeKind.PRIMITIVE, record),)
    raise ValueError(f"unsupported or unvalidated graph node record: {type(record).__name__}")


_GRAPH_CLAIM_KEYS = frozenset({
    "claim_type",
    "source_id",
    "source_kind",
    "relation",
    "target_id",
    "target_kind",
    "source_record_id",
    "target_record_id",
    "source_results",
    "target_results",
})


class EvidenceBackedGraph:
    """A closed-world graph over validated records and exact evidence members."""

    def __init__(self, nodes: Iterable[object] = (), edges: Iterable[GraphEdge] = ()) -> None:
        self._nodes: dict[tuple[NodeKind, str], GraphNode] = {}
        self._edges: dict[tuple[object, ...], GraphEdge] = {}
        self._input_edges = 0
        self._duplicate_edges = 0
        self.add_nodes(nodes)
        self.add_edges(edges)

    def add_nodes(self, records: Iterable[object]) -> EvidenceBackedGraph:
        expanded: list[GraphNode] = []
        for record in records:
            expanded.extend(_node_for_record(record))
        prospective = dict(self._nodes)
        for node in expanded:
            key = (node.kind, node.node_id)
            existing = prospective.get(key)
            if existing is not None and existing.record != node.record:
                raise ValueError("conflicting duplicate node records are not allowed")
            if any(identifier == node.node_id and kind is not node.kind for kind, identifier in prospective):
                raise ValueError("node ID cannot resolve to conflicting node types")
            prospective[key] = node
        self._validate_primitive_memberships(prospective)
        self._nodes = prospective
        return self

    def _validate_primitive_memberships(
        self,
        nodes: Mapping[tuple[NodeKind, str], GraphNode] | None = None,
    ) -> None:
        from .collision import NoveltyPrimitive
        records = self._nodes if nodes is None else nodes
        paper_ids = {identifier for kind, identifier in records if kind is NodeKind.PAPER}
        theorem_ids = {identifier for kind, identifier in records if kind is NodeKind.THEOREM}
        for node in records.values():
            if not isinstance(node.record, NoveltyPrimitive):
                continue
            missing_papers = set(node.record.paper_ids) - paper_ids
            missing_theorems = set(node.record.theorem_ids) - theorem_ids
            if missing_papers or missing_theorems:
                raise ValueError("novelty primitive memberships must resolve to registered paper/theorem nodes")
            theorem_records = {
                identifier: records[(NodeKind.THEOREM, identifier)].record
                for identifier in node.record.theorem_ids
            }
            for evidence in node.record.source_evidence:
                claim = evidence.pointer.claim
                member_id = claim.get("member_id") if isinstance(claim, Mapping) else None
                member_kind = claim.get("member_kind") if isinstance(claim, Mapping) else None
                if member_kind == NodeKind.PAPER.value:
                    if evidence.note.paper_id != member_id:
                        raise ValueError("primitive membership note must belong to the declared member paper")
                elif member_kind == NodeKind.THEOREM.value:
                    theorem = theorem_records.get(member_id)
                    if not isinstance(theorem, ValidatedTheorem) or (
                        evidence.note.paper_id != theorem.paper_id
                        or evidence.note.version_id != theorem.version_id
                    ):
                        raise ValueError("primitive membership for a theorem must use that theorem's paper/version note")

    @staticmethod
    def _result_claims(record: object) -> tuple[Mapping[str, object], ...]:
        if isinstance(record, ValidatedTheorem):
            results = record.results
        elif isinstance(record, ValidatedOpenProblem):
            results = (record.requested_result,)
        else:
            results = ()
        return tuple(freeze_json(result_payload(item)) for item in results)

    def _bound_record(
        self,
        relation: EdgeRelation,
        *,
        role: str,
        endpoint_id: str,
        record_id: str,
    ) -> object:
        if relation is EdgeRelation.OPEN_PROBLEM_SOLVED_BY:
            expected_kind = NodeKind.OPEN_PROBLEM if role == "source" else NodeKind.THEOREM
        elif relation is EdgeRelation.SOLVES:
            expected_kind = NodeKind.THEOREM if role == "source" else NodeKind.OPEN_PROBLEM
        elif relation is EdgeRelation.THEOREM_GENERALIZES:
            expected_kind = NodeKind.THEOREM
        else:
            expected_kind = NodeKind.PAPER

        node = self._nodes.get((expected_kind, record_id))
        if node is None:
            raise ValueError("graph relation structured claim does not bind a registered scientific record")
        if expected_kind in {NodeKind.OPEN_PROBLEM, NodeKind.THEOREM}:
            record_endpoint = (
                record_id if relation is EdgeRelation.THEOREM_GENERALIZES
                else node.record.paper_id
                if (relation, role) in {
                    (EdgeRelation.OPEN_PROBLEM_SOLVED_BY, "target"),
                    (EdgeRelation.SOLVES, "source"),
                }
                else record_id
            )
            if record_endpoint != endpoint_id:
                raise ValueError("graph relation record binding does not match its typed endpoint")
        elif record_id != endpoint_id:
            raise ValueError("paper relation record binding must equal its typed endpoint")
        return node.record

    def _validate_relation_claim(self, edge: GraphEdge, evidence: GraphEvidence) -> None:
        claim = evidence.pointer.claim
        if not isinstance(claim, Mapping) or set(claim) != _GRAPH_CLAIM_KEYS:
            raise ValueError("edge evidence requires an exact structured graph relation claim")
        if claim["claim_type"] != "GRAPH_RELATION":
            raise ValueError("edge evidence claim_type must be GRAPH_RELATION")
        try:
            claim_relation = EdgeRelation(claim["relation"])
            source_kind = NodeKind(claim["source_kind"])
            target_kind = NodeKind(claim["target_kind"])
        except (KeyError, TypeError, ValueError) as caught:
            raise ValueError("edge evidence structured relation claim is malformed") from caught
        direct = (
            claim["source_id"], source_kind, claim_relation, claim["target_id"], target_kind
        ) == (
            edge.source_id, edge.source_kind, edge.relation, edge.target_id, edge.target_kind
        )
        inverse = _INVERSES.get(edge.relation)
        reversed_orientation = (
            claim["source_id"], source_kind, claim_relation, claim["target_id"], target_kind
        ) == (
            edge.target_id, edge.target_kind, inverse, edge.source_id, edge.source_kind
        )
        if not direct and not reversed_orientation:
            raise ValueError("edge evidence structured relation claim is not compatible with the typed edge")

        source_record_id = claim["source_record_id"]
        target_record_id = claim["target_record_id"]
        if not isinstance(source_record_id, str) or not isinstance(target_record_id, str):
            raise ValueError("graph relation claim record IDs must be strings")
        source_record = self._bound_record(
            claim_relation,
            role="source",
            endpoint_id=claim["source_id"],
            record_id=source_record_id,
        )
        target_record = self._bound_record(
            claim_relation,
            role="target",
            endpoint_id=claim["target_id"],
            record_id=target_record_id,
        )
        if claim["source_results"] != self._result_claims(source_record):
            raise ValueError("graph relation source results do not match the exact bound record")
        if claim["target_results"] != self._result_claims(target_record):
            raise ValueError("graph relation target results do not match the exact bound record")

        if isinstance(source_record, (ValidatedTheorem, ValidatedOpenProblem)):
            source_paper_id = source_record.paper_id
            source_version_id = source_record.version_id
        else:
            source_paper_id = claim["source_id"]
            source_version_id = None
        if evidence.note.paper_id != source_paper_id or (
            source_version_id is not None and evidence.note.version_id != source_version_id
        ):
            raise ValueError("scientific edge evidence must use the bound endpoint source paper/version note")

    def _validate_edge(self, edge: GraphEdge) -> None:
        if not isinstance(edge, GraphEdge):
            raise ValueError("edges must be GraphEdge records")
        expected_kinds = _RELATION_KINDS[edge.relation]
        if (edge.source_kind, edge.target_kind) != expected_kinds:
            raise ValueError(f"{edge.relation.value} has the wrong semantic direction or endpoint kinds")
        for key in ((edge.source_kind, edge.source_id), (edge.target_kind, edge.target_id)):
            if key not in self._nodes:
                raise ValueError("graph edge has a dangling endpoint not registered as the stated node type")
        if not edge.evidence:
            raise ValueError("scientific graph edges require exact verified evidence")
        for item in edge.evidence:
            item.validate_membership()
            if item.pointer.evidence_type is not EvidenceType.GRAPH_RELATION:
                raise ValueError("scientific relation evidence must use GRAPH_RELATION evidence")
            self._validate_relation_claim(edge, item)

    @staticmethod
    def _validate_inverse_pairs(edges: Iterable[GraphEdge]) -> None:
        edge_list = tuple(edges)
        by_orientation: dict[tuple[str, EdgeRelation, str], set[str]] = {}
        for item in edge_list:
            by_orientation.setdefault(
                (item.source_id, item.relation, item.target_id), set()
            ).update(item.evidence_identity)
        checked: set[tuple[tuple[str, EdgeRelation, str], tuple[str, EdgeRelation, str]]] = set()
        for orientation, evidence_ids in by_orientation.items():
            source_id, relation, target_id = orientation
            inverse = _INVERSES.get(relation)
            if inverse is None:
                continue
            paired_orientation = (target_id, inverse, source_id)
            pair_key = tuple(sorted((orientation, paired_orientation), key=lambda item: (
                item[0], item[1].value, item[2]
            )))
            if pair_key in checked:
                continue
            checked.add(pair_key)
            paired_evidence_ids = by_orientation.get(paired_orientation)
            if paired_evidence_ids is not None and paired_evidence_ids != evidence_ids:
                raise ValueError("explicit inverse solution edges must carry the same evidence identity set")

    def add_edges(self, edges: Iterable[GraphEdge]) -> EvidenceBackedGraph:
        supplied = tuple(edges)
        for edge in supplied:
            self._validate_edge(edge)
        prospective = dict(self._edges)
        duplicates = 0
        for edge in supplied:
            existing = prospective.get(edge.identity)
            if existing is not None:
                if existing != edge:
                    raise ValueError("conflicting duplicate edges are not allowed")
                duplicates += 1
            else:
                prospective[edge.identity] = edge
        self._validate_inverse_pairs(prospective.values())
        self._edges = prospective
        self._input_edges += len(supplied)
        self._duplicate_edges += duplicates
        return self

    def validate_graph(self) -> EvidenceBackedGraph:
        for node in self._nodes.values():
            _node_for_record(node)
        self._validate_primitive_memberships()
        for edge in self._edges.values():
            self._validate_edge(edge)
        self._validate_inverse_pairs(self._edges.values())
        return self

    @property
    def nodes(self) -> tuple[GraphNode, ...]:
        return tuple(sorted(self._nodes.values(), key=lambda item: (item.kind.value, item.node_id)))

    @property
    def edges(self) -> tuple[GraphEdge, ...]:
        return tuple(sorted(self._edges.values(), key=lambda item: item.identity))

    def node_ids(self, kind: NodeKind | None = None) -> tuple[str, ...]:
        if kind is not None:
            kind = _enum(kind, NodeKind, "node kind")
        return tuple(sorted(
            node.node_id for node in self._nodes.values() if kind is None or node.kind is kind
        ))

    @property
    def typed_adjacency(self) -> Mapping[tuple[NodeKind, str], tuple[tuple[EdgeRelation, NodeKind, str], ...]]:
        result: dict[tuple[NodeKind, str], list[tuple[EdgeRelation, NodeKind, str]]] = {
            key: [] for key in self._nodes
        }
        for edge in self.edges:
            result[(edge.source_kind, edge.source_id)].append(
                (edge.relation, edge.target_kind, edge.target_id)
            )
        return MappingProxyType({key: tuple(sorted(value, key=lambda item: (
            item[0].value, item[1].value, item[2]
        ))) for key, value in sorted(result.items(), key=lambda item: (item[0][0].value, item[0][1]))})

    def adjacent(
        self,
        node_id: str,
        *,
        relation: EdgeRelation | None = None,
        target_kind: NodeKind | None = None,
    ) -> tuple[str, ...]:
        if relation is not None:
            relation = _enum(relation, EdgeRelation, "edge relation")
        if target_kind is not None:
            target_kind = _enum(target_kind, NodeKind, "target kind")
        return tuple(sorted({
            edge.target_id for edge in self._edges.values()
            if edge.source_id == node_id
            and (relation is None or edge.relation is relation)
            and (target_kind is None or edge.target_kind is target_kind)
        }))

    def _traverse(self, node_id: str, *, reverse: bool) -> tuple[str, ...]:
        if node_id not in {item.node_id for item in self._nodes.values()}:
            raise ValueError("traversal root is not a registered node")
        seen = {node_id}
        pending = [node_id]
        while pending:
            current = pending.pop(0)
            neighbors = {
                (edge.source_id if reverse else edge.target_id)
                for edge in self._edges.values()
                if (edge.target_id if reverse else edge.source_id) == current
            }
            for neighbor in sorted(neighbors):
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        seen.remove(node_id)
        return tuple(sorted(seen))

    def descendants(self, node_id: str) -> tuple[str, ...]:
        return self._traverse(node_id, reverse=False)

    def ancestors(self, node_id: str) -> tuple[str, ...]:
        return self._traverse(node_id, reverse=True)

    def conservation_report(self) -> GraphConservationReport:
        counts = {relation.value: 0 for relation in EdgeRelation}
        for edge in self._edges.values():
            counts[edge.relation.value] += 1
        return GraphConservationReport(
            self._input_edges,
            len(self._edges),
            self._duplicate_edges,
            MappingProxyType(counts),
        )

    def to_json_rows(self) -> tuple[dict[str, object], ...]:
        rows: list[dict[str, object]] = []
        for node in self.nodes:
            rows.append({
                "record_type": "NODE",
                "node_id": node.node_id,
                "node_kind": node.kind.value,
                "source_id": "",
                "source_kind": "",
                "relation": "",
                "target_id": "",
                "target_kind": "",
                "evidence_ids": "",
            })
        for edge in self.edges:
            rows.append({
                "record_type": "EDGE",
                "node_id": "",
                "node_kind": "",
                "source_id": edge.source_id,
                "source_kind": edge.source_kind.value,
                "relation": edge.relation.value,
                "target_id": edge.target_id,
                "target_kind": edge.target_kind.value,
                "evidence_ids": ";".join(edge.evidence_identity),
            })
        return tuple(rows)

    def to_csv_rows(self) -> tuple[dict[str, str], ...]:
        return tuple({key: str(value) for key, value in row.items()} for row in self.to_json_rows())

    def to_json_text(self) -> str:
        return json.dumps(self.to_json_rows(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def to_csv_text(self) -> str:
        rows = self.to_csv_rows()
        columns = (
            "record_type", "node_id", "node_kind", "source_id", "source_kind",
            "relation", "target_id", "target_kind", "evidence_ids",
        )
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
