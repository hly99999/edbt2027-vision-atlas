"""Conservative, resumable Task 3 acquisition from canonical screened records.

The live mode makes at most one landing request and one declared PDF request per
selected version.  It never attempts authentication, challenge solving, or
paywall bypass.  Offline mode only reconstructs ledgers from frozen manifests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping
from urllib.parse import urljoin, urlsplit

from db_theory_atlas.corpus_task3 import (
    AcquisitionManifest,
    AcquisitionStatus,
    IDENTITY_MISMATCH_FAILURE,
    PdfValidationStatus,
    build_offline_ledger,
    validate_pdf_payload,
)
from db_theory_atlas.ingest import HttpResponse, UrllibTransport
from db_theory_atlas.fulltext_reading import build_reading_corpus


ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "data" / "papers" / "papers.jsonl"
MANIFESTS = ROOT / "literature" / "fulltext_manifests" / "acquisition_2026_08_30.jsonl"
ATTEMPTS = ROOT / "literature" / "fulltext_manifests" / "acquisition_attempts_2026_08_30.jsonl"
LEDGER = ROOT / "literature" / "fulltext_ledgers" / "acquisition_ledger_2026_08_30.json"
READ_LEDGER = ROOT / "literature" / "fulltext_ledgers" / "read_depth_2026_08_30.json"
NOTES = ROOT / "literature" / "fulltext_notes"
AUDITS = ROOT / "literature" / "fulltext_audits" / "source_validation_2026_08_30.jsonl"
CACHE = ROOT / "literature" / "fulltext_cache"
REPORT = ROOT / ".superpowers" / "sdd" / "corpus-task-3-final-report.md"
PROVENANCE = ROOT / ".superpowers" / "sdd" / "corpus-task-3-provenance.json"
_HREF = re.compile(r"href\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
RETRYABLE_STATUSES = frozenset({AcquisitionStatus.TRANSPORT_FAILURE})
IDENTITY_POLICY_RECOVERY = "VALIDATION_POLICY_RECOVERY:IDENTITY_MISMATCH"
KR_ROUTE_POLICY_RECOVERY = "ROUTE_POLICY_RECOVERY:KR_PROCEEDINGS_2023_2026"
KR_ROUTE_POLICY_FAILURE = "official landing page did not declare a same-provider open PDF"
_OA_DOI_PREFIXES = {
    "10.4230/": "LIPICS",
    "10.24963/": "KR_PROCEEDINGS",
    "10.46298/": "LMCS",
}
_KR_LANDING_PATH = re.compile(r"^/202[3-6]/[1-9][0-9]*/$")
_KR_PDF_PATH = re.compile(
    r"^/(?P<year>202[3-6])/(?P<number>[1-9][0-9]*)/kr(?P=year)-(?P<article>[0-9]{4})-"
    r"[a-z0-9]+(?:-[a-z0-9]+)*\.pdf$"
)
_LIPICS_PDF_PATH = re.compile(
    r"^/storage/00lipics/lipics-vol[0-9]+-[a-z0-9-]+/LIPIcs\.[A-Za-z]+\.[0-9]{4}\.[0-9]+/"
    r"LIPIcs\.[A-Za-z]+\.[0-9]{4}\.[0-9]+\.pdf$"
)
_ARXIV_PDF_PATH = re.compile(r"^/pdf/[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?(?:\.pdf)?$")


def _kr_proceedings_pdf_path(path: str) -> bool:
    match = _KR_PDF_PATH.fullmatch(path)
    return match is not None and int(match["number"]) == int(match["article"])


_OA_PDF_PATHS = {
    "drops.dagstuhl.de": lambda path: _LIPICS_PDF_PATH.fullmatch(path) is not None,
    "arxiv.org": lambda path: _ARXIV_PDF_PATH.fullmatch(path) is not None,
    "export.arxiv.org": lambda path: _ARXIV_PDF_PATH.fullmatch(path) is not None,
    "proceedings.kr.org": _kr_proceedings_pdf_path,
    "lmcs.episciences.org": lambda path: bool(re.fullmatch(r"/[0-9]+/pdf", path)),
}


def _score(record: Mapping[str, object]) -> int:
    screening = record.get("screening")
    if not isinstance(screening, Mapping):
        return -1
    value = screening.get("DEEP_READ_PRIORITY_SCORE")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def _topic(record: Mapping[str, object]) -> str:
    screening = record.get("screening")
    if isinstance(screening, Mapping) and isinstance(screening.get("primary_topic_id"), str):
        return screening["primary_topic_id"]
    return "UNASSIGNED"


def _relevant(record: Mapping[str, object]) -> bool:
    screening = record.get("screening")
    return isinstance(screening, Mapping) and screening.get("relevant") is True


def _oa_route_rank(record: Mapping[str, object]) -> int:
    """Known official OA providers are attempted before publisher-only DOI routes."""

    url = record.get("official_url")
    return 0 if isinstance(url, str) and _recognized_oa_url(url) else 1


def _recognized_oa_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        return False
    if parsed.query or parsed.fragment or parsed.port is not None:
        return False
    host = (parsed.hostname or "").casefold()
    path = parsed.path
    if host == "doi.org":
        doi_path = path.lstrip("/").casefold()
        return any(doi_path.startswith(prefix) for prefix in _OA_DOI_PREFIXES)
    allowed = _OA_PDF_PATHS.get(host)
    if allowed is not None and allowed(path):
        return True
    if host == "proceedings.kr.org":
        return _KR_LANDING_PATH.fullmatch(path) is not None
    if host == "lmcs.episciences.org":
        return re.fullmatch(r"/[0-9]+/?", path) is not None
    if host in {"arxiv.org", "export.arxiv.org"}:
        return re.fullmatch(r"/(?:abs|pdf)/[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?(?:\.pdf)?", path) is not None
    return False


def select_candidates(records: Iterable[Mapping[str, object]], *, limit: int) -> tuple[dict[str, object], ...]:
    """Rank by Task 2 score while taking one item per topic on each pass."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        if not isinstance(record, Mapping) or not _relevant(record):
            continue
        paper_id = record.get("paper_id")
        source_url = record.get("official_url")
        if not isinstance(paper_id, str) or not isinstance(source_url, str) or not source_url.startswith(("https://", "http://")):
            continue
        grouped.setdefault(_topic(record), []).append(dict(record))
    for items in grouped.values():
        items.sort(key=lambda item: (_oa_route_rank(item), -_score(item), str(item["paper_id"])))
    selected: list[dict[str, object]] = []
    while grouped and len(selected) < limit:
        heads = sorted(
            ((items[0], topic) for topic, items in grouped.items() if items),
            key=lambda pair: (_oa_route_rank(pair[0]), -_score(pair[0]), str(pair[0]["paper_id"]), pair[1]),
        )
        if not heads:
            break
        for item, topic in heads:
            if len(selected) >= limit:
                break
            selected.append(item)
            grouped[topic].pop(0)
        grouped = {topic: items for topic, items in grouped.items() if items}
    return tuple(selected)


