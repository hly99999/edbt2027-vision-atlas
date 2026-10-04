from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from db_theory_atlas.fulltext_reading import (
    extract_valid_pdf,
    parse_source_audit,
    render_audited_note,
    validate_source_audit,
)
from scripts import build_fulltext_corpus as corpus


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-packet-tool.py"
PROMOTIONS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-fragments" / "closure-121-140-promotions.jsonl"
PACKETS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-packets"
REPORT = ROOT / ".superpowers" / "sdd" / "corpus-task-3-final-report.md"


def _load_tool():
    spec = importlib.util.spec_from_file_location("corpus_task3_audit_packet_tool", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(paper: str, version: str, *, status: str = "VALID_PDF") -> dict[str, object]:
    return {
        "paper_id": paper,
        "version_id": version,
        "status": status,
    }


def test_closure_selection_is_exactly_the_new_valid_selected_attempt_suffix() -> None:
    tool = _load_tool()
    baseline = [_manifest("paper:old", "version:old")]
    current = [
        _manifest("paper:new-b", "version:new-b"),
        *baseline,
        _manifest("paper:new-a", "version:new-a"),
    ]
    attempts = [
        _manifest("paper:failed", "version:failed", status="TRANSPORT_FAILURE"),
        _manifest("paper:new-a", "version:new-a"),
        _manifest("paper:new-b", "version:new-b"),
    ]

    selected = tool.select_closure_candidates(
        current,
        baseline,
        attempts,
        expected_count=2,
    )

    assert [(row["paper_id"], row["version_id"]) for row in selected] == [
        ("paper:new-a", "version:new-a"),
        ("paper:new-b", "version:new-b"),
    ]


def test_closure_selection_rejects_duplicate_paper_or_version_counting() -> None:
    tool = _load_tool()
    duplicate_versions = [
        _manifest("paper:new", "version:one"),
        _manifest("paper:new", "version:two"),
    ]

    with pytest.raises(ValueError, match="duplicate paper family"):
        tool.select_closure_candidates(
            duplicate_versions,
            [],
            duplicate_versions,
            expected_count=2,
        )


def test_index_extension_preserves_existing_ordinals_and_rejects_duplicate_keys() -> None:
    tool = _load_tool()
    existing = [
        {"ordinal": 1, "paper_id": "paper:a", "version_id": "version:a", "marker": "keep-a"},
        {"ordinal": 2, "paper_id": "paper:b", "version_id": "version:b", "marker": "keep-b"},
    ]
    additions = [
        {"paper_id": "paper:c", "version_id": "version:c"},
        {"paper_id": "paper:d", "version_id": "version:d"},
    ]

    extended = tool.append_index_rows(existing, additions)

    assert extended[:2] == tuple(existing)
    assert [row["ordinal"] for row in extended] == [1, 2, 3, 4]
    assert existing == [
        {"ordinal": 1, "paper_id": "paper:a", "version_id": "version:a", "marker": "keep-a"},
        {"ordinal": 2, "paper_id": "paper:b", "version_id": "version:b", "marker": "keep-b"},
    ]

    with pytest.raises(ValueError, match="duplicate paper/version key"):
        tool.append_index_rows(existing, [{"paper_id": "paper:a", "version_id": "version:a"}])


def test_every_closure_promotion_renders_as_a_valid_audited_note() -> None:
    rows = [json.loads(line) for line in PROMOTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifests = {
        (item.paper_id, item.version_id): item
        for item in (
            corpus._manifest_from_dict(row)
            for row in corpus._read_jsonl(corpus.MANIFESTS)
        )
    }

    for row in rows:
        audit = parse_source_audit(row)
        manifest = manifests[(audit.paper_id, audit.version_id)]
        document = extract_valid_pdf(manifest, ROOT)
        validate_source_audit(audit, manifest, document)
        render_audited_note(audit)


def _isolated_packet_output(tmp_path: Path) -> Path:
    output = tmp_path / "corpus-task-3-audit-packets"
    shutil.copytree(PACKETS, output)
    return output


def test_packet_tool_reruns_against_the_real_140_row_suffix_without_duplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    output = _isolated_packet_output(tmp_path)
    before = (output / "index.jsonl").read_bytes()
    monkeypatch.setattr(tool, "OUT", output)

    assert tool.main() == 0

    after = (output / "index.jsonl").read_bytes()
    rows = [json.loads(line) for line in after.decode("utf-8").splitlines() if line.strip()]
    assert after == before
    assert len(rows) == 140
    assert [row["ordinal"] for row in rows] == list(range(1, 141))


def test_packet_tool_rebuilds_a_missing_closure_packet_from_real_cached_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    output = _isolated_packet_output(tmp_path)
    missing = output / "127-8f9d0ae2957e204f7093.md"
    missing.unlink()
    monkeypatch.setattr(tool, "OUT", output)

    assert tool.main() == 0

    assert missing.is_file()
    assert "# UNVERIFIED Task 3 source-audit packet" in missing.read_text(encoding="utf-8")


def test_packet_tool_fails_closed_when_closure_suffix_source_hash_is_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    output = _isolated_packet_output(tmp_path)
    index_path = output / "index.jsonl"
    rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[125]["source_hash"] = "0" * 64
    index_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(tool, "OUT", output)

    with pytest.raises(ValueError, match="closure audit-packet identity changed at 126"):
        tool.main()


def test_packet_tool_fails_closed_when_real_immutable_attempt_suffix_hash_is_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _load_tool()
    output = _isolated_packet_output(tmp_path)
    attempts = [dict(row) for row in corpus._read_jsonl(corpus.ATTEMPTS)]
    attempts[-1]["content_sha256"] = "0" * 64
    attempts_path = tmp_path / "acquisition_attempts_2026_08_30.jsonl"
    attempts_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in attempts
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tool, "OUT", output)
    monkeypatch.setattr(corpus, "ATTEMPTS", attempts_path)

    with pytest.raises(ValueError, match="immutable closure attempt suffix does not match selected manifest/cache"):
        tool.main()


def test_canonical_task3_report_contains_closure_counts_without_stale_blocker() -> None:
    report = REPORT.read_text(encoding="utf-8")

    assert "FULL_SCAN: 125" in report
    assert "Target shortfalls: FULL_SCAN=0, DEEP_READ=0" in report
    assert "112 FULL_SCAN" not in report
    assert "shortfall of 8" not in report
    assert "TASK3_FINAL_PASS" in report
    assert "Spec and Quality reviews: PASS" in report
    assert "Task 4 is authorized" in report
    assert "External review remains required before progress can change" not in report
