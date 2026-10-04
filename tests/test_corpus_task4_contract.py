from __future__ import annotations

import pytest

from db_theory_atlas.corpus_task4 import (
    ExactSourceLocation,
    FormalProblemScope,
    ParameterRole,
    ParameterRoleBinding,
    ScopeValue,
    TheoremRecord,
)


def _scope() -> FormalProblemScope:
    return FormalProblemScope(
        formal_problem="evaluate a query",
        parameter_roles=(
            ParameterRoleBinding("database", ParameterRole.INPUT),
            ParameterRoleBinding("query", ParameterRole.FIXED),
            ParameterRoleBinding("width", ParameterRole.PARAMETER),
        ),
        data_vs_combined="DATA_COMPLEXITY",
        arity="BOUNDED_ARITY",
        boolean="BOOLEAN",
        query_fragment="CQ",
        semantics="SET",
        domain="FINITE",
        execution_mode="STATIC",
        randomness="DETERMINISTIC",
        preprocessing="NOT_APPLICABLE",
        query_time="POLYNOMIAL",
        delay="NOT_APPLICABLE",
        total_time="NOT_STATED_IN_SOURCE",
    )


def test_contract_rejects_blank_required_fields_and_accepts_explicit_sentinels() -> None:
    location = ExactSourceLocation(page=3, section="3 Preliminaries", label="Theorem 1")
    scope = _scope()
    record = TheoremRecord(
        theorem_id="theorem:contract-only",
        paper_id="paper:contract-only",
        version_id="version:contract-only",
        source_hash="a" * 64,
        source_location=location,
        formal_scope=scope,
        statement="A source-bound contract record, not a theorem claim.",
    )

    assert record.formal_scope.total_time is ScopeValue.NOT_STATED_IN_SOURCE
    with pytest.raises(ValueError, match="section"):
        ExactSourceLocation(page=1, section=" ", label="Theorem 1")
    with pytest.raises(ValueError, match="formal_problem"):
        FormalProblemScope(
            formal_problem="",
            parameter_roles=_scope().parameter_roles,
            data_vs_combined="DATA_COMPLEXITY",
            arity="BOUNDED_ARITY",
            boolean="BOOLEAN",
            query_fragment="CQ",
            semantics="SET",
            domain="FINITE",
            execution_mode="STATIC",
            randomness="DETERMINISTIC",
            preprocessing="NOT_APPLICABLE",
            query_time="POLYNOMIAL",
            delay="NOT_APPLICABLE",
            total_time="NOT_STATED_IN_SOURCE",
        )


def test_formal_scope_requires_fixed_input_and_parameter_roles_and_all_laundering_axes() -> None:
    scope = _scope()

    assert {binding.role for binding in scope.parameter_roles} == {
        ParameterRole.FIXED,
        ParameterRole.INPUT,
        ParameterRole.PARAMETER,
    }
    with pytest.raises(ValueError, match="FIXED, INPUT, and PARAMETER"):
        FormalProblemScope(
            formal_problem="evaluate a query",
            parameter_roles=(
                ParameterRoleBinding("database", ParameterRole.INPUT),
                ParameterRoleBinding("query", ParameterRole.FIXED),
            ),
            data_vs_combined="DATA_COMPLEXITY",
            arity="BOUNDED_ARITY",
            boolean="BOOLEAN",
            query_fragment="CQ",
            semantics="SET",
            domain="FINITE",
            execution_mode="STATIC",
            randomness="DETERMINISTIC",
            preprocessing="NOT_APPLICABLE",
            query_time="POLYNOMIAL",
            delay="NOT_APPLICABLE",
            total_time="NOT_STATED_IN_SOURCE",
        )
