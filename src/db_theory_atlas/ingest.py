"""Provider-neutral, bounded, auditable literature-search ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import re
import time
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .serialization import scientific_hash
from .sources import SourceKind, SourceObservation, normalize_doi


_DEFAULT_RESPONSE_BYTES = 8 * 1024 * 1024
_ARXIV_VERSION = re.compile(r"v[0-9]+$", re.IGNORECASE)


class Provider(str, Enum):
    CROSSREF = "CROSSREF"
    OPENALEX = "OPENALEX"
    ARXIV = "ARXIV"
    DBLP = "DBLP"
    OFFICIAL = "OFFICIAL"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A body capped by the requested transport limit plus one byte."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class HttpTransport(Protocol):
    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse: ...


class UrllibTransport:
    """Explicit live transport with bounded reads and HTTP status preservation."""

    def __init__(self, opener: Callable[..., object] = urlopen) -> None:
        self._opener = opener

    @staticmethod
    def _read_response(response: object, fallback_url: str, max_bytes: int) -> HttpResponse:
        headers = getattr(response, "headers", {})
        items = headers.items() if hasattr(headers, "items") else ()
        response_url = response.geturl() if hasattr(response, "geturl") else fallback_url
        status = getattr(response, "status", getattr(response, "code", None))
        if not isinstance(status, int):
            raise OSError("HTTP response has no integer status")
        body = response.read(max_bytes + 1)
        return HttpResponse(status, {str(key): str(value) for key, value in items}, body, str(response_url))

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer")
        request = Request(url, headers={"User-Agent": "db-theory-atlas/0.1"})
        try:
            response = self._opener(request, timeout=timeout)
        except HTTPError as error:
            # urllib raises HTTPError for useful status responses (including
            # 429); retaining the body/status lets retry policy decide safely.
            try:
                return self._read_response(error, url, max_bytes)
            finally:
                error.close()
        with response:  # type: ignore[union-attr]
            return self._read_response(response, url, max_bytes)


@dataclass(frozen=True, slots=True)
class SearchHit:
    provider: Provider
    provider_id: str | None
    title: str
    authors: tuple[str, ...]
    year: int | None
    venue: str | None
    doi: str | None
    source_url: str | None
    fulltext_url: str | None = None
    source_observation: SourceObservation | None = None

    @property
    def observation(self) -> SourceObservation | None:
        return self.source_observation

    @property
    def dedup_key(self) -> str:
        if self.doi is not None:
            return f"doi:{self.doi.casefold()}"
        if self.provider is Provider.ARXIV and self.provider_id:
            return f"arxiv:{_ARXIV_VERSION.sub('', self.provider_id).casefold()}"
        if self.provider_id:
            return f"provider:{self.provider.value.casefold()}:{self.provider_id.casefold()}"
        author = _normal_text(self.authors[0]) if self.authors else ""
        return f"fallback:{_normal_text(self.title)}:{author}:{self.year if self.year is not None else ''}"


@dataclass(frozen=True, slots=True)
class ProviderManifest:
    """Scientific state and operational details kept deliberately separate."""

    provider: Provider
    query: str
    requested: int
    received: int
    cursor: str | None
    page: int | None
    payload_hash: str | None
    status: str
    error_code: str | None
    retry_count: int
    fetched_at: str
    error_detail: str | None = None
    payload_hash_status: str = "COMPUTED"

    @property
    def error(self) -> str | None:
        """Compatibility/readability alias for operational human detail."""
        return self.error_detail

    def scientific_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider.value, "query": self.query, "requested": self.requested,
            "received": self.received, "cursor": self.cursor, "page": self.page,
            "payload_hash": self.payload_hash, "payload_hash_status": self.payload_hash_status,
            "status": self.status, "error_code": self.error_code,
        }

    @property
    def scientific_hash(self) -> str:
        return scientific_hash(self.scientific_payload())


_SOURCE_KINDS = {
    Provider.CROSSREF: SourceKind.DOI_METADATA,
    Provider.OPENALEX: SourceKind.SEARCH_DISCOVERY,
    Provider.ARXIV: SourceKind.ARXIV_FULL_TEXT,
    Provider.DBLP: SourceKind.DBLP,
    Provider.OFFICIAL: SourceKind.OFFICIAL_PROCEEDINGS,
    Provider.MANUAL: SourceKind.SEARCH_DISCOVERY,
}


def _normal_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _as_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first_text(value: object) -> str | None:
    return _as_text(value[0]) if isinstance(value, list) and value else _as_text(value)


def _year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1900 <= value <= 2100:
        return value
    if isinstance(value, str) and value[:4].isdigit() and 1900 <= int(value[:4]) <= 2100:
        return int(value[:4])
    return None


def _doi(value: object) -> str | None:
    raw = _as_text(value)
    if raw is None:
        return None
    try:
        return normalize_doi(raw)
    except ValueError:
        return None


def _url(value: object) -> str | None:
    raw = _as_text(value)
    return raw if raw and raw.startswith(("https://", "http://")) else None


def _make_hit(provider: Provider, provider_id: object, title: object, authors: tuple[str, ...], year: object,
              venue: object, doi: object, source_url: object, fulltext_url: object, observed_at: date) -> SearchHit | None:
    normalized_title = _as_text(title)
    if normalized_title is None:
        return None
    normalized_authors = tuple(author for author in authors if _as_text(author) is not None)
    normalized_year, normalized_venue, normalized_doi = _year(year), _as_text(venue), _doi(doi)
    normalized_source_url, normalized_fulltext_url = _url(source_url), _url(fulltext_url)
    observation = None
    if normalized_authors and normalized_year is not None and normalized_source_url is not None:
        observation = SourceObservation(
            source=_SOURCE_KINDS[provider], observed_title=normalized_title, authors=normalized_authors,
            year=normalized_year, venue=normalized_venue, doi=normalized_doi,
            official_url=normalized_source_url if provider is not Provider.ARXIV else None,
            preprint_url=normalized_source_url if provider is Provider.ARXIV else normalized_fulltext_url,
            volume=None, issue=None, pages=None, observed_at=observed_at, evidence_url=normalized_source_url,
        )
    return SearchHit(provider, _as_text(provider_id), normalized_title, normalized_authors, normalized_year, normalized_venue,
                     normalized_doi, normalized_source_url, normalized_fulltext_url, observation)


def _json_payload(raw: object) -> Mapping[str, object]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, Mapping):
        raise ValueError("JSON provider payload must be an object")
    return raw


def ingest_crossref(raw: object, *, observed_at: date) -> tuple[SearchHit, ...]:
    payload, hits = _json_payload(raw), []
    message = payload.get("message", {})
    items = message.get("items", []) if isinstance(message, Mapping) else []
    if not isinstance(items, list):
        raise ValueError("Crossref items must be a list")
    for item in items:
        if not isinstance(item, Mapping):
            continue
        author_records = item.get("author")
        authors = tuple(" ".join(part for part in (_as_text(author.get("given")), _as_text(author.get("family"))) if part)
                        for author in author_records if isinstance(author, Mapping)) if isinstance(author_records, list) else ()
        dates = item.get("published-print") or item.get("published-online") or item.get("issued")
        parts = dates.get("date-parts") if isinstance(dates, Mapping) else None
        year = parts[0][0] if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] else None
        hit = _make_hit(Provider.CROSSREF, item.get("DOI"), _first_text(item.get("title")), authors, year,
                        _first_text(item.get("container-title")), item.get("DOI"), item.get("URL"), None, observed_at)
        if hit:
            hits.append(hit)
    return tuple(hits)


def ingest_openalex(raw: object, *, observed_at: date) -> tuple[SearchHit, ...]:
    payload, hits = _json_payload(raw), []
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("OpenAlex results must be a list")
    for item in results:
        if not isinstance(item, Mapping):
            continue
        authorships = item.get("authorships", [])
        authors = tuple(name for authorship in authorships if isinstance(authorship, Mapping)
                        for name in (_as_text(authorship.get("author", {}).get("display_name"))
                                     if isinstance(authorship.get("author"), Mapping) else None,) if name) if isinstance(authorships, list) else ()
        location = item.get("primary_location") if isinstance(item.get("primary_location"), Mapping) else {}
        source = location.get("source") if isinstance(location.get("source"), Mapping) else {}
        best_oa = item.get("best_oa_location") if isinstance(item.get("best_oa_location"), Mapping) else {}
        hit = _make_hit(Provider.OPENALEX, item.get("id"), item.get("display_name"), authors, item.get("publication_year"),
                        source.get("display_name"), item.get("doi"), location.get("landing_page_url") or item.get("id"),
                        best_oa.get("pdf_url"), observed_at)
        if hit:
            hits.append(hit)
    return tuple(hits)


def _xml_root(raw: object) -> ElementTree.Element:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes):
        raise ValueError("XML provider payload must be text or bytes")
    return ElementTree.fromstring(raw)


def _arxiv_id(source_url: str | None) -> str | None:
    if source_url is None:
        return None
    marker = "/abs/"
    return source_url.split(marker, 1)[1] if marker in source_url else source_url.rsplit("/", 1)[-1]


def ingest_arxiv(raw: object, *, observed_at: date) -> tuple[SearchHit, ...]:
    root, namespace, hits = _xml_root(raw), {"atom": "http://www.w3.org/2005/Atom"}, []
    for entry in root.findall("atom:entry", namespace):
        source_url = entry.findtext("atom:id", namespaces=namespace)
        pdf_url = next((link.get("href") for link in entry.findall("atom:link", namespace) if link.get("title") == "pdf"), None)
        hit = _make_hit(Provider.ARXIV, _arxiv_id(source_url), entry.findtext("atom:title", namespaces=namespace),
                        tuple(element.text or "" for element in entry.findall("atom:author/atom:name", namespace)),
                        entry.findtext("atom:published", namespaces=namespace), None, None, source_url, pdf_url, observed_at)
        if hit:
            hits.append(hit)
    return tuple(hits)


def ingest_dblp(raw: object, *, observed_at: date) -> tuple[SearchHit, ...]:
    root, hits = _xml_root(raw), []
    for element in root.findall(".//hit"):
        info = element.find("info")
        if info is None:
            continue
        hit = _make_hit(Provider.DBLP, element.get("id"), info.findtext("title"),
                        tuple(author.text or "" for author in info.findall("authors/author")), info.findtext("year"),
                        info.findtext("venue"), info.findtext("doi"), info.findtext("url"), None, observed_at)
        if hit:
            hits.append(hit)
    return tuple(hits)


def ingest_hits(raw: object, provider: Provider, *, observed_at: datetime | date | None = None) -> tuple[SearchHit, ...]:
    if not isinstance(provider, Provider):
        raise ValueError("provider must be a Provider")
    when = observed_at or datetime.now(timezone.utc)
    observation_date = when.date() if isinstance(when, datetime) else when
    if not isinstance(observation_date, date):
        raise ValueError("observed_at must be a date or datetime")
    parsers = {Provider.CROSSREF: ingest_crossref, Provider.OPENALEX: ingest_openalex,
               Provider.ARXIV: ingest_arxiv, Provider.DBLP: ingest_dblp}
    parser = parsers.get(provider)
    if parser is None:
        raise ValueError(f"fixture ingestion is unsupported for {provider.value}")
    return parser(raw, observed_at=observation_date)


def deduplicate_hits(hits: tuple[SearchHit, ...] | list[SearchHit]) -> tuple[SearchHit, ...]:
    if any(not isinstance(hit, SearchHit) for hit in hits):
        raise ValueError("hits must be SearchHit records")
    grouped: dict[str, list[SearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.dedup_key, []).append(hit)
    return tuple(min(group, key=lambda hit: (hit.provider.value, hit.source_url or "", hit.title, hit.provider_id or ""))
                 for _, group in sorted(grouped.items()))


def provider_url(query: str, provider: Provider, *, limit: int = 25) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be nonempty")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if provider is Provider.CROSSREF:
        return f"https://api.crossref.org/works?{urlencode({'query': query, 'rows': limit})}"
    if provider is Provider.OPENALEX:
        return f"https://api.openalex.org/works?{urlencode({'search': query, 'per-page': limit})}"
    if provider is Provider.ARXIV:
        return f"https://export.arxiv.org/api/query?{urlencode({'search_query': 'all:' + query, 'max_results': limit})}"
    if provider is Provider.DBLP:
        return f"https://dblp.org/search/publ/api?{urlencode({'q': query, 'h': limit, 'format': 'xml'})}"
    raise ValueError(f"live ingestion is unsupported for {provider.value}")


def _provider_manifest(provider: Provider, query: str, limit: int, status: str, error_code: str | None,
                       error_detail: str | None, retries: int, stamp: str, response: HttpResponse | None = None,
                       received: int = 0, payload_hash_status: str = "COMPUTED") -> ProviderManifest:
    if response is None:
        payload_hash, payload_hash_status = None, "NOT_AVAILABLE"
    elif payload_hash_status == "COMPUTED":
        payload_hash = hashlib.sha256(response.body).hexdigest()
    else:
        payload_hash = None
    return ProviderManifest(provider, query, limit, received, None, None, payload_hash, status, error_code, retries, stamp,
                            error_detail, payload_hash_status)


def ingest_provider(query: str, provider: Provider, transport: HttpTransport, *, limit: int = 25, retries: int = 2,
                    timeout: float = 20.0, max_bytes: int = _DEFAULT_RESPONSE_BYTES,
                    sleep: Callable[[float], None] = time.sleep, fetched_at: datetime | None = None) -> tuple[tuple[SearchHit, ...], ProviderManifest]:
    """Fetch one bounded batch with explicit failure category and retry policy."""
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ValueError("retries must be a nonnegative integer")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    url, attempts, response = provider_url(query, provider, limit=limit), 0, None
    error_code: str | None = None
    error_detail: str | None = None
    while True:
        try:
            response = transport.get(url, timeout=timeout, max_bytes=max_bytes)
        except TimeoutError as caught:
            error_code, error_detail = "TRANSPORT_TIMEOUT", str(caught)
        except OSError as caught:
            error_code, error_detail = "TRANSPORT_ERROR", str(caught)
        else:
            if response.status == 429 and attempts < retries:
                sleep(float(2**attempts))
                attempts += 1
                continue
            break
        if attempts >= retries:
            break
        sleep(float(2**attempts))
        attempts += 1
    stamp = (fetched_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if response is None:
        return (), _provider_manifest(provider, query, limit, "UNAVAILABLE", error_code, error_detail, attempts, stamp)
    if len(response.body) > max_bytes:
        return (), _provider_manifest(provider, query, limit, "UNAVAILABLE", "OVERSIZE", "response exceeds maximum size",
                                      attempts, stamp, response, payload_hash_status="NOT_COMPUTED_OVERSIZE")
    if response.status != 200:
        return (), _provider_manifest(provider, query, limit, "UNAVAILABLE", "HTTP_STATUS", f"HTTP {response.status}", attempts, stamp, response)
    try:
        hits = ingest_hits(response.body, provider, observed_at=fetched_at or datetime.now(timezone.utc))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, ElementTree.ParseError) as caught:
        return (), _provider_manifest(provider, query, limit, "INVALID", "PAYLOAD_INVALID", str(caught), attempts, stamp, response)
    return hits, _provider_manifest(provider, query, limit, "SUCCESS", None, None, attempts, stamp, response, len(hits))
