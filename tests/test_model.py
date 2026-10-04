from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from db_theory_atlas.model import (
    EdgeDirection,
    EdgeStrength,
    EvidencePointer,
    FullTextStatus,
    GraphEdge,
    OpenProblemRecord,
    OpenStatus,
    PaperRecord,
    PaperVersion,
    ReadDepth,
    TheoremRecord,
)
from db_theory_atlas.serialization import scientific_hash
from claim_fixtures import default_result, default_scope, default_technique_signature, theorem_claim
from db_theory_atlas.theorems import claim_for_theorem


def pointer(*, paper_id: str = "paper:query-containment-2024", version_id: str = "version:query-containment-v1") -> EvidencePointer:
    return EvidencePointer(
        paper_id=paper_id,
        version_id=version_id,
        page=7,
        heading=None,
        evidence_type="theorem",
        paraphrase="The result holds for the stated fragment.",
        source_hash="a" * 64,
        verified=True,
        claim=theorem_claim(),
    )


def paper(
    *,
    read_depth: ReadDepth = ReadDepth.DEEP_READ,
    full_text_status: FullTextStatus = FullTextStatus.AVAILABLE,
    title: str = "Query containment frontier",
    authors: tuple[str, ...] = ("Ada Author", "Bert Author"),
) -> PaperRecord:
    paper_id = "paper:query-containment-2024"
    version = PaperVersion(
        version_id="version:query-containment-v1",
        paper_id=paper_id,
        label="conference",
        url="https://example.org/paper.pdf",
        full_text_status=full_text_status,
        source_hash="b" * 64,
    )
    return PaperRecord(
        paper_id=paper_id,
        title=title,
        authors=authors,
        year=2024,
        venue="ICDT",
        doi="HTTPS://DOI.ORG/10.1000/ABC.Def",
        official_url="https://example.org/landing",
        preprint_url=None,
        versions=(version,),
        full_text_status=full_text_status,
        read_depth=read_depth,
        source_pointers=(pointer(),),
    )


def test_enum_values_are_the_controlled_vocabularies() -> None:
    assert [item.value for item in ReadDepth] == [
        "METADATA",
        "ABSTRACT",
        "INTRO_CONCLUSION",
        "FULL_SCAN",
        "DEEP_READ",
    ]


def test_structured_claim_payload_is_immutable_and_hash_bound() -> None:
    claim = theorem_claim()
    evidence = EvidencePointer(
        paper_id="paper:query-containment-2024",
        version_id="version:query-containment-v1",
        page=7,
        heading="Theorem 1",
        evidence_type="THEOREM",
        paraphrase="For the stated fragment, the theorem proves the result.",
        source_hash="a" * 64,
        verified=True,
        claim=claim,
    )

    with pytest.raises(TypeError):
        evidence.claim["claim_type"] = "OPEN_PROBLEM"
    changed_scope = replace(default_scope(), constraints=("relational instances",))
    changed = replace(evidence, claim=claim_for_theorem(
        changed_scope,
        (default_result(),),
        ("finite relational structures",),
        default_technique_signature(),
    ))
    assert scientific_hash(evidence) != scientific_hash(changed)


def test_theorem_and_open_problem_evidence_require_structured_claims() -> None:
    with pytest.raises(ValueError, match="structured claim"):
        EvidencePointer(
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            page=7,
            heading="Theorem 1",
            evidence_type="THEOREM",
            paraphrase="For the stated fragment, the theorem proves the result.",
            source_hash="a" * 64,
            verified=True,
        )
    assert [item.value for item in OpenStatus] == [
        "OPEN_VERIFIED",
        "PARTIALLY_RESOLVED",
        "RESOLVED",
        "LIKELY_OPEN",
        "UNKNOWN",
    ]


