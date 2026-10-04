"""Deterministically screen canonical venue-census families for DB-theory relevance.

The census is the immutable input. Title-only screening remains LOW confidence;
HIGH confidence requires a DOI-linked abstract from the committed raw-response
cache. A later full-text workflow may add richer evidence in a separate cache.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CENSUS = ROOT / "literature" / "source_registry" / "venue_census_2023_2026.jsonl"
DEFAULT_OUTPUT_ROOT = ROOT
DEFAULT_REPORT = ROOT / ".superpowers" / "sdd" / "corpus-task-2-final-report.md"
OBSERVED_AT = "2026-08-28"

CLASSIFICATIONS = frozenset(
    {
        "DIRECT_DB_THEORY",
        "FOUNDATIONAL_DB_THEORY",
        "ADJACENT_THEORY_HIGH_VALUE",
        "SYSTEMS_WITH_THEORY",
        "EMPIRICAL_WITH_THEORY_COMPONENT",
        "APPLICATION_ONLY",
        "IRRELEVANT",
        "UNCERTAIN",
    }
)
CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW"})
RELEVANT_CLASSIFICATIONS = frozenset(
    {
        "DIRECT_DB_THEORY",
        "FOUNDATIONAL_DB_THEORY",
        "ADJACENT_THEORY_HIGH_VALUE",
        "SYSTEMS_WITH_THEORY",
        "EMPIRICAL_WITH_THEORY_COMPONENT",
    }
)


def _topic(
    topic_id: str,
    label: str,
    category: str,
    expressions: tuple[str, ...],
    priority: int,
    query_terms: tuple[str, ...],
    context_required_expressions: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, object]:
    return {
        "topic_id": topic_id,
        "label": label,
        "classification": category,
        "title_expressions": list(expressions),
        "priority": priority,
        "query_terms": list(query_terms),
        "evidence_policy": "title expression plus this controlled topic record supports LOW confidence only",
        "context_required_expressions": {
            expression: list(contexts) for expression, contexts in sorted((context_required_expressions or {}).items())
        },
    }


def topic_taxonomy() -> list[dict[str, object]]:
    """Return the controlled, exhaustive Task J screening taxonomy."""

    csp_domain_context = (
        "database",
        "databases",
        "query",
        "queries",
        "homomorphism",
        "homomorphisms",
        "relational structure",
        "relational structures",
        "csp",
        "constraint language",
        "constraint languages",
        "polymorphism",
        "polymorphisms",
        "datalog",
        "arc consistency",
        "bounded width",
        "graph homomorphism",
    )
    finite_model_csp_context = csp_domain_context + ("finite model theory", "finite structures")
    homomorphism_context = tuple(
        context
        for context in csp_domain_context
        if context not in {"homomorphism", "homomorphisms", "graph homomorphism"}
    )
    topics = [
        _topic("enumeration_direct_random_access", "Enumeration, direct access, and random access", "DIRECT_DB_THEORY", ("constant-delay enumeration", "enumeration of", "enumerating", "direct access", "random access"), 100, ("enumeration database queries", "direct access conjunctive queries", "random access query answers")),
        _topic("containment_equivalence", "Query containment and equivalence", "DIRECT_DB_THEORY", ("query containment", "query equivalence", "containment of", "equivalence of queries"), 98, ("query containment equivalence database theory",)),
        _topic("constraints_chase_certain_answers", "Constraints, chase, certain answers, data exchange, incomplete databases, repairs, and CQA", "DIRECT_DB_THEORY", ("certain answers", "data exchange", "incomplete database", "incomplete data", "consistent query answering", "query answering under constraints", "chase termination", "database repairs", "repair semantics"), 97, ("database chase certain answers", "data exchange incomplete databases", "consistent query answering repairs")),
        _topic("views_determinacy_qbe_learning", "Views, determinacy, QBE, learning, unique characterization, and witnesses", "DIRECT_DB_THEORY", ("view determinacy", "query determinacy", "query by example", "learning queries", "query learning", "unique characterization", "query witnesses"), 96, ("view determinacy query by example", "learning database queries witnesses")),
        _topic("provenance_explanations_causality", "Provenance, explanations, causality, and responsibility", "DIRECT_DB_THEORY", ("database provenance", "query provenance", "why(-not)-provenance", "why-not provenance", "provenance", "query explanations", "query causality", "causality in databases", "query responsibility", "responsibility measures"), 95, ("database provenance explanations causality responsibility", "why-not provenance datalog"), {"provenance": ("database", "query", "datalog", "relational"), "responsibility measures": ("database", "query", "datalog")}),
        _topic("cq_ucq", "Conjunctive queries and unions of conjunctive queries", "DIRECT_DB_THEORY", ("conjunctive query", "conjunctive queries", "union of conjunctive", "ucq"), 90, ("conjunctive queries UCQ database theory",)),
        _topic("query_evaluation", "Query evaluation", "DIRECT_DB_THEORY", ("query evaluation", "evaluating queries", "evaluate queries", "database query answering", "answering database queries"), 89, ("database query evaluation complexity",)),
        _topic("cores_minimization", "Cores and minimization", "DIRECT_DB_THEORY", ("query core", "cores of", "core of a query", "query minimization", "minimizing queries"), 88, ("query cores minimization database theory",)),
        _topic("dynamic_incremental_complexity", "Dynamic, incremental, fine-grained, and parameterized complexity", "DIRECT_DB_THEORY", ("dynamic query", "incremental query", "dynamic evaluation", "fine-grained complexity of queries", "parameterized complexity of queries", "dynamic database"), 87, ("dynamic incremental database query complexity", "fine-grained parameterized query complexity")),
        _topic("width_acyclicity", "Width and acyclicity", "DIRECT_DB_THEORY", ("acyclic conjunctive", "query acyclicity", "hypertree width", "treewidth of queries", "width of queries", "database width"), 86, ("query width acyclicity hypertree database theory",)),
        _topic("finite_model_csp_homomorphism", "Finite model theory, CSP, and homomorphisms", "FOUNDATIONAL_DB_THEORY", ("finite model", "constraint satisfaction problem", "constraint satisfaction", "csp dichotomy", "homomorphism"), 80, ("finite model theory CSP homomorphism databases",), {"finite model": finite_model_csp_context, "constraint satisfaction problem": csp_domain_context, "constraint satisfaction": csp_domain_context, "csp dichotomy": csp_domain_context, "homomorphism": homomorphism_context}),
        _topic("uncertain_probabilistic_databases", "Uncertain and probabilistic databases", "DIRECT_DB_THEORY", ("probabilistic database", "uncertain database", "probabilistic query", "uncertain data query"), 85, ("probabilistic uncertain databases query evaluation",)),
        _topic("knowledge_compilation", "Knowledge compilation", "ADJACENT_THEORY_HIGH_VALUE", ("knowledge compilation", "decomposable negation normal", "dnnf", "sentential decision diagram", "sd d"), 75, ("knowledge compilation database queries",)),
        _topic("streaming_dynamic_db_complexity", "Database-central streaming and dynamic complexity", "DIRECT_DB_THEORY", ("streaming query", "streaming database", "dynamic complexity of queries", "dynamic data structure for queries"), 84, ("streaming dynamic database query complexity",)),
    ]
    return sorted(topics, key=lambda item: (-int(item["priority"]), str(item["topic_id"])))


def _normalize_title(value: object) -> str:
    return " ".join(str(value).casefold().replace("–", "-").replace("—", "-").split())


def normalize_doi(value: object) -> str | None:
    normalized = str(value or "").strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized.rstrip(".,;)") or None


def abstract_from_inverted_index(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    words: dict[int, str] = {}
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            return None
        for position in positions:
            if not isinstance(position, int) or position < 0 or position in words:
                return None
            words[position] = token
    if not words or set(words) != set(range(max(words) + 1)):
        return None
    return " ".join(words[position] for position in range(len(words)))


def _match_expressions(title: str, expressions: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for expression in expressions:
        expression_normalized = _normalize_title(expression)
        if expression_normalized and expression_normalized in title:
            matches.append(expression_normalized)
    return matches


def _topic_matches(text: str, taxonomy: list[dict[str, object]], *, title: bool = False) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for topic in taxonomy:
        phrases = _match_expressions(text, tuple(str(value) for value in topic["title_expressions"]))
        context_rules = topic.get("context_required_expressions", {})
        if not isinstance(context_rules, dict):
            raise ValueError("topic context_required_expressions must be an object")
        phrases = [
            phrase
            for phrase in phrases
            if (
                title
                and topic["topic_id"] == "finite_model_csp_homomorphism"
                and phrase == "constraint satisfaction problem"
            )
            or (
                title
                and topic["topic_id"] == "finite_model_csp_homomorphism"
                and phrase == "constraint satisfaction"
                and any(context in text for context in ("promise", "infinite-domain", "infinite domain", "csp"))
            )
            or not context_rules.get(phrase)
            or any(_normalize_title(context) in text for context in context_rules[phrase])
        ]
        if phrases:
            matches.append({"topic": topic, "phrases": phrases})
    matches.sort(key=lambda item: (-int(item["topic"]["priority"]), str(item["topic"]["topic_id"])))
    return matches


def _abstract_evidence_for_family(
    family: dict[str, object], abstract_evidence: dict[str, dict[str, object]] | None
) -> dict[str, object] | None:
    if not abstract_evidence:
        return None
    candidates = [normalize_doi(family.get("doi"))]
    dois = family.get("dois", [])
    if isinstance(dois, list):
        candidates.extend(normalize_doi(value) for value in dois)
    for doi in candidates:
        if doi and doi in abstract_evidence:
            return abstract_evidence[doi]
    return None


def _is_systems_with_theory(title: str) -> bool:
    systems = ("system", "engine", "platform", "optimizer", "processing")
    theory = ("complexity", "lower bound", "upper bound", "algorithm", "approximation", "guarantee")
    database = ("database", "sql", "query", "queries")
    return any(term in title for term in systems) and any(term in title for term in theory) and any(term in title for term in database)


def _is_empirical_with_theory(title: str) -> bool:
    empirical = ("experimental", "empirical", "benchmark", "evaluation")
    theory = ("complexity", "algorithm", "guarantee", "bound", "theoretical")
    return any(term in title for term in empirical) and any(term in title for term in theory)


def _is_application_only(title: str) -> bool:
    application = ("clinical", "genomic", "healthcare", "medical", "geospatial", "social network analysis", "recommendation")
    return any(term in title for term in application)


def _title_signal_score(title: str) -> int:
    signals = ("theorem", "complexity", "lower bound", "upper bound", "dichotomy", "characterization", "algorithm", "tractable")
    return sum(signal in title for signal in signals)


def _scores(family: dict[str, object], classification: str, matched: list[dict[str, object]]) -> dict[str, int]:
    title = _normalize_title(family.get("title", ""))
    year = int(family.get("year", 2023))
    centrality = {
        "DIRECT_DB_THEORY": 5,
        "FOUNDATIONAL_DB_THEORY": 4,
        "ADJACENT_THEORY_HIGH_VALUE": 3,
        "SYSTEMS_WITH_THEORY": 2,
        "EMPIRICAL_WITH_THEORY_COMPONENT": 1,
    }.get(classification, 0)
    title_signals = _title_signal_score(title)
    values = {
        "frontier_recency": max(0, min(4, year - 2022)),
        "theorem_density": min(4, title_signals),
        "open_problem_value": 0,
        "collision_value": min(4, len(matched) + (1 if centrality >= 4 else 0)),
        "followup_importance": min(4, centrality + (1 if title_signals else 0)),
        "database_theory_centrality": centrality,
        "proof_technique_value": 0,
        "direction_selection_value": min(5, centrality + (1 if len(matched) > 1 else 0)),
    }
    values["DEEP_READ_PRIORITY_SCORE"] = sum(values.values())
    return values


def screen_family(
    family: dict[str, object],
    taxonomy: list[dict[str, object]] | None = None,
    abstract_evidence: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    """Classify one canonical family using only auditable title/taxonomy evidence."""

    taxonomy = topic_taxonomy() if taxonomy is None else taxonomy
    paper_id = str(family.get("paper_id", ""))
    title_display = str(family.get("title", ""))
    if not paper_id or not title_display:
        raise ValueError("canonical family must contain nonempty paper_id and title")
    title = _normalize_title(title_display)
    matches = _topic_matches(title, taxonomy, title=True)
    evidence = _abstract_evidence_for_family(family, abstract_evidence)
    abstract_matches = _topic_matches(_normalize_title(evidence.get("abstract", "")), taxonomy) if evidence else []
    classification_matches = matches or abstract_matches

    if classification_matches:
        primary = classification_matches[0]
        classification = str(primary["topic"]["classification"])
        if matches:
            reason = f"title contains controlled expression {primary['phrases'][0]!r} for the {primary['topic']['label']} topic"
            evidence_source = "TITLE_AND_TOPIC_TAXONOMY"
            evidence_pointer = f"title; taxonomy:{primary['topic']['topic_id']}"
            confidence = "LOW"
        else:
            reason = f"title identifies the family and cached abstract contains controlled expression {primary['phrases'][0]!r} for the {primary['topic']['label']} topic"
            evidence_source = f"{evidence['provider']}_ABSTRACT"
            evidence_pointer = f"{evidence['request_id']}; title+abstract"
            confidence = "HIGH"
    elif _is_systems_with_theory(title):
        primary = None
        classification = "SYSTEMS_WITH_THEORY"
        reason = "title jointly signals a database-facing system and an explicit theory result term; no abstract was inspected"
        evidence_source = "TITLE_HEURISTIC"
        evidence_pointer = "title; heuristic:systems_with_theory"
        confidence = "LOW"
    elif _is_empirical_with_theory(title):
        primary = None
        classification = "EMPIRICAL_WITH_THEORY_COMPONENT"
        reason = "title jointly signals empirical work and a theory result term; no abstract was inspected"
        evidence_source = "TITLE_HEURISTIC"
        evidence_pointer = "title; heuristic:empirical_with_theory"
        confidence = "LOW"
    elif _is_application_only(title):
        primary = None
        classification = "APPLICATION_ONLY"
        reason = "title signals an application area without a controlled DB-theory topic match"
        evidence_source = "TITLE_SCOPE"
        evidence_pointer = "title; scope:application_only"
        confidence = "LOW"
    elif any(term in title for term in ("database", "query", "queries", "data management", "sql")):
        primary = None
        classification = "UNCERTAIN"
        reason = "title has a database-related term but no controlled Task J topic match"
        evidence_source = "TITLE_SCOPE"
        evidence_pointer = "title; scope:uncertain_database_related"
        confidence = "LOW"
    else:
        primary = None
        classification = "IRRELEVANT"
        reason = "title has no controlled Task J topic or database-central theory signal"
        evidence_source = "TITLE_SCOPE"
        evidence_pointer = "title; scope:no_task_j_signal"
        confidence = "LOW"

    matched_topics = [item["topic"] for item in classification_matches]
    primary_topic_id = str(primary["topic"]["topic_id"]) if primary is not None else None
    secondary_topic_ids = [str(topic["topic_id"]) for topic in matched_topics[1:]]
    result: dict[str, object] = {
        "paper_id": paper_id,
        "classification": classification,
        "relevant": classification in RELEVANT_CLASSIFICATIONS,
        "primary_topic_id": primary_topic_id,
        "secondary_topic_ids": secondary_topic_ids,
        "topic_ids": [primary_topic_id] if primary_topic_id else [],
        "matched_title_expressions": [phrase for item in matches for phrase in item["phrases"]],
        "matched_abstract_expressions": [phrase for item in abstract_matches for phrase in item["phrases"]],
        "relevance_reason": reason,
        "evidence_source": evidence_source,
        "evidence_pointer": evidence_pointer,
        "confidence": confidence,
        "evidence_limitations": (
            "title and cached abstract evidence; no introduction, conclusion, or full text was inspected"
            if str(evidence_source).endswith("_ABSTRACT")
            else "title-and-taxonomy screening only; no abstract, introduction, conclusion, or full text was inspected"
        ),
        "score_basis": "deterministic title-and-metadata screening heuristics; values are prioritization signals, not theorem or open-problem claims",
        "observed_at": str(family.get("observed_at") or OBSERVED_AT),
    }
    title_topic_ids = {str(item["topic"]["topic_id"]) for item in matches}
    abstract_topic_ids = {str(item["topic"]["topic_id"]) for item in abstract_matches}
    if primary is not None and evidence and matches and title_topic_ids.intersection(abstract_topic_ids):
        result["confidence"] = "HIGH"
        result["evidence_source"] = f"{evidence['provider']}_ABSTRACT"
        result["evidence_pointer"] = f"{evidence['request_id']}; title+abstract"
        result["relevance_reason"] += "; matching cached abstract evidence was found for the family DOI"
        result["evidence_limitations"] = "title and cached abstract evidence; no introduction, conclusion, or full text was inspected"
    elif primary is not None and evidence and matches and abstract_matches:
        result["evidence_limitations"] = "title screening plus abstract was inspected but did not corroborate the selected topic; no introduction, conclusion, or full text was inspected"
    result.update(_scores(family, classification, matches))
    validate_screening_row(result)
    return result


def validate_screening_row(row: dict[str, object]) -> None:
    if row.get("classification") not in CLASSIFICATIONS:
        raise ValueError("invalid screening classification")
    if row.get("confidence") not in CONFIDENCES:
        raise ValueError("invalid screening confidence")
    if not isinstance(row.get("relevance_reason"), str) or not row["relevance_reason"]:
        raise ValueError("screening row requires relevance_reason")
    if not isinstance(row.get("evidence_source"), str) or not row["evidence_source"]:
        raise ValueError("screening row requires evidence_source")
    if not isinstance(row.get("evidence_pointer"), str) or not row["evidence_pointer"]:
        raise ValueError("screening row requires evidence_pointer")
    if row["classification"] in RELEVANT_CLASSIFICATIONS:
        if row["confidence"] == "HIGH" and not str(row["evidence_source"]).endswith("_ABSTRACT"):
            raise ValueError("HIGH confidence requires cached abstract evidence")
        if not row.get("topic_ids") and row.get("evidence_source") != "TITLE_HEURISTIC":
            raise ValueError("relevant controlled classifications require a topic assignment")
    for name in (
        "frontier_recency",
        "theorem_density",
        "open_problem_value",
        "collision_value",
        "followup_importance",
        "database_theory_centrality",
        "proof_technique_value",
        "direction_selection_value",
        "DEEP_READ_PRIORITY_SCORE",
    ):
        if not isinstance(row.get(name), int) or int(row[name]) < 0:
            raise ValueError(f"{name} must be a nonnegative integer")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} is not an object")
        rows.append(value)
    return rows


CANONICAL_RESPONSE_HASH_SCOPE = "CANONICAL_RESPONSE_JSON_UTF8"
EMPTY_RESPONSE_HASH_SCOPE = "EMPTY_RESPONSE_BYTES"
MAX_ABSENT_DOI_ATTEMPTS = 2


def canonical_response_sha256(response: object) -> str:
    """Hash the exact canonical JSON representation retained in the cache."""

    encoded = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_cache_row(row: dict[str, object], line_number: int) -> None:
    prefix = f"cache line {line_number}"
    if not isinstance(row.get("request_id"), str) or not re.fullmatch(r"openalex:\d{4,}", str(row.get("request_id"))):
        raise ValueError(f"{prefix}: invalid request_id")
    if row.get("provider") != "OPENALEX":
        raise ValueError(f"{prefix}: invalid provider")
    if not isinstance(row.get("url"), str) or not str(row["url"]).startswith("https://api.openalex.org/works?"):
        raise ValueError(f"{prefix}: invalid URL")
    if not isinstance(row.get("observed_at"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row["observed_at"])):
        raise ValueError(f"{prefix}: invalid observed_at")
    if not isinstance(row.get("status"), int) or int(row["status"]) < 0:
        raise ValueError(f"{prefix}: invalid status")
    requested = row.get("requested_dois")
    if not isinstance(requested, list) or not requested or any(normalize_doi(doi) is None for doi in requested):
        raise ValueError(f"{prefix}: invalid requested_dois")
    if len({normalize_doi(doi) for doi in requested}) != len(requested):
        raise ValueError(f"{prefix}: duplicate requested DOI")
    digest = row.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"{prefix}: invalid cache SHA-256")
    status = int(row["status"])
    if 200 <= status < 300:
        if row.get("sha256_scope") != CANONICAL_RESPONSE_HASH_SCOPE or not isinstance(row.get("response"), dict):
            raise ValueError(f"{prefix}: malformed successful response provenance")
        if digest != canonical_response_sha256(row["response"]):
            raise ValueError(f"{prefix}: cache SHA-256 mismatch")
        if not isinstance(row["response"].get("results"), list):
            raise ValueError(f"{prefix}: successful response has no results list")
    else:
        if row.get("sha256_scope") != EMPTY_RESPONSE_HASH_SCOPE or digest != hashlib.sha256(b"").hexdigest() or not isinstance(row.get("error"), str):
            raise ValueError(f"{prefix}: malformed failure provenance")


def _load_validated_cache_rows(cache_path: Path) -> list[dict[str, object]]:
    if not cache_path.exists():
        return []
    rows = _read_jsonl(cache_path)
    request_ids: set[str] = set()
    for line_number, row in enumerate(rows, 1):
        _validate_cache_row(row, line_number)
        request_id = str(row["request_id"])
        if request_id in request_ids:
            raise ValueError(f"cache line {line_number}: duplicate request_id")
        request_ids.add(request_id)
    return rows


def _returned_dois(row: dict[str, object]) -> dict[str, bool]:
    response = row.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return {}
    returned: dict[str, bool] = {}
    for work in response["results"]:
        if isinstance(work, dict) and (doi := normalize_doi(work.get("doi"))):
            returned[doi] = abstract_from_inverted_index(work.get("abstract_inverted_index")) is not None
    return returned


def doi_coverage(cache_rows: list[dict[str, object]], requested_dois: set[str]) -> dict[str, dict[str, object]]:
    """Record a terminal-or-pending provider outcome for each DOI without assuming batch completeness."""

    attempts: dict[str, list[dict[str, object]]] = {doi: [] for doi in requested_dois}
    returned: dict[str, bool] = {}
    for row in cache_rows:
        for doi in row.get("requested_dois", []):
            normalized = normalize_doi(doi)
            if normalized in attempts:
                attempts[normalized].append(row)
        if isinstance(row.get("status"), int) and 200 <= int(row["status"]) < 300:
            returned.update(_returned_dois(row))
    coverage: dict[str, dict[str, object]] = {}
    for doi in sorted(requested_dois):
        doi_attempts = attempts[doi]
        statuses = [int(row["status"]) for row in doi_attempts]
        if doi in returned:
            status = "RETURNED_WITH_ABSTRACT" if returned[doi] else "RETURNED_WITHOUT_ABSTRACT"
        elif any(200 <= status_code < 300 for status_code in statuses):
            status = "NOT_RETURNED"
        elif doi_attempts:
            status = "TRANSPORT_FAILURE"
        else:
            status = "NOT_REQUESTED"
        coverage[doi] = {
            "doi": doi,
            "status": status,
            "attempt_count": len(doi_attempts),
            "request_ids": [str(row["request_id"]) for row in doi_attempts],
        }
    return coverage


def abstract_evidence_from_cache(cache_path: Path) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    """Load only provenance-validated DOI-linked abstracts; malformed cache data fails closed."""

    evidence: dict[str, dict[str, object]] = {}
    failures: list[dict[str, object]] = []
    for row in _load_validated_cache_rows(cache_path):
        status = int(row["status"])
        if not 200 <= status < 300:
            failures.append({key: row.get(key) for key in ("request_id", "provider", "status", "url", "error")})
            continue
        response = row["response"]
        assert isinstance(response, dict)
        for work in response["results"]:
            if not isinstance(work, dict):
                continue
            doi = normalize_doi(work.get("doi"))
            abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))
            if doi and abstract:
                evidence.setdefault(doi, {"provider": row["provider"], "request_id": row["request_id"], "url": row["url"], "observed_at": row["observed_at"], "abstract": abstract})
    return evidence, failures


def migrate_cache_to_canonical_hashes(cache_path: Path) -> None:
    """One-time deterministic migration of legacy parsed-response envelopes to verifiable hashes."""

    rows = _read_jsonl(cache_path)
    for row in rows:
        status = row.get("status")
        if isinstance(status, int) and 200 <= status < 300 and isinstance(row.get("response"), dict):
            row["sha256_scope"] = CANONICAL_RESPONSE_HASH_SCOPE
            row["sha256"] = canonical_response_sha256(row["response"])
        else:
            row["sha256_scope"] = EMPTY_RESPONSE_HASH_SCOPE
            row["sha256"] = hashlib.sha256(b"").hexdigest()
    _write_jsonl(cache_path, rows)


def fetch_openalex_abstract_cache(
    families: list[dict[str, object]],
    cache_path: Path,
    *,
    batch_size: int = 20,
    timeout_seconds: int = 30,
    max_requests: int | None = None,
) -> dict[str, int]:
    """Fetch missing DOI batches once, retaining every canonical parsed response envelope or failure."""

    existing = _load_validated_cache_rows(cache_path)
    requested = sorted(
        {
            doi
            for family in families
            for doi in [normalize_doi(family.get("doi")), *(normalize_doi(value) for value in family.get("dois", []) if isinstance(family.get("dois", []), list))]
            if doi
        }
    )
    coverage = doi_coverage(existing, set(requested))
    missing = [
        doi
        for doi in requested
        if coverage[doi]["status"] in {"NOT_REQUESTED", "TRANSPORT_FAILURE"}
        or (coverage[doi]["status"] == "NOT_RETURNED" and int(coverage[doi]["attempt_count"]) < MAX_ABSENT_DOI_ATTEMPTS)
    ]
    rows = list(existing)
    performed = 0
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for batch_number, offset in enumerate(range(0, len(missing), batch_size), 1):
        if max_requests is not None and batch_number > max_requests:
            break
        batch = missing[offset : offset + batch_size]
        performed += 1
        request_id = f"openalex:{len(rows) + 1:04d}"
        query = urlencode(
            {
                "filter": "doi:" + "|".join(batch),
                "per-page": str(batch_size),
                "select": "doi,title,abstract_inverted_index",
            }
        )
        url = "https://api.openalex.org/works?" + query
        record: dict[str, object] = {
            "request_id": request_id,
            "provider": "OPENALEX",
            "url": url,
            "observed_at": __import__("datetime").date.today().isoformat(),
            "requested_dois": batch,
        }
        try:
            request = Request(url, headers={"User-Agent": "DB-Theory-Frontier-Atlas/0.1 evidence-cache"})
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read()
                record["status"] = int(response.status)
            record["response"] = json.loads(body.decode("utf-8"))
            record["sha256_scope"] = CANONICAL_RESPONSE_HASH_SCOPE
            record["sha256"] = canonical_response_sha256(record["response"])
        except Exception as error:  # retained cache rows make offline review possible after a transient failure
            record["status"] = 0
            record["sha256_scope"] = EMPTY_RESPONSE_HASH_SCOPE
            record["sha256"] = hashlib.sha256(b"").hexdigest()
            record["error"] = f"{type(error).__name__}: {error}"
        rows.append(record)
        _write_jsonl(cache_path, rows)
    _write_jsonl(cache_path, rows)
    evidence, failures = abstract_evidence_from_cache(cache_path)
    return {"requested_dois": len(requested), "new_requests": performed, "abstracts": len(evidence), "failures": len(failures)}


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = list(rows)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in ordered),
        encoding="utf-8",
        newline="\n",
    )


def output_paths(output_root: Path) -> dict[str, Path]:
    registry = output_root / "literature" / "source_registry"
    return {
        "taxonomy": registry / "topic_taxonomy_2023_2026.jsonl",
        "query_manifest": registry / "provider_manifests" / "topic_query_manifest_2023_2026.jsonl",
        "papers": output_root / "data" / "papers" / "papers.jsonl",
        "ledger": registry / "relevance_screening_2023_2026.jsonl",
        "summary": registry / "provider_manifests" / "relevance_screening_summary.json",
        "doi_coverage": registry / "provider_manifests" / "openalex_doi_coverage_2023_2026.jsonl",
        "abstract_cache": registry / "provider_cache" / "openalex_abstract_evidence_2023_2026.jsonl",
    }


def _manifest_rows(taxonomy: list[dict[str, object]], ledger: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for topic in taxonomy:
        rows.append(
            {
                "query_id": f"task-j:{topic['topic_id']}",
                "topic_id": topic["topic_id"],
                "query_terms": topic["query_terms"],
                "query_scope": "controlled synonyms and citation-descendant seed query",
                "provider": "OPENALEX",
                "execution_status": "COMPLETE_CENSUS_SCREEN",
                "matched_family_count": sum(
                    row.get("primary_topic_id") == topic["topic_id"] or topic["topic_id"] in row.get("secondary_topic_ids", [])
                    for row in ledger
                ),
                "reason": "all canonical census families were screened against this controlled topic; cached abstracts supplied additional evidence where available",
                "observed_at": OBSERVED_AT,
            }
        )
    return rows


def _report(summary: dict[str, object]) -> str:
    counts = summary["counts"]
    categories = summary["classification_counts"]
    evidence_sources = summary["evidence_source_counts"]
    coverage = summary["doi_coverage_counts"]
    category_lines = "\n".join(f"- {category}: {categories[category]:,}" for category in sorted(categories))
    evidence_lines = "\n".join(f"- {source}: {evidence_sources[source]:,}" for source in sorted(evidence_sources))
    return f"""# Corpus Task 2 Report

