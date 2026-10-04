"""Evidence taxonomy, note-bound pointers, and promotion authorization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

from .model import EvidencePointer, EvidenceType
from .reading import (
    CoverageCertificate,
    CoverageKind,
    NoteRecord,
    ReadingState,
    coverage_certificate,
    validate_coverage_certificate,
    validate_note,
)

if TYPE_CHECKING:
    from .model import TheoremRecord


_PLACEHOLDER = re.compile(r"^(?:todo|tbd|n/?a|\[.*?\]|<.*?>)$", re.IGNORECASE)
_CERTAINTY = re.compile(r"\b(?:certainly|definitive(?:ly)?|undeniably|guaranteed|always)\b", re.IGNORECASE)
_SCOPE = re.compile(r"\b(?:for|under|within|scope|fragment|case|assumption|stated|listed)\b", re.IGNORECASE)
_QUOTED_SPAN = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|‘([^’\n]+)’|«([^»\n]+)»')
_MAX_PARAPHRASE_CHARS = 600
_MAX_PARAPHRASE_WORDS = 80


def _has_repeated_verbatim_phrase(value: str) -> bool:
    words = re.findall(r"\b\w+\b", value.casefold(), flags=re.UNICODE)
    if len(words) < 16:
        return False
    seen: set[tuple[str, ...]] = set()
    for index in range(len(words) - 7):
        phrase = tuple(words[index:index + 8])
        if phrase in seen:
            return True
        seen.add(phrase)
    return False


def _validate_paraphrase(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("paraphrase must be nonempty")
    compact = " ".join(value.split())
    if _PLACEHOLDER.fullmatch(compact) or _CERTAINTY.search(compact):
        raise ValueError("paraphrase contains a placeholder or unsupported certainty")
    for match in _QUOTED_SPAN.finditer(compact):
        quoted = next(group for group in match.groups() if group is not None)
        if len(quoted) > 80 or len(re.findall(r"\b\w+\b", quoted, flags=re.UNICODE)) > 12:
            raise ValueError("paraphrase contains excessive quoted or verbatim text")
    word_count = len(re.findall(r"\b\w+\b", compact, flags=re.UNICODE))
    if len(compact) > _MAX_PARAPHRASE_CHARS or word_count > _MAX_PARAPHRASE_WORDS:
        raise ValueError("paraphrase must be concise: at most 80 words and 600 characters")
    if _has_repeated_verbatim_phrase(compact):
        raise ValueError("paraphrase looks like an excessive copied block")
    if not _SCOPE.search(compact):
        raise ValueError("paraphrase must state its scope")
    return compact


def _as_type(value: EvidenceType | str) -> EvidenceType:
    if isinstance(value, EvidenceType):
        return value
    try:
        return EvidenceType(value.upper())
    except (AttributeError, ValueError) as caught:
        raise ValueError("evidence_type is not in the controlled taxonomy") from caught


def validate_evidence_pointer(
    pointer: EvidencePointer,
    note: NoteRecord | None,
    *,
    paper_id: str | None = None,
    version_id: str | None = None,
    source_hash: str | None = None,
) -> EvidencePointer:
    """Check immutable identity and, when supplied, exact note coverage."""
    if not isinstance(pointer, EvidencePointer):
        raise ValueError("pointer must be an EvidencePointer")
    _as_type(pointer.evidence_type)
    _validate_paraphrase(pointer.paraphrase)
    if paper_id is not None and pointer.paper_id != paper_id:
        raise ValueError("pointer paper_id does not match history")
    if version_id is not None and pointer.version_id != version_id:
        raise ValueError("pointer version_id does not match history")
    if source_hash is not None and pointer.source_hash != source_hash.lower():
        raise ValueError("pointer source hash does not match history")
    if note is not None:
        validate_note(note)
        if (pointer.paper_id, pointer.version_id, pointer.source_hash) != (note.paper_id, note.version_id, note.source_hash):
            raise ValueError("pointer paper/version/source hash does not match note")
        if not any(pointer.page == item.page and pointer.heading == item.heading for item in note.coverage):
            raise ValueError("pointer location is outside an exact inspected location")
    return pointer


def validate_evidence_membership(pointer: EvidencePointer, note: NoteRecord) -> EvidencePointer:
    """Require exact immutable membership, including paraphrase and structured claim."""
    validate_evidence_pointer(pointer, note)
    if pointer not in note.evidence:
        raise ValueError("evidence pointer must be an exact member of the source note evidence")
    return pointer


def build_evidence_pointer(
    note: NoteRecord,
    *,
    evidence_type: EvidenceType | str,
    page: int | None,
    heading: str | None,
    paraphrase: str,
    verified: bool = True,
    claim: Mapping[str, object] | None = None,
) -> EvidencePointer:
    """Build a pointer only at a location explicitly recorded in a note."""
    validate_note(note)
    if not any(item.page == page and item.heading == heading for item in note.coverage):
        raise ValueError("evidence pointer is outside an exact inspected location")
    normalized_type = _as_type(evidence_type)
    if claim is None and normalized_type in {
        EvidenceType.THEOREM,
        EvidenceType.OPEN_PROBLEM,
        EvidenceType.FUTURE_WORK,
    }:
        matching_claims = tuple(
            pointer.claim
            for pointer in note.evidence
            if pointer.evidence_type is normalized_type
            and pointer.page == page
            and pointer.heading == heading
            and pointer.claim is not None
        )
        if matching_claims and all(item == matching_claims[0] for item in matching_claims):
            claim = matching_claims[0]
    pointer = EvidencePointer(
        paper_id=note.paper_id, version_id=note.version_id, page=page, heading=heading,
        evidence_type=normalized_type, paraphrase=_validate_paraphrase(paraphrase),
        source_hash=note.source_hash, verified=verified, claim=claim,
    )
    return validate_evidence_pointer(pointer, note)


@dataclass(frozen=True, slots=True)
class TheoremAuthorization:
    certificate: CoverageCertificate
    evidence: EvidencePointer

    def __post_init__(self) -> None:
        validate_theorem_authorization(self)


def validate_theorem_authorization(authorization: TheoremAuthorization) -> TheoremAuthorization:
    if not isinstance(authorization, TheoremAuthorization):
        raise ValueError("complete theorem extraction requires validated authorization")
    certificate = validate_coverage_certificate(authorization.certificate)
    pointer = authorization.evidence
    if not pointer.verified:
        raise ValueError("complete theorem authorization requires verified THEOREM evidence")
    if certificate.read_depth is not ReadingState.DEEP_READ:
        raise ValueError("complete theorem extraction requires DEEP_READ authorization")
    if pointer not in certificate.evidence:
        raise ValueError("theorem authorization evidence is not bound to the certificate")
    if _as_type(pointer.evidence_type) is not EvidenceType.THEOREM:
        raise ValueError("complete theorem extraction requires THEOREM evidence")
    theorem_locations = tuple(item for item in certificate.coverage if item.kind is CoverageKind.THEOREM_RESULTS)
    if not any(pointer.page == item.page and pointer.heading == item.heading for item in theorem_locations):
        raise ValueError("THEOREM evidence must occur at an inspected theorem/results location")
    return authorization


def authorize_complete_theorem(
    note: NoteRecord | CoverageCertificate,
    pointer: EvidencePointer,
) -> TheoremAuthorization:
    """Allow complete theorem extraction only from deep, theorem-specific evidence."""
    if not pointer.verified:
        raise ValueError("complete theorem authorization requires verified THEOREM evidence")
    if isinstance(note, NoteRecord):
        validate_evidence_pointer(pointer, note)
        certificate = coverage_certificate(note)
    else:
        certificate = validate_coverage_certificate(note)
        validate_evidence_pointer(
            pointer,
            None,
            paper_id=certificate.paper_id,
            version_id=certificate.version_id,
            source_hash=certificate.source_hash,
        )
    if certificate.read_depth is not ReadingState.DEEP_READ:
        raise ValueError("complete theorem extraction requires DEEP_READ")
    if _as_type(pointer.evidence_type) is not EvidenceType.THEOREM:
        raise ValueError("complete theorem extraction requires THEOREM evidence")
    if pointer not in certificate.evidence:
        raise ValueError("complete theorem evidence must be an immutable note evidence entry")
    return TheoremAuthorization(certificate, pointer)
