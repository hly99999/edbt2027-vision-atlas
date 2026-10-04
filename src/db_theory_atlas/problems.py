"""Evidence-gated open-problem, follow-up, and resolution validation."""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from datetime import date
from enum import Enum
import re
from typing import Mapping

from .evidence import validate_evidence_membership
from .model import EvidencePointer, EvidenceType, OpenStatus
from .reading import NoteRecord, coverage_certificate, validate_note
from .serialization import freeze_json, scientific_hash
from .sources import (
    VerificationStatus,
    VerifiedMetadata,
    canonical_paper_id,
    verify_metadata,
)
from .theorems import (
    QueryProblemScope,
    ScopeRelation,
    TheoremResult,
    ValidatedTheorem,
    compare_scopes,
    result_payload,
    result_from_claim,
    scope_payload,
    scope_from_claim,
    theorem_support,
    validate_measure_roles,
)
from .versions import VersionFamily, VersionRelation, resolve_version_family


class OpenProblemExplicitness(str, Enum):
    EXPLICIT = "EXPLICIT"
    IMPLICIT_GAP = "IMPLICIT_GAP"


class SearchCandidateDisposition(str, Enum):
    NO_MATCH = "NO_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    PLAUSIBLE_RESOLUTION = "PLAUSIBLE_RESOLUTION"
    VERIFIED_RESOLUTION = "VERIFIED_RESOLUTION"
    OPEN_STATUS_CONFIRMED = "OPEN_STATUS_CONFIRMED"


class SearchQueryCategory(str, Enum):
    EXACT_PHRASE = "EXACT_PHRASE"
    TITLE_CITATION = "TITLE_CITATION"
    AUTHOR = "AUTHOR"
    KEYWORD = "KEYWORD"
    LATER_VENUE = "LATER_VENUE"


class SearchSource(str, Enum):
    PUBLISHER = "PUBLISHER"
    OFFICIAL_PROCEEDINGS = "OFFICIAL_PROCEEDINGS"
    ARXIV = "ARXIV"
    AUTHOR_FULL_TEXT = "AUTHOR_FULL_TEXT"
    DBLP = "DBLP"
    OPENALEX = "OPENALEX"
    CROSSREF = "CROSSREF"
    GOOGLE_SCHOLAR = "GOOGLE_SCHOLAR"
    SEMANTIC_SCHOLAR = "SEMANTIC_SCHOLAR"

    @property
    def role(self) -> str:
        if self in {
            SearchSource.PUBLISHER,
            SearchSource.OFFICIAL_PROCEEDINGS,
            SearchSource.ARXIV,
            SearchSource.AUTHOR_FULL_TEXT,
        }:
            return "PRIMARY"
        return "METADATA"


class SearchConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ReviewerConclusion(str, Enum):
    NO_RESOLUTION_AFTER_DESCENDANT_AUDIT = "NO_RESOLUTION_AFTER_DESCENDANT_AUDIT"
    PLAUSIBLE_RESOLUTION_REQUIRES_REVIEW = "PLAUSIBLE_RESOLUTION_REQUIRES_REVIEW"
    VERIFIED_RESOLUTION_FOUND = "VERIFIED_RESOLUTION_FOUND"


_HASH = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _enum(value: object, enum_type: type[Enum], label: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the controlled taxonomy") from caught


def _text(value: object, label: str, *, min_words: int = 1, max_words: int = 80, max_chars: int = 600) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty")
    compact = " ".join(value.split())
    words = re.findall(r"\b\w+\b", compact, flags=re.UNICODE)
    if len(words) < min_words:
        raise ValueError(f"{label} must contain substantive evidence")
    if len(compact) > max_chars or len(words) > max_words:
        raise ValueError(f"{label} must be concise")
    return compact


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    candidate_id: str
    disposition: SearchCandidateDisposition
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.startswith("paper:"):
            raise ValueError("candidate_id must be a canonical paper ID")
        object.__setattr__(self, "disposition", _enum(
            self.disposition, SearchCandidateDisposition, "candidate disposition"
        ))
        object.__setattr__(self, "rationale", _text(self.rationale, "candidate rationale", min_words=5))


@dataclass(frozen=True, slots=True)
class FollowupQuery:
    category: SearchQueryCategory
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _enum(self.category, SearchQueryCategory, "query category"))
        object.__setattr__(self, "text", _text(self.text, "follow-up query", min_words=3, max_words=40, max_chars=300))


