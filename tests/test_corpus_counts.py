from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts import build_venue_census as census


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "literature" / "source_registry"
RAW = REGISTRY / "venue_census_observations_2023_2026.jsonl"
CANONICAL = REGISTRY / "venue_census_2023_2026.jsonl"
MANIFEST = REGISTRY / "provider_manifests" / "venue_year_queries.jsonl"
EXCLUSIONS = REGISTRY / "venue_census_exclusions_2023_2026.jsonl"
CONFLICTS = REGISTRY / "venue_census_conflicts_2023_2026.jsonl"
SUMMARY = REGISTRY / "provider_manifests" / "census_summary.json"
REPORT = ROOT / ".superpowers" / "sdd" / "corpus-task-1-report.md"

YEARS = {2023, 2024, 2025, 2026}
VENUES = {
    "ICDT",
    "PODS",
    "SIGMOD_PACMMOD",
    "TODS",
    "JACM",
    "LMCS",
    "ICALP",
    "CSL",
    "LICS",
    "KR_AI_LOGIC",
}
PROVIDERS = {"OFFICIAL", "CROSSREF", "ARXIV", "OPENALEX", "DBLP"}
TIERS = {"T1", "T2"}
STATUSES = {"OK", "PARTIAL", "EMPTY", "FAILED"}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    assert path.is_file(), f"missing corpus artifact: {path.relative_to(ROOT)}"
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AssertionError(f"invalid JSONL at {path}:{line_number}: {error}") from error
        assert isinstance(value, dict)
        rows.append(value)
    return rows


def test_census_meets_raw_and_canonical_discovery_floors() -> None:
    raw = read_jsonl(RAW)
    canonical = read_jsonl(CANONICAL)

    assert len(raw) >= 300
    assert len(canonical) >= 250
    assert sum(row["included"] is True for row in canonical) >= 250


def test_canonical_records_are_deduplicated_and_in_window() -> None:
    rows = read_jsonl(CANONICAL)
    ids = [str(row["paper_id"]) for row in rows]
    doi_keys = [str(row["doi"]).lower() for row in rows if row.get("doi")]
    fallback_keys = [
        (str(row["normalized_title"]), str(row["first_author_key"]))
        for row in rows
        if not row.get("doi")
    ]

    assert len(ids) == len(set(ids))
    assert len(doi_keys) == len(set(doi_keys))
    assert len(fallback_keys) == len(set(fallback_keys))
    assert {int(row["year"]) for row in rows} <= YEARS
    assert {str(row["venue_family"]) for row in rows} <= VENUES


def test_every_required_venue_year_has_a_completed_query() -> None:
    rows = read_jsonl(MANIFEST)
    papers = read_jsonl(CANONICAL)
    completed = {
        (str(row["venue_family"]), int(row["year"]))
        for row in rows
        if row["status"] in {"OK", "PARTIAL", "EMPTY"}
    }

    assert completed
    assert {(venue, year) for venue in VENUES for year in YEARS} <= completed
    observed_cells = {(str(row["venue_family"]), int(row["year"])) for row in papers}
    assert {(venue, year) for venue in VENUES for year in YEARS} <= observed_cells


def test_observations_expose_source_tier_status_and_evidence() -> None:
    rows = read_jsonl(RAW)
    assert {str(row["provider"]) for row in rows} <= PROVIDERS
    assert {str(row["source_tier"]) for row in rows} <= TIERS
    assert all(str(row["retrieval_status"]) in STATUSES for row in rows)
    assert all(str(row["evidence_url"]).startswith(("http://", "https://")) for row in rows)
    assert all(str(row["observed_at"]) == "2026-08-28" for row in rows)
    assert all(row.get("title") and row.get("authors") for row in rows)


