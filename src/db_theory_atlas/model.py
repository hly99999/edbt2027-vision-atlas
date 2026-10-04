"""Frozen, evidence-gated records for the Frontier Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import TYPE_CHECKING, Final, Mapping
from urllib.parse import urlparse

from .paths import contains_absolute_local_path
from .serialization import freeze_json

if TYPE_CHECKING:
    from .evidence import TheoremAuthorization


class ReadDepth(str, Enum):
    METADATA = "METADATA"
    ABSTRACT = "ABSTRACT"
    INTRO_CONCLUSION = "INTRO_CONCLUSION"
    FULL_SCAN = "FULL_SCAN"
    DEEP_READ = "DEEP_READ"


class EvidenceType(str, Enum):
    METADATA = "METADATA"
    ABSTRACT = "ABSTRACT"
    PROBLEM_DEFINITION = "PROBLEM_DEFINITION"
    THEOREM = "THEOREM"
    OPEN_PROBLEM = "OPEN_PROBLEM"
    LIMITATION = "LIMITATION"
    FUTURE_WORK = "FUTURE_WORK"
    RESOLUTION = "RESOLUTION"
    GRAPH_RELATION = "GRAPH_RELATION"


class OpenStatus(str, Enum):
    OPEN_VERIFIED = "OPEN_VERIFIED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLVED = "RESOLVED"
    LIKELY_OPEN = "LIKELY_OPEN"
    UNKNOWN = "UNKNOWN"


class FullTextStatus(str, Enum):
    METADATA_ONLY = "METADATA_ONLY"
    AVAILABLE = "AVAILABLE"


class EdgeDirection(str, Enum):
    DIRECTED = "DIRECTED"
    UNDIRECTED = "UNDIRECTED"


class EdgeStrength(str, Enum):
    DIRECT = "DIRECT"
    STRONG = "STRONG"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"
    NONE = "NONE"


_ID_PATTERN: Final = re.compile(r"^(?!(?:arxiv|doi|file|url):)[a-z][a-z0-9_-]*:[a-z0-9][a-z0-9._-]*$")
_DOI_PATTERN: Final = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)
_HASH_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_RELATIONS: Final = frozenset(
    {
        "cites",
        "extends",
        "generalizes",
        "specializes",
        "refines",
        "contradicts",
        "solves",
        "theorem-generalizes",
        "open-problem-solved-by",
    }
)


def _require_schema_version(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("schema_version must be a positive integer")


def _require_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a neutral canonical ID")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty")
    if contains_absolute_local_path(value):
        raise ValueError(f"{label} cannot contain an absolute local path")


def _require_tuple(value: tuple[object, ...], label: str) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_hash(value: str | None, label: str, *, required: bool = False) -> None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required")
        return
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value.lower()):
        raise ValueError(f"{label} must be a SHA-256 hex digest")


def _normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("doi must be a string or None")
    doi = value.strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE).lower()
    if not _DOI_PATTERN.fullmatch(doi):
        raise ValueError("doi is not normalized or valid")
    return doi


def _require_http_url(value: object, label: str) -> None:
    """Validate a required remotely resolvable source URL."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty http(s) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL")


def _validate_optional_http_url(value: str | None, label: str) -> None:
    """Validate an optional remotely resolvable source URL."""

    if value is None:
        return
    _require_http_url(value, label)


@dataclass(frozen=True, slots=True)
class EvidencePointer:
    paper_id: str
    version_id: str
    page: int | None
    heading: str | None
    evidence_type: EvidenceType | str
    paraphrase: str
    source_hash: str
    verified: bool
    claim: Mapping[str, object] | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        if self.page is not None and (isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1):
            raise ValueError("page must be a positive integer or None")
        if self.heading is not None:
            _require_text(self.heading, "heading")
        if self.page is None and self.heading is None:
            raise ValueError("evidence pointer requires a page or heading location")
        if isinstance(self.evidence_type, str):
            try:
                object.__setattr__(self, "evidence_type", EvidenceType(self.evidence_type.upper()))
            except ValueError as caught:
                raise ValueError("evidence_type is not in the controlled taxonomy") from caught
        if not isinstance(self.evidence_type, EvidenceType):
            raise ValueError("evidence_type is not in the controlled taxonomy")
        _require_text(self.paraphrase, "paraphrase")
        _require_hash(self.source_hash, "source_hash", required=True)
        claim_required = self.evidence_type in {
            EvidenceType.THEOREM,
            EvidenceType.OPEN_PROBLEM,
            EvidenceType.FUTURE_WORK,
        }
        if self.claim is None:
            if claim_required:
                raise ValueError("theorem/open-problem evidence requires a structured claim payload")
        else:
            if not isinstance(self.claim, Mapping) or not self.claim:
                raise ValueError("claim must be a nonempty canonical mapping")
            frozen_claim = freeze_json(self.claim)
            if not isinstance(frozen_claim, Mapping):
                raise ValueError("claim must be a canonical mapping")
            object.__setattr__(self, "claim", frozen_claim)
        if not isinstance(self.verified, bool):
            raise ValueError("verified must be a boolean")
        object.__setattr__(self, "source_hash", self.source_hash.lower())


