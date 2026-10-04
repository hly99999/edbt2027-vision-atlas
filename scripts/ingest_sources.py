"""Ingest a local provider fixture, or explicitly request one live batch."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from db_theory_atlas.ingest import Provider, ProviderManifest, UrllibTransport, ingest_hits, ingest_provider


def _json_default(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {name: getattr(value, name) for name in value.__dataclass_fields__}
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=[provider.value for provider in Provider])
    parser.add_argument("--query", required=True)
    parser.add_argument("--fixture", type=Path, help="local JSON/XML fixture; keeps the command offline")
    parser.add_argument("--live", action="store_true", help="explicitly allow one live provider request")
    parser.add_argument("--output", type=Path, required=True, help="manifest and normalized hits JSON")
    arguments = parser.parse_args(argv)
    if arguments.live == (arguments.fixture is not None):
        parser.error("choose exactly one of --fixture or --live")
    provider = Provider(arguments.provider)
    if arguments.fixture is not None:
        raw = arguments.fixture.read_bytes()
        hits = ingest_hits(raw, provider)
        manifest: object = ProviderManifest(
            provider=provider,
            query=arguments.query,
            requested=len(hits),
            received=len(hits),
            cursor=None,
            page=None,
            payload_hash=hashlib.sha256(raw).hexdigest(),
            status="SUCCESS",
            error_code=None,
            retry_count=0,
            fetched_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            error_detail=None,
        )
    else:
        hits, manifest = ingest_provider(arguments.query, provider, UrllibTransport())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps({"manifest": manifest, "hits": hits}, default=_json_default, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