@dataclass(frozen=True, slots=True)
class SearchManifestEntry:
    query_category: SearchQueryCategory
    query_text: str
    source: SearchSource
    returned_ids: tuple[str, ...]
    checked_ids: tuple[str, ...]
    manifest_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_category", _enum(
            self.query_category, SearchQueryCategory, "manifest query category"
        ))
        object.__setattr__(self, "query_text", _text(
            self.query_text, "manifest query text", min_words=3, max_words=40, max_chars=300
        ))
        object.__setattr__(self, "source", _enum(self.source, SearchSource, "manifest source"))
        for label, values in (("returned_ids", self.returned_ids), ("checked_ids", self.checked_ids)):
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item.startswith("paper:") for item in values
            ):
                raise ValueError(f"manifest {label} must be an immutable tuple of canonical paper IDs")
            if len(set(values)) != len(values):
                raise ValueError(f"manifest {label} cannot contain duplicates")
        if not set(self.checked_ids) <= set(self.returned_ids):
            raise ValueError("manifest checked_ids must be a subset of returned_ids")
        if not isinstance(self.manifest_hash, str) or not _HASH.fullmatch(self.manifest_hash):
            raise ValueError("manifest_hash must be a completed SHA-256 manifest hash")
        object.__setattr__(self, "manifest_hash", self.manifest_hash.lower())


def search_manifest_hash(
    query_category: SearchQueryCategory,
    query_text: str,
    source: SearchSource,
    returned_ids: tuple[str, ...],
    checked_ids: tuple[str, ...],
) -> str:
    """Hash the complete canonical payload of one reproducible follow-up query."""
    category = _enum(query_category, SearchQueryCategory, "manifest query category")
    normalized_text = _text(query_text, "manifest query text", min_words=3, max_words=40, max_chars=300)
    normalized_source = _enum(source, SearchSource, "manifest source")
    if not isinstance(returned_ids, tuple) or not isinstance(checked_ids, tuple):
        raise ValueError("manifest returned/checked IDs must be immutable tuples")
    return scientific_hash({
        "query_category": category.value,
        "query_text": normalized_text,
        "source": normalized_source.value,
        "returned_ids": returned_ids,
        "checked_ids": checked_ids,
    })


@dataclass(frozen=True, slots=True)
class OpenStatusEvidence:
    note: NoteRecord
    evidence: EvidencePointer
    metadata: VerifiedMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.note, NoteRecord):
            raise ValueError("open-status evidence requires a NoteRecord")
        if not isinstance(self.evidence, EvidencePointer):
            raise ValueError("open-status evidence requires an EvidencePointer")
        if not isinstance(self.metadata, VerifiedMetadata):
            raise ValueError("open-status evidence requires verified metadata")