@dataclass(frozen=True, slots=True)
class PaperVersion:
    version_id: str
    paper_id: str
    label: str
    url: str
    full_text_status: FullTextStatus
    source_hash: str | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.version_id, "version_id")
        _require_id(self.paper_id, "paper_id")
        _require_text(self.label, "label")
        _require_http_url(self.url, "url")
        if not isinstance(self.full_text_status, FullTextStatus):
            raise ValueError("full_text_status must be a FullTextStatus")
        _require_hash(self.source_hash, "source_hash")
        if self.full_text_status is FullTextStatus.AVAILABLE and self.source_hash is None:
            raise ValueError("available full text requires a source_hash")
        if self.source_hash is not None:
            object.__setattr__(self, "source_hash", self.source_hash.lower())


@dataclass(frozen=True, slots=True)
class PaperRecord:
    paper_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str | None
    doi: str | None
    official_url: str | None
    preprint_url: str | None
    versions: tuple[PaperVersion, ...]
    full_text_status: FullTextStatus
    read_depth: ReadDepth
    source_pointers: tuple[EvidencePointer, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.paper_id, "paper_id")
        _require_text(self.title, "title")
        _require_tuple(self.authors, "authors")
        if not self.authors:
            raise ValueError("authors must be an ordered nonempty tuple of names")
        for author in self.authors:
            _require_text(author, "author")
        if isinstance(self.year, bool) or not isinstance(self.year, int) or not 1900 <= self.year <= 2100:
            raise ValueError("year must be in the supported range")
        if self.venue is not None:
            _require_text(self.venue, "venue")
        _validate_optional_http_url(self.official_url, "official_url")
        _validate_optional_http_url(self.preprint_url, "preprint_url")
        _require_tuple(self.versions, "versions")
        if any(not isinstance(version, PaperVersion) or version.paper_id != self.paper_id for version in self.versions):
            raise ValueError("versions must belong to this paper")
        if not isinstance(self.full_text_status, FullTextStatus):
            raise ValueError("full_text_status must be a FullTextStatus")
        if not isinstance(self.read_depth, ReadDepth):
            raise ValueError("read_depth must be a ReadDepth")
        available_versions = tuple(
            version for version in self.versions if version.full_text_status is FullTextStatus.AVAILABLE
        )
        if self.full_text_status is FullTextStatus.AVAILABLE and not available_versions:
            raise ValueError("AVAILABLE paper status requires an available version")
        if self.full_text_status is FullTextStatus.METADATA_ONLY and available_versions:
            raise ValueError("METADATA_ONLY paper status cannot contain an available version")
        if self.full_text_status is FullTextStatus.METADATA_ONLY and self.read_depth is not ReadDepth.METADATA:
            raise ValueError("read depth beyond METADATA requires full text")
        _require_tuple(self.source_pointers, "source_pointers")
        version_ids = {version.version_id for version in self.versions}
        if self.source_pointers and not version_ids:
            raise ValueError("source pointers require a registered version")
        for evidence in self.source_pointers:
            if not isinstance(evidence, EvidencePointer) or evidence.paper_id != self.paper_id:
                raise ValueError("source pointer must identify this paper")
            if evidence.version_id not in version_ids:
                raise ValueError("source pointer must identify a registered version")
        object.__setattr__(self, "doi", _normalize_doi(self.doi))


def _validate_evidence_for_source(
    evidence_pointers: tuple[EvidencePointer, ...], paper_id: str, version_id: str, label: str
) -> None:
    _require_tuple(evidence_pointers, label)
    if not evidence_pointers:
        raise ValueError(f"{label} are required for promoted records")
    for pointer in evidence_pointers:
        if not isinstance(pointer, EvidencePointer) or pointer.paper_id != paper_id or pointer.version_id != version_id:
            raise ValueError(f"{label} must identify the source paper and version")