def test_canonical_records_have_primary_metadata_or_an_explicit_limitation() -> None:
    rows = read_jsonl(CANONICAL)
    for row in rows:
        providers = set(row["providers"])
        assert providers <= PROVIDERS
        assert row["source_status"] in {
            "VERIFIED_PRIMARY",
            "VERIFIED_WITH_WARNINGS",
            "CROSSCHECK_ONLY",
            "CONFLICTED",
        }
        if not providers.intersection({"OFFICIAL", "CROSSREF"}):
            assert row["source_status"] in {"CROSSCHECK_ONLY", "CONFLICTED"}
            assert row.get("source_limitation")


def test_exclusions_and_conflicts_are_preserved_not_silently_dropped() -> None:
    exclusions = read_jsonl(EXCLUSIONS)
    conflicts = read_jsonl(CONFLICTS)

    assert exclusions
    assert all(row.get("paper_id") and row.get("reason_code") and row.get("reason") for row in exclusions)
    assert all(row.get("paper_id") and row.get("field") and row.get("observations") for row in conflicts)


def _observation(
    observation_id: str,
    *,
    provider: str,
    title: str,
    authors: list[str],
    year: int,
    venue_family: str,
    venue: str,
    doi: str | None,
    lineage_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "provider": provider,
        "source_tier": "T1" if provider in {"OFFICIAL", "CROSSREF", "ARXIV"} else "T2",
        "retrieval_status": "OK",
        "observed_at": "2026-08-28",
        "venue_family": venue_family,
        "venue": venue,
        "year": year,
        "title": title,
        "authors": authors,
        "doi": doi,
        "pages": None,
        "volume": None,
        "issue": None,
        "official_url": f"https://doi.org/{doi}" if doi else f"https://example.test/{observation_id}",
        "evidence_url": f"https://example.test/evidence/{observation_id}",
        "metadata_hash": observation_id.removeprefix("obs:").ljust(64, "0")[:64],
        "lineage_ids": lineage_ids or [],
    }


def test_canonical_family_merges_exact_titles_across_dois_and_preserves_versions() -> None:
    conference = _observation(
        "obs:conference",
        provider="CROSSREF",
        title="Direct Access for Conjunctive Queries",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2023,
        venue_family="PODS",
        venue="PODS",
        doi="10.1000/conference",
    )
    journal = _observation(
        "obs:journal",
        provider="CROSSREF",
        title="Direct access for conjunctive queries",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2025,
        venue_family="JACM",
        venue="Journal of the ACM",
        doi="10.1000/journal",
    )

    canonical, exclusions, _conflicts = census.canonicalize([conference, journal])

    assert len(canonical) == 1
    assert exclusions == []
    assert canonical[0]["dois"] == ["10.1000/conference", "10.1000/journal"]
    assert canonical[0]["venue_families"] == ["JACM", "PODS"]
    assert canonical[0]["years"] == [2023, 2025]
    assert len(canonical[0]["versions"]) == 2


def test_near_title_versions_require_author_and_lineage_evidence() -> None:
    conference = _observation(
        "obs:near-conference",
        provider="DBLP",
        title="Enumeration for Guarded Queries",
        authors=["Ada Lovelace"],
        year=2023,
        venue_family="ICDT",
        venue="ICDT",
        doi=None,
        lineage_ids=["family:guarded-enumeration"],
    )
    journal = _observation(
        "obs:near-journal",
        provider="CROSSREF",
        title="Enumeration for Guarded Queries: Full Version",
        authors=["Ada Lovelace"],
        year=2024,
        venue_family="LMCS",
        venue="Logical Methods in Computer Science",
        doi="10.1000/full",
        lineage_ids=["family:guarded-enumeration"],
    )
    unrelated = _observation(
        "obs:near-unrelated",
        provider="DBLP",
        title="Enumeration for Guarded Queries with Updates",
        authors=["Alan Turing"],
        year=2024,
        venue_family="ICDT",
        venue="ICDT",
        doi=None,
    )

    canonical, _, _ = census.canonicalize([conference, journal, unrelated])

    assert len(canonical) == 2
    assert sorted(len(row["versions"]) for row in canonical) == [1, 2]


