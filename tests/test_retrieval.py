from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from db_theory_atlas.retrieval import RetrievalRequest, retrieve_fulltext
from db_theory_atlas.ingest import HttpResponse


FIXTURES = Path(__file__).parent / "fixtures"


class FakeTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        return self.response


def cache_root() -> Path:
    return Path.cwd() / "literature" / "fulltext_cache"


def request(pdf: bytes, *, key: str = "test-atlas") -> RetrievalRequest:
    return RetrievalRequest("https://papers.example/atlas.pdf", key, hashlib.sha256(pdf).hexdigest())


def test_retrieval_writes_valid_pdf_atomically_under_the_approved_cache() -> None:
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    target = cache_root() / "test-atlas.pdf"
    target.unlink(missing_ok=True)
    manifest = retrieve_fulltext(
        request(pdf),
        FakeTransport(HttpResponse(200, {"Content-Type": "application/pdf", "Content-Length": str(len(pdf))}, pdf, "https://papers.example/atlas.pdf")),
        cache_root(),
    )

    assert manifest.status == "AVAILABLE"
    assert manifest.content_sha256 == hashlib.sha256(pdf).hexdigest()
    assert target.read_bytes() == pdf
    assert not list(cache_root().glob(".test-atlas.*.tmp"))
    target.unlink()


def test_retrieval_rejects_html_login_page_even_when_named_pdf() -> None:
    html = (FIXTURES / "login.html").read_bytes()
    manifest = retrieve_fulltext(
        request(b"%PDF-1.4", key="login-page"),
        FakeTransport(HttpResponse(200, {"Content-Type": "text/html"}, html, "https://papers.example/atlas.pdf")),
        cache_root(),
    )

    assert manifest.status == "METADATA_ONLY"
    assert "content type" in manifest.error.lower()
    assert not (cache_root() / "login-page.pdf").exists()


def test_retrieval_rejects_magic_header_mismatch_and_cleans_partial_file() -> None:
    body = b"not a pdf"
    manifest = retrieve_fulltext(
        request(b"%PDF-1.4", key="bad-magic"),
        FakeTransport(HttpResponse(200, {"Content-Type": "application/pdf", "Content-Length": str(len(body))}, body, "https://papers.example/atlas.pdf")),
        cache_root(),
    )

    assert manifest.status == "METADATA_ONLY"
    assert "magic" in manifest.error.lower()
    assert not (cache_root() / "bad-magic.pdf").exists()
    assert not list(cache_root().glob(".bad-magic.*.tmp"))


def test_retrieval_rejects_traversal_and_arbitrary_output_roots() -> None:
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    response = FakeTransport(HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf"))

    with pytest.raises(ValueError, match="cache key"):
        retrieve_fulltext(request(pdf, key="../escape"), response, cache_root())
    with pytest.raises(ValueError, match="cache_root"):
        retrieve_fulltext(request(pdf), response, Path.cwd())


def test_retrieval_scientific_hash_ignores_operational_time_and_local_paths() -> None:
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    response = HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf")
    first = retrieve_fulltext(request(pdf, key="hash-one"), FakeTransport(response), cache_root())
    second = retrieve_fulltext(request(pdf, key="hash-two"), FakeTransport(response), cache_root())

    assert first.scientific_hash == second.scientific_hash
    (cache_root() / "hash-one.pdf").unlink(missing_ok=True)
    (cache_root() / "hash-two.pdf").unlink(missing_ok=True)


def test_retrieval_rejects_non_http_redirect_and_expected_hash_mismatch() -> None:
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    redirect = retrieve_fulltext(request(pdf, key="bad-redirect"), FakeTransport(
        HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "file:///outside.pdf"),
    ), cache_root())
    mismatch = retrieve_fulltext(RetrievalRequest("https://papers.example/atlas.pdf", "wrong-hash", "0" * 64), FakeTransport(
        HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf"),
    ), cache_root())

    assert redirect.status == "METADATA_ONLY"
    assert redirect.error_code == "REDIRECT_SCHEME"
    assert mismatch.status == "METADATA_ONLY"
    assert mismatch.error_code == "HASH_MISMATCH"


