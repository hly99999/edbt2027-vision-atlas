from __future__ import annotations

import json
from pathlib import Path
import pytest
import shutil

from scripts import build_relevance_screening as screening


ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "literature" / "source_registry" / "venue_census_2023_2026.jsonl"


def test_title_only_topic_match_is_relevant_but_never_high_confidence() -> None:
    result = screening.screen_family(
        {
            "paper_id": "paper:test",
            "title": "Constant-Delay Enumeration for Conjunctive Queries",
            "year": 2025,
            "venue_family": "ICDT",
            "versions": [],
            "dois": [],
            "venue_families": ["ICDT"],
        },
        screening.topic_taxonomy(),
    )

    assert result["classification"] == "DIRECT_DB_THEORY"
    assert result["confidence"] == "LOW"
    assert result["topic_ids"] == ["enumeration_direct_random_access"]
    assert result["evidence_source"] == "TITLE_AND_TOPIC_TAXONOMY"
    assert result["evidence_pointer"] == "title; taxonomy:enumeration_direct_random_access"


def test_openalex_abstract_evidence_can_upgrade_a_title_match_to_high_confidence() -> None:
    family = {
        "paper_id": "paper:test",
        "title": "Constant-Delay Enumeration for Conjunctive Queries",
        "year": 2025,
        "venue_family": "ICDT",
        "doi": "10.1000/example",
        "dois": ["10.1000/example"],
        "versions": [],
        "venue_families": ["ICDT"],
    }
    evidence = {
        "10.1000/example": {
            "provider": "OPENALEX",
            "request_id": "openalex:0001",
            "abstract": "We study constant-delay enumeration of conjunctive queries and give an algorithm.",
        }
    }

    result = screening.screen_family(family, screening.topic_taxonomy(), evidence)

    assert result["classification"] == "DIRECT_DB_THEORY"
    assert result["confidence"] == "HIGH"
    assert result["evidence_source"] == "OPENALEX_ABSTRACT"
    assert result["evidence_pointer"] == "openalex:0001; title+abstract"


def test_cached_openalex_response_is_reconstructed_as_abstract_evidence(tmp_path: Path) -> None:
    cache = tmp_path / "openalex.jsonl"
    response = {"results": [{"doi": "https://doi.org/10.1000/example", "abstract_inverted_index": {"A": [0], "query": [1]}}]}
    payload = {
        "request_id": "openalex:0001",
        "provider": "OPENALEX",
        "url": "https://api.openalex.org/works?filter=doi%3A10.1000%2Fexample",
        "observed_at": "2026-08-29",
        "status": 200,
        "sha256_scope": screening.CANONICAL_RESPONSE_HASH_SCOPE,
        "sha256": screening.canonical_response_sha256(response),
        "requested_dois": ["10.1000/example"],
        "response": response,
    }
    cache.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    evidence, failures = screening.abstract_evidence_from_cache(cache)

    assert evidence["10.1000/example"]["abstract"] == "A query"
    assert evidence["10.1000/example"]["request_id"] == "openalex:0001"
    assert failures == []


def test_generic_homomorphism_in_type_theory_is_not_foundational_db_theory() -> None:
    result = screening.screen_family(
        {"paper_id": "paper:type", "title": "The ∞-Category of ∞-Categories in Simplicial Type Theory", "year": 2025, "doi": "10.1000/type", "dois": []},
        abstract_evidence={"10.1000/type": {"provider": "OPENALEX", "request_id": "openalex:1", "abstract": "We establish a homomorphism principle for simplicial type theory."}},
    )

    assert result["classification"] == "IRRELEVANT"
    assert result["confidence"] == "LOW"


