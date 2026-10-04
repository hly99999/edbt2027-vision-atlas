"""Frozen Task 4 record contracts and deterministic source-map construction.

This module deliberately creates no theorem claims.  It only defines the
schemas later extraction work must satisfy and binds each eligible source to
the exact Task 3 PDF bytes from which any future claim may be inspected.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Mapping

from pypdf import PdfReader

from .fulltext_reading import _heading


READING_NORMALIZATION = "PYPDF_PAGE_TEXT_NUL_TO_SPACE_JOIN_LF_V1"
FROZEN_DEEP_READ_COUNT = 80
FROZEN_TASK3_CLOSURE_SHA256 = "b2a89d4682e7ab6a6cf223dfb6a29c08289c5971482c8b0f6f5ae7a3298cc35f"
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_LABEL = re.compile(
    r"(?im)^\s*(?:▶\s*)?((?:Theorem|Lemma|Proposition|Corollary)\s+(?:[A-Za-z]+\.)?\d+(?:\.\d+)*(?:\s*\([^\n)]*\))?)"
)
_AMBIGUOUS_HEADING_CANDIDATE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*)\s+\S")
_OBVIOUS_NUMBERED_NONHEADING = re.compile(r"(?:\bsuch that\b|\bfor all\b|\b(?:is|are|was|were|has|have|that|which)\b|[=<>≤≥∈∀∃∧∨{}\[\]()]|·\s*·|[.,;]\s*$)", re.I)
_PAGE_BLOCK_CACHE: dict[tuple[str, int], tuple["PageTextBlock", ...]] = {}
_FROZEN_CORPUS_ISSUER = object()
_BUILD_CORPUS_ATTESTATION = object()
_TEST_CORPUS_ATTESTATION = object()
_VERIFIED_FROZEN_CORPORA: dict[int, object] = {}


class ScopeValue(str, Enum):
    """Explicit source-scope sentinels; blanks are never an allowed scope."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_STATED_IN_SOURCE = "NOT_STATED_IN_SOURCE"


class ParameterRole(str, Enum):
    FIXED = "FIXED"
    INPUT = "INPUT"
    PARAMETER = "PARAMETER"


class TheoremRole(str, Enum):
    MAIN = "MAIN"
    SUPPORTING = "SUPPORTING"
    COROLLARY = "COROLLARY"
    DEFINITIONAL = "DEFINITIONAL"


class TheoremResultType(str, Enum):
    UPPER_BOUND = "UPPER_BOUND"
    LOWER_BOUND = "LOWER_BOUND"
    DICHOTOMY = "DICHOTOMY"
    EQUIVALENCE = "EQUIVALENCE"
    ALGORITHM = "ALGORITHM"
    ENUMERATION = "ENUMERATION"
    STRUCTURAL = "STRUCTURAL"


class TheoremClaimForm(str, Enum):
    """Controlled source-stated semantic form for a theorem result."""

    ALGORITHMIC = "ALGORITHMIC"
    CHARACTERIZATION = "CHARACTERIZATION"
    BOUND = "BOUND"
    HARDNESS = "HARDNESS"
    OTHER_SOURCE_STATED = "OTHER_SOURCE_STATED"


class ComplexityMeasure(str, Enum):
    DATA_COMPLEXITY = "DATA_COMPLEXITY"
    COMBINED_COMPLEXITY = "COMBINED_COMPLEXITY"
    QUERY_COMPLEXITY = "QUERY_COMPLEXITY"
    PARAMETERIZED_COMPLEXITY = "PARAMETERIZED_COMPLEXITY"
    PREPROCESSING = "PREPROCESSING"
    QUERY_TIME = "QUERY_TIME"
    DELAY = "DELAY"
    TOTAL_TIME = "TOTAL_TIME"


class ProofTechniqueKind(str, Enum):
    REDUCTION = "REDUCTION"
    INDUCTION = "INDUCTION"
    DYNAMIC_PROGRAMMING = "DYNAMIC_PROGRAMMING"
    DECOMPOSITION = "DECOMPOSITION"
    HOMOMORPHISM = "HOMOMORPHISM"
    AUTOMATA = "AUTOMATA"
    COUNTING = "COUNTING"
    CONSTRUCTION = "CONSTRUCTION"
    COMPACTNESS = "COMPACTNESS"
    AMALGAMATION = "AMALGAMATION"
    NUMBER_THEORY = "NUMBER_THEORY"
    PARTITIONING = "PARTITIONING"
    OTHER_SOURCE_STATED = "OTHER_SOURCE_STATED"


