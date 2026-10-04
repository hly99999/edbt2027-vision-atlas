from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from db_theory_atlas.ingest import (
    HttpResponse,
    Provider,
    ProviderManifest,
    SearchHit,
    UrllibTransport,
    deduplicate_hits,
    ingest_hits,
    ingest_provider,
)


FIXTURES = Path(__file__).parent / "fixtures"


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        self.calls += 1
        return self.responses.pop(0)


@pytest.mark.parametrize(
    ("provider", "fixture"),
    [
        (Provider.CROSSREF, "crossref.json"),
        (Provider.OPENALEX, "openalex.json"),
        (Provider.ARXIV, "arxiv.xml"),
        (Provider.DBLP, "dblp.xml"),
    ],
)
def test_fixture_ingestion_normalizes_provider_fields_without_guessing(provider: Provider, fixture: str) -> None:
    hits = ingest_hits((FIXTURES / fixture).read_bytes(), provider, observed_at=datetime(2026, 8, 17, tzinfo=timezone.utc))

    assert len(hits) == 1
    hit = hits[0]
    assert hit.provider is provider
    assert hit.provider_id
    assert hit.title == "A Frontier for Query Containment"
    assert hit.authors == ("Ada Author", "Bert Author")
    assert hit.year == 2024
    assert hit.source_url.startswith("http")


def test_missing_provider_fields_remain_none_or_empty_instead_of_being_invented() -> None:
    raw = b'{"message":{"items":[{"title":["Untitled Metadata"],"URL":"https://example.test/item"}]}}'

    hit = ingest_hits(raw, Provider.CROSSREF)[0]

    assert hit.authors == ()
    assert hit.year is None
    assert hit.venue is None
    assert hit.doi is None
    assert hit.source_observation is None


@pytest.mark.parametrize(
    ("provider", "fixture"),
    [
        (Provider.CROSSREF, "crossref-malformed-optional.json"),
        (Provider.OPENALEX, "openalex-malformed-optional.json"),
        (Provider.ARXIV, "arxiv-malformed-optional.xml"),
        (Provider.DBLP, "dblp-malformed-optional.xml"),
    ],
)
def test_provider_parsers_preserve_unknown_malformed_optional_fields(provider: Provider, fixture: str) -> None:
    hits = ingest_hits((FIXTURES / fixture).read_bytes(), provider)

    assert len(hits) == 1
    assert hits[0].authors == ()
    assert hits[0].year is None
    assert hits[0].venue is None
    assert hits[0].doi is None
    assert hits[0].source_observation is None


def test_rate_limit_retries_once_then_returns_success_manifest() -> None:
    raw = (FIXTURES / "crossref.json").read_bytes()
    transport = FakeTransport(
        [
            HttpResponse(429, {"content-type": "application/json"}, b"too many", "https://api.test/works"),
            HttpResponse(200, {"content-type": "application/json"}, raw, "https://api.test/works"),
        ]
    )
    delays: list[float] = []

    hits, manifest = ingest_provider("query", Provider.CROSSREF, transport, retries=1, sleep=delays.append)

    assert len(hits) == 1
    assert manifest.status == "SUCCESS"
    assert manifest.retry_count == 1
    assert transport.calls == 2
    assert delays == [1.0]


def test_permanent_provider_failure_is_manifested_without_silent_fallback() -> None:
    transport = FakeTransport([HttpResponse(503, {}, b"down", "https://api.test/works")])

    hits, manifest = ingest_provider("query", Provider.CROSSREF, transport, retries=2, sleep=lambda _: None)

    assert hits == ()
    assert manifest.status == "UNAVAILABLE"
    assert manifest.error == "HTTP 503"
    assert manifest.retry_count == 0


def test_oversize_ingestion_does_not_hash_the_truncated_prefix_as_full_payload() -> None:
    transport = FakeTransport([HttpResponse(200, {"content-type": "application/json"}, b"12345", "https://api.test/works")])

    hits, manifest = ingest_provider("query", Provider.CROSSREF, transport, max_bytes=4)

    assert hits == ()
    assert manifest.status == "UNAVAILABLE"
    assert manifest.error_code == "OVERSIZE"
    assert manifest.payload_hash is None
    assert manifest.payload_hash_status == "NOT_COMPUTED_OVERSIZE"


def test_provider_scientific_hash_excludes_operational_timestamps_and_retries() -> None:
    first = ProviderManifest(Provider.DBLP, "q", 10, 1, None, None, "a" * 64, "SUCCESS", None, 0, "2026-08-17T00:00:00Z")
    second = ProviderManifest(Provider.DBLP, "q", 10, 1, None, None, "a" * 64, "SUCCESS", None, 9, "2026-08-18T00:00:00Z")

    assert first.scientific_hash == second.scientific_hash


def test_provider_scientific_hash_excludes_raw_transport_error_detail() -> None:
    first = ProviderManifest(Provider.DBLP, "q", 10, 0, None, None, None, "UNAVAILABLE", "TRANSPORT_ERROR", 0,
                             "2026-08-17T00:00:00Z", "connection reset by peer")
    second = ProviderManifest(Provider.DBLP, "q", 10, 0, None, None, None, "UNAVAILABLE", "TRANSPORT_ERROR", 0,
                              "2026-08-18T00:00:00Z", "DNS lookup failed")

    assert first.error_code == second.error_code == "TRANSPORT_ERROR"
    assert first.scientific_hash == second.scientific_hash


