"""Deterministic, evidence-backed source metadata reconciliation.

This module deliberately separates the value chosen for display from the
evidence that supports it.  Source precedence selects a usable value, but a
contradiction is retained as a ``MetadataConflict`` instead of being erased.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import re
from typing import Iterable
import unicodedata
from urllib.parse import urlsplit, urlunsplit


class SourceAuthority(str, Enum):
    """Trust tiers used only to select a display value, never to hide conflict."""

    PRIMARY = "PRIMARY"
    AUTHOR_FULL_TEXT = "AUTHOR_FULL_TEXT"
    CROSS_CHECK = "CROSS_CHECK"
    DISCOVERY = "DISCOVERY"


class SourceKind(str, Enum):
    OFFICIAL_PROCEEDINGS = "OFFICIAL_PROCEEDINGS"
    PUBLISHER = "PUBLISHER"
    DOI_METADATA = "DOI_METADATA"
    AUTHOR_FULL_TEXT = "AUTHOR_FULL_TEXT"
    ARXIV_FULL_TEXT = "ARXIV_FULL_TEXT"
    DBLP = "DBLP"
    SEARCH_DISCOVERY = "SEARCH_DISCOVERY"

    # A concise spelling for callers that do not need to distinguish a
    # proceedings page from other official metadata.
    OFFICIAL = "OFFICIAL_PROCEEDINGS"
    CROSSREF = "DOI_METADATA"
    ARXIV = "ARXIV_FULL_TEXT"
    AUTHOR = "AUTHOR_FULL_TEXT"
    SEARCH = "SEARCH_DISCOVERY"

    @property
    def authority(self) -> SourceAuthority:
        return _SOURCE_AUTHORITIES[self]


class ConflictSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class YearStatus(str, Enum):
    """What the observed year denotes; UNKNOWN never licenses a year warning."""

    UNKNOWN = "UNKNOWN"
    ONLINE_FIRST = "ONLINE_FIRST"
    ISSUE_PUBLICATION = "ISSUE_PUBLICATION"

    ISSUE = "ISSUE_PUBLICATION"
    PUBLICATION = "ISSUE_PUBLICATION"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    VERIFIED_WITH_WARNINGS = "VERIFIED_WITH_WARNINGS"
    CONFLICTED = "CONFLICTED"
    UNVERIFIED = "UNVERIFIED"


_SOURCE_AUTHORITIES = {
    SourceKind.OFFICIAL_PROCEEDINGS: SourceAuthority.PRIMARY,
    SourceKind.PUBLISHER: SourceAuthority.PRIMARY,
    SourceKind.DOI_METADATA: SourceAuthority.PRIMARY,
    SourceKind.AUTHOR_FULL_TEXT: SourceAuthority.AUTHOR_FULL_TEXT,
    SourceKind.ARXIV_FULL_TEXT: SourceAuthority.AUTHOR_FULL_TEXT,
    SourceKind.DBLP: SourceAuthority.CROSS_CHECK,
    SourceKind.SEARCH_DISCOVERY: SourceAuthority.DISCOVERY,
}
_AUTHORITY_RANK = {
    SourceAuthority.PRIMARY: 0,
    SourceAuthority.AUTHOR_FULL_TEXT: 1,
    SourceAuthority.CROSS_CHECK: 2,
    SourceAuthority.DISCOVERY: 3,
}
_SOURCE_KIND_RANK = {
    SourceKind.OFFICIAL_PROCEEDINGS: 0,
    SourceKind.PUBLISHER: 1,
    SourceKind.DOI_METADATA: 2,
    SourceKind.AUTHOR_FULL_TEXT: 3,
    SourceKind.ARXIV_FULL_TEXT: 4,
    SourceKind.DBLP: 5,
    SourceKind.SEARCH_DISCOVERY: 6,
}
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)


def _require_url(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty http(s) URL")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL")
    try:
        if not parsed.hostname:
            raise ValueError(f"{label} must be an http(s) URL")
        parsed.port
    except ValueError as error:
        raise ValueError(f"{label} must be an http(s) URL") from error


def _require_optional_url(value: str | None, label: str) -> None:
    if value is not None:
        _require_url(value, label)


def normalize_url(value: str) -> str:
    """Normalize comparison-only URL components without changing path/query case.

    URL scheme and host are case-insensitive, while a publisher's path and
    query can be case-sensitive.  Default HTTP(S) ports therefore normalize
    away; everything after the authority is preserved byte-for-byte.
    """

    _require_url(value, "url")
    parsed = urlsplit(value.strip())
    hostname = parsed.hostname
    assert hostname is not None  # established by _require_url
    host = hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port
    default_port = (parsed.scheme.casefold() == "http" and port == 80) or (
        parsed.scheme.casefold() == "https" and port == 443
    )
    authority = host if port is None or default_port else f"{host}:{port}"
    if "@" in parsed.netloc:
        userinfo = parsed.netloc.rsplit("@", 1)[0]
        authority = f"{userinfo}@{authority}"
    return urlunsplit((parsed.scheme.casefold(), authority, parsed.path, parsed.query, parsed.fragment))


def normalize_doi(value: str | None) -> str | None:
    """Normalize a DOI for comparison while leaving observation display text intact."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("doi must be a string or None")
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.IGNORECASE).lower()
    if not _DOI_PATTERN.fullmatch(normalized):
        raise ValueError("doi is not valid")
    return normalized


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE).split())


