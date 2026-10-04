"""Build the evidence-preserving 2023--2026 venue census.

The census deliberately separates discovery observations from canonical
records.  DBLP supplies exact venue streams as a cross-check; DOI-bearing
records are verified against Crossref, and records without usable DOI metadata
fall back to arXiv and then OpenAlex.  No result is synthesized when a provider
fails: the provider manifest records the failure and the canonical record keeps
an explicit source limitation.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "literature" / "source_registry"
MANIFESTS = OUTPUT / "provider_manifests"
PROVIDER_CACHE = OUTPUT / "provider_cache"
FROZEN_CACHE = PROVIDER_CACHE / "normalized_provider_responses_2023_2026.jsonl"
REPORT_PATH = ROOT / ".superpowers" / "sdd" / "corpus-task-1-report.md"
OBSERVED_AT = date(2026, 8, 28).isoformat()
YEARS = (2023, 2024, 2025, 2026)
USER_AGENT = "DB-Theory-Frontier-Atlas/0.1 (evidence census; public scholarly APIs)"


@dataclass(frozen=True)
class VenueSpec:
    family: str
    streams: tuple[str, ...]
    exact_venues: frozenset[str]


VENUES = (
    VenueSpec("ICDT", ("conf/icdt",), frozenset({"ICDT"})),
    VenueSpec("PODS", ("conf/pods",), frozenset({"PODS"})),
    VenueSpec(
        "SIGMOD_PACMMOD",
        ("conf/sigmod", "journals/pacmmod"),
        frozenset({"SIGMOD Conference", "Proc. ACM Manag. Data"}),
    ),
    VenueSpec("TODS", ("journals/tods",), frozenset({"ACM Trans. Database Syst."})),
    VenueSpec("JACM", ("journals/jacm",), frozenset({"J. ACM"})),
    VenueSpec("LMCS", ("journals/lmcs",), frozenset({"Log. Methods Comput. Sci."})),
    VenueSpec("ICALP", ("conf/icalp",), frozenset({"ICALP"})),
    VenueSpec("CSL", ("conf/csl",), frozenset({"CSL"})),
    VenueSpec("LICS", ("conf/lics",), frozenset({"LICS"})),
    VenueSpec("KR_AI_LOGIC", ("conf/kr",), frozenset({"KR"})),
)

JOURNAL_VOLUMES = {
    "journals/pacmmod": {2023: 1, 2024: 2, 2025: 3, 2026: 4},
    "journals/tods": {2023: 48, 2024: 49, 2025: 50, 2026: 51},
    "journals/jacm": {2023: 70, 2024: 71, 2025: 72, 2026: 73},
    "journals/lmcs": {2023: 19, 2024: 20, 2025: 21, 2026: 22},
}

OPENALEX_SOURCES = {
    "ICDT": ("S4306419319",),
    "PODS": ("S4306420993",),
    "SIGMOD_PACMMOD": ("S4387289859",),
    "TODS": ("S90119964",),
    "JACM": ("S118992489",),
    "LMCS": ("S114379355",),
    "ICALP": ("S4306418971",),
    "CSL": ("S4306417978",),
    "LICS": ("S4306420475", "S4210192682"),
    "KR_AI_LOGIC": ("S4306420732",),
}

NON_RESEARCH = re.compile(
    r"\b(front[ -]?matter|workshop front[ -]?matter|preface|editorial|foreword|"
    r"proceedings of|table of contents|call for papers|doctoral symposium|"
    r"invited (?:talk|paper|keynote|abstract)|keynote(?: abstract| address| talk)?|"
    r"demonstration(?: paper)?|demo(?: paper| track)?|tutorial(?: abstract)?|panel|"
    r"workshop (?:summary|report|overview|introduction)|conference organization|"
    r"message from the (?:chairs?|editors?)|award|obituary|erratum|corrigendum|"
    r"correction to)\b",
    re.IGNORECASE,
)
SYSTEMS_SIGNALS = re.compile(
    r"\b(benchmark(?:ing)?|system demonstration|production system|platform|deployment|"
    r"database system|data[ -]?management system|video[ -]?management system|"
    r"end[ -]?to[ -]?end system|cloud[ -]?native|large language models?|llms?|"
    r"foundation models?|code generation|neural network|deep learning|recommendation system|"
    r"hardware acceleration|gpu acceleration|cloud service|industrial experience|"
    r"engineering experience|performance evaluation|low[ -]?resource hardware|throughput|latency)\b",
    re.IGNORECASE,
)
LLM_SIGNALS = re.compile(
    r"\b(large language models?|language models?|llms?|foundation models?|text[ -]?to[ -]?sql|code generation)\b",
    re.IGNORECASE,
)
THEORY_SIGNALS = re.compile(
    r"\b(theorem|proof|lower bound|upper bound|complexity|decidab(?:le|ility)|"
    r"undecidab(?:le|ility)|tractab(?:le|ility)|intractab(?:le|ility)|first[- ]order|"
    r"finite model|descriptive complexity|parameterized|approximation ratio|"
    r"constant[- ]delay|enumeration complexity|query containment|query equivalence|"
    r"logical characterization|axiomatization)\b",
    re.IGNORECASE,
)
VERSION_MARKERS = re.compile(
    r"\b(?:extended|full|short|journal|conference|preliminary)\s+version\b|"
    r"\bversion\s+(?:extended|full|short|journal|conference|preliminary)\b",
    re.IGNORECASE,
)
JOURNAL_FAMILIES = frozenset({"JACM", "TODS", "LMCS"})


def normalized_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).split())


def folded_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", normalized_text(value))
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def normalized_doi(value: str | None) -> str | None:
    if not value:
        return None
    result = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I).lower()
    result = re.sub(r"^doi:\s*", "", result, flags=re.I).rstrip(". ,;")
    return result if re.fullmatch(r"10\.\d{4,9}/\S+", result) else None


def author_names(value: object) -> list[str]:
    if isinstance(value, dict):
        value = value.get("author", [])
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return []
    names = []
    for author in value:
        if isinstance(author, dict):
            name = str(author.get("text", ""))
        else:
            name = str(author)
        name = re.sub(r"\s+\d{4}$", "", html.unescape(name)).strip()
        if name:
            names.append(name)
    return names


def crossref_authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for author in value:
        if not isinstance(author, dict):
            continue
        literal = str(author.get("name", "")).strip()
        if literal:
            names.append(literal)
            continue
        given = str(author.get("given", "")).strip()
        family = str(author.get("family", "")).strip()
        name = " ".join(part for part in (given, family) if part)
        if name:
            names.append(name)
    return names


def first_value(value: object) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = html.unescape(str(value)).strip()
    return text or None


def publication_year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published", "issued", "published-online", "created"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                pass
    return None


def request_bytes(url: str, *, attempts: int = 3, timeout: int = 30) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/xml;q=0.9, */*;q=0.5"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read(), response.geturl()
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
            if isinstance(error, HTTPError) and error.code not in {429, 500, 502, 503, 504}:
                break
            time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def request_json(url: str) -> tuple[dict[str, Any], str]:
    payload, final_url = request_bytes(url)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("provider returned a non-object JSON document")
    return value, final_url


def stable_hash(value: object, length: int = 24) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = list(rows)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in materialized:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def fetch_dblp(spec: VenueSpec, stream: str, year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query = f"stream:streams/{stream}: year:{year}:"
    url = "https://dblp.org/search/publ/api?" + urlencode({"q": query, "h": 1000, "format": "json"})
    started = time.monotonic()
    manifest: dict[str, Any] = {
        "provider": "DBLP",
        "source_tier": "T2",
        "venue_family": spec.family,
        "stream": stream,
        "year": year,
        "query_url": url,
        "observed_at": OBSERVED_AT,
    }
    try:
        payload, final_url = request_json(url)
        hits_value = payload.get("result", {}).get("hits", {}).get("hit", [])
        if isinstance(hits_value, dict):
            hits_value = [hits_value]
        hits = hits_value if isinstance(hits_value, list) else []
        exact = [hit["info"] for hit in hits if isinstance(hit, dict) and isinstance(hit.get("info"), dict) and hit["info"].get("venue") in spec.exact_venues]
        manifest.update(
            status="OK" if exact else "EMPTY",
            response_url=final_url,
            returned_count=len(hits),
            accepted_count=len(exact),
            response_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        )
        return exact, manifest
    except Exception as error:  # provider failure is recorded, not concealed
        manifest.update(status="FAILED", returned_count=0, accepted_count=0, error=f"{type(error).__name__}: {error}")
        return [], manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def toc_url(stream: str, year: int) -> str:
    kind, short = stream.split("/", 1)
    if stream in JOURNAL_VOLUMES:
        suffix = JOURNAL_VOLUMES[stream][year]
    else:
        suffix = year
    return f"https://dblp.org/db/{kind}/{short}/{short}{suffix}.xml"


def element_text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return html.unescape(value) or None


def parse_toc_entry(entry: ET.Element, spec: VenueSpec) -> dict[str, Any] | None:
    title = element_text(entry.find("title"))
    authors = [element_text(author) for author in entry.findall("author")]
    authors = [author for author in authors if author]
    year_text = element_text(entry.find("year"))
    if not title or not authors or not year_text or not year_text.isdigit():
        return None
    ee_values = [element_text(node) for node in entry.findall("ee")]
    ee_values = [value for value in ee_values if value]
    doi = next((normalized_doi(value) for value in ee_values if normalized_doi(value)), None)
    official_url = next((value for value in ee_values if value.startswith(("http://", "https://"))), None)
    key = str(entry.attrib.get("key", "")).strip()
    venue = element_text(entry.find("booktitle")) or element_text(entry.find("journal")) or next(iter(spec.exact_venues))
    return {
        "authors": {"author": [{"text": author} for author in authors]},
        "title": title,
        "venue": venue,
        "pages": element_text(entry.find("pages")),
        "volume": element_text(entry.find("volume")),
        "number": element_text(entry.find("number")),
        "year": year_text,
        "type": "Conference and Workshop Papers" if entry.tag == "inproceedings" else "Journal Articles",
        "key": key,
        "doi": doi,
        "ee": official_url,
        "url": f"https://dblp.org/rec/{key}" if key else official_url,
    }


def fetch_dblp_toc(spec: VenueSpec, stream: str, year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = toc_url(stream, year)
    started = time.monotonic()
    manifest: dict[str, Any] = {
        "provider": "DBLP",
        "source_tier": "T2",
        "venue_family": spec.family,
        "stream": stream,
        "year": year,
        "query_url": url,
        "observed_at": OBSERVED_AT,
        "method": "venue_toc_xml",
    }
    try:
        payload, final_url = request_bytes(url, attempts=2, timeout=20)
        root = ET.fromstring(payload)
        entries = []
        for tag in ("inproceedings", "article"):
            for element in root.findall(f".//{tag}"):
                parsed = parse_toc_entry(element, spec)
                if parsed is not None and int(parsed["year"]) == year:
                    entries.append(parsed)
        manifest.update(
            status="OK" if entries else "EMPTY",
            response_url=final_url,
            returned_count=len(entries),
            accepted_count=len(entries),
            response_sha256=hashlib.sha256(payload).hexdigest(),
        )
        return entries, manifest
    except HTTPError as error:
        if error.code == 404:
            manifest.update(status="EMPTY", returned_count=0, accepted_count=0, error="HTTP 404: venue-year table not published")
        else:
            manifest.update(status="FAILED", returned_count=0, accepted_count=0, error=f"HTTPError: {error}")
        return [], manifest
    except Exception as error:
        manifest.update(status="FAILED", returned_count=0, accepted_count=0, error=f"{type(error).__name__}: {error}")
        return [], manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def dblp_observation(info: dict[str, Any], family: str) -> dict[str, Any] | None:
    title = first_value(info.get("title"))
    authors = author_names(info.get("authors", {}))
    try:
        year = int(info.get("year"))
    except (TypeError, ValueError):
        return None
    if not title or not authors or year not in YEARS:
        return None
    doi = normalized_doi(first_value(info.get("doi")))
    record_url = first_value(info.get("url"))
    ee = first_value(info.get("ee"))
    evidence_url = record_url or ee
    if not evidence_url:
        return None
    row = {
        "observation_id": "obs:dblp-" + stable_hash((evidence_url, title, authors, year)),
        "provider": "DBLP",
        "source_tier": "T2",
        "retrieval_status": "OK",
        "observed_at": OBSERVED_AT,
        "venue_family": family,
        "venue": str(info.get("venue", "")),
        "year": year,
        "title": title,
        "authors": authors,
        "doi": doi,
        "pages": first_value(info.get("pages")),
        "volume": first_value(info.get("volume")),
        "issue": first_value(info.get("number")),
        "official_url": ee,
        "evidence_url": evidence_url,
        "provider_record_key": first_value(info.get("key")),
        "metadata_hash": hashlib.sha256(json.dumps(info, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    }
    return row


def crossref_lookup(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    doi = row.get("doi")
    assert isinstance(doi, str)
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    manifest: dict[str, Any] = {
        "provider": "CROSSREF",
        "source_tier": "T1",
        "doi": doi,
        "query_url": url,
        "observed_at": OBSERVED_AT,
    }
    started = time.monotonic()
    try:
        payload_bytes, final_url = request_bytes(url, attempts=2, timeout=12)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Crossref returned a non-object JSON document")
        item = payload.get("message")
        if not isinstance(item, dict):
            raise ValueError("Crossref response has no message object")
        title = first_value(item.get("title"))
        authors = crossref_authors(item.get("author"))
        year = publication_year(item)
        if not title or not authors or year is None:
            raise ValueError("Crossref record lacks title, authors, or year")
        observation = {
            "observation_id": "obs:crossref-" + stable_hash((doi, title, authors, year)),
            "provider": "CROSSREF",
            "source_tier": "T1",
            "retrieval_status": "OK",
            "observed_at": OBSERVED_AT,
            "venue_family": row["venue_family"],
            "venue": first_value(item.get("container-title")),
            "year": year,
            "title": title,
            "authors": authors,
            "doi": normalized_doi(first_value(item.get("DOI"))) or doi,
            "pages": first_value(item.get("page")),
            "volume": first_value(item.get("volume")),
            "issue": first_value(item.get("issue")),
            "official_url": first_value(item.get("URL")) or f"https://doi.org/{doi}",
            "evidence_url": url,
            "publisher": first_value(item.get("publisher")),
            "metadata_hash": hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        }
        manifest.update(status="OK", response_url=final_url, response_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        return observation, manifest
    except Exception as error:
        manifest.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        return None, manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def arxiv_lookup(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    title = str(row["title"])
    query = f'ti:"{title.replace(chr(34), "")}"'
    url = "https://export.arxiv.org/api/query?" + urlencode({"search_query": query, "start": 0, "max_results": 3})
    manifest: dict[str, Any] = {
        "provider": "ARXIV",
        "source_tier": "T1",
        "paper_hint": row["observation_id"],
        "query_url": url,
        "observed_at": OBSERVED_AT,
    }
    started = time.monotonic()
    try:
        payload, final_url = request_bytes(url, attempts=1, timeout=8)
        root = ET.fromstring(payload)
        namespace = {"a": "http://www.w3.org/2005/Atom"}
        candidates = []
        for entry in root.findall("a:entry", namespace):
            candidate_title = " ".join((entry.findtext("a:title", default="", namespaces=namespace)).split())
            score = SequenceMatcher(None, normalized_text(title), normalized_text(candidate_title)).ratio()
            candidates.append((score, entry, candidate_title))
        candidates.sort(key=lambda item: (-item[0], item[2]))
        if not candidates or candidates[0][0] < 0.92:
            manifest.update(status="EMPTY", response_url=final_url, returned_count=len(candidates))
            return None, manifest
        score, entry, candidate_title = candidates[0]
        authors = [node.findtext("a:name", default="", namespaces=namespace).strip() for node in entry.findall("a:author", namespace)]
        identifier = entry.findtext("a:id", default="", namespaces=namespace).strip()
        published = entry.findtext("a:published", default="", namespaces=namespace)
        observation = {
            "observation_id": "obs:arxiv-" + stable_hash(identifier),
            "provider": "ARXIV",
            "source_tier": "T1",
            "retrieval_status": "OK",
            "observed_at": OBSERVED_AT,
            "venue_family": row["venue_family"],
            "venue": "arXiv",
            "year": int(published[:4]) if published[:4].isdigit() else row["year"],
            "title": candidate_title,
            "authors": [author for author in authors if author],
            "doi": None,
            "pages": None,
            "volume": None,
            "issue": None,
            "official_url": identifier,
            "evidence_url": identifier,
            "match_score": round(score, 6),
            "metadata_hash": hashlib.sha256(ET.tostring(entry)).hexdigest(),
        }
        manifest.update(status="OK", response_url=final_url, returned_count=len(candidates), match_score=round(score, 6))
        return observation, manifest
    except Exception as error:
        manifest.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        return None, manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def openalex_lookup(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    title = str(row["title"])
    year = int(row["year"])
    url = "https://api.openalex.org/works?" + urlencode(
        {
            "search": title,
            "filter": f"from_publication_date:{year}-01-01,to_publication_date:{year}-12-31",
            "per-page": 5,
        }
    )
    manifest: dict[str, Any] = {
        "provider": "OPENALEX",
        "source_tier": "T2",
        "paper_hint": row["observation_id"],
        "query_url": url,
        "observed_at": OBSERVED_AT,
    }
    started = time.monotonic()
    try:
        payload, final_url = request_json(url)
        results = payload.get("results", [])
        if not isinstance(results, list):
            results = []
        candidates = []
        for item in results:
            if not isinstance(item, dict):
                continue
            candidate_title = str(item.get("title") or item.get("display_name") or "")
            score = SequenceMatcher(None, normalized_text(title), normalized_text(candidate_title)).ratio()
            candidates.append((score, item, candidate_title))
        candidates.sort(key=lambda item: (-item[0], item[2]))
        if not candidates or candidates[0][0] < 0.92:
            manifest.update(status="EMPTY", response_url=final_url, returned_count=len(candidates))
            return None, manifest
        score, item, candidate_title = candidates[0]
        authors = []
        for authorship in item.get("authorships", []):
            if isinstance(authorship, dict) and isinstance(authorship.get("author"), dict):
                name = str(authorship["author"].get("display_name", "")).strip()
                if name:
                    authors.append(name)
        primary = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
        identifiers = item.get("ids") if isinstance(item.get("ids"), dict) else {}
        evidence_url = str(item.get("id") or "")
        observation = {
            "observation_id": "obs:openalex-" + stable_hash(evidence_url),
            "provider": "OPENALEX",
            "source_tier": "T2",
            "retrieval_status": "OK",
            "observed_at": OBSERVED_AT,
            "venue_family": row["venue_family"],
            "venue": first_value(source.get("display_name")),
            "year": int(item.get("publication_year") or year),
            "title": candidate_title,
            "authors": authors,
            "doi": normalized_doi(first_value(identifiers.get("doi"))),
            "pages": None,
            "volume": first_value(primary.get("volume")),
            "issue": first_value(primary.get("issue")),
            "official_url": first_value(primary.get("landing_page_url")),
            "evidence_url": evidence_url,
            "match_score": round(score, 6),
            "metadata_hash": hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        }
        if not evidence_url or not authors:
            raise ValueError("OpenAlex match lacks stable ID or authors")
        manifest.update(status="OK", response_url=final_url, returned_count=len(candidates), match_score=round(score, 6))
        return observation, manifest
    except Exception as error:
        manifest.update(status="FAILED", error=f"{type(error).__name__}: {error}")
        return None, manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def openalex_source_id(value: object) -> str | None:
    text = first_value(value)
    if not text:
        return None
    match = re.search(r"(?:^|/)(S\d+)$", text, flags=re.I)
    return match.group(1).upper() if match else None


def doi_from_url(value: object) -> str | None:
    text = first_value(value)
    if not text:
        return None
    return normalized_doi(text)


def allowed_openalex_source_ids(family: str, *, venue: str | None = None, issue: str | None = None) -> frozenset[str]:
    allowed = set(OPENALEX_SOURCES.get(family, ()))
    if family == "PODS" and (issue == "2" or "proc acm manag data" in normalized_text(venue or "")):
        allowed.update(OPENALEX_SOURCES["SIGMOD_PACMMOD"])
    return frozenset(allowed)


def openalex_observation(
    item: dict[str, Any],
    family: str,
    *,
    expected_year: int | None = None,
) -> dict[str, Any] | None:
    title = first_value(item.get("title")) or first_value(item.get("display_name"))
    year = item.get("publication_year")
    authors = []
    for authorship in item.get("authorships", []):
        if isinstance(authorship, dict) and isinstance(authorship.get("author"), dict):
            name = first_value(authorship["author"].get("display_name"))
            if name:
                authors.append(name)
    work_id = first_value(item.get("id"))
    if not title or not authors or not isinstance(year, int) or year not in YEARS or not work_id:
        return None
    primary = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
    source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
    biblio = item.get("biblio") if isinstance(item.get("biblio"), dict) else {}
    top_level_doi = normalized_doi(first_value(item.get("doi")))
    location_doi = doi_from_url(primary.get("landing_page_url"))
    doi = location_doi or top_level_doi
    issue = first_value(biblio.get("issue"))
    effective_family = "PODS" if family == "SIGMOD_PACMMOD" and year >= 2024 and issue == "2" else family
    source_id = openalex_source_id(source.get("id"))
    venue = first_value(source.get("display_name"))
    validation_conflicts: list[str] = []
    allowed_sources = allowed_openalex_source_ids(effective_family, venue=venue, issue=issue)
    if source_id not in allowed_sources:
        validation_conflicts.append("OPENALEX_SOURCE_FAMILY_MISMATCH")
    if expected_year is not None and year != expected_year:
        validation_conflicts.append("OPENALEX_VENUE_YEAR_MISMATCH")
    if top_level_doi and location_doi and top_level_doi != location_doi:
        validation_conflicts.append("OPENALEX_DOI_LOCATION_MISMATCH")
    return {
        "observation_id": "obs:openalex-" + stable_hash(work_id),
        "provider": "OPENALEX",
        "source_tier": "T2",
        "retrieval_status": "OK",
        "observed_at": OBSERVED_AT,
        "venue_family": effective_family,
        "venue": venue,
        "year": year,
        "title": title,
        "authors": authors,
        "doi": doi,
        "top_level_doi": top_level_doi,
        "pages": "-".join(
            value for value in (first_value(biblio.get("first_page")), first_value(biblio.get("last_page"))) if value
        ) or None,
        "volume": first_value(biblio.get("volume")),
        "issue": issue,
        "official_url": first_value(primary.get("landing_page_url")) or (f"https://doi.org/{doi}" if doi else None),
        "evidence_url": work_id,
        "provider_record_key": work_id.rsplit("/", 1)[-1],
        "source_id": source_id,
        "eligible_for_canonical": not validation_conflicts,
        "validation_conflicts": validation_conflicts,
        "metadata_hash": hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    }


def fetch_openalex_venue(family: str, year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_ids = OPENALEX_SOURCES[family]
    filter_value = f"publication_year:{year},primary_location.source.id:{'|'.join(source_ids)}"
    base_parameters = {"filter": filter_value, "per-page": 200, "cursor": "*"}
    first_url = "https://api.openalex.org/works?" + urlencode(base_parameters)
    manifest: dict[str, Any] = {
        "provider": "OPENALEX",
        "source_tier": "T2",
        "venue_family": family,
        "source_ids": list(source_ids),
        "year": year,
        "query_url": first_url,
        "observed_at": OBSERVED_AT,
        "method": "source_id_year_filter",
    }
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    response_hashes = []
    cursor = "*"
    pages = 0
    try:
        while cursor and pages < 5:
            url = "https://api.openalex.org/works?" + urlencode(
                {"filter": filter_value, "per-page": 200, "cursor": cursor}
            )
            payload, _final_url = request_json(url)
            response_hashes.append(hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
            results = payload.get("results", [])
            if not isinstance(results, list):
                results = []
            for item in results:
                if isinstance(item, dict):
                    observation = openalex_observation(item, family, expected_year=year)
                    if observation is not None:
                        rows.append(observation)
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            next_cursor = meta.get("next_cursor")
            cursor = str(next_cursor) if next_cursor else ""
            pages += 1
            if not results:
                break
        unique = {str(row["observation_id"]): row for row in rows}
        rows = sorted(unique.values(), key=lambda row: normalized_text(str(row["title"])))
        manifest.update(
            status="OK" if rows else "EMPTY",
            returned_count=len(rows),
            accepted_count=len(rows),
            pages=pages,
            response_sha256=hashlib.sha256("".join(response_hashes).encode()).hexdigest(),
        )
        return rows, manifest
    except Exception as error:
        manifest.update(status="FAILED", returned_count=len(rows), accepted_count=len(rows), pages=pages, error=f"{type(error).__name__}: {error}")
        return rows, manifest
    finally:
        manifest["elapsed_ms"] = round((time.monotonic() - started) * 1000)


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalized_text(left), normalized_text(right)).ratio()


def author_key(name: str) -> str:
    words = normalized_text(name).split()
    return words[-1] if words else ""


def dedup_key(row: dict[str, Any]) -> tuple[str, str]:
    doi = normalized_doi(first_value(row.get("doi")))
    if doi:
        return "doi", doi
    authors = row.get("authors")
    first_author = str(authors[0]) if isinstance(authors, list) and authors else ""
    return "title_author", normalized_text(str(row["title"])) + "|" + author_key(first_author)


def paper_id(key: tuple[str, str]) -> str:
    return f"paper:{key[0]}-{stable_hash(key[1], 20)}"


def exclusion_for(row: dict[str, Any]) -> tuple[str, str] | None:
    title = str(row["title"])
    if NON_RESEARCH.search(title):
        return "NON_RESEARCH_MATERIAL", "invited material, front matter, editorial, demo, tutorial, keynote, or similar non-paper content"
    has_theory_signal = bool(THEORY_SIGNALS.search(title))
    if LLM_SIGNALS.search(title) and not has_theory_signal:
        return "LLM_BENCHMARK_SCOPE", "LLM/text-to-SQL benchmark or system paper retained with an explicit theory-scope exclusion"
    if SYSTEMS_SIGNALS.search(title) and not has_theory_signal:
        return "SYSTEMS_SCOPE", "systems-scope exclusion: benchmark, product, platform, deployment, or performance paper lacks an explicit theory-result signal in metadata"
    return None


def _inferred_openalex_source_id(row: dict[str, Any]) -> str | None:
    source_id = openalex_source_id(row.get("source_id"))
    if source_id:
        return source_id
    family = str(row.get("venue_family", ""))
    venue = normalized_text(str(row.get("venue") or ""))
    issue = first_value(row.get("issue"))
    if family == "LICS":
        return "S4210192682" if "proceedings symposium on logic in computer science" in venue else "S4306420475"
    if family == "PODS" and (issue == "2" or "proc acm manag data" in venue):
        return OPENALEX_SOURCES["SIGMOD_PACMMOD"][0]
    configured = OPENALEX_SOURCES.get(family, ())
    return configured[0] if len(configured) == 1 else None


def _journal_volume_year_conflict(row: dict[str, Any]) -> bool:
    family = str(row.get("venue_family", ""))
    volume = first_value(row.get("volume"))
    year = row.get("year")
    if not volume or not str(volume).isdigit() or not isinstance(year, int):
        return False
    stream_by_family = {
        "SIGMOD_PACMMOD": "journals/pacmmod",
        "PODS": "journals/pacmmod",
        "TODS": "journals/tods",
        "JACM": "journals/jacm",
        "LMCS": "journals/lmcs",
    }
    stream = stream_by_family.get(family)
    if stream is None:
        return False
    expected_volume = JOURNAL_VOLUMES[stream].get(year)
    return expected_volume is not None and int(volume) != expected_volume


def observation_validation_conflicts(row: dict[str, Any]) -> tuple[str, ...]:
    conflicts = {str(value) for value in row.get("validation_conflicts", []) if str(value).strip()}
    provider = str(row.get("provider", ""))
    family = str(row.get("venue_family", ""))
    venue = normalized_text(str(row.get("venue") or ""))
    if provider == "OPENALEX":
        source_id = _inferred_openalex_source_id(row)
        if source_id not in allowed_openalex_source_ids(family, venue=str(row.get("venue") or ""), issue=first_value(row.get("issue"))):
            conflicts.add("OPENALEX_SOURCE_FAMILY_MISMATCH")
        top_level_doi = normalized_doi(first_value(row.get("top_level_doi"))) or normalized_doi(first_value(row.get("doi")))
        location_doi = doi_from_url(row.get("official_url"))
        if top_level_doi and location_doi and top_level_doi != location_doi:
            conflicts.add("OPENALEX_DOI_LOCATION_MISMATCH")
        if _journal_volume_year_conflict(row):
            conflicts.add("OPENALEX_VENUE_YEAR_MISMATCH")
    expected_venue_tokens = {
        "JACM": ("journal of the acm", "j acm"),
        "TODS": ("acm transactions on database systems", "acm trans database syst"),
        "LMCS": ("logical methods in computer science", "log methods comput sci"),
    }
    tokens = expected_venue_tokens.get(family)
    if tokens and venue and not any(token in venue for token in tokens):
        conflicts.add("VENUE_FAMILY_MISMATCH")
    return tuple(sorted(conflicts))


def lineage_ids(row: dict[str, Any]) -> frozenset[str]:
    result: set[str] = set()
    for key in ("lineage_ids", "related_ids", "version_lineage"):
        value = row.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            result.update(normalized_text(str(item)) for item in value if normalized_text(str(item)))
    return frozenset(result)


def author_evidence(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_authors = {folded_text(str(value)) for value in left.get("authors", []) if folded_text(str(value))}
    right_authors = {folded_text(str(value)) for value in right.get("authors", []) if folded_text(str(value))}
    return bool(left_authors & right_authors)


def base_title(value: str) -> str:
    return normalized_text(VERSION_MARKERS.sub(" ", value))


def version_title_evidence(left: str, right: str) -> bool:
    left_base = base_title(left)
    right_base = base_title(right)
    left_tokens = set(left_base.split())
    right_tokens = set(right_base.split())
    if min(len(left_tokens), len(right_tokens)) < 4:
        return False
    similarity = SequenceMatcher(None, left_base, right_base).ratio()
    shared = left_tokens & right_tokens
    containment = len(shared) / min(len(left_tokens), len(right_tokens))
    union = len(left_tokens | right_tokens)
    jaccard = len(shared) / union if union else 0.0
    return similarity >= 0.92 or (containment >= 0.85 and jaccard >= 0.70)


def version_author_evidence(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_authors = [folded_text(str(value)) for value in left.get("authors", []) if folded_text(str(value))]
    right_authors = [folded_text(str(value)) for value in right.get("authors", []) if folded_text(str(value))]
    if not left_authors or not right_authors:
        return False
    shared = set(left_authors) & set(right_authors)
    if not shared:
        return False
    smaller_coverage = len(shared) / min(len(set(left_authors)), len(set(right_authors)))
    return left_authors[0] == right_authors[0] or (len(shared) >= 2 and smaller_coverage >= 2 / 3)


def conference_journal_lineage(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_family = str(left.get("venue_family") or "")
    right_family = str(right.get("venue_family") or "")
    if left_family == right_family or ((left_family in JOURNAL_FAMILIES) == (right_family in JOURNAL_FAMILIES)):
        return False
    left_year = int(left.get("year") or 0)
    right_year = int(right.get("year") or 0)
    if not left_year or not right_year or abs(left_year - right_year) > 3:
        return False
    return version_title_evidence(str(left.get("title") or ""), str(right.get("title") or "")) and version_author_evidence(left, right)


def family_groups(observations: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parent = list(range(len(observations)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    by_doi: dict[str, int] = {}
    by_title: dict[str, int] = {}
    for index, row in enumerate(observations):
        doi = normalized_doi(first_value(row.get("doi")))
        title = normalized_text(str(row.get("title") or ""))
        if doi:
            if doi in by_doi:
                union(index, by_doi[doi])
            else:
                by_doi[doi] = index
        if title:
            if title in by_title:
                union(index, by_title[title])
            else:
                by_title[title] = index
    for left in range(len(observations)):
        left_lineage = lineage_ids(observations[left])
        if not left_lineage:
            continue
        for right in range(left + 1, len(observations)):
            if not left_lineage.intersection(lineage_ids(observations[right])):
                continue
            if not author_evidence(observations[left], observations[right]):
                continue
            if title_similarity(str(observations[left]["title"]), str(observations[right]["title"])) >= 0.70:
                union(left, right)
    title_blocks: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(observations):
        tokens = base_title(str(row.get("title") or "")).split()
        if len(tokens) >= 4:
            title_blocks.setdefault((tokens[0], tokens[-1]), []).append(index)
    for candidates in title_blocks.values():
        for offset, left in enumerate(candidates):
            for right in candidates[offset + 1 :]:
                if conference_journal_lineage(observations[left], observations[right]):
                    union(left, right)
    groups: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(observations):
        groups.setdefault(find(index), []).append(row)
    return list(groups.values())


def version_groups(observations: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[tuple[object, ...], list[dict[str, Any]]] = {}
    for row in observations:
        doi = normalized_doi(first_value(row.get("doi")))
        if doi:
            key: tuple[object, ...] = ("doi", doi)
        else:
            key = (
                "metadata",
                normalized_text(str(row.get("title") or "")),
                int(row.get("year") or 0),
                normalized_text(str(row.get("venue") or "")),
            )
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def version_record(rows: list[dict[str, Any]], provider_rank: dict[str, int]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (provider_rank.get(str(row["provider"]), 99), str(row["evidence_url"])))
    usable = [row for row in ordered if not observation_validation_conflicts(row)]
    selected = usable[0] if usable else ordered[0]
    return {
        "version_id": "version:" + stable_hash(
            (
                normalized_doi(first_value(selected.get("doi"))),
                normalized_text(str(selected["title"])),
                int(selected["year"]),
                normalized_text(str(selected.get("venue") or "")),
            ),
            20,
        ),
        "title": selected["title"],
        "authors": list(selected["authors"]),
        "year": int(selected["year"]),
        "venue": selected.get("venue"),
        "venue_family": selected["venue_family"],
        "doi": normalized_doi(first_value(selected.get("doi"))),
        "official_url": selected.get("official_url"),
        "providers": sorted({str(row["provider"]) for row in ordered}, key=lambda value: provider_rank.get(value, 99)),
        "observation_ids": sorted(str(row["observation_id"]) for row in ordered),
        "validation_conflicts": sorted({conflict for row in ordered for conflict in observation_validation_conflicts(row)}),
    }


def conflict_rows(pid: str, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for field in ("title", "authors", "year", "doi"):
        values = []
        for observation in observations:
            value = observation.get(field)
            comparable = (
                normalized_text(str(value))
                if field == "title"
                else tuple(author_key(str(item)) for item in value) if field == "authors" and isinstance(value, list)
                else normalized_doi(first_value(value)) if field == "doi"
                else value
            )
            if value not in (None, [], "") and comparable not in [item[0] for item in values]:
                values.append((comparable, value, observation["provider"], observation["evidence_url"]))
        if len(values) < 2:
            continue
        if field == "title" and all(title_similarity(str(values[0][1]), str(item[1])) >= 0.97 for item in values[1:]):
            continue
        if field == "year" and max(int(item[1]) for item in values) - min(int(item[1]) for item in values) <= 1:
            severity = "WARNING"
            resolution = "online/issue year difference retained; venue census uses exact DBLP stream year"
        else:
            severity = "WARNING" if field == "authors" else "CRITICAL"
            resolution = "provider spelling/order difference retained" if field == "authors" else None
        result.append(
            {
                "paper_id": pid,
                "field": field,
                "severity": severity,
                "resolution": resolution,
                "observations": [
                    {"value": item[1], "provider": item[2], "evidence_url": item[3]} for item in values
                ],
                "observed_at": OBSERVED_AT,
            }
        )
    return result


def canonicalize(observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    canonical = []
    exclusions = []
    conflicts = []
    provider_rank = {"OFFICIAL": 0, "CROSSREF": 1, "ARXIV": 2, "OPENALEX": 3, "DBLP": 4}
    groups = family_groups(observations)
    groups.sort(key=lambda rows: min((normalized_text(str(row["title"])), str(row["observation_id"])) for row in rows))
    for rows in groups:
        rows.sort(key=lambda row: (provider_rank[str(row["provider"])], str(row["evidence_url"])))
        usable_rows = [row for row in rows if not observation_validation_conflicts(row)]
        selection_pool = usable_rows or rows
        dblp = next((row for row in selection_pool if row["provider"] == "DBLP"), None)
        primary = next((row for row in selection_pool if row["provider"] in {"OFFICIAL", "CROSSREF"}), None)
        selected = primary or dblp or rows[0]
        if primary and dblp and title_similarity(str(primary["title"]), str(dblp["title"])) < 0.90:
            selected = dblp
        dois = sorted({doi for row in rows if (doi := normalized_doi(first_value(row.get("doi"))))})
        trusted_dois = sorted({doi for row in usable_rows if (doi := normalized_doi(first_value(row.get("doi"))))})
        identity_dois = trusted_dois or dois
        key = ("doi", identity_dois[0]) if identity_dois else dedup_key(selected)
        pid = paper_id(key)
        providers = sorted({str(row["provider"]) for row in rows}, key=lambda value: provider_rank[value])
        versions = [version_record(version_rows, provider_rank) for version_rows in version_groups(rows)]
        versions.sort(key=lambda value: (int(value["year"]), str(value.get("doi") or ""), normalized_text(str(value["title"]))))
        row_conflicts: list[dict[str, Any]] = []
        for version_rows in version_groups(rows):
            row_conflicts.extend(conflict_rows(pid, version_rows))
        for row in rows:
            validation = observation_validation_conflicts(row)
            if validation:
                row_conflicts.append(
                    {
                        "paper_id": pid,
                        "field": "provider_validation",
                        "severity": "CRITICAL",
                        "resolution": "observation retained for audit but excluded from verified metadata selection",
                        "observations": [
                            {
                                "value": list(validation),
                                "provider": row["provider"],
                                "evidence_url": row["evidence_url"],
                            }
                        ],
                        "observed_at": OBSERVED_AT,
                    }
                )
        exclusion = exclusion_for(selected)
        if not usable_rows:
            exclusion = (
                "PROVIDER_METADATA_CONFLICT",
                "all observations in this family fail venue/source/year/DOI consistency validation",
            )
        authors = list(selected["authors"])
        usable_providers = {str(row["provider"]) for row in usable_rows}
        has_primary = bool(usable_providers & {"OFFICIAL", "CROSSREF"})
        source_status = (
            "CONFLICTED"
            if not usable_rows
            else "CROSSCHECK_ONLY"
            if not has_primary
            else "VERIFIED_WITH_WARNINGS"
            if row_conflicts
            else "VERIFIED_PRIMARY"
        )
        canonical_row = {
            "paper_id": pid,
            "title": selected["title"],
            "normalized_title": normalized_text(str(selected["title"])),
            "authors": authors,
            "first_author_key": author_key(str(authors[0])) if authors else "",
            "year": int(dblp["year"] if dblp else selected["year"]),
            "venue": dblp["venue"] if dblp else selected.get("venue"),
            "venue_family": selected["venue_family"],
            "doi": normalized_doi(first_value(selected.get("doi"))) or normalized_doi(first_value((dblp or {}).get("doi"))),
            "dois": dois,
            "years": sorted({int(row["year"]) for row in rows}),
            "venues": sorted({str(row["venue"]) for row in rows if row.get("venue")}),
            "venue_families": sorted({str(row["venue_family"]) for row in rows}),
            "versions": versions,
            "official_url": selected.get("official_url") or (dblp or {}).get("official_url"),
            "providers": providers,
            "trusted_providers": sorted(usable_providers, key=lambda value: provider_rank[value]),
            "observation_ids": sorted(str(row["observation_id"]) for row in rows),
            "source_status": source_status,
            "source_limitation": (
                "provider consistency validation rejected every observation"
                if not usable_rows
                else None
                if has_primary
                else "no primary DOI/publisher metadata could be resolved; DBLP/OpenAlex/arXiv metadata retained without promotion"
            ),
            "included": exclusion is None,
            "exclusion_reason_code": exclusion[0] if exclusion else None,
            "exclusion_reason": exclusion[1] if exclusion else None,
            "observed_at": OBSERVED_AT,
        }
        canonical.append(canonical_row)
        conflicts.extend(row_conflicts)
        if exclusion:
            exclusions.append(
                {
                    "paper_id": pid,
                    "title": selected["title"],
                    "venue_family": selected["venue_family"],
                    "year": int(canonical_row["year"]),
                    "reason_code": exclusion[0],
                    "reason": exclusion[1],
                    "evidence_urls": sorted({str(row["evidence_url"]) for row in rows}),
                    "observed_at": OBSERVED_AT,
                }
            )
    canonical.sort(key=lambda row: (str(row["venue_family"]), int(row["year"]), normalized_text(str(row["title"])), str(row["paper_id"])))
    exclusions.sort(key=lambda row: (str(row["venue_family"]), int(row["year"]), str(row["paper_id"])))
    conflicts.sort(key=lambda row: (str(row["paper_id"]), str(row["field"])))
    return canonical, exclusions, conflicts


def normalize_frozen_observation(value: dict[str, Any]) -> dict[str, Any]:
    row = dict(value)
    if row.get("provider") == "OPENALEX":
        top_level_doi = normalized_doi(first_value(row.get("top_level_doi"))) or normalized_doi(first_value(row.get("doi")))
        location_doi = doi_from_url(row.get("official_url"))
        row["top_level_doi"] = top_level_doi
        row["doi"] = location_doi or top_level_doi
        row["source_id"] = _inferred_openalex_source_id(row)
    validation = observation_validation_conflicts(row)
    row["validation_conflicts"] = list(validation)
    row["eligible_for_canonical"] = not validation
    return row


def write_frozen_cache(
    path: Path,
    observations: list[dict[str, Any]],
    venue_manifests: list[dict[str, Any]],
    crossref_manifests: list[dict[str, Any]],
    fallback_manifests: list[dict[str, Any]],
) -> None:
    rows: list[dict[str, Any]] = []
    for kind, values in (
        ("observation", observations),
        ("venue_manifest", venue_manifests),
        ("crossref_manifest", crossref_manifests),
        ("fallback_manifest", fallback_manifests),
    ):
        for value in values:
            rows.append({"kind": kind, "payload": value})
    rows.sort(
        key=lambda row: (
            str(row["kind"]),
            json.dumps(row["payload"], sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        )
    )
    jsonl(path, rows)


def load_frozen_cache(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(f"frozen provider cache is missing: {path}")
    result = {
        "observation": [],
        "venue_manifest": [],
        "crossref_manifest": [],
        "fallback_manifest": [],
    }
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("kind") not in result or not isinstance(value.get("payload"), dict):
            raise ValueError(f"invalid frozen cache envelope at line {line_number}")
        result[str(value["kind"])].append(dict(value["payload"]))
    if not result["observation"]:
        raise ValueError("frozen provider cache contains no observations")
    return result


def build_summary(
    observations: list[dict[str, Any]],
    canonical: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    cache_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "observed_at": OBSERVED_AT,
        "rebuild_mode": "FROZEN_OFFLINE",
        "frozen_cache": cache_path.name,
        "frozen_cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
        "year_window": list(YEARS),
        "venue_families": [spec.family for spec in VENUES],
        "routing": ["official DOI/publisher metadata", "Crossref", "arXiv", "OpenAlex", "DBLP cross-check"],
        "source_policy": {
            "T1": ["OFFICIAL", "CROSSREF", "ARXIV"],
            "T2": ["OPENALEX", "DBLP"],
            "T3_used": False,
        },
        "counts": {
            "raw_observations": len(observations),
            "canonical_papers": len(canonical),
            "canonical_versions": sum(len(row["versions"]) for row in canonical),
            "included_canonical_papers": sum(row["included"] is True for row in canonical),
            "excluded_canonical_papers": len(exclusions),
            "metadata_conflicts": len(conflicts),
            "crossref_verified": sum("CROSSREF" in row["trusted_providers"] for row in canonical),
            "crosscheck_only": sum(row["source_status"] == "CROSSCHECK_ONLY" for row in canonical),
        },
        "limitations": [
            "2026 is a partial year observed on 2026-08-28.",
            "DBLP and OpenAlex are cross-check sources; inconsistent source/year/DOI observations remain auditable but cannot be promoted.",
            "Metadata-level systems exclusions are conservative and remain available for Task 2 screening review.",
        ],
    }


def render_report(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    return f"""# Corpus Task 1 Report

