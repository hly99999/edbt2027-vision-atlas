"""One-time offline migration for Task 3 attempt history and PDF provenance.

This script reads only committed repository history, canonical metadata, and the
existing PDF cache.  It performs no network access and never writes PDF bytes.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import platform
import subprocess

import pypdf

from db_theory_atlas.corpus_task3 import AcquisitionStatus, PdfValidationStatus, validate_pdf_payload
from scripts import build_fulltext_corpus as corpus


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_LEDGER = ROOT / "literature" / "fulltext_ledgers" / "extractor_runtime_2026_08_30.json"
INITIAL_COMMIT = "9a1c12e"
CURRENT_COMMIT = "b3eb2e4"
MANIFEST_PATH = "literature/fulltext_manifests/acquisition_2026_08_30.jsonl"


def _committed_rows(commit: str) -> tuple[dict[str, object], ...]:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{MANIFEST_PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(json.loads(line) for line in completed.stdout.splitlines() if line.strip())


def _identity(record: dict[str, object], version_id: str) -> tuple[str, str | None, tuple[str, ...], str | None]:
    versions = record.get("versions")
    selected = next(
        (item for item in versions if isinstance(item, dict) and item.get("version_id") == version_id),
        None,
    ) if isinstance(versions, list) else None
    if not isinstance(selected, dict):
        raise ValueError(f"canonical version {version_id} is missing for {record.get('paper_id')}")
    title = selected.get("title")
    if not isinstance(title, str):
        raise ValueError("selected version title is missing")
    doi = selected.get("doi") if isinstance(selected.get("doi"), str) else record.get("doi")
    raw_authors = selected.get("authors") if isinstance(selected.get("authors"), list) else record.get("authors")
    authors = tuple(str(item) for item in raw_authors) if isinstance(raw_authors, list) else ()
    venue = selected.get("venue") if isinstance(selected.get("venue"), str) else record.get("venue")
    if not isinstance(venue, str):
        venue = record.get("venue_family") if isinstance(record.get("venue_family"), str) else None
    return title, doi if isinstance(doi, str) else None, authors, venue


def _route_provenance(url: str, status: AcquisitionStatus) -> str:
    direct = corpus._route_provenance(url, url)
    if direct is not None:
        return direct
    parsed = corpus.urlsplit(url)
    provider, _ = corpus._provider_and_license(url)
    if parsed.scheme == "https" and parsed.hostname == "doi.org" and not parsed.query and not parsed.fragment:
        return f"APPROVED_DOI_ROUTE:{provider}"
    if status is AcquisitionStatus.HTML_OR_CHALLENGE and corpus._recognized_oa_url(url):
        return f"APPROVED_DIRECT:{provider}_LANDING"
    raise ValueError(f"selected outcome uses an unapproved route: {url}")


def main() -> int:
    papers = {row["paper_id"]: row for row in corpus._read_jsonl(corpus.PAPERS)}
    current = tuple(corpus._manifest_from_dict(row) for row in _committed_rows(CURRENT_COMMIT))
    enriched = []
    identity_counts: dict[str, int] = {}
    for item in current:
        provenance = _route_provenance(item.source_url, item.status)
        if item.status is not AcquisitionStatus.VALID_PDF:
            enriched.append(replace(
                item,
                route_provenance=provenance,
                history_origin=f"RECOVERED_COMMIT:{CURRENT_COMMIT}",
                attempt_id=None,
            ))
            continue
        record = papers[item.paper_id]
        title, doi, authors, venue = _identity(record, item.version_id)
        payload = (ROOT / str(item.cache_path)).read_bytes()
        validation = validate_pdf_payload(
            payload,
            expected_title=title,
            expected_doi=doi,
            expected_authors=authors,
            expected_venue=venue,
        )
        if validation.status is not PdfValidationStatus.VALID:
            raise ValueError(f"strict identity revalidation failed for {item.paper_id}: {validation.failure_reason}")
        if validation.content_sha256 != item.content_sha256 or len(payload) != item.byte_count:
            raise ValueError(f"cache conservation failed for {item.paper_id}")
        basis = str(validation.identity_basis)
        identity_counts[basis] = identity_counts.get(basis, 0) + 1
        enriched.append(replace(
            item,
            route_provenance=provenance,
            page_count=validation.page_count,
            extracted_characters=validation.extracted_characters,
            validation_extraction_sha256=validation.validation_extraction_sha256,
            validation_extraction_normalization=validation.validation_extraction_normalization,
            reading_extraction_sha256=validation.reading_extraction_sha256,
            reading_extraction_normalization=validation.reading_extraction_normalization,
            title_match=validation.title_match,
            doi_match=validation.doi_match,
            identity_basis=validation.identity_basis,
            history_origin=f"RECOVERED_COMMIT:{CURRENT_COMMIT}",
            attempt_id=None,
        ))
    selected = tuple(sorted(enriched, key=lambda item: (item.paper_id, item.version_id)))

    initial = tuple(
        replace(
            corpus._manifest_from_dict(row),
            route_provenance=_route_provenance(str(row["source_url"]), AcquisitionStatus(str(row["status"]))),
            history_origin=f"RECOVERED_COMMIT:{INITIAL_COMMIT}",
            attempt_id=None,
        )
        for row in _committed_rows(INITIAL_COMMIT)
    )
    attempts_by_id = {item.attempt_id: item for item in initial}
    for item in selected:
        attempts_by_id.setdefault(item.attempt_id, item)
    attempts = tuple(sorted(attempts_by_id.values(), key=lambda item: (item.requested_at, str(item.attempt_id))))

    corpus.write_manifests(selected, corpus.MANIFESTS)
    corpus.write_attempts(attempts, corpus.ATTEMPTS)
    runtime = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "pypdf_version": pypdf.__version__,
        "validation_extraction_normalization": "PYPDF_PAGE_TEXT_JOIN_LF_V1",
        "reading_extraction_normalization": "PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1",
        "selected_outcomes": len(selected),
        "immutable_attempts": len(attempts),
        "valid_pdf_provenance_records": sum(item.status is AcquisitionStatus.VALID_PDF for item in selected),
        "identity_basis": identity_counts,
        "history_sources": [INITIAL_COMMIT, CURRENT_COMMIT],
        "unrecoverable_intermediate_attempt_details": (
            "Retry-policy markers show that some validation/route recovery operations occurred between committed "
            "snapshots, but no immutable operational row was committed for those intermediate attempts; no row was invented."
        ),
    }
    RUNTIME_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_LEDGER.write_text(
        json.dumps(runtime, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(runtime, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
