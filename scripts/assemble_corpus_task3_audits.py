"""Assemble reviewed Task 3 audit fragments into deterministic tracked registries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

from db_theory_atlas.fulltext_reading import parse_source_audit


ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-fragments"
DEEP_FRAGMENTS = ROOT / ".superpowers" / "sdd" / "corpus-task-3-deep-fragments"
INDEX = ROOT / ".superpowers" / "sdd" / "corpus-task-3-audit-packets" / "index.jsonl"
PROMOTIONS = ROOT / "literature" / "fulltext_audits" / "source_validation_2026_08_30.jsonl"
DEMOTIONS = ROOT / "literature" / "fulltext_audits" / "source_demotions_2026_08_30.jsonl"


def _read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _write_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    os.close(handle)
    stage = Path(raw)
    try:
        stage.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        os.replace(stage, path)
    finally:
        if stage.exists():
            stage.unlink()


def assemble(
    fragments: Path,
    deep_fragments: Path,
    index_path: Path,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    index = _read_jsonl(index_path)
    ordinal_by_key = {
        (str(row["paper_id"]), str(row["version_id"])): int(row["ordinal"])
        for row in index
    }
    if len(ordinal_by_key) != len(index):
        raise ValueError("audit-packet index requires unique paper/version keys")

    promotions: dict[int, dict[str, object]] = {}
    for path in sorted(fragments.glob("*-promotions.jsonl")):
        for row in _read_jsonl(path):
            audit = parse_source_audit(row)
            key = (audit.paper_id, audit.version_id)
            if key not in ordinal_by_key:
                raise ValueError(f"promotion is absent from audit-packet index: {key}")
            ordinal = ordinal_by_key[key]
            if ordinal in promotions:
                raise ValueError(f"duplicate promotion disposition for ordinal {ordinal}")
            promotions[ordinal] = row

    demotions: dict[int, dict[str, object]] = {}
    for path in sorted(fragments.glob("*-demotions.jsonl")):
        for row in _read_jsonl(path):
            ordinal = int(row["ordinal"])
            key = (str(row["paper_id"]), str(row["version_id"]))
            if ordinal_by_key.get(key) != ordinal:
                raise ValueError(f"demotion identity mismatch for ordinal {ordinal}")
            if row.get("disposition") != "ABSTRACT" or not str(row.get("reason", "")).strip():
                raise ValueError(f"demotion {ordinal} requires ABSTRACT disposition and an explicit reason")
            if ordinal in demotions:
                raise ValueError(f"duplicate demotion disposition for ordinal {ordinal}")
            demotions[ordinal] = row

    overlap = set(promotions) & set(demotions)
    if overlap:
        raise ValueError(f"ordinals have both promotion and demotion dispositions: {sorted(overlap)}")
    expected = set(ordinal_by_key.values())
    observed = set(promotions) | set(demotions)
    if observed != expected:
        raise ValueError(
            f"audit dispositions are incomplete: missing={sorted(expected - observed)}, unknown={sorted(observed - expected)}"
        )

    deep_ordinals: set[int] = set()
    if deep_fragments.is_dir():
        for path in sorted(deep_fragments.glob("*.jsonl")):
            for row in _read_jsonl(path):
                audit = parse_source_audit(row)
                if audit.read_depth.value != "DEEP_READ":
                    raise ValueError(f"deep fragment is not DEEP_READ: {audit.paper_id}")
                key = (audit.paper_id, audit.version_id)
                if key not in ordinal_by_key:
                    raise ValueError(f"deep fragment is absent from audit-packet index: {key}")
                ordinal = ordinal_by_key[key]
                if ordinal not in promotions:
                    raise ValueError(f"deep fragment has no accepted FULL_SCAN disposition: ordinal {ordinal}")
                if ordinal in deep_ordinals:
                    raise ValueError(f"duplicate DEEP_READ disposition for ordinal {ordinal}")
                full = parse_source_audit(promotions[ordinal])
                if (audit.paper_id, audit.version_id, audit.source_hash, audit.full_scan) != (
                    full.paper_id, full.version_id, full.source_hash, full.full_scan
                ):
                    raise ValueError(f"deep fragment changes the accepted FULL_SCAN evidence: ordinal {ordinal}")
                promotions[ordinal] = row
                deep_ordinals.add(ordinal)
    return (
        tuple(promotions[ordinal] for ordinal in sorted(promotions)),
        tuple(demotions[ordinal] for ordinal in sorted(demotions)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments", type=Path, default=FRAGMENTS)
    parser.add_argument("--deep-fragments", type=Path, default=DEEP_FRAGMENTS)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--promotions", type=Path, default=PROMOTIONS)
    parser.add_argument("--demotions", type=Path, default=DEMOTIONS)
    args = parser.parse_args(argv)
    promotions, demotions = assemble(args.fragments, args.deep_fragments, args.index)
    _write_jsonl_atomic(args.promotions, promotions)
    _write_jsonl_atomic(args.demotions, demotions)
    print(json.dumps({
        "FULL_SCAN": len(promotions),
        "DEEP_READ": sum(row["read_depth"] == "DEEP_READ" for row in promotions),
        "ABSTRACT": len(demotions),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