def _normalize_authors(authors: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize_text(author) for author in authors)


def _observation_key(observation: "SourceObservation") -> tuple[object, ...]:
    return (
        _AUTHORITY_RANK[observation.source.authority],
        _SOURCE_KIND_RANK[observation.source],
        _normalize_text(observation.observed_title),
        _normalize_authors(observation.authors),
        observation.year,
        _normalize_text(observation.venue) if observation.venue is not None else "",
        normalize_doi(observation.doi) or "",
        normalize_url(observation.official_url) if observation.official_url is not None else "",
        normalize_url(observation.preprint_url) if observation.preprint_url is not None else "",
        _normalize_text(observation.volume) if observation.volume is not None else "",
        _normalize_text(observation.issue) if observation.issue is not None else "",
        _normalize_text(observation.pages) if observation.pages is not None else "",
        observation.year_status.value,
        normalize_url(observation.year_evidence_url) if observation.year_evidence_url is not None else "",
        observation.observed_at.isoformat(),
        normalize_url(observation.evidence_url),
        # Comparison normalization intentionally equates spelling variants
        # (for example, host case).  The raw-value tail makes display-value
        # selection total even when all normalized scientific fields tie.
        observation.observed_title,
        observation.authors,
        observation.venue or "",
        observation.doi or "",
        observation.official_url or "",
        observation.preprint_url or "",
        observation.volume or "",
        observation.issue or "",
        observation.pages or "",
        observation.year_evidence_url or "",
        observation.evidence_url,
    )


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """Metadata observed in one citable source at one point in time."""

    source: SourceKind
    observed_title: str
    authors: tuple[str, ...]
    year: int
    observed_at: date
    evidence_url: str
    venue: str | None = None
    doi: str | None = None
    official_url: str | None = None
    preprint_url: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    year_status: YearStatus = YearStatus.UNKNOWN
    year_evidence_url: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceKind):
            raise ValueError("source must be a SourceKind")
        if not isinstance(self.observed_title, str) or not self.observed_title.strip():
            raise ValueError("observed_title must be nonempty")
        if not isinstance(self.authors, tuple) or not self.authors:
            raise ValueError("authors must be an ordered nonempty tuple")
        if any(not isinstance(author, str) or not author.strip() for author in self.authors):
            raise ValueError("authors must contain nonempty names")
        if isinstance(self.year, bool) or not isinstance(self.year, int) or not 1900 <= self.year <= 2100:
            raise ValueError("year must be in the supported range")
        for label in ("venue", "volume", "issue", "pages"):
            value = getattr(self, label)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{label} must be nonempty when present")
        normalize_doi(self.doi)
        _require_optional_url(self.official_url, "official_url")
        _require_optional_url(self.preprint_url, "preprint_url")
        if not isinstance(self.year_status, YearStatus):
            raise ValueError("year_status must be a YearStatus")
        if self.year_status is YearStatus.UNKNOWN:
            if self.year_evidence_url is not None:
                raise ValueError("year_evidence_url requires an explicit year_status")
        else:
            if self.year_evidence_url is None:
                raise ValueError("explicit year_status requires year_evidence_url")
            _require_url(self.year_evidence_url, "year_evidence_url")
        if not isinstance(self.observed_at, date) or isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a date")
        _require_url(self.evidence_url, "evidence_url")

    @property
    def authority(self) -> SourceAuthority:
        return self.source.authority

    @property
    def title(self) -> str:
        """A read-only compatibility alias for the observed title."""

        return self.observed_title


@dataclass(frozen=True, slots=True)
class MetadataConflict:
    field: str
    competing_values: tuple[object, ...]
    sources: tuple[SourceKind, ...]
    severity: ConflictSeverity
    resolution: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.field, str) or not self.field:
            raise ValueError("field must be nonempty")
        if not isinstance(self.competing_values, tuple) or len(self.competing_values) < 2:
            raise ValueError("competing_values must contain at least two values")
        if not isinstance(self.sources, tuple) or not self.sources or any(
            not isinstance(source, SourceKind) for source in self.sources
        ):
            raise ValueError("sources must be SourceKind values")
        if not isinstance(self.severity, ConflictSeverity):
            raise ValueError("severity must be a ConflictSeverity")
        if self.resolution is not None and (not isinstance(self.resolution, str) or not self.resolution.strip()):
            raise ValueError("resolution must be nonempty when present")

    @property
    def values(self) -> tuple[object, ...]:
        return self.competing_values

    @property
    def competing_sources(self) -> tuple[SourceKind, ...]:
        return self.sources


