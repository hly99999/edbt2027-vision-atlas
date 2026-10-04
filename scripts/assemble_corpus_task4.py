"""Fail-closed assembly for source-bound Corpus Task 4 fragments.

The command intentionally accepts only compact JSONL extraction fragments.  It
does not read PDFs or infer theorem claims; all semantic checks are made
against the Task 1 source-map text supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Mapping

from db_theory_atlas.corpus_task4 import (
    CacheBinding, CollisionPrimitive, CompleteTheoremSourceAuthorization, ComplexityMeasure, CoverageDisposition,
    ExactSourceLocation, ExtractionCoverage, FormalProblemScope, MutationDisposition,
    FROZEN_TASK3_CLOSURE_SHA256, FrozenTask4Corpus, MutationResult, PageTextBlock, ParameterRoleBinding, ProofTechnique,
    ProofTechniqueKind, ProofTechniqueRole, ScopeAudit, ScopeValue, TheoremRecord, TheoremRelation,
    TheoremClaimForm, TheoremRelationKind, TheoremRole, TheoremResultType, TheoremSourceMap,
    build_frozen_task4_corpus, canonical_json, canonical_sha256, is_test_frozen_task4_corpus,
    is_verified_frozen_task4_corpus,
    validate_complete_theorem_source,
    _page_block, _with_active_sections,
)


REQUIRED_MUTATION_IDS = tuple(f"T4M{number}" for number in range(1, 21))
_SENTINELS = {item.value for item in ScopeValue}


class Task4ValidationError(ValueError):
    """A deterministic validation error whose code is safe to report."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ValidatedTask4Fragment:
    theorem_records: tuple[TheoremRecord, ...]
    theorem_relations: tuple[TheoremRelation, ...]
    proof_techniques: tuple[ProofTechnique, ...]
    scope_audits: tuple[ScopeAudit, ...]
    coverage: tuple[ExtractionCoverage, ...]
    collision_primitives: tuple[CollisionPrimitive, ...]
    mutation_results: tuple[MutationResult, ...]

    def __iter__(self):
        return iter(
            self.theorem_records + self.theorem_relations + self.proof_techniques
            + self.scope_audits + self.coverage + self.collision_primitives + self.mutation_results
        )


def _fail(code: str, message: str) -> None:
    raise Task4ValidationError(code, message)


def _rows(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        _fail("T4V01", f"fragment is missing: {path}")
    result: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as caught:
            raise Task4ValidationError("T4V02", f"invalid JSONL at {path}:{line_number}") from caught
        if not isinstance(row, dict):
            _fail("T4V03", f"row {line_number} is not a JSON object")
        result.append(row)
    return tuple(result)


def _source_index(source_maps: Iterable[TheoremSourceMap]) -> dict[tuple[str, str, str], TheoremSourceMap]:
    maps = tuple(source_maps)
    if not maps or any(not isinstance(item, TheoremSourceMap) for item in maps):
        _fail("T4V04", "source_maps must contain bound Task 1 source maps")
    index = {(item.paper_id, item.version_id, item.source_hash): item for item in maps}
    if len(index) != len(maps):
        _fail("T4V05", "source maps contain duplicate paper/version/hash identities")
    return index


def _trusted_context(
    frozen_corpus: object,
    source_maps: Iterable[TheoremSourceMap],
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
) -> tuple[FrozenTask4Corpus, dict[tuple[str, str, str], TheoremSourceMap], Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization]]:
    verified = is_verified_frozen_task4_corpus(frozen_corpus)
    if not isinstance(frozen_corpus, FrozenTask4Corpus) or not verified:
        _fail("T4V17", "a real FrozenTask4Corpus is required")
    supplied = tuple(source_maps)
    maps = _source_index(supplied)
    frozen = tuple(frozen_corpus.source_maps)
    if len(supplied) != len(frozen) or any(
        found is None or canonical_sha256(item.as_dict()) != canonical_sha256(found.as_dict())
        for item in frozen
        for found in (maps.get((item.paper_id, item.version_id, item.source_hash)),)
    ):
        _fail("T4V17", "source_maps must exactly match the real frozen corpus")
    if not isinstance(source_authorizations, Mapping):
        _fail("T4V17", "complete-theorem source capabilities are required")
    required_identities = set(maps)
    if set(source_authorizations) != required_identities:
        _fail("T4V17", "complete-theorem source capability keys must exactly match the frozen corpus")
    for identity, source_map in maps.items():
        authorization = source_authorizations.get(identity)
        if not isinstance(authorization, CompleteTheoremSourceAuthorization):
            _fail("T4V17", "every frozen source requires its issued complete-theorem capability")
        if authorization.corpus is not frozen_corpus:
            _fail("T4V17", "complete-theorem capability was issued by a different frozen corpus")
        try:
            validate_complete_theorem_source(source_map, authorization)
        except ValueError as caught:
            raise Task4ValidationError("T4V17", str(caught)) from caught
    return frozen_corpus, maps, source_authorizations


def _trusted_test_context(
    frozen_corpus: object,
    source_maps: Iterable[TheoremSourceMap],
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
) -> tuple[FrozenTask4Corpus, dict[tuple[str, str, str], TheoremSourceMap], Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization]]:
    """Private fixture-only context used by the in-module mutation harness."""

    if not isinstance(frozen_corpus, FrozenTask4Corpus) or not is_test_frozen_task4_corpus(frozen_corpus):
        _fail("T4V17", "test validation requires an explicit test fixture corpus")
    supplied = tuple(source_maps)
    maps = _source_index(supplied)
    frozen = tuple(frozen_corpus.source_maps)
    if len(supplied) != len(frozen) or any(
        found is None or canonical_sha256(item.as_dict()) != canonical_sha256(found.as_dict())
        for item in frozen
        for found in (maps.get((item.paper_id, item.version_id, item.source_hash)),)
    ):
        _fail("T4V17", "source_maps must exactly match the test fixture corpus")
    if not isinstance(source_authorizations, Mapping) or set(source_authorizations) != set(maps):
        _fail("T4V17", "test fixture capabilities must cover every source")
    for identity, source_map in maps.items():
        authorization = source_authorizations.get(identity)
        if not isinstance(authorization, CompleteTheoremSourceAuthorization) or authorization.corpus is not frozen_corpus:
            _fail("T4V17", "complete-theorem capability was issued by a different frozen corpus")
        try:
            validate_complete_theorem_source(source_map, authorization)
        except ValueError as caught:
            raise Task4ValidationError("T4V17", str(caught)) from caught
    return frozen_corpus, maps, source_authorizations


