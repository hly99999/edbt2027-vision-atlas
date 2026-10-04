from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys

import pypdf

import pytest

from db_theory_atlas.corpus_task4 import (
    PageTextBlock,
    TheoremSourceMap,
    build_frozen_task4_corpus,
    build_source_maps,
    canonical_source_maps_jsonl,
    clear_source_map_page_cache,
    source_map_sha256,
    validate_complete_theorem_source,
    verify_frozen_task3_closure,
)
from db_theory_atlas.corpus_task4 import _page_block, _with_active_sections


ROOT = Path(__file__).resolve().parents[1]


def test_task4_uses_the_pinned_python_and_pypdf_runtime() -> None:
    assert tuple(sys.version_info[:3]) == (3, 12, 13), (
        "runtime mismatch: expected CPython 3.12.13, "
        f"got {sys.version.split()[0]}"
    )
    assert pypdf.__version__ == "6.10.0", (
        "runtime mismatch: expected pypdf 6.10.0, "
        f"got {pypdf.__version__}"
    )


def test_task4_source_map_builder_is_exported_from_package() -> None:
    import db_theory_atlas as atlas

    assert atlas.build_source_maps is build_source_maps


def test_complete_theorem_source_rejects_a_self_declared_deep_read_mapping() -> None:
    with pytest.raises(ValueError, match="authorization"):
        validate_complete_theorem_source({
            "paper_id": "paper:forged", "version_id": "version:forged", "source_hash": "a" * 64,
            "read_depth": "DEEP_READ", "reading_extraction_normalization": "PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1",
        })


def test_complete_theorem_source_requires_a_frozen_corpus_authorization() -> None:
    corpus = build_frozen_task4_corpus(ROOT)
    source = corpus.source_maps[0]
    authorization = corpus.authorize(source)

    assert validate_complete_theorem_source({
        "paper_id": source.paper_id, "version_id": source.version_id, "source_hash": source.source_hash,
    }, authorization) == authorization
    with pytest.raises(ValueError, match="source map"):
        validate_complete_theorem_source({
            "paper_id": source.paper_id, "version_id": source.version_id, "source_hash": source.source_hash,
        }, replace(authorization, source_map_sha256="0" * 64))
    with pytest.raises(ValueError, match="does not match"):
        validate_complete_theorem_source({
            "paper_id": source.paper_id, "version_id": source.version_id, "source_hash": "0" * 64,
        }, authorization)


def _copied_task3_input(tmp_path: Path, filename: str) -> Path:
    source = ROOT / "literature" / "fulltext_manifests" / filename
    destination = tmp_path / filename
    shutil.copyfile(source, destination)
    return destination


@pytest.mark.parametrize("field", ("paper_id", "version_id", "source_hash"))
def test_builder_rejects_tampered_ledger_identity_before_pdf_extraction(tmp_path: Path, field: str) -> None:
    ledger = json.loads((ROOT / "literature/fulltext_ledgers/read_depth_2026_08_30.json").read_text(encoding="utf-8"))
    record = next(item for item in ledger["records"] if item["read_depth"] == "DEEP_READ")
    record[field] = "paper:tampered" if field == "paper_id" else ("version:tampered" if field == "version_id" else "0" * 64)
    copied = tmp_path / "read_depth_2026_08_30.json"
    copied.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    with pytest.raises(ValueError, match="closure bundle hashes"):
        build_source_maps(ROOT, read_ledger_path=copied)


