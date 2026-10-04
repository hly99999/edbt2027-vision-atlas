"""Extract UTF-8 text from PDFs for internal source audits."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def extract(pdf_path: Path, output_path: Path) -> None:
    reader = PdfReader(pdf_path)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        pages.append(f"\n\n===== PAGE {number} =====\n\n{page.extract_text() or ''}")
    output_path.write_text("".join(pages).lstrip(), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    extract(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