def _location(raw: object, identity: tuple[str, str, str] | None = None) -> ExactSourceLocation:
    if not isinstance(raw, Mapping):
        _fail("T4V06", "source_location must be an object")
    if identity is None:
        supplied = tuple(raw.get(field) for field in ("paper_id", "version_id", "source_hash"))
        identity = supplied if all(isinstance(item, str) for item in supplied) else None  # type: ignore[assignment]
    elif any(raw.get(field) is not None for field in ("paper_id", "version_id", "source_hash")):
        supplied = tuple(raw.get(field) for field in ("paper_id", "version_id", "source_hash"))
        if supplied != identity:
            _fail("T4M8", "source location identity does not match its record source")
    try:
        return ExactSourceLocation(
            raw.get("page"), raw.get("section"), raw.get("label"),
            *(identity if identity is not None else (None, None, None)),
        )
    except ValueError as caught:
        raise Task4ValidationError("T4V06", str(caught)) from caught


def _bound_location(location: ExactSourceLocation, source_map: TheoremSourceMap) -> None:
    location_identity = (location.paper_id, location.version_id, location.source_hash)
    if any(item is not None for item in location_identity) and location_identity != (
        source_map.paper_id, source_map.version_id, source_map.source_hash,
    ):
        _fail("T4M8", "source location identity does not match bound source map")
    if location.page > source_map.page_count:
        _fail("T4M8", "source page does not exist in bound source map")
    block = source_map.page_blocks[location.page - 1]
    if not isinstance(location.section, ScopeValue) and location.section not in block.section_headings:
        _fail("T4M8", "source section does not exist in bound source-map page block")
    if not isinstance(location.label, ScopeValue) and location.label not in block.theorem_labels:
        _fail("T4M8", "theorem label does not exist in bound source-map page block")
    if not isinstance(location.section, ScopeValue) and not isinstance(location.label, ScopeValue):
        if not any(
            item.label == location.label and item.section_heading == location.section
            for item in block.statement_blocks
        ):
            _fail("T4M8", "theorem label is not bound to the submitted active section")


def _mixed_row_key(raw: Mapping[str, object]) -> tuple[str, str, str, int, str, str]:
    locations = raw.get("source_locations")
    nested = locations[0] if isinstance(locations, list) and locations and isinstance(locations[0], Mapping) else {}
    identity = tuple(str(raw.get(field) or nested.get(field) or "") for field in ("paper_id", "version_id", "source_hash"))
    rank = {"theorem": 0, "proof_technique": 1, "scope_audit": 2, "collision_primitive": 3,
            "theorem_relation": 4, "coverage": 5, "mutation_result": 6}
    kind = str(raw.get("record_type", raw.get("kind", "")))
    location = raw.get("source_location") if isinstance(raw.get("source_location"), Mapping) else {}
    key = str(raw.get("theorem_id") or raw.get("primitive_id") or raw.get("mutation_id")
              or (str(location.get("label", "")) + ":" + str(raw.get("technique", ""))))
    return (*identity, rank.get(kind, 99), kind, key)


def _scope(raw: object) -> FormalProblemScope:
    if not isinstance(raw, Mapping):
        _fail("T4V07", "formal_scope must be an object")
    bindings = raw.get("parameter_roles")
    if not isinstance(bindings, list):
        _fail("T4V07", "formal_scope.parameter_roles must be a list")
    try:
        roles = tuple(ParameterRoleBinding(item.get("name"), item.get("role")) for item in bindings if isinstance(item, Mapping))
        if len(roles) != len(bindings):
            _fail("T4V07", "every parameter role must be an object")
        assumptions = raw.get("assumptions", [])
        if not isinstance(assumptions, list):
            _fail("T4V07", "formal_scope.assumptions must be a list")
        return FormalProblemScope(
            raw.get("formal_problem"), roles, raw.get("data_vs_combined"), raw.get("arity"), raw.get("boolean"),
            raw.get("query_fragment"), raw.get("semantics"), raw.get("domain"), raw.get("execution_mode"),
            raw.get("randomness"), raw.get("preprocessing"), raw.get("query_time"), raw.get("delay"),
            raw.get("total_time"), tuple(assumptions),
            raw.get("communication_rounds", ScopeValue.NOT_APPLICABLE.value),
            raw.get("load", ScopeValue.NOT_APPLICABLE.value),
            raw.get("access_time", ScopeValue.NOT_APPLICABLE.value),
        )
    except ValueError as caught:
        raise Task4ValidationError("T4V07", str(caught)) from caught


def _page_text(source_map: TheoremSourceMap, location: ExactSourceLocation) -> str:
    return source_map.page_blocks[location.page - 1].normalized_text.casefold()


def _statement_scope_text(source_map: TheoremSourceMap, location: ExactSourceLocation) -> str:
    block = source_map.page_blocks[location.page - 1]
    statement = next(
        item for item in block.statement_blocks
        if item.label == location.label and item.section_heading == location.section
    )
    end_candidates = [len(block.normalized_text)]
    end_candidates.extend(item.offset for item in block.statement_blocks if item.offset > statement.offset)
    end_candidates.extend(offset for _, offset in block.heading_offsets if offset > statement.offset)
    end = min(end_candidates)
    proof = re.search(r"(?im)^\s*Proof(?:\s*\([^\n)]*\))?\s*\.", block.normalized_text[statement.offset:end])
    if proof is not None:
        end = statement.offset + proof.start()
    return block.normalized_text[statement.offset:end].casefold()


def _role(scope: FormalProblemScope, name: str) -> str | None:
    found = next((binding.role.value for binding in scope.parameter_roles if binding.name.casefold() == name), None)
    return found


def _has(scope: FormalProblemScope, token: str) -> bool:
    values = (scope.arity, scope.query_fragment, *scope.assumptions)
    return any(token in (value.value if isinstance(value, Enum) else str(value)).casefold() for value in values)