def test_conference_and_journal_versions_merge_from_high_precision_metadata() -> None:
    examples = (
        (
            "Coverability in VASS Revisited: Improving Rackoff's Bound to Obtain Conditional Optimality.",
            "Coverability in VASS Revisited: Improving Rackoff’s Bounds to Obtain Conditional Optimality",
            ["Marvin Künnemann", "Filip Mazowiecki", "Lia Schütze", "Henry Sinclair-Banks", "Karol Wegrzycki"],
            ["Marvin Künnemann", "Filip Mazowiecki", "Lia Schütze", "Henry Sinclair-Banks", "Karol Węgrzycki"],
            "ICALP",
            "JACM",
        ),
        (
            "Range Entropy Queries and Partitioning.",
            "Range (Rényi) Entropy Queries and Partitioning",
            ["Sanjay Krishnan", "Stavros Sintos"],
            ["Aryan Esmailpour", "Sanjay Krishnan", "Stavros Sintos"],
            "ICDT",
            "LMCS",
        ),
        (
            "A categorical account of composition methods in logic.",
            "A categorical account of composition methods in logic (extended version)",
            ["Tomas Jakl", "Dan Marsden", "Nihil Shah"],
            ["Tomáš Jakl", "Dan Marsden", "Nihil Shah"],
            "LICS",
            "LMCS",
        ),
        (
            "From Thin Concurrent Games to Generalized Species of Structures.",
            "From Thin Concurrent Games to Generalized Species of Structures (Extended Version)",
            ["Pierre Clairambault", "Federico Olimpieri", "Hugo Paquet"],
            ["Pierre Clairambault", "Federico Olimpieri", "Hugo Paquet"],
            "LICS",
            "LMCS",
        ),
    )
    observations = []
    for index, (conference_title, journal_title, conference_authors, journal_authors, conference_venue, journal_venue) in enumerate(examples):
        observations.extend(
            (
                _observation(
                    f"obs:conference-version-{index}",
                    provider="DBLP",
                    title=conference_title,
                    authors=conference_authors,
                    year=2023 + (index == 1),
                    venue_family=conference_venue,
                    venue=conference_venue,
                    doi=f"10.1000/conference-{index}",
                ),
                _observation(
                    f"obs:journal-version-{index}",
                    provider="OPENALEX",
                    title=journal_title,
                    authors=journal_authors,
                    year=2025,
                    venue_family=journal_venue,
                    venue={"JACM": "Journal of the ACM", "LMCS": "Logical Methods in Computer Science"}[journal_venue],
                    doi=f"10.1000/journal-{index}",
                ),
            )
        )

    canonical, _, _ = census.canonicalize(observations)

    assert len(canonical) == 4
    assert sorted(len(row["versions"]) for row in canonical) == [2, 2, 2, 2]


def test_topic_similarity_alone_does_not_merge_distinct_papers() -> None:
    first = _observation(
        "obs:topic-similar-one",
        provider="DBLP",
        title="Range Entropy Queries and Partitioning",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2023,
        venue_family="ICDT",
        venue="ICDT",
        doi="10.1000/topic-one",
    )
    second = _observation(
        "obs:topic-similar-two",
        provider="OPENALEX",
        title="Range Entropy Queries with Dynamic Partitioning",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2025,
        venue_family="LMCS",
        venue="Logical Methods in Computer Science",
        doi="10.1000/topic-two",
    )

    canonical, _, _ = census.canonicalize([first, second])

    assert len(canonical) == 2


