from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from db_theory_atlas.corpus_task3 import (
    AcquisitionManifest,
    AcquisitionStatus,
    PdfValidationStatus,
    build_offline_ledger,
    validate_pdf_payload,
)
import db_theory_atlas.fulltext_reading as reading_impl
from db_theory_atlas.fulltext_reading import _heading, build_reading_corpus
from db_theory_atlas.reading import ReadingState, parse_note_frontmatter
from scripts import build_fulltext_corpus as corpus


def _pdf(*pages: str, metadata_title: str | None = None, metadata_author: str | None = None) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        })
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands = ["BT /F1 10 Tf 55 740 Td"]
        for index, line in enumerate(escaped.splitlines()):
            if index:
                commands.append("0 -15 Td")
            commands.append(f"({line}) Tj")
        commands.append("ET")
        stream.set_data(" ".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    metadata: dict[str, str] = {}
    if metadata_title is not None:
        metadata["/Title"] = metadata_title
    if metadata_author is not None:
        metadata["/Author"] = metadata_author
    if metadata:
        writer.add_metadata(metadata)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _manifest(payload: bytes, *, paper_id: str = "paper:audited") -> AcquisitionManifest:
    import hashlib

    token = paper_id.split(":", 1)[1]
    validation = validate_pdf_payload(
        payload,
        expected_title="Audited Query Evaluation",
        expected_doi="10.4230/LIPIcs.ICDT.2026.99",
        expected_authors=("Ada Lovelace",),
        expected_venue="ICDT",
    )
    assert validation.status is PdfValidationStatus.VALID
    return AcquisitionManifest(
        paper_id=paper_id,
        version_id=f"version:{token}",
        source_url="https://drops.dagstuhl.de/storage/00lipics/test/Audited.pdf",
        provider="LIPICS",
        source_tier="T1",
        requested_at="2026-08-30T00:00:00Z",
        observed_at="2026-08-30T00:00:00Z",
        status=AcquisitionStatus.VALID_PDF,
        http_status=200,
        media_type="application/pdf",
        byte_count=len(payload),
        content_sha256=hashlib.sha256(payload).hexdigest(),
        license_status="OPEN_ACCESS_DECLARED",
        redistribution_status="CACHE_LOCAL_ONLY",
        cache_path=f"literature/fulltext_cache/{token}.pdf",
        failure_reason=None,
        retry_policy="NO_RETRY",
        selected_reading_version=f"version:{token}",
        alternatives=(),
        route_provenance="APPROVED_DIRECT:LIPICS_PDF",
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


def _record(paper_id: str = "paper:audited") -> dict[str, object]:
    token = paper_id.split(":", 1)[1]
    return {
        "paper_id": paper_id,
        "title": "Audited Query Evaluation",
        "authors": ["Ada Lovelace"],
        "year": 2026,
        "venue": "ICDT",
        "venue_family": "ICDT",
        "doi": "10.4230/LIPIcs.ICDT.2026.99",
        "screening": {
            "relevant": True,
            "primary_topic_id": "query_evaluation",
            "DEEP_READ_PRIORITY_SCORE": 20,
        },
        "versions": [{
            "version_id": f"version:{token}",
            "title": "Audited Query Evaluation",
            "authors": ["Ada Lovelace"],
            "venue": "ICDT",
            "doi": "10.4230/LIPIcs.ICDT.2026.99",
        }],
    }


def _deep_payload(
    conclusion_heading: str = "6 Conclusion",
    limitations_heading: str = "5 Limitations and Future Work",
) -> bytes:
    return _pdf(
        "Audited Query Evaluation\nAda Lovelace\nICDT 2026\n10.4230/LIPIcs.ICDT.2026.99\n"
        "Abstract\nWe study evaluation of bounded conjunctive queries over finite relational instances.\n"
        "1 Introduction\nThe paper asks how to enumerate every answer tuple under set semantics.",
        "2 Formal Setting\nThe input is a finite relational instance and a bounded conjunctive query. "
        "The output is its answer relation; arity and query size are parameters.",
        "3 Main Results\nThe paper gives a polynomial data-complexity upper bound for the bounded fragment "
        "and a conditional lower bound outside it.",
        "4 Proof Overview\nThe upper bound uses a homomorphism reduction and dynamic programming on a decomposition.",
        f"{limitations_heading}\nThe analysis assumes set semantics and bounded arity. "
        "Bag semantics and unions of conjunctive queries are left open.",
        f"{conclusion_heading}\nThe conclusion restates the bounded-fragment result and the two open extensions.",
        metadata_title="Audited Query Evaluation",
        metadata_author="Ada Lovelace",
    )


def _audit(manifest: AcquisitionManifest) -> dict[str, object]:
    loc = lambda page, heading: {"page": page, "heading": heading}
    return {
        "paper_id": manifest.paper_id,
        "version_id": manifest.version_id,
        "source_hash": manifest.content_sha256,
        "read_depth": "DEEP_READ",
        "reviewer_status": "SOURCE_VERIFIED",
        "validation_method": "FULL_PDF_SOURCE_AUDIT",
        "section_map": [
            {"page": 1, "heading": "1 Introduction", "summary": "Problem motivation and answer-enumeration task."},
            {"page": 2, "heading": "2 Formal Setting", "summary": "Finite-instance and bounded-query model."},
            {"page": 3, "heading": "3 Main Results", "summary": "Non-complete upper/lower-bound overview."},
            {"page": 5, "heading": "5 Limitations and Future Work", "summary": "Scope limits and open extensions."},
            {"page": 6, "heading": "6 Conclusion", "summary": "Result and future-work recap."},
        ],
        "full_scan": {
            "identity_version": {"value": "ICDT 2026 version by Ada Lovelace; DOI shown on page 1.", "locations": [loc(1, "1 Introduction")]},
            "abstract": {"value": "The paper studies bounded conjunctive-query evaluation on finite relational instances.", "locations": [loc(1, "Abstract")]},
            "problem": {"value": "Evaluate and enumerate all answer tuples of a bounded conjunctive query on a finite relational instance.", "locations": [loc(1, "1 Introduction")]},
            "formal_scope": {"value": "Finite relational instances, bounded conjunctive queries, set semantics, bounded arity, and query/data-size parameters.", "locations": [loc(2, "2 Formal Setting")]},
            "main_results_non_complete": {"value": "A polynomial data-complexity upper bound is paired with a conditional lower bound beyond the bounded fragment; theorem statements are intentionally not reproduced.", "locations": [loc(3, "3 Main Results")]},
            "limitations": {"value": "The analysis is restricted to set semantics and bounded arity.", "locations": [loc(5, "5 Limitations and Future Work")]},
            "future_open_work": {"value": "Bag semantics and unions of conjunctive queries are explicit open extensions.", "locations": [loc(5, "5 Limitations and Future Work"), loc(6, "6 Conclusion")]},
        },
        "deep_read": {
            "formal_problem": {"value": "Compute the answer relation of a bounded conjunctive query on a finite relational instance.", "locations": [loc(2, "2 Formal Setting")]},
            "input": {"value": "A finite relational instance and a bounded conjunctive query.", "locations": [loc(2, "2 Formal Setting")]},
            "output": {"value": "The complete answer relation (all satisfying tuples).", "locations": [loc(1, "1 Introduction"), loc(2, "2 Formal Setting")]},
            "semantics": {"value": "Set semantics.", "locations": [loc(1, "1 Introduction"), loc(5, "5 Limitations and Future Work")]},
            "query_languages": {"value": "Bounded conjunctive queries.", "locations": [loc(2, "2 Formal Setting")]},
            "constraint_languages": {"value": "NOT_EXPLICIT_IN_INSPECTED_SOURCE", "locations": [loc(2, "2 Formal Setting"), loc(6, "6 Conclusion")]},
            "parameters": {"value": "Query size, database size, and arity bound.", "locations": [loc(2, "2 Formal Setting")]},
            "theorem_result_inventory": {"value": "Non-complete inventory: one bounded-fragment upper-bound result and one conditional lower-bound result outside it.", "locations": [loc(3, "3 Main Results")]},
            "upper_bounds": {"value": "Polynomial data-complexity upper bound for the bounded fragment.", "locations": [loc(3, "3 Main Results")]},
            "lower_bounds": {"value": "Conditional lower bound outside the bounded fragment.", "locations": [loc(3, "3 Main Results")]},
            "structural_fragments": {"value": "The bounded-query/bounded-arity fragment.", "locations": [loc(2, "2 Formal Setting"), loc(3, "3 Main Results")]},
            "assumptions": {"value": "Finite instances, set semantics, and bounded arity.", "locations": [loc(2, "2 Formal Setting"), loc(5, "5 Limitations and Future Work")]},
            "limitations": {"value": "Bag semantics and unbounded arity are outside the established scope.", "locations": [loc(5, "5 Limitations and Future Work")]},
            "open_extensions": {"value": "Bag semantics and unions of conjunctive queries.", "locations": [loc(5, "5 Limitations and Future Work"), loc(6, "6 Conclusion")]},
            "proof_technique_signals": {"value": "Homomorphism reduction plus dynamic programming over a decomposition.", "locations": [loc(4, "4 Proof Overview")]},
        },
    }


def _install_cache(root: Path, manifest: AcquisitionManifest, payload: bytes) -> None:
    target = root / str(manifest.cache_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)


@pytest.mark.parametrize("closing_heading", ["6 Conclusions", "6 Discussions", "6 Future Directions"])
def test_source_audit_accepts_real_plural_or_directional_closing_headings(
    tmp_path: Path, closing_heading: str,
) -> None:
    limitations_heading = "5 Scope Limitations"
    payload = _deep_payload(closing_heading, limitations_heading)
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    audit = json.loads(
        json.dumps(_audit(manifest))
        .replace("6 Conclusion", closing_heading)
        .replace("5 Limitations and Future Work", limitations_heading)
    )

    result = build_reading_corpus(
        (manifest,), (_record(),), tmp_path,
        tmp_path / "notes", tmp_path / "ledger.json",
        audits=(audit,), deep_read_target=1,
    )

    assert result["counts"]["DEEP_READ"] == 1


def test_title_only_identity_is_limited_to_trusted_title_region_and_requires_corroboration() -> None:
    bibliography_only = _pdf(
        "Wrong Paper\nMallory\n1 Introduction\nThis is unrelated.",
        "References\nAda Lovelace. Audited Query Evaluation. ICDT 2026.",
        metadata_title="Wrong Paper",
        metadata_author="Mallory",
    )
    rejected = validate_pdf_payload(
        bibliography_only,
        expected_title="Audited Query Evaluation",
        expected_doi=None,
        expected_authors=("Ada Lovelace",),
        expected_venue="ICDT",
    )
    assert rejected.status is PdfValidationStatus.IDENTITY_MISMATCH
    assert rejected.title_match is False

    first_page = _pdf(
        "Audited Query Evaluation\nAda Lovelace\nICDT 2026\nAbstract\nA source-specific abstract.",
        metadata_title="Audited Query Evaluation",
        metadata_author="Ada Lovelace",
    )
    accepted = validate_pdf_payload(
        first_page,
        expected_title="Audited Query Evaluation",
        expected_doi=None,
        expected_authors=("Ada Lovelace",),
        expected_venue="ICDT",
    )
    assert accepted.status is PdfValidationStatus.VALID
    assert accepted.identity_basis in {
        "TITLE_METADATA+AUTHOR_CORROBORATION",
        "TITLE_FIRST_PAGE+AUTHOR_CORROBORATION",
    }


def test_valid_pdf_manifest_persists_both_extraction_hashes_and_normalization_provenance() -> None:
    manifest = _manifest(_deep_payload())

    assert manifest.page_count == 6
    assert manifest.extracted_characters and manifest.extracted_characters > 100
    assert manifest.validation_extraction_sha256
    assert manifest.reading_extraction_sha256
    assert manifest.validation_extraction_normalization == "PYPDF_PAGE_TEXT_JOIN_LF_V1"
    assert manifest.reading_extraction_normalization == "PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1"
    assert manifest.identity_basis == "DOI_MATCH"


def test_attempt_history_is_append_only_while_selected_outcomes_remain_unique(tmp_path: Path) -> None:
    payload = _deep_payload()
    success = _manifest(payload)
    failure = replace(
        success,
        status=AcquisitionStatus.TRANSPORT_FAILURE,
        source_url="https://doi.org/10.4230/LIPIcs.ICDT.2026.99",
        http_status=None,
        media_type=None,
        byte_count=None,
        content_sha256=None,
        cache_path=None,
        failure_reason="landing request failed: TimeoutError",
        route_provenance="APPROVED_DOI_ROUTE:LIPICS",
        page_count=None,
        extracted_characters=None,
        validation_extraction_sha256=None,
        validation_extraction_normalization=None,
        reading_extraction_sha256=None,
        reading_extraction_normalization=None,
        title_match=None,
        doi_match=None,
        identity_basis=None,
        attempt_id=None,
    )
    selected, attempts = corpus.conserve_attempt_history((failure,), (failure,), (success,))

    assert selected == (success,)
    assert attempts == (failure, success)
    counts = build_offline_ledger(selected, tmp_path / "ledger.json", attempt_history=attempts)
    assert counts["selected_outcomes"]["outcomes"] == 1
    assert counts["selected_outcomes"]["valid_pdf"] == 1
    assert counts["attempt_history"]["attempts"] == 2
    assert counts["attempt_history"]["transport_failure"] == 1
    assert counts["attempt_history"]["valid_pdf"] == 1


@pytest.mark.parametrize("url", (
    "https://untrusted.example/download.pdf?ref=10.4230/fake",
    "https://doi.org.evil.example/10.4230/LIPIcs.ICDT.2026.1",
    "https://drops.dagstuhl.de.evil.example/paper.pdf",
    "https://proceedings.kr.org/2026/19/kr2026-0019-paper.pdf?download=10.24963/kr.2026/19",
))
def test_oa_recognition_rejects_adversarial_host_and_query_substrings(url: str) -> None:
    assert corpus._recognized_oa_url(url) is False
    assert corpus._provider_and_license(url) == ("OFFICIAL_PUBLISHER", "LICENSE_UNCONFIRMED")


def test_direct_pdf_requires_an_approved_route_or_verified_doi_resolution(tmp_path: Path) -> None:
    record = _record()
    record["official_url"] = "https://untrusted.example/paper.pdf?ref=10.4230/LIPIcs.ICDT.2026.99"
    response = corpus.HttpResponse(200, {"Content-Type": "application/pdf"}, _deep_payload(), str(record["official_url"]))

    class Transport:
        def get(self, *_args: object, **_kwargs: object) -> object:
            return response

    outcome = corpus.acquire_candidate(record, Transport(), cache_root=tmp_path)

    assert outcome.status is AcquisitionStatus.HTTP_FAILURE
    assert "approved host/route" in str(outcome.failure_reason)


@pytest.mark.parametrize("false_heading", (
    "16 Andrei Bulatov and Víctor Dalmau. A simple algorithm for mal’tsev constraints.SIAM",
    "12 Paraschos Koutris, Paul Beame, and Dan Suciu. Worst-case optimal algorithms for parallel",
    "43 Todd L. Veldhuizen. Leapfrog triejoin: a worst-case optimal join algorithm. CoRR,",
    "47 Alan L. Selman. Promise problems for complexity classes.Information and Computation,",
    "6 Leopoldo E. Bertossi, Loreto Bravo, Enrico Franconi, and Andrei Lopatenko. The complexity",
    "11 if ∃i′ < i.∀q′ ∈ Q.l[q′, i] = l[q′, i′] return confs",
    "2 and therefore calling the algorithm forQhb on this instance does not necessarily",
    "3. for every ℓ∈{1, . . . , n}, xℓ̸∈F +,q.",
    "4 suggests currently",
    "1. If v is a leaf, then w(δ)≤1.",
    "4. the set N[X] is represented by the following list",
    "9 return EOF",
))
def test_heading_detector_rejects_production_reference_algorithm_formula_list_and_prose_classes(false_heading: str) -> None:
    assert _heading(false_heading) is None


def test_only_source_audits_can_promote_and_note_contains_substantive_paper_specific_fields(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)

    result = build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "notes", tmp_path / "ledger.json",
        audits=(_audit(manifest),), deep_read_target=80,
    )

    assert result["counts"] == {"FULL_SCAN": 1, "FULL_SCAN_ONLY": 0, "DEEP_READ": 1, "SHORTFALL": 0}
    note = parse_note_frontmatter((tmp_path / "notes" / "audited.md").read_text(encoding="utf-8"))
    assert note.read_depth is ReadingState.DEEP_READ
    inventories = [pointer.claim for pointer in note.evidence if pointer.claim]
    assert inventories
    inventory = next(item for item in inventories if item.get("claim_type") == "TASK3_NON_COMPLETE_READING_INVENTORY")
    deep = inventory["deep_read"]
    assert deep["input"]["value"].startswith("A finite relational instance")
    assert deep["output"]["value"].startswith("The complete answer relation")
    assert deep["semantics"]["value"] == "Set semantics."
    assert deep["constraint_languages"]["value"] == "NOT_EXPLICIT_IN_INSPECTED_SOURCE"
    assert "homomorphism reduction" in deep["proof_technique_signals"]["value"].casefold()
    assert "'signals'" not in str(inventory)

    without_audit = build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "other-notes", tmp_path / "other-ledger.json",
        audits=(), deep_read_target=80,
    )
    assert without_audit["counts"]["FULL_SCAN"] == 0
    assert without_audit["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"


def test_source_audit_accepts_a_real_outlook_closing_section(tmp_path: Path) -> None:
    payload = _pdf(
        "Audited Query Evaluation\nAda Lovelace\nICDT 2026\n10.4230/LIPIcs.ICDT.2026.99\n"
        "Abstract\nWe study bounded conjunctive-query evaluation.\n1 Introduction\nThe paper states the task.",
        "2 Formal Setting\nThe input is a finite instance and a bounded conjunctive query.",
        "3 Main Results\nThe paper gives a polynomial upper bound for the bounded fragment.",
        "4 Proof Overview\nThe proof uses a homomorphism reduction.",
        "5 Limitations and Future Work\nBag semantics is outside the established scope.",
        "6 Outlook\nThe paper closes by identifying bag semantics as an open extension.",
        metadata_title="Audited Query Evaluation",
        metadata_author="Ada Lovelace",
    )
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    audit = _audit(manifest)
    audit["read_depth"] = "FULL_SCAN"
    audit["deep_read"] = None
    audit["section_map"] = audit["section_map"][:3] + audit["section_map"][-1:]
    audit["section_map"][-1]["heading"] = "6 Outlook"
    audit["full_scan"]["future_open_work"]["locations"][-1]["heading"] = "6 Outlook"

    result = build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "notes", tmp_path / "ledger.json",
        audits=(audit,),
    )

    assert result["counts"]["FULL_SCAN"] == 1