@dataclass(frozen=True, slots=True)
class FollowupSearchRecord:
    problem_id: str
    query_fingerprint: str
    queries: tuple[FollowupQuery, ...]
    sources: tuple[SearchSource, ...]
    audit_date: str
    through_year: int
    result_candidates: tuple[SearchCandidate, ...]
    manifests: tuple[SearchManifestEntry, ...]
    source_metadata: VerifiedMetadata
    open_status_evidence: tuple[OpenStatusEvidence, ...]
    completed: bool
    reviewer_verified: bool
    reviewer_conclusion: ReviewerConclusion
    reviewer_rationale: str
    confidence: SearchConfidence

    def __post_init__(self) -> None:
        if not isinstance(self.problem_id, str) or not self.problem_id.startswith("problem:"):
            raise ValueError("follow-up problem_id must be a canonical problem ID")
        if not isinstance(self.query_fingerprint, str) or not _HASH.fullmatch(self.query_fingerprint):
            raise ValueError("query_fingerprint must be a SHA-256 scientific fingerprint")
        object.__setattr__(self, "query_fingerprint", self.query_fingerprint.lower())
        if not isinstance(self.queries, tuple) or not self.queries or any(
            not isinstance(item, FollowupQuery) for item in self.queries
        ):
            raise ValueError("queries must be a nonempty immutable tuple of FollowupQuery records")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ValueError("sources must be a named nonempty immutable tuple")
        normalized_sources = tuple(_enum(item, SearchSource, "follow-up source") for item in self.sources)
        if len(set(normalized_sources)) != len(normalized_sources):
            raise ValueError("follow-up sources cannot contain duplicates")
        object.__setattr__(self, "sources", normalized_sources)
        if not isinstance(self.audit_date, str):
            raise ValueError("audit_date must be an ISO calendar date")
        try:
            audited = date.fromisoformat(self.audit_date)
        except ValueError as caught:
            raise ValueError("audit_date must be an ISO calendar date") from caught
        if isinstance(self.through_year, bool) or not isinstance(self.through_year, int):
            raise ValueError("through_year must be an integer scientific coverage year")
        if self.through_year > audited.year:
            raise ValueError("through_year cannot exceed the scientific audit date year")
        if not isinstance(self.result_candidates, tuple) or any(
            not isinstance(item, SearchCandidate) for item in self.result_candidates
        ):
            raise ValueError("result_candidates must be an immutable tuple of SearchCandidate records")
        if len({item.candidate_id for item in self.result_candidates}) != len(self.result_candidates):
            raise ValueError("result_candidates cannot contain duplicate paper IDs")
        if not isinstance(self.manifests, tuple) or not self.manifests or any(
            not isinstance(item, SearchManifestEntry) for item in self.manifests
        ):
            raise ValueError("manifests must contain completed SearchManifestEntry records")
        if len({item.manifest_hash for item in self.manifests}) != len(self.manifests):
            raise ValueError("manifest hashes must be unique")
        if not isinstance(self.source_metadata, VerifiedMetadata):
            raise ValueError("follow-up source_metadata must be verified metadata")
        if not isinstance(self.open_status_evidence, tuple) or any(
            not isinstance(item, OpenStatusEvidence) for item in self.open_status_evidence
        ):
            raise ValueError("open_status_evidence must be an immutable tuple of OpenStatusEvidence records")
        if not isinstance(self.completed, bool) or not isinstance(self.reviewer_verified, bool):
            raise ValueError("completed and reviewer_verified must be booleans")
        object.__setattr__(self, "reviewer_conclusion", _enum(
            self.reviewer_conclusion, ReviewerConclusion, "reviewer conclusion"
        ))
        rationale = _text(self.reviewer_rationale, "reviewer rationale", min_words=12)
        if re.fullmatch(r"no result(?: was)? found[.!]?", rationale, re.IGNORECASE):
            raise ValueError("reviewer rationale cannot be absence-only")
        object.__setattr__(self, "reviewer_rationale", rationale)
        object.__setattr__(self, "confidence", _enum(self.confidence, SearchConfidence, "search confidence"))


def problem_fingerprint(problem_id: str, scope: QueryProblemScope, requested_result: TheoremResult) -> str:
    if not isinstance(problem_id, str) or not problem_id.startswith("problem:"):
        raise ValueError("problem_id must be a canonical problem ID")
    if not isinstance(scope, QueryProblemScope) or not isinstance(requested_result, TheoremResult):
        raise ValueError("problem fingerprint requires structured scope and requested result")
    validate_measure_roles(requested_result, scope)
    return scientific_hash({
        "problem_id": problem_id,
        "scope": scope_payload(scope),
        "requested_result": result_payload(requested_result),
    })


