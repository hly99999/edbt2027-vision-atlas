from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from db_theory_atlas.corpus_task4 import (
    FROZEN_TASK3_CLOSURE_SHA256, CacheBinding, FrozenTask4Corpus, PageTextBlock,
    TheoremSourceMap, _FROZEN_CORPUS_ISSUER, _page_block, _with_active_sections,
)
from scripts.assemble_corpus_task4 import (
    _assemble_task4_for_test, _load_and_validate_fragment_for_test,
    assemble_task4, load_and_validate_fragment,
)


def _map() -> TheoremSourceMap:
    text = (
        "1 Introduction\nTheorem 1. For acyclic self-join-free CQ, with query fixed, "
        "database input and k parameter, data complexity has an upper bound. "
        "Assuming bounded arity, the deterministic algorithm has linear preprocessing, "
        "constant query time, constant delay, and linear total time."
    )
    digest = hashlib.sha256(b"fixture-pdf").hexdigest()
    return TheoremSourceMap(
        paper_id="paper:fixture", version_id="version:official", source_hash=digest,
        cache_binding=CacheBinding("literature/fulltext_cache/fixture.pdf", 11, digest, 11, digest,
                                   "attempt:1", "a" * 64, "attempt:1", "b" * 64),
        page_count=1,
        page_blocks=_with_active_sections((_page_block(1, text),)),
    )


def _theorem(source_map: TheoremSourceMap) -> dict[str, object]:
    return {
        "record_type": "theorem", "theorem_id": "theorem:fixture", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "formal_scope": {
            "formal_problem": "evaluate a CQ", "parameter_roles": [
                {"name": "database", "role": "INPUT"}, {"name": "query", "role": "FIXED"},
                {"name": "k", "role": "PARAMETER"}], "data_vs_combined": "DATA_COMPLEXITY",
            "arity": "BOUNDED_ARITY", "boolean": "BOOLEAN", "query_fragment": "ACYCLIC_CQ",
            "semantics": "SET", "domain": "FINITE", "execution_mode": "STATIC",
            "randomness": "DETERMINISTIC", "preprocessing": "LINEAR", "query_time": "CONSTANT",
            "delay": "CONSTANT", "total_time": "LINEAR", "assumptions": ["bounded arity", "self-join-free"],
        }, "statement": "Theorem 1 gives an upper bound for the fixed-query problem.",
        "result_type": "UPPER_BOUND", "complexity_measure": "DATA_COMPLEXITY",
        "source_tier": "OFFICIAL", "version_lineage_authorized": True,
    }


def _frozen(
    source_map: TheoremSourceMap,
    version_lineages: tuple[tuple[str, str, str, str], ...] = (),
) -> FrozenTask4Corpus:
    maps = (source_map,) + tuple(
        replace(source_map, paper_id=f"paper:fixture-{number:03d}", version_id=f"version:fixture-{number:03d}")
        for number in range(1, 80)
    )
    return FrozenTask4Corpus.for_test(maps, FROZEN_TASK3_CLOSURE_SHA256, version_lineages)


