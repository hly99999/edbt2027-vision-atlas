"""Append-only reading histories and portable full-text notes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import re
from typing import TYPE_CHECKING, Iterable

from .serialization import scientific_hash

if TYPE_CHECKING:
    from .model import EvidencePointer


class ReadingState(str, Enum):
    METADATA = "METADATA"
    ABSTRACT = "ABSTRACT"
    INTRO_CONCLUSION = "INTRO_CONCLUSION"
    FULL_SCAN = "FULL_SCAN"
    DEEP_READ = "DEEP_READ"


class CoverageKind(str, Enum):
    """Explicit semantic coverage used to justify promoted read depths."""

    INTRODUCTION = "INTRODUCTION"
    CONCLUSION = "CONCLUSION"
    FULL_SCAN_SECTION = "FULL_SCAN_SECTION"
    PROBLEM_DEFINITION = "PROBLEM_DEFINITION"
    FORMAL_SCOPE_ASSUMPTIONS = "FORMAL_SCOPE_ASSUMPTIONS"
    THEOREM_RESULTS = "THEOREM_RESULTS"
    LIMITATIONS_FUTURE_WORK = "LIMITATIONS_FUTURE_WORK"


_STATES = tuple(ReadingState)
_ID = re.compile(r"^(?!(?:arxiv|doi|file|url):)[a-z][a-z0-9_-]*:[a-z0-9][a-z0-9._-]*$")
_HASH = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_FRONTMATTER_KEYS = frozenset(
    {
        "paper_id", "version_id", "source_hash", "read_depth", "sections", "pages", "headings",
        "created_at", "updated_at", "extractor_status", "reviewer_status",
    }
)


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a canonical ID")
    return value


def _require_hash(value: object) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("source_hash must be a SHA-256 digest")
    return value.lower()


def _as_state(value: ReadingState | str) -> ReadingState:
    if isinstance(value, ReadingState):
        return value
    try:
        return ReadingState(value)
    except (TypeError, ValueError) as caught:
        raise ValueError("read_depth must be a ReadingState") from caught


def _as_coverage_kind(value: CoverageKind | str) -> CoverageKind:
    if isinstance(value, CoverageKind):
        return value
    try:
        return CoverageKind(value)
    except (TypeError, ValueError) as caught:
        raise ValueError("coverage kind is not recognized") from caught


def _tuple_text(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must contain nonempty text")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} cannot contain duplicates")
    return value


def _tuple_pages(value: object) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise ValueError("pages must be an immutable tuple")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
        raise ValueError("pages must contain positive integers")
    if len(set(value)) != len(value):
        raise ValueError("pages cannot contain duplicates")
    return value


def _operational_date(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty operational date")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as caught:
        raise ValueError(f"{label} must be ISO-8601") from caught
    return value


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    kind: CoverageKind
    page: int | None
    heading: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _as_coverage_kind(self.kind))
        if self.page is not None and (isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1):
            raise ValueError("coverage page must be a positive integer or None")
        if self.heading is not None and (not isinstance(self.heading, str) or not self.heading.strip()):
            raise ValueError("coverage heading must be nonempty or None")
        if self.page is None and self.heading is None:
            raise ValueError("coverage requires an inspected location")


def _same_location(pointer: EvidencePointer, coverage: CoverageEntry) -> bool:
    return pointer.page == coverage.page and pointer.heading == coverage.heading


def _base_scientific_payload(
    paper_id: str,
    version_id: str,
    source_hash: str,
    read_depth: ReadingState,
    sections: tuple[str, ...],
    pages: tuple[int, ...],
    headings: tuple[str, ...],
    coverage: tuple[CoverageEntry, ...],
    evidence: tuple[EvidencePointer, ...],
) -> dict[str, object]:
    return {
        "paper_id": paper_id,
        "version_id": version_id,
        "source_hash": source_hash,
        "read_depth": read_depth.value,
        "sections": sections,
        "pages": pages,
        "headings": headings,
        "coverage": coverage,
        "evidence": evidence,
    }


def _validate_scientific_coverage(
    *,
    paper_id: str,
    version_id: str,
    source_hash: str,
    read_depth: ReadingState,
    sections: tuple[str, ...],
    pages: tuple[int, ...],
    headings: tuple[str, ...],
    coverage: tuple[CoverageEntry, ...],
    evidence: tuple[EvidencePointer, ...],
) -> None:
    from .evidence import validate_evidence_pointer
    from .model import EvidencePointer, EvidenceType

    if not isinstance(coverage, tuple) or any(not isinstance(item, CoverageEntry) for item in coverage):
        raise ValueError("coverage must be an immutable tuple of CoverageEntry records")
    if len(set(coverage)) != len(coverage):
        raise ValueError("coverage cannot contain duplicates")
    if not isinstance(evidence, tuple) or any(not isinstance(item, EvidencePointer) for item in evidence):
        raise ValueError("note evidence must be an immutable tuple of EvidencePointer records")
    if not evidence:
        raise ValueError("note requires immutable scientific evidence entries")
    for item in coverage:
        if item.page is not None and item.page not in pages:
            raise ValueError("coverage page is outside inspected note pages")
        if item.heading is not None and item.heading not in headings:
            raise ValueError("coverage heading is outside inspected note headings")
    for pointer in evidence:
        validate_evidence_pointer(
            pointer, None, paper_id=paper_id, version_id=version_id, source_hash=source_hash
        )
        if not any(_same_location(pointer, item) for item in coverage):
            raise ValueError("evidence pointer is outside an exact inspected location")

    verified_evidence = tuple(pointer for pointer in evidence if pointer.verified)
    kinds = {pointer.evidence_type for pointer in verified_evidence}
    coverage_kinds = {item.kind for item in coverage}
    if EvidenceType.METADATA not in kinds:
        raise ValueError("note requires METADATA evidence")
    if _STATES.index(read_depth) >= _STATES.index(ReadingState.ABSTRACT) and EvidenceType.ABSTRACT not in kinds:
        raise ValueError("ABSTRACT note requires abstract evidence")
    if _STATES.index(read_depth) >= _STATES.index(ReadingState.INTRO_CONCLUSION):
        if not {CoverageKind.INTRODUCTION, CoverageKind.CONCLUSION} <= coverage_kinds:
            raise ValueError("INTRO_CONCLUSION note requires inspected introduction and conclusion coverage")
    if _STATES.index(read_depth) >= _STATES.index(ReadingState.FULL_SCAN):
        scan = tuple(item for item in coverage if item.kind is CoverageKind.FULL_SCAN_SECTION)
        distinct_headings = {item.heading.casefold() for item in scan if item.heading}
        if len(scan) < 3 or len(distinct_headings) < 3:
            raise ValueError("FULL_SCAN requires at least three distinct inspected section headings")
        if any(not any(_same_location(pointer, item) for pointer in verified_evidence) for item in scan):
            raise ValueError("FULL_SCAN section coverage requires verified evidence at each inspected location")
    if read_depth is ReadingState.DEEP_READ:
        required = {
            CoverageKind.PROBLEM_DEFINITION,
            CoverageKind.FORMAL_SCOPE_ASSUMPTIONS,
            CoverageKind.THEOREM_RESULTS,
            CoverageKind.LIMITATIONS_FUTURE_WORK,
        }
        missing = required - coverage_kinds
        if missing:
            labels = {
                CoverageKind.PROBLEM_DEFINITION: "problem definition",
                CoverageKind.FORMAL_SCOPE_ASSUMPTIONS: "formal scope/assumptions",
                CoverageKind.THEOREM_RESULTS: "theorem/results",
                CoverageKind.LIMITATIONS_FUTURE_WORK: "limitations/future work",
            }
            raise ValueError("DEEP_READ requires " + ", ".join(labels[item] for item in sorted(missing, key=lambda item: item.value)))
        expected_types = {
            CoverageKind.PROBLEM_DEFINITION: {EvidenceType.PROBLEM_DEFINITION},
            CoverageKind.FORMAL_SCOPE_ASSUMPTIONS: {EvidenceType.PROBLEM_DEFINITION, EvidenceType.THEOREM},
            CoverageKind.THEOREM_RESULTS: {EvidenceType.THEOREM},
            CoverageKind.LIMITATIONS_FUTURE_WORK: {EvidenceType.LIMITATION, EvidenceType.FUTURE_WORK},
        }
        for kind, accepted_types in expected_types.items():
            entries = tuple(item for item in coverage if item.kind is kind)
            if not any(
                _same_location(pointer, item) and pointer.evidence_type in accepted_types
                for item in entries
                for pointer in verified_evidence
            ):
                raise ValueError(
                    f"DEEP_READ {kind.value.lower()} coverage requires matching verified inspected evidence"
                )


@dataclass(frozen=True, slots=True)
class NoteRecord:
    """A note's immutable scientific evidence plus excluded operational fields."""

    paper_id: str
    version_id: str
    source_hash: str
    read_depth: ReadingState
    sections: tuple[str, ...]
    pages: tuple[int, ...]
    headings: tuple[str, ...]
    created_at: str
    updated_at: str
    extractor_status: str
    reviewer_status: str
    coverage: tuple[CoverageEntry, ...] = ()
    evidence: tuple[EvidencePointer, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        object.__setattr__(self, "source_hash", _require_hash(self.source_hash))
        object.__setattr__(self, "read_depth", _as_state(self.read_depth))
        _tuple_text(self.sections, "sections")
        _tuple_pages(self.pages)
        _tuple_text(self.headings, "headings")
        _operational_date(self.created_at, "created_at")
        _operational_date(self.updated_at, "updated_at")
        if not isinstance(self.extractor_status, str) or not self.extractor_status.strip():
            raise ValueError("extractor_status must be nonempty")
        if not isinstance(self.reviewer_status, str) or not self.reviewer_status.strip():
            raise ValueError("reviewer_status must be nonempty")
        _validate_scientific_coverage(
            paper_id=self.paper_id, version_id=self.version_id, source_hash=self.source_hash,
            read_depth=self.read_depth, sections=self.sections, pages=self.pages, headings=self.headings,
            coverage=self.coverage, evidence=self.evidence,
        )

    def scientific_payload(self) -> dict[str, object]:
        return _base_scientific_payload(
            self.paper_id, self.version_id, self.source_hash, self.read_depth, self.sections,
            self.pages, self.headings, self.coverage, self.evidence,
        )

    @property
    def scientific_hash(self) -> str:
        return scientific_hash(self.scientific_payload())

    def with_operational_dates(self, created_at: datetime | str, updated_at: datetime | str) -> NoteRecord:
        def stamp(value: datetime | str) -> str:
            if isinstance(value, datetime):
                return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            return value
        return replace(self, created_at=stamp(created_at), updated_at=stamp(updated_at))


def validate_note(note: NoteRecord) -> NoteRecord:
    if not isinstance(note, NoteRecord):
        raise ValueError("note must be a NoteRecord")
    _validate_scientific_coverage(
        paper_id=note.paper_id, version_id=note.version_id, source_hash=note.source_hash,
        read_depth=note.read_depth, sections=note.sections, pages=note.pages, headings=note.headings,
        coverage=note.coverage, evidence=note.evidence,
    )
    return note


def parse_note_frontmatter(text: str) -> NoteRecord:
    """Parse deterministic frontmatter and JSON-line scientific body entries."""
    from .model import EvidencePointer

    if not isinstance(text, str) or not text.startswith("---\n"):
        raise ValueError("note must begin with frontmatter")
    closing = text.find("\n---", 4)
    if closing < 0:
        raise ValueError("note frontmatter is not closed")
    values: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        if not line or ":" not in line:
            raise ValueError("frontmatter lines must be key: value")
        key, value = line.split(":", 1)
        if key not in _FRONTMATTER_KEYS or key in values:
            raise ValueError("frontmatter has an unknown or duplicate key")
        values[key] = value.strip()
    if set(values) != _FRONTMATTER_KEYS:
        raise ValueError("frontmatter must contain every required field")
    try:
        pages = tuple(int(item.strip()) for item in values["pages"].split(",") if item.strip())
    except ValueError as caught:
        raise ValueError("pages must be comma-separated integers") from caught
    split = lambda value: tuple(item.strip() for item in value.split("|") if item.strip())
    coverage: list[CoverageEntry] = []
    evidence: list[EvidencePointer] = []
    for line in text[closing + 4:].splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as caught:
            raise ValueError("scientific note body must use one JSON evidence or coverage entry per line") from caught
        if not isinstance(entry, dict):
            raise ValueError("scientific note body entries must be JSON objects")
        if "coverage" in entry:
            if set(entry) != {"coverage", "page", "heading"}:
                raise ValueError("coverage entries require coverage, page, and heading")
            coverage.append(CoverageEntry(_as_coverage_kind(entry["coverage"]), entry["page"], entry["heading"]))
        elif "evidence_type" in entry:
            base_keys = {"evidence_type", "page", "heading", "paraphrase", "verified"}
            if frozenset(entry) not in {frozenset(base_keys), frozenset(base_keys | {"claim"})}:
                raise ValueError("evidence entries require type, location, paraphrase, verified status, and optional claim")
            evidence.append(EvidencePointer(
                paper_id=values["paper_id"], version_id=values["version_id"], source_hash=values["source_hash"],
                evidence_type=entry["evidence_type"], page=entry["page"], heading=entry["heading"],
                paraphrase=entry["paraphrase"], verified=entry["verified"], claim=entry.get("claim"),
            ))
        else:
            raise ValueError("scientific note body entry is neither coverage nor evidence")
    return NoteRecord(
        paper_id=values["paper_id"], version_id=values["version_id"], source_hash=values["source_hash"],
        read_depth=_as_state(values["read_depth"]), sections=split(values["sections"]), pages=pages,
        headings=split(values["headings"]), created_at=values["created_at"], updated_at=values["updated_at"],
        extractor_status=values["extractor_status"], reviewer_status=values["reviewer_status"],
        coverage=tuple(coverage), evidence=tuple(evidence),
    )


parse_note = parse_note_frontmatter


@dataclass(frozen=True, slots=True)
class CoverageCertificate:
    """Portable validated snapshot of a note's scientific content."""

    paper_id: str
    version_id: str
    source_hash: str
    read_depth: ReadingState
    sections: tuple[str, ...]
    pages: tuple[int, ...]
    headings: tuple[str, ...]
    coverage: tuple[CoverageEntry, ...]
    evidence: tuple[EvidencePointer, ...]
    note_hash: str

    def __post_init__(self) -> None:
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        object.__setattr__(self, "source_hash", _require_hash(self.source_hash))
        object.__setattr__(self, "read_depth", _as_state(self.read_depth))
        _tuple_text(self.sections, "sections")
        _tuple_pages(self.pages)
        _tuple_text(self.headings, "headings")
        if any(not pointer.verified for pointer in self.evidence):
            raise ValueError("coverage certificate evidence must be verified")
        _validate_scientific_coverage(
            paper_id=self.paper_id, version_id=self.version_id, source_hash=self.source_hash,
            read_depth=self.read_depth, sections=self.sections, pages=self.pages, headings=self.headings,
            coverage=self.coverage, evidence=self.evidence,
        )
        expected = scientific_hash(self.scientific_payload())
        if not isinstance(self.note_hash, str) or self.note_hash.lower() != expected:
            raise ValueError("coverage certificate note hash does not match its scientific evidence")
        object.__setattr__(self, "note_hash", self.note_hash.lower())

    def scientific_payload(self) -> dict[str, object]:
        return _base_scientific_payload(
            self.paper_id, self.version_id, self.source_hash, self.read_depth, self.sections,
            self.pages, self.headings, self.coverage, self.evidence,
        )


def coverage_certificate(note: NoteRecord) -> CoverageCertificate:
    validate_note(note)
    verified_evidence = tuple(pointer for pointer in note.evidence if pointer.verified)
    certificate_payload = _base_scientific_payload(
        note.paper_id,
        note.version_id,
        note.source_hash,
        note.read_depth,
        note.sections,
        note.pages,
        note.headings,
        note.coverage,
        verified_evidence,
    )
    return CoverageCertificate(
        paper_id=note.paper_id, version_id=note.version_id, source_hash=note.source_hash,
        read_depth=note.read_depth, sections=note.sections, pages=note.pages, headings=note.headings,
        coverage=note.coverage,
        evidence=verified_evidence,
        note_hash=scientific_hash(certificate_payload),
    )


def validate_coverage_certificate(certificate: CoverageCertificate) -> CoverageCertificate:
    if not isinstance(certificate, CoverageCertificate):
        raise ValueError("certificate must be a CoverageCertificate")
    expected = scientific_hash(certificate.scientific_payload())
    if certificate.note_hash != expected:
        raise ValueError("coverage certificate evidence hash is invalid")
    return certificate


@dataclass(frozen=True, slots=True)
class ReadingEvent:
    state: ReadingState
    evidence: tuple[EvidencePointer, ...]
    unavailable_locations: tuple[str, ...] = ()
    certificate: CoverageCertificate | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _as_state(self.state))
        if not isinstance(self.evidence, tuple):
            raise ValueError("evidence must be an immutable tuple")
        _tuple_text(self.unavailable_locations, "unavailable_locations")
        if self.certificate is not None and not isinstance(self.certificate, CoverageCertificate):
            raise ValueError("certificate must be a CoverageCertificate or None")


