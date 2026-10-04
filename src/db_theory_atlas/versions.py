"""Evidence-gated version-family resolution for registered papers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable
from urllib.parse import urlparse

from .sources import (
    SourceObservation,
    VerifiedMetadata,
    _normalize_authors,
    _normalize_text,
    canonical_paper_id,
    normalize_doi,
    normalize_url,
)


class VersionKind(str, Enum):
    PREPRINT = "PREPRINT"
    CONFERENCE = "CONFERENCE"
    JOURNAL = "JOURNAL"
    OTHER = "OTHER"


class VersionRelation(str, Enum):
    SAME_WORK = "SAME_WORK"
    PREPRINT_OF = "PREPRINT_OF"
    CONFERENCE_OF = "CONFERENCE_OF"
    JOURNAL_EXTENSION_OF = "JOURNAL_EXTENSION_OF"
    CORRECTS = "CORRECTS"
    UNKNOWN_RELATED = "UNKNOWN_RELATED"


class LineageEvidenceKind(str, Enum):
    """The evidentiary basis that permits a version relation."""

    DOI_RELATION = "DOI_RELATION"
    EXPLICIT_VERSION_STATEMENT = "EXPLICIT_VERSION_STATEMENT"
    HIGH_CONFIDENCE_METADATA = "HIGH_CONFIDENCE_METADATA"


VersionRelationType = VersionRelation
_ID_PATTERN = re.compile(r"^version:[a-z0-9][a-z0-9._-]*$")


def _require_version_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a stable neutral version ID")


def _require_url(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty http(s) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL")


@dataclass(frozen=True, slots=True)
class VersionObservation:
    """A concrete preprint, conference, journal, or other paper manifestation."""

    version_id: str
    kind: VersionKind
    source_observation: SourceObservation
    version_url: str

    def __post_init__(self) -> None:
        _require_version_id(self.version_id, "version_id")
        if not isinstance(self.kind, VersionKind):
            raise ValueError("kind must be a VersionKind")
        if not isinstance(self.source_observation, SourceObservation):
            raise ValueError("source_observation must be a SourceObservation")
        _require_url(self.version_url, "version_url")


@dataclass(frozen=True, slots=True)
class VersionLineage:
    """A directed, evidence-backed relationship between two registered versions."""

    source_version_id: str
    target_version_id: str
    relation: VersionRelation
    evidence_urls: tuple[str, ...]
    evidence_kind: LineageEvidenceKind = LineageEvidenceKind.HIGH_CONFIDENCE_METADATA

    def __post_init__(self) -> None:
        _require_version_id(self.source_version_id, "source_version_id")
        _require_version_id(self.target_version_id, "target_version_id")
        if self.source_version_id == self.target_version_id:
            raise ValueError("version lineage cannot be self-referential")
        if not isinstance(self.relation, VersionRelation):
            raise ValueError("relation must be a VersionRelation")
        if not isinstance(self.evidence_kind, LineageEvidenceKind):
            raise ValueError("evidence_kind must be a LineageEvidenceKind")
        if not isinstance(self.evidence_urls, tuple) or not self.evidence_urls:
            raise ValueError("version lineage requires evidence URLs")
        for evidence_url in self.evidence_urls:
            _require_url(evidence_url, "lineage evidence URL")


@dataclass(frozen=True, slots=True)
class VersionFamily:
    paper_id: str
    metadata: VerifiedMetadata
    versions: tuple[VersionObservation, ...]
    lineage: tuple[VersionLineage, ...]

    @property
    def lineages(self) -> tuple[VersionLineage, ...]:
        return self.lineage


def _lineage_key(lineage: VersionLineage) -> tuple[object, ...]:
    return (
        lineage.source_version_id,
        lineage.target_version_id,
        lineage.relation.value,
        lineage.evidence_kind.value,
        tuple(normalize_url(url) for url in lineage.evidence_urls),
    )


def _has_cycle(lineage: tuple[VersionLineage, ...]) -> bool:
    adjacency: dict[str, set[str]] = {}
    for edge in lineage:
        adjacency.setdefault(edge.source_version_id, set()).add(edge.target_version_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in adjacency.get(node, ())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in tuple(adjacency))


def _high_confidence_same_work(metadata: VerifiedMetadata, version: VersionObservation) -> bool:
    observation = version.source_observation
    if not observation.evidence_url or _normalize_text(observation.observed_title) != _normalize_text(metadata.title):
        return False
    if _normalize_authors(observation.authors) != _normalize_authors(metadata.authors):
        return False
    metadata_doi = normalize_doi(metadata.doi)
    observation_doi = normalize_doi(observation.doi)
    return metadata_doi is None or observation_doi is None or metadata_doi == observation_doi


def _is_metadata_anchor(metadata: VerifiedMetadata, version: VersionObservation) -> bool:
    """Require both verified identity and a source URL already supporting metadata."""

    if not _high_confidence_same_work(metadata, version):
        return False
    metadata_urls: set[str] = set()
    for observation in metadata.supporting_observations:
        metadata_urls.add(normalize_url(observation.evidence_url))
        if observation.official_url is not None:
            metadata_urls.add(normalize_url(observation.official_url))
        if observation.preprint_url is not None:
            metadata_urls.add(normalize_url(observation.preprint_url))
    candidate = version.source_observation
    candidate_urls = {normalize_url(candidate.evidence_url)}
    if candidate.official_url is not None:
        candidate_urls.add(normalize_url(candidate.official_url))
    if candidate.preprint_url is not None:
        candidate_urls.add(normalize_url(candidate.preprint_url))
    return bool(metadata_urls & candidate_urls)


def _known_evidence_urls(version: VersionObservation) -> set[str]:
    observation = version.source_observation
    urls = {normalize_url(version.version_url), normalize_url(observation.evidence_url)}
    if observation.official_url is not None:
        urls.add(normalize_url(observation.official_url))
    if observation.preprint_url is not None:
        urls.add(normalize_url(observation.preprint_url))
    return urls


def _relation_kinds_are_plausible(source: VersionObservation, target: VersionObservation, relation: VersionRelation) -> bool:
    if relation in {VersionRelation.SAME_WORK, VersionRelation.CORRECTS, VersionRelation.UNKNOWN_RELATED}:
        return True
    if relation is VersionRelation.PREPRINT_OF:
        return source.kind is VersionKind.PREPRINT and target.kind in {
            VersionKind.CONFERENCE,
            VersionKind.JOURNAL,
            VersionKind.OTHER,
        }
    if relation is VersionRelation.CONFERENCE_OF:
        return source.kind is VersionKind.CONFERENCE and target.kind in {VersionKind.JOURNAL, VersionKind.OTHER}
    if relation is VersionRelation.JOURNAL_EXTENSION_OF:
        return source.kind in {VersionKind.PREPRINT, VersionKind.CONFERENCE} and target.kind is VersionKind.JOURNAL
    return False


def _validate_lineage_evidence(
    metadata: VerifiedMetadata, relation: VersionLineage, versions_by_id: dict[str, VersionObservation]
) -> None:
    source = versions_by_id[relation.source_version_id]
    target = versions_by_id[relation.target_version_id]
    if not _relation_kinds_are_plausible(source, target, relation.relation):
        raise ValueError("version lineage relation is not plausible for the version kinds")
    endpoint_urls = _known_evidence_urls(source) | _known_evidence_urls(target)
    if not all(normalize_url(url) in endpoint_urls for url in relation.evidence_urls):
        raise ValueError("version lineage evidence must be attached to a relation endpoint")
    if relation.evidence_kind is LineageEvidenceKind.HIGH_CONFIDENCE_METADATA:
        if not (_high_confidence_same_work(metadata, source) and _high_confidence_same_work(metadata, target)):
            raise ValueError("high-confidence lineage requires identity evidence for both versions")
    elif relation.evidence_kind is LineageEvidenceKind.DOI_RELATION:
        if normalize_doi(source.source_observation.doi) is None or normalize_doi(target.source_observation.doi) is None:
            raise ValueError("DOI lineage requires DOI identity evidence for both versions")


def _connected_to_anchors(
    anchors: set[str], version_ids: set[str], lineage: tuple[VersionLineage, ...]
) -> set[str]:
    adjacency: dict[str, set[str]] = {version_id: set() for version_id in version_ids}
    for relation in lineage:
        adjacency[relation.source_version_id].add(relation.target_version_id)
        adjacency[relation.target_version_id].add(relation.source_version_id)
    reachable = set(anchors)
    pending = list(anchors)
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                pending.append(neighbor)
    return reachable


def resolve_version_family(
    metadata: VerifiedMetadata,
    version_observations: Iterable[VersionObservation],
    lineage: Iterable[VersionLineage] = (),
) -> VersionFamily:
    """Resolve only a metadata-anchored, evidence-connected version family.

    At least one observation must match the supplied verified metadata and one
    of its supporting URLs. Every other member must reach such an anchor through
    acyclic, relation-kind-plausible lineage with evidence attached to an
    endpoint. A title variant is permitted only when its explicit or DOI
    relation evidence passes those checks; unlinked observations are rejected.
    """

    if not isinstance(metadata, VerifiedMetadata):
        raise ValueError("metadata must be VerifiedMetadata")
    versions = tuple(version_observations)
    if not versions:
        raise ValueError("version family requires at least one version")
    if any(not isinstance(version, VersionObservation) for version in versions):
        raise ValueError("version_observations must be VersionObservation records")
    version_ids = tuple(version.version_id for version in versions)
    if len(set(version_ids)) != len(version_ids):
        raise ValueError("duplicate version IDs are not allowed")
    normalized_urls = tuple(normalize_url(version.version_url) for version in versions)
    if len(set(normalized_urls)) != len(normalized_urls):
        raise ValueError("duplicate versions cannot share a version URL")
    relations = tuple(lineage)
    if any(not isinstance(item, VersionLineage) for item in relations):
        raise ValueError("lineage must contain VersionLineage records")
    if len(set(relations)) != len(relations):
        raise ValueError("duplicate version lineage is not allowed")
    known_ids = set(version_ids)
    if any(item.source_version_id not in known_ids or item.target_version_id not in known_ids for item in relations):
        raise ValueError("version lineage must reference registered versions")
    if _has_cycle(relations):
        raise ValueError("version lineage cycle is not allowed")
    versions_by_id = {version.version_id: version for version in versions}
    for relation in relations:
        _validate_lineage_evidence(metadata, relation, versions_by_id)
    anchors = {version.version_id for version in versions if _is_metadata_anchor(metadata, version)}
    if not anchors:
        raise ValueError("version family requires a version anchored to verified metadata identity evidence")
    if _connected_to_anchors(anchors, known_ids, relations) != known_ids:
        raise ValueError("every version must be connected to an anchored version")
    return VersionFamily(
        paper_id=canonical_paper_id(metadata),
        metadata=metadata,
        versions=tuple(sorted(versions, key=lambda version: version.version_id)),
        lineage=tuple(sorted(relations, key=_lineage_key)),
    )