def claim_for_open_problem(
    scope: QueryProblemScope,
    requested_result: TheoremResult,
    *,
    restricted_scope: QueryProblemScope | None = None,
    remaining_scope: QueryProblemScope | None = None,
) -> Mapping[str, object]:
    if not isinstance(scope, QueryProblemScope) or not isinstance(requested_result, TheoremResult):
        raise ValueError("open-problem claim requires structured scope and requested result")
    validate_measure_roles(requested_result, scope)
    remaining = remaining_scope or scope
    if remaining != scope:
        raise ValueError("open-problem scope must equal its remaining_scope")
    frozen = freeze_json({
        "claim_type": "OPEN_PROBLEM",
        "scope": scope_payload(scope),
        "requested_result": result_payload(requested_result),
        "restricted_scope": scope_payload(restricted_scope) if restricted_scope is not None else None,
        "remaining_scope": scope_payload(remaining),
    })
    assert isinstance(frozen, Mapping)
    return frozen


def _open_problem_support(
    pointer: EvidencePointer,
) -> tuple[QueryProblemScope, TheoremResult, QueryProblemScope | None, QueryProblemScope]:
    claim = pointer.claim
    required = {"claim_type", "scope", "requested_result", "restricted_scope", "remaining_scope"}
    if not isinstance(claim, Mapping) or frozenset(claim) != required or claim["claim_type"] != "OPEN_PROBLEM":
        raise ValueError("open-problem evidence lacks a complete structured claim")
    scope = scope_from_claim(claim["scope"])
    requested = result_from_claim(claim["requested_result"])
    restricted = scope_from_claim(claim["restricted_scope"]) if claim["restricted_scope"] is not None else None
    remaining = scope_from_claim(claim["remaining_scope"])
    if scope != remaining:
        raise ValueError("open-problem structured scope must equal remaining_scope")
    validate_measure_roles(requested, scope)
    return scope, requested, restricted, remaining


@dataclass(frozen=True, slots=True)
class OpenProblemExtraction:
    problem_id: str
    paraphrase: str
    scope: QueryProblemScope
    requested_result: TheoremResult
    explicitness: OpenProblemExplicitness
    evidence: EvidencePointer
    status: OpenStatus
    followup_search: FollowupSearchRecord | None
    restricted_case_evidence: EvidencePointer | None = None
    unresolved_case_evidence: EvidencePointer | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.problem_id, str) or not self.problem_id.startswith("problem:"):
            raise ValueError("problem_id must be a canonical problem ID")
        object.__setattr__(self, "paraphrase", _text(self.paraphrase, "problem paraphrase"))
        if not isinstance(self.scope, QueryProblemScope) or not isinstance(self.requested_result, TheoremResult):
            raise ValueError("open problem requires structured scope and requested_result")
        validate_measure_roles(self.requested_result, self.scope)
        object.__setattr__(self, "explicitness", _enum(
            self.explicitness, OpenProblemExplicitness, "open-problem explicitness"
        ))
        if not isinstance(self.evidence, EvidencePointer):
            raise ValueError("open-problem extraction requires evidence")
        if not isinstance(self.status, OpenStatus):
            raise ValueError("status must be an OpenStatus")
        if self.followup_search is not None and not isinstance(self.followup_search, FollowupSearchRecord):
            raise ValueError("followup_search must be a FollowupSearchRecord or None")


_VALIDATED_PROBLEM_TOKEN = object()
_VALIDATED_RESOLUTION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class ValidatedOpenProblem:
    problem_id: str
    problem_fingerprint: str
    paper_id: str
    version_id: str
    paraphrase: str
    scope: QueryProblemScope
    requested_result: TheoremResult
    explicitness: OpenProblemExplicitness
    evidence: EvidencePointer
    status: OpenStatus
    followup_search: FollowupSearchRecord | None
    restricted_case_evidence: EvidencePointer | None
    unresolved_case_evidence: EvidencePointer | None
    _validation_token: InitVar[object] = None

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _VALIDATED_PROBLEM_TOKEN:
            raise ValueError("ValidatedOpenProblem can only be created by validate_open_problem")