@dataclass(frozen=True, slots=True)
class ReadingHistory:
    paper_id: str
    version_id: str
    source_hash: str
    full_text_available: bool
    events: tuple[ReadingEvent, ...]

    def __post_init__(self) -> None:
        _require_id(self.paper_id, "paper_id")
        _require_id(self.version_id, "version_id")
        object.__setattr__(self, "source_hash", _require_hash(self.source_hash))
        if not isinstance(self.full_text_available, bool):
            raise ValueError("full_text_available must be a boolean")
        if not isinstance(self.events, tuple) or not self.events:
            raise ValueError("events must be a nonempty immutable tuple")
        validate_reading_history(self)

    @property
    def current_state(self) -> ReadingState:
        return self.events[-1].state

    def scientific_payload(self) -> dict[str, object]:
        return {
            "paper_id": self.paper_id, "version_id": self.version_id, "source_hash": self.source_hash,
            "full_text_available": self.full_text_available,
            "events": tuple(
                {"state": event.state.value, "evidence": event.evidence,
                 "unavailable_locations": event.unavailable_locations, "certificate": event.certificate}
                for event in self.events
            ),
        }

    @property
    def scientific_hash(self) -> str:
        return scientific_hash(self.scientific_payload())


def _pointer_types(event: ReadingEvent) -> set[str]:
    return {getattr(pointer.evidence_type, "value", pointer.evidence_type) for pointer in event.evidence}