def _manifest_key(manifest: AcquisitionManifest) -> tuple[str, str]:
    return manifest.paper_id, manifest.version_id


def _candidate_key(record: Mapping[str, object]) -> tuple[str, str]:
    return str(record["paper_id"]), _version_fields(record)[0]


def _retry_is_allowed(manifest: AcquisitionManifest, retry_statuses: frozenset[AcquisitionStatus]) -> bool:
    return manifest.status in retry_statuses and manifest.retry_policy == "NO_RETRY"


def _identity_recovery_is_allowed(manifest: AcquisitionManifest) -> bool:
    return (
        manifest.status is AcquisitionStatus.INVALID_PDF
        and manifest.failure_reason == IDENTITY_MISMATCH_FAILURE
        and manifest.retry_policy == "RETRY_ONCE:TRANSPORT_FAILURE"
    )


def _kr_route_policy_recovery_is_allowed(manifest: AcquisitionManifest) -> bool:
    parsed = urlsplit(manifest.source_url)
    return (
        manifest.provider == "KR_PROCEEDINGS"
        and manifest.status is AcquisitionStatus.HTML_OR_CHALLENGE
        and manifest.failure_reason == KR_ROUTE_POLICY_FAILURE
        and manifest.retry_policy in {"NO_RETRY", "RETRY_ONCE:TRANSPORT_FAILURE"}
        and parsed.scheme == "https"
        and parsed.hostname == "proceedings.kr.org"
        and parsed.query == ""
        and parsed.fragment == ""
        and _KR_LANDING_PATH.fullmatch(parsed.path) is not None
    )


def planned_action(previous: AcquisitionManifest | None) -> str:
    if previous is None:
        return "NEW"
    if _identity_recovery_is_allowed(previous):
        return "VALIDATION_POLICY_RECOVERY"
    return "KR_ROUTE_POLICY_RECOVERY" if _kr_route_policy_recovery_is_allowed(previous) else "RETRY"


def next_retry_policy(previous: AcquisitionManifest | None) -> str:
    if previous is None:
        return "NO_RETRY"
    if _identity_recovery_is_allowed(previous):
        return IDENTITY_POLICY_RECOVERY
    if _kr_route_policy_recovery_is_allowed(previous):
        return KR_ROUTE_POLICY_RECOVERY
    return f"RETRY_ONCE:{previous.status.value}"


def select_live_candidates(records: Iterable[Mapping[str, object]], existing: Iterable[AcquisitionManifest], *,
                           limit: int, retry_statuses: frozenset[AcquisitionStatus] = frozenset(),
                           oa_only: bool = False, recover_identity_mismatch: bool = False,
                           recover_kr_route_policy: bool = False) -> tuple[dict[str, object], ...]:
    """Select unseen records plus one explicitly requested retry per failed record."""

    if not retry_statuses <= RETRYABLE_STATUSES:
        raise ValueError("only explicitly retryable acquisition statuses may be retried")
    prior = tuple(existing)
    if any(not isinstance(item, AcquisitionManifest) for item in prior):
        raise ValueError("existing must contain AcquisitionManifest records")
    by_key = {_manifest_key(item): item for item in prior}
    if len(by_key) != len(prior):
        raise ValueError("existing manifests must conserve one paper/version record")
    eligible: list[Mapping[str, object]] = []
    for candidate in records:
        if not isinstance(candidate, Mapping):
            continue
        source_url = candidate.get("official_url")
        if oa_only and (not isinstance(source_url, str) or not _recognized_oa_url(source_url)):
            continue
        found = by_key.get(_candidate_key(candidate))
        if (
            found is None
            or _retry_is_allowed(found, retry_statuses)
            or (recover_identity_mismatch and _identity_recovery_is_allowed(found))
            or (recover_kr_route_policy and _kr_route_policy_recovery_is_allowed(found))
        ):
            eligible.append(candidate)
    return select_candidates(eligible, limit=limit)


