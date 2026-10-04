"""Fail-closed validation for the EDBT 2027 vision-paper package."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "docs/edbt2027_vision/official_requirements.md",
    "artifacts/edbt2027/claim_registry.csv",
    "artifacts/edbt2027/prototype_statistics.json",
    "artifacts/edbt2027/PROTOTYPE_STATISTICS.md",
    "artifacts/edbt2027/ARTIFACT_STATEMENT.md",
    "AI_USE_LEDGER.md",
    "reports/edbt2027/NOVELTY_AUDIT.md",
    "reports/edbt2027/RELATED_WORK_MATRIX.csv",
    "reports/edbt2027/RUNNING_EXAMPLE_AUDIT.md",
    "reports/edbt2027/CLAIM_EVIDENCE_REPORT.md",
    "reports/edbt2027/REVIEWER_REDTEAM.md",
    "reports/edbt2027/MOCK_REVIEWS.md",
    "reports/edbt2027/CITATION_AUDIT.md",
    "reports/edbt2027/FINAL_SUBMISSION_AUDIT.md",
    "reports/edbt2027/final_edbt2027_vision_report.md",
    "paper/edbt2027_vision/main.tex",
    "paper/edbt2027_vision/references.bib",
    "paper/edbt2027_vision/edbt2027_vision.pdf",
    "paper/edbt2027_vision/figures/architecture.svg",
    "paper/edbt2027_vision/figures/architecture.pdf",
    "paper/edbt2027_vision/figures/running_example.svg",
    "paper/edbt2027_vision/figures/running_example.pdf",
    "paper/edbt2027_vision/SUBMISSION_CHECKLIST.md",
    "paper/edbt2027_vision/official-template/acmart.cls",
    "paper/edbt2027_vision/official-template/edbt-macros.tex",
    "paper/edbt2027_vision/official-template/ACM-Reference-Format.bst",
    "paper/edbt2027_vision/official-template/edbt-paper-template.tex",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    for rel in REQUIRED:
        path = ROOT / rel
        require(path.is_file() and path.stat().st_size > 0, f"missing or empty {rel}")

    stats = json.loads((ROOT / "artifacts/edbt2027/prototype_statistics.json").read_text(encoding="utf-8"))
    expected = {
        "raw_observations": 3737,
        "canonical_paper_families": 3356,
        "relevant_paper_families": 309,
        "full_scan_papers": 125,
        "deep_read_papers": 80,
        "audited_theorem_papers": 20,
        "audited_theorem_records": 127,
        "records_with_source_locations": 127,
        "audited_version_families": 20,
    }
    require(stats["statistics"] == expected, "prototype statistics differ from frozen expected values")
    require(len(stats["inputs"]) == 5 and all(len(v["sha256"]) == 64 for v in stats["inputs"].values()), "statistics are not hash-bound")

    with (ROOT / "artifacts/edbt2027/claim_registry.csv").open(encoding="utf-8-sig", newline="") as f:
        claims = list(csv.DictReader(f))
    require(len(claims) >= 20, "claim registry has fewer than 20 claims")
    require(all(c["status"] == "BOUND" and c["source"] and c["evidence"] for c in claims), "unbound claim found")

    with (ROOT / "reports/edbt2027/RELATED_WORK_MATRIX.csv").open(encoding="utf-8-sig", newline="") as f:
        works = list(csv.DictReader(f))
    require(len(works) >= 25, "fewer than 25 serious related-work candidates")
    require(sum(w["closest overlap"] == "DIRECT" for w in works) >= 5, "fewer than five direct threats")

    red = (ROOT / "reports/edbt2027/REVIEWER_REDTEAM.md").read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## R[1-6]", red)[1:]
    require(len(sections) == 6, "reviewer persona count is not six")
    require(all(len(re.findall(r"(?m)^\d+\. ", s)) >= 15 for s in sections), "a reviewer persona has fewer than 15 questions")
    mocks = (ROOT / "reports/edbt2027/MOCK_REVIEWS.md").read_text(encoding="utf-8")
    require(len(re.findall(r"(?m)^## Review [1-5]", mocks)) == 5, "mock review count is not five")

    pdf = PdfReader(str(ROOT / "paper/edbt2027_vision/edbt2027_vision.pdf"))
    require(len(pdf.pages) == 7, "candidate PDF must have six body pages plus one references page")
    for i in range(6):
        require(f"Body page {i+1} of 6" in (pdf.pages[i].extract_text() or ""), f"missing body-page marker {i+1}")
    require("References (additional page" in (pdf.pages[6].extract_text() or ""), "references page not separated")

    scope = [ROOT / "docs/edbt2027_vision", ROOT / "reports/edbt2027", ROOT / "artifacts/edbt2027", ROOT / "paper/edbt2027_vision"]
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for d in scope for p in d.rglob("*") if p.suffix.lower() in {".md", ".tex", ".bib", ".csv", ".json", ".svg"})
    forbidden = re.compile(r"\b(first-ever|unprecedented|we introduce the first|no prior work)\b", re.I)
    require(not forbidden.search(corpus), "forbidden novelty wording found")
    final_report = (ROOT / "reports/edbt2027/final_edbt2027_vision_report.md").read_text(encoding="utf-8")
    require(not re.search(r"(?m)^SUBMISSION_READY\.?$", final_report), "package overstates readiness")
    require("CONDITIONAL_READY" in corpus and "CONDITIONAL_GO" in corpus, "required conditional verdicts absent")
    require("theorem:batch-001-005-01" in corpus, "running-example theorem identity absent")

    print("EDBT2027_PACKAGE_VALID")
    print(f"claims={len(claims)} related_work={len(works)} direct_threats={sum(w['closest overlap']=='DIRECT' for w in works)} pdf_pages={len(pdf.pages)}")


if __name__ == "__main__":
    main()
