# Release Staging Audit

Generated: 2026-10-04

## Scope

This audit records the bounded artifact that is prepared for the EDBT 2027 Vision Paper. It does not provide CMT submission authorization.

## Included categories

| Category | Included paths | Decision |
|---|---|---|
| Source code | `src/` | Include; Python source only, bytecode excluded. |
| Rebuild/audit scripts | `scripts/` | Include; scripts are needed to recompute and validate the bounded package. |
| Tests | `tests/` | Include; synthetic login and PDF fixtures excluded. |
| Canonical/derived metadata | `data/papers/`, `indexes/`, selected `literature/source_registry/` | Include; bibliographic identifiers, source URLs, hashes, and deterministic screening metadata. |
| Audited theorem records | `data/theorems/fragments/batch-001-020.jsonl`, `claim-inventory-001-020.jsonl`, `coverage-001-020.jsonl` | Include; this is the only theorem batch in the release. |
| Read-depth provenance | `literature/fulltext_ledgers/read_depth_2026_08_30.json` | Include; contains hashes/pointers, not source PDF bytes. |
| EDBT artifact/audit documentation | `artifacts/edbt2027/`, `docs/edbt2027_vision/`, `reports/edbt2027/` | Include; bounded claims and limitations retained. |
| Manuscript source | `paper/edbt2027_vision/main.tex`, `references.bib` | Include as source context; author and Liuye Hua ORCID are entered; Jiong Zheng ORCID remains pending. |
| Original figures | `paper/edbt2027_vision/figures/*.svg` and generated `*.pdf` | Include; generated locally and not external source PDFs. |
| Licenses | `LICENSE`, `LICENSE-CC-BY-4.0.txt` | Include; Apache-2.0 covers code and CC BY 4.0 covers documentation/derived data. |

## Excluded categories

| Category | Reason |
|---|---|
| `literature/fulltext_cache/*.pdf` | Copyright/access restrictions; retain hashes and source pointers only. |
| `literature/fulltext_notes/` and `literature/fulltext_audits/` | Derived from full text and may reproduce source prose; legal/publication review required before redistribution. |
| `literature/source_registry/provider_cache/` | Provider payloads/abstract evidence may carry provider-specific terms; not needed for the bounded release candidate. |
| `paper/edbt2027_vision/official-template/` and template ZIP | Official template redistribution terms not separately confirmed; use the official source link. |
| `paper/edbt2027_vision/*.{aux,log,out,pdf}` and PNG QA renders | Build products, temporary files, or submission output; excluded from the artifact candidate. |
| `data/theorems/fragments/batch-021-040.jsonl` and later batches | Release boundary is audited batch 001-020. |
| `tests/fixtures/login.html` and `tests/fixtures/sample.pdf` | Synthetic fixture files excluded from public package. |

## Checks

- EDBT package validator: **PASS** (125 package files; claims=20, related_work=32, direct_threats=9, pdf_pages=7).
- Local path/credential scan: **PASS** for the package boundary.
- Liuye Hua ORCID: **0009-0000-2122-0764**, confirmed by the author and entered in the manuscript; public profile shows Liuye Hua at Xinjiang University.
- Jiong Zheng ORCID: **pending**; no placeholder is used.
- License files: **present** at repository root.
- Public URL and immutable release commit/tag: **pending push** to the authorized GitHub repository `hly99999/edbt2027-vision-atlas` (planned tag `v0.1.0`).
- User-reported duplicate/overlap status: no overlap; CMT conflicts none (reported by author).
- User-reported author review status: complete/no issues (reported by author; not independently verifiable from filesystem alone).
- CMT submission authorization: **not granted**; no CMT submission was made.

## Required after publication

1. Record the exact commit hash reached by tag `v0.1.0` in the local release record.
2. Recheck the public repository contents and tag after the push; keep the source-PDF, provider-cache, unreviewed theorem-batch, credential, and official-template exclusions intact.
3. Keep CMT submission blocked until the authors explicitly authorize it and finish any required CMT conflict/profile fields.

## Local archive candidate

`EDBT2027_artifact_candidate_20261004.zip` is a convenience archive of the bounded package. SHA-256: `e7cf69b709252f86c07282dd6dace195f53e6c6639bdf1e7433e4ad1b4dd4b8a`.

The archive remains local; the public immutable identity will be the GitHub repository plus tag `v0.1.0` after the author-authorized push.