def _validate_open_verified(
    extraction: OpenProblemExtraction,
    fingerprint: str,
    source_note: NoteRecord,
) -> None:
    if extraction.status in {OpenStatus.RESOLVED, OpenStatus.PARTIALLY_RESOLVED}:
        raise ValueError("resolved statuses require validate_resolution and a later validated theorem")
    if extraction.status is not OpenStatus.OPEN_VERIFIED:
        return
    search = extraction.followup_search
    if search is None or not search.completed or search.through_year < 2026:
        raise ValueError("OPEN_VERIFIED requires a completed follow-up search through 2026")
    if search.problem_id != extraction.problem_id:
        raise ValueError("follow-up search is bound to a different problem")
    if search.query_fingerprint != fingerprint:
        raise ValueError("follow-up query fingerprint does not match the structured problem")
    source_verified = _validated_metadata(search.source_metadata, "open-problem source publication")
    if canonical_paper_id(source_verified) != source_note.paper_id:
        raise ValueError("follow-up source metadata does not identify the original problem paper")
    categories = {item.category for item in search.queries}
    if categories != set(SearchQueryCategory):
        raise ValueError("OPEN_VERIFIED requires all exact query categories")
    if len(categories) != len(search.queries):
        raise ValueError("OPEN_VERIFIED requires one exact query text per query category")
    declared_queries = {item.category: item.text for item in search.queries}
    roles = {item.role for item in search.sources}
    if roles != {"PRIMARY", "METADATA"}:
        raise ValueError("OPEN_VERIFIED requires primary and metadata source coverage")
    manifest_categories = {item.query_category for item in search.manifests}
    manifest_sources = {item.source for item in search.manifests}
    if manifest_categories != categories or manifest_sources != set(search.sources):
        raise ValueError("completed manifests must cover every query category and named source")
    if any(item.query_category not in categories or item.source not in search.sources for item in search.manifests):
        raise ValueError("manifest entries must be bound to declared queries and sources")
    for manifest in search.manifests:
        if manifest.query_text != declared_queries[manifest.query_category]:
            raise ValueError("manifest exact query text does not match the declared query")
        expected_hash = search_manifest_hash(
            manifest.query_category,
            manifest.query_text,
            manifest.source,
            manifest.returned_ids,
            manifest.checked_ids,
        )
        if manifest.manifest_hash != expected_hash:
            raise ValueError("manifest hash does not recompute from its canonical payload")
    if not search.result_candidates:
        raise ValueError("OPEN_VERIFIED requires nonempty positive result candidates")
    candidate_ids = {item.candidate_id for item in search.result_candidates}
    returned_ids = {item for manifest in search.manifests for item in manifest.returned_ids}
    checked_ids = {item for manifest in search.manifests for item in manifest.checked_ids}
    if returned_ids != candidate_ids or checked_ids != candidate_ids:
        raise ValueError("query manifests must return and check every declared result candidate ID")
    plausible = {
        SearchCandidateDisposition.PLAUSIBLE_RESOLUTION,
        SearchCandidateDisposition.VERIFIED_RESOLUTION,
    }
    if any(item.disposition in plausible for item in search.result_candidates):
        raise ValueError("OPEN_VERIFIED cannot coexist with a plausible resolution candidate")
    positive_candidates = {
        item.candidate_id
        for item in search.result_candidates
        if item.disposition is SearchCandidateDisposition.OPEN_STATUS_CONFIRMED
    }
    if not positive_candidates or not search.open_status_evidence:
        raise ValueError("OPEN_VERIFIED requires positive later-source open-status evidence")
    evidence_candidates: set[str] = set()
    for status in search.open_status_evidence:
        validate_note(status.note)
        validate_evidence_membership(status.evidence, status.note)
        if not status.evidence.verified or status.evidence.evidence_type not in {
            EvidenceType.OPEN_PROBLEM,
            EvidenceType.FUTURE_WORK,
        }:
            raise ValueError("positive status evidence must be exact verified OPEN_PROBLEM or FUTURE_WORK evidence")
        later_metadata = _validated_metadata(status.metadata, "later open-status publication")
        later_id = canonical_paper_id(later_metadata)
        if later_id != status.note.paper_id:
            raise ValueError("later open-status metadata does not identify its evidence note")
        if later_metadata.year <= source_verified.year:
            raise ValueError("OPEN_VERIFIED status evidence requires a strictly later verified publication year")
        supported_scope, supported_result, _restricted, _remaining = _open_problem_support(status.evidence)
        if supported_scope != extraction.scope or supported_result != extraction.requested_result:
            raise ValueError("later open-status evidence must match the exact problem scope and requested result")
        evidence_candidates.add(later_id)
    if evidence_candidates != positive_candidates:
        raise ValueError("positive open-status candidates must match the exact later evidence sources")
    if not search.reviewer_verified:
        raise ValueError("OPEN_VERIFIED requires affirmative reviewer verification")
    if search.reviewer_conclusion is not ReviewerConclusion.NO_RESOLUTION_AFTER_DESCENDANT_AUDIT:
        raise ValueError("OPEN_VERIFIED requires a descendant-audit reviewer conclusion")
    if search.confidence not in {SearchConfidence.HIGH, SearchConfidence.MEDIUM}:
        raise ValueError("OPEN_VERIFIED requires HIGH or MEDIUM reviewer confidence")