def _source_backed_scope(scope: FormalProblemScope, text: str) -> None:
    # These checks only apply where a source page explicitly states a fact;
    # absence is represented by the controlled NOT_STATED_IN_SOURCE sentinel.
    if "data complexity" in text and "data" not in str(scope.data_vs_combined).casefold():
        _fail("T4M3", "source states data complexity, not combined complexity")
    if "combined complexity" in text and "combined" not in str(scope.data_vs_combined).casefold():
        _fail("T4M3", "source states combined complexity, not data complexity")
    if "query fixed" in text and _role(scope, "query") != "FIXED":
        _fail("T4M4", "source fixes the query")
    if "query input" in text and _role(scope, "query") != "INPUT":
        _fail("T4M4", "source makes the query an input")
    if "database input" in text and _role(scope, "database") != "INPUT":
        _fail("T4M7", "source makes the database an input")
    if "k parameter" in text and _role(scope, "k") != "PARAMETER":
        _fail("T4M7", "source makes k a parameter")
    if "acyclic" in text and not _has(scope, "acyclic"):
        _fail("T4M5", "source states an acyclic restriction")
    if "self-join-free" in text and not _has(scope, "self-join-free"):
        _fail("T4M6", "source states a self-join-free restriction")
    if "assuming bounded arity" in text and not any(
        "bounded arity" in str(item).casefold() for item in scope.assumptions
    ):
        _fail("T4M11", "source-stated bounded-arity assumption is absent")
    if "deterministic algorithm" in text and scope.randomness != "DETERMINISTIC":
        _fail("T4M15", "source guarantee is deterministic")
    if "randomized algorithm" in text and scope.randomness != "RANDOMIZED":
        _fail("T4M15", "source guarantee is randomized")
    _split_metric(scope, text, "preprocessing", "T4M16")
    _split_metric(scope, text, "query_time", "T4M16")
    _split_metric(scope, text, "delay", "T4M17")
    _split_metric(scope, text, "total_time", "T4M17")


def _split_metric(scope: FormalProblemScope, text: str, field: str, code: str) -> None:
    claimed = getattr(scope, field)
    claimed_text = claimed.value if isinstance(claimed, ScopeValue) else str(claimed)
    if claimed_text in _SENTINELS:
        return
    if re.search(r"(?:O|O~)\s*\(", claimed_text, re.I):
        return
    words = {"query_time": "query time", "total_time": "total time"}
    words = words.get(field, field)
    match = re.search(r"\b(linear|constant|polynomial|logarithmic)\s+" + re.escape(words) + r"\b", text)
    if match and match.group(1) not in claimed_text.casefold():
        _fail(code, f"{words} is confused with another resource bound")


def _source_result_direction(text: str) -> str | None:
    upper = re.search(r"\bupper\s+bound(?:s)?\b", text) is not None
    lower = re.search(r"\blower\s+bound(?:s)?\b", text) is not None
    if upper == lower:
        return None
    return "UPPER_BOUND" if upper else "LOWER_BOUND"


def _theorem(
    raw: Mapping[str, object], maps: Mapping[tuple[str, str, str], TheoremSourceMap],
    authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization],
) -> TheoremRecord:
    identity = (raw.get("paper_id"), raw.get("version_id"), raw.get("source_hash"))
    if not all(isinstance(item, str) for item in identity) or identity not in maps:
        _fail("T4M19", "unknown paper/version/source hash or non-DEEP_READ theorem source")
    location = _location(raw.get("source_location"), identity)  # type: ignore[arg-type]
    if raw.get("read_depth", "DEEP_READ") != "DEEP_READ":
        _fail("T4M19", "FULL_SCAN-only paper cannot generate a complete theorem")
    source_map = maps[identity]  # type: ignore[index]
    claimed_source_tier = raw.get("source_tier", "OFFICIAL")
    if claimed_source_tier == "METADATA_ONLY":
        _fail("T4M20", "metadata-only paper cannot generate a theorem")
    if claimed_source_tier != source_map.source_tier:
        _fail("T4M10", "fragment source tier does not match immutable source metadata")
    canonical_family = authorizations[identity].corpus.version_family_id(identity)
    claimed_family = raw.get("version_family_id")
    if claimed_family is not None and claimed_family != canonical_family:
        _fail("T4M9", "version family must be derived from the frozen canonical source registry")
    _bound_location(location, source_map)
    text = _page_text(source_map, location)
    scope_text = _statement_scope_text(source_map, location)
    raw_scope = raw.get("formal_scope")
    if not isinstance(raw_scope, Mapping):
        _fail("T4V07", "formal_scope must be an object")
    raw_roles = raw_scope.get("parameter_roles")
    if isinstance(raw_roles, list):
        role_by_name = {
            item.get("name", "").casefold(): item.get("role")
            for item in raw_roles if isinstance(item, Mapping) and isinstance(item.get("name"), str)
        }
        if "query fixed" in scope_text and role_by_name.get("query") != "FIXED":
            _fail("T4M4", "source fixes the query")
        if "database input" in scope_text and role_by_name.get("database") != "INPUT":
            _fail("T4M7", "source makes the database an input")
    scope = _scope(raw_scope)
    statement = raw.get("statement")
    if not isinstance(statement, str):
        _fail("T4V08", "theorem statement must be text")
    statement_text = statement.casefold()
    result_type = raw.get("result_type", ScopeValue.NOT_STATED_IN_SOURCE.value)
    direction = _source_result_direction(text)
    if result_type in {TheoremResultType.UPPER_BOUND.value, TheoremResultType.LOWER_BOUND.value}:
        if direction is None:
            _fail("T4M1", "bound claim lacks an explicit source direction cue")
        if result_type != direction:
            _fail("T4M1", "source-bound result direction was reversed")
        expected_cue = "upper bound" if result_type == TheoremResultType.UPPER_BOUND.value else "lower bound"
        if expected_cue not in statement_text:
            _fail("T4M1", "theorem statement must explicitly state the source-bound direction")
    if ("hardness" in statement_text or "complete" in statement_text) and not (
        "hardness" in text or "complete" in text
    ):
        _fail("T4M2", "hardness/completeness has no source support")
    if "hardness" in statement_text and "hardness" not in text:
        _fail("T4M2", "hardness claim has no source support")
    if "complete" in statement_text and "complete" not in text:
        _fail("T4M2", "completeness claim has no source support")
    claim_form = raw.get("claim_form", TheoremClaimForm.OTHER_SOURCE_STATED.value)
    if "algorithmic result" in text and (
        raw.get("result_type") != TheoremResultType.ALGORITHM.value
        or claim_form != TheoremClaimForm.ALGORITHMIC.value
    ):
        _fail("T4M13", "source-stated algorithmic result was written as another semantic form")
    if "bounded" in text and "unrestricted" in str(scope.arity).casefold():
        _fail("T4M14", "bounded source result was written as unrestricted")
    _source_backed_scope(scope, scope_text)
    try:
        record = TheoremRecord(
            raw.get("theorem_id"), identity[0], identity[1], identity[2], location, scope, statement,
            raw.get("role", TheoremRole.MAIN.value), raw.get("result_type", ScopeValue.NOT_STATED_IN_SOURCE.value),
            raw.get("complexity_measure", ScopeValue.NOT_STATED_IN_SOURCE.value), canonical_family, claim_form,
        )
        try:
            validate_complete_theorem_source(record, authorizations.get(identity))
        except ValueError as caught:
            raise Task4ValidationError("T4V17", str(caught)) from caught
        return record
    except ValueError as caught:
        raise Task4ValidationError("T4V08", str(caught)) from caught