def test_openalex_venue_observation_retains_doi_location_conflict_but_is_ineligible() -> None:
    item = {
        "id": "https://openalex.org/W1",
        "title": "A Journal Extension",
        "publication_year": 2023,
        "doi": "https://doi.org/10.1109/conference.1",
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {
            "landing_page_url": "https://doi.org/10.1145/journal.2",
            "source": {"id": "https://openalex.org/S118992489", "display_name": "Journal of the ACM"},
        },
        "biblio": {"volume": "73", "issue": "4", "first_page": "1", "last_page": "20"},
    }

    row = census.openalex_observation(item, "JACM", expected_year=2023)

    assert row is not None
    assert row["eligible_for_canonical"] is False
    assert row["doi"] == "10.1145/journal.2"
    assert row["top_level_doi"] == "10.1109/conference.1"
    assert "OPENALEX_DOI_LOCATION_MISMATCH" in row["validation_conflicts"]


def test_openalex_venue_observation_rejects_wrong_source_or_year_for_verified_use() -> None:
    item = {
        "id": "https://openalex.org/W2",
        "title": "Wrong Venue",
        "publication_year": 2024,
        "doi": "https://doi.org/10.1000/wrong",
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {
            "landing_page_url": "https://doi.org/10.1000/wrong",
            "source": {"id": "https://openalex.org/S999", "display_name": "Unrelated Venue"},
        },
        "biblio": {},
    }

    row = census.openalex_observation(item, "JACM", expected_year=2023)

    assert row is not None
    assert row["eligible_for_canonical"] is False
    assert set(row["validation_conflicts"]) >= {
        "OPENALEX_SOURCE_FAMILY_MISMATCH",
        "OPENALEX_VENUE_YEAR_MISMATCH",
    }


def test_invalid_provider_doi_cannot_control_the_canonical_family_id() -> None:
    trusted = _observation(
        "obs:trusted-family-id",
        provider="CROSSREF",
        title="Trusted Canonical Family",
        authors=["Ada Lovelace"],
        year=2025,
        venue_family="JACM",
        venue="Journal of the ACM",
        doi="10.9999/valid",
    )
    invalid = _observation(
        "obs:invalid-family-id",
        provider="OPENALEX",
        title="Trusted Canonical Family",
        authors=["Ada Lovelace"],
        year=2025,
        venue_family="JACM",
        venue="Journal of the ACM",
        doi="10.0001/invalid",
    )
    invalid.update(
        source_id="S118992489",
        official_url="https://doi.org/10.9998/location",
        validation_conflicts=["OPENALEX_DOI_LOCATION_MISMATCH"],
        eligible_for_canonical=False,
    )

    canonical, _, _ = census.canonicalize([invalid, trusted])

    assert canonical[0]["paper_id"] == census.paper_id(("doi", "10.9999/valid"))


def test_non_papers_and_pure_systems_or_llm_benchmarks_are_explicitly_excluded() -> None:
    titles_and_codes = {
        "Invited Talk: The Future of Data": "NON_RESEARCH_MATERIAL",
        "Workshop Preface": "NON_RESEARCH_MATERIAL",
        "A Benchmark for Large Language Model SQL Systems": "LLM_BENCHMARK_SCOPE",
        "CloudDB: An Industrial Deployment Platform": "SYSTEMS_SCOPE",
    }
    for index, (title, code) in enumerate(titles_and_codes.items()):
        row = _observation(
            f"obs:excluded-{index}",
            provider="DBLP",
            title=title,
            authors=["Ada Lovelace"],
            year=2025,
            venue_family="SIGMOD_PACMMOD",
            venue="SIGMOD Conference",
            doi=None,
        )
        exclusion = census.exclusion_for(row)
        assert exclusion is not None
        assert exclusion[0] == code

    theory_row = _observation(
        "obs:theory-system-word",
        provider="DBLP",
        title="A Lower Bound for Distributed Query Evaluation Systems",
        authors=["Ada Lovelace"],
        year=2025,
        venue_family="PODS",
        venue="PODS",
        doi=None,
    )
    assert census.exclusion_for(theory_row) is None