@pytest.mark.parametrize("filename,field", (
    ("acquisition_2026_08_30.jsonl", "content_sha256"),
    ("acquisition_2026_08_30.jsonl", "byte_count"),
    ("acquisition_attempts_2026_08_30.jsonl", "content_sha256"),
    ("acquisition_attempts_2026_08_30.jsonl", "byte_count"),
))
def test_builder_rejects_tampered_manifest_or_attempt_bundle(tmp_path: Path, filename: str, field: str) -> None:
    copied = _copied_task3_input(tmp_path, filename)
    rows = [json.loads(line) for line in copied.read_text(encoding="utf-8").splitlines() if line.strip()]
    valid = next(item for item in rows if item["status"] == "VALID_PDF")
    valid[field] = "0" * 64 if field == "content_sha256" else int(valid[field]) + 1
    copied.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")

    kwargs = {"manifests_path": copied} if filename.startswith("acquisition_") and "attempts" not in filename else {"attempts_path": copied}
    with pytest.raises(ValueError, match="closure bundle hashes"):
        build_source_maps(ROOT, **kwargs)


def test_builder_rejects_a_duplicate_deep_read_family_before_pdf_extraction(tmp_path: Path) -> None:
    ledger = json.loads((ROOT / "literature/fulltext_ledgers/read_depth_2026_08_30.json").read_text(encoding="utf-8"))
    deep = [item for item in ledger["records"] if item["read_depth"] == "DEEP_READ"]
    deep[1]["paper_id"] = deep[0]["paper_id"]
    copied = tmp_path / "read_depth_2026_08_30.json"
    copied.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    with pytest.raises(ValueError, match="closure bundle hashes"):
        build_source_maps(ROOT, read_ledger_path=copied)


def test_builder_rejects_a_missing_cached_pdf_after_validating_the_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    real_is_file = Path.is_file

    def missing_cache(path: Path) -> bool:
        if "fulltext_cache" in path.parts:
            return False
        return real_is_file(path)

    monkeypatch.setattr(Path, "is_file", missing_cache)
    with pytest.raises(ValueError, match="selected cache PDF is missing"):
        build_source_maps(ROOT)


def test_build_source_maps_binds_exactly_the_frozen_deep_read_cache_and_is_deterministic() -> None:
    clear_source_map_page_cache()
    first = build_source_maps(ROOT)
    clear_source_map_page_cache()
    second = build_source_maps(ROOT)

    assert len(first) == 80
    assert {(item.paper_id, item.version_id) for item in first} == {
        (item.paper_id, item.version_id) for item in second
    }
    assert len({item.paper_id for item in first}) == 80
    assert len({item.version_id for item in first}) == 80
    assert canonical_source_maps_jsonl(first) == canonical_source_maps_jsonl(second)
    assert source_map_sha256(first) == source_map_sha256(second)
    assert all(item.page_blocks[0].page == 1 for item in first)
    assert all(item.cache_binding.actual_sha256 == item.source_hash for item in first)
    assert all(item.cache_binding.actual_byte_count == item.cache_binding.byte_count for item in first)


def test_source_map_contract_fails_closed_for_nonordered_page_blocks_and_tampered_cache_binding() -> None:
    source_map = build_source_maps(ROOT)[0]
    with pytest.raises(ValueError, match="ordered"):
        replace(source_map, page_blocks=tuple(reversed(source_map.page_blocks)))
    with pytest.raises(ValueError, match="actual SHA-256"):
        replace(source_map.cache_binding, actual_sha256="0" * 64)
    with pytest.raises(ValueError, match="actual byte count"):
        replace(source_map.cache_binding, actual_byte_count=source_map.cache_binding.actual_byte_count + 1)
    with pytest.raises(ValueError, match="duplicate family/version"):
        canonical_source_maps_jsonl((source_map, source_map))


def test_source_map_detects_lipics_theorem_labels_prefixed_by_statement_marker() -> None:
    block = _page_block(
        10,
        "6 Main Result\n▶ Theorem 16. Every formula in the stated fragment has size at least the bound.\n",
    )

    assert block.theorem_labels == ("Theorem 16",)