class ProofTechniqueRole(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class TheoremRelationKind(str, Enum):
    GENERALIZES = "GENERALIZES"
    SPECIALIZES = "SPECIALIZES"
    STRENGTHENS = "STRENGTHENS"
    WEAKENS = "WEAKENS"
    MATCHES = "MATCHES"
    CLOSES_GAP = "CLOSES_GAP"
    USES = "USES"
    CONTRADICTS = "CONTRADICTS"
    INCOMPARABLE_WITH_EXPLANATION = "INCOMPARABLE_WITH_EXPLANATION"
    SUPERSEDED_BY_VERSION = "SUPERSEDED_BY_VERSION"


class CoverageDisposition(str, Enum):
    COMPLETE_THEOREM_EXTRACTION = "COMPLETE_THEOREM_EXTRACTION"
    NO_THEOREM_RECORD_WITH_REASON = "NO_THEOREM_RECORD_WITH_REASON"


class SourceConfidence(str, Enum):
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    SOURCE_LIMITED = "SOURCE_LIMITED"


class MutationDisposition(str, Enum):
    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty")
    return " ".join(value.split())


def _identifier(value: object, label: str) -> str:
    return _text(value, label)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value.casefold()


def _enum(value: object, kind: type[Enum], label: str):
    if isinstance(value, kind):
        return value
    try:
        return kind(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the controlled taxonomy") from caught


def _scope_value(value: object, label: str) -> str | ScopeValue:
    if isinstance(value, ScopeValue):
        return value
    if isinstance(value, str) and value in {item.value for item in ScopeValue}:
        return ScopeValue(value)
    return _text(value, label)


def _scope_tuple(value: object, label: str) -> tuple[str | ScopeValue, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{label} must be a nonempty immutable tuple")
    result = tuple(_scope_value(item, label) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} cannot contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ParameterRoleBinding:
    name: str
    role: ParameterRole

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "parameter name"))
        object.__setattr__(self, "role", _enum(self.role, ParameterRole, "parameter role"))


@dataclass(frozen=True, slots=True)
class ExactSourceLocation:
    page: int
    section: str | ScopeValue
    label: str | ScopeValue
    paper_id: str | None = None
    version_id: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1:
            raise ValueError("page must be a 1-based positive integer")
        object.__setattr__(self, "section", _scope_value(self.section, "section"))
        object.__setattr__(self, "label", _scope_value(self.label, "label"))
        if isinstance(self.section, ScopeValue) or isinstance(self.label, ScopeValue):
            raise ValueError("source locator section and label must be concrete source headings")
        identity = (self.paper_id, self.version_id, self.source_hash)
        if any(item is not None for item in identity):
            if not all(isinstance(item, str) for item in identity):
                raise ValueError("source identity must include paper_id, version_id, and source_hash")
            object.__setattr__(self, "paper_id", _identifier(self.paper_id, "paper_id"))
            object.__setattr__(self, "version_id", _identifier(self.version_id, "version_id"))
            object.__setattr__(self, "source_hash", _sha256(self.source_hash, "source_hash"))


@dataclass(frozen=True, slots=True)
class FormalProblemScope:
    """All complexity-scope axes that prevent result-scope laundering."""

    formal_problem: str
    parameter_roles: tuple[ParameterRoleBinding, ...]
    data_vs_combined: str | ScopeValue
    arity: str | ScopeValue
    boolean: str | ScopeValue
    query_fragment: str | ScopeValue
    semantics: str | ScopeValue
    domain: str | ScopeValue
    execution_mode: str | ScopeValue
    randomness: str | ScopeValue
    preprocessing: str | ScopeValue
    query_time: str | ScopeValue
    delay: str | ScopeValue
    total_time: str | ScopeValue
    assumptions: tuple[str | ScopeValue, ...] = ()
    communication_rounds: str | ScopeValue = ScopeValue.NOT_APPLICABLE
    load: str | ScopeValue = ScopeValue.NOT_APPLICABLE
    access_time: str | ScopeValue = ScopeValue.NOT_APPLICABLE

    def __post_init__(self) -> None:
        object.__setattr__(self, "formal_problem", _text(self.formal_problem, "formal_problem"))
        if not isinstance(self.parameter_roles, tuple) or not self.parameter_roles or any(
            not isinstance(item, ParameterRoleBinding) for item in self.parameter_roles
        ):
            raise ValueError("parameter_roles must be a nonempty immutable tuple of ParameterRoleBinding")
        names = tuple(item.name.casefold() for item in self.parameter_roles)
        if len(set(names)) != len(names):
            raise ValueError("parameter_roles cannot contain duplicate names")
        roles = {item.role for item in self.parameter_roles}
        if roles != {ParameterRole.FIXED, ParameterRole.INPUT, ParameterRole.PARAMETER}:
            raise ValueError("parameter_roles must identify FIXED, INPUT, and PARAMETER roles")
        for field in (
            "data_vs_combined", "arity", "boolean", "query_fragment", "semantics", "domain",
            "execution_mode", "randomness", "preprocessing", "query_time", "delay", "total_time",
            "communication_rounds", "load", "access_time",
        ):
            object.__setattr__(self, field, _scope_value(getattr(self, field), field))
        if not isinstance(self.assumptions, tuple):
            raise ValueError("assumptions must be an immutable tuple")
        normalized_assumptions = tuple(_scope_value(item, "assumption") for item in self.assumptions)
        if len(set(normalized_assumptions)) != len(normalized_assumptions):
            raise ValueError("assumptions cannot contain duplicates")
        object.__setattr__(self, "assumptions", normalized_assumptions)


@dataclass(frozen=True, slots=True)
class TheoremRecord:
    """A validation contract for a later source-bound theorem extraction."""

    theorem_id: str
    paper_id: str
    version_id: str
    source_hash: str
    source_location: ExactSourceLocation
    formal_scope: FormalProblemScope
    statement: str
    role: TheoremRole = TheoremRole.MAIN
    result_type: TheoremResultType | ScopeValue = ScopeValue.NOT_STATED_IN_SOURCE
    complexity_measure: ComplexityMeasure | ScopeValue = ScopeValue.NOT_STATED_IN_SOURCE
    version_family_id: str | None = None
    claim_form: TheoremClaimForm = TheoremClaimForm.OTHER_SOURCE_STATED

    def __post_init__(self) -> None:
        for field in ("theorem_id", "paper_id", "version_id", "statement"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        object.__setattr__(self, "source_hash", _sha256(self.source_hash, "source_hash"))
        object.__setattr__(self, "version_family_id", _identifier(
            self.paper_id if self.version_family_id is None else self.version_family_id, "version_family_id"
        ))
        if not isinstance(self.source_location, ExactSourceLocation):
            raise ValueError("source_location must be an ExactSourceLocation")
        if not isinstance(self.formal_scope, FormalProblemScope):
            raise ValueError("formal_scope must be a FormalProblemScope")
        object.__setattr__(self, "role", _enum(self.role, TheoremRole, "theorem role"))
        object.__setattr__(self, "claim_form", _enum(self.claim_form, TheoremClaimForm, "theorem claim form"))
        object.__setattr__(self, "result_type", _scope_value_or_enum(self.result_type, TheoremResultType, "result_type"))
        object.__setattr__(
            self, "complexity_measure", _scope_value_or_enum(self.complexity_measure, ComplexityMeasure, "complexity_measure")
        )


def _scope_value_or_enum(value: object, kind: type[Enum], label: str) -> Enum | ScopeValue:
    if isinstance(value, ScopeValue) or (isinstance(value, str) and value in {item.value for item in ScopeValue}):
        return _scope_value(value, label)
    return _enum(value, kind, label)


@dataclass(frozen=True, slots=True)
class ProofTechnique:
    technique: ProofTechniqueKind
    role: ProofTechniqueRole
    source_location: ExactSourceLocation
    evidence: str
    evidence_page: int
    evidence_start: int
    evidence_end: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "technique", _enum(self.technique, ProofTechniqueKind, "proof technique"))
        object.__setattr__(self, "role", _enum(self.role, ProofTechniqueRole, "proof technique role"))
        if not isinstance(self.source_location, ExactSourceLocation):
            raise ValueError("source_location must be an ExactSourceLocation")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("proof-technique evidence must be nonempty")
        if isinstance(self.evidence_page, bool) or not isinstance(self.evidence_page, int) or self.evidence_page < 1:
            raise ValueError("evidence_page must be a 1-based positive integer")
        if isinstance(self.evidence_start, bool) or not isinstance(self.evidence_start, int) or self.evidence_start < 0:
            raise ValueError("evidence_start must be a nonnegative integer")
        if isinstance(self.evidence_end, bool) or not isinstance(self.evidence_end, int) or self.evidence_end <= self.evidence_start:
            raise ValueError("evidence_end must be greater than evidence_start")


@dataclass(frozen=True, slots=True)
class TheoremRelation:
    relation: TheoremRelationKind
    source_theorem_id: str
    target_theorem_id: str
    scope_comparison: str | ScopeValue
    evidence_location: ExactSourceLocation

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation", _enum(self.relation, TheoremRelationKind, "theorem relation"))
        object.__setattr__(self, "source_theorem_id", _identifier(self.source_theorem_id, "source_theorem_id"))
        object.__setattr__(self, "target_theorem_id", _identifier(self.target_theorem_id, "target_theorem_id"))
        if self.source_theorem_id == self.target_theorem_id:
            raise ValueError("theorem relation requires distinct theorem IDs")
        object.__setattr__(self, "scope_comparison", _scope_value(self.scope_comparison, "scope_comparison"))
        if not isinstance(self.evidence_location, ExactSourceLocation):
            raise ValueError("evidence_location must be an ExactSourceLocation")


@dataclass(frozen=True, slots=True)
class ScopeAudit:
    theorem_id: str
    formal_scope: FormalProblemScope
    source_locations: tuple[ExactSourceLocation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "theorem_id", _identifier(self.theorem_id, "theorem_id"))
        if not isinstance(self.formal_scope, FormalProblemScope):
            raise ValueError("formal_scope must be a FormalProblemScope")
        if not isinstance(self.source_locations, tuple) or not self.source_locations or any(
            not isinstance(item, ExactSourceLocation) for item in self.source_locations
        ):
            raise ValueError("source_locations must be a nonempty immutable tuple of ExactSourceLocation")


@dataclass(frozen=True, slots=True)
class ExtractionCoverage:
    paper_id: str
    version_id: str
    source_hash: str
    disposition: CoverageDisposition
    reason: str | ScopeValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "paper_id", _identifier(self.paper_id, "paper_id"))
        object.__setattr__(self, "version_id", _identifier(self.version_id, "version_id"))
        object.__setattr__(self, "source_hash", _sha256(self.source_hash, "source_hash"))
        object.__setattr__(self, "disposition", _enum(self.disposition, CoverageDisposition, "coverage disposition"))
        object.__setattr__(self, "reason", _scope_value(self.reason, "coverage reason"))