def test_urllib_transport_converts_http_error_to_a_bounded_response() -> None:
    body = b"rate limited response"

    def opener(request: object, *, timeout: float) -> object:
        raise HTTPError("https://api.test/works", 429, "Too Many Requests", {"Retry-After": "1"}, io.BytesIO(body))

    response = UrllibTransport(opener=opener).get("https://api.test/works", timeout=1.0, max_bytes=8)

    assert response.status == 429
    assert response.headers["Retry-After"] == "1"
    assert response.body == body[:9]
    assert response.url == "https://api.test/works"


def test_urllib_http_error_participates_in_429_retry_policy() -> None:
    raw = (FIXTURES / "crossref.json").read_bytes()
    calls = 0

    class SuccessResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self, size: int) -> bytes:
            return raw[:size]

        def geturl(self) -> str:
            return "https://api.test/works"

        def __enter__(self) -> "SuccessResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def opener(request: object, *, timeout: float) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError("https://api.test/works", 429, "Too Many Requests", {}, io.BytesIO(b"retry"))
        return SuccessResponse()

    hits, manifest = ingest_provider("query", Provider.CROSSREF, UrllibTransport(opener=opener), retries=1, sleep=lambda _: None)

    assert len(hits) == 1
    assert manifest.status == "SUCCESS"
    assert manifest.retry_count == 1


def test_urllib_transport_reads_at_most_requested_limit_plus_one() -> None:
    class Stream:
        status = 200
        headers = {"Content-Type": "application/pdf"}

        def __init__(self) -> None:
            self.read_sizes: list[int] = []

        def read(self, size: int) -> bytes:
            self.read_sizes.append(size)
            return b"x" * size

        def geturl(self) -> str:
            return "https://api.test/works"

        def __enter__(self) -> "Stream":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    stream = Stream()
    response = UrllibTransport(opener=lambda request, timeout: stream).get("https://api.test/works", timeout=1.0, max_bytes=8)

    assert stream.read_sizes == [9]
    assert response.body == b"x" * 9


def test_arxiv_dedup_removes_only_terminal_version_suffix_and_preserves_old_style_category() -> None:
    raw = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/solv-int/9702001</id><title>Old Result</title><published>1997-02-01T00:00:00Z</published><author><name>Ada</name></author></entry><entry><id>https://arxiv.org/abs/2401.00001v12</id><title>New Result</title><published>2024-01-01T00:00:00Z</published><author><name>Bert</name></author></entry></feed>'''
    old, new = ingest_hits(raw, Provider.ARXIV)

    assert old.provider_id == "solv-int/9702001"
    assert old.dedup_key == "arxiv:solv-int/9702001"
    assert new.provider_id == "2401.00001v12"
    assert new.dedup_key == "arxiv:2401.00001"


def test_dedup_keys_prioritize_doi_then_provider_identity_then_metadata_fallback() -> None:
    doi_hit = SearchHit(Provider.CROSSREF, "first", "Title", ("Ada",), 2024, None, "10.1000/x", "https://a.test")
    same_doi = SearchHit(Provider.OPENALEX, "second", "Other", ("Bert",), 2025, None, "10.1000/x", "https://b.test")
    provider_hit = SearchHit(Provider.DBLP, "rec/1", "Title", ("Ada",), 2024, None, None, "https://c.test")
    fallback = SearchHit(Provider.MANUAL, None, "  Title ", ("Ada",), 2024, None, None, None)

    assert tuple(hit.dedup_key for hit in deduplicate_hits((same_doi, doi_hit, provider_hit, fallback))) == (
        "doi:10.1000/x", "fallback:title:ada:2024", "provider:dblp:rec/1",
    )


def test_public_package_exports_ingestion_records() -> None:
    from db_theory_atlas import Provider as PublicProvider, SearchHit

    assert PublicProvider is Provider
    assert SearchHit.__name__ == "SearchHit"


def test_offline_fixture_cli_writes_normalized_hits_and_manifest(tmp_path: Path) -> None:
    from scripts.ingest_sources import main

    output = tmp_path / "ingested.json"

    assert main([
        "--provider", "CROSSREF", "--query", "containment",
        "--fixture", str(FIXTURES / "crossref.json"), "--output", str(output),
    ]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manifest"] == {
        "provider": "CROSSREF", "query": "containment", "requested": 1, "received": 1,
        "cursor": None, "page": None, "payload_hash": hashlib.sha256((FIXTURES / "crossref.json").read_bytes()).hexdigest(),
        "status": "SUCCESS", "error_code": None, "retry_count": 0,
        "fetched_at": payload["manifest"]["fetched_at"], "error_detail": None, "payload_hash_status": "COMPUTED",
    }
    assert payload["hits"][0]["title"] == "A Frontier for Query Containment"