def _context(source_map: TheoremSourceMap):
    corpus = _frozen(source_map)
    return corpus, corpus.source_maps, {(
        item.paper_id, item.version_id, item.source_hash): corpus.authorize(item) for item in corpus.source_maps
    }


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_fragment_loader_rejects_source_location_not_bound_to_source_map(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    row["source_location"] = {"page": 1, "section": "1 Introduction", "label": "Theorem 99"}
    fragment = tmp_path / "bad.jsonl"
    _write(fragment, [row])

    with pytest.raises(ValueError, match="T4M8"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_assembly_is_atomic_deterministic_and_requires_full_coverage_unless_partial(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    fragment = tmp_path / "clean.jsonl"
    coverage = {
        "record_type": "coverage", "paper_id": source_map.paper_id, "version_id": source_map.version_id,
        "source_hash": source_map.source_hash, "disposition": "COMPLETE_THEOREM_EXTRACTION",
        "reason": "source inspected",
    }
    _write(fragment, [_theorem(source_map), coverage])
    output = tmp_path / "out"

    with pytest.raises(ValueError, match="coverage"):
        _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations)
    first = _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    payloads = {path.name: path.read_bytes() for path in output.glob("*.jsonl")}
    second = _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    assert first == second
    assert payloads == {path.name: path.read_bytes() for path in output.glob("*.jsonl")}
    assert "theorem_records.jsonl" in first


def test_assembly_validates_every_fragment_before_replacing_existing_outputs(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    clean = tmp_path / "clean.jsonl"
    coverage = {"record_type": "coverage", "paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "disposition": "COMPLETE_THEOREM_EXTRACTION", "reason": "source inspected"}
    _write(clean, [_theorem(source_map), coverage])
    output = tmp_path / "out"
    _assemble_task4_for_test([clean], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    before = {path.name: path.read_bytes() for path in output.glob("*.jsonl")}
    bad = _theorem(source_map)
    bad["theorem_id"] = "theorem:unbound"
    bad["source_location"] = {"page": 1, "section": "1 Introduction", "label": "Theorem 99"}
    invalid = tmp_path / "invalid.jsonl"
    _write(invalid, [bad])

    with pytest.raises(ValueError, match="T4M8"):
        _assemble_task4_for_test([clean, invalid], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    assert before == {path.name: path.read_bytes() for path in output.glob("*.jsonl")}


def test_assembly_rejects_semantic_duplicate_across_fragment_boundaries(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    first = _theorem(source_map)
    coverage = {"record_type": "coverage", "paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "disposition": "COMPLETE_THEOREM_EXTRACTION", "reason": "source inspected"}
    second = _theorem(source_map)
    second["theorem_id"] = "theorem:fixture-duplicate"
    fragment_one, fragment_two = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    _write(fragment_one, [first, coverage])
    _write(fragment_two, [second])

    with pytest.raises(ValueError, match="T4M9"):
        _assemble_task4_for_test([fragment_one, fragment_two], tmp_path / "out", corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_loader_requires_real_frozen_corpus_and_issued_capability(tmp_path: Path) -> None:
    source_map = _map()
    fragment = tmp_path / "claim.jsonl"
    _write(fragment, [_theorem(source_map)])
    fake = SimpleNamespace(source_maps=(source_map,))

    with pytest.raises(ValueError, match="FrozenTask4Corpus"):
        load_and_validate_fragment(fragment, fake, (source_map,), source_authorizations={}, partial=True)


def test_final_assembly_rejects_the_original_simplenamespace_forgery(tmp_path: Path) -> None:
    source_map = _map()
    fragment = tmp_path / "forged-final.jsonl"
    _write(fragment, [_theorem(source_map)])

    with pytest.raises(ValueError, match="FrozenTask4Corpus"):
        assemble_task4(
            [fragment], tmp_path / "out", SimpleNamespace(source_maps=(source_map,)), (source_map,),
            source_authorizations={}, partial=False,
        )


def test_public_assembly_interfaces_do_not_expose_test_corpus_bypass(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    fragment = tmp_path / "public-bypass.jsonl"
    _write(fragment, [_theorem(source_map)])

    with pytest.raises(TypeError):
        load_and_validate_fragment(
            fragment, corpus, source_maps, source_authorizations=authorizations,
            partial=True, test_only=True,
        )
    with pytest.raises(TypeError):
        assemble_task4(
            [fragment], tmp_path / "out", corpus, source_maps,
            source_authorizations=authorizations, partial=True, test_only=True,
        )


def test_capabilities_must_be_issued_by_the_exact_passed_corpus(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, _ = _context(source_map)
    equal_but_distinct_corpus = FrozenTask4Corpus.for_test(source_maps, FROZEN_TASK3_CLOSURE_SHA256)
    foreign_authorizations = {
        (item.paper_id, item.version_id, item.source_hash): equal_but_distinct_corpus.authorize(item)
        for item in source_maps
    }
    fragment = tmp_path / "foreign-capability.jsonl"
    _write(fragment, [_theorem(source_map)])

    with pytest.raises(ValueError, match="different frozen corpus"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=foreign_authorizations, partial=True,
        )


@pytest.mark.parametrize("mutation", ("missing", "extra", "wrong_key", "shadow_map"))
def test_capability_registry_must_exactly_bind_every_canonical_source(
    tmp_path: Path, mutation: str,
) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    forged = dict(authorizations)
    identity = (source_map.paper_id, source_map.version_id, source_map.source_hash)
    if mutation == "missing":
        forged.pop(identity)
    elif mutation == "extra":
        forged[("paper:extra", "version:extra", "f" * 64)] = authorizations[identity]
    elif mutation == "wrong_key":
        forged[("paper:wrong", source_map.version_id, source_map.source_hash)] = forged.pop(identity)
    else:
        shadow = replace(source_map, page_blocks=(replace(
            source_map.page_blocks[0], normalized_text="shadow text",
            page_text_sha256=hashlib.sha256(b"shadow text").hexdigest(),
        ),))
        forged[identity] = replace(authorizations[identity], source_map=shadow)
    fragment = tmp_path / f"{mutation}.jsonl"
    _write(fragment, [_theorem(source_map)])

    with pytest.raises(ValueError, match="T4V17"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=forged, partial=True)


@pytest.mark.parametrize("record_type", ("scope_audit", "collision_primitive"))
def test_audit_and_primitive_locations_require_bound_source_identity(tmp_path: Path, record_type: str) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    location = {"paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "page": 999,
                "section": "1 Introduction", "label": "Theorem 1"}
    row = (
        {"record_type": "scope_audit", "theorem_id": "theorem:fixture", "formal_scope": _theorem(source_map)["formal_scope"], "source_locations": [location]}
        if record_type == "scope_audit"
        else {"record_type": "collision_primitive", "primitive_id": "primitive:fixture", "label": "fixture", "source_locations": [location]}
    )
    fragment = tmp_path / "unbound-locations.jsonl"
    _write(fragment, [row])

    with pytest.raises(ValueError, match="T4M8"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_scope_and_collision_serialization_preserve_exact_source_identity(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    theorem = _theorem(source_map)
    location = {"paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "page": 1,
                "section": "1 Introduction", "label": "Theorem 1"}
    fragment = tmp_path / "identity.jsonl"
    _write(fragment, [
        theorem,
        {"record_type": "scope_audit", "theorem_id": theorem["theorem_id"],
         "formal_scope": theorem["formal_scope"], "source_locations": [location]},
        {"record_type": "collision_primitive", "primitive_id": "primitive:fixture",
         "label": "fixture", "source_locations": [location]},
    ])
    output = tmp_path / "out"
    _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)

    audit = json.loads((output / "theorem_scope_audit.jsonl").read_text(encoding="utf-8"))
    primitive = json.loads((output / "collision_primitives.jsonl").read_text(encoding="utf-8"))
    expected_identity = {
        "paper_id": source_map.paper_id, "version_id": source_map.version_id, "source_hash": source_map.source_hash,
    }
    assert {key: audit["source_locations"][0][key] for key in expected_identity} == expected_identity
    assert {key: primitive["source_locations"][0][key] for key in expected_identity} == expected_identity


def test_atomic_rollback_restores_all_seven_targets_after_midway_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    fragment = tmp_path / "clean.jsonl"
    coverage = {"record_type": "coverage", "paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "disposition": "COMPLETE_THEOREM_EXTRACTION", "reason": "source inspected"}
    _write(fragment, [_theorem(source_map), coverage])
    output = tmp_path / "out"
    _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    before = {path.name: path.read_bytes() for path in output.glob("*.jsonl")}
    import scripts.assemble_corpus_task4 as assembler
    actual_replace, staged_replaces = assembler.os.replace, 0

    def fail_midway_staged(source, target):
        nonlocal staged_replaces
        if Path(source).name.startswith(".") and Path(target).suffix == ".jsonl":
            staged_replaces += 1
            if staged_replaces == 4:
                raise OSError("simulated midway replace failure")
        return actual_replace(source, target)

    monkeypatch.setattr(assembler.os, "replace", fail_midway_staged)
    with pytest.raises(OSError, match="simulated midway replace"):
        _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    assert len(before) == 7
    assert before == {path.name: path.read_bytes() for path in output.glob("*.jsonl")}


def test_atomic_rollback_failure_retains_recovery_material_and_affected_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    fragment = tmp_path / "clean.jsonl"
    coverage = {"record_type": "coverage", "paper_id": source_map.paper_id, "version_id": source_map.version_id,
                "source_hash": source_map.source_hash, "disposition": "COMPLETE_THEOREM_EXTRACTION", "reason": "source inspected"}
    _write(fragment, [_theorem(source_map), coverage])
    output = tmp_path / "out"
    _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)

    import scripts.assemble_corpus_task4 as assembler
    actual_replace = assembler.os.replace
    staged_replaces = 0
    backup_restore_failed = False

    def fail_stage_then_restore(source, target):
        nonlocal staged_replaces, backup_restore_failed
        source_name = Path(source).name
        if source_name.startswith(".") and ".backup-" not in source_name and Path(target).suffix == ".jsonl":
            staged_replaces += 1
            if staged_replaces == 2:
                raise OSError("simulated second staged replace failure")
        if ".backup-" in source_name and not backup_restore_failed:
            backup_restore_failed = True
            raise OSError("simulated first backup restore failure")
        return actual_replace(source, target)

    monkeypatch.setattr(assembler.os, "replace", fail_stage_then_restore)
    with pytest.raises(RuntimeError, match="retained recovery paths=.*affected targets=") as caught:
        _assemble_task4_for_test([fragment], output, corpus, source_maps, source_authorizations=authorizations, partial=True)
    assert "theorem_records.jsonl" in str(caught.value)
    assert any(".backup-" in path.name for path in output.iterdir())
    assert any(path.name.startswith(".theorem_") for path in output.iterdir())


def test_algorithmic_claim_form_is_source_bound_and_cannot_be_laundered_as_characterization(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    row.update({"result_type": "ALGORITHM", "claim_form": "ALGORITHMIC"})
    row["statement"] = "The source-stated algorithmic result evaluates the fixed-query problem."
    source_map = replace(source_map, page_blocks=(replace(
        source_map.page_blocks[0], normalized_text=source_map.page_blocks[0].normalized_text + " Algorithmic result.",
        page_text_sha256=hashlib.sha256((source_map.page_blocks[0].normalized_text + " Algorithmic result.").encode()).hexdigest(),
    ),))
    corpus, source_maps, authorizations = _context(source_map)
    fragment = tmp_path / "algorithm.jsonl"
    _write(fragment, [row])
    _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)
    row["result_type"] = "STRUCTURAL"
    row["claim_form"] = "CHARACTERIZATION"
    _write(fragment, [row])

    with pytest.raises(ValueError, match="T4M13"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_fragment_cannot_self_declare_a_different_version_family(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    row["version_family_id"] = "family:forged"
    fragment = tmp_path / "forged-family.jsonl"
    _write(fragment, [row])

    with pytest.raises(ValueError, match="T4M9"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_semantic_duplicate_ignores_rewritten_statement_across_authorized_lineage_versions(tmp_path: Path) -> None:
    source_map = _map()
    maps = (source_map,) + tuple(
        replace(source_map, paper_id=f"paper:fixture-{number:03d}", version_id=f"version:fixture-{number:03d}")
        for number in range(1, 80)
    )
    shared_lineage = tuple(
        (item.paper_id, item.version_id, item.source_hash, "lineage:conference-journal")
        if index < 2 else (item.paper_id, item.version_id, item.source_hash, item.paper_id)
        for index, item in enumerate(maps)
    )
    corpus = FrozenTask4Corpus.for_test(maps, FROZEN_TASK3_CLOSURE_SHA256, shared_lineage)
    source_maps = corpus.source_maps
    authorizations = {
        (item.paper_id, item.version_id, item.source_hash): corpus.authorize(item)
        for item in source_maps
    }
    first = _theorem(source_maps[0])
    second = _theorem(source_maps[1])
    second["theorem_id"] = "theorem:fixture-rewritten"
    second["statement"] = "A paraphrased statement gives an upper bound for the fixed-query problem."
    fragment = tmp_path / "lineage-duplicate.jsonl"
    _write(fragment, [first, second])
    with pytest.raises(ValueError, match="T4M9"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_source_bound_direction_rejects_lower_claim_even_when_statement_and_result_type_are_mutated(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    clean = _theorem(source_map)
    fragment = tmp_path / "direction.jsonl"
    _write(fragment, [clean])
    _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)

    mutant = _theorem(source_map)
    mutant["statement"] = "Theorem 1 gives a lower bound."
    mutant["result_type"] = "LOWER_BOUND"
    _write(fragment, [mutant])
    with pytest.raises(ValueError, match="T4M1"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_direction_claim_requires_an_explicit_bound_cue(tmp_path: Path) -> None:
    no_direction_text = (
        "1 Introduction\nTheorem 1 establishes a result for the fixed-query problem. "
        "Assuming bounded arity, the deterministic algorithm has linear preprocessing, "
        "constant query time, constant delay, and linear total time."
    )
    source_map = replace(_map(), page_blocks=(replace(
        _map().page_blocks[0], normalized_text=no_direction_text,
        page_text_sha256=hashlib.sha256(no_direction_text.encode()).hexdigest(),
    ),))
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    with pytest.raises(ValueError, match="T4M1"):
        fragment = tmp_path / "missing-direction.jsonl"
        _write(fragment, [row])
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_hardness_cue_cannot_be_relabelled_as_completeness(tmp_path: Path) -> None:
    block = _map().page_blocks[0]
    text = block.normalized_text + " The proof establishes hardness."
    source_map = replace(_map(), page_blocks=(replace(
        block, normalized_text=text,
        page_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    ),))
    corpus, source_maps, authorizations = _context(source_map)
    clean = _theorem(source_map)
    clean["statement"] = "Theorem 1 gives an upper bound and establishes hardness."
    fragment = tmp_path / "hardness-completeness.jsonl"
    _write(fragment, [clean])
    _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)
    mutant = dict(clean)
    mutant["statement"] = "Theorem 1 gives an upper bound and establishes completeness."
    _write(fragment, [mutant])
    with pytest.raises(ValueError, match="T4M2"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_proof_technique_requires_meaningful_technique_specific_source_cue(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    row = {
        "record_type": "proof_technique", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "technique": "REDUCTION",
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "evidence": "the",
    }
    fragment = tmp_path / "generic-proof-evidence.jsonl"
    _write(fragment, [row])
    with pytest.raises(ValueError, match="T4M18"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations,
            partial=True,
        )


def test_proof_technique_cue_must_be_inside_submitted_evidence_span(tmp_path: Path) -> None:
    source_map = _map()
    block = source_map.page_blocks[0]
    text = block.normalized_text + " The proof uses reduction elsewhere."
    source_map = replace(source_map, page_blocks=(replace(
        block, normalized_text=text,
        page_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    ),))
    corpus, source_maps, authorizations = _context(source_map)
    row = {
        "record_type": "proof_technique", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "technique": "REDUCTION",
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "evidence": "upper bound",
    }
    fragment = tmp_path / "unrelated-proof-cue.jsonl"
    _write(fragment, [row])
    with pytest.raises(ValueError, match="T4M18"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations,
            partial=True,
        )


def test_proof_technique_offsets_bind_the_exact_source_slice(tmp_path: Path) -> None:
    source_map = _map()
    block = source_map.page_blocks[0]
    evidence = "1 Introduction\nTheorem"
    start = block.normalized_text.index(evidence)
    row = {
        "record_type": "proof_technique", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "technique": "OTHER_SOURCE_STATED",
        "role": "PRIMARY",
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "evidence_page": 1, "evidence_start": start, "evidence_end": start + len(evidence),
        "evidence": evidence,
    }
    fragment = tmp_path / "exact-proof-evidence.jsonl"
    _write(fragment, [row])
    corpus, source_maps, authorizations = _context(source_map)

    loaded = _load_and_validate_fragment_for_test(
        fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
    )
    proof = loaded.proof_techniques[0]
    assert block.normalized_text[proof.evidence_start:proof.evidence_end] == proof.evidence


@pytest.mark.parametrize("field,value", (("evidence_start", -1), ("evidence_end", 10_000)))
def test_proof_technique_rejects_invalid_source_offsets(
    tmp_path: Path, field: str, value: int,
) -> None:
    source_map = _map()
    block = source_map.page_blocks[0]
    evidence = "deterministic algorithm"
    start = block.normalized_text.index(evidence)
    row = {
        "record_type": "proof_technique", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "technique": "OTHER_SOURCE_STATED",
        "role": "PRIMARY",
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "evidence_page": 1, "evidence_start": start, "evidence_end": start + len(evidence),
        "evidence": evidence,
    }
    row[field] = value
    fragment = tmp_path / f"invalid-proof-{field}.jsonl"
    _write(fragment, [row])
    corpus, source_maps, authorizations = _context(source_map)

    with pytest.raises(ValueError, match="T4M18"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
        )


@pytest.mark.parametrize("roles", (("SECONDARY",), ("PRIMARY", "PRIMARY")))
def test_each_proof_group_requires_exactly_one_primary_technique(
    tmp_path: Path, roles: tuple[str, ...],
) -> None:
    source_map = _map()
    block = source_map.page_blocks[0]
    evidence = "deterministic algorithm"
    start = block.normalized_text.index(evidence)
    rows = [{
        "record_type": "proof_technique", "paper_id": source_map.paper_id,
        "version_id": source_map.version_id, "source_hash": source_map.source_hash,
        "technique": "OTHER_SOURCE_STATED", "role": role,
        "source_location": {"page": 1, "section": "1 Introduction", "label": "Theorem 1"},
        "evidence_page": 1, "evidence_start": start, "evidence_end": start + len(evidence),
        "evidence": evidence,
    } for role in roles]
    fragment = tmp_path / "invalid-proof-primary.jsonl"
    _write(fragment, rows)
    corpus, source_maps, authorizations = _context(source_map)

    with pytest.raises(ValueError, match="T4V09"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
        )


def test_scope_validation_does_not_inherit_restrictions_from_the_proof_block(tmp_path: Path) -> None:
    source_map = _map()
    text = (
        "1 Introduction\n"
        "Theorem 1. With query fixed, database input and k parameter, data complexity has an upper bound.\n"
        "Proof. The implementation materializes an acyclic self-join-free auxiliary query."
    )
    source_map = replace(source_map, page_blocks=_with_active_sections((_page_block(1, text),)))
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    row["formal_scope"]["query_fragment"] = "CONJUNCTIVE_QUERY"
    row["formal_scope"]["assumptions"] = ["NOT_STATED_IN_SOURCE"]
    fragment = tmp_path / "no-proof-scope-leakage.jsonl"
    _write(fragment, [row])

    _load_and_validate_fragment_for_test(
        fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
    )


@pytest.mark.parametrize("record_type", ("theorem", "scope_audit", "collision_primitive"))
def test_source_locators_reject_scopevalue_sentinels_for_every_record_kind(tmp_path: Path, record_type: str) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    theorem = _theorem(source_map)
    bad_location = {"paper_id": source_map.paper_id, "version_id": source_map.version_id,
                    "source_hash": source_map.source_hash, "page": 1,
                    "section": "NOT_APPLICABLE", "label": "Theorem 1"}
    if record_type == "theorem":
        row = dict(theorem)
        row["source_location"] = bad_location
    elif record_type == "scope_audit":
        row = {"record_type": record_type, "theorem_id": theorem["theorem_id"],
               "formal_scope": theorem["formal_scope"], "source_locations": [bad_location]}
    else:
        row = {"record_type": record_type, "primitive_id": "primitive:sentinel",
               "label": "sentinel", "source_locations": [bad_location]}
    fragment = tmp_path / f"sentinel-{record_type}.jsonl"
    _write(fragment, [theorem] if record_type != "theorem" else [row])
    if record_type != "theorem":
        _write(fragment, [theorem, row])
    with pytest.raises(ValueError, match="concrete"):
        _load_and_validate_fragment_for_test(fragment, corpus, source_maps, source_authorizations=authorizations, partial=True)


def test_fragment_loader_rejects_label_bound_to_a_different_section_on_same_page(tmp_path: Path) -> None:
    source_map = _map()
    text = "2 Preliminaries\nTheorem 2.1. Setup.\n3 Main Results\nTheorem 3.1. Upper bound.\n"
    source_map = replace(source_map, page_blocks=_with_active_sections((_page_block(1, text),)))
    corpus, source_maps, authorizations = _context(source_map)
    row = _theorem(source_map)
    row["source_location"] = {"page": 1, "section": "2 Preliminaries", "label": "Theorem 3.1"}
    fragment = tmp_path / "wrong-section.jsonl"
    _write(fragment, [row])

    with pytest.raises(ValueError, match="T4M8"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
        )


def test_fragment_loader_rejects_noncanonical_mixed_row_order(tmp_path: Path) -> None:
    source_map = _map()
    corpus, source_maps, authorizations = _context(source_map)
    theorem = _theorem(source_map)
    coverage = {"record_type": "coverage", "paper_id": source_map.paper_id,
                "version_id": source_map.version_id, "source_hash": source_map.source_hash,
                "disposition": "COMPLETE_THEOREM_EXTRACTION", "reason": "source inspected"}
    fragment = tmp_path / "unordered.jsonl"
    _write(fragment, [coverage, theorem])

    with pytest.raises(ValueError, match="canonical.*order"):
        _load_and_validate_fragment_for_test(
            fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
        )


def test_distinct_source_labels_are_not_semantic_duplicates(tmp_path: Path) -> None:
    text = "1 Introduction\nTheorem 1. Upper bound.\nTheorem 2. Upper bound.\n"
    source_map = replace(_map(), page_blocks=_with_active_sections((_page_block(1, text),)))
    corpus, source_maps, authorizations = _context(source_map)
    first = _theorem(source_map)
    second = dict(first)
    second["theorem_id"] = "theorem:fixture-2"
    second["source_location"] = {"page": 1, "section": "1 Introduction", "label": "Theorem 2"}
    fragment = tmp_path / "distinct-labels.jsonl"
    _write(fragment, [first, second])

    _load_and_validate_fragment_for_test(
        fragment, corpus, source_maps, source_authorizations=authorizations, partial=True,
    )
