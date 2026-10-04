from dataclasses import replace

import pytest

from db_theory_atlas.collision import CollisionRecord, CollisionSeverity
from db_theory_atlas.graph import GraphEvidence
from db_theory_atlas.ranking import (
    BENEFIT_THRESHOLD,
    DirectionCategory,
    DirectionScore,
    RankedDirection,
    rank_open_directions,
)
from test_problems import complete_search, explicit_extraction, original_problem, problem_note
from test_collision import collision_for_severity
from db_theory_atlas.model import OpenStatus
from db_theory_atlas.problems import validate_open_problem
from db_theory_atlas.serialization import freeze_json


SCORE_FIELDS = {
    "ICDT_fit", "novelty_potential", "theorem_depth", "naturalness",
    "four_week_feasibility", "implementation_support", "prior_art_density", "proof_risk",
}


def score(*, benefit: int = 8, prior_art: int = 2, proof_risk: int = 3,
          feasibility: int | None = None, pointer=None) -> DirectionScore:
    source = GraphEvidence(pointer or original_problem().evidence, problem_note())
    values = {
        "ICDT_fit": benefit,
        "novelty_potential": benefit,
        "theorem_depth": benefit,
        "naturalness": benefit,
        "four_week_feasibility": feasibility if feasibility is not None else benefit,
        "implementation_support": benefit,
        "prior_art_density": prior_art,
        "proof_risk": proof_risk,
    }
    return DirectionScore(
        **values,
        reasons={name: f"The verified source supports the controlled {name} assessment." for name in SCORE_FIELDS},
        source_pointers=(source,),
    )


def collision(severity: CollisionSeverity = CollisionSeverity.NONE) -> CollisionRecord:
    return collision_for_severity(severity)


def direction(identifier: str, direction_score: DirectionScore, severity: CollisionSeverity = CollisionSeverity.NONE,
              *, verified_open: bool = True, findings: tuple[str, ...] = ()) -> RankedDirection:
    if verified_open:
        search = complete_search()
        problem = validate_open_problem(
            explicit_extraction(status=OpenStatus.OPEN_VERIFIED, followup_search=search),
            problem_note(),
        )
    else:
        problem = original_problem()
    return RankedDirection(
        identifier,
        f"Direction {identifier}",
        problem,
        direction_score,
        collision(severity),
        findings,
    )


def test_direction_score_requires_all_eight_integer_bounds_reasons_and_sources() -> None:
    assert SCORE_FIELDS <= {field.name for field in __import__("dataclasses").fields(DirectionScore)}
    for field in SCORE_FIELDS:
        with pytest.raises(ValueError, match="0..10|integer"):
            replace(score(), **{field: 11})
        with pytest.raises(ValueError, match="0..10|integer"):
            replace(score(), **{field: True})
    with pytest.raises(ValueError, match="reason"):
        replace(score(), reasons={"ICDT_fit": "Only one reason."})
    with pytest.raises(ValueError, match="source"):
        replace(score(), source_pointers=())


def test_direction_score_rejects_naked_verified_pointer_without_note_membership() -> None:
    naked = replace(
        original_problem().evidence,
        paper_id="paper:missing",
        version_id="version:missing",
        source_hash="f" * 64,
    )

    with pytest.raises(ValueError, match="note|membership|GraphEvidence|source evidence"):
        replace(score(), source_pointers=(naked,))
    with pytest.raises(ValueError, match="exact member|paper/version/source hash|paper_id|version_id|source_hash"):
        replace(score(), source_pointers=(GraphEvidence(naked, problem_note()),))


def test_direction_score_source_order_uses_complete_scientific_identity() -> None:
    note = problem_note()
    first = GraphEvidence(original_problem().evidence, note)
    second_pointer = replace(
        first.pointer,
        claim=freeze_json({
            "claim_type": "RANKING_SUPPORT",
            "dimension": "proof_risk",
        }),
    )
    second = GraphEvidence(
        second_pointer,
        replace(note, evidence=note.evidence + (second_pointer,)),
    )

    forward = replace(score(), source_pointers=(first, second))
    reverse = replace(score(), source_pointers=(second, first))
    forward_ids = tuple(item.identity for item in forward.source_pointers)
    reverse_ids = tuple(item.identity for item in reverse.source_pointers)

    assert forward_ids == reverse_ids == tuple(sorted((first.identity, second.identity)))


def test_formula_keeps_benefits_and_risks_separate() -> None:
    low_risk = score(benefit=8, prior_art=1, proof_risk=1)
    high_risk = score(benefit=8, prior_art=10, proof_risk=10)

    assert low_risk.benefit_score == high_risk.benefit_score
    assert low_risk.risk_score < high_risk.risk_score
    assert low_risk.overall_score > high_risk.overall_score
    assert BENEFIT_THRESHOLD > 0