def test_paper_normalizes_doi_and_preserves_ordered_authors() -> None:
    record = paper()

    assert record.doi == "10.1000/abc.def"
    assert record.authors == ("Ada Author", "Bert Author")
    with pytest.raises(FrozenInstanceError):
        record.title = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("paper_id", "doi:10.1000/example"),
        ("authors", ()),
        ("authors", ["Ada Author"]),
        ("year", 1800),
        ("official_url", "file:///C:/private/paper.pdf"),
    ],
)
def test_paper_rejects_noncanonical_or_unsupported_metadata(field: str, value: object) -> None:
    values = {
        "paper_id": "paper:query-containment-2024",
        "title": "Query containment frontier",
        "authors": ("Ada Author",),
        "year": 2024,
        "venue": "ICDT",
        "doi": None,
        "official_url": "https://example.org/landing",
        "preprint_url": None,
        "versions": (),
        "full_text_status": FullTextStatus.METADATA_ONLY,
        "read_depth": ReadDepth.METADATA,
        "source_pointers": (),
    }
    values[field] = value

    with pytest.raises(ValueError):
        PaperRecord(**values)  # type: ignore[arg-type]


def test_paper_rejects_shallow_fulltext_incompatibility_and_foreign_pointer() -> None:
    with pytest.raises(ValueError, match="full text"):
        paper(read_depth=ReadDepth.ABSTRACT, full_text_status=FullTextStatus.METADATA_ONLY)

    foreign = pointer(paper_id="paper:other-2024")
    with pytest.raises(ValueError, match="pointer"):
        PaperRecord(
            paper_id="paper:query-containment-2024",
            title="Query containment frontier",
            authors=("Ada Author",),
            year=2024,
            venue=None,
            doi=None,
            official_url=None,
            preprint_url=None,
            versions=(),
            full_text_status=FullTextStatus.METADATA_ONLY,
            read_depth=ReadDepth.METADATA,
            source_pointers=(foreign,),
        )


def test_paper_pointer_requires_a_registered_matching_version_even_when_versions_are_empty() -> None:
    with pytest.raises(ValueError, match="registered version"):
        PaperRecord(
            paper_id="paper:query-containment-2024",
            title="Query containment frontier",
            authors=("Ada Author",),
            year=2024,
            venue=None,
            doi=None,
            official_url=None,
            preprint_url=None,
            versions=(),
            full_text_status=FullTextStatus.METADATA_ONLY,
            read_depth=ReadDepth.METADATA,
            source_pointers=(pointer(),),
        )


def test_aggregate_full_text_status_requires_an_available_version() -> None:
    metadata_version = PaperVersion(
        version_id="version:query-containment-v1",
        paper_id="paper:query-containment-2024",
        label="metadata",
        url="https://example.org/landing",
        full_text_status=FullTextStatus.METADATA_ONLY,
        source_hash=None,
    )

    with pytest.raises(ValueError, match="available version"):
        PaperRecord(
            paper_id="paper:query-containment-2024",
            title="Query containment frontier",
            authors=("Ada Author",),
            year=2024,
            venue=None,
            doi=None,
            official_url=None,
            preprint_url=None,
            versions=(metadata_version,),
            full_text_status=FullTextStatus.AVAILABLE,
            read_depth=ReadDepth.DEEP_READ,
            source_pointers=(pointer(),),
        )


@pytest.mark.parametrize("url", [None, "", "doi:10.1000/example", "file:///C:/private/paper.pdf"])
def test_paper_version_requires_a_nonempty_http_url(url: object) -> None:
    with pytest.raises(ValueError, match="url"):
        PaperVersion(
            version_id="version:query-containment-v1",
            paper_id="paper:query-containment-2024",
            label="conference",
            url=url,  # type: ignore[arg-type]
            full_text_status=FullTextStatus.METADATA_ONLY,
            source_hash=None,
        )


def test_evidence_pointer_requires_paper_version_and_location() -> None:
    with pytest.raises(ValueError, match="location"):
        EvidencePointer(
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            page=None,
            heading=None,
            evidence_type="theorem",
            paraphrase="A concise paraphrase.",
            source_hash="a" * 64,
            verified=True,
        )