def _proof(raw: Mapping[str, object], maps: Mapping[tuple[str, str, str], TheoremSourceMap]) -> ProofTechnique:
    identity = (raw.get("paper_id"), raw.get("version_id"), raw.get("source_hash"))
    if identity not in maps:
        _fail("T4V09", "proof technique has an unknown theorem source")
    location = _location(raw.get("source_location"), identity)  # type: ignore[arg-type]
    source_map = maps[identity]  # type: ignore[index]
    _bound_location(location, source_map)
    evidence = raw.get("evidence")
    evidence_page = raw.get("evidence_page")
    evidence_start = raw.get("evidence_start")
    evidence_end = raw.get("evidence_end")
    if (
        not isinstance(evidence, str)
        or len(evidence.strip().split()) < 2
        or isinstance(evidence_page, bool)
        or not isinstance(evidence_page, int)
        or evidence_page < 1
        or evidence_page > source_map.page_count
        or isinstance(evidence_start, bool)
        or not isinstance(evidence_start, int)
        or evidence_start < 0
        or isinstance(evidence_end, bool)
        or not isinstance(evidence_end, int)
        or evidence_end <= evidence_start
    ):
        _fail("T4M18", "proof technique lacks valid exact source offsets")
    evidence_page_text = source_map.page_blocks[evidence_page - 1].normalized_text
    if evidence_end > len(evidence_page_text) or evidence_page_text[evidence_start:evidence_end] != evidence:
        _fail("T4M18", "proof technique evidence does not equal its exact source slice")
    try:
        technique = ProofTechnique(
            raw.get("technique"), raw.get("role"), location, evidence,
            evidence_page, evidence_start, evidence_end,
        )
    except ValueError as caught:
        raise Task4ValidationError("T4V09", str(caught)) from caught
    text = _page_text(source_map, location)
    cues = {
        ProofTechniqueKind.REDUCTION: ("reduction", "reduce", "reducing", "solve3sum"),
        ProofTechniqueKind.INDUCTION: ("induction", "inductive"),
        ProofTechniqueKind.DYNAMIC_PROGRAMMING: ("dynamic programming",),
        ProofTechniqueKind.DECOMPOSITION: ("decomposition", "decompose"),
        ProofTechniqueKind.HOMOMORPHISM: ("homomorphism",),
        ProofTechniqueKind.AUTOMATA: ("automata", "automaton"),
        ProofTechniqueKind.COUNTING: ("counting", "count"),
        ProofTechniqueKind.CONSTRUCTION: ("construction", "construct"),
        ProofTechniqueKind.COMPACTNESS: ("compactness",),
        ProofTechniqueKind.AMALGAMATION: ("amalgamation",),
        ProofTechniqueKind.NUMBER_THEORY: ("number theory", "number-theoretic"),
        ProofTechniqueKind.PARTITIONING: ("partition", "group organization", "organized"),
    }
    evidence_text = " ".join(evidence.casefold().split())
    if technique.technique is not ProofTechniqueKind.OTHER_SOURCE_STATED and not any(
        cue in evidence_text for cue in cues[technique.technique]
    ):
        _fail("T4M18", "proof technique cue is not inside the submitted evidence span")
    if technique.technique is ProofTechniqueKind.OTHER_SOURCE_STATED and not any(
        token.isalpha() and len(token) >= 4 for token in re.findall(r"[A-Za-z]+", evidence)
    ):
        _fail("T4M18", "other proof technique requires meaningful anchored evidence")
    return technique


def _relation(raw: Mapping[str, object], maps: Mapping[tuple[str, str, str], TheoremSourceMap]) -> TheoremRelation:
    identity = (raw.get("paper_id"), raw.get("version_id"), raw.get("source_hash"))
    if identity not in maps:
        _fail("T4V10", "relation has unknown evidence source")
    location = _location(raw.get("evidence_location"), identity)  # type: ignore[arg-type]
    source_map = maps[identity]  # type: ignore[index]
    _bound_location(location, source_map)
    if raw.get("relation") == "GENERALIZES":
        comparison = raw.get("scope_comparison")
        if not isinstance(comparison, str) or comparison in _SENTINELS or not comparison.strip():
            _fail("T4M12", "GENERALIZES requires explicit scope comparison")
        if "generaliz" not in _page_text(source_map, location):
            _fail("T4M12", "GENERALIZES requires explicit source evidence")
    try:
        return TheoremRelation(raw.get("relation"), raw.get("source_theorem_id"), raw.get("target_theorem_id"), raw.get("scope_comparison"), location)
    except ValueError as caught:
        raise Task4ValidationError("T4V10", str(caught)) from caught


def _bound_locations(raw_locations: object, maps: Mapping[tuple[str, str, str], TheoremSourceMap]) -> tuple[ExactSourceLocation, ...]:
    if not isinstance(raw_locations, list) or not raw_locations:
        _fail("T4V11", "source locations must be a nonempty list")
    result: list[ExactSourceLocation] = []
    for raw_location in raw_locations:
        if not isinstance(raw_location, Mapping):
            _fail("T4V11", "source location must be an object")
        identity = (raw_location.get("paper_id"), raw_location.get("version_id"), raw_location.get("source_hash"))
        if identity not in maps:
            _fail("T4M8", "source location has an unknown source identity")
        location = _location(raw_location, identity)  # type: ignore[arg-type]
        _bound_location(location, maps[identity])  # type: ignore[index]
        result.append(location)
    return tuple(result)


def _simple(raw: Mapping[str, object], kind: str, maps: Mapping[tuple[str, str, str], TheoremSourceMap]):
    try:
        if kind == "coverage":
            return ExtractionCoverage(raw.get("paper_id"), raw.get("version_id"), raw.get("source_hash"), raw.get("disposition"), raw.get("reason"))
        if kind == "scope_audit":
            return ScopeAudit(raw.get("theorem_id"), _scope(raw.get("formal_scope")), _bound_locations(raw.get("source_locations"), maps))
        if kind == "collision_primitive":
            return CollisionPrimitive(raw.get("primitive_id"), raw.get("label"), _bound_locations(raw.get("source_locations"), maps))
        if kind == "mutation_result":
            return MutationResult(raw.get("mutation_id"), raw.get("disposition"), raw.get("reason"))
    except ValueError as caught:
        raise Task4ValidationError("T4V11", str(caught)) from caught
    _fail("T4V11", f"unsupported record type {kind}")


def _semantic_key(raw: Mapping[str, object], record: TheoremRecord) -> tuple[object, ...]:
    del raw  # semantic identity is derived from the validated canonical record, never caller input.
    return _record_semantic_key(record)


