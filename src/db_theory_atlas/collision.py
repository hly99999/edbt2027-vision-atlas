"""Conservative novelty-primitive and structured collision assessment."""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from enum import Enum
import re
from typing import Mapping

from .graph import (
    EdgeRelation,
    EvidenceBackedGraph,
    GraphEvidence,
    NodeKind,
    claim_for_graph_relation,
)
from .model import EvidenceType
from .problems import ValidatedOpenProblem
from .serialization import freeze_json
from .theorems import ScopeRelation, ValidatedTheorem, compare_scopes


class PrimitiveStatus(str, Enum):
    OBSERVED = "OBSERVED"
    ACTIVE = "ACTIVE"
    HISTORICAL = "HISTORICAL"
    RETIRED = "RETIRED"
    UNKNOWN = "UNKNOWN"


class CollisionSeverity(str, Enum):
    DIRECT = "DIRECT"
    STRONG = "STRONG"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"
    NONE = "NONE"


_VALIDATED_COLLISION_TOKEN = object()


def _enum(value: object, enum_type: type[Enum], label: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the controlled taxonomy") from caught


def _ids(value: object, prefix: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")
    if any(not isinstance(item, str) or not item.startswith(f"{prefix}:") for item in value):
        raise ValueError(f"{label} must contain canonical {prefix} IDs")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} cannot contain duplicates")
    return tuple(sorted(value))


def _primitive_phrase(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("primitive phrase must be concise controlled text")
    phrase = " ".join(value.casefold().split())
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", phrase)
    if not 2 <= len(words) <= 8 or " ".join(words) != phrase:
        raise ValueError("primitive phrase must be a concise normalized concept of 2..8 words")
    if any(word.startswith("novel") for word in words):
        raise ValueError("novelty primitive phrase cannot make a novelty claim")
    return phrase


def claim_for_primitive_membership(
    primitive_id: str,
    phrase: str,
    member_id: str,
    member_kind: NodeKind,
    years: tuple[int, ...],
    status: PrimitiveStatus,
) -> Mapping[str, object]:
    """Build the exact structured claim required for one primitive member."""

    if not isinstance(primitive_id, str) or not primitive_id.startswith("primitive:"):
        raise ValueError("primitive_id must be a canonical primitive ID")
    phrase = _primitive_phrase(phrase)
    member_kind = _enum(member_kind, NodeKind, "primitive member kind")
    if member_kind not in {NodeKind.PAPER, NodeKind.THEOREM}:
        raise ValueError("primitive membership must bind a PAPER or THEOREM member")
    prefix = "paper" if member_kind is NodeKind.PAPER else "theorem"
    member_id = _ids((member_id,), prefix, "primitive member ID")[0]
    if not isinstance(years, tuple) or not years or any(
        isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100
        for year in years
    ) or len(set(years)) != len(years):
        raise ValueError("primitive membership years must be unique supported publication years")
    status = _enum(status, PrimitiveStatus, "primitive status")
    payload = freeze_json({
        "claim_type": "NOVELTY_PRIMITIVE_MEMBERSHIP",
        "primitive_id": primitive_id,
        "phrase": phrase,
        "member_id": member_id,
        "member_kind": member_kind.value,
        "years": tuple(sorted(years)),
        "status": status.value,
    })
    assert isinstance(payload, Mapping)
    return payload


@dataclass(frozen=True, slots=True)
class NoveltyPrimitive:
    """An observed, source-backed concept; the record makes no novelty claim."""

    primitive_id: str
    phrase: str
    paper_ids: tuple[str, ...]
    theorem_ids: tuple[str, ...]
    years: tuple[int, ...]
    status: PrimitiveStatus
    source_evidence: tuple[GraphEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.primitive_id, str) or not self.primitive_id.startswith("primitive:"):
            raise ValueError("primitive_id must be a canonical primitive ID")
        phrase = _primitive_phrase(self.phrase)
        object.__setattr__(self, "phrase", phrase)
        object.__setattr__(self, "paper_ids", _ids(self.paper_ids, "paper", "paper_ids"))
        object.__setattr__(self, "theorem_ids", _ids(self.theorem_ids, "theorem", "theorem_ids"))
        if not self.paper_ids and not self.theorem_ids:
            raise ValueError("novelty primitive requires paper or theorem memberships")
        if not isinstance(self.years, tuple) or not self.years:
            raise ValueError("novelty primitive requires observed years")
        if any(isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100 for year in self.years):
            raise ValueError("primitive years must be supported publication years")
        if len(set(self.years)) != len(self.years):
            raise ValueError("primitive years cannot contain duplicates")
        object.__setattr__(self, "years", tuple(sorted(self.years)))
        object.__setattr__(self, "status", _enum(self.status, PrimitiveStatus, "primitive status"))
        if not isinstance(self.source_evidence, tuple) or not self.source_evidence:
            raise ValueError("novelty primitive must be evidence-backed")
        expected_claims = {
            member_id: claim_for_primitive_membership(
                self.primitive_id,
                phrase,
                member_id,
                member_kind,
                self.years,
                self.status,
            )
            for member_kind, members in (
                (NodeKind.PAPER, self.paper_ids),
                (NodeKind.THEOREM, self.theorem_ids),
            )
            for member_id in members
        }
        identities: set[str] = set()
        covered_members: set[str] = set()
        for evidence in self.source_evidence:
            if not isinstance(evidence, GraphEvidence):
                raise ValueError("primitive source evidence must be exact note-backed graph evidence")
            evidence.validate_membership()
            if evidence.pointer.evidence_type is not EvidenceType.GRAPH_RELATION:
                raise ValueError("primitive membership evidence must use GRAPH_RELATION evidence")
            matching_members = tuple(
                member_id for member_id, claim in expected_claims.items()
                if evidence.pointer.claim == claim
            )
            if len(matching_members) != 1:
                raise ValueError("primitive membership evidence requires an exact structured claim")
            covered_members.add(matching_members[0])
            member_id = matching_members[0]
            if member_id in self.paper_ids and evidence.note.paper_id != member_id:
                raise ValueError("primitive membership note must belong to the declared member paper")
            if evidence.identity in identities:
                raise ValueError("primitive source evidence cannot contain duplicates")
            identities.add(evidence.identity)
        if covered_members != set(expected_claims):
            raise ValueError("every primitive paper/theorem membership requires exact evidence")
        object.__setattr__(self, "source_evidence", tuple(sorted(
            self.source_evidence, key=lambda item: item.identity
        )))


@dataclass(frozen=True, slots=True)
class CollisionRecord:
    left_id: str
    right_id: str
    severity: CollisionSeverity
    reasons: tuple[str, ...]
    evidence: tuple[GraphEvidence, ...]
    shared_primitive_ids: tuple[str, ...]
    exact_scope: bool
    exact_result_signature: bool
    exact_relation: EdgeRelation | None
    _validation_token: InitVar[object] = None

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _VALIDATED_COLLISION_TOKEN:
            raise ValueError("CollisionRecord can only be created by assess_collision")
        if not isinstance(self.left_id, str) or not isinstance(self.right_id, str) or self.left_id == self.right_id:
            raise ValueError("collision endpoints must be distinct canonical IDs")
        object.__setattr__(self, "severity", _enum(self.severity, CollisionSeverity, "collision severity"))
        if not isinstance(self.reasons, tuple) or not self.reasons or any(
            not isinstance(reason, str) or not reason.strip() for reason in self.reasons
        ):
            raise ValueError("collision record requires explicit reasons")
        if not isinstance(self.evidence, tuple) or any(not isinstance(item, GraphEvidence) for item in self.evidence):
            raise ValueError("collision evidence must be exact note-backed graph evidence")
        for evidence in self.evidence:
            evidence.validate_membership()
        object.__setattr__(self, "shared_primitive_ids", _ids(
            self.shared_primitive_ids, "primitive", "shared_primitive_ids"
        ))
        if not isinstance(self.exact_scope, bool) or not isinstance(self.exact_result_signature, bool):
            raise ValueError("exact collision flags must be booleans")
        if self.exact_relation is not None:
            object.__setattr__(self, "exact_relation", _enum(
                self.exact_relation, EdgeRelation, "exact collision relation"
            ))
        if self.severity in {CollisionSeverity.DIRECT, CollisionSeverity.STRONG} and not (
            self.evidence or self.shared_primitive_ids
        ):
            raise ValueError("DIRECT/STRONG collision requires verified evidence")
        if self.severity is CollisionSeverity.DIRECT:
            solution_relation = self.exact_relation in {
                EdgeRelation.SOLVES,
                EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
            }
            if not self.exact_scope or not self.exact_result_signature or not solution_relation:
                raise ValueError("DIRECT collision requires exact scope/result and an exact solution relation")


def _solution_claims(
    candidate: ValidatedOpenProblem,
    prior: ValidatedTheorem | ValidatedOpenProblem,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(prior, ValidatedTheorem):
        return ()
    solved_by_claim = claim_for_graph_relation(
        candidate.problem_id,
        NodeKind.OPEN_PROBLEM,
        EdgeRelation.OPEN_PROBLEM_SOLVED_BY,
        prior.paper_id,
        NodeKind.PAPER,
        source_record_id=candidate.problem_id,
        target_record_id=prior.theorem_id,
        source_results=(candidate.requested_result,),
        target_results=prior.results,
    )
    solves_claim = claim_for_graph_relation(
        prior.paper_id,
        NodeKind.PAPER,
        EdgeRelation.SOLVES,
        candidate.problem_id,
        NodeKind.OPEN_PROBLEM,
        source_record_id=prior.theorem_id,
        target_record_id=candidate.problem_id,
        source_results=prior.results,
        target_results=(candidate.requested_result,),
    )
    return (solved_by_claim, solves_claim)


def _solution_edges(
    candidate: ValidatedOpenProblem,
    prior: ValidatedTheorem | ValidatedOpenProblem,
    graph: EvidenceBackedGraph,
):
    expected_claims = _solution_claims(candidate, prior)
    if not expected_claims:
        return ()
    return tuple(edge for edge in graph.edges if (
        (
            edge.source_id == candidate.problem_id
            and edge.relation is EdgeRelation.OPEN_PROBLEM_SOLVED_BY
            and edge.target_id == prior.paper_id
        ) or (
            edge.source_id == prior.paper_id
            and edge.relation is EdgeRelation.SOLVES
            and edge.target_id == candidate.problem_id
        )
    ) and any(
        evidence.pointer.claim in expected_claims for evidence in edge.evidence
    ))


def _shared_primitives(
    candidate: ValidatedOpenProblem,
    prior: ValidatedTheorem | ValidatedOpenProblem,
    graph: EvidenceBackedGraph,
    primitives: tuple[NoveltyPrimitive, ...] | None,
) -> tuple[NoveltyPrimitive, ...]:
    registered = {
        node.node_id: node.record
        for node in graph.nodes
        if node.kind is NodeKind.PRIMITIVE
    }
    result = []
    for primitive in registered.values():
        prior_member = (
            prior.theorem_id in primitive.theorem_ids
            if isinstance(prior, ValidatedTheorem)
            else prior.paper_id in primitive.paper_ids
        )
        if candidate.paper_id in primitive.paper_ids and prior_member:
            result.append(primitive)
    complete = tuple(sorted(result, key=lambda item: item.primitive_id))
    if primitives is None:
        return complete
    for primitive in primitives:
        if not isinstance(primitive, NoveltyPrimitive) or primitive.primitive_id not in registered:
            raise ValueError("collision primitives must be registered validated graph nodes")
        if registered[primitive.primitive_id] != primitive:
            raise ValueError("collision primitive must equal its registered graph record; shadow primitive records are rejected")
    supplied = tuple(sorted(primitives, key=lambda item: item.primitive_id))
    if supplied != complete:
        raise ValueError("collision primitives must equal the complete graph-derived shared primitive set")
    return complete


def _require_registered_collision_record(
    record: ValidatedOpenProblem | ValidatedTheorem,
    graph: EvidenceBackedGraph,
    *,
    role: str,
) -> None:
    if isinstance(record, ValidatedTheorem):
        kind = NodeKind.THEOREM
        identifier = record.theorem_id
    else:
        kind = NodeKind.OPEN_PROBLEM
        identifier = record.problem_id
    registered = next((
        node.record
        for node in graph.nodes
        if node.kind is kind and node.node_id == identifier
    ), None)
    if registered != record:
        raise ValueError(
            f"collision {role} must equal its registered graph record; "
            f"missing or shadow {role} records are rejected"
        )


def assess_collision(
    candidate: ValidatedOpenProblem,
    prior: ValidatedTheorem | ValidatedOpenProblem,
    *,
    graph: EvidenceBackedGraph,
    primitives: tuple[NoveltyPrimitive, ...] | None = None,
    token_overlap: bool = False,
) -> CollisionRecord:
    """Assess only structured overlap; lexical overlap never yields DIRECT/STRONG."""

    if not isinstance(candidate, ValidatedOpenProblem):
        raise ValueError("collision candidate must be a ValidatedOpenProblem")
    if not isinstance(prior, (ValidatedTheorem, ValidatedOpenProblem)):
        raise ValueError("collision prior art must be a validated theorem or open problem")
    if not isinstance(graph, EvidenceBackedGraph):
        raise ValueError("collision assessment requires an EvidenceBackedGraph")
    if primitives is not None and not isinstance(primitives, tuple):
        raise ValueError("collision primitives must be omitted or supplied as an immutable tuple")
    if not isinstance(token_overlap, bool):
        raise ValueError("collision primitives/token_overlap must use controlled immutable values")
    graph.validate_graph()
    _require_registered_collision_record(candidate, graph, role="candidate")
    _require_registered_collision_record(prior, graph, role="prior")

    prior_id = prior.theorem_id if isinstance(prior, ValidatedTheorem) else prior.problem_id
    prior_results = prior.results if isinstance(prior, ValidatedTheorem) else (prior.requested_result,)
    scope_relation = compare_scopes(prior.scope, candidate.scope)
    exact_scope = scope_relation is ScopeRelation.EQUAL
    exact_result = candidate.requested_result in prior_results
    solutions = _solution_edges(candidate, prior, graph)
    solution_claims = _solution_claims(candidate, prior)
    shared = _shared_primitives(candidate, prior, graph, primitives)
    evidence = tuple(sorted({
        item.identity: item
        for edge in solutions
        for item in edge.evidence
        if isinstance(item, GraphEvidence) and item.pointer.claim in solution_claims
    }.values(), key=lambda item: item.identity))
    exact_relation = solutions[0].relation if solutions else None

    if exact_scope and exact_result and solutions:
        severity = CollisionSeverity.DIRECT
        reasons = ("Exact formal scope and requested/result signature coincide with verified direct prior-art evidence.",)
    elif exact_result and scope_relation in {ScopeRelation.EQUAL, ScopeRelation.NARROWER, ScopeRelation.BROADER} and (
        evidence or shared
    ):
        severity = CollisionSeverity.STRONG
        reasons = ("Substantial structured scope/result overlap is supported by verified evidence or a shared primitive.",)
    elif exact_scope or scope_relation in {ScopeRelation.NARROWER, ScopeRelation.BROADER}:
        severity = CollisionSeverity.PARTIAL
        reasons = ("A structured component overlaps, but no verified exact resolving relation is present.",)
    elif token_overlap:
        severity = CollisionSeverity.WEAK
        reasons = ("Only token or co-occurrence overlap is established; severity is conservatively capped.",)
    else:
        severity = CollisionSeverity.NONE
        reasons = ("The validated formal scopes and result signatures do not establish overlap.",)

    return CollisionRecord(
        candidate.problem_id,
        prior_id,
        severity,
        reasons,
        evidence,
        tuple(item.primitive_id for item in shared),
        exact_scope,
        exact_result,
        exact_relation,
        _validation_token=_VALIDATED_COLLISION_TOKEN,
    )
