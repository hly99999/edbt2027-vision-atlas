from __future__ import annotations

from datetime import date

import pytest

from db_theory_atlas.sources import SourceKind, SourceObservation, verify_metadata
from db_theory_atlas.versions import (
    LineageEvidenceKind,
    VersionKind,
    VersionLineage,
    VersionObservation,
    VersionRelation,
    resolve_version_family,
)


def source(
    title: str = "A Frontier for Query Containment",
    *,
    authors: tuple[str, ...] = ("Ada Author", "Bert Author"),
    doi: str | None = "10.1000/containment.2024",
    evidence_url: str = "https://evidence.example/publisher",
    official_url: str | None = "https://publisher.example/paper",
) -> SourceObservation:
    return SourceObservation(
        source=SourceKind.PUBLISHER,
        observed_title=title,
        authors=authors,
        year=2024,
        venue="ICDT",
        doi=doi,
        official_url=official_url,
        preprint_url=None,
        volume=None,
        issue=None,
        pages=None,
        observed_at=date(2026, 8, 17),
        evidence_url=evidence_url,
    )


def version(
    identifier: str,
    kind: VersionKind,
    *,
    title: str = "A Frontier for Query Containment",
    source_observation: SourceObservation | None = None,
    version_url: str | None = None,
) -> VersionObservation:
    return VersionObservation(
        version_id=identifier,
        kind=kind,
        source_observation=source_observation or source(title),
        version_url=version_url or f"https://versions.example/{identifier}",
    )


def test_resolves_arxiv_conference_and_journal_with_explicit_evidence() -> None:
    metadata = verify_metadata((source(),))
    preprint = version("version:containment-arxiv", VersionKind.PREPRINT)
    conference = version("version:containment-icdt", VersionKind.CONFERENCE)
    journal = version("version:containment-journal", VersionKind.JOURNAL)
    family = resolve_version_family(
        metadata,
        (preprint, conference, journal),
        (
            VersionLineage(
                source_version_id=preprint.version_id,
                target_version_id=conference.version_id,
                relation=VersionRelation.PREPRINT_OF,
                evidence_urls=(preprint.source_observation.evidence_url,),
                evidence_kind=LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
            ),
            VersionLineage(
                source_version_id=conference.version_id,
                target_version_id=journal.version_id,
                relation=VersionRelation.JOURNAL_EXTENSION_OF,
                evidence_urls=(journal.source_observation.evidence_url,),
                evidence_kind=LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
            ),
        ),
    )

    assert family.paper_id.startswith("paper:doi-")
    assert tuple(item.version_id for item in family.versions) == (
        "version:containment-arxiv",
        "version:containment-icdt",
        "version:containment-journal",
    )
    assert {item.relation for item in family.lineage} == {
        VersionRelation.PREPRINT_OF,
        VersionRelation.JOURNAL_EXTENSION_OF,
    }


def test_unrelated_similar_titles_do_not_merge_without_lineage_evidence() -> None:
    metadata = verify_metadata((source(),))

    with pytest.raises(ValueError, match="connected"):
        resolve_version_family(
            metadata,
            (
                version("version:containment-a", VersionKind.PREPRINT),
                version("version:containment-b", VersionKind.CONFERENCE, title="A Frontier for Query Containment (Survey)"),
            ),
        )