def _record_semantic_key(record: TheoremRecord) -> tuple[object, ...]:
    scope = record.formal_scope
    def value(item: object) -> object:
        return item.value if isinstance(item, Enum) else item

    return (
        record.version_family_id,
        str(record.source_location.label).casefold(),
        value(record.role),
        record.result_type.value if isinstance(record.result_type, Enum) else str(record.result_type),
        record.complexity_measure.value if isinstance(record.complexity_measure, Enum) else str(record.complexity_measure),
        tuple(sorted((binding.name.casefold(), value(binding.role)) for binding in scope.parameter_roles)),
        tuple(value(getattr(scope, field)) for field in (
            "data_vs_combined", "arity", "boolean", "query_fragment", "semantics", "domain",
            "execution_mode", "randomness", "preprocessing", "query_time", "delay", "total_time",
        )),
        tuple(sorted(value(item) for item in scope.assumptions)),
        value(record.claim_form),
    )


def _load_and_validate_fragment_with_context(
    path: Path | str, maps: Mapping[tuple[str, str, str], TheoremSourceMap],
    authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization], *,
    partial: bool = False,
) -> ValidatedTask4Fragment:
    """Parse one JSONL fragment and return only validated Task 4 contract objects."""
    buckets: dict[str, list[object]] = {key: [] for key in ("theorem", "theorem_relation", "proof_technique", "scope_audit", "coverage", "collision_primitive", "mutation_result")}
    raw_theorems: list[tuple[Mapping[str, object], TheoremRecord]] = []
    rows = _rows(Path(path))
    if tuple(sorted(rows, key=_mixed_row_key)) != rows:
        _fail("T4V18", "fragment rows must be in canonical source-identity/type/key order")
    for raw in rows:
        kind = raw.get("record_type", raw.get("kind"))
        if kind == "theorem":
            record = _theorem(raw, maps, authorizations)
            raw_theorems.append((raw, record)); buckets[kind].append(record)
        elif kind == "proof_technique": buckets[kind].append(_proof(raw, maps))
        elif kind == "theorem_relation": buckets[kind].append(_relation(raw, maps))
        elif kind in {"scope_audit", "coverage", "collision_primitive", "mutation_result"}:
            record = _simple(raw, kind, maps)
            if kind == "coverage" and (record.paper_id, record.version_id, record.source_hash) not in maps:
                _fail("T4V15", "coverage references an unknown paper/version/source hash")
            buckets[kind].append(record)
        else: _fail("T4V12", "record_type must name a supported Task 4 record")
    ids = [record.theorem_id for _, record in raw_theorems]
    if len(ids) != len(set(ids)):
        _fail("T4V13", "duplicate theorem IDs")
    keys = [_semantic_key(raw, record) for raw, record in raw_theorems]
    if len(keys) != len(set(keys)):
        _fail("T4M9", "duplicate theorem result within a version family")
    coverage_keys = [(record.paper_id, record.version_id, record.source_hash) for record in buckets["coverage"]]  # type: ignore[attr-defined]
    if len(coverage_keys) != len(set(coverage_keys)):
        _fail("T4V14", "duplicate coverage rows")
    proof_groups: dict[tuple[object, ...], list[ProofTechnique]] = {}
    for proof in buckets["proof_technique"]:
        location = proof.source_location  # type: ignore[attr-defined]
        key = (
            location.paper_id, location.version_id, location.source_hash,
            location.page, location.section, location.label,
        )
        proof_groups.setdefault(key, []).append(proof)  # type: ignore[arg-type]
    if any(
        sum(proof.role is ProofTechniqueRole.PRIMARY for proof in group) != 1
        for group in proof_groups.values()
    ):
        _fail("T4V09", "each theorem proof group requires exactly one primary technique")
    return ValidatedTask4Fragment(
        tuple(buckets["theorem"]), tuple(buckets["theorem_relation"]), tuple(buckets["proof_technique"]),
        tuple(buckets["scope_audit"]), tuple(buckets["coverage"]), tuple(buckets["collision_primitive"]), tuple(buckets["mutation_result"]),
    )


def load_and_validate_fragment(
    path: Path | str, frozen_corpus: object, source_maps: Iterable[TheoremSourceMap], *,
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
    partial: bool = False,
) -> ValidatedTask4Fragment:
    """Parse a fragment only against the real, attested frozen corpus."""

    _, maps, authorizations = _trusted_context(frozen_corpus, source_maps, source_authorizations)
    return _load_and_validate_fragment_with_context(path, maps, authorizations, partial=partial)


def _load_and_validate_fragment_for_test(
    path: Path | str, frozen_corpus: object, source_maps: Iterable[TheoremSourceMap], *,
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
    partial: bool = False,
) -> ValidatedTask4Fragment:
    """Private mutation-fixture entry point; never part of production assembly."""

    _, maps, authorizations = _trusted_test_context(frozen_corpus, source_maps, source_authorizations)
    return _load_and_validate_fragment_with_context(path, maps, authorizations, partial=partial)


def _serialize(value: object) -> dict[str, object]:
    if isinstance(value, TheoremRecord):
        scope = value.formal_scope
        return {"theorem_id": value.theorem_id, "paper_id": value.paper_id, "version_id": value.version_id, "source_hash": value.source_hash,
                "source_location": _serialize(value.source_location), "formal_scope": _serialize(scope), "statement": value.statement,
                "role": value.role.value, "result_type": value.result_type.value, "complexity_measure": value.complexity_measure.value,
                "version_family_id": value.version_family_id, "claim_form": value.claim_form.value}
    if isinstance(value, FormalProblemScope):
        return {"formal_problem": value.formal_problem, "parameter_roles": [_serialize(x) for x in value.parameter_roles],
                **{field: getattr(value, field).value if isinstance(getattr(value, field), Enum) else getattr(value, field)
                   for field in ("data_vs_combined", "arity", "boolean", "query_fragment", "semantics", "domain", "execution_mode", "randomness", "preprocessing", "query_time", "delay", "total_time", "communication_rounds", "load", "access_time")},
                "assumptions": [item.value if isinstance(item, Enum) else item for item in value.assumptions]}
    if isinstance(value, ParameterRoleBinding): return {"name": value.name, "role": value.role.value}
    if isinstance(value, ExactSourceLocation):
        payload: dict[str, object] = {
            "page": value.page,
            "section": value.section.value if isinstance(value.section, Enum) else value.section,
            "label": value.label.value if isinstance(value.label, Enum) else value.label,
        }
        if value.paper_id is not None:
            payload.update({"paper_id": value.paper_id, "version_id": value.version_id, "source_hash": value.source_hash})
        return payload
    if isinstance(value, ProofTechnique):
        return {
            "technique": value.technique.value,
            "role": value.role.value,
            "source_location": _serialize(value.source_location),
            "evidence": value.evidence,
            "evidence_page": value.evidence_page,
            "evidence_start": value.evidence_start,
            "evidence_end": value.evidence_end,
        }
    if isinstance(value, TheoremRelation): return {"relation": value.relation.value, "source_theorem_id": value.source_theorem_id, "target_theorem_id": value.target_theorem_id, "scope_comparison": value.scope_comparison.value if isinstance(value.scope_comparison, Enum) else value.scope_comparison, "evidence_location": _serialize(value.evidence_location)}
    if isinstance(value, ScopeAudit): return {"theorem_id": value.theorem_id, "formal_scope": _serialize(value.formal_scope), "source_locations": [_serialize(item) for item in value.source_locations]}
    if isinstance(value, ExtractionCoverage): return {"paper_id": value.paper_id, "version_id": value.version_id, "source_hash": value.source_hash, "disposition": value.disposition.value, "reason": value.reason.value if isinstance(value.reason, Enum) else value.reason}
    if isinstance(value, CollisionPrimitive): return {"primitive_id": value.primitive_id, "label": value.label, "source_locations": [_serialize(item) for item in value.source_locations]}
    if isinstance(value, MutationResult): return {"mutation_id": value.mutation_id, "disposition": value.disposition.value, "reason": value.reason}
    raise TypeError(f"cannot serialize {type(value)!r}")


