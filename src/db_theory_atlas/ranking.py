"""Risk-separated deterministic ranking of validated open directions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from fractions import Fraction
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from .collision import CollisionRecord, CollisionSeverity
from .graph import GraphEvidence
from .model import OpenStatus
from .problems import OpenProblemExtraction, ValidatedOpenProblem, problem_fingerprint, validate_open_problem


class DirectionCategory(str, Enum):
    HIGH_VALUE_FEASIBLE = "HIGH_VALUE_FEASIBLE"
    HIGH_VALUE_HARD = "HIGH_VALUE_HARD"
    INTERESTING_BUT_COLLISION_RISK = "INTERESTING_BUT_COLLISION_RISK"
    LIKELY_SOLVED_DO_NOT_USE = "LIKELY_SOLVED_DO_NOT_USE"


RankingCategory = DirectionCategory


BENEFIT_WEIGHTS: Mapping[str, int] = MappingProxyType({
    "ICDT_fit": 22,
    "novelty_potential": 22,
    "theorem_depth": 18,
    "naturalness": 14,
    "four_week_feasibility": 16,
    "implementation_support": 8,
})
RISK_WEIGHTS: Mapping[str, int] = MappingProxyType({
    "prior_art_density": 60,
    "proof_risk": 40,
})
SCORE_FIELDS = tuple(BENEFIT_WEIGHTS) + tuple(RISK_WEIGHTS)
BENEFIT_THRESHOLD = Fraction(7, 1)
RISK_THRESHOLD = Fraction(5, 1)
FEASIBILITY_THRESHOLD = 6
PROOF_RISK_THRESHOLD = 6
COLLISION_RISK_THRESHOLD = 8


def _score(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
        raise ValueError(f"{label} must be an integer in 0..10")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty")
    compact = " ".join(value.split())
    if len(compact) > 600 or len(compact.split()) > 80:
        raise ValueError(f"{label} must be concise")
    return compact


@dataclass(frozen=True, slots=True)
class DirectionScore:
    ICDT_fit: int
    novelty_potential: int
    theorem_depth: int
    naturalness: int
    four_week_feasibility: int
    implementation_support: int
    prior_art_density: int
    proof_risk: int
    reasons: Mapping[str, str]
    source_pointers: tuple[GraphEvidence, ...]

    def __post_init__(self) -> None:
        for name in SCORE_FIELDS:
            object.__setattr__(self, name, _score(getattr(self, name), name))
        if not isinstance(self.reasons, Mapping) or set(self.reasons) != set(SCORE_FIELDS):
            raise ValueError("score reasons must cover exactly all eight dimensions")
        normalized = {name: _text(self.reasons[name], f"{name} reason") for name in SCORE_FIELDS}
        object.__setattr__(self, "reasons", MappingProxyType(normalized))
        if not isinstance(self.source_pointers, tuple) or not self.source_pointers:
            raise ValueError("direction score requires note-backed source evidence")
        if any(not isinstance(item, GraphEvidence) for item in self.source_pointers):
            raise ValueError("direction score sources must be note-backed GraphEvidence records")
        for item in self.source_pointers:
            item.validate_membership()
        pointer_identities = tuple(item.identity for item in self.source_pointers)
        if len(set(pointer_identities)) != len(pointer_identities):
            raise ValueError("direction score source evidence cannot contain duplicates")
        object.__setattr__(self, "source_pointers", tuple(sorted(
            self.source_pointers,
            key=lambda item: item.identity,
        )))

    @property
    def benefit_score(self) -> Fraction:
        """Weighted 0..10 benefit score; risk fields are deliberately absent."""

        return Fraction(sum(BENEFIT_WEIGHTS[name] * getattr(self, name) for name in BENEFIT_WEIGHTS), 100)

    @property
    def risk_score(self) -> Fraction:
        """Weighted 0..10 risk score kept separate from benefit presentation."""

        return Fraction(sum(RISK_WEIGHTS[name] * getattr(self, name) for name in RISK_WEIGHTS), 100)

    @property
    def overall_score(self) -> Fraction:
        """Explicit ordering formula: benefit minus one-half of risk."""

        return self.benefit_score - self.risk_score / 2


@dataclass(frozen=True, slots=True)
class RankedDirection:
    direction_id: str
    title: str
    problem: ValidatedOpenProblem
    score: DirectionScore
    collision: CollisionRecord
    data_quality_findings: tuple[str, ...] = ()
    category: DirectionCategory | None = None
    top_50_eligible: bool = False
    recommended: bool = False
    rank: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.direction_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", self.direction_id):
            raise ValueError("direction_id must be a stable normalized identifier")
        object.__setattr__(self, "title", _text(self.title, "direction title"))
        if not isinstance(self.problem, ValidatedOpenProblem):
            raise ValueError("ranked direction requires a validated open problem")
        if not isinstance(self.score, DirectionScore) or not isinstance(self.collision, CollisionRecord):
            raise ValueError("ranked direction requires DirectionScore and CollisionRecord records")
        if self.collision.left_id != self.problem.problem_id:
            raise ValueError("collision record must be bound to the ranked open problem")
        if not isinstance(self.data_quality_findings, tuple) or any(
            not isinstance(item, str) or not re.match(r"^S[0-3]:\s+\S", item) for item in self.data_quality_findings
        ):
            raise ValueError("data-quality findings must use explicit S0..S3 labels")
        if self.category is not None and not isinstance(self.category, DirectionCategory):
            raise ValueError("category must be a DirectionCategory or None")
        if not isinstance(self.top_50_eligible, bool) or not isinstance(self.recommended, bool):
            raise ValueError("eligibility and recommendation flags must be booleans")
        if self.rank is not None and (isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1):
            raise ValueError("rank must be a positive integer or None")


def _category(direction: RankedDirection) -> DirectionCategory:
    score = direction.score
    collision = direction.collision.severity
    if direction.problem.status is OpenStatus.RESOLVED or collision is CollisionSeverity.DIRECT:
        return DirectionCategory.LIKELY_SOLVED_DO_NOT_USE
    if (
        collision is CollisionSeverity.STRONG
        or score.prior_art_density >= COLLISION_RISK_THRESHOLD
        or score.benefit_score < BENEFIT_THRESHOLD
    ):
        return DirectionCategory.INTERESTING_BUT_COLLISION_RISK
    if (
        score.four_week_feasibility >= FEASIBILITY_THRESHOLD
        and score.proof_risk <= PROOF_RISK_THRESHOLD
        and score.risk_score <= RISK_THRESHOLD
    ):
        return DirectionCategory.HIGH_VALUE_FEASIBLE
    return DirectionCategory.HIGH_VALUE_HARD


def _top_50_eligible(direction: RankedDirection) -> bool:
    search = direction.problem.followup_search
    expected_fingerprint = problem_fingerprint(
        direction.problem.problem_id,
        direction.problem.scope,
        direction.problem.requested_result,
    )
    no_severe_findings = not any(item.startswith(("S2:", "S3:")) for item in direction.data_quality_findings)
    source_context = next((
        item
        for item in direction.score.source_pointers
        if item.pointer == direction.problem.evidence
        and item.note.paper_id == direction.problem.paper_id
        and item.note.version_id == direction.problem.version_id
    ), None)
    source_verified = source_context is not None
    audit_replayed = False
    if source_context is not None:
        extraction = OpenProblemExtraction(
            problem_id=direction.problem.problem_id,
            paraphrase=direction.problem.paraphrase,
            scope=direction.problem.scope,
            requested_result=direction.problem.requested_result,
            explicitness=direction.problem.explicitness,
            evidence=direction.problem.evidence,
            status=direction.problem.status,
            followup_search=search,
            restricted_case_evidence=direction.problem.restricted_case_evidence,
            unresolved_case_evidence=direction.problem.unresolved_case_evidence,
        )
        try:
            replayed_problem = validate_open_problem(extraction, source_context.note)
            if replayed_problem == direction.problem:
                validate_open_problem(
                    replace(extraction, status=OpenStatus.OPEN_VERIFIED),
                    source_context.note,
                )
                audit_replayed = True
        except ValueError:
            audit_replayed = False
    recency_complete = (
        search is not None
        and search.problem_id == direction.problem.problem_id
        and search.query_fingerprint == expected_fingerprint
        and direction.problem.problem_fingerprint == expected_fingerprint
        and search.completed
        and search.reviewer_verified
        and search.through_year >= 2026
        and audit_replayed
    )
    return (
        direction.problem.status is not OpenStatus.RESOLVED
        and source_verified
        and recency_complete
        and no_severe_findings
    )


_CATEGORY_ORDER = {
    DirectionCategory.HIGH_VALUE_FEASIBLE: 0,
    DirectionCategory.HIGH_VALUE_HARD: 1,
    DirectionCategory.INTERESTING_BUT_COLLISION_RISK: 2,
    DirectionCategory.LIKELY_SOLVED_DO_NOT_USE: 3,
}


def rank_open_directions(directions: Iterable[RankedDirection]) -> tuple[RankedDirection, ...]:
    """Categorize and rank with stable risk-aware ordering and eligibility gates."""

    supplied = tuple(directions)
    if any(not isinstance(item, RankedDirection) for item in supplied):
        raise ValueError("rank_open_directions requires RankedDirection records")
    identifiers = tuple(item.direction_id for item in supplied)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("ranked direction IDs must be unique")

    categorized = []
    for item in supplied:
        category = _category(item)
        eligible = _top_50_eligible(item)
        recommended = eligible and category in {
            DirectionCategory.HIGH_VALUE_FEASIBLE,
            DirectionCategory.HIGH_VALUE_HARD,
        }
        categorized.append(replace(
            item,
            category=category,
            top_50_eligible=eligible,
            recommended=recommended,
            rank=None,
        ))
    categorized.sort(key=lambda item: (
        _CATEGORY_ORDER[item.category],
        -item.score.overall_score,
        item.direction_id,
    ))
    return tuple(replace(item, rank=index) for index, item in enumerate(categorized, start=1))
