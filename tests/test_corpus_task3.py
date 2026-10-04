from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from db_theory_atlas.ingest import HttpResponse
from db_theory_atlas.corpus_task3 import (
    AcquisitionManifest,
    AcquisitionStatus,
    PdfValidationStatus,
    build_offline_ledger,
    validate_pdf_payload,
)
from scripts import build_fulltext_corpus as corpus


def _pdf(title: str, doi: str, *, author: str = "Ada Lovelace") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({title} {doi}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Title": title, "/Subject": doi, "/Author": author})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_validation_requires_signature_pages_extractable_identity_and_hash() -> None:
    payload = _pdf("Acyclic Query Evaluation", "10.4230/LIPIcs.ICDT.2026.1")

    validation = validate_pdf_payload(
        payload,
        expected_title="Acyclic Query Evaluation",
        expected_doi="10.4230/lipics.icdt.2026.1",
    )

    assert validation.status is PdfValidationStatus.VALID
    assert validation.page_count == 1
    assert validation.content_sha256
    assert validation.extraction_sha256
    assert validation.title_match is True
    assert validation.doi_match is True


def test_html_is_never_reported_as_a_pdf() -> None:
    validation = validate_pdf_payload(
        b"<html><title>Sign in</title></html>",
        expected_title="Acyclic Query Evaluation",
        expected_doi=None,
    )

    assert validation.status is PdfValidationStatus.HTML_OR_CHALLENGE
    assert validation.page_count is None


def test_pdf_validation_accepts_a_matching_doi_when_title_extraction_is_not_exact() -> None:
    validation = validate_pdf_payload(
        _pdf("A Different Display Title", "10.4230/LIPIcs.ICDT.2026.12"),
        expected_title="The Complexity of Finding Missing Answer Repairs",
        expected_doi="10.4230/lipics.icdt.2026.12",
    )

    assert validation.status is PdfValidationStatus.VALID
    assert validation.title_match is False
    assert validation.doi_match is True


def test_pdf_validation_accepts_a_robust_full_title_without_a_doi() -> None:
    validation = validate_pdf_payload(
        _pdf("Acyclic-\nQuery Evaluation: Robustness", "10.4230/LIPIcs.ICDT.2026.1"),
        expected_title="Acyclic Query Evaluation Robustness",
        expected_doi=None,
        expected_authors=("Ada Lovelace",),
    )

    assert validation.status is PdfValidationStatus.VALID
    assert validation.title_match is True
    assert validation.doi_match is None


def test_pdf_validation_rejects_an_unrelated_document_when_both_identities_fail() -> None:
    validation = validate_pdf_payload(
        _pdf("An Unrelated Paper", "10.4230/LIPIcs.ICDT.2026.99"),
        expected_title="The Complexity of Finding Missing Answer Repairs",
        expected_doi="10.4230/lipics.icdt.2026.12",
    )

    assert validation.status is PdfValidationStatus.IDENTITY_MISMATCH
    assert validation.title_match is False
    assert validation.doi_match is False


def test_pdf_validation_rejects_when_title_and_optional_doi_are_both_missing() -> None:
    validation = validate_pdf_payload(
        _pdf("An Unrelated Paper", "10.4230/LIPIcs.ICDT.2026.99"),
        expected_title="The Complexity of Finding Missing Answer Repairs",
        expected_doi=None,
    )

    assert validation.status is PdfValidationStatus.IDENTITY_MISMATCH
    assert validation.title_match is False
    assert validation.doi_match is None


def test_manifest_hash_ignores_operational_time_but_binds_reading_version_and_pdf_hash() -> None:
    base = AcquisitionManifest(
        paper_id="paper:acyclic-2026",
        version_id="version:acyclic-preprint",
        source_url="https://drops.example/paper.pdf",
        provider="LIPICS",
        source_tier="T1",
        requested_at="2026-08-30T00:00:00Z",
        observed_at="2026-08-30T00:00:00Z",
        status=AcquisitionStatus.VALID_PDF,
        http_status=200,
        media_type="application/pdf",
        byte_count=123,
        content_sha256="a" * 64,
        license_status="OPEN_ACCESS",
        redistribution_status="CACHE_LOCAL_ONLY",
        cache_path="literature/fulltext_cache/acyclic.pdf",
        failure_reason=None,
        retry_policy="NO_RETRY",
        selected_reading_version="version:acyclic-preprint",
        alternatives=("version:acyclic-conference",),
    )

    moved_time = replace(base, observed_at="2026-09-01T00:00:00Z")
    changed_version = replace(
        base,
        selected_reading_version="version:acyclic-journal",
        alternatives=("version:acyclic-conference",),
    )

    assert base.scientific_hash == moved_time.scientific_hash
    assert base.scientific_hash != changed_version.scientific_hash


def test_offline_ledger_reports_exact_counts_and_refuses_note_without_valid_source(tmp_path: Path) -> None:
    valid = AcquisitionManifest(
        paper_id="paper:acyclic-2026",
        version_id="version:acyclic-preprint",
        source_url="https://drops.example/paper.pdf",
        provider="LIPICS",
        source_tier="T1",
        requested_at="2026-08-30T00:00:00Z",
        observed_at="2026-08-30T00:00:00Z",
        status=AcquisitionStatus.VALID_PDF,
        http_status=200,
        media_type="application/pdf",
        byte_count=123,
        content_sha256="a" * 64,
        license_status="OPEN_ACCESS",
        redistribution_status="CACHE_LOCAL_ONLY",
        cache_path="literature/fulltext_cache/acyclic.pdf",
        failure_reason=None,
        retry_policy="NO_RETRY",
        selected_reading_version="version:acyclic-preprint",
        alternatives=(),
    )
    html = replace(valid, paper_id="paper:html-2026", status=AcquisitionStatus.HTML_OR_CHALLENGE,
                   content_sha256=None, byte_count=None, cache_path=None,
                   failure_reason="publisher returned HTML login page")

    ledger = build_offline_ledger((valid, html), tmp_path / "ledger.json")

    assert ledger["attempts"] == 2
    assert ledger["valid_pdf"] == 1
    assert ledger["html_or_challenge"] == 1
    assert (tmp_path / "ledger.json").is_file()


def test_priority_selection_is_deterministic_and_preserves_topic_venue_diversity() -> None:
    records = (
        {"paper_id": "paper:a", "venue_family": "ICDT", "year": 2026, "official_url": "https://doi.org/10.4230/LIPIcs.ICDT.2026.1",
         "screening": {"relevant": True, "DEEP_READ_PRIORITY_SCORE": 12, "primary_topic_id": "cq"}},
        {"paper_id": "paper:b", "venue_family": "PODS", "year": 2025, "official_url": "https://doi.org/10.1145/1",
         "screening": {"relevant": True, "DEEP_READ_PRIORITY_SCORE": 11, "primary_topic_id": "cq"}},
        {"paper_id": "paper:c", "venue_family": "LICS", "year": 2026, "official_url": "https://doi.org/10.4230/LIPIcs.LICS.2026.1",
         "screening": {"relevant": True, "DEEP_READ_PRIORITY_SCORE": 10, "primary_topic_id": "csp"}},
        {"paper_id": "paper:d", "venue_family": "ICDT", "year": 2026, "official_url": "https://doi.org/10.4230/LIPIcs.ICDT.2026.2",
         "screening": {"relevant": False, "DEEP_READ_PRIORITY_SCORE": 99, "primary_topic_id": "cq"}},
    )

    selected = corpus.select_candidates(records, limit=3)

    assert [item["paper_id"] for item in selected] == ["paper:a", "paper:c", "paper:b"]


def test_cache_is_gitignored_and_offline_rebuild_is_byte_identical(tmp_path: Path) -> None:
    manifests = (
        AcquisitionManifest(
            paper_id="paper:acyclic-2026", version_id="version:acyclic-preprint",
            source_url="https://drops.example/paper.pdf", provider="LIPICS", source_tier="T1",
            requested_at="2026-08-30T00:00:00Z", observed_at="2026-08-30T00:00:00Z",
            status=AcquisitionStatus.VALID_PDF, http_status=200, media_type="application/pdf", byte_count=123,
            content_sha256="a" * 64, license_status="OPEN_ACCESS", redistribution_status="CACHE_LOCAL_ONLY",
            cache_path="literature/fulltext_cache/acyclic.pdf", failure_reason=None, retry_policy="NO_RETRY",
            selected_reading_version="version:acyclic-preprint", alternatives=(),
        ),
    )
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    build_offline_ledger(manifests, first)
    build_offline_ledger(tuple(reversed(manifests)), second)

    assert first.read_bytes() == second.read_bytes()
    assert "literature/fulltext_cache/" in (Path(__file__).parents[1] / ".gitignore").read_text(encoding="utf-8")


def test_offline_report_is_exact_about_shortfalls() -> None:
    report = corpus.render_report(
        {"attempts": 120, "valid_pdf": 0, "html_or_challenge": 0, "http_failure": 0,
         "transport_failure": 120, "invalid_pdf": 0, "not_attempted": 0},
        {"FULL_SCAN": 0, "DEEP_READ": 0},
        {"cq": 8}, {"2026": 9}, {"ICDT": 10},
        {"OFFICIAL_PUBLISHER": 120}, {"LICENSE_UNCONFIRMED": 120},
    )

    assert "Selected outcomes: 120" in report
    assert "Total immutable attempts: 120" in report
    assert "Valid PDFs: 0" in report
    assert "FULL_SCAN: 0" in report
    assert "shortfall" in report.casefold()


def _candidate(paper_id: str, *, score: int = 12) -> dict[str, object]:
    return {
        "paper_id": paper_id,
        "official_url": f"https://doi.org/10.4230/LIPIcs.ICDT.2026.{paper_id[-1]}",
        "venue_family": "ICDT",
        "year": 2026,
        "versions": [{"version_id": f"version:{paper_id[-1]}", "title": "Acyclic Query Evaluation", "doi": "10.4230/LIPIcs.ICDT.2026.1"}],
        "screening": {"relevant": True, "DEEP_READ_PRIORITY_SCORE": score, "primary_topic_id": "cq"},
    }


def _transport_failure(paper_id: str, *, retry_policy: str = "NO_RETRY") -> AcquisitionManifest:
    return AcquisitionManifest(
        paper_id=paper_id, version_id=f"version:{paper_id[-1]}", source_url="https://doi.org/10.4230/LIPIcs.ICDT.2026.1",
        provider="OFFICIAL_PUBLISHER", source_tier="T1", requested_at="2026-08-30T00:00:00Z",
        observed_at="2026-08-30T00:00:00Z", status=AcquisitionStatus.TRANSPORT_FAILURE, http_status=None,
        media_type=None, byte_count=None, content_sha256=None, license_status="LICENSE_UNCONFIRMED",
        redistribution_status="NOT_REDISTRIBUTED", cache_path=None, failure_reason="network unavailable",
        retry_policy=retry_policy, selected_reading_version=f"version:{paper_id[-1]}", alternatives=(),
    )


def test_live_selection_retries_only_explicit_once_eligible_transport_failures() -> None:
    retryable = _transport_failure("paper:a")
    exhausted = _transport_failure("paper:b", retry_policy="RETRY_ONCE:TRANSPORT_FAILURE")
    terminal = replace(exhausted, paper_id="paper:c", version_id="version:c", status=AcquisitionStatus.HTML_OR_CHALLENGE,
                       failure_reason="official landing page did not declare an OA PDF")
    records = (_candidate("paper:a", score=10), _candidate("paper:b", score=11), _candidate("paper:c", score=12), _candidate("paper:d", score=9))

    selected = corpus.select_live_candidates(
        records, (retryable, exhausted, terminal), limit=4,
        retry_statuses=frozenset({AcquisitionStatus.TRANSPORT_FAILURE}),
    )

    assert [item["paper_id"] for item in selected] == ["paper:a", "paper:d"]


def test_retry_replacement_conserves_one_manifest_per_paper_version_and_marks_policy() -> None:
    prior = _transport_failure("paper:a")
    replacement = replace(prior, requested_at="2026-08-31T00:00:00Z", observed_at="2026-08-31T00:00:00Z",
                          retry_policy="RETRY_ONCE:TRANSPORT_FAILURE", failure_reason="official PDF request timed out")
    untouched = _transport_failure("paper:b")

    merged = corpus.replace_manifests((prior, untouched), (replacement,))

    assert len(merged) == 2
    assert [item.paper_id for item in merged] == ["paper:a", "paper:b"]
    assert merged[0] is replacement
    assert merged[0].retry_policy == "RETRY_ONCE:TRANSPORT_FAILURE"


def test_retry_planning_and_manifest_serialization_are_deterministic() -> None:
    records = (_candidate("paper:a", score=10), _candidate("paper:d", score=9))
    prior = _transport_failure("paper:a")

    first = corpus.select_live_candidates(records, (prior,), limit=2, retry_statuses=frozenset({AcquisitionStatus.TRANSPORT_FAILURE}))
    second = corpus.select_live_candidates(tuple(reversed(records)), (prior,), limit=2, retry_statuses=frozenset({AcquisitionStatus.TRANSPORT_FAILURE}))

    assert first == second


def test_explicit_oa_provider_routes_allow_declared_kr_and_lmcs_pdf_paths() -> None:
    kr = HttpResponse(200, {"Content-Type": "text/html"}, b'<a href="/2026/19/kr2026-0019-bogaerts-et-al.pdf">PDF</a>',
                      "https://proceedings.kr.org/2026/19/")
    lmcs = HttpResponse(200, {"Content-Type": "text/html"}, b'<a href="/18508/pdf">PDF</a>',
                        "https://lmcs.episciences.org/18508")

    assert corpus._pdf_link(kr) == "https://proceedings.kr.org/2026/19/kr2026-0019-bogaerts-et-al.pdf"
    assert corpus._pdf_link(lmcs) == "https://lmcs.episciences.org/18508/pdf"


@pytest.mark.parametrize("year,number,filename", (
    ("2023", "18", "kr2023-0018-david-et-al.pdf"),
    ("2024", "50", "kr2024-0050-lutz-et-al.pdf"),
    ("2025", "33", "kr2025-0033-funk-et-al.pdf"),
    ("2026", "19", "kr2026-0019-bogaerts-et-al.pdf"),
))
def test_kr_route_allowlist_accepts_only_declared_2023_to_2026_proceedings_paths(
        year: str, number: str, filename: str) -> None:
    landing = HttpResponse(
        200, {"Content-Type": "text/html"},
        f'<a href="/{year}/{number}/{filename}">PDF</a>'.encode(),
        f"https://proceedings.kr.org/{year}/{number}/",
    )

    assert corpus._pdf_link(landing) == f"https://proceedings.kr.org/{year}/{number}/{filename}"


@pytest.mark.parametrize("href", (
    "/2022/18/kr2022-0018-david-et-al.pdf",
    "/2027/18/kr2027-0018-david-et-al.pdf",
    "/2025/33/kr2024-0033-funk-et-al.pdf",
    "/2025/33/kr2025-033-funk-et-al.pdf",
    "/2025/33/not-a-kr-paper.pdf",
    "https://example.org/2025/33/kr2025-0033-funk-et-al.pdf",
))
def test_kr_route_allowlist_rejects_out_of_range_malformed_and_external_paths(href: str) -> None:
    landing = HttpResponse(200, {"Content-Type": "text/html"}, f'<a href="{href}">PDF</a>'.encode(),
                           "https://proceedings.kr.org/2025/33/")

    assert corpus._pdf_link(landing) is None


def test_oa_only_live_selection_excludes_publisher_only_candidates_without_losing_oa_diversity() -> None:
    lipics = _candidate("paper:a", score=10)
    kr = _candidate("paper:b", score=9)
    kr["official_url"] = "https://doi.org/10.24963/kr.2026/19"
    acm = _candidate("paper:c", score=20)
    acm["official_url"] = "https://doi.org/10.1145/3801904"

    selected = corpus.select_live_candidates((acm, kr, lipics), (), limit=3, oa_only=True)

    assert [item["paper_id"] for item in selected] == ["paper:a", "paper:b"]


def test_validation_policy_recovery_selects_only_exact_identity_mismatches_after_transport_retry() -> None:
    identity_mismatch = replace(
        _transport_failure("paper:a", retry_policy="RETRY_ONCE:TRANSPORT_FAILURE"),
        status=AcquisitionStatus.INVALID_PDF,
        failure_reason="expected title or DOI is not present in extractable identity data",
    )
    other_invalid = replace(identity_mismatch, paper_id="paper:b", version_id="version:b",
                            failure_reason="PDF parser rejected payload: PdfReadError")
    records = (_candidate("paper:a", score=10), _candidate("paper:b", score=11), _candidate("paper:c", score=9))

    selected = corpus.select_live_candidates(records, (identity_mismatch, other_invalid), limit=3,
                                              recover_identity_mismatch=True)

    assert [item["paper_id"] for item in selected] == ["paper:a", "paper:c"]


def test_validation_policy_recovery_has_a_distinct_one_time_action_and_policy() -> None:
    prior = replace(
        _transport_failure("paper:a", retry_policy="RETRY_ONCE:TRANSPORT_FAILURE"),
        status=AcquisitionStatus.INVALID_PDF,
        failure_reason="expected title or DOI is not present in extractable identity data",
    )

    assert corpus.planned_action(prior) == "VALIDATION_POLICY_RECOVERY"
    assert corpus.next_retry_policy(prior) == "VALIDATION_POLICY_RECOVERY:IDENTITY_MISMATCH"
    assert corpus.planned_action(None) == "NEW"


def test_kr_route_policy_recovery_selects_only_exact_2023_to_2026_kr_route_failures() -> None:
    route_failure = replace(
        _transport_failure("paper:a", retry_policy="RETRY_ONCE:TRANSPORT_FAILURE"),
        provider="KR_PROCEEDINGS", status=AcquisitionStatus.HTML_OR_CHALLENGE,
        source_url="https://proceedings.kr.org/2025/33/",
        failure_reason="official landing page did not declare a same-provider open PDF",
    )
    non_kr = replace(route_failure, paper_id="paper:b", version_id="version:b", provider="OFFICIAL_PUBLISHER")
    wrong_year = replace(route_failure, paper_id="paper:c", version_id="version:c",
                         source_url="https://proceedings.kr.org/2022/18/")
    other_html = replace(route_failure, paper_id="paper:d", version_id="version:d",
                         failure_reason="publisher returned a challenge")
    records = tuple(_candidate(f"paper:{letter}", score=10 - index)
                    for index, letter in enumerate(("a", "b", "c", "d", "e")))

    selected = corpus.select_live_candidates(records, (route_failure, non_kr, wrong_year, other_html), limit=5,
                                              recover_kr_route_policy=True)

    assert [item["paper_id"] for item in selected] == ["paper:a", "paper:e"]


def test_kr_route_policy_recovery_has_a_distinct_one_time_action_and_policy() -> None:
    route_failure = replace(
        _transport_failure("paper:a"), provider="KR_PROCEEDINGS", status=AcquisitionStatus.HTML_OR_CHALLENGE,
        source_url="https://proceedings.kr.org/2023/18/",
        failure_reason="official landing page did not declare a same-provider open PDF",
    )

    assert corpus.planned_action(route_failure) == "KR_ROUTE_POLICY_RECOVERY"
    assert corpus.next_retry_policy(route_failure) == "ROUTE_POLICY_RECOVERY:KR_PROCEEDINGS_2023_2026"


def test_report_has_no_stale_commit_or_test_placeholders() -> None:
    report = corpus.render_report(
        {"attempts": 120}, {"FULL_SCAN": 0, "DEEP_READ": 0}, {}, {}, {}, {}, {},
    )

    assert "Selected outcomes" in report
    assert "Immutable attempt history" in report
    assert "PENDING_FIRST_COMMIT" not in report
    assert "62 passed" not in report