def _validate_event(history: ReadingHistory, event: ReadingEvent) -> None:
    from .evidence import EvidenceType, validate_evidence_pointer

    if not isinstance(event, ReadingEvent):
        raise ValueError("events must be ReadingEvent records")
    for pointer in event.evidence:
        validate_evidence_pointer(
            pointer, None, paper_id=history.paper_id, version_id=history.version_id, source_hash=history.source_hash
        )
    if event.certificate is not None:
        validate_coverage_certificate(event.certificate)
        certificate = event.certificate
        if (certificate.paper_id, certificate.version_id, certificate.source_hash) != (
            history.paper_id, history.version_id, history.source_hash
        ):
            raise ValueError("coverage certificate does not match reading history identity")
        if certificate.read_depth is not event.state or certificate.evidence != event.evidence:
            raise ValueError("reading event must bind the certificate depth and exact evidence")
    if event.state in {ReadingState.FULL_SCAN, ReadingState.DEEP_READ} and event.certificate is None:
        raise ValueError("FULL_SCAN and DEEP_READ require a validated NoteRecord or CoverageCertificate")
    if event.state in {ReadingState.FULL_SCAN, ReadingState.DEEP_READ} and any(
        not pointer.verified for pointer in event.evidence
    ):
        raise ValueError("FULL_SCAN and DEEP_READ promotion evidence must be verified")
    kinds = _pointer_types(event)
    if event.state is ReadingState.METADATA and EvidenceType.METADATA.value not in kinds:
        raise ValueError("metadata state requires metadata evidence")
    if event.state is ReadingState.ABSTRACT and EvidenceType.ABSTRACT.value not in kinds:
        raise ValueError("ABSTRACT requires abstract evidence")
    if event.state is ReadingState.INTRO_CONCLUSION:
        headings = {str(pointer.heading).casefold() for pointer in event.evidence if pointer.heading}
        unavailable = {item.casefold() for item in event.unavailable_locations}
        has_intro = any("intro" in item for item in headings) or "introduction" in unavailable
        has_conclusion = any("conclusion" in item for item in headings) or "conclusion" in unavailable
        if not has_intro or not has_conclusion:
            raise ValueError("INTRO_CONCLUSION requires both locations or explicit unavailability")


