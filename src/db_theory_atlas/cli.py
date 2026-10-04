"""Argparse command-line interface for committed Frontier Atlas indexes."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence

from .index import InvalidIndex, QueryError, RecordNotFound, load_index


DEFAULT_INDEX = "frontier-atlas"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbta",
        description="Search an integrity-checked static Database Theory Frontier Atlas index.",
    )
    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX,
        help="committed manifest index name or path (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="rank exact index records with deterministic BM25-like scoring")
    search.add_argument("query", help="nonempty token query")
    search.add_argument("--id", dest="identifier", help="exact canonical record ID")
    search.add_argument("--type", dest="record_type", choices=(
        "paper", "theorem", "open_problem", "topic", "collision", "ranking", "primitive",
    ))
    search.add_argument("--topic", help="exact topic ID or label")
    search.add_argument("--year", type=int, help="exact publication/primitive year")
    search.add_argument("--year-min", type=int, help="inclusive minimum year")
    search.add_argument("--year-max", type=int, help="inclusive maximum year")
    search.add_argument("--venue", help="exact venue")
    search.add_argument("--status", help="exact controlled status")
    search.add_argument("--complexity", help="exact complexity class")
    search.add_argument("--taxonomy", help="exact controlled taxonomy value")
    search.add_argument("--collision-severity", help="exact collision severity")
    search.add_argument("--ranking-category", help="exact ranking category")
    search.add_argument("--proof-technique", help="exact proof technique")

    for command, help_text in (
        ("paper", "return one exact validated paper record"),
        ("theorem", "return one exact validated theorem record"),
        ("open", "return one exact validated open-problem record"),
        ("topic", "return one exact validated topic record"),
    ):
        child = subparsers.add_parser(command, help=help_text)
        child.add_argument("identifier", help="exact canonical ID; partial IDs are never guessed")

    collision = subparsers.add_parser("collision", help="return one exact validated collision record")
    collision.add_argument("identifier", help="collision ID, or exact candidate ID when PRIOR_ID is supplied")
    collision.add_argument("prior_id", nargs="?", help="exact prior-art ID")

    descendants = subparsers.add_parser("descendants", help="traverse validated graph descendants cycle-safely")
    descendants.add_argument("identifier", help="exact graph-node ID")
    descendants.add_argument("--relation", help="exact EdgeRelation filter")
    descendants.add_argument("--type", dest="node_type", help="exact NodeKind result filter")

    unresolved = subparsers.add_parser("unresolved", help="list validated non-RESOLVED open problems")
    unresolved.add_argument("--category", help="exact ranking category")
    return parser


def _emit(value: object) -> None:
    def json_value(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(key): json_value(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [json_value(child) for child in item]
        return item

    sys.stdout.write(json.dumps(json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _configure_stdout_utf8() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="strict")


def _error(message: str) -> None:
    try:
        sys.stderr.write(message + "\n")
    except (OSError, UnicodeError):
        pass


def main(argv: Sequence[str] | None = None) -> int:
    try:
        _configure_stdout_utf8()
        args = _parser().parse_args(argv)
        index = load_index(args.index)
        if args.command == "search":
            filters = {
                name: getattr(args, name)
                for name in (
                    "identifier", "record_type", "topic", "year", "year_min", "year_max", "venue",
                    "status", "complexity", "taxonomy", "collision_severity", "ranking_category",
                    "proof_technique",
                )
                if getattr(args, name) is not None
            }
            _emit([item.as_dict() for item in index.search(args.query, **filters)])
        elif args.command in {"paper", "theorem", "open", "topic"}:
            _emit(getattr(index, args.command)(args.identifier))
        elif args.command == "collision":
            _emit(index.collision(args.identifier, args.prior_id))
        elif args.command == "descendants":
            _emit(index.descendants(args.identifier, relation=args.relation, node_type=args.node_type))
        elif args.command == "unresolved":
            _emit(index.unresolved(category=args.category))
        return 0
    except InvalidIndex as caught:
        _error(f"invalid index: {caught}")
        return 2
    except RecordNotFound as caught:
        _error(f"not found: {caught}")
        return 3
    except QueryError as caught:
        _error(f"query error: {caught}")
        return 4
    except (OSError, UnicodeError) as caught:
        _error(f"output encoding error: {caught}")
        return 2
    except (ValueError, TypeError) as caught:
        _error(f"invalid request: {caught}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
