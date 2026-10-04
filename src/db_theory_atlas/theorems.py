"""Semantic validation for note-bound complete theorem extractions."""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from enum import Enum
import re
from typing import Mapping

from .evidence import (
    TheoremAuthorization,
    validate_evidence_membership,
    validate_theorem_authorization,
)
from .model import EvidencePointer
from .reading import NoteRecord, ReadingState, coverage_certificate, validate_note
from .serialization import freeze_json
from .techniques import (
    ProofTechnique,
    ProofTechniqueProfile,
    ProofTechniqueSignature,
    technique_signature,
    validate_techniques,
)


class QuerySemantics(str, Enum):
    SET = "SET"
    BAG = "BAG"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ResultDirection(str, Enum):
    UPPER_BOUND = "UPPER_BOUND"
    LOWER_BOUND = "LOWER_BOUND"
    DICHOTOMY = "DICHOTOMY"
    TRACTABLE_FRAGMENT = "TRACTABLE_FRAGMENT"
    HARD_FRAGMENT = "HARD_FRAGMENT"
    ENUMERATION = "ENUMERATION"
    PARAMETERIZED = "PARAMETERIZED"
    STRUCTURAL = "STRUCTURAL"
    ALGORITHMIC = "ALGORITHMIC"
    CERTIFICATE = "CERTIFICATE"


class ComplexityMeasure(str, Enum):
    DATA_COMPLEXITY = "DATA_COMPLEXITY"
    COMBINED_COMPLEXITY = "COMBINED_COMPLEXITY"
    QUERY_COMPLEXITY = "QUERY_COMPLEXITY"
    PARAMETERIZED_COMPLEXITY = "PARAMETERIZED_COMPLEXITY"
    DELAY = "DELAY"
    UPDATE_TIME = "UPDATE_TIME"
    PREPROCESSING = "PREPROCESSING"


class ParameterRole(str, Enum):
    FIXED = "FIXED"
    INPUT = "INPUT"
    PARAMETER = "PARAMETER"


class ParameterDimension(str, Enum):
    QUERY = "QUERY"
    DATA = "DATA"
    PARAMETER = "PARAMETER"


class QuestionType(str, Enum):
    COMPLEXITY_BOUND = "COMPLEXITY_BOUND"
    DICHOTOMY = "DICHOTOMY"
    TRACTABLE_FRAGMENT = "TRACTABLE_FRAGMENT"
    HARDNESS = "HARDNESS"
    ENUMERATION = "ENUMERATION"
    PARAMETERIZED = "PARAMETERIZED"
    STRUCTURAL = "STRUCTURAL"
    ALGORITHM = "ALGORITHM"
    CERTIFICATE = "CERTIFICATE"


class ScopeRelation(str, Enum):
    EQUAL = "EQUAL"
    NARROWER = "NARROWER"
    BROADER = "BROADER"
    DISJOINT = "DISJOINT"
    UNKNOWN = "UNKNOWN"


def _enum(value: object, enum_type: type[Enum], label: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as caught:
        raise ValueError(f"{label} is not in the controlled taxonomy") from caught


def _text(value: object, label: str, *, max_words: int = 80, max_chars: int = 600) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty")
    compact = " ".join(value.split())
    if len(compact) > max_chars or len(re.findall(r"\b\w+\b", compact, flags=re.UNICODE)) > max_words:
        raise ValueError(f"{label} must be concise")
    return compact


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{label} must be explicit; use UNKNOWN when omitted by the source")
    normalized = tuple(_text(item, label) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} cannot contain duplicates")
    if "UNKNOWN" in normalized and len(normalized) != 1:
        raise ValueError(f"{label} cannot mix UNKNOWN with asserted values")
    return normalized


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    role: ParameterRole
    dimension: ParameterDimension

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "parameter name", max_words=20, max_chars=120))
        object.__setattr__(self, "role", _enum(self.role, ParameterRole, "parameter role"))
        object.__setattr__(self, "dimension", _enum(self.dimension, ParameterDimension, "parameter dimension"))
        if self.dimension is not ParameterDimension.PARAMETER and self.role is ParameterRole.PARAMETER:
            raise ValueError("only a named PARAMETER dimension may use the PARAMETER role")


