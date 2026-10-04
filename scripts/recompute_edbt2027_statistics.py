"""Recompute the bounded prototype facts used by the EDBT 2027 vision paper."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "raw_observations": ROOT / "literature/source_registry/venue_census_observations_2023_2026.jsonl",
    "canonical_papers": ROOT / "data/papers/papers.jsonl",
    "read_depth": ROOT / "literature/fulltext_ledgers/read_depth_2026_08_30.json",
    "audited_records": ROOT / "data/theorems/fragments/batch-001-020.jsonl",
    "coverage": ROOT / "data/theorems/fragments/coverage-001-020.jsonl",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    papers = jsonl(INPUTS["canonical_papers"])
    records = jsonl(INPUTS["audited_records"])
    coverage = jsonl(INPUTS["coverage"])
    read_depth = json.loads(INPUTS["read_depth"].read_text(encoding="utf-8"))
    theorem_records = [r for r in records if r.get("record_type") == "theorem"]
    classifications = Counter(p.get("screening", {}).get("classification") for p in papers)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    stats = {
        "generated_on": str(date.today()),
        "scope": "Only canonical corpus metadata and formally audited theorem batch 001-020.",
        "commit": commit,
        "script": "scripts/recompute_edbt2027_statistics.py",
        "inputs": {name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)} for name, path in INPUTS.items()},
        "statistics": {
            "raw_observations": sum(1 for line in INPUTS["raw_observations"].read_text(encoding="utf-8").splitlines() if line.strip()),
            "canonical_paper_families": len(papers),
            "relevant_paper_families": sum(bool(p.get("screening", {}).get("relevant")) for p in papers),
            "full_scan_papers": read_depth["counts"]["FULL_SCAN"],
            "deep_read_papers": read_depth["counts"]["DEEP_READ"],
            "audited_theorem_papers": len(coverage),
            "audited_theorem_records": len(theorem_records),
            "records_with_source_locations": sum(bool(r.get("source_location")) for r in theorem_records),
            "audited_version_families": len({r.get("version_id") for r in theorem_records}),
        },
        "classification_counts": dict(sorted(classifications.items())),
        "definitions": {
            "raw_observations": "Nonblank provider-observation rows before canonical family deduplication.",
            "canonical_paper_families": "Rows in data/papers/papers.jsonl, each representing one canonical paper family.",
            "relevant_paper_families": "Canonical families whose deterministic screening record has relevant=true.",
            "full_scan_papers": "Source-verified papers counted as FULL_SCAN by the frozen read-depth ledger; includes DEEP_READ.",
            "deep_read_papers": "Source-verified papers counted as DEEP_READ by the frozen read-depth ledger.",
            "audited_theorem_papers": "Coverage rows in coverage-001-020.jsonl.",
            "audited_theorem_records": "Rows with record_type=theorem in batch-001-020.jsonl.",
            "records_with_source_locations": "Audited theorem rows containing a nonempty source_location object.",
            "audited_version_families": "Distinct version_id values among audited theorem rows.",
        },
        "exclusions": [
            "No theorem records from batches 021-040 are used.",
            "No theorem extraction claim is made for papers 041-080.",
            "Counts do not estimate completeness, extraction accuracy, effectiveness, adoption, or open-problem status.",
        ],
    }
    out_dir = ROOT / "artifacts/edbt2027"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "prototype_statistics.json"
    out.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    s = stats["statistics"]
    md = f"""# Frozen Prototype Statistics

Generated: {stats['generated_on']}  
Commit: `{commit}`  
Recompute: `python scripts/recompute_edbt2027_statistics.py`

| Measure | Value | Definition |
|---|---:|---|
""" + "\n".join(f"| {k.replace('_',' ')} | {v:,} | {stats['definitions'][k]} |" for k, v in s.items()) + """

## Evidence boundary

Every value above is computed from an input whose SHA-256 is recorded in `prototype_statistics.json`. The admissible theorem evidence is exactly batch 001-020. These counts establish bounded construction feasibility and auditability only.
"""
    (out_dir / "PROTOTYPE_STATISTICS.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