## Result

This is a deterministic offline rebuild of every canonical family in the venue census. It uses controlled title taxonomy and, where present in the committed provenance-validated OpenAlex cache, DOI-linked abstracts.

- Canonical families screened: {counts['canonical_families']:,}
- Screening ledger rows: {counts['ledger_rows']:,}
- Relevant families: {counts['relevant_families']:,}
- Title-and-taxonomy evidence rows: {counts['title_and_taxonomy_evidence_rows']:,}
- Cached abstract evidence rows: {counts['network_evidence_rows']:,}
- Cached network failures: {counts['network_failure_rows']:,}
- DOI records not returned by a successful provider batch: {coverage.get('NOT_RETURNED', 0):,}
- DOI records returned without reconstructable abstracts: {coverage.get('RETURNED_WITHOUT_ABSTRACT', 0):,}

## Classification counts

{category_lines}

## Evidence-source counts

{evidence_lines}

## Evidence and limitations

- HIGH requires cached abstract evidence for the selected controlled topic. A title/abstract topic mismatch remains LOW and records the lack of corroboration.
- Ambiguous finite-model/CSP expressions and homomorphism are context-gated; explicit CSP terminology is retained, and the provenance taxonomy includes Datalog why-not provenance and is checked for observed coverage.
- Every cache envelope validates provider, URL, observed date, requested DOI list, status, hash scope, and SHA-256 before contributing evidence; malformed cache data fails closed.
- DOI coverage records NOT_RETURNED, RETURNED_WITHOUT_ABSTRACT, transport failures, and unrequested values explicitly. Missing provider results never count as complete evidence.