def test_llm_and_pure_system_counterexamples_have_explicit_scope_reasons() -> None:
    titles_and_codes = {
        "PolarDB-IMCI: A Cloud-Native HTAP Database System at Alibaba": "SYSTEMS_SCOPE",
        "CodeS: Towards Building Open-source Language Models for Text-to-SQL": "LLM_BENCHMARK_SCOPE",
        "Pneuma: Leveraging LLMs for Tabular Data Representation and Retrieval in an End-to-End System": "LLM_BENCHMARK_SCOPE",
        "A Scalable Video-Management System": "SYSTEMS_SCOPE",
        "TranSQL+: Serving Large Language Models with SQL on Low-Resource Hardware": "LLM_BENCHMARK_SCOPE",
        "A Foundation Models Benchmark for Code Generation": "LLM_BENCHMARK_SCOPE",
    }
    for index, (title, expected_code) in enumerate(titles_and_codes.items()):
        row = _observation(
            f"obs:scope-counterexample-{index}",
            provider="DBLP",
            title=title,
            authors=["Ada Lovelace"],
            year=2025,
            venue_family="SIGMOD_PACMMOD",
            venue="SIGMOD Conference",
            doi=f"10.1000/scope-{index}",
        )

        exclusion = census.exclusion_for(row)

        assert exclusion is not None
        assert exclusion[0] == expected_code
        assert "scope" in exclusion[1]


def test_report_counts_are_generated_from_the_committed_summary() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    report = REPORT.read_text(encoding="utf-8")
    counts = summary["counts"]

    assert f"Raw observations: {counts['raw_observations']:,}" in report
    assert f"Canonical deduplicated paper families: {counts['canonical_papers']:,}" in report
    assert f"Included canonical paper families: {counts['included_canonical_papers']:,}" in report
    assert f"Explicitly excluded canonical paper families: {counts['excluded_canonical_papers']:,}" in report
    assert "without duplicate inflation" not in report


def test_frozen_outputs_have_no_exact_title_duplicate_families_or_promoted_invalid_openalex() -> None:
    raw = read_jsonl(RAW)
    canonical = read_jsonl(CANONICAL)
    normalized_titles = [str(row["normalized_title"]) for row in canonical]
    promoted_observation_ids = {
        str(observation_id)
        for row in canonical
        if row["source_status"] == "VERIFIED_PRIMARY"
        for observation_id in row["observation_ids"]
    }
    invalid_openalex_ids = {
        str(row["observation_id"])
        for row in raw
        if row["provider"] == "OPENALEX" and row.get("validation_conflicts")
    }

    assert len(normalized_titles) == len(set(normalized_titles))
    assert promoted_observation_ids.isdisjoint(invalid_openalex_ids)
    assert all(
        row["included"] is False and row["source_status"] == "CONFLICTED"
        for row in canonical
        if row["venue_family"] == "JACM" and "foundations of computer science" in str(row["venue"]).casefold()
    )


def test_frozen_cache_rebuild_is_byte_identical_and_does_not_read_prior_outputs(tmp_path: Path) -> None:
    assert census.FROZEN_CACHE.is_file()
    first_registry = tmp_path / "first" / "source_registry"
    second_registry = tmp_path / "second" / "source_registry"
    first_report = tmp_path / "first" / "report.md"
    second_report = tmp_path / "second" / "report.md"

    census.rebuild_from_frozen(census.FROZEN_CACHE, first_registry, first_report)
    shutil.copytree(first_registry, second_registry)
    (second_registry / "venue_census_2023_2026.jsonl").write_text("stale output\n", encoding="utf-8")
    census.rebuild_from_frozen(census.FROZEN_CACHE, second_registry, second_report)

    assert census.artifact_hashes(first_registry, first_report) == census.artifact_hashes(second_registry, second_report)
    assert census.artifact_hashes(first_registry, first_report) == census.artifact_hashes(REGISTRY, REPORT)