def test_rejected_local_redirects_keep_raw_urls_operational_and_hash_to_the_same_scientific_failure() -> None:
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    first = retrieve_fulltext(request(pdf, key="local-redirect-one"), FakeTransport(
        HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "file:///C:/private/one.pdf"),
    ), cache_root())
    second = retrieve_fulltext(request(pdf, key="local-redirect-two"), FakeTransport(
        HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "file:///D:/different/two.pdf"),
    ), cache_root())

    assert first.resolved_url == "file:///C:/private/one.pdf"
    assert second.resolved_url == "file:///D:/different/two.pdf"
    assert first.scientific_hash == second.scientific_hash


def test_retrieval_passes_explicit_limit_and_rejects_streamed_oversize_body() -> None:
    class LimitCheckingTransport:
        received_limit: int | None = None

        def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
            self.received_limit = max_bytes
            return HttpResponse(200, {"Content-Type": "application/pdf"}, b"%PDF-1.4\n%%EOF" + b"x" * 4, url)

    transport = LimitCheckingTransport()
    manifest = retrieve_fulltext(RetrievalRequest("https://papers.example/atlas.pdf", "oversize", max_bytes=12), transport, cache_root())

    assert transport.received_limit == 12
    assert manifest.status == "METADATA_ONLY"
    assert manifest.error_code == "OVERSIZE"


def test_retrieval_uses_stable_error_code_for_distinct_transport_messages() -> None:
    class FailingTransport:
        def __init__(self, message: str) -> None:
            self.message = message

        def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
            raise OSError(self.message)

    pdf = (FIXTURES / "sample.pdf").read_bytes()
    first = retrieve_fulltext(request(pdf, key="failure-one"), FailingTransport("connection refused"), cache_root())
    second = retrieve_fulltext(request(pdf, key="failure-two"), FailingTransport("host unreachable"), cache_root())

    assert first.error_code == second.error_code == "TRANSPORT_ERROR"
    assert first.scientific_hash == second.scientific_hash


def test_retrieval_rejects_symlinked_cache_route_and_returns_unavailable_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from db_theory_atlas import retrieval

    repository = tmp_path / "repository"
    cache = repository / "literature" / "fulltext_cache"
    cache.mkdir(parents=True)
    monkeypatch.setattr(retrieval, "_repository_root", lambda: repository)
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    monkeypatch.setattr(retrieval, "_is_symlink", lambda path: path == cache)

    with pytest.raises(ValueError, match="symlink"):
        retrieve_fulltext(request(pdf, key="symlink"), FakeTransport(HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf")), cache)

    monkeypatch.setattr(retrieval, "_is_symlink", lambda path: False)
    monkeypatch.setattr(retrieval.os, "replace", lambda source, destination: (_ for _ in ()).throw(OSError("disk full")))
    manifest = retrieve_fulltext(request(pdf, key="replace-failure"), FakeTransport(HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf")), cache)

    assert manifest.status == "UNAVAILABLE"
    assert manifest.error_code == "CACHE_IO"
    assert not list(cache.glob(".replace-failure.*.tmp"))


@pytest.mark.parametrize("stage", ["mkdir", "temporary", "fsync"])
def test_retrieval_converts_cache_io_failures_to_unavailable_manifests(stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from db_theory_atlas import retrieval

    repository = tmp_path / "repository"
    cache = repository / "literature" / "fulltext_cache"
    monkeypatch.setattr(retrieval, "_repository_root", lambda: repository)
    pdf = (FIXTURES / "sample.pdf").read_bytes()
    if stage == "mkdir":
        original_mkdir = Path.mkdir

        def fail_cache_mkdir(path: Path, *args: object, **kwargs: object) -> None:
            if path == cache:
                raise OSError("permission denied")
            original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fail_cache_mkdir)
    else:
        cache.mkdir(parents=True)
        if stage == "temporary":
            monkeypatch.setattr(retrieval.tempfile, "mkstemp", lambda **kwargs: (_ for _ in ()).throw(OSError("no temp file")))
        else:
            monkeypatch.setattr(retrieval.os, "fsync", lambda descriptor: (_ for _ in ()).throw(OSError("sync failed")))

    manifest = retrieve_fulltext(request(pdf, key=f"io-{stage}"), FakeTransport(
        HttpResponse(200, {"Content-Type": "application/pdf"}, pdf, "https://papers.example/atlas.pdf"),
    ), cache)

    assert manifest.status == "UNAVAILABLE"
    assert manifest.error_code == "CACHE_IO"