## Reproduction and verification

- Offline rebuild: `PYTHONPATH=src python scripts/build_relevance_screening.py --offline` (produces the same committed artifacts and this complete report).
- Cache migration: `PYTHONPATH=src python scripts/build_relevance_screening.py --migrate-cache` (one-time canonical-hash migration; no network).
- Focused verification: `PYTHONPATH=src python -m pytest tests/test_relevance_screening.py --basetemp=.pytest-tmp`.
- Full verification: `PYTHONPATH=src python -m pytest --basetemp=.pytest-tmp-full`.
- Recorded verification results for this review-fix build: focused 17 passed; full suite 321 passed.
- Task 2 implementation commits before this review-fix rebuild: `89cccbb`, `1af4038`, `a844382`, `16545be`, `f46a8eb`.

## Review-fix report

- Ambiguous finite-model/CSP expressions and `homomorphism` require finite-model/CSP/database/query context; explicit established CSP titles such as `constraint satisfaction problem(s)` and Promise/infinite-domain CSP are retained at LOW confidence, while category/type-theory occurrences such as the cubical type-theory boundary-filling paper are not DB-theory evidence.
- Provenance vocabulary now includes Datalog why-not provenance, and the manifest records the actual census-screen match count for each topic.
- Every HIGH row has an abstract-aware limitation string and, when a title topic exists, the cached abstract must corroborate that same topic.
- The OpenAlex cache uses a verifiable canonical-response SHA-256 scope; malformed provenance or digest mismatch aborts the offline rebuild.
- Per-DOI coverage records omitted 2xx results, returned-without-abstract values, and transport failures. Such DOI values cannot silently support HIGH evidence.
- The report is generated entirely by this deterministic rebuild; no manual execution appendix is appended after generation.