@dataclass(frozen=True, slots=True)
class TheoremRecord:
    theorem_id: str
    paper_id: str
    version_id: str
    paraphrase: str
    complete: bool
    read_depth: ReadDepth
    evidence_pointers: tuple[EvidencePointer, ...]
    promoted: bool = True
    schema_version: int = 1
    authorization: TheoremAuthorization | None = None

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.theorem_id, "theorem_id")
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        _require_text(self.paraphrase, "paraphrase")
        if not isinstance(self.complete, bool) or not isinstance(self.promoted, bool):
            raise ValueError("complete and promoted must be booleans")
        if not isinstance(self.read_depth, ReadDepth):
            raise ValueError("read_depth must be a ReadDepth")
        if self.complete and self.read_depth is not ReadDepth.DEEP_READ:
            raise ValueError("complete theorem extraction requires DEEP_READ")
        _require_tuple(self.evidence_pointers, "evidence_pointers")
        if self.promoted:
            _validate_evidence_for_source(self.evidence_pointers, self.paper_id, self.version_id, "evidence_pointers")
        if self.complete and not any(pointer.evidence_type is EvidenceType.THEOREM for pointer in self.evidence_pointers):
            raise ValueError("complete theorem extraction requires THEOREM evidence")
        if self.complete and any(not pointer.verified for pointer in self.evidence_pointers):
            raise ValueError("complete theorem extraction requires verified evidence")
        if self.complete:
            from .evidence import TheoremAuthorization, validate_theorem_authorization

            if not isinstance(self.authorization, TheoremAuthorization):
                raise ValueError("complete theorem extraction requires validated authorization")
            authorization = validate_theorem_authorization(self.authorization)
            certificate = authorization.certificate
            if (certificate.paper_id, certificate.version_id) != (self.paper_id, self.version_id):
                raise ValueError("theorem authorization must identify the source paper and version")
            if authorization.evidence not in self.evidence_pointers:
                raise ValueError("authorized THEOREM evidence must be attached to the theorem record")


@dataclass(frozen=True, slots=True)
class OpenProblemRecord:
    problem_id: str
    paper_id: str
    version_id: str
    paraphrase: str
    status: OpenStatus
    evidence_pointers: tuple[EvidencePointer, ...]
    resolution_paper_id: str | None = None
    resolution_version_id: str | None = None
    resolution_evidence_pointers: tuple[EvidencePointer, ...] = ()
    promoted: bool = True
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.problem_id, "problem_id")
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        _require_text(self.paraphrase, "paraphrase")
        if not isinstance(self.status, OpenStatus):
            raise ValueError("status must be an OpenStatus")
        if not isinstance(self.promoted, bool):
            raise ValueError("promoted must be a boolean")
        _require_tuple(self.evidence_pointers, "evidence_pointers")
        _require_tuple(self.resolution_evidence_pointers, "resolution_evidence_pointers")
        if self.promoted:
            _validate_evidence_for_source(self.evidence_pointers, self.paper_id, self.version_id, "evidence_pointers")
        if self.status is OpenStatus.RESOLVED:
            if self.resolution_paper_id is None or self.resolution_version_id is None:
                raise ValueError("resolved status requires resolution paper and version")
            _require_id(self.resolution_paper_id, "resolution_paper_id")
            _require_id(self.resolution_version_id, "resolution_version_id")
            _validate_evidence_for_source(
                self.resolution_evidence_pointers,
                self.resolution_paper_id,
                self.resolution_version_id,
                "resolution evidence",
            )
        elif self.resolution_paper_id is not None or self.resolution_version_id is not None or self.resolution_evidence_pointers:
            raise ValueError("resolution fields require RESOLVED status")


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source_id: str
    target_id: str
    relation: str
    direction: EdgeDirection
    strength: EdgeStrength
    evidence_pointers: tuple[EvidencePointer, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_id(self.source_id, "source_id")
        _require_id(self.target_id, "target_id")
        if self.source_id == self.target_id:
            raise ValueError("graph edge endpoints must differ")
        if self.relation not in _ALLOWED_RELATIONS:
            raise ValueError("relation is not in the controlled vocabulary")
        if not isinstance(self.direction, EdgeDirection):
            raise ValueError("direction must be an EdgeDirection")
        if not isinstance(self.strength, EdgeStrength):
            raise ValueError("strength must be an EdgeStrength")
        _require_tuple(self.evidence_pointers, "evidence_pointers")
        if self.strength in {EdgeStrength.DIRECT, EdgeStrength.STRONG} and not self.evidence_pointers:
            raise ValueError("strong graph edges require evidence")
        if any(not isinstance(pointer, EvidencePointer) for pointer in self.evidence_pointers):
            raise ValueError("evidence_pointers must contain EvidencePointer records")