def validate_open_problem(extraction: OpenProblemExtraction, source_note: NoteRecord) -> ValidatedOpenProblem:
    if not isinstance(extraction, OpenProblemExtraction):
        raise ValueError("extraction must be an OpenProblemExtraction")
    validate_note(source_note)
    validate_evidence_membership(extraction.evidence, source_note)
    if not extraction.evidence.verified:
        raise ValueError("open-problem evidence must be verified")
    supported_scope, supported_result, claimed_restricted, remaining_scope = _open_problem_support(extraction.evidence)
    if extraction.scope != supported_scope:
        raise ValueError("open-problem scope does not match its structured evidence claim")
    if extraction.requested_result != supported_result:
        raise ValueError("open-problem requested result does not match its structured evidence claim")
    if extraction.explicitness is OpenProblemExplicitness.EXPLICIT:
        if extraction.evidence.evidence_type not in {EvidenceType.OPEN_PROBLEM, EvidenceType.FUTURE_WORK}:
            raise ValueError("EXPLICIT open problem requires verified OPEN_PROBLEM or FUTURE_WORK evidence")
        if claimed_restricted is not None:
            raise ValueError("EXPLICIT open problem cannot carry an implicit restricted scope")
        if extraction.restricted_case_evidence is not None or extraction.unresolved_case_evidence is not None:
            raise ValueError("restricted/unresolved evidence fields require IMPLICIT_GAP")
    else:
        restricted_pointer = extraction.restricted_case_evidence
        remaining_pointer = extraction.unresolved_case_evidence
        if restricted_pointer is None or remaining_pointer is None:
            raise ValueError("IMPLICIT_GAP requires restricted-case and unresolved-case evidence")
        validate_evidence_membership(restricted_pointer, source_note)
        validate_evidence_membership(remaining_pointer, source_note)
        if not restricted_pointer.verified or not remaining_pointer.verified:
            raise ValueError("IMPLICIT_GAP evidence must be verified")
        if restricted_pointer.evidence_type is not EvidenceType.THEOREM:
            raise ValueError("IMPLICIT_GAP restricted case requires THEOREM evidence")
        if remaining_pointer.evidence_type not in {EvidenceType.OPEN_PROBLEM, EvidenceType.FUTURE_WORK}:
            raise ValueError("IMPLICIT_GAP remaining case requires OPEN_PROBLEM or FUTURE_WORK evidence")
        if extraction.evidence != remaining_pointer or claimed_restricted is None:
            raise ValueError("IMPLICIT_GAP primary evidence must contain restricted and remaining scopes")
        theorem_scope, theorem_results, _assumptions, _technique = theorem_support(restricted_pointer)
        if theorem_scope != claimed_restricted:
            raise ValueError("IMPLICIT_GAP restricted scope does not match the theorem evidence")
        if extraction.requested_result not in theorem_results:
            raise ValueError("IMPLICIT_GAP restricted theorem must prove the exact requested result signature")
        if remaining_scope != extraction.scope:
            raise ValueError("IMPLICIT_GAP remaining scope does not match the extracted problem")
        if compare_scopes(theorem_scope, remaining_scope) is not ScopeRelation.NARROWER:
            raise ValueError("IMPLICIT_GAP requires an explicit NARROWER-to-broader generalization relation")
    fingerprint = problem_fingerprint(extraction.problem_id, extraction.scope, extraction.requested_result)
    _validate_open_verified(extraction, fingerprint, source_note)
    return ValidatedOpenProblem(
        problem_id=extraction.problem_id,
        problem_fingerprint=fingerprint,
        paper_id=source_note.paper_id,
        version_id=source_note.version_id,
        paraphrase=extraction.paraphrase,
        scope=extraction.scope,
        requested_result=extraction.requested_result,
        explicitness=extraction.explicitness,
        evidence=extraction.evidence,
        status=extraction.status,
        followup_search=extraction.followup_search,
        restricted_case_evidence=extraction.restricted_case_evidence,
        unresolved_case_evidence=extraction.unresolved_case_evidence,
        _validation_token=_VALIDATED_PROBLEM_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class ResolutionClaim:
    resolution_paper_id: str
    resolution_version_id: str
    explanation: str
    evidence: EvidencePointer

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_paper_id, str) or not self.resolution_paper_id.startswith("paper:"):
            raise ValueError("resolution_paper_id must be a canonical paper ID")
        if not isinstance(self.resolution_version_id, str) or not self.resolution_version_id.startswith("version:"):
            raise ValueError("resolution_version_id must be a canonical version ID")
        object.__setattr__(self, "explanation", _text(self.explanation, "resolution explanation", min_words=6))
        if not isinstance(self.evidence, EvidencePointer):
            raise ValueError("resolution claim requires theorem/result evidence")