def test_source_map_carries_one_unambiguous_active_section_to_a_theorem_only_page() -> None:
    blocks = _with_active_sections((
        _page_block(1, "3 Main Results\nThe setup is fixed here.\n"),
        _page_block(2, "The discussion continues.\nTheorem 3.1. The stated bound holds.\n"),
    ))

    assert blocks[1].section_headings == ("3 Main Results",)
    assert blocks[1].carried_section_heading == "3 Main Results"
    assert blocks[1].carried_section_from_page == 1


def test_source_map_local_heading_takes_precedence_over_prior_active_section() -> None:
    blocks = _with_active_sections((
        _page_block(1, "2 Preliminaries\n"),
        _page_block(2, "3 Main Result\nTheorem 3.1. The stated bound holds.\n"),
    ))

    assert blocks[1].section_headings == ("3 Main Result",)
    assert blocks[1].carried_section_heading is None
    assert blocks[1].carried_section_from_page is None


def test_source_map_retains_prior_section_for_theorem_before_first_local_heading() -> None:
    blocks = _with_active_sections((
        _page_block(1, "6 Main Result\n"),
        _page_block(2, "Theorem 16. The lower bound holds.\n7 Proof Overview\n"),
    ))

    assert blocks[1].section_headings == ("6 Main Result", "7 Proof Overview")
    assert blocks[1].carried_section_heading == "6 Main Result"
    assert blocks[1].carried_section_from_page == 1


def test_source_map_last_local_heading_resets_active_section_by_reading_order() -> None:
    blocks = _with_active_sections((
        _page_block(1, "2 Preliminaries\n"),
        _page_block(2, "3 Results\n3.1 Upper Bound\n"),
        _page_block(3, "Theorem 3.2. The stated lower bound holds.\n"),
    ))

    assert blocks[2].section_headings == ("3.1 Upper Bound",)
    assert blocks[2].carried_section_heading == "3.1 Upper Bound"
    assert blocks[2].carried_section_from_page == 2


def test_source_map_does_not_invent_an_active_section_without_prior_provenance() -> None:
    block = _with_active_sections((
        _page_block(1, "Theorem 1. The stated result holds.\n"),
    ))[0]

    assert block.section_headings == ()
    assert block.carried_section_heading is None
    assert block.carried_section_from_page is None


def test_source_map_binds_each_statement_offset_to_its_active_section() -> None:
    block = _with_active_sections((_page_block(
        1,
        "2 Preliminaries\nTheorem 2.1. Setup.\n3 Main Results\nTheorem 3.1. Result.\n",
    ),))[0]

    assert [(item.label, item.section_heading) for item in block.statement_blocks] == [
        ("Theorem 2.1", "2 Preliminaries"),
        ("Theorem 3.1", "3 Main Results"),
    ]
    assert [item.offset for item in block.statement_blocks] == sorted(
        item.offset for item in block.statement_blocks
    )


@pytest.mark.parametrize("false_heading", (
    "1 (a1) ∧ · · · ∧ RA",
    "1 such that, for all X in σ,",
))
def test_task4_heading_state_rejects_real_paper_formula_and_prose_fragments(false_heading: str) -> None:
    assert _page_block(1, false_heading + "\n").section_headings == ()


def test_ambiguous_numbered_candidate_resets_carried_section_fail_closed() -> None:
    blocks = _with_active_sections((
        _page_block(1, "3 Main Results\n"),
        _page_block(2, "4 Potential Heading With Many Capitalized Terms Across Several Distinct Technical Topics And Additional Context Beyond Normal Limits\nTheorem 3.17. Result.\n"),
    ))

    assert blocks[1].statement_blocks[0].section_heading is None
    assert blocks[1].carried_section_heading is None


def test_ambiguous_numbered_candidate_resets_local_section_fail_closed() -> None:
    block = _with_active_sections((_page_block(
        1,
        "3 Main Results\n"
        "4 Potential Heading With Many Capitalized Terms Across Several Distinct Technical Topics And Additional Context Beyond Normal Limits\n"
        "Theorem 3.17. Result.\n",
    ),))[0]

    assert block.statement_blocks[0].section_heading is None
