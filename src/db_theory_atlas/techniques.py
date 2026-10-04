"""Controlled proof-technique profiles bound to verified source evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .evidence import validate_evidence_pointer
from .model import EvidencePointer, EvidenceType
from .reading import NoteRecord


class ProofTechnique(str, Enum):
    HOMOMORPHISM = "HOMOMORPHISM"
    CANONICAL_DATABASE = "CANONICAL_DATABASE"
    CHASE = "CHASE"
    TREE_DECOMPOSITION = "TREE_DECOMPOSITION"
    HYPERTREE_DECOMPOSITION = "HYPERTREE_DECOMPOSITION"
    DYNAMIC_PROGRAMMING = "DYNAMIC_PROGRAMMING"
    AUTOMATA = "AUTOMATA"
    GAMES = "GAMES"
    FINITE_MODEL_ARGUMENTS = "FINITE_MODEL_ARGUMENTS"
    CSP_REDUCTION = "CSP_REDUCTION"
    SAT_REDUCTION = "SAT_REDUCTION"
    QSAT_REDUCTION = "QSAT_REDUCTION"
    GRAPH_GADGET = "GRAPH_GADGET"
    HITTING_SET = "HITTING_SET"
    SET_COVER = "SET_COVER"
    VERTEX_COVER = "VERTEX_COVER"
    EXACT_COVER = "EXACT_COVER"
    PARAMETERIZED_REDUCTION = "PARAMETERIZED_REDUCTION"
    KERNELIZATION = "KERNELIZATION"
    ENUMERATION_DELAY = "ENUMERATION_DELAY"
    DUALITY = "DUALITY"
    FRONTIER = "FRONTIER"
    TEACHING_SET = "TEACHING_SET"
    WITNESS_CONSTRUCTION = "WITNESS_CONSTRUCTION"
    CANONICAL_FORM = "CANONICAL_FORM"
    SMALL_MODEL = "SMALL_MODEL"
    DESCRIPTIVE_COMPLEXITY = "DESCRIPTIVE_COMPLEXITY"


def _as_technique(value: ProofTechnique | str, label: str) -> ProofTechnique:
    if isinstance(value, ProofTechnique):
        return value
    try:
        return ProofTechnique(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the exact proof-technique taxonomy") from caught


def _concise_evidence_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty or explicitly UNKNOWN/NOT_APPLICABLE")
    compact = " ".join(value.split())
    words = re.findall(r"\b\w+\b", compact, flags=re.UNICODE)
    if len(compact) > 600 or len(words) > 80:
        raise ValueError(f"{label} must be concise")
    return compact


@dataclass(frozen=True, slots=True)
class ProofTechniqueSignature:
    primary: ProofTechnique
    secondary: tuple[ProofTechnique, ...]
    technical_obstacle: str
    restriction_preservation_trick: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "primary", _as_technique(self.primary, "primary technique"))
        if not isinstance(self.secondary, tuple):
            raise ValueError("secondary techniques must be an immutable tuple")
        normalized = tuple(_as_technique(item, "secondary technique") for item in self.secondary)
        if len(set(normalized)) != len(normalized) or self.primary in normalized:
            raise ValueError("secondary techniques must be distinct and exclude the primary technique")
        object.__setattr__(self, "secondary", normalized)
        object.__setattr__(self, "technical_obstacle", _concise_evidence_text(
            self.technical_obstacle, "technical_obstacle"
        ))
        object.__setattr__(self, "restriction_preservation_trick", _concise_evidence_text(
            self.restriction_preservation_trick, "restriction_preservation_trick"
        ))


@dataclass(frozen=True, slots=True)
class ProofTechniqueProfile:
    primary: ProofTechnique
    secondary: tuple[ProofTechnique, ...]
    technical_obstacle: str
    restriction_preservation_trick: str
    evidence: EvidencePointer

    def __post_init__(self) -> None:
        signature = technique_signature(self)
        object.__setattr__(self, "primary", signature.primary)
        object.__setattr__(self, "secondary", signature.secondary)
        object.__setattr__(self, "technical_obstacle", signature.technical_obstacle)
        object.__setattr__(self, "restriction_preservation_trick", signature.restriction_preservation_trick)
        if not isinstance(self.evidence, EvidencePointer):
            raise ValueError("proof-technique profile requires evidence")


def technique_signature(profile: ProofTechniqueProfile) -> ProofTechniqueSignature:
    """Return the evidence-free proof-technique fields bound into theorem claims."""
    return ProofTechniqueSignature(
        profile.primary,
        profile.secondary,
        profile.technical_obstacle,
        profile.restriction_preservation_trick,
    )


def validate_techniques(profile: ProofTechniqueProfile, note: NoteRecord | None = None) -> ProofTechniqueProfile:
    """Validate the exact taxonomy and bind descriptive fields to theorem evidence."""
    if not isinstance(profile, ProofTechniqueProfile):
        raise ValueError("profile must be a ProofTechniqueProfile")
    _as_technique(profile.primary, "primary technique")
    for item in profile.secondary:
        _as_technique(item, "secondary technique")
    _concise_evidence_text(profile.technical_obstacle, "technical_obstacle")
    _concise_evidence_text(profile.restriction_preservation_trick, "restriction_preservation_trick")
    validate_evidence_pointer(profile.evidence, note)
    if not profile.evidence.verified or profile.evidence.evidence_type is not EvidenceType.THEOREM:
        raise ValueError("proof-technique profile requires verified THEOREM evidence")
    return profile
