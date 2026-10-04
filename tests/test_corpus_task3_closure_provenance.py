from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import build_fulltext_corpus as corpus


ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / ".superpowers" / "sdd" / "corpus-task-3-closure-provenance.json"
READ_LEDGER = ROOT / "literature" / "fulltext_ledgers" / "read_depth_2026_08_30.json"
PROMOTIONS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-fragments" / "closure-121-140-promotions.jsonl"
DEMOTIONS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-fragments" / "closure-121-140-demotions.jsonl"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_task3_closure_provenance_is_canonical_and_bound_to_current_artifacts() -> None:
    document = json.loads(CLOSURE.read_text(encoding="utf-8"))
    assert set(document) == {"schema_version", "closure_payload", "task3_closure_sha256"}
    assert document["schema_version"] == "TASK3_CLOSURE_PROVENANCE_V1"
    payload = document["closure_payload"]
    assert document["task3_closure_sha256"] == _canonical_sha256(payload)
    assert payload["task3_input_head"] == "7b3615530d5abf0aeca1540de5de79cdc83ccea4"
    assert payload["closure_evidence_head"] == "c11f03cc41c4e443a2c52d03f267b970e01a7bce"

    ledger = json.loads(READ_LEDGER.read_text(encoding="utf-8"))
    assert payload["counts"] == {
        "deep_read": ledger["counts"]["DEEP_READ"],
        "full_scan": ledger["counts"]["FULL_SCAN"],
        "reading_shortfalls": ledger["counts"]["SHORTFALL"],
    }
    assert payload["closure_audit"] == {
        "demotions": _jsonl_count(DEMOTIONS),
        "promotions": _jsonl_count(PROMOTIONS),
        "release_margin": "PASS_WITH_BUFFER",
    }
    assert payload["reviews"] == {
        "quality": {"critical": 0, "important": 0, "verdict": "PASS"},
        "spec": {"critical": 0, "important": 0, "verdict": "PASS"},
    }
    assert payload["fresh_tests"]["focused"] == {"failed": 0, "passed": 89}
    assert payload["fresh_tests"]["full"] == {"collected": 410, "failed": 0}
    assert payload["builder_verification"] == {"deterministic": True, "exit_codes": [0, 0], "runs": 2}

    current_hashes = {
        "immutable_attempts": corpus._file_sha256(corpus.ATTEMPTS),
        "reading_notes_and_ledger": corpus._reading_bundle_hash(corpus.NOTES, corpus.READ_LEDGER),
        "selected_outcomes": corpus._file_sha256(corpus.MANIFESTS),
    }
    assert payload["closure_bundle_hashes"] == current_hashes
    assert payload["pre_closure_bundle_hashes"] == {
        "immutable_attempts": "1a3ca5112ee98a6d3637ad5093df745261bb9cdf68be6b51af51b8de69fd6864",
        "reading_notes_and_ledger": "f5fcca1d85f869a02bcb15a0eb99e3eef0ccfd55ccc5946f6582e970005c605c",
        "selected_outcomes": "0131a8395e49993e71dbbb7355c324c4a8a45cf2016f7f1dc3c17f110c3ce32f",
    }
    assert payload["gate_verdict"] == "TASK3_FINAL_PASS"
    assert payload["task4_authorized"] is True