def _canonical_payload(rows: Iterable[object], key) -> bytes:
    return b"".join(canonical_json(_serialize(row)).encode("utf-8") + b"\n" for row in sorted(rows, key=key))


def _fsync(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _write_all_atomic(root: Path, payloads: Mapping[str, bytes]) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    replaced: list[str] = []
    rollback_errors: list[BaseException] = []
    try:
        for name, payload in payloads.items():
            handle, temporary = tempfile.mkstemp(prefix=f".{name}-", dir=root); os.close(handle)
            target = Path(temporary); staged[name] = target; target.write_bytes(payload); _fsync(target)
        for name in payloads:
            target = root / name
            if target.exists():
                handle, backup_name = tempfile.mkstemp(prefix=f".{name}.backup-", dir=root); os.close(handle)
                backup = Path(backup_name); backups[name] = backup; shutil.copyfile(target, backup); _fsync(backup)
        for name, staged_path in staged.items():
            os.replace(staged_path, root / name); replaced.append(name)
    except BaseException as failure:
        restored: set[str] = set()
        for name in reversed(replaced):
            target = root / name
            try:
                if name in backups:
                    os.replace(backups[name], target)
                    restored.add(name)
                elif target.exists(): target.unlink()
            except BaseException as caught: rollback_errors.append(caught)
        if rollback_errors:
            retained = sorted(str(path) for path in (*staged.values(), *backups.values()) if path.exists())
            affected = sorted(set(replaced) - restored)
            raise RuntimeError(
                "Task 4 assembly rollback failed; retained recovery paths="
                f"{retained}; affected targets={affected}"
            ) from rollback_errors[0]
        raise failure
    finally:
        if not rollback_errors:
            for staged_path in (*staged.values(), *backups.values()):
                if staged_path.exists(): staged_path.unlink()
    return {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}


def _assemble_task4_with_context(
    fragment_paths: Iterable[Path | str], output_root: Path | str,
    maps_index: Mapping[tuple[str, str, str], TheoremSourceMap],
    authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization], *,
    partial: bool = False,
) -> dict[str, str]:
    """Validate all fragments from an already trusted context."""
    maps = tuple(maps_index.values())
    fragments = tuple(_load_and_validate_fragment_with_context(path, maps_index, authorizations, partial=partial) for path in fragment_paths)
    all_rows = lambda field: tuple(item for fragment in fragments for item in getattr(fragment, field))
    records = all_rows("theorem_records"); relations = all_rows("theorem_relations"); techniques = all_rows("proof_techniques")
    audits = all_rows("scope_audits"); coverage = all_rows("coverage"); primitives = all_rows("collision_primitives")
    record_ids = [row.theorem_id for row in records]
    if len(record_ids) != len(set(record_ids)):
        _fail("T4V13", "duplicate theorem IDs across fragments")
    record_semantics = [_record_semantic_key(row) for row in records]
    if len(record_semantics) != len(set(record_semantics)):
        _fail("T4M9", "duplicate theorem result within a version family across fragments")
    covered = {(row.paper_id, row.version_id, row.source_hash) for row in coverage}
    source_ids = {(row.paper_id, row.version_id, row.source_hash) for row in maps}
    if len(covered) != len(coverage): _fail("T4V14", "duplicate coverage rows across fragments")
    if not partial:
        if covered != source_ids:
            _fail("T4V15", "final assembly requires exactly one coverage disposition for every frozen DEEP_READ paper")
    elif not covered.issubset(source_ids): _fail("T4V15", "coverage references an unknown source")
    known_ids = set(record_ids)
    for relation in relations:
        if relation.source_theorem_id not in known_ids or relation.target_theorem_id not in known_ids:
            _fail("T4V16", "theorem relation references an unknown theorem")
    if any(audit.theorem_id not in known_ids for audit in audits):
        _fail("T4V16", "scope audit references an unknown theorem")
    proof_groups: dict[tuple[object, ...], list[ProofTechnique]] = {}
    for proof in techniques:
        location = proof.source_location
        key = (
            location.paper_id, location.version_id, location.source_hash,
            location.page, location.section, location.label,
        )
        proof_groups.setdefault(key, []).append(proof)
    if any(
        sum(proof.role is ProofTechniqueRole.PRIMARY for proof in group) != 1
        for group in proof_groups.values()
    ):
        _fail("T4V09", "assembled theorem proof groups require exactly one primary technique")
    mutations = run_required_mutation_suite()
    payloads = {
        "theorem_records.jsonl": _canonical_payload(records, lambda row: (row.paper_id, row.source_location.page, str(row.source_location.label), row.theorem_id)),
        "theorem_relations.jsonl": _canonical_payload(relations, lambda row: (row.source_theorem_id, row.target_theorem_id, row.relation.value)),
        "proof_techniques.jsonl": _canonical_payload(techniques, lambda row: (row.technique.value, row.evidence, row.source_location.page)),
        "theorem_scope_audit.jsonl": _canonical_payload(audits, lambda row: row.theorem_id),
        "extraction_coverage.jsonl": _canonical_payload(coverage, lambda row: (row.paper_id, row.version_id, row.source_hash)),
        "collision_primitives.jsonl": _canonical_payload(primitives, lambda row: row.primitive_id),
        "mutation_results.jsonl": _canonical_payload(mutations, lambda row: row.mutation_id),
    }
    return _write_all_atomic(Path(output_root), payloads)