def test_evidence_pointer_requires_a_source_hash_without_attribute_error() -> None:
    with pytest.raises(ValueError, match="source_hash"):
        EvidencePointer(
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            page=7,
            heading=None,
            evidence_type="theorem",
            paraphrase="A concise paraphrase.",
            source_hash=None,  # type: ignore[arg-type]
            verified=True,
        )


@pytest.mark.parametrize(
    "path",
    [
        r"C:\private\paper.pdf",
        "Cached copy: C:/private/paper.pdf",
        r"Cached copy: \\server\share\paper.pdf",
        "/tmp/paper.pdf",
        "Cached copy: /home/alice/paper.pdf",
        "/data",
        "Working directory: /workspace",
        "Account root: /Users",
        "/project",
        "Cache root: /cache",
        "Corpus root: /papers",
        "Custom root: /custom-root",
        "Unicode root: /数据",
        "Network cache: //server/share/paper.pdf",
        "Retrieved from file:///tmp/paper.pdf",
        "Retrieved from file:///C:/private/paper.pdf",
    ],
)
def test_paper_rejects_absolute_local_path_in_textual_fields(path: str) -> None:
    with pytest.raises(ValueError, match="absolute local path"):
        paper(title=path)


@pytest.mark.parametrize(
    "text",
    [
        "A / B dichotomy",
        "The ratio n/m is bounded.",
        "https://doi.org/10.1000/query.containment",
        "10.1000/query/containment",
        r"The proof uses \\alpha and \\frac{n}{m}.",
        "The quotient x/y is finite.",
        "A mathematical / operator is not a path.",
        "https://example.org/A/B",
        "α/β reduction",
        "集合/商 semantics",
        "查询/包含 problem",
        "Mixed 查询/containment notation",
    ],
)
def test_paper_accepts_scientific_prose_that_is_not_a_local_path(text: str) -> None:
    assert paper(title=text).title == text


def test_paper_validates_each_author_as_text_and_accepts_normal_names() -> None:
    accepted = ("A.-B. O'Connor", "Émilie du Châtelet", "李明")
    assert paper(authors=accepted).authors == accepted

    with pytest.raises(ValueError, match="absolute local path"):
        paper(authors=("Ada Author", r"C:\private\author.txt"))


def test_complete_theorem_requires_deep_read_and_evidence() -> None:
    with pytest.raises(ValueError, match="DEEP_READ"):
        TheoremRecord(
            theorem_id="theorem:containment-bound",
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            paraphrase="Containment has the stated lower bound.",
            complete=True,
            read_depth=ReadDepth.FULL_SCAN,
            evidence_pointers=(pointer(),),
        )

    with pytest.raises(ValueError, match="evidence"):
        TheoremRecord(
            theorem_id="theorem:containment-bound",
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            paraphrase="Containment has the stated lower bound.",
            complete=True,
            read_depth=ReadDepth.DEEP_READ,
            evidence_pointers=(),
        )


def test_promoted_problem_and_resolution_require_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        OpenProblemRecord(
            problem_id="problem:containment-open-case",
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            paraphrase="Determine containment for the remaining case.",
            status=OpenStatus.LIKELY_OPEN,
            evidence_pointers=(),
        )

    with pytest.raises(ValueError, match="resolution"):
        OpenProblemRecord(
            problem_id="problem:containment-open-case",
            paper_id="paper:query-containment-2024",
            version_id="version:query-containment-v1",
            paraphrase="Determine containment for the remaining case.",
            status=OpenStatus.RESOLVED,
            evidence_pointers=(pointer(),),
        )


def test_strong_graph_edges_require_valid_relation_direction_and_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        GraphEdge(
            source_id="problem:containment-open-case",
            target_id="paper:solution-2025",
            relation="solves",
            direction=EdgeDirection.DIRECTED,
            strength=EdgeStrength.STRONG,
            evidence_pointers=(),
        )

    with pytest.raises(ValueError, match="relation"):
        GraphEdge(
            source_id="paper:query-containment-2024",
            target_id="paper:solution-2025",
            relation="cooccurs",
            direction=EdgeDirection.DIRECTED,
            strength=EdgeStrength.WEAK,
            evidence_pointers=(pointer(),),
        )
