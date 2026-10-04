"""Auditable full-text validation and offline Task 3 ledger generation.

This module deliberately separates an acquisition attempt from an evidence-backed
reading promotion.  A valid PDF is necessary for a FULL_SCAN, but never
sufficient: notes remain a manual, source-linked scholarly record.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Iterable
import unicodedata

from pypdf import PdfReader

from .serialization import scientific_hash


_HASH = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_CACHE = re.compile(r"^literature/fulltext_cache/[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.pdf$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
IDENTITY_MISMATCH_FAILURE = "expected title or DOI is not present in extractable identity data"
VALIDATION_EXTRACTION_NORMALIZATION = "PYPDF_PAGE_TEXT_JOIN_LF_V1"
READING_EXTRACTION_NORMALIZATION = "PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1"


class AcquisitionStatus(str, Enum):
    """Closed taxonomy for conservative full-text acquisition outcomes."""

    VALID_PDF = "VALID_PDF"
    HTML_OR_CHALLENGE = "HTML_OR_CHALLENGE"
    HTTP_FAILURE = "HTTP_FAILURE"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    INVALID_PDF = "INVALID_PDF"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class PdfValidationStatus(str, Enum):
    VALID = "VALID"
    HTML_OR_CHALLENGE = "HTML_OR_CHALLENGE"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    INVALID_PDF = "INVALID_PDF"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _hash(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value.casefold()


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())


def _identity_compact(value: str) -> str:
    """Normalize extraction-only typography without weakening full-title identity."""

    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", normalized)
    return re.sub(r"[^\w]", "", normalized, flags=re.UNICODE)


def _title_identity_matches(expected_title: str, identity_text: str) -> bool:
    expected = _identity_compact(expected_title)
    words = re.findall(r"\w+", unicodedata.normalize("NFKD", expected_title), flags=re.UNICODE)
    return len(words) >= 2 and len(expected) >= 12 and expected in _identity_compact(identity_text)


def _doi_identity_matches(expected_doi: str, identity_text: str) -> bool:
    return _identity_compact(expected_doi) in _identity_compact(identity_text)


@dataclass(frozen=True, slots=True)
class PdfValidation:
    status: PdfValidationStatus
    content_sha256: str | None
    page_count: int | None
    extracted_characters: int | None
    validation_extraction_sha256: str | None
    validation_extraction_normalization: str | None
    reading_extraction_sha256: str | None
    reading_extraction_normalization: str | None
    title_match: bool
    doi_match: bool | None
    identity_basis: str | None
    failure_reason: str | None

    @property
    def extraction_sha256(self) -> str | None:
        """Backward-compatible name for the validation-time extraction hash."""

        return self.validation_extraction_sha256


def _metadata_value(metadata: object, key: str) -> str:
    if not isinstance(metadata, dict):
        try:
            value = metadata.get(key)  # type: ignore[union-attr]
        except (AttributeError, TypeError):
            return ""
    else:
        value = metadata.get(key)
    return "" if value is None else str(value)


def _author_corroborates(expected_authors: tuple[str, ...], identity_region: str) -> bool:
    region = _identity_compact(identity_region)
    for author in expected_authors:
        tokens = re.findall(r"\w+", unicodedata.normalize("NFKD", author), flags=re.UNICODE)
        candidates = [author]
        if tokens:
            candidates.append(tokens[-1])
        if any(len(_identity_compact(candidate)) >= 4 and _identity_compact(candidate) in region
               for candidate in candidates):
            return True
    return False


def _venue_corroborates(expected_venue: str | None, identity_region: str) -> bool:
    if expected_venue is None:
        return False
    expected = _identity_compact(expected_venue)
    return len(expected) >= 3 and expected in _identity_compact(identity_region)


def validate_pdf_payload(
    payload: bytes,
    *,
    expected_title: str,
    expected_doi: str | None,
    expected_authors: Iterable[str] = (),
    expected_venue: str | None = None,
) -> PdfValidation:
    """Validate bytes before they may be represented as a full-text PDF.

    The reader must be able to extract nonempty page text; metadata alone is
    never enough to call a download a usable scholarly full text.
    """

    title = _text(expected_title, "expected_title")
    doi = _optional_text(expected_doi, "expected_doi")
    authors = tuple(_text(item, "expected_author") for item in expected_authors)
    venue = _optional_text(expected_venue, "expected_venue")
    if not isinstance(payload, bytes):
        raise ValueError("payload must be bytes")
    if payload.lstrip().startswith((b"<", b"<!DOCTYPE", b"{\"error\"")):
        return PdfValidation(PdfValidationStatus.HTML_OR_CHALLENGE, None, None, None, None, None, None, None,
                             False, None, None, "response is HTML, a challenge, or another non-PDF payload")
    if not payload.startswith(b"%PDF-"):
        return PdfValidation(PdfValidationStatus.INVALID_SIGNATURE, None, None, None, None, None, None, None,
                             False, None, None, "missing PDF signature")
    content_hash = hashlib.sha256(payload).hexdigest()
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        page_count = len(reader.pages)
        pages = tuple(page.extract_text() or "" for page in reader.pages)
        text = "\n".join(pages)
        metadata = reader.metadata or {}
    except Exception as caught:  # pypdf exposes several parser-specific exception classes.
        return PdfValidation(PdfValidationStatus.INVALID_PDF, content_hash, None, None, None, None, None, None,
                             False, None, None, f"PDF parser rejected payload: {type(caught).__name__}")
    if page_count < 1:
        return PdfValidation(PdfValidationStatus.INVALID_PDF, content_hash, page_count, 0, None, None, None, None,
                             False, None, None, "PDF contains no pages")
    if not text.strip():
        empty_hash = hashlib.sha256(b"").hexdigest()
        return PdfValidation(PdfValidationStatus.INVALID_PDF, content_hash, page_count, 0,
                             empty_hash, VALIDATION_EXTRACTION_NORMALIZATION,
                             empty_hash, READING_EXTRACTION_NORMALIZATION,
                             False, None, None, "PDF has no extractable page text")
    metadata_text = " ".join(str(value) for value in metadata.values() if value is not None)
    metadata_title = _metadata_value(metadata, "/Title")
    first_page = pages[0]
    trusted_title_region = f"{metadata_title}\n{first_page}"
    trusted_corroboration_region = f"{metadata_text}\n{first_page}"
    title_metadata_match = _title_identity_matches(title, metadata_title)
    title_first_page_match = _title_identity_matches(title, first_page)
    title_match = title_metadata_match or title_first_page_match
    doi_match = None if doi is None else _doi_identity_matches(doi, f"{text}\n{metadata_text}")
    validation_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    reading_text = "\n".join(page.replace("\x00", " ") for page in pages)
    reading_hash = hashlib.sha256(reading_text.encode("utf-8")).hexdigest()
    author_match = _author_corroborates(authors, trusted_corroboration_region)
    venue_match = _venue_corroborates(venue, trusted_corroboration_region)
    identity_basis: str | None = None
    if doi_match is True:
        identity_basis = "DOI_MATCH"
    elif title_match and (author_match or venue_match):
        title_region = "TITLE_METADATA" if title_metadata_match else "TITLE_FIRST_PAGE"
        corroboration = "AUTHOR_CORROBORATION" if author_match else "VENUE_CORROBORATION"
        identity_basis = f"{title_region}+{corroboration}"
    if identity_basis is None:
        return PdfValidation(
            PdfValidationStatus.IDENTITY_MISMATCH, content_hash, page_count, len(text),
            validation_hash, VALIDATION_EXTRACTION_NORMALIZATION,
            reading_hash, READING_EXTRACTION_NORMALIZATION,
            title_match, doi_match, None, IDENTITY_MISMATCH_FAILURE,
        )
    return PdfValidation(
        PdfValidationStatus.VALID, content_hash, page_count, len(text),
        validation_hash, VALIDATION_EXTRACTION_NORMALIZATION,
        reading_hash, READING_EXTRACTION_NORMALIZATION,
        title_match, doi_match, identity_basis, None,
    )


@dataclass(frozen=True, slots=True)
class AcquisitionManifest:
    """Portable per-attempt record; cache locations are repository-relative only."""

    paper_id: str
    version_id: str
    source_url: str
    provider: str
    source_tier: str
    requested_at: str
    observed_at: str
    status: AcquisitionStatus
    http_status: int | None
    media_type: str | None
    byte_count: int | None
    content_sha256: str | None
    license_status: str
    redistribution_status: str
    cache_path: str | None
    failure_reason: str | None
    retry_policy: str
    selected_reading_version: str
    alternatives: tuple[str, ...]
    route_provenance: str | None = None
    page_count: int | None = None
    extracted_characters: int | None = None
    validation_extraction_sha256: str | None = None
    validation_extraction_normalization: str | None = None
    reading_extraction_sha256: str | None = None
    reading_extraction_normalization: str | None = None
    title_match: bool | None = None
    doi_match: bool | None = None
    identity_basis: str | None = None
    attempt_id: str | None = None
    history_origin: str = "RECORDED_OPERATION"

    def __post_init__(self) -> None:
        for label in ("paper_id", "version_id", "source_url", "provider", "source_tier", "license_status",
                      "redistribution_status", "retry_policy", "selected_reading_version"):
            _text(getattr(self, label), label)
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be http(s)")
        if not isinstance(self.status, AcquisitionStatus):
            raise ValueError("status must be an AcquisitionStatus")
        if not _ISO.fullmatch(self.requested_at) or not _ISO.fullmatch(self.observed_at):
            raise ValueError("timestamps must be UTC ISO-8601 seconds")
        if self.http_status is not None and (isinstance(self.http_status, bool) or not 100 <= self.http_status <= 599):
            raise ValueError("http_status must be a HTTP status code or None")
        if self.byte_count is not None and (isinstance(self.byte_count, bool) or self.byte_count < 0):
            raise ValueError("byte_count must be nonnegative or None")
        content_hash = _hash(self.content_sha256, "content_sha256")
        object.__setattr__(self, "content_sha256", content_hash)
        for field_name in ("validation_extraction_sha256", "reading_extraction_sha256"):
            object.__setattr__(self, field_name, _hash(getattr(self, field_name), field_name))
        for field_name in ("page_count", "extracted_characters"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{field_name} must be nonnegative or None")
        for field_name in ("title_match", "doi_match"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean or None")
        _text(self.history_origin, "history_origin")
        if self.cache_path is not None and not _CACHE.fullmatch(self.cache_path):
            raise ValueError("cache_path must be a portable fulltext_cache PDF path")
        if not isinstance(self.alternatives, tuple) or any(not isinstance(item, str) or not item for item in self.alternatives):
            raise ValueError("alternatives must be a tuple of version IDs")
        if len(set(self.alternatives)) != len(self.alternatives) or self.selected_reading_version in self.alternatives:
            raise ValueError("alternatives must be distinct non-selected versions")
        if self.status is AcquisitionStatus.VALID_PDF:
            if content_hash is None or self.byte_count is None or self.cache_path is None:
                raise ValueError("VALID_PDF requires a hash, size, and local cache path")
            if self.failure_reason is not None:
                raise ValueError("VALID_PDF cannot have a failure reason")
        elif self.failure_reason is None:
            raise ValueError("non-successful acquisition requires an honest failure reason")
        operational = {
            "paper_id": self.paper_id,
            "version_id": self.version_id,
            "source_url": self.source_url,
            "requested_at": self.requested_at,
            "observed_at": self.observed_at,
            "status": self.status.value,
            "http_status": self.http_status,
            "failure_reason": self.failure_reason,
            "retry_policy": self.retry_policy,
            "content_sha256": self.content_sha256,
        }
        encoded = json.dumps(operational, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_attempt_id = "attempt:" + hashlib.sha256(encoded).hexdigest()[:24]
        if self.attempt_id is not None and not re.fullmatch(r"attempt:[0-9a-f]{24}", self.attempt_id):
            raise ValueError("attempt_id must be a deterministic attempt digest")
        object.__setattr__(self, "attempt_id", expected_attempt_id)

    def scientific_payload(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id, "version_id": self.version_id, "source_url": self.source_url,
            "provider": self.provider, "source_tier": self.source_tier, "status": self.status.value,
            "http_status": self.http_status, "media_type": self.media_type, "byte_count": self.byte_count,
            "content_sha256": self.content_sha256, "license_status": self.license_status,
            "redistribution_status": self.redistribution_status, "failure_reason": self.failure_reason,
            "retry_policy": self.retry_policy, "selected_reading_version": self.selected_reading_version,
            "alternatives": self.alternatives,
            "route_provenance": self.route_provenance,
            "page_count": self.page_count,
            "extracted_characters": self.extracted_characters,
            "validation_extraction_sha256": self.validation_extraction_sha256,
            "validation_extraction_normalization": self.validation_extraction_normalization,
            "reading_extraction_sha256": self.reading_extraction_sha256,
            "reading_extraction_normalization": self.reading_extraction_normalization,
            "title_match": self.title_match,
            "doi_match": self.doi_match,
            "identity_basis": self.identity_basis,
        }

    @property
    def scientific_hash(self) -> str:
        return scientific_hash(self.scientific_payload())

    def as_dict(self) -> dict[str, object]:
        result = self.scientific_payload()
        result.update({"requested_at": self.requested_at, "observed_at": self.observed_at,
                       "cache_path": self.cache_path, "scientific_hash": self.scientific_hash,
                       "attempt_id": self.attempt_id, "history_origin": self.history_origin})
        return result

    @property
    def has_complete_validation_provenance(self) -> bool:
        return self.status is not AcquisitionStatus.VALID_PDF or all((
            self.route_provenance,
            self.page_count is not None,
            self.extracted_characters is not None,
            self.validation_extraction_sha256,
            self.validation_extraction_normalization,
            self.reading_extraction_sha256,
            self.reading_extraction_normalization,
            self.title_match is not None,
            self.identity_basis,
        ))


def _status_counts(values: tuple[AcquisitionManifest, ...], *, count_label: str) -> dict[str, int]:
    return {
        count_label: len(values),
        "valid_pdf": sum(item.status is AcquisitionStatus.VALID_PDF for item in values),
        "html_or_challenge": sum(item.status is AcquisitionStatus.HTML_OR_CHALLENGE for item in values),
        "http_failure": sum(item.status is AcquisitionStatus.HTTP_FAILURE for item in values),
        "transport_failure": sum(item.status is AcquisitionStatus.TRANSPORT_FAILURE for item in values),
        "invalid_pdf": sum(item.status is AcquisitionStatus.INVALID_PDF for item in values),
        "not_attempted": sum(item.status is AcquisitionStatus.NOT_ATTEMPTED for item in values),
    }


def build_offline_ledger(
    manifests: Iterable[AcquisitionManifest],
    destination: Path,
    *,
    attempt_history: Iterable[AcquisitionManifest] | None = None,
) -> dict[str, object]:
    """Write a deterministic, exact-count ledger without network or cache reads."""

    values = tuple(manifests)
    if any(not isinstance(item, AcquisitionManifest) for item in values):
        raise ValueError("manifests must contain AcquisitionManifest records")
    paper_versions = [(item.paper_id, item.version_id) for item in values]
    if len(set(paper_versions)) != len(paper_versions):
        raise ValueError("each paper/version may have exactly one selected acquisition manifest")
    ordered = tuple(sorted(values, key=lambda item: (item.paper_id, item.version_id)))
    attempts = tuple(attempt_history) if attempt_history is not None else ordered
    if any(not isinstance(item, AcquisitionManifest) for item in attempts):
        raise ValueError("attempt_history must contain AcquisitionManifest records")
    attempt_ids = [item.attempt_id for item in attempts]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise ValueError("attempt_history cannot contain duplicate immutable attempts")
    ordered_attempts = tuple(sorted(attempts, key=lambda item: (item.requested_at, str(item.attempt_id))))
    selected_counts = _status_counts(ordered, count_label="outcomes")
    attempt_counts = _status_counts(ordered_attempts, count_label="attempts")
    content = {
        "selected_outcomes": {"counts": selected_counts, "manifests": [item.as_dict() for item in ordered]},
        "attempt_history": {"counts": attempt_counts, "attempts": [item.as_dict() for item in ordered_attempts]},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return {
        "selected_outcomes": selected_counts,
        "attempt_history": attempt_counts,
        # Legacy aliases remain available to older callers, but are explicitly selected-outcome counts.
        "attempts": selected_counts["outcomes"],
        **{key: value for key, value in selected_counts.items() if key != "outcomes"},
    }
