from db_theory_atlas.theorems import (
    ComplexityMeasure,
    ParameterDimension,
    ParameterRole,
    ParameterSpec,
    QueryProblemScope,
    QuerySemantics,
    QuestionType,
    ResultDirection,
    TheoremResult,
    claim_for_theorem,
)
from db_theory_atlas.techniques import ProofTechnique, ProofTechniqueSignature


def default_scope() -> QueryProblemScope:
    return QueryProblemScope(
        input="finite relational database",
        output="query answers",
        query_language="conjunctive queries",
        semantics=QuerySemantics.SET,
        constraints=("relational instances", "bounded arity"),
        parameters=(
            ParameterSpec("query", ParameterRole.FIXED, ParameterDimension.QUERY),
            ParameterSpec("database", ParameterRole.INPUT, ParameterDimension.DATA),
        ),
    )


def default_result() -> TheoremResult:
    return TheoremResult(
        "PTIME",
        ResultDirection.UPPER_BOUND,
        ComplexityMeasure.DATA_COMPLEXITY,
        QuestionType.COMPLEXITY_BOUND,
    )


def default_technique_signature():
    return ProofTechniqueSignature(
        ProofTechnique.HOMOMORPHISM,
        (ProofTechnique.CANONICAL_DATABASE,),
        "Preserving the stated bounded-arity restriction during the homomorphism construction.",
        "Use the canonical database only within the stated fragment.",
    )


def theorem_claim():
    return claim_for_theorem(
        default_scope(),
        (default_result(),),
        ("finite relational structures",),
        default_technique_signature(),
    )


def open_problem_claim():
    scope = theorem_claim()["scope"]
    requested_result = theorem_claim()["results"][0]
    return {
        "claim_type": "OPEN_PROBLEM",
        "scope": scope,
        "requested_result": requested_result,
        "restricted_scope": None,
        "remaining_scope": scope,
    }