@dataclass(frozen=True, slots=True)
class QueryProblemScope:
    input: str
    output: str
    query_language: str
    semantics: QuerySemantics
    constraints: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input", _text(self.input, "input"))
        object.__setattr__(self, "output", _text(self.output, "output"))
        object.__setattr__(self, "query_language", _text(self.query_language, "query_language"))
        object.__setattr__(self, "semantics", _enum(self.semantics, QuerySemantics, "semantics"))
        object.__setattr__(self, "constraints", _text_tuple(self.constraints, "constraints"))
        if not isinstance(self.parameters, tuple) or any(not isinstance(item, ParameterSpec) for item in self.parameters):
            raise ValueError("parameters must be an immutable tuple of ParameterSpec records")
        names = [item.name.casefold() for item in self.parameters]
        if len(set(names)) != len(names):
            raise ValueError("parameters cannot contain duplicate names")
        dimensions = [item.dimension for item in self.parameters]
        if dimensions.count(ParameterDimension.QUERY) != 1 or dimensions.count(ParameterDimension.DATA) != 1:
            raise ValueError("formal scope must identify exactly one QUERY and one DATA dimension")


_QUESTION_DIRECTIONS = {
    QuestionType.COMPLEXITY_BOUND: {ResultDirection.UPPER_BOUND, ResultDirection.LOWER_BOUND},
    QuestionType.DICHOTOMY: {ResultDirection.DICHOTOMY},
    QuestionType.TRACTABLE_FRAGMENT: {ResultDirection.TRACTABLE_FRAGMENT},
    QuestionType.HARDNESS: {ResultDirection.HARD_FRAGMENT},
    QuestionType.ENUMERATION: {ResultDirection.ENUMERATION},
    QuestionType.PARAMETERIZED: {ResultDirection.PARAMETERIZED},
    QuestionType.STRUCTURAL: {ResultDirection.STRUCTURAL},
    QuestionType.ALGORITHM: {ResultDirection.ALGORITHMIC},
    QuestionType.CERTIFICATE: {ResultDirection.CERTIFICATE},
}
_LOWER_CLASS = re.compile(r"(?:hard|complete|undecidable|lower|omega|Ω)", re.IGNORECASE)
_HARD_CLASS = re.compile(r"(?:hard|complete|undecidable)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TheoremResult:
    complexity_class: str
    direction: ResultDirection
    measure: ComplexityMeasure
    question_type: QuestionType

    def __post_init__(self) -> None:
        object.__setattr__(self, "complexity_class", _text(
            self.complexity_class, "complexity_class", max_words=20, max_chars=120
        ))
        object.__setattr__(self, "direction", _enum(self.direction, ResultDirection, "result direction"))
        object.__setattr__(self, "measure", _enum(self.measure, ComplexityMeasure, "complexity measure"))
        object.__setattr__(self, "question_type", _enum(self.question_type, QuestionType, "question type"))
        if self.direction not in _QUESTION_DIRECTIONS[self.question_type]:
            raise ValueError("result direction is inconsistent with question type")
        if self.direction is ResultDirection.LOWER_BOUND and not _LOWER_CLASS.search(self.complexity_class):
            raise ValueError("lower-bound direction is inconsistent with complexity class")
        if self.direction is ResultDirection.UPPER_BOUND and _HARD_CLASS.search(self.complexity_class):
            raise ValueError("upper-bound direction is inconsistent with a hardness complexity class")
        if self.direction is ResultDirection.HARD_FRAGMENT and not _HARD_CLASS.search(self.complexity_class):
            raise ValueError("hard-fragment direction requires an explicit hardness class")
        if self.question_type is QuestionType.ENUMERATION and self.measure not in {
            ComplexityMeasure.DELAY,
            ComplexityMeasure.PREPROCESSING,
        }:
            raise ValueError("enumeration result requires DELAY or PREPROCESSING measure")
        if self.question_type is QuestionType.PARAMETERIZED and self.measure is not ComplexityMeasure.PARAMETERIZED_COMPLEXITY:
            raise ValueError("parameterized result requires PARAMETERIZED_COMPLEXITY")


def validate_measure_roles(result: TheoremResult, scope: QueryProblemScope) -> None:
    """Validate complexity roles against the named QUERY/DATA/PARAMETER dimensions."""
    by_dimension = {item.dimension: item for item in scope.parameters}
    query_role = by_dimension[ParameterDimension.QUERY].role
    data_role = by_dimension[ParameterDimension.DATA].role
    if result.measure in {
        ComplexityMeasure.DATA_COMPLEXITY,
        ComplexityMeasure.DELAY,
        ComplexityMeasure.UPDATE_TIME,
        ComplexityMeasure.PREPROCESSING,
    }:
        if query_role is not ParameterRole.FIXED:
            raise ValueError(f"{result.measure.value} requires QUERY dimension role FIXED")
        if data_role is not ParameterRole.INPUT:
            raise ValueError(f"{result.measure.value} requires DATA dimension role INPUT")
    elif result.measure is ComplexityMeasure.COMBINED_COMPLEXITY:
        if query_role is not ParameterRole.INPUT:
            raise ValueError("COMBINED_COMPLEXITY requires QUERY dimension role INPUT")
        if data_role is not ParameterRole.INPUT:
            raise ValueError("COMBINED_COMPLEXITY requires DATA dimension role INPUT")
    elif result.measure is ComplexityMeasure.QUERY_COMPLEXITY:
        if query_role is not ParameterRole.INPUT:
            raise ValueError("QUERY_COMPLEXITY requires QUERY dimension role INPUT")
        if data_role is not ParameterRole.FIXED:
            raise ValueError("QUERY_COMPLEXITY requires DATA dimension role FIXED")
    elif result.measure is ComplexityMeasure.PARAMETERIZED_COMPLEXITY:
        named = [
            item for item in scope.parameters
            if item.dimension is ParameterDimension.PARAMETER and item.role is ParameterRole.PARAMETER
        ]
        if not named:
            raise ValueError("PARAMETERIZED_COMPLEXITY requires a named PARAMETER dimension with PARAMETER role")


def compare_scopes(candidate: QueryProblemScope, reference: QueryProblemScope) -> ScopeRelation:
    """Classify candidate scope relative to reference without lexical-overlap guessing."""
    if not isinstance(candidate, QueryProblemScope) or not isinstance(reference, QueryProblemScope):
        raise ValueError("scope comparison requires QueryProblemScope records")
    scalar_values = (
        candidate.input,
        candidate.output,
        candidate.query_language,
        reference.input,
        reference.output,
        reference.query_language,
    )
    if "UNKNOWN" in scalar_values or candidate.constraints == ("UNKNOWN",) or reference.constraints == ("UNKNOWN",):
        return ScopeRelation.UNKNOWN
    if (
        candidate.input != reference.input
        or candidate.output != reference.output
        or candidate.query_language != reference.query_language
        or candidate.semantics is not reference.semantics
        or candidate.parameters != reference.parameters
    ):
        return ScopeRelation.DISJOINT
    candidate_constraints = set(candidate.constraints)
    reference_constraints = set(reference.constraints)
    if candidate_constraints == reference_constraints:
        return ScopeRelation.EQUAL
    if candidate_constraints > reference_constraints:
        return ScopeRelation.NARROWER
    if candidate_constraints < reference_constraints:
        return ScopeRelation.BROADER
    return ScopeRelation.DISJOINT


_SCOPE_KEYS = frozenset({"input", "output", "query_language", "semantics", "constraints", "parameters"})
_RESULT_KEYS = frozenset({"complexity_class", "direction", "measure", "question_type"})


def scope_payload(scope: QueryProblemScope) -> dict[str, object]:
    return {
        "input": scope.input,
        "output": scope.output,
        "query_language": scope.query_language,
        "semantics": scope.semantics.value,
        "constraints": scope.constraints,
        "parameters": tuple({
            "name": item.name,
            "role": item.role.value,
            "dimension": item.dimension.value,
        } for item in scope.parameters),
    }


def result_payload(result: TheoremResult) -> dict[str, object]:
    return {
        "complexity_class": result.complexity_class,
        "direction": result.direction.value,
        "measure": result.measure.value,
        "question_type": result.question_type.value,
    }


def proof_technique_payload(signature: ProofTechniqueSignature) -> dict[str, object]:
    if not isinstance(signature, ProofTechniqueSignature):
        raise ValueError("theorem claim requires a ProofTechniqueSignature")
    return {
        "primary": signature.primary.value,
        "secondary": tuple(item.value for item in signature.secondary),
        "technical_obstacle": signature.technical_obstacle,
        "restriction_preservation_trick": signature.restriction_preservation_trick,
    }


def claim_for_theorem(
    scope: QueryProblemScope,
    results: tuple[TheoremResult, ...],
    assumptions: tuple[str, ...],
    proof_technique: ProofTechniqueSignature,
) -> Mapping[str, object]:
    if not isinstance(scope, QueryProblemScope):
        raise ValueError("theorem claim requires a QueryProblemScope")
    if not isinstance(results, tuple) or not results or any(not isinstance(item, TheoremResult) for item in results):
        raise ValueError("theorem claim requires a nonempty tuple of TheoremResult records")
    for result in results:
        validate_measure_roles(result, scope)
    normalized_assumptions = _text_tuple(assumptions, "assumptions")
    frozen = freeze_json({
        "claim_type": "THEOREM",
        "scope": scope_payload(scope),
        "results": tuple(result_payload(item) for item in results),
        "assumptions": normalized_assumptions,
        "proof_technique": proof_technique_payload(proof_technique),
    })
    assert isinstance(frozen, Mapping)
    return frozen


def scope_from_claim(payload: object) -> QueryProblemScope:
    if not isinstance(payload, Mapping) or frozenset(payload) != _SCOPE_KEYS:
        raise ValueError("structured claim scope has an invalid schema")
    parameters = payload["parameters"]
    if not isinstance(parameters, tuple):
        raise ValueError("structured claim parameters must be an immutable tuple")
    parsed_parameters: list[ParameterSpec] = []
    for item in parameters:
        if not isinstance(item, Mapping) or frozenset(item) != {"name", "role", "dimension"}:
            raise ValueError("structured claim parameter has an invalid schema")
        parsed_parameters.append(ParameterSpec(item["name"], item["role"], item["dimension"]))
    constraints = payload["constraints"]
    if not isinstance(constraints, tuple):
        raise ValueError("structured claim constraints must be an immutable tuple")
    return QueryProblemScope(
        input=payload["input"],
        output=payload["output"],
        query_language=payload["query_language"],
        semantics=payload["semantics"],
        constraints=constraints,
        parameters=tuple(parsed_parameters),
    )


def result_from_claim(payload: object) -> TheoremResult:
    if not isinstance(payload, Mapping) or frozenset(payload) != _RESULT_KEYS:
        raise ValueError("structured claim result has an invalid schema")
    return TheoremResult(
        complexity_class=payload["complexity_class"],
        direction=payload["direction"],
        measure=payload["measure"],
        question_type=payload["question_type"],
    )


def proof_technique_from_claim(payload: object) -> ProofTechniqueSignature:
    required = {"primary", "secondary", "technical_obstacle", "restriction_preservation_trick"}
    if not isinstance(payload, Mapping) or frozenset(payload) != required:
        raise ValueError("structured proof-technique claim has an invalid schema")
    secondary = payload["secondary"]
    if not isinstance(secondary, tuple):
        raise ValueError("structured secondary techniques must be an immutable tuple")
    return ProofTechniqueSignature(
        ProofTechnique(payload["primary"]),
        tuple(ProofTechnique(item) for item in secondary),
        payload["technical_obstacle"],
        payload["restriction_preservation_trick"],
    )


def theorem_support(
    pointer: EvidencePointer,
) -> tuple[QueryProblemScope, tuple[TheoremResult, ...], tuple[str, ...], ProofTechniqueSignature]:
    claim = pointer.claim
    required = {"claim_type", "scope", "results", "assumptions", "proof_technique"}
    if not isinstance(claim, Mapping) or frozenset(claim) != required:
        raise ValueError("authorized theorem evidence lacks a complete structured claim")
    if claim["claim_type"] != "THEOREM":
        raise ValueError("authorized theorem evidence has the wrong structured claim type")
    scope = scope_from_claim(claim["scope"])
    raw_results = claim["results"]
    if not isinstance(raw_results, tuple) or not raw_results:
        raise ValueError("authorized theorem evidence requires structured result signatures")
    results = tuple(result_from_claim(item) for item in raw_results)
    for result in results:
        validate_measure_roles(result, scope)
    assumptions = _text_tuple(claim["assumptions"], "structured theorem assumptions")
    signature = proof_technique_from_claim(claim["proof_technique"])
    return scope, results, assumptions, signature


@dataclass(frozen=True, slots=True)
class TheoremExtraction:
    theorem_id: str
    paraphrase: str
    scope: QueryProblemScope
    results: tuple[TheoremResult, ...]
    assumptions: tuple[str, ...]
    techniques: ProofTechniqueProfile
    evidence: EvidencePointer

    def __post_init__(self) -> None:
        object.__setattr__(self, "paraphrase", _text(self.paraphrase, "paraphrase"))
        if not isinstance(self.theorem_id, str) or not self.theorem_id.startswith("theorem:"):
            raise ValueError("theorem_id must be a canonical theorem ID")
        if not isinstance(self.scope, QueryProblemScope):
            raise ValueError("scope must be a QueryProblemScope")
        if not isinstance(self.results, tuple) or not self.results or any(
            not isinstance(item, TheoremResult) for item in self.results
        ):
            raise ValueError("results must be a nonempty immutable tuple of TheoremResult records")
        for result in self.results:
            validate_measure_roles(result, self.scope)
        object.__setattr__(self, "assumptions", _text_tuple(self.assumptions, "assumptions"))
        if not isinstance(self.techniques, ProofTechniqueProfile):
            raise ValueError("techniques must be a ProofTechniqueProfile")
        if not isinstance(self.evidence, EvidencePointer):
            raise ValueError("theorem extraction requires evidence")


_VALIDATED_THEOREM_TOKEN = object()


@dataclass(frozen=True, slots=True)
class ValidatedTheorem:
    theorem_id: str
    paper_id: str
    version_id: str
    paraphrase: str
    scope: QueryProblemScope
    results: tuple[TheoremResult, ...]
    assumptions: tuple[str, ...]
    techniques: ProofTechniqueProfile
    evidence: EvidencePointer
    authorization: TheoremAuthorization
    _validation_token: InitVar[object] = None

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _VALIDATED_THEOREM_TOKEN:
            raise ValueError("ValidatedTheorem can only be created by validate_theorem")


def validate_theorem(
    extraction: TheoremExtraction,
    deep_note: NoteRecord,
    authorization: TheoremAuthorization,
) -> ValidatedTheorem:
    """Validate extraction claims solely against the authorized pointer payload."""
    if not isinstance(extraction, TheoremExtraction):
        raise ValueError("extraction must be a TheoremExtraction")
    validate_note(deep_note)
    if deep_note.read_depth is not ReadingState.DEEP_READ:
        raise ValueError("theorem validation requires a DEEP_READ note")
    validate_theorem_authorization(authorization)
    if authorization.certificate != coverage_certificate(deep_note):
        raise ValueError("theorem authorization is not bound to the supplied deep note")
    if extraction.evidence != authorization.evidence:
        raise ValueError("theorem evidence does not match its authorization")
    validate_evidence_membership(extraction.evidence, deep_note)
    validate_techniques(extraction.techniques, deep_note)
    if extraction.techniques.evidence != extraction.evidence:
        raise ValueError("proof-technique evidence must match the authorized theorem source")
    supported_scope, supported_results, supported_assumptions, supported_technique = theorem_support(
        authorization.evidence
    )
    relation = compare_scopes(extraction.scope, supported_scope)
    if relation is not ScopeRelation.EQUAL:
        raise ValueError(
            f"source-extracted theorem scope must be EQUAL to the evidence-supported scope; "
            f"{relation.value.lower()} is a derived specialization or mismatch"
        )
    for claimed in extraction.results:
        if claimed not in supported_results:
            raise ValueError("theorem result is not in the authorized evidence-supported result signatures")
    if extraction.assumptions != supported_assumptions:
        raise ValueError("theorem assumptions do not match the authorized evidence claim")
    if technique_signature(extraction.techniques) != supported_technique:
        raise ValueError("proof technique signature does not match the authorized evidence claim")
    return ValidatedTheorem(
        theorem_id=extraction.theorem_id,
        paper_id=deep_note.paper_id,
        version_id=deep_note.version_id,
        paraphrase=extraction.paraphrase,
        scope=extraction.scope,
        results=extraction.results,
        assumptions=extraction.assumptions,
        techniques=extraction.techniques,
        evidence=extraction.evidence,
        authorization=authorization,
        _validation_token=_VALIDATED_THEOREM_TOKEN,
    )
