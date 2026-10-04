"""Validated, bounded PDF retrieval confined to the gitignored cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping
from urllib.parse import urlsplit

from .ingest import HttpTransport
from .serialization import scientific_hash


_CACHE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_HASH = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    source_url: str
    cache_key: str
    expected_sha256: str | None = None
    max_bytes: int = _MAX_BYTES

    def __post_init__(self) -> None:
        parsed = urlsplit(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an http(s) URL")
        if not _CACHE_KEY.fullmatch(self.cache_key):
            raise ValueError("cache key must be a safe filename token")
        if self.expected_sha256 is not None and not _HASH.fullmatch(self.expected_sha256):
            raise ValueError("expected_sha256 must be a SHA-256 digest")
        if isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or self.max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer")


@dataclass(frozen=True, slots=True)
class RetrievalManifest:
    source_url: str
    resolved_url: str | None
    status: str
    content_sha256: str | None
    byte_count: int | None
    expected_sha256: str | None
    error_code: str | None
    error_detail: str | None
    retrieved_at: str
    http_status: int | None
    cache_name: str

    @property
    def error(self) -> str | None:
        return self.error_detail

    @property
    def outcome(self) -> str:
        return "UNAVAILABLE" if self.status == "METADATA_ONLY" else self.status

    def scientific_payload(self) -> dict[str, object]:
        allowed_resolved_url = self.resolved_url if _valid_http_url(self.resolved_url) else None
        resolved_url_status = "HTTP" if allowed_resolved_url is not None else (
            "REJECTED_NON_HTTP" if self.resolved_url is not None else "NOT_RESOLVED"
        )
        return {"source_url": self.source_url, "resolved_url": allowed_resolved_url,
                "resolved_url_status": resolved_url_status, "status": self.status,
                "content_sha256": self.content_sha256, "byte_count": self.byte_count,
                "expected_sha256": self.expected_sha256, "error_code": self.error_code, "http_status": self.http_status}

    @property
    def scientific_hash(self) -> str:
        return scientific_hash(self.scientific_payload())


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_symlink(path: Path) -> bool:
    """Filesystem seam that keeps the cache-route escape guard testable."""
    return path.is_symlink()


def _cache_dir(cache_root: Path | str) -> Path:
    repository = _repository_root()
    expected = repository / "literature" / "fulltext_cache"
    requested = Path(cache_root)
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if os.path.normcase(os.path.abspath(requested)) != os.path.normcase(os.path.abspath(expected)):
        raise ValueError("cache_root must be literature/fulltext_cache")
    current = repository
    for part in ("literature", "fulltext_cache"):
        current = current / part
        if current.exists() and _is_symlink(current):
            raise ValueError("cache_root cannot be a symlink")
    expected.mkdir(parents=True, exist_ok=True)
    if expected.resolve() != expected.absolute():
        raise ValueError("cache_root cannot resolve outside literature/fulltext_cache")
    return expected


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.casefold()
    return next((value for key, value in headers.items() if key.casefold() == target), None)


def _valid_http_url(url: str | None) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _failure(request: RetrievalRequest, *, status: str = "METADATA_ONLY", error_code: str, error_detail: str,
             resolved_url: str | None, http_status: int | None, retrieved_at: str) -> RetrievalManifest:
    return RetrievalManifest(request.source_url, resolved_url, status, None, None,
                             request.expected_sha256.lower() if request.expected_sha256 else None,
                             error_code, error_detail, retrieved_at, http_status, f"{request.cache_key}.pdf")


def retrieve_fulltext(request: RetrievalRequest, transport: HttpTransport, cache_root: Path | str, *, timeout: float = 30.0,
                      retrieved_at: datetime | None = None) -> RetrievalManifest:
    """Download at most ``max_bytes + 1`` and atomically cache a validated PDF."""
    if not isinstance(request, RetrievalRequest):
        raise ValueError("request must be a RetrievalRequest")
    stamp = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        root = _cache_dir(cache_root)
    except OSError as caught:
        return _failure(request, status="UNAVAILABLE", error_code="CACHE_IO", error_detail=str(caught),
                        resolved_url=None, http_status=None, retrieved_at=stamp)
    try:
        response = transport.get(request.source_url, timeout=timeout, max_bytes=request.max_bytes)
    except TimeoutError as caught:
        return _failure(request, error_code="TRANSPORT_TIMEOUT", error_detail=str(caught), resolved_url=None,
                        http_status=None, retrieved_at=stamp)
    except OSError as caught:
        return _failure(request, error_code="TRANSPORT_ERROR", error_detail=str(caught), resolved_url=None,
                        http_status=None, retrieved_at=stamp)
    if not _valid_http_url(response.url):
        return _failure(request, error_code="REDIRECT_SCHEME", error_detail="redirect target is not an allowed http(s) URL",
                        resolved_url=response.url, http_status=response.status, retrieved_at=stamp)
    if response.status != 200:
        return _failure(request, error_code="HTTP_STATUS", error_detail=f"HTTP {response.status}", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    if len(response.body) > request.max_bytes:
        return _failure(request, error_code="OVERSIZE", error_detail="response exceeds maximum size", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    content_type = _header(response.headers, "content-type")
    if content_type is None or content_type.split(";", 1)[0].strip().casefold() != "application/pdf":
        return _failure(request, error_code="CONTENT_TYPE", error_detail="content type is not application/pdf", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    length_header = _header(response.headers, "content-length")
    if length_header is not None:
        try:
            declared_length = int(length_header)
        except ValueError:
            return _failure(request, error_code="CONTENT_LENGTH", error_detail="invalid Content-Length", resolved_url=response.url,
                            http_status=response.status, retrieved_at=stamp)
        if declared_length != len(response.body):
            return _failure(request, error_code="TRUNCATED", error_detail="truncated response body", resolved_url=response.url,
                            http_status=response.status, retrieved_at=stamp)
    if not response.body:
        return _failure(request, error_code="EMPTY", error_detail="empty response body", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    if not response.body.startswith(b"%PDF-") or b"%%EOF" not in response.body[-1024:]:
        return _failure(request, error_code="PDF_MAGIC", error_detail="PDF magic or trailer is invalid", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    content_hash = hashlib.sha256(response.body).hexdigest()
    if request.expected_sha256 is not None and content_hash != request.expected_sha256.casefold():
        return _failure(request, error_code="HASH_MISMATCH", error_detail="SHA-256 mismatch", resolved_url=response.url,
                        http_status=response.status, retrieved_at=stamp)
    target, temporary_name = root / f"{request.cache_key}.pdf", None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{request.cache_key}.", suffix=".tmp", dir=root)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(response.body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    except OSError as caught:
        return _failure(request, status="UNAVAILABLE", error_code="CACHE_IO", error_detail=str(caught),
                        resolved_url=response.url, http_status=response.status, retrieved_at=stamp)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
    return RetrievalManifest(request.source_url, response.url, "AVAILABLE", content_hash, len(response.body),
                             request.expected_sha256.lower() if request.expected_sha256 else None, None, None, stamp,
                             response.status, target.name)
