from __future__ import annotations

from dataclasses import dataclass
import math

import pytest

from db_theory_atlas.model import EvidencePointer, ReadDepth
from db_theory_atlas.serialization import canonical_json, freeze_json, scientific_hash
from claim_fixtures import open_problem_claim


@dataclass(frozen=True)
class Envelope:
    value: object


@dataclass
class MutableEnvelope:
    value: object


def test_canonical_json_tags_tuples_enums_and_dataclasses_deterministically() -> None:
    pointer = EvidencePointer(
        paper_id="paper:query-containment-2024",
        version_id="version:query-containment-v1",
        page=None,
        heading="Conclusion",
        evidence_type="open_problem",
        paraphrase="The remaining case is stated as open.",
        source_hash="a" * 64,
        verified=True,
        claim=open_problem_claim(),
    )

    first = canonical_json({"b": (ReadDepth.DEEP_READ, pointer), "a": 1})
    second = canonical_json({"a": 1, "b": (ReadDepth.DEEP_READ, pointer)})

    assert first == second
    assert '"$tuple"' in first
    assert '"$enum"' in first
    assert '"$dataclass"' in first
    assert scientific_hash({"a": 1, "b": (ReadDepth.DEEP_READ, pointer)}) == scientific_hash(
        {"b": (ReadDepth.DEEP_READ, pointer), "a": 1}
    )


def test_freeze_json_recursively_makes_scientific_payload_immutable() -> None:
    payload = freeze_json({"metadata": ["ICDT", {"year": 2024}]})

    assert payload["metadata"][1]["year"] == 2024
    with pytest.raises(TypeError):
        payload["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        payload["metadata"][1]["year"] = 2025  # type: ignore[index]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {"bad": {1, 2}}])
def test_canonical_json_rejects_nonfinite_and_unsupported_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json(value)


@pytest.mark.parametrize("path", ["C:/private/paper.pdf", "/tmp/paper.pdf", "file:///C:/private/paper.pdf"])
def test_scientific_payload_rejects_absolute_local_paths(path: str) -> None:
    with pytest.raises(ValueError, match="absolute local path"):
        freeze_json({"local_path": path})


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
def test_scientific_hash_recursively_rejects_paths_inside_dataclasses_enums_mappings_and_tuples(path: str) -> None:
    payload = Envelope(value=(ReadDepth.DEEP_READ, {"source": path}))

    with pytest.raises(ValueError, match="absolute local path"):
        scientific_hash(payload)


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
def test_freeze_json_accepts_nonpath_scientific_prose(text: str) -> None:
    assert freeze_json({"note": text})["note"] == text


def test_freeze_json_snapshots_dataclasses_before_hashing() -> None:
    source = MutableEnvelope({"nested": ["original"]})
    frozen = freeze_json(source)
    snapshot_hash = scientific_hash(frozen)

    source.value["nested"].append("changed")  # type: ignore[index]

    assert frozen is not source
    assert scientific_hash(frozen) == snapshot_hash
    assert '"$dataclass"' in canonical_json(frozen)
    with pytest.raises(TypeError):
        frozen["$dataclass"]["fields"]["new"] = "value"  # type: ignore[index]


def test_scientific_hash_is_path_independent_by_schema_design() -> None:
    scientific_payload = {
        "paper_id": "paper:query-containment-2024",
        "authors": ("Ada Author",),
        "year": 2024,
    }

    assert scientific_hash(scientific_payload) == scientific_hash(dict(reversed(tuple(scientific_payload.items()))))