@dataclass(frozen=True, slots=True)
class ValidatedResolution:
    problem_id: str
    status: OpenStatus
    claim: ResolutionClaim
    theorem_id: str
    matched_result: TheoremResult
    _validation_token: InitVar[object] = None

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _VALIDATED_RESOLUTION_TOKEN:
            raise ValueError("ValidatedResolution can only be created by validate_resolution")


def _validated_metadata(metadata: VerifiedMetadata, label: str) -> VerifiedMetadata:
    if not isinstance(metadata, VerifiedMetadata):
        raise ValueError(f"{label} requires verified metadata")
    recomputed = verify_metadata(metadata.supporting_observations)
    if recomputed != metadata or metadata.status not in {
        VerificationStatus.VERIFIED,
        VerificationStatus.VERIFIED_WITH_WARNINGS,
    } or "year" not in metadata.verified_fields:
        raise ValueError(f"{label} requires verified metadata with publication-year evidence")
    return metadata


def _validated_family(family: VersionFamily | None) -> VersionFamily | None:
    if family is None:
        return None
    if not isinstance(family, VersionFamily):
        raise ValueError("version_family must be a validated VersionFamily")
    recomputed = resolve_version_family(family.metadata, family.versions, family.lineage)
    if recomputed != family:
        raise ValueError("version_family does not reproduce from verified lineage inputs")
    return family


def _lineage_reaches(family: VersionFamily, source_version: str, target_version: str) -> bool:
    chronological = {
        VersionRelation.PREPRINT_OF,
        VersionRelation.CONFERENCE_OF,
        VersionRelation.JOURNAL_EXTENSION_OF,
        VersionRelation.CORRECTS,
    }
    adjacency: dict[str, set[str]] = {}
    for edge in family.lineage:
        if edge.relation in chronological:
            adjacency.setdefault(edge.source_version_id, set()).add(edge.target_version_id)
    pending = [source_version]
    seen = set(pending)
    while pending:
        current = pending.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor == target_version:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return False


