from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from db_theory_atlas.corpus_task3 import AcquisitionManifest, AcquisitionStatus
from db_theory_atlas.fulltext_reading import (
    ReadingAnalysis,
    _heading,
    build_reading_corpus,
    extract_valid_pdf,
    select_deep_read_ids,
)
from db_theory_atlas.reading import CoverageKind, ReadingState, parse_note_frontmatter
from scripts import build_fulltext_corpus as corpus


def _pdf(*pages: str) -> bytes:
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
        lines = escaped.splitlines()
        commands = ["BT /F1 10 Tf 55 740 Td"]
        for index, line in enumerate(lines):
            if index:
                commands.append("0 -15 Td")
            commands.append(f"({line}) Tj")
        commands.append("ET")
        stream.set_data(" ".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _manifest(payload: bytes, *, paper_id: str = "paper:reading-a") -> AcquisitionManifest:
    import hashlib

    token = paper_id.rsplit(":", 1)[1]
    return AcquisitionManifest(
        paper_id=paper_id,
        version_id=f"version:{token}",
        source_url="https://drops.example/paper.pdf",
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
    )


def _record(paper_id: str = "paper:reading-a", *, topic: str = "cq", venue: str = "ICDT", score: int = 12) -> dict[str, object]:
    token = paper_id.rsplit(":", 1)[1]
    return {
        "paper_id": paper_id,
        "title": "Scoped Query Evaluation",
        "year": 2026,
        "venue_family": venue,
        "screening": {
            "relevant": True,
            "primary_topic_id": topic,
            "DEEP_READ_PRIORITY_SCORE": score,
        },
        "versions": [{"version_id": f"version:{token}", "title": "Scoped Query Evaluation"}],
    }


def _deep_pdf() -> bytes:
    return _pdf(
        "Scoped Query Evaluation\nAbstract\nWe study query evaluation for finite relational structures and bounded conjunctive queries.\n1 Introduction\nGiven a finite database and a query, the task is to return all satisfying tuples under set semantics.",
        "2 Formal Setting\nLet the input be a finite relational instance and a conjunctive query. The output is the answer relation. We assume bounded arity and use set semantics, with query size and database size as parameters.",
        "3 Main Results\nWe prove a polynomial data-complexity upper bound for the bounded fragment and a matching hardness bound outside that fragment. The proof combines a homomorphism reduction with dynamic programming.",
        "4 Limitations and Future Work\nThe result is restricted to bounded arity and does not cover bag semantics. Extending the method to unions of conjunctive queries remains future work.",
        "5 Conclusion\nFor the stated finite and bounded setting, the paper summarizes the query-evaluation bounds and the remaining semantic extension.",
    )


def test_extract_valid_pdf_verifies_manifest_status_size_and_sha256(tmp_path: Path) -> None:
    payload = _deep_pdf()
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    document = extract_valid_pdf(manifest, tmp_path)

    assert document.source_hash == manifest.content_sha256
    assert document.page_count == 5
    assert "Formal Setting" in document.pages[1]

    target.write_bytes(payload + b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        extract_valid_pdf(manifest, tmp_path)
    with pytest.raises(ValueError, match="VALID_PDF"):
        extract_valid_pdf(replace(manifest, status=AcquisitionStatus.INVALID_PDF,
                                  content_sha256=None, byte_count=None, cache_path=None,
                                  failure_reason="invalid"), tmp_path)


def test_offline_build_does_not_promote_without_a_source_audit(tmp_path: Path) -> None:
    payload = _deep_pdf()
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    notes = tmp_path / "literature" / "fulltext_notes"
    ledger = tmp_path / "literature" / "fulltext_ledgers" / "read_depth_2026_08_30.json"

    result = build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, deep_read_target=1)

    assert result["counts"] == {"FULL_SCAN": 0, "FULL_SCAN_ONLY": 0, "DEEP_READ": 0, "SHORTFALL": 1}
    assert not (notes / "reading-a.md").exists()
    ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
    assert ledger_data["counts"]["DEEP_READ"] == 0
    assert ledger_data["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"
    assert ledger_data["records"][0]["page_count"] == 5


def test_missing_limitation_or_future_work_fails_closed_below_full_scan(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract\nWe study query evaluation for finite structures.\n1 Introduction\nGiven a database and query, return the answers.",
        "2 Formal Setting\nLet the input be a finite database and the output be its query answers.",
        "3 Results\nWe prove a polynomial-time algorithm by dynamic programming.",
        "4 Conclusion\nWe summarize the algorithm.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"] == {"FULL_SCAN": 0, "FULL_SCAN_ONLY": 0, "DEEP_READ": 0, "SHORTFALL": 1}
    assert result["records"][0]["read_depth"] == "ABSTRACT"
    assert result["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"


def _analysis(paper_id: str, topic: str, venue: str, score: int) -> ReadingAnalysis:
    return ReadingAnalysis.testing_deep(paper_id=paper_id, version_id=f"version:{paper_id[-1]}",
                                        source_hash=(paper_id[-1] * 64), topic=topic, venue=venue,
                                        year=2026, priority_score=score)


def test_deep_read_selection_is_deterministic_and_preserves_topic_and_venue_diversity() -> None:
    analyses = (
        _analysis("paper:a", "cq", "ICDT", 20),
        _analysis("paper:b", "cq", "ICDT", 19),
        _analysis("paper:c", "csp", "LICS", 18),
        _analysis("paper:d", "provenance", "PODS", 17),
    )

    selected = select_deep_read_ids(analyses, limit=3)
    reversed_selected = select_deep_read_ids(tuple(reversed(analyses)), limit=3)

    assert selected == reversed_selected == ("paper:a", "paper:c", "paper:d")


def test_offline_rebuild_is_byte_identical_for_notes_and_read_depth_ledger(tmp_path: Path) -> None:
    payload = _deep_pdf()
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    notes = tmp_path / "notes"
    ledger = tmp_path / "ledger.json"

    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, deep_read_target=1)
    first_readme = (notes / "README.md").read_bytes()
    first_index = (notes / ".generated-index.json").read_bytes()
    first_ledger = ledger.read_bytes()
    build_reading_corpus((manifest,), (_record(),), tmp_path, notes, ledger, deep_read_target=1)

    assert (notes / "README.md").read_bytes() == first_readme
    assert (notes / ".generated-index.json").read_bytes() == first_index
    assert ledger.read_bytes() == first_ledger


def test_common_publisher_heading_variants_still_bind_exact_sections(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract. We study finite query evaluation and present a bounded-fragment algorithm.\n1. Introduction.\nGiven a database and a query, the task returns all answers under set semantics.",
        "2. Formal Setting.\nLet the input be a finite instance and query, and the output be answer tuples; bounded arity is assumed.",
        "3. Contributions.\nWe establish a polynomial upper bound for the stated fragment through a homomorphism reduction.",
        "4. Conclusions\nThe method is restricted to set semantics and needs adaptation for bag semantics in future work.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"]["DEEP_READ"] == 0
    assert _heading("1. Introduction.") == "1. Introduction."
    assert _heading("4. Conclusions") == "4. Conclusions"


def test_opening_subsection_and_explicit_future_direction_can_supply_missing_named_sections(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract\nWe study finite query evaluation and present an algorithm.\n1.1 Problem Setting\nGiven a database and query, the task returns answers under set semantics.",
        "2 Formal Model\nLet the input be finite and the output be answer tuples, assuming bounded arity.",
        "3 Contributions\nWe prove a polynomial bound by a homomorphism reduction.",
        "6 Future Directions\nThe stated fragment remains restricted to set semantics and does not cover bag semantics.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"]["DEEP_READ"] == 0
    assert result["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"


def test_offline_cli_derives_report_counts_from_generated_frozen_notes(tmp_path: Path) -> None:
    payload = _deep_pdf()
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    manifests = tmp_path / "manifests.jsonl"
    papers = tmp_path / "papers.jsonl"
    acquisition_ledger = tmp_path / "acquisition.json"
    read_ledger = tmp_path / "read-depth.json"
    notes = tmp_path / "notes"
    report = tmp_path / "report.md"
    corpus.write_manifests((manifest,), manifests)
    papers.write_text(json.dumps(_record(), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    exit_code = corpus.main([
        "--root", str(tmp_path), "--papers", str(papers), "--manifests", str(manifests),
        "--ledger", str(acquisition_ledger), "--read-ledger", str(read_ledger),
        "--notes", str(notes), "--report", str(report), "--deep-read-target", "1",
    ])

    assert exit_code == 0
    rendered = report.read_text(encoding="utf-8")
    assert "FULL_SCAN: 0" in rendered
    assert "FULL_SCAN only: 0" in rendered
    assert "DEEP_READ: 0" in rendered
    assert "Reading-depth coverage" in rendered
    assert "paper:reading-a" not in rendered or "shortfall" in rendered
    assert "reading_notes_and_ledger" in rendered
    assert json.loads(read_ledger.read_text(encoding="utf-8"))["counts"]["DEEP_READ"] == 0


def test_section_map_may_include_intro_and_conclusion_distinct_from_semantic_evidence(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract\nWe present a bounded-fragment algorithm for query evaluation.\n1 Introduction\nThis section gives the article roadmap and context.",
        "2 Problem Definition\nGiven a finite database and query, the task returns answer tuples under set semantics.",
        "3 Formal Model\nLet the input be finite and the output be query answers, assuming bounded arity.",
        "4 Main Result\nWe prove a polynomial bound by a homomorphism reduction.",
        "5 Limitations\nThe stated fragment does not cover bag semantics and leaves that extension for future work.",
        "6 Conclusion\nThis section summarizes the article.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"]["DEEP_READ"] == 0
    assert result["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"


def test_source_certainty_words_are_not_repeated_as_unsupported_note_certainty(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract\nWe study finite query evaluation and present an algorithm.\n1 Introduction\nGiven a database and query, the task returns answers.",
        "2 Formal Setting\nLet the input be finite and the output be answer tuples under set semantics.",
        "3 Results\nWe prove that the algorithm always returns answers for the bounded fragment by dynamic programming.",
        "4 Limitations\nThe method does not cover bag semantics and leaves that extension for future work.",
        "5 Conclusion\nThe paper summarizes the bounded result.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"]["DEEP_READ"] == 0


def test_note_validation_failure_is_recorded_as_lower_depth_instead_of_aborting(tmp_path: Path) -> None:
    payload = _pdf(
        "Scoped Query Evaluation\nAbstract\nWe study finite query evaluation.\n1 Introduction\nGiven a database and query, return the answers.",
        "2 C:\\local\\Formal Setting\nLet the input be finite and output be answers under set semantics.",
        "3 Results\nWe prove a polynomial bound by dynamic programming.",
        "4 Limitations\nThe result does not cover bag semantics and leaves future work.",
        "5 Conclusion\nThe article concludes.",
    )
    manifest = _manifest(payload)
    target = tmp_path / manifest.cache_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    result = build_reading_corpus((manifest,), (_record(),), tmp_path,
                                  tmp_path / "notes", tmp_path / "ledger.json", deep_read_target=1)

    assert result["counts"]["SHORTFALL"] == 1
    assert result["records"][0]["read_depth"] == "ABSTRACT"
    assert result["records"][0]["shortfall_reason"] == "SOURCE_AUDIT_NOT_COMPLETED"


def test_heading_detector_rejects_bibliography_entries_and_numbered_prose() -> None:
    assert _heading("1. Introduction.") == "1. Introduction."
    assert _heading("3.2 The General 0–1 Law") == "3.2 The General 0–1 Law"
    assert _heading("3.1. MMSNP with guarded inequality. In this subsection, we prove the following") == "3.1. MMSNP with guarded inequality."
    assert _heading("3.2. Guarded Monotone SNP over one-element signatures.In this section, we prove") == "3.2. Guarded Monotone SNP over one-element signatures."
    assert _heading("4. NP is polynomial-time equiv alent to MMSNP with inequality") == "4. NP is polynomial-time equiv alent to MMSNP with inequality"
    assert _heading("4.1. Obliviousness. A Turing machine M is called oblivious if there exists a function") == "4.1. Obliviousness."
    assert _heading("30 Mihalis Yannakakis. Algorithms for Acyclic Database Schemes. In VLDB, pages 82-94, 1981.") is None
    assert _heading("9 Observe that, for monotone queries, it is equivalent whether a fact has positive impact") is None
