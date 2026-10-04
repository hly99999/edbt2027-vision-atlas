"""Deterministic, source-bound reading notes from frozen validated PDF bytes.

This module does not infer theorem records or open-problem status.  It records
compact reading signals only when the corresponding text occurs at an exact
PDF page and section heading, then delegates promotion validity to
``db_theory_atlas.reading``.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable, Mapping

from pypdf import PdfReader

from .corpus_task3 import AcquisitionManifest, AcquisitionStatus
from .reading import CoverageKind, ReadingState, parse_note_frontmatter


_HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*)\s+\S")
_TIGHT_NUMBERED_HEADING = re.compile(
    r"^\d+(?:\.\d+)*\.?(?:Introduction|Abstract|Background|Preliminaries|Conclusion|Results?|Discussion)",
    re.IGNORECASE,
)
_REFERENCE_LIKE = re.compile(
    r"\b(?:doi|pages?|journal|proceedings|volume|press|springer|acm|ieee|vldb|corr|siam|trans(?:actions)?)\b"
    r"|\b(?:19|20)\d{2}\b|\b(?:et al)\b",
    re.I,
)
_NUMBERED_PROSE = re.compile(r"\b(?:is|are|was|were|has|have|whether|which|that|observe|suppose|then)\b", re.I)
_NON_HEADING_OPEN = re.compile(r"^(?:and|but|for|if|return|suggests?|the|then|therefore|while)\b", re.I)
_PSEUDOCODE_OR_FORMULA = re.compile(
    r"(?:\b(?:return|eof|for every|for all|such that|if|then|while|foreach)\b|[=<>≤≥∈∀∃∧∨{}\[\]()]|·\s*·|\b(?:lemma|proof)\s+of\b)",
    re.I,
)
_HEADING_WORDS = re.compile(
    r"^(?:abstract|introduction|background|related work|preliminaries|definitions?|formal (?:setting|framework|model)|"
    r"problem (?:statement|definition|setting)|methods?|approach|algorithms?|contributions?|main results?|results?|complexity|"
    r"proof(?: overview| sketch)?|discussion|limitations?(?: and future work)?|future work|conclusions?|"
    r"concluding remarks|appendix(?: [A-Z])?)$",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_STOP = frozenset(
    "the a an and or but if then this that these those we our paper work section for from with into over under "
    "within of to in on by as at is are was were be been being has have had do does did can could may might "
    "will would should using use used show shows shown prove proves proved consider considers considered study "
    "studies studied present presents presented result results problem problems".split()
)
_UNSUPPORTED_CERTAINTY = frozenset({"always", "certainly", "definitive", "definitively", "undeniably", "guaranteed"})

_PROBLEM = re.compile(r"\b(?:we (?:study|consider|investigate|address)|problem|task|given|input|query|decid(?:e|ing))\b", re.I)
_FORMAL = re.compile(r"\b(?:let|given|input|output|semantics?|language|fragment|parameter|assum(?:e|ption)|finite|arity)\b", re.I)
_RESULT = re.compile(r"\b(?:we (?:show|prove|establish|obtain|give|present|explain|demonstrate)|main result|theorem|upper bound|lower bound|hardness|complexity|algorithm|dichotomy|implementation|contribution)\b", re.I)
_LIMITATION = re.compile(r"\b(?:limitation|future work|future research|remain(?:s|ing)?|open (?:question|problem)|does not|do not|not cover|restricted|only|challenge|further work|extension|need(?:s|ed)?|adapt(?:ed|ation)?)\b", re.I)
_TECHNIQUE = re.compile(r"\b(?:proof|reduction|induction|game|encoding|algorithm|construction|homomorphism|dynamic programming|automata|decomposition|translation)\b", re.I)


@dataclass(frozen=True, slots=True)
class PdfDocument:
    source_hash: str
    page_count: int
    pages: tuple[str, ...]
    extraction_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    page: int
    heading: str
    sentence: str
    signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadingAnalysis:
    paper_id: str
    version_id: str
    source_hash: str
    page_count: int
    extraction_sha256: str
    topic: str
    venue: str
    year: int
    priority_score: int
    abstract: EvidenceLocation | None
    introduction: EvidenceLocation | None
    conclusion: EvidenceLocation | None
    problem: EvidenceLocation | None
    formal_scope: EvidenceLocation | None
    result: EvidenceLocation | None
    limitation: EvidenceLocation | None
    technique: EvidenceLocation | None
    shortfall_reason: str | None = None

    @property
    def full_scan_eligible(self) -> bool:
        required = (self.abstract, self.introduction, self.conclusion, self.problem,
                    self.formal_scope, self.result, self.limitation)
        headings = {item.heading.casefold() for item in required if item is not None}
        return all(item is not None for item in required) and len(headings) >= 3

    @property
    def deep_read_eligible(self) -> bool:
        return self.full_scan_eligible and self.technique is not None

    @classmethod
    def testing_deep(cls, *, paper_id: str, version_id: str, source_hash: str, topic: str,
                     venue: str, year: int, priority_score: int) -> "ReadingAnalysis":
        intro = EvidenceLocation(1, "Introduction", "We study a scoped problem.", ("scoped", "query"))
        formal = EvidenceLocation(2, "Formal Setting", "Let the input and output be finite.", ("input", "output", "finite"))
        result = EvidenceLocation(3, "Main Results", "We prove the stated bound.", ("bound", "fragment"))
        limitation = EvidenceLocation(4, "Limitations", "The result does not cover an extension.", ("cover", "extension"))
        return cls(paper_id, version_id, source_hash, 4, "e" * 64, topic, venue, year, priority_score,
                   intro, intro, limitation, intro, formal, result, limitation, result)


@dataclass(frozen=True, slots=True)
class _Block:
    page: int
    heading: str
    text: str


def extract_valid_pdf(manifest: AcquisitionManifest, repository_root: Path) -> PdfDocument:
    """Read a VALID_PDF cache entry and conserve manifest size/hash exactly."""

    if not isinstance(manifest, AcquisitionManifest) or manifest.status is not AcquisitionStatus.VALID_PDF:
        raise ValueError("reading extraction consumes only VALID_PDF manifests")
    if manifest.cache_path is None or manifest.content_sha256 is None or manifest.byte_count is None:
        raise ValueError("VALID_PDF manifest lacks cache conservation fields")
    root = repository_root.resolve()
    cache_root = (root / "literature" / "fulltext_cache").resolve()
    target = (root / manifest.cache_path).resolve()
    try:
        target.relative_to(cache_root)
    except ValueError as caught:
        raise ValueError("cache path escapes literature/fulltext_cache") from caught
    payload = target.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest.content_sha256:
        raise ValueError("cache SHA-256 does not match manifest")
    if len(payload) != manifest.byte_count:
        raise ValueError("cache byte count does not match manifest")
    reader = PdfReader(BytesIO(payload), strict=True)
    pages = tuple((page.extract_text() or "").replace("\x00", " ") for page in reader.pages)
    if not pages or not any(page.strip() for page in pages):
        raise ValueError("validated cache PDF no longer has extractable text")
    extraction = "\n".join(pages)
    return PdfDocument(digest, len(pages), pages, hashlib.sha256(extraction.encode("utf-8")).hexdigest())


def _clean(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _heading(value: str) -> str | None:
    line = _clean(value).strip("•▶▷")
    if not line or len(line) > 120 or "|" in line or len(line.split()) > 16:
        return None
    if _HEADING_NUMBER.match(line) or _TIGHT_NUMBERED_HEADING.match(line):
        inline_section = re.match(
            r"^(\d+(?:\.\d+)*\.\s+[A-Z][^.]{2,70}\.)\s*(?:(?:In this (?:sub)?section|We (?:prove|show|study))\b|(?=[A-Z]))",
            line,
        )
        if inline_section:
            return inline_section.group(1)
        if re.match(r"^\d+(?:\.\d+)*\.\s+(?:NP|P|PTIME|CSP|MMSNP)\s+is\s+", line):
            return line
        title = re.sub(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*)\s*", "", line)
        internal_periods = title.rstrip(".").count(".")
        short_the_title = (
            title.casefold().startswith("the ")
            and len(title.split()) <= 8
            and _NUMBERED_PROSE.search(title) is None
        )
        if (
            not title
            or (_NON_HEADING_OPEN.search(title) and not short_the_title)
            or _PSEUDOCODE_OR_FORMULA.search(title)
            or _REFERENCE_LIKE.search(title)
            or internal_periods
            or (len(title.split()) > 8 and _NUMBERED_PROSE.search(title))
            or ("," in title and " and " in title.casefold())
        ):
            return None
        return line
    if line.endswith((".", ";", ",")):
        return None
    if _HEADING_WORDS.fullmatch(line):
        return line
    return None


def _blocks(document: PdfDocument) -> tuple[_Block, ...]:
    blocks: list[_Block] = []
    current_heading: str | None = None
    current_page = 1
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        text = _clean(" ".join(body))
        if current_heading is not None and text:
            blocks.append(_Block(current_page, current_heading, text))
        body = []

    for page_number, page in enumerate(document.pages, 1):
        for raw in page.splitlines():
            inline_abstract = re.match(r"^\s*(Abstract)\.\s+(.+)$", raw, re.IGNORECASE)
            if inline_abstract is not None:
                flush()
                current_heading, current_page = inline_abstract.group(1).title(), page_number
                body.append(inline_abstract.group(2))
                continue
            candidate = _heading(raw)
            if candidate is not None:
                flush()
                current_heading, current_page = candidate, page_number
            elif current_heading is not None and raw.strip():
                body.append(raw)
        flush()
        current_heading = None
    return tuple(blocks)


def _sentences(block: _Block) -> tuple[str, ...]:
    values = tuple(_clean(item) for item in _SENTENCE.split(block.text) if len(_clean(item).split()) >= 5)
    return values or ((block.text,) if block.text else ())


def _signals(sentence: str, *, limit: int = 12) -> tuple[str, ...]:
    result: list[str] = []
    for match in _WORD.findall(sentence):
        word = match.casefold()
        if word in _STOP or word in _UNSUPPORTED_CERTAINTY or word in result:
            continue
        result.append(word)
        if len(result) == limit:
            break
    return tuple(result)


def _loc(block: _Block, sentence: str) -> EvidenceLocation:
    return EvidenceLocation(block.page, block.heading, sentence, _signals(sentence))


def _choose(blocks: tuple[_Block, ...], pattern: re.Pattern[str], *, heading: re.Pattern[str] | None = None,
            reverse: bool = False) -> EvidenceLocation | None:
    scored: list[tuple[int, int, int, _Block, str]] = []
    for block_index, block in enumerate(blocks):
        heading_bonus = 5 if heading is not None and heading.search(block.heading) else 0
        for sentence_index, sentence in enumerate(_sentences(block)):
            matches = len(pattern.findall(sentence))
            if matches:
                order = -block_index if reverse else block_index
                scored.append((matches + heading_bonus, -order, -sentence_index, block, sentence))
    if not scored:
        return None
    _, _, _, block, sentence = max(scored, key=lambda item: item[:3])
    return _loc(block, sentence)


def _by_heading(blocks: tuple[_Block, ...], pattern: re.Pattern[str], *, last: bool = False) -> EvidenceLocation | None:
    matching = [block for block in blocks if pattern.search(block.heading)]
    if not matching:
        return None
    block = matching[-1] if last else matching[0]
    sentences = _sentences(block)
    return _loc(block, sentences[0] if sentences else block.heading)


def _topic(record: Mapping[str, object]) -> str:
    screening = record.get("screening")
    if isinstance(screening, Mapping) and isinstance(screening.get("primary_topic_id"), str):
        return str(screening["primary_topic_id"])
    return "UNASSIGNED"


def _score(record: Mapping[str, object]) -> int:
    screening = record.get("screening")
    value = screening.get("DEEP_READ_PRIORITY_SCORE") if isinstance(screening, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def analyze_document(manifest: AcquisitionManifest, record: Mapping[str, object], document: PdfDocument) -> ReadingAnalysis:
    blocks = _blocks(document)
    abstract = _by_heading(blocks, re.compile(r"\babstract\b", re.I))
    introduction = _by_heading(blocks, re.compile(r"\bintroduction\b", re.I))
    if introduction is None:
        opening = next((block for block in blocks if re.match(r"^1(?:\.\d+)*\.?\s+", block.heading)), None)
        if opening is not None:
            sentences = _sentences(opening)
            introduction = _loc(opening, sentences[0] if sentences else opening.heading)
    conclusion = _by_heading(
        blocks,
        re.compile(r"\b(?:conclusions?|concluding (?:remarks|comments)|discussion|future (?:work|directions)|limitations?|now what)\b", re.I),
        last=True,
    )
    problem = _choose(blocks, _PROBLEM, heading=re.compile(r"abstract|introduction|problem", re.I))
    formal = _choose(blocks, _FORMAL, heading=re.compile(r"formal|preliminar|definition|setting|framework", re.I))
    result = _choose(blocks, _RESULT, heading=re.compile(r"result|theorem|complexity|algorithm", re.I))
    limitation = _choose(blocks, _LIMITATION, heading=re.compile(r"limitation|future|conclusion|discussion", re.I), reverse=True)
    technique = _choose(blocks, _TECHNIQUE, heading=re.compile(r"proof|method|algorithm|result", re.I))
    if conclusion is None and limitation is not None:
        conclusion = limitation
    missing: list[str] = []
    for label, value in (("abstract", abstract), ("introduction", introduction), ("conclusion", conclusion),
                         ("problem", problem), ("formal scope", formal), ("main result", result),
                         ("limitations/future-work", limitation)):
        if value is None:
            missing.append(label)
    headings = {item.heading.casefold() for item in (abstract, introduction, conclusion, problem, formal, result, limitation)
                if item is not None}
    if len(headings) < 3:
        missing.append("three distinct inspected headings")
    shortfall = None if not missing else "missing exact " + ", ".join(missing) + " evidence"
    year = record.get("year")
    venue = record.get("venue_family")
    return ReadingAnalysis(
        manifest.paper_id, manifest.version_id, document.source_hash, document.page_count,
        document.extraction_sha256, _topic(record), str(venue) if isinstance(venue, str) else "UNASSIGNED",
        year if isinstance(year, int) and not isinstance(year, bool) else 0, _score(record),
        abstract, introduction, conclusion, problem, formal, result, limitation, technique, shortfall,
    )


def select_deep_read_ids(analyses: Iterable[ReadingAnalysis], *, limit: int) -> tuple[str, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    grouped: dict[tuple[str, str], list[ReadingAnalysis]] = {}
    for item in analyses:
        if item.deep_read_eligible:
            grouped.setdefault((item.topic, item.venue), []).append(item)
    for values in grouped.values():
        values.sort(key=lambda item: (-item.priority_score, -item.year, item.paper_id))
    selected: list[str] = []
    while grouped and len(selected) < limit:
        heads = [(values[0], key) for key, values in grouped.items()]
        heads.sort(key=lambda pair: (-pair[0].priority_score, pair[0].paper_id, pair[1]))
        for item, key in heads:
            if len(selected) == limit:
                break
            selected.append(item.paper_id)
            grouped[key].pop(0)
        grouped = {key: values for key, values in grouped.items() if values}
    return tuple(selected)


_FULL_SCAN_FIELDS = (
    "identity_version",
    "abstract",
    "problem",
    "formal_scope",
    "main_results_non_complete",
    "limitations",
    "future_open_work",
)
_DEEP_READ_FIELDS = (
    "formal_problem",
    "input",
    "output",
    "semantics",
    "query_languages",
    "constraint_languages",
    "parameters",
    "theorem_result_inventory",
    "upper_bounds",
    "lower_bounds",
    "structural_fragments",
    "assumptions",
    "limitations",
    "open_extensions",
    "proof_technique_signals",
)
_NOT_EXPLICIT = "NOT_EXPLICIT_IN_INSPECTED_SOURCE"
_STAMP = "2026-08-30T00:00:00Z"
_INDEX_NAME = ".generated-index.json"


@dataclass(frozen=True, slots=True)
class AuditLocation:
    page: int
    heading: str


@dataclass(frozen=True, slots=True)
class AuditField:
    value: str
    locations: tuple[AuditLocation, ...]


@dataclass(frozen=True, slots=True)
class SectionMapEntry:
    page: int
    heading: str
    summary: str


@dataclass(frozen=True, slots=True)
class SourceAudit:
    paper_id: str
    version_id: str
    source_hash: str
    read_depth: ReadingState
    reviewer_status: str
    validation_method: str
    section_map: tuple[SectionMapEntry, ...]
    full_scan: Mapping[str, AuditField]
    deep_read: Mapping[str, AuditField] | None

    @property
    def scientific_payload(self) -> dict[str, object]:
        def field_payload(values: Mapping[str, AuditField] | None) -> object:
            if values is None:
                return None
            return {
                key: {
                    "value": values[key].value,
                    "locations": [
                        {"page": item.page, "heading": item.heading}
                        for item in values[key].locations
                    ],
                }
                for key in sorted(values)
            }

        return {
            "paper_id": self.paper_id,
            "version_id": self.version_id,
            "source_hash": self.source_hash,
            "read_depth": self.read_depth.value,
            "reviewer_status": self.reviewer_status,
            "validation_method": self.validation_method,
            "section_map": [
                {"page": item.page, "heading": item.heading, "summary": item.summary}
                for item in self.section_map
            ],
            "full_scan": field_payload(self.full_scan),
            "deep_read": field_payload(self.deep_read),
        }

    @property
    def audit_hash(self) -> str:
        encoded = json.dumps(self.scientific_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _audit_location(value: object) -> AuditLocation:
    if not isinstance(value, Mapping):
        raise ValueError("audit location must be an object")
    page, heading = value.get("page"), value.get("heading")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("audit location page must be positive")
    if not isinstance(heading, str) or not heading.strip():
        raise ValueError("audit location heading must be nonempty")
    return AuditLocation(page, heading.strip())


def _audit_fields(value: object, required: tuple[str, ...], label: str) -> dict[str, AuditField]:
    if not isinstance(value, Mapping) or set(value) != set(required):
        raise ValueError(f"{label} must contain exactly: {', '.join(required)}")
    result: dict[str, AuditField] = {}
    for key in required:
        item = value[key]
        if not isinstance(item, Mapping) or set(item) != {"value", "locations"}:
            raise ValueError(f"{label}.{key} requires value and locations")
        field_value, locations = item["value"], item["locations"]
        if not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(f"{label}.{key}.value must be substantive text or {_NOT_EXPLICIT}")
        if not isinstance(locations, list) or not locations:
            raise ValueError(f"{label}.{key} requires inspected source locations")
        result[key] = AuditField(field_value.strip(), tuple(_audit_location(location) for location in locations))
    return result


def parse_source_audit(value: Mapping[str, object]) -> SourceAudit:
    required = {
        "paper_id", "version_id", "source_hash", "read_depth", "reviewer_status",
        "validation_method", "section_map", "full_scan", "deep_read",
    }
    if set(value) != required:
        raise ValueError("source audit has missing or unknown fields")
    try:
        depth = ReadingState(str(value["read_depth"]))
    except ValueError as caught:
        raise ValueError("source audit depth is invalid") from caught
    if depth not in {ReadingState.FULL_SCAN, ReadingState.DEEP_READ}:
        raise ValueError("source audit can promote only FULL_SCAN or DEEP_READ")
    if value["reviewer_status"] != "SOURCE_VERIFIED" or value["validation_method"] != "FULL_PDF_SOURCE_AUDIT":
        raise ValueError("promoted source audit requires explicit source verification")
    raw_sections = value["section_map"]
    if not isinstance(raw_sections, list) or len(raw_sections) < 3:
        raise ValueError("FULL_SCAN source audit requires at least three real section headings")
    section_map: list[SectionMapEntry] = []
    for raw in raw_sections:
        if not isinstance(raw, Mapping) or set(raw) != {"page", "heading", "summary"}:
            raise ValueError("section_map entries require page, heading, and summary")
        location = _audit_location(raw)
        summary = raw["summary"]
        if not isinstance(summary, str) or len(summary.split()) < 3:
            raise ValueError("section_map summary must be substantive")
        section_map.append(SectionMapEntry(location.page, location.heading, summary.strip()))
    headings = {item.heading.casefold() for item in section_map}
    if len(headings) < 3:
        raise ValueError("FULL_SCAN source audit requires three distinct real section headings")
    full_scan = _audit_fields(value["full_scan"], _FULL_SCAN_FIELDS, "full_scan")
    deep_read = None
    if depth is ReadingState.DEEP_READ:
        deep_read = _audit_fields(value["deep_read"], _DEEP_READ_FIELDS, "deep_read")
    elif value["deep_read"] is not None:
        raise ValueError("FULL_SCAN audit cannot claim a DEEP_READ inventory")
    source_hash = value["source_hash"]
    if not isinstance(source_hash, str) or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None:
        raise ValueError("source audit hash must be SHA-256")
    return SourceAudit(
        str(value["paper_id"]), str(value["version_id"]), source_hash,
        depth, str(value["reviewer_status"]), str(value["validation_method"]),
        tuple(section_map), full_scan, deep_read,
    )


def _heading_occurs(document: PdfDocument, location: AuditLocation) -> bool:
    if location.page > document.page_count:
        return False
    expected = _clean(location.heading).casefold().rstrip(".")
    for raw in document.pages[location.page - 1].splitlines():
        observed = _clean(raw).casefold()
        if observed.rstrip(".") == expected:
            return True
        if expected == "abstract" and re.match(r"^abstract\.\s+\S", observed):
            return True
    return False


def validate_source_audit(audit: SourceAudit, manifest: AcquisitionManifest, document: PdfDocument) -> SourceAudit:
    if (audit.paper_id, audit.version_id, audit.source_hash) != (
        manifest.paper_id, manifest.version_id, document.source_hash,
    ):
        raise ValueError("source audit paper/version/source hash does not match validated PDF")
    locations: list[AuditLocation] = [AuditLocation(item.page, item.heading) for item in audit.section_map]
    for field in audit.full_scan.values():
        locations.extend(field.locations)
    if audit.deep_read is not None:
        for field in audit.deep_read.values():
            locations.extend(field.locations)
    missing = [f"page {item.page} heading {item.heading!r}" for item in locations if not _heading_occurs(document, item)]
    if missing:
        raise ValueError("source audit cites non-heading or absent locations: " + "; ".join(dict.fromkeys(missing)))
    if not any("introduction" in item.heading.casefold() for item in audit.section_map):
        raise ValueError("source audit section map must include the inspected introduction")
    if not any(re.search(
        r"\b(?:conclusions?|concluding|discussions?|future (?:work|directions?)|outlook)\b",
        item.heading,
        re.I,
    )
               for item in audit.section_map):
        raise ValueError("source audit section map must include the inspected conclusion/future-work section")
    return audit


def _field_payload(field: AuditField) -> dict[str, object]:
    return {
        "value": field.value,
        "locations": [{"page": item.page, "heading": item.heading} for item in field.locations],
    }


def _scoped(label: str, field: AuditField) -> str:
    value = field.value
    if len(value) > 470:
        raise ValueError(f"{label} audit prose is too long for a concise evidence pointer")
    return f"Within the inspected {label} scope, {value}"


def render_audited_note(audit: SourceAudit) -> str:
    section_locations = [AuditLocation(item.page, item.heading) for item in audit.section_map]
    all_locations: list[AuditLocation] = []
    for field in audit.full_scan.values():
        all_locations.extend(field.locations)
    if audit.deep_read is not None:
        for field in audit.deep_read.values():
            all_locations.extend(field.locations)
    locations = tuple(dict.fromkeys(all_locations))
    headings = tuple(dict.fromkeys(item.heading for item in locations))
    pages = tuple(dict.fromkeys(item.page for item in locations))
    represented = set(locations)
    try:
        introduction = next(
            item
            for item in section_locations
            if item in represented and "introduction" in item.heading.casefold()
        )
        conclusion = next(
            item
            for item in reversed(section_locations)
            if item in represented and re.search(
                r"\b(?:conclusions?|concluding|discussions?|future (?:work|directions?)|outlook)\b",
                item.heading,
                re.I,
            )
        )
    except StopIteration as caught:
        raise ValueError(
            "source audit introduction and conclusion must be represented by field evidence"
        ) from caught
    coverage: list[dict[str, object]] = [
        {"coverage": CoverageKind.INTRODUCTION.value, "page": introduction.page, "heading": introduction.heading},
        {"coverage": CoverageKind.CONCLUSION.value, "page": conclusion.page, "heading": conclusion.heading},
    ]
    coverage.extend(
        {"coverage": CoverageKind.FULL_SCAN_SECTION.value, "page": item.page, "heading": item.heading}
        for item in locations
    )
    if audit.read_depth is ReadingState.DEEP_READ:
        assert audit.deep_read is not None
        semantic = (
            (CoverageKind.PROBLEM_DEFINITION, audit.deep_read["formal_problem"]),
            (CoverageKind.FORMAL_SCOPE_ASSUMPTIONS, audit.deep_read["assumptions"]),
            (CoverageKind.THEOREM_RESULTS, audit.deep_read["theorem_result_inventory"]),
            (CoverageKind.LIMITATIONS_FUTURE_WORK, audit.deep_read["limitations"]),
        )
        coverage.extend(
            {"coverage": kind.value, "page": field.locations[0].page, "heading": field.locations[0].heading}
            for kind, field in semantic
        )
    inventory = {
        "claim_type": "TASK3_NON_COMPLETE_READING_INVENTORY",
        "complete": False,
        "completeness": "NON_COMPLETE_TASK3",
        "source_audit_hash": audit.audit_hash,
        "full_scan": {key: _field_payload(audit.full_scan[key]) for key in _FULL_SCAN_FIELDS},
        "deep_read": ({key: _field_payload(audit.deep_read[key]) for key in _DEEP_READ_FIELDS}
                      if audit.deep_read is not None else None),
    }
    full = audit.full_scan
    evidence: list[dict[str, object]] = [
        {"evidence_type": "METADATA", "page": full["identity_version"].locations[0].page,
         "heading": full["identity_version"].locations[0].heading,
         "paraphrase": _scoped("identity/version", full["identity_version"]), "verified": True},
        {"evidence_type": "ABSTRACT", "page": full["abstract"].locations[0].page,
         "heading": full["abstract"].locations[0].heading,
         "paraphrase": _scoped("abstract", full["abstract"]), "verified": True},
        {"evidence_type": "PROBLEM_DEFINITION", "page": full["problem"].locations[0].page,
         "heading": full["problem"].locations[0].heading,
         "paraphrase": _scoped("problem", full["problem"]), "verified": True},
        {"evidence_type": "PROBLEM_DEFINITION", "page": full["formal_scope"].locations[0].page,
         "heading": full["formal_scope"].locations[0].heading,
         "paraphrase": _scoped("formal", full["formal_scope"]), "verified": True},
        {"evidence_type": "THEOREM", "page": full["main_results_non_complete"].locations[0].page,
         "heading": full["main_results_non_complete"].locations[0].heading,
         "paraphrase": _scoped("non-complete result", full["main_results_non_complete"]),
         "verified": True, "claim": inventory},
        {"evidence_type": "LIMITATION", "page": full["limitations"].locations[0].page,
         "heading": full["limitations"].locations[0].heading,
         "paraphrase": _scoped("limitations", full["limitations"]), "verified": True},
    ]
    if audit.deep_read is not None:
        deep_problem = audit.deep_read["formal_problem"]
        deep_assumptions = audit.deep_read["assumptions"]
        if (deep_problem.locations[0].page, deep_problem.locations[0].heading) != (
            full["problem"].locations[0].page, full["problem"].locations[0].heading,
        ):
            evidence.append({"evidence_type": "PROBLEM_DEFINITION", "page": deep_problem.locations[0].page,
                             "heading": deep_problem.locations[0].heading,
                             "paraphrase": _scoped("deep formal problem", deep_problem), "verified": True})
        if (deep_assumptions.locations[0].page, deep_assumptions.locations[0].heading) != (
            full["formal_scope"].locations[0].page, full["formal_scope"].locations[0].heading,
        ):
            evidence.append({"evidence_type": "PROBLEM_DEFINITION", "page": deep_assumptions.locations[0].page,
                             "heading": deep_assumptions.locations[0].heading,
                             "paraphrase": _scoped("deep assumptions", deep_assumptions), "verified": True})
    typed_fields: list[tuple[str, str, AuditField]] = [
        ("METADATA", "identity/version", full["identity_version"]),
        ("ABSTRACT", "abstract", full["abstract"]),
        ("PROBLEM_DEFINITION", "problem", full["problem"]),
        ("PROBLEM_DEFINITION", "formal scope", full["formal_scope"]),
        ("THEOREM", "non-complete result", full["main_results_non_complete"]),
        ("LIMITATION", "limitations", full["limitations"]),
        ("LIMITATION", "future/open work", full["future_open_work"]),
    ]
    if audit.deep_read is not None:
        problem_fields = (
            "formal_problem", "input", "output", "semantics", "query_languages", "constraint_languages",
            "parameters", "structural_fragments", "assumptions",
        )
        theorem_fields = ("theorem_result_inventory", "upper_bounds", "lower_bounds", "proof_technique_signals")
        typed_fields.extend(
            ("PROBLEM_DEFINITION", key.replace("_", " "), audit.deep_read[key]) for key in problem_fields
        )
        typed_fields.extend(("THEOREM", key.replace("_", " "), audit.deep_read[key]) for key in theorem_fields)
        typed_fields.extend((
            ("LIMITATION", "deep limitations", audit.deep_read["limitations"]),
            ("LIMITATION", "open extensions", audit.deep_read["open_extensions"]),
        ))
    evidenced_locations = {(int(item["page"]), str(item["heading"])) for item in evidence}
    for evidence_type, label, field in typed_fields:
        for location in field.locations:
            key = (location.page, location.heading)
            if key in evidenced_locations:
                continue
            pointer: dict[str, object] = {
                "evidence_type": evidence_type,
                "page": location.page,
                "heading": location.heading,
                "paraphrase": _scoped(label, field),
                "verified": True,
            }
            if evidence_type == "THEOREM":
                pointer["claim"] = inventory
            evidence.append(pointer)
            evidenced_locations.add(key)
    body = coverage + evidence
    frontmatter = (
        "---\n"
        f"paper_id: {audit.paper_id}\n"
        f"version_id: {audit.version_id}\n"
        f"source_hash: {audit.source_hash}\n"
        f"read_depth: {audit.read_depth.value}\n"
        f"sections: {' | '.join(item.heading for item in audit.section_map)}\n"
        f"pages: {', '.join(str(page) for page in pages)}\n"
        f"headings: {' | '.join(headings)}\n"
        f"created_at: {_STAMP}\n"
        f"updated_at: {_STAMP}\n"
        "extractor_status: pypdf-source-audit-render-v2\n"
        "reviewer_status: SOURCE_VERIFIED\n"
        "---\n"
    )
    text = frontmatter + "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in body
    )
    parse_note_frontmatter(text)
    return text


def _note_name(version_id: str) -> str:
    return version_id.split(":", 1)[1] + ".md"


def _generated_readme(counts: Mapping[str, int]) -> str:
    return (
        "# Full-text reading notes\n\n"
        "This directory is a deterministic rendering of source-verified audit records. "
        "Keyword extraction may prepare review packets but cannot promote read depth or set verified evidence.\n\n"
        f"- FULL_SCAN: {counts['FULL_SCAN']}\n"
        f"- DEEP_READ: {counts['DEEP_READ']}\n"
        f"- SHORTFALL: {counts['SHORTFALL']}\n"
    )


def _owned_files(notes_directory: Path) -> tuple[set[str], bool]:
    if not notes_directory.exists():
        return set(), False
    if not notes_directory.is_dir():
        raise ValueError("notes output root is not a directory")
    entries = tuple(notes_directory.iterdir())
    if not entries:
        return set(), False
    index_path = notes_directory / _INDEX_NAME
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as caught:
            raise ValueError("generated notes ownership index is invalid") from caught
        if not isinstance(index, Mapping) or index.get("schema") not in {1, 2}:
            raise ValueError("generated notes ownership index is invalid")
        expected_keys = {"files", "schema"} if index["schema"] == 1 else {"files", "ledger", "schema"}
        if set(index) != expected_keys:
            raise ValueError("generated notes ownership index is invalid")
        files = index["files"]
        if not isinstance(files, Mapping):
            raise ValueError("generated notes ownership index is invalid")
        expected = set(str(name) for name in files)
        actual = {path.name for path in entries if path.name != _INDEX_NAME}
        if actual != expected or any(not (notes_directory / name).is_file() for name in expected):
            raise ValueError("notes output contains unexpected or unowned files")
        for name, digest in files.items():
            if not isinstance(digest, str) or hashlib.sha256((notes_directory / str(name)).read_bytes()).hexdigest() != digest:
                raise ValueError("owned generated note was manually changed")
        return expected | {_INDEX_NAME}, True
    # One-time migration of the old Task 3 generated corpus.  Every note must carry its old generator marker.
    if all(path.is_file() for path in entries) and all(
        path.name == "README.md" or (
            path.suffix == ".md" and "reviewer_status: deterministic_source_inspection" in path.read_text(encoding="utf-8")
        )
        for path in entries
    ):
        return {path.name for path in entries}, True
    raise ValueError("notes output contains unexpected or unowned files")


def _ledger_is_owned(notes_directory: Path, ledger_path: Path, *, notes_owned: bool, owned_files: set[str]) -> bool:
    if not ledger_path.exists() or not notes_owned:
        return False
    if not ledger_path.is_file():
        raise ValueError("reading ledger output is not a file")
    index_path = notes_directory / _INDEX_NAME
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("schema") == 2:
            ledger = index.get("ledger")
            if not isinstance(ledger, Mapping) or set(ledger) != {"name", "sha256"}:
                raise ValueError("generated notes ownership index is invalid")
            return (
                ledger.get("name") == ledger_path.name
                and ledger.get("sha256") == hashlib.sha256(ledger_path.read_bytes()).hexdigest()
            )
    try:
        content = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    records = content.get("records") if isinstance(content, Mapping) else None
    if not isinstance(records, list):
        return False
    linked: dict[str, str] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("note_path"), str):
            continue
        name = Path(str(record["note_path"])).name
        note_hash = record.get("note_hash")
        if not isinstance(note_hash, str):
            return False
        linked[name] = note_hash
    expected = owned_files - {_INDEX_NAME, "README.md"}
    if set(linked) != expected:
        return False
    return all(
        parse_note_frontmatter((notes_directory / name).read_text(encoding="utf-8")).scientific_hash == digest
        for name, digest in linked.items()
    )


def _invalidate_owned_outputs(
    notes_directory: Path,
    ledger_path: Path,
    *,
    notes_owned: bool,
    ledger_owned: bool,
) -> None:
    if notes_owned and notes_directory.exists():
        shutil.rmtree(notes_directory)
    if ledger_owned and ledger_path.exists():
        ledger_path.unlink()


def _replace_reading_outputs(
    notes_directory: Path,
    ledger_path: Path,
    files: Mapping[str, bytes],
    ledger_content: Mapping[str, object],
) -> None:
    notes_parent = notes_directory.parent
    notes_parent.mkdir(parents=True, exist_ok=True)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    notes_stage = Path(tempfile.mkdtemp(prefix=f".{notes_directory.name}-stage-", dir=notes_parent))
    handle, raw_ledger_stage = tempfile.mkstemp(prefix=f".{ledger_path.name}-", dir=ledger_path.parent)
    os.close(handle)
    ledger_stage = Path(raw_ledger_stage)
    notes_backup = notes_parent / f".{notes_directory.name}-backup-{os.getpid()}"
    ledger_backup = ledger_path.parent / f".{ledger_path.name}-backup-{os.getpid()}"
    notes_had_output = notes_directory.exists()
    ledger_had_output = ledger_path.exists()
    try:
        ledger_payload = (
            json.dumps(ledger_content, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        ledger_stage.write_bytes(ledger_payload)
        hashes: dict[str, str] = {}
        for name, payload in sorted(files.items()):
            (notes_stage / name).write_bytes(payload)
            hashes[name] = hashlib.sha256(payload).hexdigest()
        index = {
            "schema": 2,
            "files": hashes,
            "ledger": {"name": ledger_path.name, "sha256": hashlib.sha256(ledger_payload).hexdigest()},
        }
        (notes_stage / _INDEX_NAME).write_text(
            json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        if notes_backup.exists():
            shutil.rmtree(notes_backup)
        if ledger_backup.exists():
            ledger_backup.unlink()
        if notes_had_output:
            os.replace(notes_directory, notes_backup)
        if ledger_had_output:
            os.replace(ledger_path, ledger_backup)
        os.replace(notes_stage, notes_directory)
        os.replace(ledger_stage, ledger_path)
    except BaseException:
        if notes_stage.exists():
            shutil.rmtree(notes_stage)
        if ledger_stage.exists():
            ledger_stage.unlink()
        if notes_backup.exists():
            if notes_directory.exists():
                shutil.rmtree(notes_directory)
            os.replace(notes_backup, notes_directory)
        elif not notes_had_output and notes_directory.exists():
            shutil.rmtree(notes_directory)
        if ledger_backup.exists():
            if ledger_path.exists():
                ledger_path.unlink()
            os.replace(ledger_backup, ledger_path)
        elif not ledger_had_output and ledger_path.exists():
            ledger_path.unlink()
        raise
    try:
        if notes_backup.exists():
            shutil.rmtree(notes_backup)
        if ledger_backup.exists():
            ledger_backup.unlink()
    except OSError:
        pass


def build_reading_corpus(manifests: Iterable[AcquisitionManifest], records: Iterable[Mapping[str, object]],
                         repository_root: Path, notes_directory: Path, ledger_path: Path, *,
                         audits: Iterable[Mapping[str, object] | SourceAudit] = (),
                         deep_read_target: int = 80) -> dict[str, object]:
    """Render only source-audited promotions through a staged, fail-closed offline rebuild."""

    by_id = {str(item.get("paper_id")): item for item in records if isinstance(item, Mapping)}
    parsed_audits = tuple(item if isinstance(item, SourceAudit) else parse_source_audit(item) for item in audits)
    audits_by_key = {(item.paper_id, item.version_id): item for item in parsed_audits}
    if len(audits_by_key) != len(parsed_audits):
        raise ValueError("source audits require unique paper/version keys")
    owned_files, notes_owned = _owned_files(notes_directory)
    ledger_owned = _ledger_is_owned(
        notes_directory, ledger_path, notes_owned=notes_owned, owned_files=owned_files,
    )
    if ledger_path.exists() and not ledger_owned:
        raise ValueError("reading ledger output is unexpected or unowned")
    valid = sorted((item for item in manifests if item.status is AcquisitionStatus.VALID_PDF),
                   key=lambda item: (item.paper_id, item.version_id))
    documents: dict[tuple[str, str], PdfDocument] = {}
    try:
        for manifest in valid:
            if by_id.get(manifest.paper_id) is None:
                raise ValueError(f"canonical paper record is missing for {manifest.paper_id}")
            document = extract_valid_pdf(manifest, repository_root)
            if manifest.reading_extraction_sha256 is not None and document.extraction_sha256 != manifest.reading_extraction_sha256:
                raise ValueError(f"reading extraction SHA-256 does not match manifest for {manifest.paper_id}")
            documents[_manifest_key(manifest)] = document
        valid_keys = set(documents)
        if not set(audits_by_key) <= valid_keys:
            raise ValueError("source audit has no selected VALID_PDF outcome")
        validated_audits = {
            key: validate_source_audit(audit, next(item for item in valid if _manifest_key(item) == key), documents[key])
            for key, audit in audits_by_key.items()
        }
    except (OSError, ValueError):
        _invalidate_owned_outputs(
            notes_directory, ledger_path, notes_owned=notes_owned, ledger_owned=ledger_owned,
        )
        raise

    note_files: dict[str, bytes] = {}
    ledger_records: list[dict[str, object]] = []
    full_scan_only = deep_read = 0
    for manifest in valid:
        key = _manifest_key(manifest)
        document = documents[key]
        record = by_id[manifest.paper_id]
        audit = validated_audits.get(key)
        base = {
            "paper_id": manifest.paper_id,
            "version_id": manifest.version_id,
            "source_hash": document.source_hash,
            "page_count": document.page_count,
            "extracted_characters": manifest.extracted_characters,
            "validation_extraction_sha256": manifest.validation_extraction_sha256,
            "validation_extraction_normalization": manifest.validation_extraction_normalization,
            "reading_extraction_sha256": document.extraction_sha256,
            "reading_extraction_normalization": manifest.reading_extraction_normalization,
            "title_match": manifest.title_match,
            "doi_match": manifest.doi_match,
            "identity_basis": manifest.identity_basis,
        }
        if audit is None:
            ledger_records.append({
                **base,
                "read_depth": ReadingState.ABSTRACT.value,
                "shortfall_reason": "SOURCE_AUDIT_NOT_COMPLETED",
            })
            continue
        try:
            note_text = render_audited_note(audit)
            note = parse_note_frontmatter(note_text)
        except (OSError, ValueError):
            _invalidate_owned_outputs(
                notes_directory, ledger_path, notes_owned=notes_owned, ledger_owned=ledger_owned,
            )
            raise
        note_name = _note_name(audit.version_id)
        note_files[note_name] = note_text.encode("utf-8")
        full_scan_only += audit.read_depth is ReadingState.FULL_SCAN
        deep_read += audit.read_depth is ReadingState.DEEP_READ
        screening = record.get("screening") if isinstance(record, Mapping) else None
        topic = screening.get("primary_topic_id") if isinstance(screening, Mapping) else None
        ledger_records.append({
            **base,
            "read_depth": audit.read_depth.value,
            "note_path": f"literature/fulltext_notes/{note_name}",
            "note_hash": note.scientific_hash, "shortfall_reason": None,
            "source_audit_hash": audit.audit_hash,
            "topic": topic if isinstance(topic, str) else "UNASSIGNED",
            "venue": record.get("venue_family", "UNASSIGNED"),
            "year": record.get("year", 0),
            "priority_score": screening.get("DEEP_READ_PRIORITY_SCORE", -1) if isinstance(screening, Mapping) else -1,
        })
    counts = {
        "FULL_SCAN": full_scan_only + deep_read,
        "FULL_SCAN_ONLY": full_scan_only,
        "DEEP_READ": deep_read,
        "SHORTFALL": len(valid) - full_scan_only - deep_read,
    }
    content = {"counts": counts, "deep_read_target": deep_read_target,
               "records": sorted(ledger_records, key=lambda item: (str(item["paper_id"]), str(item["version_id"])))}
    note_files["README.md"] = _generated_readme(counts).encode("utf-8")
    _replace_reading_outputs(notes_directory, ledger_path, note_files, content)
    return content


def _manifest_key(manifest: AcquisitionManifest) -> tuple[str, str]:
    return manifest.paper_id, manifest.version_id
