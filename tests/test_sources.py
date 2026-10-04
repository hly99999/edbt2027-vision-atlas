from __future__ import annotations

from datetime import date

from db_theory_atlas.sources import (
    ConflictSeverity,
    SourceKind,
    SourceObservation,
    VerificationStatus,
    YearStatus,
    canonical_paper_id,
    verify_metadata,
)


def observed(
    source: SourceKind,
    *,
    title: str = "A Frontier for Query Containment",
    authors: tuple[str, ...] = ("Ada Author", "Bert Author"),
    year: int = 2024,
    venue: str | None = "ICDT",
    doi: str | None = "10.1000/Containment.2024",
    evidence_url: str | None = None,
    year_status: YearStatus = YearStatus.UNKNOWN,
    official_url: str | None = None,
    year_evidence_url: str | None = None,
) -> SourceObservation:
    return SourceObservation(
        source=source,
        observed_title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        official_url=official_url or ("https://publisher.example/paper" if source is SourceKind.PUBLISHER else None),
        preprint_url="https://arxiv.org/abs/2401.00001" if source is SourceKind.ARXIV_FULL_TEXT else None,
        volume=None,
        issue=None,
        pages=None,
        observed_at=date(2026, 8, 17),
        evidence_url=evidence_url or f"https://evidence.example/{source.value.lower()}",
        year_status=year_status,
        year_evidence_url=year_evidence_url
        or (
            f"https://evidence.example/{source.value.lower()}/year"
            if year_status is not YearStatus.UNKNOWN
            else None
        ),
    )


def test_agreeing_observations_select_primary_display_values_and_verified_doi() -> None:
    metadata = verify_metadata(
        (
            observed(SourceKind.DBLP, doi="https://doi.org/10.1000/containment.2024"),
            observed(SourceKind.PUBLISHER),
            observed(SourceKind.ARXIV_FULL_TEXT, title="  A frontier for query containment  "),
        )
    )

    assert metadata.title == "A Frontier for Query Containment"
    assert metadata.authors == ("Ada Author", "Bert Author")
    assert metadata.doi == "10.1000/Containment.2024"
    assert metadata.status is VerificationStatus.VERIFIED
    assert metadata.unresolved_conflicts == ()
    assert canonical_paper_id(metadata).startswith("paper:doi-")


def test_reordered_authors_are_a_critical_visible_conflict() -> None:
    metadata = verify_metadata(
        (
            observed(SourceKind.PUBLISHER),
            observed(SourceKind.DBLP, authors=("Bert Author", "Ada Author")),
        )
    )

    conflict = next(conflict for conflict in metadata.unresolved_conflicts if conflict.field == "authors")
    assert conflict.severity is ConflictSeverity.CRITICAL
    assert metadata.authors == ("Ada Author", "Bert Author")
    assert metadata.status is VerificationStatus.CONFLICTED


def test_doi_target_disagreement_is_critical_even_when_doi_string_agrees() -> None:
    metadata = verify_metadata(
        (
            observed(SourceKind.PUBLISHER),
            observed(SourceKind.DOI_METADATA, title="A Different Paper"),
        )
    )

    assert any(
        conflict.field == "doi_target" and conflict.severity is ConflictSeverity.CRITICAL
        for conflict in metadata.unresolved_conflicts
    )


def test_crossref_online_first_year_is_a_resolved_warning_only_with_named_status_evidence() -> None:
    metadata = verify_metadata(
        (
            observed(SourceKind.PUBLISHER, year=2024, year_status=YearStatus.ISSUE_PUBLICATION),
            observed(SourceKind.DOI_METADATA, year=2023, year_status=YearStatus.ONLINE_FIRST),
        )
    )

    warning = next(conflict for conflict in metadata.conflicts if conflict.field == "year")
    assert warning.severity is ConflictSeverity.WARNING
    assert warning.resolution is not None
    assert metadata.unresolved_conflicts == ()
    assert metadata.status is VerificationStatus.VERIFIED_WITH_WARNINGS


