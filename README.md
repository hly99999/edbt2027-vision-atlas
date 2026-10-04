# Evidence-Grounded Database-Theory Atlas — EDBT 2027 Vision Artifact

This repository contains the reproducibility artifact for the EDBT 2027 Vision Paper, “From Papers to Scoped Theorems: Evidence-Grounded Knowledge Infrastructure for Database Theory.”

The public boundary is deliberately limited to deterministic code, schemas, derived metadata, audited theorem records for batch 001–020, generated figures, rebuild scripts, tests, and audit documentation. Copyrighted source PDFs, extracted full-text notes, provider payload caches, build products, credentials, and theorem batches after 001–020 are excluded.

## Authors

- Liuye Hua, Xinjiang University — hualiuye@stu.xju.edu.cn
- Jiong Zheng (corresponding author), Xinjiang University — zhengjiong@xju.edu.cn

## Rebuild and validation

The release package was validated in the source checkout before staging (`EDBT2027_PACKAGE_VALID`). The bounded public repository intentionally excludes the official submission template and final submission PDF; those files remain available from the official EDBT 2027 sources and are not redistributed here. The stored `RELEASE_AUDIT.md`, `MANIFEST.json`, and `SHA256SUMS.txt` document the exact public boundary and validation result.

For local development of the code and tests:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest
python scripts/recompute_edbt2027_statistics.py
```

## Licensing

- Source code: Apache License 2.0 (`LICENSE`).
- Documentation, generated figures, and derived metadata/records: Creative Commons Attribution 4.0 International (`LICENSE-CC-BY-4.0.txt`).
- Source PDFs and extracted full-text materials are not redistributed by this repository.

The EDBT 2027 official LaTeX template is not redistributed here; obtain it from the official CFP link recorded in `docs/edbt2027_vision/official_requirements.md`.

## Release identity

The immutable release tag is `v0.1.0`. The public URL is `https://github.com/hly99999/edbt2027-vision-atlas`. The exact commit reached by that tag is recorded in the local release record after the GitHub push. This repository is the artifact only; CMT submission remains a separate author-controlled action.