@dataclass(frozen=True, slots=True)
class VerifiedMetadata:
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str | None
    doi: str | None
    official_url: str | None
    preprint_url: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    supporting_observations: tuple[SourceObservation, ...]
    conflicts: tuple[MetadataConflict, ...]
    unresolved_conflicts: tuple[MetadataConflict, ...]
    status: VerificationStatus
    verified_fields: frozenset[str]

    @property
    def verification_status(self) -> VerificationStatus:
        return self.status

    @property
    def normalized_doi(self) -> str | None:
        return normalize_doi(self.doi)


_FIELD_NORMALIZERS = {
    "title": _normalize_text,
    "authors": _normalize_authors,
    "year": lambda value: value,
    "venue": _normalize_text,
    "doi": normalize_doi,
    "official_url": normalize_url,
    "preprint_url": normalize_url,
    "volume": _normalize_text,
    "issue": _normalize_text,
    "pages": _normalize_text,
}
_OBSERVATION_FIELDS = {
    "title": "observed_title",
    "authors": "authors",
    "year": "year",
    "venue": "venue",
    "doi": "doi",
    "official_url": "official_url",
    "preprint_url": "preprint_url",
    "volume": "volume",
    "issue": "issue",
    "pages": "pages",
}


def _values_for_field(observations: tuple[SourceObservation, ...], field: str) -> list[tuple[SourceObservation, object, object]]:
    attribute = _OBSERVATION_FIELDS[field]
    normalizer = _FIELD_NORMALIZERS[field]
    values = []
    for observation in observations:
        value = getattr(observation, attribute)
        if value is not None:
            values.append((observation, value, normalizer(value)))
    return values


def _distinct_values(values: list[tuple[SourceObservation, object, object]]) -> list[tuple[object, tuple[SourceObservation, ...]]]:
    buckets: list[tuple[object, list[SourceObservation]]] = []
    for observation, _display, comparable in values:
        for bucket_value, sources in buckets:
            if comparable == bucket_value:
                sources.append(observation)
                break
        else:
            buckets.append((comparable, [observation]))
    return [(value, tuple(sorted(sources, key=_observation_key))) for value, sources in buckets]


def _conflict_for_field(
    field: str, values: list[tuple[SourceObservation, object, object]]
) -> MetadataConflict | None:
    distinct = _distinct_values(values)
    if len(distinct) < 2:
        return None
    ordered_values = sorted(values, key=lambda item: _observation_key(item[0]))
    displays: list[object] = []
    sources: list[SourceKind] = []
    comparable_seen: list[object] = []
    for observation, display, comparable in ordered_values:
        if comparable not in comparable_seen:
            comparable_seen.append(comparable)
            displays.append(display)
        if observation.source not in sources:
            sources.append(observation.source)
    is_online_first = _is_supported_online_first_difference(field, values)
    if is_online_first:
        return MetadataConflict(
            field=field,
            competing_values=tuple(displays),
            sources=tuple(sources),
            severity=ConflictSeverity.WARNING,
            resolution="online-first and issue-year difference retained as a warning",
        )
    return MetadataConflict(
        field=field,
        competing_values=tuple(displays),
        sources=tuple(sources),
        severity=ConflictSeverity.CRITICAL,
        resolution=None,
    )


def _is_supported_online_first_difference(
    field: str, values: list[tuple[SourceObservation, object, object]]
) -> bool:
    """Recognize only explicitly evidenced, one-year online-first differences."""

    if field != "year":
        return False
    years = {display for _observation, display, _comparable in values}
    if len(years) != 2 or any(not isinstance(year, int) for year in years) or max(years) - min(years) != 1:
        return False
    online_first_years: set[int] = set()
    issue_publication_years: set[int] = set()
    for observation, _display, _comparable in values:
        if observation.year_evidence_url is None:
            return False
        if observation.source is SourceKind.DOI_METADATA and observation.year_status is YearStatus.ONLINE_FIRST:
            online_first_years.add(observation.year)
        elif (
            observation.source in {SourceKind.PUBLISHER, SourceKind.OFFICIAL_PROCEEDINGS}
            and observation.year_status is YearStatus.ISSUE_PUBLICATION
        ):
            issue_publication_years.add(observation.year)
        else:
            return False
    if len(online_first_years) != 1 or len(issue_publication_years) != 1:
        return False
    online_first_year = next(iter(online_first_years))
    issue_publication_year = next(iter(issue_publication_years))
    return online_first_year < issue_publication_year and issue_publication_year - online_first_year == 1


