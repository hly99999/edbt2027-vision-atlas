from __future__ import annotations

import json
from pathlib import Path

from db_theory_atlas.corpus_task4 import build_frozen_task4_corpus


ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / "data" / "theorems" / "fragments" / "batch-001-020.jsonl"
INVENTORY = ROOT / "data" / "theorems" / "fragments" / "claim-inventory-001-020.jsonl"


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _theorems() -> list[dict[str, object]]:
    return [row for row in _rows(FRAGMENT) if row.get("record_type") == "theorem"]


def test_claim_inventory_has_concise_source_located_claims_with_exact_spans() -> None:
    corpus = build_frozen_task4_corpus(ROOT)
    maps = {(item.paper_id, item.version_id, item.source_hash): item for item in corpus.source_maps}
    inventory = _rows(INVENTORY)

    assert inventory
    for row in inventory:
        claim_text = row["claim_text"]
        claim_source = row["claim_source"]
        region = row["claim_region"]
        assert isinstance(claim_text, str) and 20 <= len(claim_text) <= 420
        assert isinstance(claim_source, str) and len(claim_source.split()) >= 3
        assert claim_source != "abstract/introduction/contributions reconciliation"
        assert isinstance(region, dict)
        source_map = maps[(row["paper_id"], row["version_id"], row["source_hash"])]
        page_text = source_map.page_blocks[region["page"] - 1].normalized_text
        assert page_text[region["start"]:region["end"]] == claim_source
        assert region["section"]
        assert row["mapped_theorem_id"].startswith("theorem:batch-001-")


def test_paper_12_inventory_includes_all_omitted_main_results() -> None:
    rows = [row for row in _rows(INVENTORY) if row["ordinal"] == 12]
    labels = {row["source_location"]["label"] for row in rows}
    assert {"Theorem 2", "Theorem 5", "Theorem 7"} <= labels


def test_sampled_theorem_scopes_preserve_exact_source_bounds() -> None:
    ordinal_by_identity = {
        (row["paper_id"], row["version_id"], row["source_hash"]): row["ordinal"]
        for row in _rows(INVENTORY)
    }
    by_ordinal_label = {
        (
            ordinal_by_identity[(row["paper_id"], row["version_id"], row["source_hash"])],
            row["source_location"]["label"],
        ): row["formal_scope"]
        for row in _theorems()
    }
    paper5 = by_ordinal_label[(5, "Theorem 14")]
    assert paper5["communication_rounds"] == "3"
    assert "|D|/p" in paper5["load"] and "1/c(S)" in paper5["load"]
    assert paper5["randomness"] == "RANDOMIZED_HIGH_PROBABILITY"
    paper6 = by_ordinal_label[(6, "Theorem 8")]
    assert paper6["preprocessing"] == "O(|K|)"
    assert paper6["delay"] == "CONSTANT"
    assert "acyclic" not in " ".join(paper6["assumptions"]).casefold()
    assert paper6["query_fragment"] == "FULL_CQ_WITH_GIVEN_COVER"
    paper9 = by_ordinal_label[(9, "Theorem 2")]
    assert paper9["preprocessing"] == "O(N^p)"
    assert paper9["delay"] == "O(N^e)"
    paper20 = by_ordinal_label[(20, "Theorem 5")]
    assert paper20["preprocessing"] == "LOGLINEAR"
    assert paper20["access_time"] == "LOGARITHMIC"
    assert paper20["assumptions"] == [
        "logarithmic-time commutative semiring",
        "positive branch: free-connex",
        "positive branch: no disruptive trio",
        "conditional negative branch: self-join-free",
        "conditional negative cyclic case: HYPERCLIQUE hypothesis",
        "conditional negative acyclic case: SparseBMM hypothesis",
    ]
    assert paper20["query_fragment"] == (
        "CQ_STAR_FREE_CONNEX_NO_DISRUPTIVE_TRIO_POSITIVE_SELF_JOIN_FREE_NEGATIVE"
    )


def test_no_result_inherits_assumptions_from_unrelated_page_text() -> None:
    claims = {row["mapped_theorem_id"]: row["claim_source"].casefold() for row in _rows(INVENTORY)}
    for row in _theorems():
        source_claim = claims[row["theorem_id"]]
        assumptions = " ".join(row["formal_scope"]["assumptions"]).casefold()
        if "acyclic" in assumptions:
            assert "acyclic" in source_claim
        if "self-join-free" in assumptions:
            assert "self-join-free" in source_claim
        if assumptions != "not_stated_in_source":
            assert assumptions


def test_theorem_statements_are_concise_clean_paraphrases() -> None:
    forbidden = ("proof.", "references", "bibliography", "proceedings of", "doi:", "http://", "https://")
    for row in _theorems():
        statement = row["statement"]
        assert 20 <= len(statement) <= 420
        assert not any(token in statement.casefold() for token in forbidden)
        assert "records the source-stated result:" not in statement.casefold()


def test_sampled_proof_methods_are_complete_and_exactly_source_bound() -> None:
    corpus = build_frozen_task4_corpus(ROOT)
    maps = {(item.paper_id, item.version_id, item.source_hash): item for item in corpus.source_maps}
    rows = [row for row in _rows(FRAGMENT) if row.get("record_type") == "proof_technique"]
    ordinal_by_identity = {
        (row["paper_id"], row["version_id"], row["source_hash"]): row["ordinal"]
        for row in _rows(INVENTORY)
    }
    by_ordinal_label: dict[tuple[int, str], list[dict[str, object]]] = {}
    for row in rows:
        ordinal = ordinal_by_identity[(row["paper_id"], row["version_id"], row["source_hash"])]
        by_ordinal_label.setdefault((ordinal, row["source_location"]["label"]), []).append(row)
        source_map = maps[(row["paper_id"], row["version_id"], row["source_hash"])]
        page_text = source_map.page_blocks[row["evidence_page"] - 1].normalized_text
        assert page_text[row["evidence_start"]:row["evidence_end"]] == row["evidence"]

    assert by_ordinal_label[(5, "Theorem 14")]
    paper5 = by_ordinal_label[(5, "Theorem 14")]
    assert [(row["technique"], row["role"]) for row in paper5] == [("PARTITIONING", "PRIMARY")]
    assert "partition" in paper5[0]["evidence"].casefold()
    assert {row["technique"] for row in by_ordinal_label[(18, "Theorem 4.1")]} >= {
        "COMPACTNESS", "AMALGAMATION", "REDUCTION",
    }
    assert {row["technique"] for row in by_ordinal_label[(20, "Theorem 9")]} >= {
        "REDUCTION", "HOMOMORPHISM", "NUMBER_THEORY",
    }

    for proof_rows in by_ordinal_label.values():
        assert sum(row["role"] == "PRIMARY" for row in proof_rows) == 1
        assert all(row["role"] in {"PRIMARY", "SECONDARY"} for row in proof_rows)
        assert all(row["technique"] != "OTHER_SOURCE_STATED" for row in proof_rows)
