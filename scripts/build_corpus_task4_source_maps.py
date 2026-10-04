"""Build deterministic Task 4 source maps from frozen Task 3 cached PDFs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from db_theory_atlas.corpus_task4 import build_source_maps, write_source_maps_atomic


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "theorem_source_maps" / "theorem_source_maps.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--read-ledger", type=Path, default=None)
    parser.add_argument("--manifests", type=Path, default=None)
    parser.add_argument("--attempts", type=Path, default=None)
    args = parser.parse_args(argv)
    maps = build_source_maps(
        args.root,
        read_ledger_path=args.read_ledger,
        manifests_path=args.manifests,
        attempts_path=args.attempts,
    )
    digest = write_source_maps_atomic(maps, args.output)
    print(json.dumps({"count": len(maps), "output": str(args.output), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
