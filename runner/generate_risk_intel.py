"""Generate same-day risk-intel.json from a local snapshot or fixture.

This script intentionally keeps the MCP boundary outside the adapter path:
Claude Code can materialize a standardized snapshot into `runner/local/`,
while CI and plain Python environments can rely on fixtures or skip generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .risk_intel_utils import (
    DATA_DIR,
    LOCAL_INPUT_PATH,
    build_risk_intel_chapter,
    hkt_date_str,
    parse_json_file,
    risk_intel_payload,
)


def _log(message: str):
    print(f"  [risk-intel] {message}", file=sys.stderr)


def _load_input(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    _log(f"Loading input snapshot: {path}")
    return parse_json_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local risk intelligence chapter data")
    parser.add_argument("--fixture", help="Read a fixture JSON instead of a local snapshot")
    parser.add_argument("--input", help="Read a JSON snapshot from an explicit path")
    parser.add_argument("--date", help="Override report date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload instead of saving")
    args = parser.parse_args()

    date_str = args.date or hkt_date_str()
    explicit_input = Path(args.input).expanduser() if args.input else None
    fixture_input = Path(args.fixture).expanduser() if args.fixture else None

    snapshot = _load_input(explicit_input) or _load_input(LOCAL_INPUT_PATH)
    source_kind = "snapshot"

    if snapshot is None:
        snapshot = _load_input(fixture_input)
        source_kind = "fixture"

    if snapshot is None:
        _log("No local snapshot available. Skipping risk-intel generation.")
        return 0

    chapter = build_risk_intel_chapter(snapshot, date_str)
    payload = risk_intel_payload(chapter, date_str)
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    out_dir = DATA_DIR / "reports" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "risk-intel.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    _log(f"Saved {out_path} ({source_kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