def replace_manifests(existing: Iterable[AcquisitionManifest], replacements: Iterable[AcquisitionManifest]) -> tuple[AcquisitionManifest, ...]:
    """Replace selected retry outcomes in place without duplicate paper/version rows."""

    prior, changes = tuple(existing), tuple(replacements)
    if any(not isinstance(item, AcquisitionManifest) for item in prior + changes):
        raise ValueError("manifests must contain AcquisitionManifest records")
    prior_by_key = {_manifest_key(item): item for item in prior}
    replacement_by_key = {_manifest_key(item): item for item in changes}
    if len(prior_by_key) != len(prior) or len(replacement_by_key) != len(changes):
        raise ValueError("manifests and replacements require unique paper/version keys")
    if not set(replacement_by_key) <= set(prior_by_key):
        raise ValueError("replacements must correspond to an existing manifest")
    return tuple(
        replacement_by_key.get(_manifest_key(item), item)
        for item in sorted(prior, key=_manifest_key)
    )


def conserve_attempt_history(
    selected: Iterable[AcquisitionManifest],
    attempts: Iterable[AcquisitionManifest],
    outcomes: Iterable[AcquisitionManifest],
) -> tuple[tuple[AcquisitionManifest, ...], tuple[AcquisitionManifest, ...]]:
    """Append immutable outcomes while maintaining one selected outcome per paper/version."""

    prior_selected, prior_attempts, new_outcomes = tuple(selected), tuple(attempts), tuple(outcomes)
    if any(not isinstance(item, AcquisitionManifest) for item in prior_selected + prior_attempts + new_outcomes):
        raise ValueError("selected outcomes and attempt history must contain AcquisitionManifest records")
    selected_by_key = {_manifest_key(item): item for item in prior_selected}
    if len(selected_by_key) != len(prior_selected):
        raise ValueError("selected outcomes require unique paper/version keys")
    outcome_by_key = {_manifest_key(item): item for item in new_outcomes}
    if len(outcome_by_key) != len(new_outcomes):
        raise ValueError("new outcomes require unique paper/version keys")
    selected_by_key.update(outcome_by_key)
    attempt_ids = {item.attempt_id for item in prior_attempts}
    if len(attempt_ids) != len(prior_attempts):
        raise ValueError("attempt history contains duplicate immutable attempts")
    conserved = list(prior_attempts)
    for outcome in new_outcomes:
        if outcome.attempt_id not in attempt_ids:
            conserved.append(outcome)
            attempt_ids.add(outcome.attempt_id)
    return tuple(selected_by_key[key] for key in sorted(selected_by_key)), tuple(conserved)


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _media_type(response: HttpResponse) -> str | None:
    for key, value in response.headers.items():
        if key.casefold() == "content-type":
            return value.split(";", 1)[0].strip().casefold()
    return None


def _pdf_link(landing: HttpResponse) -> str | None:
    """Use an explicitly declared same-provider OA PDF link, never a scraper guess."""

    media = _media_type(landing)
    if media not in {"text/html", "application/xhtml+xml"}:
        return None
    try:
        body = landing.body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    host = urlsplit(landing.url).hostname or ""
    for raw in _HREF.findall(body):
        candidate = urljoin(landing.url, unescape(raw))
        parsed = urlsplit(candidate)
        if parsed.scheme != "https" or parsed.hostname != host or parsed.query or parsed.fragment:
            continue
        allowed_path = _OA_PDF_PATHS.get(host)
        if allowed_path is not None and allowed_path(parsed.path):
            return candidate
    return None


def _version_fields(record: Mapping[str, object]) -> tuple[str, tuple[str, ...], str, str | None]:
    versions = record.get("versions")
    if not isinstance(versions, list) or not versions or not isinstance(versions[0], Mapping):
        raise ValueError("canonical candidate has no version record")
    selected = versions[0]
    version_id, title = selected.get("version_id"), selected.get("title")
    if not isinstance(version_id, str) or not isinstance(title, str):
        raise ValueError("canonical candidate version lacks ID or title")
    alternatives = tuple(
        str(item["version_id"]) for item in versions[1:]
        if isinstance(item, Mapping) and isinstance(item.get("version_id"), str)
    )
    doi = selected.get("doi") if isinstance(selected.get("doi"), str) else record.get("doi")
    return version_id, alternatives, title, doi if isinstance(doi, str) else None