def _doi_target_conflict(observations: tuple[SourceObservation, ...]) -> MetadataConflict | None:
    doi_to_titles: dict[str, list[tuple[SourceObservation, str]]] = {}
    for observation in observations:
        doi = normalize_doi(observation.doi)
        if doi is not None:
            doi_to_titles.setdefault(doi, []).append((observation, _normalize_text(observation.observed_title)))
    bad_groups = [items for items in doi_to_titles.values() if len({title for _observation, title in items}) > 1]
    if not bad_groups:
        return None
    items = sorted((item for group in bad_groups for item in group), key=lambda item: _observation_key(item[0]))
    values: list[object] = []
    sources: list[SourceKind] = []
    seen_titles: set[str] = set()
    for observation, title in items:
        if title not in seen_titles:
            values.append(observation.observed_title)
            seen_titles.add(title)
        if observation.source not in sources:
            sources.append(observation.source)
    return MetadataConflict("doi_target", tuple(values), tuple(sources), ConflictSeverity.CRITICAL, None)


def verify_metadata(observations: Iterable[SourceObservation]) -> VerifiedMetadata:
    """Reconcile observations deterministically without concealing disagreement."""

    materialized = tuple(observations)
    if not materialized:
        raise ValueError("at least one source observation is required")
    if any(not isinstance(observation, SourceObservation) for observation in materialized):
        raise ValueError("observations must be SourceObservation records")
    ordered = tuple(sorted(materialized, key=_observation_key))

    selected: dict[str, object | None] = {}
    conflicts: list[MetadataConflict] = []
    verified_fields: set[str] = set()
    for field in _OBSERVATION_FIELDS:
        values = _values_for_field(ordered, field)
        if not values:
            selected[field] = None
            continue
        best_observation, display, _normalized = min(values, key=lambda item: _observation_key(item[0]))
        selected[field] = display
        conflict = _conflict_for_field(field, values)
        if conflict is not None:
            conflicts.append(conflict)
        if best_observation.authority is SourceAuthority.PRIMARY:
            verified_fields.add(field)
    target_conflict = _doi_target_conflict(ordered)
    if target_conflict is not None:
        conflicts.append(target_conflict)
    conflicts.sort(key=lambda conflict: (conflict.field, conflict.severity.value, repr(conflict.competing_values)))
    unresolved = tuple(conflict for conflict in conflicts if conflict.resolution is None)
    if unresolved:
        status = VerificationStatus.CONFLICTED
    elif conflicts:
        status = VerificationStatus.VERIFIED_WITH_WARNINGS
    elif SourceAuthority.PRIMARY in {observation.authority for observation in ordered}:
        status = VerificationStatus.VERIFIED
    else:
        status = VerificationStatus.UNVERIFIED
    return VerifiedMetadata(
        title=selected["title"],  # type: ignore[arg-type]
        authors=selected["authors"],  # type: ignore[arg-type]
        year=selected["year"],  # type: ignore[arg-type]
        venue=selected["venue"],  # type: ignore[arg-type]
        doi=selected["doi"],  # type: ignore[arg-type]
        official_url=selected["official_url"],  # type: ignore[arg-type]
        preprint_url=selected["preprint_url"],  # type: ignore[arg-type]
        volume=selected["volume"],  # type: ignore[arg-type]
        issue=selected["issue"],  # type: ignore[arg-type]
        pages=selected["pages"],  # type: ignore[arg-type]
        supporting_observations=ordered,
        conflicts=tuple(conflicts),
        unresolved_conflicts=unresolved,
        status=status,
        verified_fields=frozenset(verified_fields),
    )


def canonical_paper_id(metadata: VerifiedMetadata) -> str:
    """Return a neutral, stable paper identifier from verified metadata only."""

    if not isinstance(metadata, VerifiedMetadata):
        raise ValueError("metadata must be VerifiedMetadata")
    normalized_doi = normalize_doi(metadata.doi)
    if normalized_doi is not None and "doi" in metadata.verified_fields and not any(
        conflict.field in {"doi", "doi_target"} and conflict.severity is ConflictSeverity.CRITICAL
        for conflict in metadata.unresolved_conflicts
    ):
        digest = hashlib.sha256(normalized_doi.encode("utf-8")).hexdigest()[:24]
        return f"paper:doi-{digest}"
    payload = "\x1f".join((_normalize_text(metadata.title), _normalize_text(metadata.authors[0]), str(metadata.year)))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"paper:title-{digest}"