@dataclass(frozen=True, slots=True)
class CollisionPrimitive:
    primitive_id: str
    label: str
    source_locations: tuple[ExactSourceLocation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "primitive_id", _identifier(self.primitive_id, "primitive_id"))
        object.__setattr__(self, "label", _text(self.label, "primitive label"))
        if not isinstance(self.source_locations, tuple) or not self.source_locations or any(
            not isinstance(item, ExactSourceLocation) for item in self.source_locations
        ):
            raise ValueError("source_locations must be a nonempty immutable tuple of ExactSourceLocation")


@dataclass(frozen=True, slots=True)
class MutationResult:
    mutation_id: str
    disposition: MutationDisposition
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mutation_id", _identifier(self.mutation_id, "mutation_id"))
        object.__setattr__(self, "disposition", _enum(self.disposition, MutationDisposition, "mutation disposition"))
        object.__setattr__(self, "reason", _text(self.reason, "mutation reason"))


def canonical_json(value: object) -> str:
    """Canonical plain JSON for Task 4 portable rows (sorted, compact UTF-8)."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _row_sha256(row: Mapping[str, object]) -> str:
    return canonical_sha256(dict(row))


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        raise ValueError(f"required Task 3 input is missing: {path}")
    rows: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as caught:
            raise ValueError(f"invalid JSONL at {path}:{number}") from caught
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row at {path}:{number} must be an object")
        rows.append(row)
    return tuple(rows)


def _task3_file_sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"frozen Task 3 bundle input is missing: {path}")
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _task3_reading_bundle_sha256(notes: Path, ledger: Path) -> str:
    if not notes.is_dir():
        raise ValueError(f"frozen Task 3 reading notes are missing: {notes}")
    if not ledger.is_file():
        raise ValueError(f"frozen Task 3 reading ledger is missing: {ledger}")
    digest = hashlib.sha256()
    files = sorted(path for path in notes.glob("*.md") if path.name != "README.md") + [ledger]
    for path in files:
        if not path.is_file():
            raise ValueError(f"frozen Task 3 reading bundle item is missing: {path}")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify_frozen_task3_closure(
    repository_root: Path | str,
    *,
    read_ledger_path: Path | str | None = None,
    manifests_path: Path | str | None = None,
    attempts_path: Path | str | None = None,
) -> Mapping[str, object]:
    """Verify that Task 4 reads exactly the frozen, Task-3-approved inputs."""

    root = Path(repository_root).resolve()
    closure_path = root / ".superpowers" / "sdd" / "corpus-task-3-closure-provenance.json"
    if not closure_path.is_file():
        raise ValueError(f"frozen Task 3 closure provenance is missing: {closure_path}")
    try:
        document = json.loads(closure_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as caught:
        raise ValueError("frozen Task 3 closure provenance is invalid JSON") from caught
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "closure_payload", "task3_closure_sha256"}:
        raise ValueError("frozen Task 3 closure provenance has an invalid schema")
    if document.get("schema_version") != "TASK3_CLOSURE_PROVENANCE_V1":
        raise ValueError("frozen Task 3 closure provenance schema version is not authorized")
    payload = document.get("closure_payload")
    claimed_hash = document.get("task3_closure_sha256")
    if not isinstance(payload, Mapping) or _sha256(claimed_hash, "task3_closure_sha256") != canonical_sha256(dict(payload)):
        raise ValueError("frozen Task 3 closure payload hash does not match its canonical payload")
    if claimed_hash != FROZEN_TASK3_CLOSURE_SHA256:
        raise ValueError("frozen Task 3 closure hash is not the authorized Task 3 closure")
    counts = payload.get("counts")
    if not isinstance(counts, Mapping) or counts.get("full_scan") != 125 or counts.get("deep_read") != 80:
        raise ValueError("frozen Task 3 closure does not establish FULL_SCAN=125 and DEEP_READ=80")
    if payload.get("gate_verdict") != "TASK3_FINAL_PASS":
        raise ValueError("frozen Task 3 closure verdict is not TASK3_FINAL_PASS")
    if payload.get("task4_authorized") is not True:
        raise ValueError("frozen Task 3 closure does not authorize Task 4")
    selected_path = Path(manifests_path) if manifests_path is not None else root / "literature/fulltext_manifests/acquisition_2026_08_30.jsonl"
    immutable_path = Path(attempts_path) if attempts_path is not None else root / "literature/fulltext_manifests/acquisition_attempts_2026_08_30.jsonl"
    ledger_path = Path(read_ledger_path) if read_ledger_path is not None else root / "literature/fulltext_ledgers/read_depth_2026_08_30.json"
    actual_hashes = {
        "selected_outcomes": _task3_file_sha256(selected_path),
        "immutable_attempts": _task3_file_sha256(immutable_path),
        "reading_notes_and_ledger": _task3_reading_bundle_sha256(root / "literature" / "fulltext_notes", ledger_path),
    }
    expected_hashes = payload.get("closure_bundle_hashes")
    if not isinstance(expected_hashes, Mapping) or dict(expected_hashes) != actual_hashes:
        raise ValueError("frozen Task 3 closure bundle hashes do not match the current inputs")
    return payload


def _portable_cache_path(value: object, root: Path) -> tuple[str, Path]:
    if not isinstance(value, str) or not value:
        raise ValueError("selected manifest cache_path is missing")
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("cache path must be repository-relative and cannot escape the cache")
    target = (root / raw).resolve()
    cache_root = (root / "literature" / "fulltext_cache").resolve()
    try:
        target.relative_to(cache_root)
    except ValueError as caught:
        raise ValueError("cache path escapes literature/fulltext_cache") from caught
    return value.replace("\\", "/"), target


@dataclass(frozen=True, slots=True)
class CacheBinding:
    cache_path: str
    byte_count: int
    expected_sha256: str
    actual_byte_count: int
    actual_sha256: str
    selected_manifest_attempt_id: str
    selected_manifest_sha256: str
    immutable_attempt_id: str
    immutable_attempt_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.cache_path, str) or not self.cache_path.strip() or Path(self.cache_path).is_absolute():
            raise ValueError("cache_path must be a nonempty repository-relative path")
        for field in ("byte_count", "actual_byte_count"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a nonnegative integer")
        for field in ("expected_sha256", "actual_sha256", "selected_manifest_sha256", "immutable_attempt_sha256"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        for field in ("selected_manifest_attempt_id", "immutable_attempt_id"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        if self.byte_count != self.actual_byte_count:
            raise ValueError("actual byte count does not match selected manifest")
        if self.expected_sha256 != self.actual_sha256:
            raise ValueError("actual SHA-256 does not match selected manifest")
        if self.selected_manifest_attempt_id != self.immutable_attempt_id:
            raise ValueError("selected manifest attempt identity does not match immutable attempt")

    def as_dict(self) -> dict[str, object]:
        return {
            "actual_byte_count": self.actual_byte_count,
            "actual_sha256": self.actual_sha256,
            "byte_count": self.byte_count,
            "cache_path": self.cache_path,
            "expected_sha256": self.expected_sha256,
            "immutable_attempt_id": self.immutable_attempt_id,
            "immutable_attempt_sha256": self.immutable_attempt_sha256,
            "selected_manifest_attempt_id": self.selected_manifest_attempt_id,
            "selected_manifest_sha256": self.selected_manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class StatementBlock:
    label: str
    offset: int
    section_heading: str | None

    def as_dict(self) -> dict[str, object]:
        return {"label": self.label, "offset": self.offset, "section_heading": self.section_heading}


@dataclass(frozen=True, slots=True)
class PageTextBlock:
    page: int
    normalized_text: str
    page_text_sha256: str
    section_headings: tuple[str, ...]
    theorem_labels: tuple[str, ...]
    carried_section_heading: str | None = None
    carried_section_from_page: int | None = None
    heading_offsets: tuple[tuple[str, int], ...] = ()
    statement_blocks: tuple[StatementBlock, ...] = ()
    ambiguous_heading_offsets: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1:
            raise ValueError("page block page must be a 1-based positive integer")
        if not isinstance(self.normalized_text, str) or "\x00" in self.normalized_text:
            raise ValueError("normalized page text must be text with NUL replaced by a space")
        actual = hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()
        object.__setattr__(self, "page_text_sha256", _sha256(self.page_text_sha256, "page_text_sha256"))
        if self.page_text_sha256 != actual:
            raise ValueError("page-text SHA-256 does not match normalized page text")
        for field in ("section_headings", "theorem_labels"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"{field} must be an immutable tuple of nonblank text")
            compact = tuple(" ".join(item.split()) for item in value)
            if len(set(compact)) != len(compact):
                raise ValueError(f"{field} cannot contain duplicate values")
            object.__setattr__(self, field, compact)
        carried = (self.carried_section_heading, self.carried_section_from_page)
        if carried == (None, None):
            return
        if not isinstance(self.carried_section_heading, str) or not self.carried_section_heading.strip():
            raise ValueError("carried section heading must be nonblank text")
        if (
            isinstance(self.carried_section_from_page, bool)
            or not isinstance(self.carried_section_from_page, int)
            or not 1 <= self.carried_section_from_page < self.page
        ):
            raise ValueError("carried section origin must be an earlier 1-based page")
        compact_heading = " ".join(self.carried_section_heading.split())
        if not self.section_headings or self.section_headings[0] != compact_heading:
            raise ValueError("a carried section must be the first page-block section heading")
        object.__setattr__(self, "carried_section_heading", compact_heading)

    def as_dict(self) -> dict[str, object]:
        return {
            "normalized_text": self.normalized_text,
            "page": self.page,
            "page_text_sha256": self.page_text_sha256,
            "carried_section_from_page": self.carried_section_from_page,
            "carried_section_heading": self.carried_section_heading,
            "section_headings": list(self.section_headings),
            "heading_offsets": [[heading, offset] for heading, offset in self.heading_offsets],
            "statement_blocks": [item.as_dict() for item in self.statement_blocks],
            "ambiguous_heading_offsets": list(self.ambiguous_heading_offsets),
            "theorem_labels": list(self.theorem_labels),
        }


@dataclass(frozen=True, slots=True)
class TheoremSourceMap:
    paper_id: str
    version_id: str
    source_hash: str
    cache_binding: CacheBinding
    page_count: int
    page_blocks: tuple[PageTextBlock, ...]
    source_tier: str = "OFFICIAL"

    def __post_init__(self) -> None:
        object.__setattr__(self, "paper_id", _identifier(self.paper_id, "paper_id"))
        object.__setattr__(self, "version_id", _identifier(self.version_id, "version_id"))
        object.__setattr__(self, "source_hash", _sha256(self.source_hash, "source_hash"))
        if not isinstance(self.cache_binding, CacheBinding):
            raise ValueError("cache_binding must be a CacheBinding")
        if self.source_hash != self.cache_binding.actual_sha256:
            raise ValueError("source_hash does not match actual cached PDF SHA-256")
        if isinstance(self.page_count, bool) or not isinstance(self.page_count, int) or self.page_count < 1:
            raise ValueError("page_count must be a positive integer")
        if not isinstance(self.page_blocks, tuple) or len(self.page_blocks) != self.page_count or any(
            not isinstance(item, PageTextBlock) for item in self.page_blocks
        ):
            raise ValueError("page_blocks must contain exactly one PageTextBlock for every page")
        pages = tuple(item.page for item in self.page_blocks)
        if pages != tuple(range(1, self.page_count + 1)):
            raise ValueError("page blocks must be ordered 1-based contiguous page locators")
        object.__setattr__(self, "source_tier", _text(self.source_tier, "source tier"))

    def as_dict(self) -> dict[str, object]:
        return {
            "cache_binding": self.cache_binding.as_dict(),
            "page_blocks": [item.as_dict() for item in self.page_blocks],
            "page_count": self.page_count,
            "paper_id": self.paper_id,
            "source_hash": self.source_hash,
            "source_tier": self.source_tier,
            "version_id": self.version_id,
        }


@dataclass(frozen=True, slots=True)
class CompleteTheoremSourceAuthorization:
    """Opaque capability proving a source belongs to the frozen Task 4 corpus."""

    paper_id: str
    version_id: str
    source_hash: str
    source_map_sha256: str
    closure_sha256: str
    source_map: TheoremSourceMap
    corpus: "FrozenTask4Corpus"
    _issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "paper_id", _identifier(self.paper_id, "paper_id"))
        object.__setattr__(self, "version_id", _identifier(self.version_id, "version_id"))
        for field_name in ("source_hash", "source_map_sha256", "closure_sha256"):
            object.__setattr__(self, field_name, _sha256(getattr(self, field_name), field_name))
        if not isinstance(self.source_map, TheoremSourceMap):
            raise ValueError("complete theorem source authorization requires a TheoremSourceMap")
        if self._issuer is not _FROZEN_CORPUS_ISSUER:
            raise ValueError("complete theorem source authorization was not issued by a frozen corpus")


@dataclass(frozen=True, slots=True)
class FrozenTask4Corpus:
    """The only issuer of complete-theorem source authorizations.

    Instances are created by :func:`build_frozen_task4_corpus`, after the
    Task 3 closure and all cache bindings have been independently checked.
    """

    source_maps: tuple[TheoremSourceMap, ...]
    closure_sha256: str
    _issuer: object = field(repr=False, compare=False)
    version_lineages: tuple[tuple[str, str, str, str], ...] = ()

    def __post_init__(self) -> None:
        if self._issuer not in {_BUILD_CORPUS_ATTESTATION, _TEST_CORPUS_ATTESTATION}:
            raise ValueError("FrozenTask4Corpus must be created by the frozen builder or explicit test fixture")
        object.__setattr__(self, "closure_sha256", _sha256(self.closure_sha256, "closure_sha256"))
        if self.closure_sha256 != FROZEN_TASK3_CLOSURE_SHA256:
            raise ValueError("FrozenTask4Corpus closure hash is not the Task 3 frozen closure")
        if not isinstance(self.source_maps, tuple) or len(self.source_maps) != FROZEN_DEEP_READ_COUNT or any(
            not isinstance(item, TheoremSourceMap) for item in self.source_maps
        ):
            raise ValueError("FrozenTask4Corpus requires exactly the frozen 80 source maps")
        canonical_source_maps_jsonl(self.source_maps)
        source_identities = {
            (item.paper_id, item.version_id, item.source_hash) for item in self.source_maps
        }
        lineages = self.version_lineages
        if not lineages:
            lineages = tuple((paper_id, version_id, source_hash, paper_id) for paper_id, version_id, source_hash in sorted(source_identities))
            object.__setattr__(self, "version_lineages", lineages)
        if not isinstance(lineages, tuple) or any(
            not isinstance(item, tuple) or len(item) != 4 or not all(isinstance(value, str) and value.strip() for value in item)
            for item in lineages
        ):
            raise ValueError("version_lineages must be immutable canonical source identities")
        if len(lineages) != len(source_identities) or {
            (paper_id, version_id, source_hash) for paper_id, version_id, source_hash, _ in lineages
        } != source_identities:
            raise ValueError("version_lineages must cover every frozen source exactly once")
        if len({(paper_id, version_id, source_hash) for paper_id, version_id, source_hash, _ in lineages}) != len(lineages):
            raise ValueError("version_lineages cannot duplicate source identities")
        object.__setattr__(self, "version_lineages", tuple(
            (paper_id, version_id, source_hash, _text(lineage_id, "version lineage id"))
            for paper_id, version_id, source_hash, lineage_id in lineages
        ))

    def version_family_id(self, identity: tuple[str, str, str]) -> str:
        for paper_id, version_id, source_hash, lineage_id in self.version_lineages:
            if (paper_id, version_id, source_hash) == identity:
                return lineage_id
        raise ValueError("source identity is absent from the frozen version-lineage registry")

    def authorize(self, source_map: TheoremSourceMap) -> CompleteTheoremSourceAuthorization:
        if not isinstance(source_map, TheoremSourceMap):
            raise ValueError("complete theorem source authorization requires a TheoremSourceMap")
        identity = (source_map.paper_id, source_map.version_id, source_map.source_hash)
        found = next(
            (item for item in self.source_maps if (item.paper_id, item.version_id, item.source_hash) == identity),
            None,
        )
        if found is None or canonical_json(found.as_dict()) != canonical_json(source_map.as_dict()):
            raise ValueError("source map is not a member of this frozen corpus")
        return CompleteTheoremSourceAuthorization(
            *identity,
            canonical_sha256(source_map.as_dict()),
            self.closure_sha256,
            source_map,
            self,
            _FROZEN_CORPUS_ISSUER,
        )

    @classmethod
    def for_test(
        cls, source_maps: tuple[TheoremSourceMap, ...], closure_sha256: str,
        version_lineages: tuple[tuple[str, str, str, str], ...] = (),
    ) -> "FrozenTask4Corpus":
        """Create an explicitly test-only corpus; production context rejects it."""

        return cls(source_maps, closure_sha256, _TEST_CORPUS_ATTESTATION, version_lineages)


def is_verified_frozen_task4_corpus(value: object) -> bool:
    return isinstance(value, FrozenTask4Corpus) and _VERIFIED_FROZEN_CORPORA.get(id(value)) is value


def is_test_frozen_task4_corpus(value: object) -> bool:
    return isinstance(value, FrozenTask4Corpus) and value._issuer is _TEST_CORPUS_ATTESTATION


def validate_complete_theorem_source(
    record: TheoremRecord | TheoremSourceMap | Mapping[str, object],
    authorization: CompleteTheoremSourceAuthorization | None = None,
) -> CompleteTheoremSourceAuthorization:
    """Authorize a later complete-theorem record only via a frozen capability.

    A self-declared ledger-like mapping is deliberately insufficient: callers
    must pass the capability issued for the exact map by a
    :class:`FrozenTask4Corpus`.
    """

    if not isinstance(authorization, CompleteTheoremSourceAuthorization):
        raise ValueError("complete theorem source requires frozen corpus authorization")
    if authorization._issuer is not _FROZEN_CORPUS_ISSUER:
        raise ValueError("complete theorem source authorization was not issued by a frozen corpus")
    if not isinstance(authorization.corpus, FrozenTask4Corpus) or authorization.corpus._issuer not in {
        _BUILD_CORPUS_ATTESTATION, _TEST_CORPUS_ATTESTATION,
    }:
        raise ValueError("complete theorem source authorization has no frozen corpus membership")
    if authorization.corpus._issuer is _BUILD_CORPUS_ATTESTATION and not is_verified_frozen_task4_corpus(authorization.corpus):
        raise ValueError("complete theorem source authorization has no verified frozen corpus attestation")
    if authorization.closure_sha256 != FROZEN_TASK3_CLOSURE_SHA256:
        raise ValueError("complete theorem source authorization has the wrong frozen closure")
    source_map = authorization.source_map
    identity = (authorization.paper_id, authorization.version_id, authorization.source_hash)
    if (source_map.paper_id, source_map.version_id, source_map.source_hash) != identity:
        raise ValueError("complete theorem source authorization source map identity is inconsistent")
    if authorization.source_map_sha256 != canonical_sha256(source_map.as_dict()):
        raise ValueError("complete theorem source authorization source map hash is inconsistent")
    if not any(
        (item.paper_id, item.version_id, item.source_hash) == identity
        and canonical_json(item.as_dict()) == canonical_json(source_map.as_dict())
        for item in authorization.corpus.source_maps
    ):
        raise ValueError("complete theorem source authorization source map is absent from the frozen corpus")
    if _source_identity(record) != identity:
        raise ValueError("complete theorem source does not match its frozen authorization")
    return authorization


def authorize_complete_theorem_source(
    corpus: FrozenTask4Corpus, source_map: TheoremSourceMap,
) -> CompleteTheoremSourceAuthorization:
    """Convenience entry point for later theorem validators."""

    if not isinstance(corpus, FrozenTask4Corpus):
        raise ValueError("complete theorem source authorization requires a FrozenTask4Corpus")
    return corpus.authorize(source_map)


def _index_unique(rows: Iterable[Mapping[str, object]], label: str) -> dict[tuple[str, str], Mapping[str, object]]:
    index: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in rows:
        paper_id, version_id = row.get("paper_id"), row.get("version_id")
        if not isinstance(paper_id, str) or not isinstance(version_id, str):
            raise ValueError(f"{label} row lacks paper_id/version_id")
        key = (paper_id, version_id)
        if key in index:
            raise ValueError(f"duplicate {label} paper/version identity: {key}")
        index[key] = row
    return index


def _attempt_index(rows: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        attempt_id = row.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("immutable attempt lacks attempt_id")
        if attempt_id in result:
            raise ValueError(f"duplicate immutable attempt identity: {attempt_id}")
        result[attempt_id] = row
    return result


def _record_deep_read(record: Mapping[str, object]) -> None:
    if record.get("read_depth") != "DEEP_READ":
        raise ValueError("FULL_SCAN-only or metadata-only record cannot be a complete theorem source")
    if record.get("shortfall_reason") is not None:
        raise ValueError("DEEP_READ source record cannot have a shortfall reason")
    if record.get("reading_extraction_normalization") != READING_NORMALIZATION:
        raise ValueError("DEEP_READ record does not use Task 3 reading normalization")


def _source_identity(value: object) -> tuple[str, str, str]:
    if isinstance(value, (TheoremRecord, TheoremSourceMap)):
        return value.paper_id, value.version_id, value.source_hash
    if not isinstance(value, Mapping):
        raise ValueError("complete theorem source must be a theorem record or source identity mapping")
    return (
        _identifier(value.get("paper_id"), "paper_id"),
        _identifier(value.get("version_id"), "version_id"),
        _sha256(value.get("source_hash"), "source_hash"),
    )


def _page_block(page: int, raw_text: str) -> PageTextBlock:
    normalized = raw_text.replace("\x00", " ")
    headings: list[str] = []
    heading_offsets: list[tuple[str, int]] = []
    ambiguous_offsets: list[int] = []
    offset = 0
    for line in normalized.splitlines(keepends=True):
        heading = _heading(line)
        if heading is not None and heading not in headings:
            headings.append(heading)
            heading_offsets.append((heading, offset))
        elif _AMBIGUOUS_HEADING_CANDIDATE.match(line) and not _OBVIOUS_NUMBERED_NONHEADING.search(line):
            ambiguous_offsets.append(offset)
        offset += len(line)
    labels: list[str] = []
    statements: list[StatementBlock] = []
    for match in _LABEL.finditer(normalized):
        label = " ".join(match.group(1).split())
        if label not in labels:
            labels.append(label)
            active = next((heading for heading, at in reversed(heading_offsets) if at < match.start()), None)
            statements.append(StatementBlock(label, match.start(), active))
    return PageTextBlock(
        page=page,
        normalized_text=normalized,
        page_text_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        section_headings=tuple(headings),
        theorem_labels=tuple(labels),
        heading_offsets=tuple(heading_offsets),
        statement_blocks=tuple(statements),
        ambiguous_heading_offsets=tuple(ambiguous_offsets),
    )


def _with_active_sections(page_blocks: tuple[PageTextBlock, ...]) -> tuple[PageTextBlock, ...]:
    """Carry one source-page-provenanced active section onto theorem-only pages.

    Page-local headings take precedence from the line where they occur and reset
    the active section; when several occur, the last one in extracted reading
    order is active at the page boundary.  A theorem before the first local
    heading retains the prior active section, while a theorem after a local
    heading does not.  A page inherits nothing without an earlier unambiguous
    active section.
    """

    active_heading: str | None = None
    active_page: int | None = None
    enriched: list[PageTextBlock] = []
    for block in page_blocks:
        prior_heading, prior_page = active_heading, active_page
        ambiguous_events = [(offset, None) for offset in block.ambiguous_heading_offsets]
        events = sorted(
            [(offset, heading) for heading, offset in block.heading_offsets] + ambiguous_events,
            key=lambda item: item[0],
        )
        statement_blocks = []
        for item in block.statement_blocks:
            section = prior_heading
            for event_offset, event_heading in events:
                if event_offset >= item.offset:
                    break
                section = event_heading
            statement_blocks.append(replace(item, section_heading=section))
        needs_prior = prior_heading is not None and prior_page is not None and any(
            item.section_heading == prior_heading for item in statement_blocks
        )
        local_headings = tuple(heading for heading in block.section_headings if heading != prior_heading)
        block = replace(
            block,
            section_headings=((prior_heading, *local_headings) if needs_prior else local_headings),
            carried_section_heading=prior_heading if needs_prior else None,
            carried_section_from_page=prior_page if needs_prior else None,
            statement_blocks=tuple(statement_blocks),
        )
        enriched.append(block)
        if events:
            active_heading = events[-1][1]
            active_page = block.page if active_heading is not None else None
    return tuple(enriched)


def _build_one(
    record: Mapping[str, object], manifest: Mapping[str, object], attempt: Mapping[str, object], root: Path,
) -> TheoremSourceMap:
    _record_deep_read(record)
    paper_id, version_id = str(record["paper_id"]), str(record["version_id"])
    source_hash = _sha256(record.get("source_hash"), "ledger source_hash")
    for label, row in (("selected manifest", manifest), ("immutable attempt", attempt)):
        if (row.get("paper_id"), row.get("version_id")) != (paper_id, version_id):
            raise ValueError(f"{label} paper/version identity does not match DEEP_READ ledger")
        if row.get("status") != "VALID_PDF":
            raise ValueError(f"{label} is not a VALID_PDF")
        if _sha256(row.get("content_sha256"), f"{label} content_sha256") != source_hash:
            raise ValueError(f"{label} source hash does not match DEEP_READ ledger")
    if dict(manifest) != dict(attempt):
        raise ValueError("selected manifest does not exactly bind its immutable attempt")
    attempt_id = manifest.get("attempt_id")
    if not isinstance(attempt_id, str) or attempt_id != attempt.get("attempt_id"):
        raise ValueError("selected manifest attempt identity does not match immutable attempt")
    byte_count = manifest.get("byte_count")
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 1:
        raise ValueError("selected manifest byte_count is invalid")
    cache_path, cache = _portable_cache_path(manifest.get("cache_path"), root)
    if not cache.is_file():
        raise ValueError(f"selected cache PDF is missing: {cache_path}")
    payload = cache.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    binding = CacheBinding(
        cache_path=cache_path,
        byte_count=byte_count,
        expected_sha256=source_hash,
        actual_byte_count=len(payload),
        actual_sha256=actual_sha256,
        selected_manifest_attempt_id=attempt_id,
        selected_manifest_sha256=_row_sha256(manifest),
        immutable_attempt_id=str(attempt["attempt_id"]),
        immutable_attempt_sha256=_row_sha256(attempt),
    )
    cache_key = (actual_sha256, len(payload))
    page_blocks = _PAGE_BLOCK_CACHE.get(cache_key)
    if page_blocks is None:
        try:
            reader = PdfReader(BytesIO(payload), strict=True)
            pages = tuple(page.extract_text() or "" for page in reader.pages)
        except Exception as caught:  # pypdf parser failures are always fail-closed source failures.
            raise ValueError(f"cached PDF extraction failed for {paper_id}: {type(caught).__name__}") from caught
        if not pages or not any(item.strip() for item in pages):
            raise ValueError(f"cached PDF has no extractable page text for {paper_id}")
        page_blocks = _with_active_sections(tuple(
            _page_block(number, page) for number, page in enumerate(pages, 1)
        ))
        _PAGE_BLOCK_CACHE[cache_key] = page_blocks
    expected_pages = manifest.get("page_count")
    if expected_pages != len(page_blocks) or record.get("page_count") != len(page_blocks):
        raise ValueError("cached PDF page count does not match selected manifest/ledger")
    combined = "\n".join(item.normalized_text for item in page_blocks)
    combined_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    if record.get("reading_extraction_sha256") != combined_hash or manifest.get("reading_extraction_sha256") != combined_hash:
        raise ValueError("Task 3 reading extraction SHA-256 does not match cached PDF pages")
    source_url = str(manifest.get("source_url", "")).casefold()
    source_tier = "ARXIV" if "arxiv.org" in source_url else "OFFICIAL"
    return TheoremSourceMap(paper_id, version_id, source_hash, binding, len(page_blocks), page_blocks, source_tier)


def build_source_maps(
    repository_root: Path | str,
    *,
    read_ledger_path: Path | str | None = None,
    manifests_path: Path | str | None = None,
    attempts_path: Path | str | None = None,
    expected_deep_read: int = FROZEN_DEEP_READ_COUNT,
) -> tuple[TheoremSourceMap, ...]:
    """Build all and only frozen DEEP_READ maps from Task 3's canonical inputs."""

    root = Path(repository_root).resolve()
    if isinstance(expected_deep_read, bool) or not isinstance(expected_deep_read, int) or expected_deep_read < 1:
        raise ValueError("expected_deep_read must be a positive integer")
    ledger_path = Path(read_ledger_path) if read_ledger_path is not None else root / "literature/fulltext_ledgers/read_depth_2026_08_30.json"
    selected_path = Path(manifests_path) if manifests_path is not None else root / "literature/fulltext_manifests/acquisition_2026_08_30.jsonl"
    immutable_path = Path(attempts_path) if attempts_path is not None else root / "literature/fulltext_manifests/acquisition_attempts_2026_08_30.jsonl"
    verify_frozen_task3_closure(
        root,
        read_ledger_path=ledger_path,
        manifests_path=selected_path,
        attempts_path=immutable_path,
    )
    if not ledger_path.is_file():
        raise ValueError(f"required Task 3 input is missing: {ledger_path}")
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as caught:
        raise ValueError("Task 3 reading ledger is invalid JSON") from caught
    if not isinstance(ledger, Mapping) or not isinstance(ledger.get("records"), list):
        raise ValueError("Task 3 reading ledger lacks records")
    records = ledger["records"]
    if any(not isinstance(item, Mapping) for item in records):
        raise ValueError("Task 3 reading ledger records must be objects")
    deep = tuple(item for item in records if item.get("read_depth") == "DEEP_READ")
    declared = ledger.get("counts")
    if not isinstance(declared, Mapping) or declared.get("DEEP_READ") != expected_deep_read or len(deep) != expected_deep_read:
        raise ValueError(f"frozen Task 3 ledger must contain exactly {expected_deep_read} DEEP_READ records")
    _index_unique(deep, "DEEP_READ ledger")
    family_ids = [str(item.get("paper_id")) for item in deep]
    version_ids = [str(item.get("version_id")) for item in deep]
    if len(set(family_ids)) != expected_deep_read:
        raise ValueError("duplicate DEEP_READ paper family")
    if len(set(version_ids)) != expected_deep_read:
        raise ValueError("duplicate DEEP_READ version")
    selected = _index_unique(_read_jsonl(selected_path), "selected manifest")
    attempts = _attempt_index(_read_jsonl(immutable_path))
    maps: list[TheoremSourceMap] = []
    for record in sorted(deep, key=lambda item: (str(item["paper_id"]), str(item["version_id"]))):
        key = (str(record["paper_id"]), str(record["version_id"]))
        manifest = selected.get(key)
        if manifest is None:
            raise ValueError(f"DEEP_READ ledger record has no selected manifest: {key}")
        attempt_id = manifest.get("attempt_id")
        if not isinstance(attempt_id, str) or attempt_id not in attempts:
            raise ValueError(f"selected manifest has no immutable attempt: {key}")
        maps.append(_build_one(record, manifest, attempts[attempt_id], root))
    return tuple(maps)