def test_rejects_duplicate_versions_and_cycles() -> None:
    metadata = verify_metadata((source(),))
    first = version("version:containment-a", VersionKind.PREPRINT)
    second = version("version:containment-b", VersionKind.CONFERENCE)

    with pytest.raises(ValueError, match="duplicate"):
        resolve_version_family(metadata, (first, first))

    duplicate_url = VersionObservation(
        version_id="version:containment-a-copy",
        kind=VersionKind.PREPRINT,
        source_observation=source(),
        version_url=first.version_url,
    )
    with pytest.raises(ValueError, match="duplicate"):
        resolve_version_family(metadata, (first, duplicate_url))

    cycle = (
        VersionLineage(
            first.version_id,
            second.version_id,
            VersionRelation.PREPRINT_OF,
            (first.source_observation.evidence_url,),
            LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
        ),
        VersionLineage(
            second.version_id,
            first.version_id,
            VersionRelation.CONFERENCE_OF,
            (second.source_observation.evidence_url,),
            LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        resolve_version_family(metadata, (first, second), cycle)


def test_family_requires_a_metadata_anchor_and_connects_every_version_to_it() -> None:
    metadata = verify_metadata((source(),))
    unrelated = version(
        "version:unrelated",
        VersionKind.PREPRINT,
        source_observation=source("An Unrelated Result", authors=("Other Author",), doi="10.1000/other"),
    )
    with pytest.raises(ValueError, match="anchor"):
        resolve_version_family(metadata, (unrelated,))

    anchor = version("version:anchor", VersionKind.PREPRINT)
    disconnected = version(
        "version:disconnected",
        VersionKind.CONFERENCE,
        source_observation=source(
            evidence_url="https://evidence.example/disconnected",
            official_url="https://publisher.example/disconnected",
        ),
    )
    with pytest.raises(ValueError, match="connected"):
        resolve_version_family(metadata, (anchor, disconnected))


def test_explicit_edge_cannot_link_an_unrelated_version_without_identity_evidence() -> None:
    metadata = verify_metadata((source(),))
    anchor = version("version:anchor", VersionKind.PREPRINT)
    unrelated = version(
        "version:unrelated",
        VersionKind.CONFERENCE,
        source_observation=source("An Unrelated Result", authors=("Other Author",), doi="10.1000/other"),
    )
    edge = VersionLineage(
        anchor.version_id,
        unrelated.version_id,
        VersionRelation.PREPRINT_OF,
        (anchor.source_observation.evidence_url,),
        LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
    )

    with pytest.raises(ValueError, match="identity evidence"):
        resolve_version_family(metadata, (anchor, unrelated), (edge,))


def test_explicit_extension_statement_can_connect_a_title_variant_only_from_an_endpoint() -> None:
    metadata = verify_metadata((source(),))
    preprint = version("version:anchor", VersionKind.PREPRINT)
    journal = version(
        "version:journal-extension",
        VersionKind.JOURNAL,
        source_observation=source(
            "A Frontier for Query Containment: Extended Version",
            evidence_url="https://evidence.example/extension-statement",
            official_url="https://publisher.example/extension",
        ),
    )
    statement = VersionLineage(
        preprint.version_id,
        journal.version_id,
        VersionRelation.JOURNAL_EXTENSION_OF,
        (journal.source_observation.evidence_url,),
        LineageEvidenceKind.EXPLICIT_VERSION_STATEMENT,
    )

    assert len(resolve_version_family(metadata, (preprint, journal), (statement,)).versions) == 2

    unattached = VersionLineage(
        preprint.version_id,
        journal.version_id,
        VersionRelation.JOURNAL_EXTENSION_OF,
        ("https://evidence.example/not-an-endpoint",),
        LineageEvidenceKind.EXPLICIT_VERSION_STATEMENT,
    )
    with pytest.raises(ValueError, match="attached"):
        resolve_version_family(metadata, (preprint, journal), (unattached,))


def test_url_comparison_normalizes_host_but_preserves_path_case() -> None:
    metadata = verify_metadata((source(),))
    upper_path = version("version:upper-path", VersionKind.PREPRINT, version_url="HTTPS://VERSIONS.EXAMPLE:443/Paper")
    same_url = version("version:same-url", VersionKind.CONFERENCE, version_url="https://versions.example/Paper")
    with pytest.raises(ValueError, match="duplicate"):
        resolve_version_family(metadata, (upper_path, same_url))

    lower_path = version("version:lower-path", VersionKind.CONFERENCE, version_url="https://versions.example/paper")
    lineage = VersionLineage(
        upper_path.version_id,
        lower_path.version_id,
        VersionRelation.PREPRINT_OF,
        (upper_path.source_observation.evidence_url,),
        LineageEvidenceKind.HIGH_CONFIDENCE_METADATA,
    )
    assert tuple(item.version_id for item in resolve_version_family(metadata, (upper_path, lower_path), (lineage,)).versions) == (
        "version:lower-path",
        "version:upper-path",
    )