def _provider_and_license(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return "OFFICIAL_PUBLISHER", "LICENSE_UNCONFIRMED"
    host = (parsed.hostname or "").casefold()
    path = parsed.path
    if host == "doi.org":
        doi_path = path.lstrip("/").casefold()
        for prefix, provider in _OA_DOI_PREFIXES.items():
            if doi_path.startswith(prefix):
                return provider, "OPEN_ACCESS_DECLARED"
        return "OFFICIAL_PUBLISHER", "LICENSE_UNCONFIRMED"
    if host == "drops.dagstuhl.de" and _OA_PDF_PATHS[host](path):
        return "LIPICS", "OPEN_ACCESS_DECLARED"
    if host in {"arxiv.org", "export.arxiv.org"} and _recognized_oa_url(url):
        return "ARXIV", "OPEN_ACCESS_DECLARED"
    if host == "proceedings.kr.org" and (_kr_proceedings_pdf_path(path) or _KR_LANDING_PATH.fullmatch(path)):
        return "KR_PROCEEDINGS", "OPEN_ACCESS_DECLARED"
    if host == "lmcs.episciences.org" and (
        re.fullmatch(r"/[0-9]+/pdf", path) or re.fullmatch(r"/[0-9]+/?", path)
    ):
        return "LMCS", "OPEN_ACCESS_DECLARED"
    return "OFFICIAL_PUBLISHER", "LICENSE_UNCONFIRMED"


def _approved_pdf_route(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return False
    allowed = _OA_PDF_PATHS.get((parsed.hostname or "").casefold())
    return allowed is not None and allowed(parsed.path)


def _route_provenance(requested_url: str, observed_url: str) -> str | None:
    observed_provider, _ = _provider_and_license(observed_url)
    if _approved_pdf_route(observed_url):
        return f"APPROVED_DIRECT:{observed_provider}_PDF"
    requested = urlsplit(requested_url)
    if requested.scheme == "https" and requested.hostname == "doi.org" and not requested.query and not requested.fragment:
        requested_provider, _ = _provider_and_license(requested_url)
        if requested_provider != "OFFICIAL_PUBLISHER" and urlsplit(observed_url).scheme == "https":
            return f"VERIFIED_DOI_RESOLUTION:{requested_provider}"
    return None


def _failure(record: Mapping[str, object], *, version_id: str, alternatives: tuple[str, ...], source_url: str,
             status: AcquisitionStatus, stamp: str, http_status: int | None, media_type: str | None,
             reason: str, provider: str | None = None, license_status: str | None = None,
             retry_policy: str = "NO_RETRY") -> AcquisitionManifest:
    selected_provider, selected_license = _provider_and_license(source_url)
    return AcquisitionManifest(
        paper_id=str(record["paper_id"]), version_id=version_id, source_url=source_url,
        provider=provider or selected_provider, source_tier="T1", requested_at=stamp, observed_at=stamp,
        status=status, http_status=http_status, media_type=media_type, byte_count=None, content_sha256=None,
        license_status=license_status or selected_license, redistribution_status="NOT_REDISTRIBUTED",
        cache_path=None, failure_reason=reason, retry_policy=retry_policy, selected_reading_version=version_id,
        alternatives=alternatives,
        route_provenance=(f"APPROVED_DOI_ROUTE:{selected_provider}" if _recognized_oa_url(source_url)
                          and urlsplit(source_url).hostname == "doi.org" else None),
    )


def acquire_candidate(record: Mapping[str, object], transport: UrllibTransport, *, cache_root: Path = CACHE,
                      retry_policy: str = "NO_RETRY") -> AcquisitionManifest:
    """Perform one legal OA acquisition attempt and record every outcome."""

    version_id, alternatives, title, doi = _version_fields(record)
    versions = record.get("versions")
    selected = versions[0] if isinstance(versions, list) and versions and isinstance(versions[0], Mapping) else {}
    author_value = selected.get("authors") if isinstance(selected, Mapping) else None
    if not isinstance(author_value, list):
        author_value = record.get("authors")
    authors = tuple(str(item) for item in author_value) if isinstance(author_value, list) else ()
    venue_value = selected.get("venue") if isinstance(selected, Mapping) else None
    if not isinstance(venue_value, str):
        venue_value = record.get("venue") if isinstance(record.get("venue"), str) else record.get("venue_family")
    source_url = str(record["official_url"])
    stamp = _stamp()
    try:
        landing = transport.get(source_url, timeout=30.0, max_bytes=2 * 1024 * 1024)
    except (OSError, TimeoutError) as caught:
        return _failure(record, version_id=version_id, alternatives=alternatives, source_url=source_url,
                        status=AcquisitionStatus.TRANSPORT_FAILURE, stamp=stamp, http_status=None, media_type=None,
                        reason=f"landing request failed: {type(caught).__name__}", retry_policy=retry_policy)
    media = _media_type(landing)
    response, pdf_url = landing, landing.url
    if media != "application/pdf":
        pdf_url = _pdf_link(landing)
        if pdf_url is None:
            status = AcquisitionStatus.HTML_OR_CHALLENGE if media in {"text/html", "application/xhtml+xml"} else AcquisitionStatus.HTTP_FAILURE
            return _failure(record, version_id=version_id, alternatives=alternatives, source_url=landing.url,
                            status=status, stamp=stamp, http_status=landing.status, media_type=media,
                            reason=KR_ROUTE_POLICY_FAILURE, retry_policy=retry_policy)
        try:
            response = transport.get(pdf_url, timeout=30.0, max_bytes=50 * 1024 * 1024)
        except (OSError, TimeoutError) as caught:
            return _failure(record, version_id=version_id, alternatives=alternatives, source_url=pdf_url,
                            status=AcquisitionStatus.TRANSPORT_FAILURE, stamp=stamp, http_status=None, media_type=None,
                            reason=f"declared PDF request failed: {type(caught).__name__}", retry_policy=retry_policy)
        media = _media_type(response)
    if response.status != 200:
        return _failure(record, version_id=version_id, alternatives=alternatives, source_url=pdf_url,
                        status=AcquisitionStatus.HTTP_FAILURE, stamp=stamp, http_status=response.status, media_type=media,
                        reason=f"official source returned HTTP {response.status}", retry_policy=retry_policy)
    route_provenance = _route_provenance(source_url, pdf_url)
    if media == "application/pdf" and route_provenance is None:
        return _failure(
            record, version_id=version_id, alternatives=alternatives, source_url=pdf_url,
            status=AcquisitionStatus.HTTP_FAILURE, stamp=stamp, http_status=response.status, media_type=media,
            reason="direct PDF did not use an approved host/route or verified DOI-resolution provenance",
            retry_policy=retry_policy,
        )
    validation = validate_pdf_payload(
        response.body,
        expected_title=title,
        expected_doi=doi,
        expected_authors=authors,
        expected_venue=venue_value if isinstance(venue_value, str) else None,
    )
    if validation.status is not PdfValidationStatus.VALID:
        status = AcquisitionStatus.HTML_OR_CHALLENGE if validation.status is PdfValidationStatus.HTML_OR_CHALLENGE else AcquisitionStatus.INVALID_PDF
        return _failure(record, version_id=version_id, alternatives=alternatives, source_url=pdf_url,
                        status=status, stamp=stamp, http_status=response.status, media_type=media,
                        reason=validation.failure_reason or validation.status.value, retry_policy=retry_policy)
    cache_root.mkdir(parents=True, exist_ok=True)
    key = version_id.split(":", 1)[1].replace("/", "-")
    target = cache_root / f"{key}.pdf"
    target.write_bytes(response.body)
    provider, license_status = _provider_and_license(pdf_url)
    return AcquisitionManifest(
        paper_id=str(record["paper_id"]), version_id=version_id, source_url=pdf_url, provider=provider, source_tier="T1",
        requested_at=stamp, observed_at=stamp, status=AcquisitionStatus.VALID_PDF, http_status=response.status,
        media_type=media, byte_count=len(response.body), content_sha256=validation.content_sha256,
        license_status=license_status, redistribution_status="CACHE_LOCAL_ONLY",
        cache_path=f"literature/fulltext_cache/{target.name}", failure_reason=None, retry_policy=retry_policy,
        selected_reading_version=version_id, alternatives=alternatives,
        route_provenance=route_provenance,
        page_count=validation.page_count,
        extracted_characters=validation.extracted_characters,
        validation_extraction_sha256=validation.validation_extraction_sha256,
        validation_extraction_normalization=validation.validation_extraction_normalization,
        reading_extraction_sha256=validation.reading_extraction_sha256,
        reading_extraction_normalization=validation.reading_extraction_normalization,
        title_match=validation.title_match,
        doi_match=validation.doi_match,
        identity_basis=validation.identity_basis,
    )


def _manifest_from_dict(value: Mapping[str, object]) -> AcquisitionManifest:
    return AcquisitionManifest(
        paper_id=str(value["paper_id"]), version_id=str(value["version_id"]), source_url=str(value["source_url"]),
        provider=str(value["provider"]), source_tier=str(value["source_tier"]), requested_at=str(value["requested_at"]),
        observed_at=str(value["observed_at"]), status=AcquisitionStatus(str(value["status"])),
        http_status=value.get("http_status") if isinstance(value.get("http_status"), int) else None,
        media_type=value.get("media_type") if isinstance(value.get("media_type"), str) else None,
        byte_count=value.get("byte_count") if isinstance(value.get("byte_count"), int) else None,
        content_sha256=value.get("content_sha256") if isinstance(value.get("content_sha256"), str) else None,
        license_status=str(value["license_status"]), redistribution_status=str(value["redistribution_status"]),
        cache_path=value.get("cache_path") if isinstance(value.get("cache_path"), str) else None,
        failure_reason=value.get("failure_reason") if isinstance(value.get("failure_reason"), str) else None,
        retry_policy=str(value["retry_policy"]), selected_reading_version=str(value["selected_reading_version"]),
        alternatives=tuple(value.get("alternatives", ())),
        route_provenance=value.get("route_provenance") if isinstance(value.get("route_provenance"), str) else None,
        page_count=value.get("page_count") if isinstance(value.get("page_count"), int) else None,
        extracted_characters=(value.get("extracted_characters")
                              if isinstance(value.get("extracted_characters"), int) else None),
        validation_extraction_sha256=(value.get("validation_extraction_sha256")
                                      if isinstance(value.get("validation_extraction_sha256"), str) else None),
        validation_extraction_normalization=(value.get("validation_extraction_normalization")
                                             if isinstance(value.get("validation_extraction_normalization"), str) else None),
        reading_extraction_sha256=(value.get("reading_extraction_sha256")
                                   if isinstance(value.get("reading_extraction_sha256"), str) else None),
        reading_extraction_normalization=(value.get("reading_extraction_normalization")
                                          if isinstance(value.get("reading_extraction_normalization"), str) else None),
        title_match=value.get("title_match") if isinstance(value.get("title_match"), bool) else None,
        doi_match=value.get("doi_match") if isinstance(value.get("doi_match"), bool) else None,
        identity_basis=value.get("identity_basis") if isinstance(value.get("identity_basis"), str) else None,
        attempt_id=value.get("attempt_id") if isinstance(value.get("attempt_id"), str) else None,
        history_origin=str(value.get("history_origin", "LEGACY_COMMITTED_HISTORY")),
    )


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def write_manifests(manifests: Iterable[AcquisitionManifest], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(manifests, key=lambda item: (item.paper_id, item.version_id))
    destination.write_text("".join(json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in ordered), encoding="utf-8")


def write_attempts(attempts: Iterable[AcquisitionManifest], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    values = tuple(attempts)
    if len({item.attempt_id for item in values}) != len(values):
        raise ValueError("attempt ledger cannot contain duplicate immutable attempts")
    ordered = sorted(values, key=lambda item: (item.requested_at, str(item.attempt_id)))
    destination.write_text(
        "".join(json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for item in ordered),
        encoding="utf-8",
    )


def _listed(values: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={values[key]}" for key in sorted(values)) or "none"


def _validated_report_provenance(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return {"implementation_commits": [], "commands": [], "test_results": [], "runtime": {}, "limitations": []}
    required = {"implementation_commits", "commands", "test_results", "runtime", "limitations"}
    if set(value) != required:
        raise ValueError("report provenance has missing or unknown fields")
    commits = value["implementation_commits"]
    if not isinstance(commits, list) or any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{7,40}", item) is None
                                            for item in commits):
        raise ValueError("report implementation commits must be validated Git IDs")
    commands = value["commands"]
    if not isinstance(commands, list) or any(not isinstance(item, str) or not item.strip() for item in commands):
        raise ValueError("report commands must be nonempty strings")
    results = value["test_results"]
    if not isinstance(results, list):
        raise ValueError("report test_results must be a list")
    for result in results:
        if not isinstance(result, Mapping) or set(result) != {"command", "passed", "failed"}:
            raise ValueError("test result requires command, passed, and failed")
        if not isinstance(result["command"], str) or any(
            isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
            for key in ("passed", "failed")
        ):
            raise ValueError("test result values are invalid")
    runtime = value["runtime"]
    if not isinstance(runtime, Mapping) or any(not isinstance(key, str) or not isinstance(item, str)
                                               for key, item in runtime.items()):
        raise ValueError("runtime provenance must map names to versions")
    limitations = value["limitations"]
    if not isinstance(limitations, list) or any(not isinstance(item, str) or not item.strip() for item in limitations):
        raise ValueError("report limitations must be nonempty strings")
    return value


def render_report(
    selected_counts: Mapping[str, int],
    *args: Mapping[str, object],
    reading_coverage: Mapping[str, Mapping[str, Mapping[str, int]]] | None = None,
    reading_shortfalls: tuple[Mapping[str, object], ...] = (),
    provenance: Mapping[str, object] | None = None,
    validation_summary: Mapping[str, object] | None = None,
    bundle_hashes: Mapping[str, str] | None = None,
) -> str:
    """Render exact selected-outcome, attempt-history, reading, and frozen provenance counts."""

    if len(args) == 6:  # Backward-compatible unit-call shape: selected, reading, coverage dimensions.
        read_depth, topics, years, venues, providers, licenses = args
        attempt_counts: Mapping[str, object] = {
            "attempts": selected_counts.get("attempts", selected_counts.get("outcomes", 0)),
            **{key: value for key, value in selected_counts.items() if key not in {"attempts", "outcomes"}},
        }
    elif len(args) == 7:
        attempt_counts, read_depth, topics, years, venues, providers, licenses = args
    else:
        raise TypeError("render_report requires selected and attempt/read/coverage mappings")
    frozen = _validated_report_provenance(provenance)
    task4_authorized = any("Task 4 is authorized" in item for item in frozen["limitations"])
    validation = validation_summary or {}
    hashes = bundle_hashes or {}
    full_scan = int(read_depth.get("FULL_SCAN", 0))
    deep_read = int(read_depth.get("DEEP_READ", 0))
    full_scan_only = int(read_depth.get("FULL_SCAN_ONLY", max(0, full_scan - deep_read)))
    shortfall = int(read_depth.get("SHORTFALL", max(0, int(selected_counts.get("valid_pdf", 0)) - full_scan)))
    result = (
        f"TASK3_FINAL_PASS — the frozen corpus establishes {full_scan} FULL_SCAN and {deep_read} DEEP_READ "
        "records; independent Spec and Quality gates pass and Task 4 is authorized."
        if task4_authorized
        else (
            "DONE_WITH_CONCERNS — every promoted note is bound to a source-verified audit; "
            f"the frozen corpus currently establishes {full_scan} FULL_SCAN and {deep_read} DEEP_READ records."
        )
    )
    coverage = reading_coverage or {}
    full_coverage = coverage.get("FULL_SCAN", {})
    deep_coverage = coverage.get("DEEP_READ", {})
    shortfall_lines = tuple(
        f"- `{item.get('paper_id')}` ({item.get('read_depth')}): {item.get('shortfall_reason')}"
        for item in reading_shortfalls
    ) or ("- none",)
    commit_lines = tuple(f"- `{item}`" for item in frozen["implementation_commits"]) or ("- none supplied",)
    command_lines = tuple(f"- `{item}`" for item in frozen["commands"]) or ("- none supplied",)
    test_lines = tuple(
        f"- `{item['command']}`: {item['passed']} passed; {item['failed']} failed"
        for item in frozen["test_results"]
    ) or ("- none supplied",)
    runtime_lines = tuple(f"- {key}: {value}" for key, value in sorted(frozen["runtime"].items())) or ("- none supplied",)
    limitation_lines = tuple(f"- {item}" for item in frozen["limitations"]) or ("- none supplied",)
    hash_lines = tuple(f"- {key}: `{value}`" for key, value in sorted(hashes.items())) or ("- none supplied",)
    gate_line = (
        "- Spec and Quality reviews: PASS (Critical=0, Important=0); Task 4 is authorized."
        if task4_authorized
        else "- External review remains required before progress can change; progress is intentionally unchanged."
    )
    return "\n".join((
        "# Corpus Task 3 Report", "", "## Result", "", result, "",
        "## Selected current outcomes", "",
        f"- Selected outcomes: {selected_counts.get('outcomes', selected_counts.get('attempts', 0))}",
        f"- Valid PDFs: {selected_counts.get('valid_pdf', 0)}",
        f"- HTML/challenge: {selected_counts.get('html_or_challenge', 0)}",
        f"- HTTP failures: {selected_counts.get('http_failure', 0)}",
        f"- Transport failures: {selected_counts.get('transport_failure', 0)}",
        f"- Invalid PDFs: {selected_counts.get('invalid_pdf', 0)}", "",
        "## Immutable attempt history", "",
        f"- Total immutable attempts: {attempt_counts.get('attempts', 0)}",
        f"- Valid PDFs in attempt history: {attempt_counts.get('valid_pdf', 0)}",
        f"- HTML/challenge in attempt history: {attempt_counts.get('html_or_challenge', 0)}",
        f"- Transport failures in attempt history: {attempt_counts.get('transport_failure', 0)}",
        f"- HTTP failures in attempt history: {attempt_counts.get('http_failure', 0)}",
        f"- Invalid PDFs in attempt history: {attempt_counts.get('invalid_pdf', 0)}", "",
        "## Source-verified reading counts", "",
        f"- FULL_SCAN: {full_scan}", f"- FULL_SCAN only: {full_scan_only}",
        f"- DEEP_READ: {deep_read}", f"- Reading shortfalls: {shortfall}",
        f"- Target shortfalls: FULL_SCAN={max(0, 120 - full_scan)}, DEEP_READ={max(0, 80 - deep_read)}", "",
        "## Validation provenance", "",
        f"- Complete validation records: {validation.get('complete_records', 0)}",
        f"- Identity basis: {_listed(validation.get('identity_basis', {}))}",
        f"- Validation extraction normalization: {_listed(validation.get('validation_normalization', {}))}",
        f"- Reading extraction normalization: {_listed(validation.get('reading_normalization', {}))}", "",
        "## Coverage of selected outcomes", "", f"- Topics: {_listed(topics)}", f"- Years: {_listed(years)}",
        f"- Venues: {_listed(venues)}", "", "## Source and license distribution", "",
        f"- Providers: {_listed(providers)}", f"- License status: {_listed(licenses)}", "",
        "## Reading-depth coverage", "",
        f"- FULL_SCAN topics: {_listed(full_coverage.get('topics', {}))}",
        f"- FULL_SCAN years: {_listed(full_coverage.get('years', {}))}",
        f"- FULL_SCAN venues: {_listed(full_coverage.get('venues', {}))}",
        f"- DEEP_READ topics: {_listed(deep_coverage.get('topics', {}))}",
        f"- DEEP_READ years: {_listed(deep_coverage.get('years', {}))}",
        f"- DEEP_READ venues: {_listed(deep_coverage.get('venues', {}))}", "",
        "## Reading shortfalls", "", *shortfall_lines, "",
        "## Frozen bundle hashes", "", *hash_lines, "",
        "## Reproduction commands", "", *command_lines, "",
        "## Test evidence", "", *test_lines, "",
        "## Extraction runtime", "", *runtime_lines, "",
        "## Implementation commits", "", *commit_lines, "",
        "## Limitations and concerns", "", *limitation_lines, gate_line, "",
    ))


def _coverage(manifests: Iterable[AcquisitionManifest], records: Iterable[Mapping[str, object]]) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    by_id = {str(item.get("paper_id")): item for item in records if isinstance(item.get("paper_id"), str)}
    topics: dict[str, int] = {}
    years: dict[str, int] = {}
    venues: dict[str, int] = {}
    for manifest in manifests:
        record = by_id.get(manifest.paper_id)
        if record is None:
            continue
        topic, year, venue = _topic(record), record.get("year"), record.get("venue_family")
        topics[topic] = topics.get(topic, 0) + 1
        if isinstance(year, int):
            years[str(year)] = years.get(str(year), 0) + 1
        if isinstance(venue, str):
            venues[venue] = venues.get(venue, 0) + 1
    return topics, years, venues


def _reading_coverage(records: Iterable[Mapping[str, object]]) -> dict[str, dict[str, dict[str, int]]]:
    result: dict[str, dict[str, dict[str, int]]] = {}
    values = tuple(records)
    for label, accepted in (("FULL_SCAN", {"FULL_SCAN", "DEEP_READ"}), ("DEEP_READ", {"DEEP_READ"})):
        dimensions: dict[str, dict[str, int]] = {"topics": {}, "years": {}, "venues": {}}
        for item in values:
            if item.get("read_depth") not in accepted:
                continue
            for dimension, field in (("topics", "topic"), ("years", "year"), ("venues", "venue")):
                value = item.get(field)
                if value is None:
                    continue
                key = str(value)
                dimensions[dimension][key] = dimensions[dimension].get(key, 0) + 1
        result[label] = dimensions
    return result


def _reading_bundle_hash(notes: Path, ledger: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in notes.glob("*.md") if path.name != "README.md") + [ledger]
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def _validation_summary(manifests: Iterable[AcquisitionManifest]) -> dict[str, object]:
    valid = tuple(item for item in manifests if item.status is AcquisitionStatus.VALID_PDF)
    identity: dict[str, int] = {}
    validation_norm: dict[str, int] = {}
    reading_norm: dict[str, int] = {}
    complete = 0
    for item in valid:
        complete += bool(item.has_complete_validation_provenance)
        if item.identity_basis:
            identity[item.identity_basis] = identity.get(item.identity_basis, 0) + 1
        if item.validation_extraction_normalization:
            key = item.validation_extraction_normalization
            validation_norm[key] = validation_norm.get(key, 0) + 1
        if item.reading_extraction_normalization:
            key = item.reading_extraction_normalization
            reading_norm[key] = reading_norm.get(key, 0) + 1
    return {
        "complete_records": complete,
        "identity_basis": identity,
        "validation_normalization": validation_norm,
        "reading_normalization": reading_norm,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="perform bounded, official-source acquisition attempts")
    parser.add_argument("--limit", type=int, default=30, help="maximum selected family attempts per live batch")
    parser.add_argument("--oa-only", action="store_true", help="restrict live batches to recognized official OA DOI families")
    parser.add_argument("--retry-status", action="append", choices=tuple(item.value for item in RETRYABLE_STATUSES), default=[],
                        help="explicitly retry one prior result of this status; each record permits one retry only")
    parser.add_argument("--recover-identity-mismatch", action="store_true",
                        help="replace once only INVALID_PDF rows with the exact prior identity-policy mismatch")
    parser.add_argument("--recover-kr-route-policy", action="store_true",
                        help="replace once only exact 2023--2026 KR route-policy HTML failures")
    parser.add_argument("--dry-run", action="store_true", help="print the deterministic live batch plan without requests or writes")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root containing the frozen PDF cache")
    parser.add_argument("--papers", type=Path, default=PAPERS)
    parser.add_argument("--manifests", type=Path, default=MANIFESTS)
    parser.add_argument("--attempts", type=Path, default=ATTEMPTS)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--read-ledger", type=Path, default=READ_LEDGER)
    parser.add_argument("--notes", type=Path, default=NOTES)
    parser.add_argument("--audits", type=Path, default=None)
    parser.add_argument("--deep-read-target", type=int, default=80)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--provenance", type=Path, default=None)
    args = parser.parse_args(argv)
    audits_path = args.audits or args.root / "literature" / "fulltext_audits" / "source_validation_2026_08_30.jsonl"
    provenance_path = args.provenance or args.root / ".superpowers" / "sdd" / "corpus-task-3-provenance.json"
    if args.live:
        records = _read_jsonl(args.papers)
        existing = tuple(_manifest_from_dict(item) for item in _read_jsonl(args.manifests)) if args.manifests.is_file() else ()
        attempts = tuple(_manifest_from_dict(item) for item in _read_jsonl(args.attempts)) if args.attempts.is_file() else existing
        retry_statuses = frozenset(AcquisitionStatus(item) for item in args.retry_status)
        candidates = select_live_candidates(records, existing, limit=args.limit, retry_statuses=retry_statuses,
                                            oa_only=args.oa_only, recover_identity_mismatch=args.recover_identity_mismatch,
                                            recover_kr_route_policy=args.recover_kr_route_policy)
        existing_by_key = {_manifest_key(item): item for item in existing}
        if args.dry_run:
            plan = [
                {"paper_id": str(item["paper_id"]), "version_id": _version_fields(item)[0],
                 "action": planned_action(existing_by_key.get(_candidate_key(item))),
                 "source_url": str(item["official_url"])}
                for item in candidates
            ]
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        outcomes: list[AcquisitionManifest] = []
        for candidate in candidates:
            previous = existing_by_key.get(_candidate_key(candidate))
            policy = next_retry_policy(previous)
            outcome = acquire_candidate(candidate, UrllibTransport(), cache_root=args.root / "literature" / "fulltext_cache",
                                        retry_policy=policy)
            outcomes.append(outcome)
        manifests, attempts = conserve_attempt_history(existing, attempts, outcomes)
        write_manifests(manifests, args.manifests)
        write_attempts(attempts, args.attempts)
    else:
        manifests = tuple(_manifest_from_dict(item) for item in _read_jsonl(args.manifests))
        attempts = tuple(_manifest_from_dict(item) for item in _read_jsonl(args.attempts)) if args.attempts.is_file() else manifests
    counts = build_offline_ledger(manifests, args.ledger, attempt_history=attempts)
    records = _read_jsonl(args.papers)
    audits = _read_jsonl(audits_path) if audits_path.is_file() else ()
    reading = build_reading_corpus(
        manifests, records, args.root, args.notes, args.read_ledger,
        audits=audits,
        deep_read_target=args.deep_read_target,
    )
    topics, years, venues = _coverage(manifests, records)
    providers: dict[str, int] = {}
    licenses: dict[str, int] = {}
    for manifest in manifests:
        providers[manifest.provider] = providers.get(manifest.provider, 0) + 1
        licenses[manifest.license_status] = licenses.get(manifest.license_status, 0) + 1
    reading_records = tuple(item for item in reading["records"] if isinstance(item, Mapping))
    shortfalls = tuple(item for item in reading_records if item.get("read_depth") not in {"FULL_SCAN", "DEEP_READ"})
    frozen_provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else None
    bundle_hashes = {
        "selected_outcomes": _file_sha256(args.manifests),
        "immutable_attempts": _file_sha256(args.attempts) if args.attempts.is_file() else _file_sha256(args.manifests),
        "reading_notes_and_ledger": _reading_bundle_hash(args.notes, args.read_ledger),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(
        counts["selected_outcomes"], counts["attempt_history"], reading["counts"],
        topics, years, venues, providers, licenses,
        reading_coverage=_reading_coverage(reading_records),
        reading_shortfalls=shortfalls,
        provenance=frozen_provenance,
        validation_summary=_validation_summary(manifests),
        bundle_hashes=bundle_hashes,
    ), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
