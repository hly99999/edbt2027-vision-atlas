"""Deterministic, integrity-checked static indexes for the Frontier Atlas."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import InitVar, dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
import json
from hashlib import sha256
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable, Mapping
import unicodedata

from .collision import CollisionRecord, NoveltyPrimitive
from .graph import EdgeRelation, EvidenceBackedGraph, NodeKind, TopicRecord
from .model import OpenStatus, PaperRecord
from .problems import ValidatedOpenProblem
from .ranking import RankedDirection, rank_open_directions
from .serialization import freeze_json, scientific_hash
from .sources import VerifiedMetadata, canonical_paper_id, verify_metadata
from .theorems import ValidatedTheorem


SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INDEXES_ROOT = REPOSITORY_ROOT / "indexes"
INDEX_MANIFEST_PATH = INDEXES_ROOT / "manifest.json"
INDEX_RECORD_TYPES = frozenset({
    "PAPER", "THEOREM", "OPEN_PROBLEM", "TOPIC", "COLLISION", "RANKING", "PRIMITIVE",
})
FIELD_WEIGHTS: Mapping[str, int] = MappingProxyType({
    "identifier": 12,
    "title": 8,
    "label": 8,
    "paraphrase": 7,
    "phrase": 7,
    "authors": 4,
    "venue": 4,
    "complexity": 5,
    "proof_technique": 4,
    "scope": 3,
    "reasons": 3,
    "taxonomy": 2,
    "other": 1,
})
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_INDEX_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")
_VALIDATED_INDEX_RECORD_TOKEN = object()
_RELATION_KINDS = {
    EdgeRelation.CITES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.EXTENDS: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.GENERALIZES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.SPECIALIZES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.REFINES: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.CONTRADICTS: (NodeKind.PAPER, NodeKind.PAPER),
    EdgeRelation.SOLVES: (NodeKind.PAPER, NodeKind.OPEN_PROBLEM),
    EdgeRelation.THEOREM_GENERALIZES: (NodeKind.THEOREM, NodeKind.THEOREM),
    EdgeRelation.OPEN_PROBLEM_SOLVED_BY: (NodeKind.OPEN_PROBLEM, NodeKind.PAPER),
}


class InvalidIndex(ValueError):
    """Raised when a serialized index is malformed or fails integrity checks."""


class QueryError(ValueError):
    """Raised for an empty or wholly unknown full-text query."""


class RecordNotFound(LookupError):
    """Raised for exact lookup/traversal of an unknown canonical ID."""


def tokenize(text: str) -> tuple[str, ...]:
    """Apply explicit Unicode NFKC/casefold tokenization."""

    if not isinstance(text, str):
        raise QueryError("query must be text")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(_TOKEN_RE.findall(normalized))


def _plain(value: object) -> object:
    # String-valued enums must be normalized before the primitive string case;
    # otherwise JSON emission silently changes their scientific identity.
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        items = [_plain(item) for item in value]
        if isinstance(value, (set, frozenset)):
            items.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return items
    # Fractions and similarly stable numeric objects are presentation-only.
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return f"{value.numerator}/{value.denominator}"
    raise TypeError(f"unsupported index payload value: {type(value).__name__}")


def _canonical_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized_exact(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold()


def _values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(str(item) for item in value)
    return (str(value),)


@dataclass(frozen=True, slots=True)
class IndexRecord:
    record_id: str
    record_type: str
    payload: Mapping[str, object]
    search_fields: Mapping[str, str]
    filters: Mapping[str, object]
    scientific_hash: str
    _validation_token: InitVar[object] = None

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _VALIDATED_INDEX_RECORD_TOKEN:
            raise InvalidIndex("IndexRecord can only be created by the validated builder or loader")
        if self.record_type not in INDEX_RECORD_TYPES:
            raise InvalidIndex("unsupported index record type")
        if not isinstance(self.record_id, str) or not self.record_id:
            raise InvalidIndex("index record ID must be nonempty")
        if not isinstance(self.payload, Mapping) or not isinstance(self.search_fields, Mapping):
            raise InvalidIndex("index record payload/search fields must be mappings")
        if not isinstance(self.filters, Mapping):
            raise InvalidIndex("index record filters must be a mapping")
        payload = freeze_json(self.payload)
        search_fields = freeze_json(self.search_fields)
        filters = freeze_json(self.filters)
        assert isinstance(payload, Mapping) and isinstance(search_fields, Mapping) and isinstance(filters, Mapping)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "search_fields", search_fields)
        object.__setattr__(self, "filters", filters)

    def as_serialized(self) -> dict[str, object]:
        body = {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "payload": _plain(self.payload),
            "search_fields": _plain(self.search_fields),
            "filters": _plain(self.filters),
        }
        return {**body, "scientific_hash": self.scientific_hash}


@dataclass(frozen=True, slots=True)
class SearchResult:
    record_id: str
    record_type: str
    score: Decimal
    record: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "score": format(self.score, ".6f"),
            "record": dict(self.record),
        }


def _record_hash(body: Mapping[str, object]) -> str:
    return scientific_hash(dict(body))


def _make_record(
    record_id: str,
    record_type: str,
    payload: Mapping[str, object],
    search_fields: Mapping[str, object],
    filters: Mapping[str, object],
) -> IndexRecord:
    normalized_fields = {
        key: " ".join(str(item) for item in _values(value))
        for key, value in search_fields.items()
        if value is not None and _values(value)
    }
    normalized_filters = _plain(dict(filters))
    assert isinstance(normalized_filters, dict)
    body = {
        "record_id": record_id,
        "record_type": record_type,
        "payload": dict(payload),
        "search_fields": normalized_fields,
        "filters": normalized_filters,
    }
    return IndexRecord(
        record_id,
        record_type,
        MappingProxyType(dict(payload)),
        MappingProxyType(normalized_fields),
        MappingProxyType(normalized_filters),
        _record_hash(body),
        _validation_token=_VALIDATED_INDEX_RECORD_TOKEN,
    )


def _scope_text(payload: Mapping[str, object]) -> str:
    scope = payload.get("scope", {})
    return _canonical_text(scope) if isinstance(scope, Mapping) else str(scope)


def _metadata_record(record: VerifiedMetadata | PaperRecord) -> IndexRecord:
    if isinstance(record, VerifiedMetadata):
        if verify_metadata(record.supporting_observations) != record:
            raise ValueError("unsupported or unvalidated paper metadata")
        record_id = canonical_paper_id(record)
    elif isinstance(record, PaperRecord):
        record_id = record.paper_id
    else:
        raise ValueError("unsupported or unvalidated paper record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    return _make_record(record_id, "PAPER", payload, {
        "identifier": record_id,
        "title": payload.get("title"),
        "authors": payload.get("authors"),
        "venue": payload.get("venue"),
        "other": payload.get("doi"),
    }, {
        "year": payload.get("year"),
        "venue": payload.get("venue"),
        "status": payload.get("status") or payload.get("full_text_status"),
    })


def _theorem_record(record: ValidatedTheorem, papers: Mapping[str, Mapping[str, object]]) -> IndexRecord:
    if not isinstance(record, ValidatedTheorem):
        raise ValueError("unsupported or unvalidated theorem record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    paper = papers.get(record.paper_id, {})
    techniques = payload.get("techniques", {})
    results = payload.get("results", [])
    proof_terms: list[str] = []
    if isinstance(techniques, Mapping):
        proof_terms.extend(_values(techniques.get("primary")))
        proof_terms.extend(_values(techniques.get("supporting")))
    complexity = [item.get("complexity_class") for item in results if isinstance(item, Mapping)]
    taxonomy = [item.get(key) for item in results if isinstance(item, Mapping) for key in ("direction", "measure", "question_type")]
    scope = payload.get("scope", {})
    if isinstance(scope, Mapping):
        taxonomy.append(scope.get("semantics"))
    return _make_record(record.theorem_id, "THEOREM", payload, {
        "identifier": record.theorem_id,
        "paraphrase": record.paraphrase,
        "scope": _scope_text(payload),
        "complexity": complexity,
        "proof_technique": proof_terms,
        "taxonomy": taxonomy,
    }, {
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "complexity": complexity,
        "taxonomy": taxonomy,
        "proof_technique": proof_terms,
    })


def _problem_record(
    record: ValidatedOpenProblem,
    papers: Mapping[str, Mapping[str, object]],
    categories: Mapping[str, str],
    unresolved_eligible: bool,
) -> IndexRecord:
    if not isinstance(record, ValidatedOpenProblem):
        raise ValueError("unsupported or unvalidated open-problem record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    paper = papers.get(record.paper_id, {})
    requested = payload.get("requested_result", {})
    complexity = requested.get("complexity_class") if isinstance(requested, Mapping) else None
    taxonomy = []
    if isinstance(requested, Mapping):
        taxonomy.extend(requested.get(key) for key in ("direction", "measure", "question_type"))
    taxonomy.append(payload.get("explicitness"))
    search = payload.get("followup_search")
    through_year = search.get("through_year") if isinstance(search, Mapping) else None
    return _make_record(record.problem_id, "OPEN_PROBLEM", payload, {
        "identifier": record.problem_id,
        "paraphrase": record.paraphrase,
        "scope": _scope_text(payload),
        "complexity": complexity,
        "taxonomy": taxonomy,
    }, {
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "status": record.status.value,
        "complexity": complexity,
        "taxonomy": taxonomy,
        "ranking_category": categories.get(record.problem_id),
        "audit_through_year": through_year,
        "unresolved_eligible": unresolved_eligible,
    })


def _topic_record(record: TopicRecord) -> IndexRecord:
    if not isinstance(record, TopicRecord):
        raise ValueError("unsupported or unvalidated topic record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    return _make_record(record.topic_id, "TOPIC", payload, {
        "identifier": record.topic_id, "label": record.label,
    }, {"topic": (record.topic_id, record.label)})


def _collision_id(record: CollisionRecord) -> str:
    return f"collision:{record.left_id}--{record.right_id}"


def _collision_record(record: CollisionRecord) -> IndexRecord:
    if not isinstance(record, CollisionRecord):
        raise ValueError("unsupported or unvalidated collision record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    record_id = _collision_id(record)
    return _make_record(record_id, "COLLISION", payload, {
        "identifier": (record_id, record.left_id, record.right_id),
        "reasons": record.reasons,
        "other": record.shared_primitive_ids,
    }, {"collision_severity": record.severity.value})


def _ranking_record(record: RankedDirection) -> IndexRecord:
    if not isinstance(record, RankedDirection):
        raise ValueError("unsupported or unvalidated ranking record")
    payload = _plain(record)
    assert isinstance(payload, dict)
    record_id = f"direction:{record.direction_id}"
    return _make_record(record_id, "RANKING", payload, {
        "identifier": (record_id, record.problem.problem_id),
        "title": record.title,
        "paraphrase": record.problem.paraphrase,
        "taxonomy": record.category.value if record.category else None,
    }, {
        "status": record.problem.status.value,
        "ranking_category": record.category.value if record.category else None,
        "collision_severity": record.collision.severity.value,
    })


def _primitive_record(record: NoveltyPrimitive) -> IndexRecord:
    if not isinstance(record, NoveltyPrimitive):
        raise ValueError("unsupported or unvalidated novelty primitive")
    payload = _plain(record)
    assert isinstance(payload, dict)
    return _make_record(record.primitive_id, "PRIMITIVE", payload, {
        "identifier": record.primitive_id,
        "phrase": record.phrase,
        "other": tuple(record.paper_ids) + tuple(record.theorem_ids),
    }, {"year": list(record.years), "status": record.status.value})


class AtlasIndex:
    """Closed, deterministic search view over already validated records."""

    def __init__(
        self,
        records: Iterable[IndexRecord],
        graph_nodes: Iterable[Mapping[str, str]] = (),
        graph_edges: Iterable[Mapping[str, str]] = (),
    ) -> None:
        try:
            supplied = tuple(records)
            if any(not isinstance(item, IndexRecord) for item in supplied):
                raise InvalidIndex("static index contains an unsupported record")
            identities = tuple((item.record_type, item.record_id) for item in supplied)
            if len(set(identities)) != len(identities):
                raise InvalidIndex("duplicate record ID/type in static index")
            self._records = tuple(sorted(supplied, key=lambda item: (item.record_type, item.record_id)))
            self._by_type_id = {(item.record_type, item.record_id): item for item in self._records}
            nodes = tuple(dict(item) for item in graph_nodes)
            edges = tuple(dict(item) for item in graph_edges)
            if any(set(item) != {"id", "kind"} for item in nodes):
                raise InvalidIndex("invalid static graph node structure")
            if any(set(item) != {
                "source_id", "source_kind", "relation", "target_id", "target_kind",
            } for item in edges):
                raise InvalidIndex("invalid static graph edge structure")
            if any(not all(isinstance(value, str) for value in item.values()) for item in nodes + edges):
                raise InvalidIndex("static graph values must be strings")
            self._nodes = tuple(sorted(nodes, key=lambda item: (item["kind"], item["id"])))
            self._edges = tuple(sorted(edges, key=lambda item: (
                item["source_id"], item["relation"], item["target_id"], item["target_kind"],
            )))
            node_ids = tuple(item["id"] for item in self._nodes)
            if len(set(node_ids)) != len(node_ids):
                raise InvalidIndex("static graph contains duplicate node IDs")
            edge_ids = tuple(
                (item["source_id"], item["relation"], item["target_id"], item["target_kind"])
                for item in self._edges
            )
            if len(set(edge_ids)) != len(edge_ids):
                raise InvalidIndex("static graph contains duplicate edges")
            node_id_set = set(node_ids)
            if any(edge["source_id"] not in node_id_set or edge["target_id"] not in node_id_set for edge in self._edges):
                raise InvalidIndex("static graph contains a dangling endpoint")
            self._validate_graph_values()
            self._scientific_hash = scientific_hash(self._body())
        except InvalidIndex:
            raise
        except (KeyError, TypeError, ValueError) as caught:
            raise InvalidIndex("malformed static index or graph") from caught

    def _validate_graph_values(self) -> None:
        try:
            node_kinds = {node["id"]: NodeKind(node["kind"]) for node in self._nodes}
            for node in self._nodes:
                NodeKind(node["kind"])
            for edge in self._edges:
                relation = EdgeRelation(edge["relation"])
                source_kind = NodeKind(edge["source_kind"])
                target_kind = NodeKind(edge["target_kind"])
                if (source_kind, target_kind) != _RELATION_KINDS[relation]:
                    raise InvalidIndex("static graph relation has incompatible endpoint kinds or direction")
                if node_kinds[edge["source_id"]] is not source_kind or node_kinds[edge["target_id"]] is not target_kind:
                    raise InvalidIndex("static graph endpoint kinds disagree with registered nodes")
            edge_keys = {
                (edge["source_id"], edge["relation"], edge["target_id"])
                for edge in self._edges
            }
            for edge in self._edges:
                relation = EdgeRelation(edge["relation"])
                if relation is EdgeRelation.SOLVES:
                    inverse = (edge["target_id"], EdgeRelation.OPEN_PROBLEM_SOLVED_BY.value, edge["source_id"])
                    if inverse not in edge_keys:
                        raise InvalidIndex("static graph SOLVES relation is missing its inverse")
                elif relation is EdgeRelation.OPEN_PROBLEM_SOLVED_BY:
                    inverse = (edge["target_id"], EdgeRelation.SOLVES.value, edge["source_id"])
                    if inverse not in edge_keys:
                        raise InvalidIndex("static graph OPEN_PROBLEM_SOLVED_BY relation is missing its inverse")
        except (KeyError, ValueError, TypeError) as caught:
            if isinstance(caught, InvalidIndex):
                raise
            raise InvalidIndex("static graph contains unsupported controlled values") from caught

    @property
    def records(self) -> tuple[IndexRecord, ...]:
        return self._records

    @property
    def scientific_hash(self) -> str:
        return self._scientific_hash

    def _body(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "field_weights": dict(FIELD_WEIGHTS),
            "records": [item.as_serialized() for item in self._records],
            "graph": {"nodes": list(self._nodes), "edges": list(self._edges)},
        }

    def to_json(self) -> str:
        payload = {**self._body(), "index_hash": self.scientific_hash}
        return _canonical_text(payload) + "\n"

    def write(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8", newline="")

    def _matches(self, record: IndexRecord, filters: Mapping[str, object]) -> bool:
        for key, requested in filters.items():
            if requested is None:
                continue
            if key == "record_type":
                if record.record_type != str(requested).upper():
                    return False
                continue
            if key == "identifier":
                if record.record_id != requested:
                    return False
                continue
            if key == "year_min":
                years = tuple(int(value) for value in _values(record.filters.get("year")) if str(value).isdigit())
                if not years or max(years) < int(requested):
                    return False
                continue
            if key == "year_max":
                years = tuple(int(value) for value in _values(record.filters.get("year")) if str(value).isdigit())
                if not years or min(years) > int(requested):
                    return False
                continue
            actual = record.filters.get(key)
            if key == "year":
                if str(requested) not in _values(actual):
                    return False
                continue
            requested_key = _normalized_exact(requested)
            if requested_key not in {_normalized_exact(value) for value in _values(actual)}:
                return False
        return True

    def search(self, query: str, **filters: object) -> tuple[SearchResult, ...]:
        terms = tokenize(query)
        if not terms:
            raise QueryError("empty query is not allowed")
        documents: dict[tuple[str, str], dict[str, Counter[str]]] = {}
        corpus_terms: set[str] = set()
        for record in self._records:
            field_terms = {name: Counter(tokenize(text)) for name, text in record.search_fields.items()}
            documents[(record.record_type, record.record_id)] = field_terms
            corpus_terms.update(token for counter in field_terms.values() for token in counter)
        if not any(term in corpus_terms for term in terms):
            raise QueryError("no indexed record contains any query token")
        selected = tuple(record for record in self._records if self._matches(record, filters))
        count = max(len(self._records), 1)
        document_frequency = {
            term: sum(
                1 for field_terms in documents.values()
                if any(term in counter for counter in field_terms.values())
            )
            for term in set(terms)
        }
        results: list[SearchResult] = []
        for record in selected:
            field_terms = documents[(record.record_type, record.record_id)]
            score = Decimal(0)
            for term in terms:
                weighted_tf = sum(
                    FIELD_WEIGHTS.get(field, FIELD_WEIGHTS["other"]) * counter[term]
                    for field, counter in field_terms.items()
                )
                if not weighted_tf:
                    continue
                # A rational BM25-like saturation avoids platform-dependent floating logs.
                inverse_df = Decimal(count + 1) / Decimal(document_frequency[term] + 1)
                saturation = Decimal(weighted_tf * 25) / Decimal(weighted_tf * 10 + 15)
                score += inverse_df * saturation
            if score:
                results.append(SearchResult(
                    record.record_id,
                    record.record_type,
                    score.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN),
                    record.payload,
                ))
        results.sort(key=lambda item: (-item.score, item.record_id))
        return tuple(results)

    def _exact(self, record_type: str, identifier: str) -> Mapping[str, object]:
        record = self._by_type_id.get((record_type, identifier))
        if record is None:
            raise RecordNotFound(f"{record_type.lower()} record not found: {identifier}")
        return record.payload

    def paper(self, identifier: str) -> Mapping[str, object]:
        return self._exact("PAPER", identifier)

    def theorem(self, identifier: str) -> Mapping[str, object]:
        return self._exact("THEOREM", identifier)

    def open(self, identifier: str) -> Mapping[str, object]:
        return self._exact("OPEN_PROBLEM", identifier)

    def topic(self, identifier: str) -> Mapping[str, object]:
        return self._exact("TOPIC", identifier)

    def collision(self, identifier: str, right_id: str | None = None) -> Mapping[str, object]:
        collision_id = f"collision:{identifier}--{right_id}" if right_id is not None else identifier
        return self._exact("COLLISION", collision_id)

    def descendants(
        self,
        identifier: str,
        *,
        relation: str | EdgeRelation | None = None,
        node_type: str | NodeKind | None = None,
    ) -> tuple[str, ...]:
        node_by_id = {item["id"]: item for item in self._nodes}
        if identifier not in node_by_id:
            raise RecordNotFound(f"graph node not found: {identifier}")
        relation_value = EdgeRelation(relation).value if relation is not None else None
        kind_value = NodeKind(node_type).value if node_type is not None else None
        seen = {identifier}
        pending = deque([identifier])
        while pending:
            current = pending.popleft()
            neighbors = sorted({
                edge["target_id"]
                for edge in self._edges
                if edge["source_id"] == current
                and (relation_value is None or edge["relation"] == relation_value)
            })
            for neighbor in neighbors:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        seen.remove(identifier)
        return tuple(sorted(
            item for item in seen
            if kind_value is None or node_by_id[item]["kind"] == kind_value
        ))

    def unresolved(self, *, category: str | None = None) -> tuple[dict[str, object], ...]:
        rows: list[dict[str, object]] = []
        for record in self._records:
            if record.record_type != "OPEN_PROBLEM" or record.filters.get("status") == OpenStatus.RESOLVED.value:
                continue
            ranking_category = record.filters.get("ranking_category")
            audit_year = record.filters.get("audit_through_year")
            evidence = record.payload.get("evidence")
            if (
                record.filters.get("unresolved_eligible") is not True
                or not isinstance(ranking_category, str)
                or not ranking_category
                or isinstance(audit_year, bool)
                or not isinstance(audit_year, int)
                or audit_year < 2026
                or not isinstance(evidence, Mapping)
                or not all(isinstance(evidence.get(key), str) and evidence.get(key) for key in (
                    "paper_id", "version_id", "source_hash",
                ))
                or evidence.get("verified") is not True
            ):
                continue
            row = {
                "problem_id": record.record_id,
                "category": ranking_category,
                "status": record.filters.get("status"),
                "source": {
                    "paper_id": record.payload.get("paper_id"),
                    "version_id": record.payload.get("version_id"),
                    "source_hash": (
                        record.payload.get("evidence", {}).get("source_hash")
                        if isinstance(record.payload.get("evidence"), Mapping) else None
                    ),
                },
                "audit_through_year": audit_year,
                "record": dict(record.payload),
            }
            if category is None or _normalized_exact(row["category"]) == _normalized_exact(category):
                rows.append(row)
        rows.sort(key=lambda item: item["problem_id"])
        return tuple(rows)


def build_index(
    *,
    papers: Iterable[VerifiedMetadata | PaperRecord] = (),
    theorems: Iterable[ValidatedTheorem] = (),
    open_problems: Iterable[ValidatedOpenProblem] = (),
    topics: Iterable[TopicRecord] = (),
    collisions: Iterable[CollisionRecord] = (),
    rankings: Iterable[RankedDirection] = (),
    primitives: Iterable[NoveltyPrimitive] = (),
    graph: EvidenceBackedGraph | None = None,
) -> AtlasIndex:
    """Build an order-independent index solely from validated domain records."""

    paper_records = tuple(_metadata_record(item) for item in papers)
    paper_payloads = {item.record_id: item.payload for item in paper_records}
    supplied_rankings = tuple(rankings)
    if any(not isinstance(item, RankedDirection) for item in supplied_rankings):
        raise ValueError("unsupported or unvalidated ranking record")
    canonical_rankings = rank_open_directions(supplied_rankings)
    canonical_by_id = {item.direction_id: item for item in canonical_rankings}
    default_output = (None, False, False, None)
    for supplied in supplied_rankings:
        canonical = canonical_by_id[supplied.direction_id]
        supplied_output = (
            supplied.category, supplied.top_50_eligible, supplied.recommended, supplied.rank,
        )
        canonical_output = (
            canonical.category, canonical.top_50_eligible, canonical.recommended, canonical.rank,
        )
        if supplied_output != default_output and supplied_output != canonical_output:
            raise ValueError("forged ranking output does not match canonical rank_open_directions output")
    ranking_by_problem: dict[str, RankedDirection] = {}
    for item in canonical_rankings:
        ranking_by_problem.setdefault(item.problem.problem_id, item)
    problem_inputs = tuple(open_problems)
    categories = {
        problem.problem_id: ranking_by_problem[problem.problem_id].category.value
        for problem in problem_inputs
        if problem.problem_id in ranking_by_problem
        and ranking_by_problem[problem.problem_id].problem == problem
        and ranking_by_problem[problem.problem_id].category is not None
    }
    unresolved_eligible = {
        problem.problem_id
        for problem in problem_inputs
        if problem.problem_id in ranking_by_problem
        and ranking_by_problem[problem.problem_id].problem == problem
        and ranking_by_problem[problem.problem_id].top_50_eligible
        and ranking_by_problem[problem.problem_id].category is not None
    }
    records = list(paper_records)
    records.extend(_theorem_record(item, paper_payloads) for item in theorems)
    records.extend(
        _problem_record(item, paper_payloads, categories, item.problem_id in unresolved_eligible)
        for item in problem_inputs
    )
    records.extend(_topic_record(item) for item in topics)
    records.extend(_collision_record(item) for item in collisions)
    records.extend(_ranking_record(item) for item in canonical_rankings)
    records.extend(_primitive_record(item) for item in primitives)
    graph_nodes: tuple[dict[str, str], ...] = ()
    graph_edges: tuple[dict[str, str], ...] = ()
    if graph is not None:
        if not isinstance(graph, EvidenceBackedGraph):
            raise ValueError("graph must be an EvidenceBackedGraph")
        graph.validate_graph()
        graph_nodes = tuple({"id": item.node_id, "kind": item.kind.value} for item in graph.nodes)
        graph_edges = tuple({
            "source_id": item.source_id,
            "source_kind": item.source_kind.value,
            "relation": item.relation.value,
            "target_id": item.target_id,
            "target_kind": item.target_kind.value,
        } for item in graph.edges)
    return AtlasIndex(records, graph_nodes, graph_edges)


def load_index_text(text: str) -> AtlasIndex:
    """Parse canonical index text; file provenance is enforced by :func:`load_index`."""

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as caught:
        raise InvalidIndex("invalid index JSON") from caught
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise InvalidIndex("invalid index schema version")
    if payload.get("field_weights") != dict(FIELD_WEIGHTS):
        raise InvalidIndex("invalid index field weights")
    if not isinstance(payload.get("records"), list) or not isinstance(payload.get("graph"), dict):
        raise InvalidIndex("invalid index record or graph section")
    records: list[IndexRecord] = []
    try:
        for serialized in payload["records"]:
            if not isinstance(serialized, dict) or set(serialized) != {
                "record_id", "record_type", "payload", "search_fields", "filters", "scientific_hash",
            }:
                raise InvalidIndex("invalid index record structure")
            if not all(isinstance(serialized[key], dict) for key in ("payload", "search_fields", "filters")):
                raise InvalidIndex("invalid index record mappings")
            body = {key: serialized[key] for key in serialized if key != "scientific_hash"}
            if serialized["scientific_hash"] != _record_hash(body):
                raise InvalidIndex("record scientific hash integrity failure")
            records.append(IndexRecord(
                serialized["record_id"],
                serialized["record_type"],
                MappingProxyType(dict(serialized["payload"])),
                MappingProxyType(dict(serialized["search_fields"])),
                MappingProxyType(dict(serialized["filters"])),
                serialized["scientific_hash"],
                _validation_token=_VALIDATED_INDEX_RECORD_TOKEN,
            ))
        graph = payload["graph"]
        if (
            not isinstance(graph, dict)
            or set(graph) != {"nodes", "edges"}
            or not isinstance(graph["nodes"], list)
            or not isinstance(graph["edges"], list)
        ):
            raise InvalidIndex("invalid index graph structure")
        index = AtlasIndex(records, graph["nodes"], graph["edges"])
        if payload.get("index_hash") != index.scientific_hash:
            raise InvalidIndex("index hash integrity failure")
        if text != index.to_json():
            raise InvalidIndex("index is not canonically serialized")
        return index
    except InvalidIndex:
        raise
    except (KeyError, TypeError, ValueError) as caught:
        raise InvalidIndex("invalid index record or graph values") from caught


def _manifest_entries() -> Mapping[str, Mapping[str, str]]:
    try:
        text = INDEX_MANIFEST_PATH.read_text(encoding="utf-8")
        payload = json.loads(text)
        if text != _canonical_text(payload) + "\n":
            raise InvalidIndex("committed index manifest is not canonically serialized")
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "indexes"}:
            raise InvalidIndex("invalid committed index manifest structure")
        if payload["schema_version"] != MANIFEST_SCHEMA_VERSION or not isinstance(payload["indexes"], dict):
            raise InvalidIndex("invalid committed index manifest schema")
        entries: dict[str, Mapping[str, str]] = {}
        seen_paths: set[str] = set()
        for name, entry in payload["indexes"].items():
            if not isinstance(name, str) or not _INDEX_NAME_RE.fullmatch(name):
                raise InvalidIndex("invalid committed index manifest name")
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                raise InvalidIndex("invalid committed index manifest entry")
            relative = entry["path"]
            expected = entry["sha256"]
            if (
                not isinstance(relative, str)
                or "\\" in relative
                or not relative.startswith("indexes/")
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or Path(relative).suffix != ".json"
                or relative == "indexes/manifest.json"
            ):
                raise InvalidIndex("committed index manifest path must stay in indexes/")
            if not isinstance(expected, str) or not _HASH_RE.fullmatch(expected):
                raise InvalidIndex("committed index manifest requires a lowercase SHA-256")
            if relative in seen_paths:
                raise InvalidIndex("committed index manifest paths must be unique")
            seen_paths.add(relative)
            entries[name] = MappingProxyType({"path": relative, "sha256": expected})
        return MappingProxyType(entries)
    except InvalidIndex:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as caught:
        raise InvalidIndex("cannot read committed index manifest") from caught


def load_index(selector: str | Path = "frontier-atlas") -> AtlasIndex:
    """Load only a manifest-allowlisted canonical index from this repository."""

    if not isinstance(selector, (str, Path)):
        raise InvalidIndex("index selector must be a committed manifest name or path")
    selected = str(selector).replace("\\", "/")
    if not selected or Path(selected).is_absolute() or ".." in Path(selected).parts:
        raise InvalidIndex("index selector must name a committed manifest entry")
    entries = _manifest_entries()
    matches = [entry for name, entry in entries.items() if selected in {name, entry["path"]}]
    if len(matches) != 1:
        raise InvalidIndex("index selector is not in the committed manifest allowlist")
    entry = matches[0]
    target = REPOSITORY_ROOT / entry["path"]
    try:
        resolved_indexes = INDEXES_ROOT.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        if resolved_target.parent != resolved_indexes or target.is_symlink():
            raise InvalidIndex("committed index target escapes the fixed indexes directory")
        raw = resolved_target.read_bytes()
        if sha256(raw).hexdigest() != entry["sha256"]:
            raise InvalidIndex("committed index SHA-256 does not match manifest")
        return load_index_text(raw.decode("utf-8"))
    except InvalidIndex:
        raise
    except (OSError, UnicodeError, TypeError, ValueError) as caught:
        raise InvalidIndex(f"cannot read committed index: {entry['path']}") from caught
