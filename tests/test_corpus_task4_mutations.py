from __future__ import annotations

import pytest

import scripts.assemble_corpus_task4 as assembler
from scripts.assemble_corpus_task4 import (
    REQUIRED_MUTATION_IDS, Task4ValidationError, run_required_mutation_suite,
)


def test_required_mutations_are_detected_by_real_fragment_validation() -> None:
    results = run_required_mutation_suite()

    assert tuple(result.mutation_id for result in results) == REQUIRED_MUTATION_IDS
    assert {result.disposition.value for result in results} == {"DETECTED"}
    assert {result.reason for result in results} == set(REQUIRED_MUTATION_IDS)


@pytest.mark.parametrize("mutation_id", REQUIRED_MUTATION_IDS)
def test_each_required_mutation_has_its_own_real_detection(mutation_id: str) -> None:
    result = {item.mutation_id: item for item in run_required_mutation_suite()}[mutation_id]

    assert result.disposition.value == "DETECTED"
    assert result.reason == mutation_id


def test_mutation_suite_runs_an_independent_clean_and_mutated_validation_for_every_id(monkeypatch: pytest.MonkeyPatch) -> None:
    actual = assembler._validate_rows
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return actual(*args, **kwargs)

    monkeypatch.setattr(assembler, "_validate_rows", counted)
    assert {item.disposition.value for item in run_required_mutation_suite()} == {"DETECTED"}
    assert calls == 2 * len(REQUIRED_MUTATION_IDS)


def test_mutation_is_not_detected_when_its_clean_control_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    actual = assembler._validate_rows
    calls = 0

    def fail_first_clean(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Task4ValidationError("T4M1", "simulated invalid clean control")
        return actual(*args, **kwargs)

    monkeypatch.setattr(assembler, "_validate_rows", fail_first_clean)
    result = run_required_mutation_suite()[0]
    assert result.disposition.value == "NOT_DETECTED"
    assert result.reason == "CLEAN_CONTROL_T4M1"


def test_mutation_is_not_detected_when_mutant_fails_with_another_code(monkeypatch: pytest.MonkeyPatch) -> None:
    actual = assembler._validate_rows
    calls = 0

    def wrong_second_code(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise Task4ValidationError("T4M2", "simulated wrong-code rejection")
        return actual(*args, **kwargs)

    monkeypatch.setattr(assembler, "_validate_rows", wrong_second_code)
    result = run_required_mutation_suite()[0]
    assert result.disposition.value == "NOT_DETECTED"
    assert result.reason == "T4M2"