def assemble_task4(
    fragment_paths: Iterable[Path | str], output_root: Path | str, frozen_corpus: object,
    source_maps: Iterable[TheoremSourceMap], *,
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
    partial: bool = False,
) -> dict[str, str]:
    """Validate and atomically assemble only against an attested frozen corpus."""

    _, maps_index, authorizations = _trusted_context(frozen_corpus, source_maps, source_authorizations)
    return _assemble_task4_with_context(
        fragment_paths, output_root, maps_index, authorizations, partial=partial,
    )


def _assemble_task4_for_test(
    fragment_paths: Iterable[Path | str], output_root: Path | str, frozen_corpus: object,
    source_maps: Iterable[TheoremSourceMap], *,
    source_authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization] | None,
    partial: bool = False,
) -> dict[str, str]:
    """Private fixture-only assembly entry point for the mutation harness/tests."""

    _, maps_index, authorizations = _trusted_test_context(frozen_corpus, source_maps, source_authorizations)
    return _assemble_task4_with_context(
        fragment_paths, output_root, maps_index, authorizations, partial=partial,
    )


def _mutation_map(
    *, paper_id: str = "paper:mutation", version_id: str = "version:official",
    source_tier: str = "OFFICIAL", seed: str = "mutation-fixture", anchor: str = "",
) -> TheoremSourceMap:
    text = ("1 Introduction\nTheorem 1. For acyclic self-join-free CQ, with query fixed, database input and k parameter, data complexity has an upper bound. Assuming bounded arity, the deterministic algorithm has linear preprocessing, constant query time, constant delay, and linear total time." + anchor)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return TheoremSourceMap(paper_id, version_id, digest, CacheBinding(
        f"literature/fulltext_cache/{seed}.pdf", 16, digest, 16, digest,
        "attempt:1", "a" * 64, "attempt:1", "b" * 64,
    ), 1, _with_active_sections((_page_block(1, text),)), source_tier)


def _mutation_control(
    source_map: TheoremSourceMap, *, theorem_id: str = "theorem:mutation",
    result_type: str = "UPPER_BOUND", statement: str | None = None,
    role: str = "MAIN", claim_form: str = "OTHER_SOURCE_STATED",
) -> dict[str, object]:
    return {"record_type": "theorem", "theorem_id": theorem_id, "paper_id": source_map.paper_id, "version_id": source_map.version_id, "source_hash": source_map.source_hash, "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"}, "formal_scope": {"formal_problem": "evaluate a CQ", "parameter_roles": [{"name": "database", "role": "INPUT"}, {"name": "query", "role": "FIXED"}, {"name": "k", "role": "PARAMETER"}], "data_vs_combined": "DATA_COMPLEXITY", "arity": "BOUNDED_ARITY", "boolean": "BOOLEAN", "query_fragment": "ACYCLIC_CQ", "semantics": "SET", "domain": "FINITE", "execution_mode": "STATIC", "randomness": "DETERMINISTIC", "preprocessing": "LINEAR", "query_time": "CONSTANT", "delay": "CONSTANT", "total_time": "LINEAR", "assumptions": ["bounded arity", "self-join-free"]}, "statement": statement or ("Theorem 1 gives an upper bound for the fixed-query problem." if result_type == "UPPER_BOUND" else "Theorem 1 gives a structural characterization of the fixed-query problem."), "role": role, "result_type": result_type, "complexity_measure": "DATA_COMPLEXITY", "claim_form": claim_form, "source_tier": source_map.source_tier}


def _mutation_context(
    source_map: TheoremSourceMap, additional_maps: tuple[TheoremSourceMap, ...] = (),
) -> tuple[FrozenTask4Corpus, tuple[TheoremSourceMap, ...], dict[tuple[str, str, str], CompleteTheoremSourceAuthorization]]:
    initial = (source_map,) + additional_maps
    generated = tuple(
        replace(source_map, paper_id=f"paper:mutation-{number:03d}", version_id=f"version:mutation-{number:03d}")
        for number in range(1, 81 - len(initial))
    )
    maps = tuple(sorted(initial + generated, key=lambda item: (item.paper_id, item.version_id)))
    shared = {(item.paper_id, item.version_id, item.source_hash) for item in initial}
    lineages = tuple(
        (item.paper_id, item.version_id, item.source_hash, "lineage:conference-journal" if (item.paper_id, item.version_id, item.source_hash) in shared else item.paper_id)
        for item in maps
    )
    corpus = FrozenTask4Corpus.for_test(maps, FROZEN_TASK3_CLOSURE_SHA256, lineages)
    return corpus, maps, {(item.paper_id, item.version_id, item.source_hash): corpus.authorize(item) for item in maps}


def _mutation_map_with_anchor(source_map: TheoremSourceMap, anchor: str) -> TheoremSourceMap:
    block = source_map.page_blocks[0]
    text = block.normalized_text + " " + anchor
    return replace(source_map, page_blocks=_with_active_sections((_page_block(block.page, text),)))


def _mutation_map_with_unanchored_second_page(source_map: TheoremSourceMap) -> TheoremSourceMap:
    second_text = "2 Related Work\nTheorem 2. A later result is discussed without any explicit scope comparison."
    return replace(source_map, page_count=2, page_blocks=_with_active_sections((
        source_map.page_blocks[0], _page_block(2, second_text),
    )))


def _validate_rows(rows: list[dict[str, object]], corpus: FrozenTask4Corpus, source_maps: tuple[TheoremSourceMap, ...], authorizations: Mapping[tuple[str, str, str], CompleteTheoremSourceAuthorization]) -> None:
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "mutation.jsonl"
        path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")
        _load_and_validate_fragment_for_test(path, corpus, source_maps, source_authorizations=authorizations, partial=True)