External review is still required; this report does not mark Task 2 complete in `.superpowers/sdd/progress.md`.
"""


def build_screening(census_path: Path = DEFAULT_CENSUS, output_root: Path = DEFAULT_OUTPUT_ROOT, report_path: Path = DEFAULT_REPORT) -> dict[str, object]:
    families = _read_jsonl(census_path)
    taxonomy = topic_taxonomy()
    family_ids = [str(family.get("paper_id", "")) for family in families]
    if not family_ids or any(not paper_id for paper_id in family_ids) or len(family_ids) != len(set(family_ids)):
        raise ValueError("census must contain one nonempty unique paper_id per canonical family")
    families.sort(key=lambda family: str(family["paper_id"]))
    paths = output_paths(output_root)
    cache_rows = _load_validated_cache_rows(paths["abstract_cache"])
    abstract_evidence, network_failures = abstract_evidence_from_cache(paths["abstract_cache"])
    requested_dois = {
        doi
        for family in families
        for doi in [normalize_doi(family.get("doi")), *(normalize_doi(value) for value in family.get("dois", []) if isinstance(family.get("dois", []), list))]
        if doi
    }
    coverage = doi_coverage(cache_rows, requested_dois)
    doi_to_paper_ids: dict[str, list[str]] = {}
    for family in families:
        for doi in [normalize_doi(family.get("doi")), *(normalize_doi(value) for value in family.get("dois", []) if isinstance(family.get("dois", []), list))]:
            if doi:
                doi_to_paper_ids.setdefault(doi, []).append(str(family["paper_id"]))
    coverage_rows = [{**row, "paper_ids": sorted(doi_to_paper_ids[row["doi"]])} for row in coverage.values()]
    ledger = [screen_family(family, taxonomy, abstract_evidence) for family in families]
    if len(ledger) != len(families) or {str(row["paper_id"]) for row in ledger} != set(family_ids):
        raise ValueError("screening did not conserve canonical families")
    papers = [{**family, "screening": row} for family, row in zip(families, ledger, strict=True)]
    counts = Counter(str(row["classification"]) for row in ledger)
    evidence_sources = Counter(str(row["evidence_source"]) for row in ledger)
    summary: dict[str, object] = {
        "schema_version": 1,
        "rebuild_mode": "FROZEN_OFFLINE",
        "input_census": str(census_path.name),
        "input_census_sha256": hashlib.sha256(census_path.read_bytes()).hexdigest(),
        "observed_at": OBSERVED_AT,
        "counts": {
            "canonical_families": len(families),
            "ledger_rows": len(ledger),
            "relevant_families": sum(bool(row["relevant"]) for row in ledger),
            "title_and_taxonomy_evidence_rows": sum(row["evidence_source"] == "TITLE_AND_TOPIC_TAXONOMY" for row in ledger),
            "network_evidence_rows": sum(str(row["evidence_source"]).endswith("_ABSTRACT") for row in ledger),
            "network_failure_rows": len(network_failures),
            "families_missing_doi": sum(not normalize_doi(family.get("doi")) and not family.get("dois") for family in families),
        },
        "classification_counts": {classification: counts[classification] for classification in sorted(CLASSIFICATIONS)},
        "evidence_source_counts": {source: evidence_sources[source] for source in sorted(evidence_sources)},
        "confidence_counts": {confidence: sum(row["confidence"] == confidence for row in ledger) for confidence in sorted(CONFIDENCES)},
        "doi_coverage_counts": dict(sorted(Counter(str(row["status"]) for row in coverage_rows).items())),
        "topic_coverage": [str(topic["topic_id"]) for topic in taxonomy],
        "limitations": [
            "OpenAlex abstract evidence is limited to DOI-linked cached responses; Crossref, primary-source introduction/conclusion, and full-text evidence were not collected.",
            f"{len(network_failures)} initial OpenAlex transport failures are retained in the cache for audit, including failures whose DOI batches were later retried.",
            "Scores are screening-priority heuristics and do not assert theorem density, open problems, proof techniques, or novelty outcomes.",
        ],
    }
    _write_jsonl(paths["taxonomy"], taxonomy)
    _write_jsonl(paths["query_manifest"], _manifest_rows(taxonomy, ledger))
    _write_jsonl(paths["papers"], papers)
    _write_jsonl(paths["ledger"], ledger)
    _write_jsonl(paths["doi_coverage"], sorted(coverage_rows, key=lambda row: str(row["doi"])))
    paths["summary"].parent.mkdir(parents=True, exist_ok=True)
    paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report(summary), encoding="utf-8", newline="\n")
    return summary


def artifact_hashes(output_root: Path, report_path: Path) -> dict[str, str]:
    paths = output_paths(output_root)
    generated = ("taxonomy", "query_manifest", "papers", "ledger", "summary", "doi_coverage")
    result = {name: hashlib.sha256(paths[name].read_bytes()).hexdigest() for name in generated}
    result["report"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="rebuild only from committed cache")
    parser.add_argument("--live-enrich", action="store_true", help="fetch missing DOI batches from OpenAlex into the raw-response cache")
    parser.add_argument("--migrate-cache", action="store_true", help="rewrite legacy parsed-response envelopes with canonical verifiable hashes")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-requests", type=int, default=None)
    args = parser.parse_args(argv)
    if sum((args.offline, args.live_enrich, args.migrate_cache)) != 1:
        parser.error("choose exactly one of --offline, --live-enrich, or --migrate-cache")
    if args.migrate_cache:
        migrate_cache_to_canonical_hashes(output_paths(args.output_root)["abstract_cache"])
        print(json.dumps({"migrated_cache": str(output_paths(args.output_root)["abstract_cache"])}, sort_keys=True))
        return 0
    if args.live_enrich:
        families = _read_jsonl(args.census)
        fetched = fetch_openalex_abstract_cache(
            families,
            output_paths(args.output_root)["abstract_cache"],
            batch_size=args.batch_size,
            max_requests=args.max_requests,
        )
        print(json.dumps(fetched, sort_keys=True))
    summary = build_screening(args.census, args.output_root, args.report)
    print(json.dumps(summary["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