def build_frozen_task4_corpus(
    repository_root: Path | str,
    **source_map_kwargs: object,
) -> FrozenTask4Corpus:
    """Build the sealed 80-map corpus that may authorize theorem records."""

    maps = build_source_maps(repository_root, **source_map_kwargs)
    verify_frozen_task3_closure(
        repository_root,
        read_ledger_path=source_map_kwargs.get("read_ledger_path"),
        manifests_path=source_map_kwargs.get("manifests_path"),
        attempts_path=source_map_kwargs.get("attempts_path"),
    )
    corpus = FrozenTask4Corpus(maps, FROZEN_TASK3_CLOSURE_SHA256, _BUILD_CORPUS_ATTESTATION)
    _VERIFIED_FROZEN_CORPORA[id(corpus)] = corpus
    return corpus


def clear_source_map_page_cache() -> None:
    """Clear extraction memoization so deterministic builds can be independently checked."""

    _PAGE_BLOCK_CACHE.clear()


def canonical_source_maps_jsonl(source_maps: Iterable[TheoremSourceMap]) -> bytes:
    values = tuple(source_maps)
    if any(not isinstance(item, TheoremSourceMap) for item in values):
        raise ValueError("source_maps must contain TheoremSourceMap records")
    keys = tuple((item.paper_id, item.version_id) for item in values)
    if keys != tuple(sorted(keys)):
        raise ValueError("source maps must be canonically ordered by paper_id/version_id")
    if len(set(keys)) != len(keys) or len({item.paper_id for item in values}) != len(values) or len({item.version_id for item in values}) != len(values):
        raise ValueError("source maps cannot contain duplicate family/version identities")
    return b"".join(canonical_json(item.as_dict()).encode("utf-8") + b"\n" for item in values)


def source_map_sha256(source_maps: Iterable[TheoremSourceMap]) -> str:
    return hashlib.sha256(canonical_source_maps_jsonl(source_maps)).hexdigest()


def write_source_maps_atomic(source_maps: Iterable[TheoremSourceMap], destination: Path | str) -> str:
    """Atomically write deterministic canonical JSONL and return its SHA-256."""

    target = Path(destination)
    payload = canonical_source_maps_jsonl(source_maps)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}-", dir=target.parent)
    os.close(handle)
    staged = Path(temporary)
    try:
        staged.write_bytes(payload)
        os.replace(staged, target)
    finally:
        if staged.exists():
            staged.unlink()
    return hashlib.sha256(payload).hexdigest()