def test_constraint_satisfaction_programming_in_cubical_type_theory_is_not_db_theory() -> None:
    result = screening.screen_family(
        {
            "paper_id": "paper:cubical-type-theory",
            "title": "Automating Boundary Filling in Cubical Type Theories",
            "year": 2026,
            "doi": "10.46298/lmcs-22(2:28)2026",
            "dois": ["10.46298/lmcs-22(2:28)2026"],
        },
        abstract_evidence={
            "10.46298/lmcs-22(2:28)2026": {
                "provider": "OPENALEX",
                "request_id": "openalex:0169",
                "abstract": "We automate boundary filling in cubical type theory using constraint satisfaction programming.",
            }
        },
    )

    assert result["classification"] == "IRRELEVANT"
    assert result["relevant"] is False
    assert result["confidence"] == "LOW"


def test_explicit_promise_infinite_domain_csp_title_is_foundational_low_confidence() -> None:
    result = screening.screen_family(
        {
            "paper_id": "paper:doi-d48bd31ba96904792a51",
            "title": "Promise and Infinite-Domain Constraint Satisfaction",
            "year": 2024,
            "doi": "10.4230/lipics.csl.2024.41",
            "dois": ["10.4230/lipics.csl.2024.41"],
        }
    )

    assert result["classification"] == "FOUNDATIONAL_DB_THEORY"
    assert result["relevant"] is True
    assert result["confidence"] == "LOW"
    assert result["primary_topic_id"] == "finite_model_csp_homomorphism"


def test_explicit_constraint_satisfaction_problem_title_is_foundational_low_confidence() -> None:
    result = screening.screen_family(
        {
            "paper_id": "paper:doi-4a5401999ae205938860",
            "title": "Limitations of Affine Integer Relaxations for Solving Constraint Satisfaction Problems",
            "year": 2025,
            "doi": "10.4230/lipics.icalp.2025.166",
            "dois": ["10.4230/lipics.icalp.2025.166"],
        }
    )

    assert result["classification"] == "FOUNDATIONAL_DB_THEORY"
    assert result["relevant"] is True
    assert result["confidence"] == "LOW"
    assert result["primary_topic_id"] == "finite_model_csp_homomorphism"


def test_datalog_why_not_provenance_is_covered_as_direct_db_theory() -> None:
    result = screening.screen_family(
        {"paper_id": "paper:provenance", "title": "Why(-Not)-Provenance for Datalog with Negation", "year": 2024, "dois": []}
    )

    assert result["classification"] == "DIRECT_DB_THEORY"
    assert result["primary_topic_id"] == "provenance_explanations_causality"


def test_disjoint_title_and_abstract_topics_do_not_upgrade_to_high() -> None:
    result = screening.screen_family(
        {"paper_id": "paper:disjoint", "title": "Query Evaluation", "year": 2025, "doi": "10.1000/disjoint", "dois": []},
        abstract_evidence={"10.1000/disjoint": {"provider": "OPENALEX", "request_id": "openalex:2", "abstract": "We prove a finite model homomorphism theorem."}},
    )

    assert result["primary_topic_id"] == "query_evaluation"
    assert result["confidence"] == "LOW"
    assert "abstract was inspected but did not corroborate" in result["evidence_limitations"]