def test_source_audit_binds_an_inline_abstract_label(tmp_path: Path) -> None:
    payload = _pdf(
        "Audited Query Evaluation\nAda Lovelace\nICDT 2026\n10.4230/LIPIcs.ICDT.2026.99\n"
        "Abstract. We study bounded conjunctive-query evaluation.\n1 Introduction\nThe paper states the task.",
        "2 Formal Setting\nThe input is a finite instance and a bounded conjunctive query.",
        "3 Main Results\nThe paper gives a polynomial upper bound for the bounded fragment.",
        "4 Proof Overview\nThe proof uses a homomorphism reduction.",
        "5 Limitations and Future Work\nBag semantics is outside the established scope.",
        "6 Conclusion\nThe paper closes by identifying bag semantics as an open extension.",
        metadata_title="Audited Query Evaluation",
        metadata_author="Ada Lovelace",
    )
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)

    result = build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "notes", tmp_path / "ledger.json",
        audits=(_audit(manifest),),
    )

    assert result["counts"]["DEEP_READ"] == 1


def test_staged_rebuild_rejects_unowned_contamination_without_overwriting_it(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    notes = tmp_path / "notes"
    notes.mkdir()
    manual = notes / "manual.md"
    manual.write_text("manual scholarship\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected or unowned"):
        build_reading_corpus(
            (manifest,), (_record(),), tmp_path, notes, tmp_path / "ledger.json",
            audits=(_audit(manifest),),
        )

    assert manual.read_text(encoding="utf-8") == "manual scholarship\n"
    assert not (tmp_path / "ledger.json").exists()


def test_cache_hash_failure_invalidates_prior_owned_notes_instead_of_leaving_stale_promotions(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    notes = tmp_path / "notes"
    ledger = tmp_path / "ledger.json"
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(_audit(manifest),))
    assert (notes / "audited.md").is_file()

    (tmp_path / str(manifest.cache_path)).write_bytes(payload + b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(_audit(manifest),))

    assert not (notes / "audited.md").exists()
    assert not ledger.exists()


def test_clean_isolated_rebuilds_are_byte_identical(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    bundles: list[tuple[bytes, bytes, bytes]] = []
    for label in ("one", "two"):
        root = tmp_path / label
        _install_cache(root, manifest, payload)
        notes = root / "notes"
        ledger = root / "ledger.json"
        build_reading_corpus((manifest,), (_record(),), root, notes, ledger, audits=(_audit(manifest),))
        bundles.append(((notes / "audited.md").read_bytes(), (notes / ".generated-index.json").read_bytes(), ledger.read_bytes()))

    assert bundles[0] == bundles[1]


def test_frozen_text_hash_is_stable_across_checkout_line_endings(tmp_path: Path) -> None:
    lf = tmp_path / "lf.jsonl"
    crlf = tmp_path / "crlf.jsonl"
    lf.write_bytes(b'{"paper_id":"paper:one"}\n{"paper_id":"paper:two"}\n')
    crlf.write_bytes(b'{"paper_id":"paper:one"}\r\n{"paper_id":"paper:two"}\r\n')

    assert corpus._file_sha256(lf) == corpus._file_sha256(crlf)


def test_failed_ledger_commit_rolls_back_notes_and_ledger_together(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    notes = tmp_path / "notes"
    ledger = tmp_path / "ledger.json"
    audit = _audit(manifest)
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(audit,))
    before_note = (notes / "audited.md").read_bytes()
    before_ledger = ledger.read_bytes()
    changed = json.loads(json.dumps(audit))
    changed["full_scan"]["abstract"]["value"] += " The inspected source uses a bounded-query setting."

    real_replace = reading_impl.os.replace
    injected = False

    def fail_ledger_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal injected
        if not injected and Path(destination) == ledger and Path(source).name.startswith(f".{ledger.name}-"):
            injected = True
            raise OSError("injected ledger commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(reading_impl.os, "replace", fail_ledger_replace)
    with pytest.raises(OSError, match="injected ledger"):
        build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(changed,))

    assert (notes / "audited.md").read_bytes() == before_note
    assert ledger.read_bytes() == before_ledger


def test_backup_cleanup_failure_keeps_new_notes_and_ledger_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    notes = tmp_path / "notes"
    ledger = tmp_path / "ledger.json"
    audit = _audit(manifest)
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(audit,))
    before_note = (notes / "audited.md").read_bytes()
    changed = json.loads(json.dumps(audit))
    changed["full_scan"]["abstract"]["value"] += " The inspected source uses a bounded-query setting."

    real_unlink = reading_impl.Path.unlink
    injected = False

    def fail_ledger_backup_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected and path.name.startswith(f".{ledger.name}-backup-"):
            injected = True
            raise OSError("injected ledger backup cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(reading_impl.Path, "unlink", fail_ledger_backup_cleanup)
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(changed,))

    note = parse_note_frontmatter((notes / "audited.md").read_text(encoding="utf-8"))
    ledger_content = json.loads(ledger.read_text(encoding="utf-8"))
    assert injected
    assert (notes / "audited.md").read_bytes() != before_note
    assert ledger_content["records"][0]["note_hash"] == note.scientific_hash


def test_validation_failure_preserves_unowned_external_ledger(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload + b"tampered")
    ledger = tmp_path / "external-ledger.json"
    ledger.write_text("manual external ledger\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected or unowned"):
        build_reading_corpus(
            (manifest,), (_record(),), tmp_path, tmp_path / "notes", ledger,
            audits=(_audit(manifest),),
        )

    assert ledger.read_text(encoding="utf-8") == "manual external ledger\n"


def test_render_failure_invalidates_prior_owned_notes_and_ledger(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    notes = tmp_path / "notes"
    ledger = tmp_path / "ledger.json"
    audit = _audit(manifest)
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(audit,))
    invalid = json.loads(json.dumps(audit))
    invalid["full_scan"]["problem"]["value"] = "The procedure always returns the required answers."

    with pytest.raises(ValueError, match="placeholder or unsupported certainty"):
        build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, audits=(invalid,))

    assert not notes.exists()
    assert not ledger.exists()