def run_required_mutation_suite() -> tuple[MutationResult, ...]:
    """Run one clean control and one mutant for every required defect code."""
    results: list[MutationResult] = []
    for mutation_id in REQUIRED_MUTATION_IDS:
        source_map = _mutation_map()
        clean = _mutation_control(source_map)
        clean_rows: list[dict[str, object]] = [clean]
        mutant_rows: list[dict[str, object]]
        additional_maps: tuple[TheoremSourceMap, ...] = ()
        def altered(mutator):
            row = json.loads(json.dumps(clean)); mutator(row); return [row]
        if mutation_id == "T4M1": mutant_rows = altered(lambda r: r.__setitem__("statement", "Theorem 1 gives a lower bound."))
        elif mutation_id == "T4M2":
            source_map = _mutation_map(seed="mutation-hardness", anchor=" The proof establishes hardness.")
            clean = _mutation_control(
                source_map, statement="Theorem 1 gives an upper bound and establishes hardness.",
            )
            clean_rows = [clean]
            mutant_rows = altered(lambda r: r.__setitem__("statement", "Theorem 1 gives an upper bound and establishes completeness."))
        elif mutation_id == "T4M3": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("data_vs_combined", "COMBINED_COMPLEXITY"))
        elif mutation_id == "T4M4": mutant_rows = altered(lambda r: r["formal_scope"]["parameter_roles"].__setitem__(1, {"name": "query", "role": "INPUT"}))
        elif mutation_id == "T4M5": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("query_fragment", "CQ"))
        elif mutation_id == "T4M6": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("assumptions", ["bounded arity"]))
        elif mutation_id == "T4M7": mutant_rows = altered(lambda r: r["formal_scope"]["parameter_roles"].__setitem__(0, {"name": "database", "role": "FIXED"}))
        elif mutation_id == "T4M8": mutant_rows = altered(lambda r: r.__setitem__("source_location", {"page": 1, "section": "1 Introduction", "label": "Theorem 99"}))
        elif mutation_id == "T4M9":
            source_map = _mutation_map(source_tier="CONFERENCE", seed="mutation-conference")
            journal_map = _mutation_map(
                paper_id="paper:mutation-journal", version_id="version:journal",
                source_tier="JOURNAL", seed="mutation-journal",
            )
            additional_maps = (journal_map,)
            clean = _mutation_control(source_map)
            journal_clean = _mutation_control(
                journal_map, theorem_id="theorem:mutation-journal", role="COROLLARY",
            )
            clean_rows = [clean, journal_clean]
            journal_mutant = json.loads(json.dumps(journal_clean))
            journal_mutant.update({
                "theorem_id": "theorem:mutation-copy",
                "role": "MAIN",
            })
            mutant_rows = [clean, journal_mutant]
        elif mutation_id == "T4M10":
            source_map = _mutation_map(source_tier="PREPRINT", seed="mutation-preprint")
            clean = _mutation_control(source_map)
            clean_rows = [clean]
            mutant_rows = altered(lambda r: r.__setitem__("source_tier", "OFFICIAL"))
        elif mutation_id == "T4M11": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("assumptions", ["self-join-free"]))
        elif mutation_id == "T4M12":
            source_map = _mutation_map_with_anchor(source_map, "This result generalizes the previous scope.")
            source_map = _mutation_map_with_unanchored_second_page(source_map)
            relation = {"record_type": "theorem_relation", "paper_id": source_map.paper_id, "version_id": source_map.version_id, "source_hash": source_map.source_hash, "relation": "GENERALIZES", "source_theorem_id": "theorem:a", "target_theorem_id": "theorem:b", "scope_comparison": "strictly broader query fragment", "evidence_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"}}
            clean_rows = [relation]
            mutant_rows = [dict(relation, evidence_location={"page": 2, "section": "2 Related Work", "label": "Theorem 2"})]
        elif mutation_id == "T4M13":
            source_map = _mutation_map_with_anchor(source_map, "Algorithmic result.")
            clean.update({"result_type": "ALGORITHM", "claim_form": "ALGORITHMIC", "statement": "The source-stated algorithmic result evaluates the fixed-query problem."})
            clean_rows = [clean]
            mutant = json.loads(json.dumps(clean)); mutant.update({"result_type": "STRUCTURAL", "claim_form": "CHARACTERIZATION"}); mutant_rows = [mutant]
        elif mutation_id == "T4M14": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("arity", "UNRESTRICTED_ARITY"))
        elif mutation_id == "T4M15": mutant_rows = altered(lambda r: r["formal_scope"].__setitem__("randomness", "RANDOMIZED"))
        elif mutation_id == "T4M16": mutant_rows = altered(lambda r: (r["formal_scope"].__setitem__("preprocessing", "CONSTANT"), r["formal_scope"].__setitem__("query_time", "LINEAR")))
        elif mutation_id == "T4M17": mutant_rows = altered(lambda r: (r["formal_scope"].__setitem__("delay", "LINEAR"), r["formal_scope"].__setitem__("total_time", "CONSTANT")))
        elif mutation_id == "T4M18":
            source_map = _mutation_map_with_anchor(source_map, "The proof is by reduction.")
            evidence = "The proof is by reduction"
            evidence_start = source_map.page_blocks[0].normalized_text.index(evidence)
            proof = {
                "record_type": "proof_technique", "paper_id": source_map.paper_id,
                "version_id": source_map.version_id, "source_hash": source_map.source_hash,
                "technique": "REDUCTION",
                "role": "PRIMARY",
                "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
                "evidence": evidence, "evidence_page": 1, "evidence_start": evidence_start,
                "evidence_end": evidence_start + len(evidence),
            }
            clean_rows = [proof]
            mutant_rows = [dict(proof, evidence="guessed reduction")]
        elif mutation_id == "T4M19": mutant_rows = altered(lambda r: r.__setitem__("read_depth", "FULL_SCAN"))
        else: mutant_rows = altered(lambda r: r.__setitem__("source_tier", "METADATA_ONLY"))
        corpus, source_maps, authorizations = _mutation_context(source_map, additional_maps)
        try:
            _validate_rows(clean_rows, corpus, source_maps, authorizations)
        except Task4ValidationError as caught:
            results.append(MutationResult(mutation_id, MutationDisposition.NOT_DETECTED, f"CLEAN_CONTROL_{caught.code}"))
            continue
        try: _validate_rows(mutant_rows, corpus, source_maps, authorizations)
        except Task4ValidationError as caught:
            disposition = MutationDisposition.DETECTED if caught.code == mutation_id else MutationDisposition.NOT_DETECTED
            results.append(MutationResult(mutation_id, disposition, caught.code))
        else: results.append(MutationResult(mutation_id, MutationDisposition.NOT_DETECTED, "NO_REJECTION"))
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble validated Corpus Task 4 fragments")
    parser.add_argument("fragments", nargs="+", type=Path); parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--partial", action="store_true", help="allow incomplete coverage; never use for final assembly")
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    corpus = build_frozen_task4_corpus(repository_root)
    authorizations = {(item.paper_id, item.version_id, item.source_hash): corpus.authorize(item) for item in corpus.source_maps}
    hashes = assemble_task4(args.fragments, args.output_root, corpus, corpus.source_maps, source_authorizations=authorizations, partial=args.partial)
    print(canonical_json(hashes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