def test_cache_digest_and_provenance_fail_closed(tmp_path: Path) -> None:
    cache = tmp_path / "tampered.jsonl"
    cache.write_text(json.dumps({"request_id": "", "provider": "OPENALEX", "url": "not-a-url", "observed_at": "bad", "status": 200, "requested_dois": ["10.1000/example"], "sha256": "not-a-sha256", "response": {"results": []}}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cache"):
        screening.abstract_evidence_from_cache(cache)


def test_coverage_marks_successful_batch_dois_omitted_by_provider_as_not_returned() -> None:
    cache_rows = [
        {
            "request_id": "openalex:1",
            "provider": "OPENALEX",
            "url": "https://api.openalex.org/works?x=1",
            "observed_at": "2026-08-29",
            "status": 200,
            "requested_dois": ["10.1000/returned", "10.1000/omitted"],
            "response": {"results": [{"doi": "https://doi.org/10.1000/returned", "abstract_inverted_index": {"database": [0]}}]},
        }
    ]
    for row in cache_rows:
        row["sha256"] = screening.canonical_response_sha256(row["response"])

    coverage = screening.doi_coverage(cache_rows, {"10.1000/returned", "10.1000/omitted"})

    assert coverage["10.1000/returned"]["status"] == "RETURNED_WITH_ABSTRACT"
    assert coverage["10.1000/omitted"]["status"] == "NOT_RETURNED"


def test_build_reports_exact_evidence_source_counts(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    summary = screening.build_screening(CENSUS, tmp_path, report)

    assert summary["evidence_source_counts"] == {
        "TITLE_AND_TOPIC_TAXONOMY": summary["counts"]["title_and_taxonomy_evidence_rows"],
        "TITLE_HEURISTIC": 1,
        "TITLE_SCOPE": summary["counts"]["canonical_families"] - summary["counts"]["title_and_taxonomy_evidence_rows"] - 1,
    }
    rendered = report.read_text(encoding="utf-8")
    assert f"- TITLE_AND_TOPIC_TAXONOMY: {summary['counts']['title_and_taxonomy_evidence_rows']}" in rendered


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_complete_screening_conserves_families_and_enforces_evidence_rules(tmp_path: Path) -> None:
    summary = screening.build_screening(CENSUS, tmp_path, tmp_path / "report.md")
    canonical = _read_jsonl(CENSUS)
    ledger = _read_jsonl(screening.output_paths(tmp_path)["ledger"])

    assert len(canonical) == 3_356
    assert len(ledger) == len(canonical) == summary["counts"]["canonical_families"]
    assert {row["paper_id"] for row in ledger} == {row["paper_id"] for row in canonical}
    assert {row["classification"] for row in ledger} <= screening.CLASSIFICATIONS
    assert all(row["confidence"] in screening.CONFIDENCES for row in ledger)
    assert all(row["confidence"] != "HIGH" for row in ledger)
    for row in ledger:
        assert row["relevance_reason"] and row["evidence_source"] and row["evidence_pointer"]
        if row["relevant"]:
            assert row["evidence_source"] in {"TITLE_AND_TOPIC_TAXONOMY", "TITLE_HEURISTIC"}
            assert row["confidence"] in {"LOW", "MEDIUM"}


def test_task_j_taxonomy_and_query_manifest_cover_every_required_topic(tmp_path: Path) -> None:
    screening.build_screening(CENSUS, tmp_path, tmp_path / "report.md")
    taxonomy = _read_jsonl(screening.output_paths(tmp_path)["taxonomy"])
    manifest = _read_jsonl(screening.output_paths(tmp_path)["query_manifest"])
    required = {
        "cq_ucq",
        "query_evaluation",
        "containment_equivalence",
        "cores_minimization",
        "enumeration_direct_random_access",
        "dynamic_incremental_complexity",
        "width_acyclicity",
        "constraints_chase_certain_answers",
        "provenance_explanations_causality",
        "views_determinacy_qbe_learning",
        "finite_model_csp_homomorphism",
        "uncertain_probabilistic_databases",
        "knowledge_compilation",
        "streaming_dynamic_db_complexity",
    }

    assert {row["topic_id"] for row in taxonomy} == required
    assert {row["topic_id"] for row in manifest} == required
    assert all(row["execution_status"] == "COMPLETE_CENSUS_SCREEN" for row in manifest)
    assert next(row for row in manifest if row["topic_id"] == "provenance_explanations_causality")["matched_family_count"] > 0
    assert next(row for row in manifest if row["topic_id"] == "finite_model_csp_homomorphism")["matched_family_count"] > 0


def test_papers_preserve_census_versions_dois_and_venues(tmp_path: Path) -> None:
    screening.build_screening(CENSUS, tmp_path, tmp_path / "report.md")
    canonical = {row["paper_id"]: row for row in _read_jsonl(CENSUS)}
    papers = _read_jsonl(screening.output_paths(tmp_path)["papers"])

    assert len(papers) == len(canonical)
    for paper in papers:
        source = canonical[paper["paper_id"]]
        assert paper["doi"] == source["doi"]
        assert paper["dois"] == source["dois"]
        assert paper["venue"] == source["venue"]
        assert paper["venue_families"] == source["venue_families"]
        assert paper["versions"] == source["versions"]


def test_offline_rebuild_is_byte_identical_and_summary_counts_are_exact(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_report = tmp_path / "first-report.md"
    second_report = tmp_path / "second-report.md"

    first_summary = screening.build_screening(CENSUS, first, first_report)
    shutil.copytree(first, second)
    screening.output_paths(second)["ledger"].write_text("stale output\n", encoding="utf-8")
    second_summary = screening.build_screening(CENSUS, second, second_report)

    assert first_summary == second_summary
    assert screening.artifact_hashes(first, first_report) == screening.artifact_hashes(second, second_report)
    ledger = _read_jsonl(screening.output_paths(first)["ledger"])
    assert first_summary["counts"]["ledger_rows"] == len(ledger)
    assert first_summary["counts"]["relevant_families"] == sum(row["relevant"] for row in ledger)
    assert first_summary["classification_counts"] == {
        category: sum(row["classification"] == category for row in ledger)
        for category in sorted(screening.CLASSIFICATIONS)
    }


def test_committed_cache_rebuild_reproduces_production_artifacts_and_high_evidence(tmp_path: Path) -> None:
    output_root = tmp_path / "rebuilt"
    rebuilt_paths = screening.output_paths(output_root)
    rebuilt_paths["abstract_cache"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(screening.output_paths(ROOT)["abstract_cache"], rebuilt_paths["abstract_cache"])
    rebuilt_report = output_root / "report.md"

    summary = screening.build_screening(CENSUS, output_root, rebuilt_report)
    production_paths = screening.output_paths(ROOT)
    production_summary = json.loads(production_paths["summary"].read_text(encoding="utf-8"))
    assert summary == production_summary
    assert screening.artifact_hashes(output_root, rebuilt_report) == screening.artifact_hashes(ROOT, ROOT / ".superpowers" / "sdd" / "corpus-task-2-final-report.md")

    ledger = _read_jsonl(production_paths["ledger"])
    ledger_by_id = {row["paper_id"]: row for row in ledger}
    for paper_id in ("paper:doi-d48bd31ba96904792a51", "paper:doi-4a5401999ae205938860"):
        assert ledger_by_id[paper_id]["classification"] == "FOUNDATIONAL_DB_THEORY"
        assert ledger_by_id[paper_id]["confidence"] == "LOW"
        assert ledger_by_id[paper_id]["primary_topic_id"] == "finite_model_csp_homomorphism"
    evidence, _failures = screening.abstract_evidence_from_cache(production_paths["abstract_cache"])
    for row in ledger:
        if row["confidence"] != "HIGH":
            continue
        assert row["evidence_source"] == "OPENALEX_ABSTRACT"
        assert "no abstract" not in row["evidence_limitations"]
        family = next(paper for paper in _read_jsonl(CENSUS) if paper["paper_id"] == row["paper_id"])
        abstract = screening._abstract_evidence_for_family(family, evidence)
        assert abstract is not None
        title_topics = {item["topic"]["topic_id"] for item in screening._topic_matches(screening._normalize_title(family["title"]), screening.topic_taxonomy())}
        abstract_topics = {item["topic"]["topic_id"] for item in screening._topic_matches(screening._normalize_title(abstract["abstract"]), screening.topic_taxonomy())}
        assert not title_topics or title_topics.intersection(abstract_topics)

    coverage = _read_jsonl(production_paths["doi_coverage"])
    assert sum(row["status"] == "NOT_RETURNED" for row in coverage) == production_summary["doi_coverage_counts"]["NOT_RETURNED"]
    manifest = _read_jsonl(production_paths["query_manifest"])
    assert next(row for row in manifest if row["topic_id"] == "provenance_explanations_causality")["matched_family_count"] > 0