## Result

The 2023--2026 venue census is rebuilt deterministically from the committed normalized provider-response cache. Earlier manually transcribed counts in this report are superseded; the generated `census_summary.json` and the matching counts below are authoritative.

- Raw observations: {counts['raw_observations']:,}
- Canonical deduplicated paper families: {counts['canonical_papers']:,}
- Preserved version records: {counts['canonical_versions']:,}
- Included canonical paper families: {counts['included_canonical_papers']:,}
- Explicitly excluded canonical paper families: {counts['excluded_canonical_papers']:,}
- Crossref-verified canonical families: {counts['crossref_verified']:,}
- Cross-check-only canonical families: {counts['crosscheck_only']:,}
- Preserved metadata conflicts: {counts['metadata_conflicts']:,}

Counts use canonical paper families. DOI, exact normalized title, and evidence-backed version lineage are resolved together while individual DOIs, venues, years, and versions remain preserved.

## Integrity changes

- OpenAlex source IDs, venue families, venue years, and top-level versus primary-location DOI URLs are validated before promotion. Inconsistent records remain in the raw evidence and conflict ledger but cannot become `VERIFIED_PRIMARY`.
- Invited talks, prefaces, editorials, keynotes, demos, tutorials, workshop front matter, pure systems papers, and LLM benchmarks receive explicit exclusion reasons unless the title exposes a direct theory-result signal.
- Offline/frozen rebuild is the default. Live provider access occurs only with `--live-refresh`, which replaces the committed normalized cache explicitly.
- The frozen cache SHA-256 is `{summary['frozen_cache_sha256']}`.

