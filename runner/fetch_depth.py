"""Deterministic depth data saver and validator.

Ensures ALL SQL rows are saved (never a subset) and validates coverage
against OKX tier instruments.

Usage:
    # Save MCP query result (pipe JSON from getQueryResult on stdin):
    echo '{"data":{"rows":[...]}}' | python3 -m runner.fetch_depth save

    # Validate existing depth file:
    python3 -m runner.fetch_depth check

    # Show the SQL to run:
    python3 -m runner.fetch_depth sql
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_RUNNER_DIR = Path(__file__).resolve().parent
DEPTH_FILE = _RUNNER_DIR / "local" / "depth_sql.json"
TIERS_FILE = _RUNNER_DIR.parent / "params_cli" / "mmr_future" / "current_tiers.json"

MIN_BTC_DEPTH = 1_000_000
MIN_COVERAGE_PCT = 90

DEPTH_SQL_TEMPLATE = """SELECT symbol, contract_type, AVG(avg_depth) AS depth_7d_avg
FROM ads_okx_competitor_all_min_depth_di
WHERE exchange = 'OKX' AND type = '永续'
  AND pt BETWEEN '{start}' AND '{end}'
GROUP BY symbol, contract_type"""


def _log(msg: str):
    print(f"  [fetch-depth] {msg}", file=sys.stderr)


def get_depth_sql() -> str:
    """Return the SQL query with today's date range (7 days back)."""
    hkt = ZoneInfo("Asia/Hong_Kong")
    today = datetime.now(hkt)
    start = (today - timedelta(days=7)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    return DEPTH_SQL_TEMPLATE.format(start=start, end=end)


def save_from_mcp_result(raw: dict) -> dict:
    """Parse MCP getQueryResult response and save ALL rows.

    Accepts either:
      - Full MCP response: {"code":0, "data":{"rows":[...], "columns":[...]}}
      - Just the data part: {"rows":[...], "columns":[...]}
      - Raw rows list: [[symbol, type, depth], ...]
    """
    # Normalize input format
    if "data" in raw and isinstance(raw["data"], dict):
        data = raw["data"]
    elif "rows" in raw:
        data = raw
    elif isinstance(raw, list):
        data = {"rows": raw, "columns": ["symbol", "contract_type", "depth_7d_avg"]}
    else:
        return {"status": "ERROR", "message": f"Unrecognized input format. Keys: {list(raw.keys())}"}

    rows = data.get("rows", [])
    if not rows:
        return {"status": "ERROR", "message": "No rows in input"}

    # Build depth dict from ALL rows
    depth: dict[str, float] = {}
    for row in rows:
        if len(row) >= 3:
            symbol = str(row[0])
            try:
                avg_depth = float(row[2])
            except (ValueError, TypeError):
                continue
            depth[symbol] = avg_depth

    if not depth:
        return {"status": "ERROR", "message": "No valid depth entries parsed"}

    # Validate BTC sanity
    btc = depth.get("BTC-USDT", 0)
    if btc < MIN_BTC_DEPTH:
        return {
            "status": "ERROR",
            "message": f"BTC-USDT depth={btc:,.0f} (need >{MIN_BTC_DEPTH:,}). Data may be corrupted.",
        }

    # Save
    DEPTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEPTH_FILE.write_text(json.dumps(depth, indent=2))

    # Check coverage against tiers
    coverage_info = _check_coverage(depth)

    return {
        "status": "OK",
        "saved": len(depth),
        "path": str(DEPTH_FILE),
        "btc_depth": btc,
        **coverage_info,
    }


def _check_coverage(depth: dict) -> dict:
    """Check depth coverage against tier instruments."""
    if not TIERS_FILE.exists():
        return {"coverage": "unknown", "tiers_file": "missing"}
    try:
        tiers = json.loads(TIERS_FILE.read_text())
    except Exception:
        return {"coverage": "unknown", "tiers_file": "parse_error"}

    tier_symbols = set(tiers.keys())
    depth_symbols = set(depth.keys())
    covered = len(tier_symbols & depth_symbols)
    total = len(tier_symbols)
    pct = covered / total * 100 if total else 0

    return {
        "coverage": f"{covered}/{total} ({pct:.0f}%)",
        "covered": covered,
        "total_tiers": total,
        "coverage_pct": round(pct, 1),
    }


def check() -> bool:
    """Validate existing depth file. Returns True if OK."""
    if not DEPTH_FILE.exists():
        _log(f"FAIL: {DEPTH_FILE} does not exist")
        print(json.dumps({"status": "FAIL", "reason": "file_missing"}))
        return False

    try:
        depth = json.loads(DEPTH_FILE.read_text())
    except Exception as e:
        _log(f"FAIL: {DEPTH_FILE} is not valid JSON: {e}")
        print(json.dumps({"status": "FAIL", "reason": "invalid_json"}))
        return False

    btc = depth.get("BTC-USDT", 0)
    if btc < MIN_BTC_DEPTH:
        _log(f"FAIL: BTC-USDT depth={btc:,.0f} (need >{MIN_BTC_DEPTH:,})")
        print(json.dumps({"status": "FAIL", "reason": "btc_too_low", "btc_depth": btc}))
        return False

    info = _check_coverage(depth)
    pct = info.get("coverage_pct", 0)

    if pct < MIN_COVERAGE_PCT:
        _log(f"FAIL: coverage {info['coverage']} — need ≥{MIN_COVERAGE_PCT}%")
        print(json.dumps({"status": "FAIL", "reason": "low_coverage", **info}))
        return False

    _log(f"OK: {len(depth)} instruments, BTC-USDT={btc:,.0f}, coverage {info['coverage']}")
    print(json.dumps({"status": "OK", "instruments": len(depth), "btc_depth": btc, **info}))
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 -m runner.fetch_depth {save|check|sql}", file=sys.stderr)
        return 1

    cmd = sys.argv[1]

    if cmd == "sql":
        print(get_depth_sql())
        return 0

    if cmd == "check":
        return 0 if check() else 1

    if cmd == "save":
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            _log("ERROR: No input on stdin")
            return 1
        try:
            raw = json.loads(raw_input)
        except json.JSONDecodeError as e:
            _log(f"ERROR: Invalid JSON on stdin: {e}")
            return 1
        result = save_from_mcp_result(raw)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "OK" else 1

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