def validate_reading_history(history: ReadingHistory) -> ReadingHistory:
    if not isinstance(history, ReadingHistory):
        raise ValueError("history must be a ReadingHistory")
    states = tuple(event.state for event in history.events)
    if states[0] is not ReadingState.METADATA:
        raise ValueError("history must begin at METADATA")
    for previous, current in zip(states, states[1:]):
        if _STATES.index(current) != _STATES.index(previous) + 1:
            raise ValueError("reading history must be sequential and cannot be rewritten")
    if not history.full_text_available and any(state is not ReadingState.METADATA for state in states):
        raise ValueError("full text is unavailable beyond METADATA")
    for event in history.events:
        _validate_event(history, event)
    return history


def _event_from_scientific_source(target: ReadingState, source: NoteRecord | CoverageCertificate) -> ReadingEvent:
    certificate = coverage_certificate(source) if isinstance(source, NoteRecord) else validate_coverage_certificate(source)
    if certificate.read_depth is not target:
        raise ValueError("note/certificate read depth must match the promotion target")
    return ReadingEvent(target, certificate.evidence, certificate=certificate)


def _events_for_promotion(target: ReadingState, evidence: object) -> tuple[ReadingEvent, ...]:
    if isinstance(evidence, (NoteRecord, CoverageCertificate)):
        return (_event_from_scientific_source(target, evidence),)
    if isinstance(evidence, tuple) and all(isinstance(item, ReadingEvent) for item in evidence):
        return evidence
    if isinstance(evidence, list) and all(isinstance(item, ReadingEvent) for item in evidence):
        return tuple(evidence)
    return (ReadingEvent(target, evidence if isinstance(evidence, tuple) else tuple(evidence)),)


def promote_read_depth(
    history: ReadingHistory,
    target: ReadingState | str,
    evidence: Iterable[EvidencePointer] | tuple[ReadingEvent, ...] | NoteRecord | CoverageCertificate,
) -> ReadingHistory:
    """Append evidence-backed state transitions without mutating prior history."""
    validate_reading_history(history)
    target_state = _as_state(target)
    current_index, target_index = _STATES.index(history.current_state), _STATES.index(target_state)
    if target_index <= current_index:
        raise ValueError("cannot downgrade or rewrite reading history")
    if not history.full_text_available:
        raise ValueError("full text is unavailable; promotion beyond METADATA is forbidden")
    appended = _events_for_promotion(target_state, evidence)
    expected = _STATES[current_index + 1 : target_index + 1]
    if tuple(item.state for item in appended) != expected:
        raise ValueError("promotion must be sequential; provide explicit intermediate evidence events")
    return ReadingHistory(
        history.paper_id, history.version_id, history.source_hash,
        history.full_text_available, history.events + appended,
    )