def test_unrepresented_section_map_entry_is_not_mislabeled_as_problem_evidence(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    audit = _audit(manifest)
    audit["read_depth"] = "FULL_SCAN"
    audit["deep_read"] = None
    audit["section_map"].insert(3, {
        "page": 4,
        "heading": "4 Proof Overview",
        "summary": "Explains the proof architecture and reduction sequence.",
    })

    build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "notes", tmp_path / "ledger.json",
        audits=(audit,),
    )
    note = parse_note_frontmatter((tmp_path / "notes" / "audited.md").read_text(encoding="utf-8"))

    assert not any(pointer.page == 4 and pointer.heading == "4 Proof Overview" for pointer in note.evidence)


def test_render_uses_a_represented_closing_section_when_later_conclusion_is_map_only(tmp_path: Path) -> None:
    payload = _deep_payload()
    manifest = _manifest(payload)
    _install_cache(tmp_path, manifest, payload)
    audit = _audit(manifest)
    audit["read_depth"] = "FULL_SCAN"
    audit["deep_read"] = None
    audit["full_scan"]["future_open_work"]["locations"] = [
        {"page": 5, "heading": "5 Limitations and Future Work"},
    ]

    result = build_reading_corpus(
        (manifest,), (_record(),), tmp_path, tmp_path / "notes", tmp_path / "ledger.json",
        audits=(audit,),
    )

    assert result["counts"]["FULL_SCAN"] == 1