def test_unsupported_or_gross_year_disagreement_remains_critical() -> None:
    metadata = verify_metadata(
        (
            observed(SourceKind.PUBLISHER, year=2024, year_status=YearStatus.ISSUE_PUBLICATION),
            observed(SourceKind.DOI_METADATA, year=2020, year_status=YearStatus.ONLINE_FIRST),
        )
    )

    conflict = next(conflict for conflict in metadata.unresolved_conflicts if conflict.field == "year")
    assert conflict.severity is ConflictSeverity.CRITICAL

    unsupported = verify_metadata(
        (
            observed(SourceKind.PUBLISHER, year=2024),
            observed(SourceKind.DOI_METADATA, year=2023),
        )
    )
    assert any(conflict.field == "year" for conflict in unsupported.unresolved_conflicts)


def test_reversed_or_within_status_years_cannot_be_online_first_warnings() -> None:
    reversed_years = verify_metadata(
        (
            observed(SourceKind.PUBLISHER, year=2023, year_status=YearStatus.ISSUE_PUBLICATION),
            observed(SourceKind.DOI_METADATA, year=2024, year_status=YearStatus.ONLINE_FIRST),
        )
    )
    assert any(conflict.field == "year" for conflict in reversed_years.unresolved_conflicts)

    conflicting_online_first = verify_metadata(
        (
            observed(
                SourceKind.DOI_METADATA,
                year=2023,
                year_status=YearStatus.ONLINE_FIRST,
                evidence_url="https://evidence.example/crossref-2023",
            ),
            observed(
                SourceKind.DOI_METADATA,
                year=2024,
                year_status=YearStatus.ONLINE_FIRST,
                evidence_url="https://evidence.example/crossref-2024",
            ),
            observed(SourceKind.PUBLISHER, year=2024, year_status=YearStatus.ISSUE_PUBLICATION),
        )
    )
    assert any(conflict.field == "year" for conflict in conflicting_online_first.unresolved_conflicts)


def test_equal_precedence_ties_are_total_and_input_order_independent() -> None:
    first_publisher = observed(
        SourceKind.PUBLISHER,
        doi="10.1000/z-last",
        evidence_url="https://evidence.example/same",
        official_url="https://EXAMPLE.org:443/Record",
    )
    second_publisher = observed(
        SourceKind.PUBLISHER,
        doi="10.1000/a-first",
        evidence_url="https://evidence.example/same",
        official_url="https://example.org/Record",
    )

    first = verify_metadata((first_publisher, second_publisher))
    second = verify_metadata((second_publisher, first_publisher))

    assert first.doi == second.doi == "10.1000/a-first"
    assert first.official_url == second.official_url == "https://example.org/Record"
    assert canonical_paper_id(first) == canonical_paper_id(second)


def test_url_authority_case_equivalents_still_have_a_deterministic_display_winner() -> None:
    upper_host = observed(
        SourceKind.PUBLISHER,
        evidence_url="https://evidence.example/same",
        official_url="https://EXAMPLE.org/Record",
    )
    lower_host = observed(
        SourceKind.PUBLISHER,
        evidence_url="https://evidence.example/same",
        official_url="https://example.org/Record",
    )

    first = verify_metadata((upper_host, lower_host))
    second = verify_metadata((lower_host, upper_host))

    assert first.official_url == second.official_url == "https://EXAMPLE.org/Record"


def test_absent_doi_is_explicit_and_fallback_id_is_order_independent() -> None:
    publisher = observed(SourceKind.PUBLISHER, doi=None)
    arxiv = observed(SourceKind.ARXIV_FULL_TEXT, doi=None)

    first = verify_metadata((publisher, arxiv))
    second = verify_metadata((arxiv, publisher))

    assert first.doi is None
    assert canonical_paper_id(first) == canonical_paper_id(second)
    assert canonical_paper_id(first).startswith("paper:title-")