def _later_publication(
    problem: ValidatedOpenProblem,
    claim: ResolutionClaim,
    source_metadata: VerifiedMetadata,
    resolution_metadata: VerifiedMetadata,
    family: VersionFamily | None,
) -> None:
    source_id = canonical_paper_id(source_metadata)
    resolution_id = canonical_paper_id(resolution_metadata)
    if source_id != problem.paper_id:
        raise ValueError("source verified metadata does not identify the original problem paper")
    if resolution_id != claim.resolution_paper_id:
        raise ValueError("resolution verified metadata does not identify the claimed paper")
    if source_id != resolution_id:
        if resolution_metadata.year <= source_metadata.year:
            raise ValueError("resolution requires a verified later publication")
        return
    if family is None or family.paper_id != source_id:
        raise ValueError("same-paper resolution requires verified version lineage")
    if not _lineage_reaches(family, problem.version_id, claim.resolution_version_id):
        raise ValueError("version lineage does not prove the resolution version is later")
    versions = {item.version_id: item for item in family.versions}
    if problem.version_id not in versions or claim.resolution_version_id not in versions:
        raise ValueError("version lineage is missing a claimed publication endpoint")
    source_year = versions[problem.version_id].source_observation.year
    resolution_year = versions[claim.resolution_version_id].source_observation.year
    if resolution_year <= source_year:
        raise ValueError(
            "resolution requires a strictly later verified publication year; equal-year versions need verified dates"
        )


def _explanation_matches(explanation: str, result: TheoremResult) -> bool:
    normalized = " ".join(re.sub(r"[^\w]+", " ", explanation.casefold()).split())
    required = (
        result.complexity_class,
        result.measure.value.replace("_", " "),
        result.direction.value.replace("_", " "),
    )
    return all(" ".join(re.sub(r"[^\w]+", " ", item.casefold()).split()) in normalized for item in required)


def validate_resolution(
    problem: ValidatedOpenProblem,
    claim: ResolutionClaim,
    resolution_note: NoteRecord,
    theorem: ValidatedTheorem | None,
    *,
    source_metadata: VerifiedMetadata,
    resolution_metadata: VerifiedMetadata,
    version_family: VersionFamily | None = None,
) -> ValidatedResolution:
    if not isinstance(problem, ValidatedOpenProblem):
        raise ValueError("problem must be a ValidatedOpenProblem")
    if not isinstance(claim, ResolutionClaim):
        raise ValueError("claim must be a ResolutionClaim")
    validate_note(resolution_note)
    if theorem is None or not isinstance(theorem, ValidatedTheorem):
        raise ValueError("RESOLVED or PARTIALLY_RESOLVED requires a validated theorem")
    if theorem.authorization.certificate != coverage_certificate(resolution_note):
        raise ValueError("resolution note certificate does not match the theorem authorization")
    note_source = (resolution_note.paper_id, resolution_note.version_id)
    claim_source = (claim.resolution_paper_id, claim.resolution_version_id)
    theorem_source = (theorem.paper_id, theorem.version_id)
    if claim_source != note_source or theorem_source != note_source:
        raise ValueError("resolution claim, note, and theorem must identify the same source")
    source_verified = _validated_metadata(source_metadata, "source publication")
    resolution_verified = _validated_metadata(resolution_metadata, "resolution publication")
    family = _validated_family(version_family)
    _later_publication(problem, claim, source_verified, resolution_verified, family)
    validate_evidence_membership(claim.evidence, resolution_note)
    if not claim.evidence.verified or claim.evidence.evidence_type is not EvidenceType.THEOREM:
        raise ValueError("resolution requires exact verified theorem evidence")
    if claim.evidence != theorem.evidence:
        raise ValueError("resolution evidence must be the validated theorem member")
    if problem.requested_result not in theorem.results:
        raise ValueError("resolution theorem does not match the open problem requested result signature")
    relation = compare_scopes(theorem.scope, problem.scope)
    if relation is ScopeRelation.EQUAL:
        status = OpenStatus.RESOLVED
    elif relation is ScopeRelation.NARROWER:
        status = OpenStatus.PARTIALLY_RESOLVED
    else:
        raise ValueError(f"resolution theorem scope relation is {relation.value}, not EQUAL or NARROWER")
    if not _explanation_matches(claim.explanation, problem.requested_result):
        raise ValueError("resolution explanation must name the matched result class, measure, and direction")
    return ValidatedResolution(
        problem.problem_id,
        status,
        claim,
        theorem.theorem_id,
        problem.requested_result,
        _validation_token=_VALIDATED_RESOLUTION_TOKEN,
    )