def test_report_uses_frozen_provenance_and_separates_selected_outcomes_from_attempt_history() -> None:
    rendered = corpus.render_report(
        {"outcomes": 153, "valid_pdf": 121, "html_or_challenge": 1, "transport_failure": 31,
         "http_failure": 0, "invalid_pdf": 0, "not_attempted": 0},
        {"attempts": 242, "valid_pdf": 121, "html_or_challenge": 1, "transport_failure": 120,
         "http_failure": 0, "invalid_pdf": 0, "not_attempted": 0},
        {"FULL_SCAN": 1, "FULL_SCAN_ONLY": 0, "DEEP_READ": 1, "SHORTFALL": 120},
        {}, {}, {}, {}, {},
        provenance={
            "implementation_commits": ["abcdef1"],
            "commands": ["python -m pytest tests/test_corpus_task3_integrity.py"],
            "test_results": [{"command": "python -m pytest tests/test_corpus_task3_integrity.py", "passed": 20, "failed": 0}],
            "runtime": {"python": "3.12.13", "pypdf": "6.10.0"},
            "limitations": ["Only source-audited records are promoted."],
        },
        validation_summary={
            "complete_records": 121,
            "identity_basis": {"DOI_MATCH": 86, "TITLE_FIRST_PAGE+AUTHOR_CORROBORATION": 35},
            "validation_normalization": {"PYPDF_PAGE_TEXT_JOIN_LF_V1": 121},
            "reading_normalization": {"PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1": 121},
        },
        bundle_hashes={"attempts": "a" * 64, "selected": "b" * 64, "reading": "c" * 64},
    )

    assert "Selected outcomes: 153" in rendered
    assert "Total immutable attempts: 242" in rendered
    assert "Transport failures in attempt history: 120" in rendered
    assert "abcdef1" in rendered
    assert "20 passed; 0 failed" in rendered
    assert "PENDING_FIRST_COMMIT" not in rendered
    assert "62 passed" not in rendered