def test_all_four_categories_have_explicit_risk_aware_thresholds() -> None:
    ranked = rank_open_directions((
        direction("a", score(benefit=9, prior_art=1, proof_risk=2)),
        direction("b", score(benefit=9, prior_art=2, proof_risk=8)),
        direction("c", score(benefit=9, prior_art=9, proof_risk=4), CollisionSeverity.STRONG),
        direction("d", score(benefit=10, prior_art=0, proof_risk=0), CollisionSeverity.DIRECT),
    ))
    by_id = {item.direction_id: item for item in ranked}
    assert by_id["a"].category is DirectionCategory.HIGH_VALUE_FEASIBLE
    assert by_id["b"].category is DirectionCategory.HIGH_VALUE_HARD
    assert by_id["c"].category is DirectionCategory.INTERESTING_BUT_COLLISION_RISK
    assert by_id["d"].category is DirectionCategory.LIKELY_SOLVED_DO_NOT_USE
    assert by_id["d"].recommended is False


def test_stable_ordering_uses_category_score_then_identifier() -> None:
    same = score(benefit=8, prior_art=2, proof_risk=2)
    ranked = rank_open_directions((direction("z", same), direction("a", same), direction("m", same)))
    assert tuple(item.direction_id for item in ranked) == ("a", "m", "z")
    assert tuple(item.rank for item in ranked) == (1, 2, 3)


def test_top50_requires_verified_sources_completed_2026_audit_and_no_s2_s3() -> None:
    good = direction("good", score())
    hard = direction("hard", score(proof_risk=8))
    stale = direction("stale", score(), verified_open=False)
    s2 = direction("s2", score(), findings=("S2: unresolved promoted-record conflict",))
    strong = direction("strong", score(), CollisionSeverity.STRONG)
    direct = direction("direct", score(), CollisionSeverity.DIRECT)
    ranked = {
        item.direction_id: item
        for item in rank_open_directions((good, hard, stale, s2, strong, direct))
    }

    assert ranked["good"].top_50_eligible is True
    assert ranked["good"].recommended is True
    assert ranked["hard"].category is DirectionCategory.HIGH_VALUE_HARD
    assert ranked["hard"].top_50_eligible is True
    assert ranked["hard"].recommended is True
    assert ranked["stale"].top_50_eligible is False
    assert ranked["s2"].top_50_eligible is False
    assert ranked["strong"].top_50_eligible is True
    assert ranked["strong"].recommended is False
    assert ranked["direct"].top_50_eligible is True
    assert ranked["direct"].recommended is False


def test_top50_recency_audit_must_bind_exact_problem_id_and_fingerprint() -> None:
    wrong_id = direction("wrong-id", score())
    object.__setattr__(
        wrong_id.problem,
        "followup_search",
        replace(wrong_id.problem.followup_search, problem_id="problem:other"),
    )
    wrong_fingerprint = direction("wrong-fingerprint", score())
    object.__setattr__(
        wrong_fingerprint.problem,
        "followup_search",
        replace(wrong_fingerprint.problem.followup_search, query_fingerprint="0" * 64),
    )

    ranked = {
        item.direction_id: item
        for item in rank_open_directions((wrong_id, wrong_fingerprint))
    }

    assert ranked["wrong-id"].top_50_eligible is False
    assert ranked["wrong-fingerprint"].top_50_eligible is False


def test_top50_replays_complete_task5_audit_for_open_and_likely_open_statuses() -> None:
    base = complete_search()
    first_manifest = base.manifests[0]
    forgeries = (
        replace(base, result_candidates=(), open_status_evidence=()),
        replace(base, queries=base.queries[:1], manifests=base.manifests[:1]),
        replace(base, open_status_evidence=()),
        replace(base, manifests=(replace(first_manifest, manifest_hash="f" * 64),) + base.manifests[1:]),
    )
    directions = []
    for index, forged in enumerate(forgeries):
        item = direction(f"open-forgery-{index}", score())
        object.__setattr__(item.problem, "followup_search", forged)
        directions.append(item)

    likely = direction("likely-open-forgery", score(), verified_open=False)
    object.__setattr__(likely.problem, "followup_search", forgeries[0])
    directions.append(likely)

    ranked = rank_open_directions(tuple(directions))

    assert all(item.top_50_eligible is False for item in ranked)


def test_high_benefit_does_not_override_collision_or_proof_risk() -> None:
    risky = direction("risky", score(benefit=10, prior_art=1, proof_risk=10))
    collided = direction("collided", score(benefit=10, prior_art=0, proof_risk=0), CollisionSeverity.STRONG)
    ranked = {item.direction_id: item for item in rank_open_directions((risky, collided))}

    assert ranked["risky"].category is DirectionCategory.HIGH_VALUE_HARD
    assert ranked["collided"].category is DirectionCategory.INTERESTING_BUT_COLLISION_RISK
    assert ranked["collided"].recommended is False