## Artifacts

- `literature/source_registry/provider_cache/normalized_provider_responses_2023_2026.jsonl`
- `literature/source_registry/venue_census_2023_2026.jsonl`
- `literature/source_registry/venue_census_observations_2023_2026.jsonl`
- `literature/source_registry/venue_census_conflicts_2023_2026.jsonl`
- `literature/source_registry/venue_census_exclusions_2023_2026.jsonl`
- `literature/source_registry/provider_manifests/`
- `scripts/build_venue_census.py`
- `tests/test_corpus_counts.py`

## Reproduction

Run `python scripts/build_venue_census.py --offline` in a clean checkout. The generated census, manifests, summary, and report are byte-identical to the committed artifacts. Use `--live-refresh` only for an explicit provider refresh.

This task freezes discovery metadata only. Relevance, reading depth, theorem content, and novelty status are deliberately not inferred here.
"""


def rebuild_from_frozen(cache_path: Path, output_dir: Path, report_path: Path) -> dict[str, Any]:
    frozen = load_frozen_cache(cache_path)
    observations = [normalize_frozen_observation(row) for row in frozen["observation"]]
    observations.sort(key=lambda row: (str(row["venue_family"]), int(row["year"]), normalized_text(str(row["title"])), str(row["provider"]), str(row["observation_id"])))
    canonical, exclusions, conflicts = canonicalize(observations)
    manifests = output_dir / "provider_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    jsonl(output_dir / "venue_census_observations_2023_2026.jsonl", observations)
    jsonl(output_dir / "venue_census_2023_2026.jsonl", canonical)
    jsonl(output_dir / "venue_census_exclusions_2023_2026.jsonl", exclusions)
    jsonl(output_dir / "venue_census_conflicts_2023_2026.jsonl", conflicts)
    jsonl(manifests / "venue_year_queries.jsonl", frozen["venue_manifest"])
    jsonl(manifests / "crossref_doi_lookups.jsonl", frozen["crossref_manifest"])
    jsonl(manifests / "fallback_queries.jsonl", frozen["fallback_manifest"])
    summary = build_summary(observations, canonical, exclusions, conflicts, cache_path)
    (manifests / "census_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8", newline="\n")
    return summary


def artifact_hashes(output_dir: Path, report_path: Path) -> dict[str, str]:
    relative_paths = (
        "venue_census_observations_2023_2026.jsonl",
        "venue_census_2023_2026.jsonl",
        "venue_census_exclusions_2023_2026.jsonl",
        "venue_census_conflicts_2023_2026.jsonl",
        "provider_manifests/venue_year_queries.jsonl",
        "provider_manifests/crossref_doi_lookups.jsonl",
        "provider_manifests/fallback_queries.jsonl",
        "provider_manifests/census_summary.json",
    )
    result = {
        path: hashlib.sha256((output_dir / path).read_bytes()).hexdigest()
        for path in relative_paths
    }
    result["corpus-task-1-report.md"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return result


def run_live_refresh() -> int:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    dblp_rows: list[dict[str, Any]] = []
    # A live refresh never reads prior census outputs.  DBLP venue tables are
    # fetched sequentially to keep rate pressure bounded; PODS 2024+ is also
    # represented by PACMMOD issue 2 in the OpenAlex route below.
    for spec in VENUES:
        for year in YEARS:
            for stream in spec.streams:
                infos, _manifest = fetch_dblp_toc(spec, stream, year)
                for info in infos:
                    observation = dblp_observation(info, spec.family)
                    if observation is not None:
                        dblp_rows.append(observation)
                time.sleep(0.75)
    venue_manifests: list[dict[str, Any]] = []
    for spec in VENUES:
        for year in YEARS:
            family_accepted = sum(
                row.get("venue_family") == spec.family and row.get("year") == year for row in dblp_rows
            )
            venue_manifests.append(
                {
                    "provider": "DBLP",
                    "source_tier": "T2",
                    "venue_family": spec.family,
                    "year": year,
                    "streams": list(spec.streams),
                    "status": "PARTIAL" if family_accepted else "FAILED",
                    "accepted_count": family_accepted,
                    "observed_at": OBSERVED_AT,
                    "queries": [
                        {
                            "provider": "DBLP",
                            "source_tier": "T2",
                            "venue_family": spec.family,
                            "year": year,
                            "streams": list(spec.streams),
                            "status": "PARTIAL" if family_accepted else "FAILED",
                            "accepted_count": family_accepted,
                            "observed_at": OBSERVED_AT,
                            "method": "explicit_live_sequential_exact_stream",
                        }
                    ],
                }
            )

    openalex_rows: list[dict[str, Any]] = []
    openalex_queries: dict[tuple[str, int], tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_openalex_venue, spec.family, year): (spec.family, year)
            for spec in VENUES
            for year in YEARS
        }
        for future in as_completed(futures):
            key = futures[future]
            rows, manifest = future.result()
            openalex_queries[key] = (rows, manifest)
            openalex_rows.extend(rows)
    for family_manifest in venue_manifests:
        key = (str(family_manifest["venue_family"]), int(family_manifest["year"]))
        rows, manifest = openalex_queries[key]
        family_manifest["queries"].append(manifest)
        family_manifest["queries"].sort(key=lambda row: (str(row["provider"]), str(row.get("stream", ""))))
        family_manifest["accepted_count"] = int(family_manifest["accepted_count"]) + len(rows)
        if rows:
            family_manifest["status"] = "OK"
        elif family_manifest["status"] == "FAILED" and manifest["status"] in {"EMPTY", "OK"}:
            family_manifest["status"] = "EMPTY"

    # Remove duplicated DBLP hits deterministically before provider expansion.
    unique_dblp = {str(row["observation_id"]): row for row in dblp_rows}
    dblp_rows = sorted(unique_dblp.values(), key=lambda row: (str(row["venue_family"]), int(row["year"]), normalized_text(str(row["title"]))))
    unique_openalex = {str(row["observation_id"]): row for row in openalex_rows}
    openalex_rows = sorted(unique_openalex.values(), key=lambda row: (str(row["venue_family"]), int(row["year"]), normalized_text(str(row["title"]))))
    discovery_rows = dblp_rows + openalex_rows
    print(f"DBLP exact-stream observations: {len(dblp_rows)}; OpenAlex venue observations: {len(openalex_rows)}", flush=True)

    doi_rows: dict[str, dict[str, Any]] = {}
    for row in discovery_rows:
        doi = row.get("doi")
        if isinstance(doi, str) and not observation_validation_conflicts(row):
            doi_rows.setdefault(doi, row)
    crossref_rows: list[dict[str, Any]] = []
    crossref_manifests: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        selected_dois = dict(list(sorted(doi_rows.items()))[:320])
        futures = {executor.submit(crossref_lookup, row): doi for doi, row in selected_dois.items()}
        for future in as_completed(futures):
            observation, manifest = future.result()
            crossref_manifests.append(manifest)
            if observation is not None:
                crossref_rows.append(observation)
    print(
        f"Crossref DOI verifications: {len(crossref_rows)} total; {len(selected_dois)} live attempts of {len(doi_rows)} discovered DOIs",
        flush=True,
    )

    primary_keys = {dedup_key(row) for row in crossref_rows}
    fallback_candidates = [row for row in discovery_rows if dedup_key(row) not in primary_keys]
    fallback_rows: list[dict[str, Any]] = []
    fallback_manifests: list[dict[str, Any]] = []
    # arXiv requests are intentionally sequential and bounded to respect its API.
    # A bounded sample proves and records the fallback route without hammering
    # arXiv's intentionally low-rate public endpoint.  Remaining DBLP-only
    # records stay explicitly CROSSCHECK_ONLY rather than being fabricated.
    for row in fallback_candidates[:10]:
        arxiv_row, arxiv_manifest = arxiv_lookup(row)
        fallback_manifests.append(arxiv_manifest)
        if arxiv_row is not None:
            fallback_rows.append(arxiv_row)
            continue
        openalex_row, openalex_manifest = openalex_lookup(row)
        fallback_manifests.append(openalex_manifest)
        if openalex_row is not None:
            fallback_rows.append(openalex_row)
        time.sleep(0.35)

    observations = discovery_rows + crossref_rows + fallback_rows
    observations.sort(key=lambda row: (str(row["venue_family"]), int(row["year"]), normalized_text(str(row["title"])), str(row["provider"]), str(row["observation_id"])))
    write_frozen_cache(
        FROZEN_CACHE,
        observations,
        venue_manifests,
        sorted(crossref_manifests, key=lambda row: str(row["doi"])),
        sorted(fallback_manifests, key=lambda row: (str(row.get("paper_hint", "")), str(row["provider"]))),
    )
    summary = rebuild_from_frozen(FROZEN_CACHE, OUTPUT, REPORT_PATH)
    print(json.dumps(summary["counts"], sort_keys=True))
    failed = sum(row["status"] == "FAILED" for row in venue_manifests)
    return 1 if failed else 0


def run() -> int:
    summary = rebuild_from_frozen(FROZEN_CACHE, OUTPUT, REPORT_PATH)
    print(json.dumps(summary["counts"], sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", "--frozen", dest="offline", action="store_true", help="rebuild from the committed normalized provider cache (default)")
    mode.add_argument("--live-refresh", action="store_true", help="explicitly query providers, replace the frozen cache, and rebuild outputs")
    arguments = parser.parse_args(argv)
    return run_live_refresh() if arguments.live_refresh else run()


if __name__ == "__main__":
    sys.exit(main())
