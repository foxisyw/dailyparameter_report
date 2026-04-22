"""Fetch OKX market data + alert context, merge MCP query results, validate gate.

Populates the `market_data` and `alert_context` sections of
`runner/local/raw_risk_input.json` from OKX public REST endpoints and the
Lark document text. Merges MCP query results for `position_data` and
`user_master_info`. Validates that all flagged assets have real data before
handing off to `build_risk_intel`.

Subcommands:
    fetch     — populate market_data + alert_context (OKX REST, no MCP)
    merge     — stdin envelope (positions/hourly/users/schema) → raw_risk_input
    validate  — abort if raw_risk_input is missing required data
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

_RUNNER_DIR = Path(__file__).resolve().parent
_LOCAL_DIR = _RUNNER_DIR / "local"
_DEFAULT_INPUT = _LOCAL_DIR / "raw_risk_input.json"

OKX_BASE = "https://www.okx.com"
HTTP_TIMEOUT = 10.0
MAX_WORKERS = 6


def _log(msg: str) -> None:
    print(f"  [fetch-risk-data] {msg}", file=sys.stderr)


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        _log(f"ERROR: {path} does not exist")
        sys.exit(1)
    try:
        return json.loads(path.read_text())
    except Exception as e:
        _log(f"ERROR: cannot parse {path}: {e}")
        sys.exit(1)


def _save_raw(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# OKX market fetch
# ---------------------------------------------------------------------------

def _detect_inst_type(inst_id: str) -> str:
    """Infer OKX instType from an instrument identifier."""
    if inst_id.endswith("-SWAP"):
        return "SWAP"
    if re.search(r"_UM-\d{6}$", inst_id) or re.search(r"-\d{6}$", inst_id):
        return "FUTURES"
    return "SPOT"


def _okx_get(client: httpx.Client, path: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        resp = client.get(f"{OKX_BASE}{path}", params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        return {"_error": str(e)}
    if body.get("code") not in ("0", 0):
        return {"_error": f"OKX code={body.get('code')} msg={body.get('msg')}"}
    data = body.get("data") or []
    return data[0] if data else {}


def _fetch_market_one(inst_id: str) -> tuple[str, dict[str, Any] | None]:
    inst_type = _detect_inst_type(inst_id)
    with httpx.Client() as client:
        ticker = _okx_get(client, "/api/v5/market/ticker", {"instId": inst_id})
        if "_error" in ticker or not ticker:
            _log(f"{inst_id}: ticker failed ({ticker.get('_error', 'empty data')})")
            return inst_id, None

        entry: dict[str, Any] = {
            "price": str(ticker.get("last", "")),
            "open24h": str(ticker.get("open24h", "")),
            "volCcy24h": str(ticker.get("volCcy24h", "")),
            "vol24h": str(ticker.get("vol24h", "")),
            "instType": inst_type,
        }

        if inst_type in ("SWAP", "FUTURES"):
            oi = _okx_get(
                client, "/api/v5/public/open-interest",
                {"instType": inst_type, "instId": inst_id},
            )
            if "_error" not in oi and oi:
                entry["oi"] = str(oi.get("oi", ""))
                entry["oiUsd"] = str(oi.get("oiUsd", ""))
            else:
                _log(f"{inst_id}: open-interest failed ({oi.get('_error', 'empty')})")

        if inst_type == "SWAP":
            funding = _okx_get(
                client, "/api/v5/public/funding-rate", {"instId": inst_id},
            )
            if "_error" not in funding and funding:
                entry["fundingRate"] = str(funding.get("fundingRate", ""))
            else:
                _log(f"{inst_id}: funding-rate failed ({funding.get('_error', 'empty')})")

    return inst_id, entry


def _fetch_all_markets(inst_ids: list[str]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for inst_id, entry in ex.map(_fetch_market_one, inst_ids):
            if entry is not None:
                results[inst_id] = entry
    return results


# ---------------------------------------------------------------------------
# Alert context parser
# ---------------------------------------------------------------------------

_SECTION_MARKERS = [
    ("1️⃣", "Index Alarm"),
    ("2️⃣", "Price Limit"),
    ("3️⃣", "Collateral Coin"),
    ("4️⃣", "Platform OI"),
]

_SEVERITY_EMOJI = {"🔴": "critical", "🟠": "warning"}

_DEVIATION_RE = re.compile(r"偏离\s*([+-]?\d+(?:\.\d+)?%)")
_LIMIT_RATIO_RE = re.compile(r"(\d+(?:\.\d+)?%)\s*[（(]?阈值")
_ASSET_VALUE_RE = re.compile(r"([A-Z0-9]{2,})\s*(?:偏离\s*)?([+-]?\d+(?:\.\d+)?%)")


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Return list of (alert_type, section_text) pairs."""
    sections: list[tuple[str, str]] = []
    remaining = content
    for marker, label in _SECTION_MARKERS:
        idx = remaining.find(marker)
        if idx < 0:
            continue
        next_start = len(remaining)
        for m2, _ in _SECTION_MARKERS:
            if m2 == marker:
                continue
            j = remaining.find(m2, idx + len(marker))
            if 0 <= j < next_start:
                next_start = j
        sections.append((label, remaining[idx:next_start]))
    return sections


def _asset_keys_for_match(flagged_assets: list[str]) -> dict[str, str]:
    """Build a lookup from matchable-token to full flagged_asset key.

    `RAVE-USDT-SWAP` -> keys: {"RAVE-USDT-SWAP": "RAVE-USDT-SWAP",
                               "RAVE-USDT": "RAVE-USDT-SWAP",
                               "RAVE": "RAVE-USDT-SWAP"}
    """
    keys: dict[str, str] = {}
    for asset in flagged_assets:
        keys[asset] = asset
        stripped = re.sub(r"-SWAP$", "", asset)
        if stripped != asset:
            keys[stripped] = asset
        base = stripped.split("-")[0]
        if base and base not in keys:
            keys[base] = asset
    return keys


def _parse_alert_context(
    content: str, flagged_assets: list[str]
) -> dict[str, dict[str, Any]]:
    key_lookup = _asset_keys_for_match(flagged_assets)
    results: dict[str, dict[str, Any]] = {}

    for alert_type, section in _split_sections(content):
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_sev: str | None = None
            for emoji, sev in _SEVERITY_EMOJI.items():
                if emoji in line:
                    line_sev = sev
                    break
            if line_sev is None:
                continue

            fragments = re.split(r"[，,；;]\s*", line)
            for frag in fragments:
                limit_m = _LIMIT_RATIO_RE.search(frag)
                limit_ratio = limit_m.group(1) if limit_m else None

                for match in _ASSET_VALUE_RE.finditer(frag):
                    token, pct = match.group(1), match.group(2)
                    asset = key_lookup.get(token)
                    if not asset or asset in results:
                        continue
                    entry: dict[str, Any] = {
                        "severity": line_sev,
                        "alert_type": alert_type,
                        "oi_deviation_24h": pct,
                        "source_section": alert_type,
                    }
                    if limit_ratio:
                        entry["oi_limit_ratio"] = limit_ratio
                    results[asset] = entry

                if not _ASSET_VALUE_RE.search(frag):
                    for token, asset in key_lookup.items():
                        if asset in results:
                            continue
                        if re.search(rf"\b{re.escape(token)}\b", frag):
                            entry = {
                                "severity": line_sev,
                                "alert_type": alert_type,
                                "source_section": alert_type,
                            }
                            dev_m = _DEVIATION_RE.search(frag)
                            if dev_m:
                                entry["oi_deviation_24h"] = dev_m.group(1)
                            if limit_ratio:
                                entry["oi_limit_ratio"] = limit_ratio
                            results[asset] = entry

    for asset in flagged_assets:
        if asset not in results:
            _log(f"WARN: no alert line matched for {asset}; using default warning")
            results[asset] = {
                "severity": "warning",
                "alert_type": "unknown",
                "source_section": "unknown",
            }
    return results


# ---------------------------------------------------------------------------
# Merge (stdin MCP envelope)
# ---------------------------------------------------------------------------

def _normalize_holder(row: dict[str, Any], direction_col: str) -> dict[str, Any]:
    """Map the MCP row into the builder's expected holder shape.

    Warehouse schema: `direction` (1=either/one-way mode, 2=long, 3=short).
    In one-way mode the long/short side is determined by the sign of
    position_qty (positive=long, negative=short). The builder reads
    `position_type` where 1=long, 2=short.
    """
    normalized = dict(row)
    if direction_col == "direction":
        d = str(row.get("direction", ""))
        if d == "2":
            normalized["position_type"] = "1"
        elif d == "3":
            normalized["position_type"] = "2"
        else:
            try:
                qty = float(row.get("position_qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            normalized["position_type"] = "2" if qty < 0 else "1"
    normalized.setdefault("margin_mode", row.get("margin_mode", ""))
    return normalized


def _merge_envelope(raw: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    direction_col = (envelope.get("schema") or {}).get("direction_column", "position_type")
    positions = envelope.get("positions") or []
    hourly_rows = envelope.get("hourly") or []
    users = envelope.get("users") or []

    position_data: dict[str, dict[str, list]] = {}
    sub_to_master: dict[str, str] = {}
    for row in positions:
        inst = row.get("instrument_name") or row.get("instId") or ""
        if not inst:
            continue
        position_data.setdefault(inst, {"holders": [], "hourly": []})
        position_data[inst]["holders"].append(_normalize_holder(row, direction_col))
        sub = str(row.get("user_id") or "")
        master = str(row.get("master_user_id") or "")
        if sub and master:
            sub_to_master[sub] = master

    for row in hourly_rows:
        inst = row.get("instrument_name") or ""
        if not inst:
            continue
        position_data.setdefault(inst, {"holders": [], "hourly": []})
        position_data[inst]["hourly"].append(row)

    users_by_master: dict[str, dict[str, Any]] = {}
    for row in users:
        mid = str(row.get("master_user_id") or row.get("user_id") or "")
        if mid:
            users_by_master[mid] = row

    user_master: dict[str, dict[str, Any]] = dict(users_by_master)
    for sub, master in sub_to_master.items():
        if master in users_by_master and sub not in user_master:
            user_master[sub] = users_by_master[master]

    raw["position_data"] = position_data
    raw["user_master_info"] = user_master
    return raw


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    flagged = raw.get("flagged_assets") or []
    market_data = raw.get("market_data") or {}
    alert_context = raw.get("alert_context") or {}
    position_data = raw.get("position_data") or {}
    user_master = raw.get("user_master_info") or {}

    if not flagged:
        errors.append("flagged_assets is empty")
        return errors

    for asset in flagged:
        if asset not in market_data:
            errors.append(f"{asset}: missing market_data")
        if asset not in alert_context:
            errors.append(f"{asset}: missing alert_context")

    any_holders = False
    for asset in flagged:
        ctx = alert_context.get(asset, {})
        if ctx.get("severity") == "critical":
            holders = (position_data.get(asset) or {}).get("holders") or []
            if not holders:
                errors.append(f"{asset}: critical alert but no position holders")
            else:
                any_holders = True
        else:
            holders = (position_data.get(asset) or {}).get("holders") or []
            if holders:
                any_holders = True

    if any_holders and not user_master:
        errors.append("position holders present but user_master_info is empty")

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_fetch(input_path: Path) -> int:
    raw = _load_raw(input_path)
    flagged = raw.get("flagged_assets") or []
    if not flagged:
        _log("ERROR: flagged_assets is empty; nothing to fetch")
        return 1

    _log(f"Fetching market data for {len(flagged)} assets...")
    market_data = _fetch_all_markets(flagged)
    raw["market_data"] = market_data

    content = (raw.get("lark_document") or {}).get("content", "")
    if content:
        _log("Parsing alert_context from Lark document content...")
        raw["alert_context"] = _parse_alert_context(content, flagged)
    else:
        _log("WARN: no lark_document.content; alert_context left empty")
        raw.setdefault("alert_context", {})

    _save_raw(input_path, raw)
    _log(
        f"OK: market_data={len(market_data)}/{len(flagged)}, "
        f"alert_context={len(raw.get('alert_context') or {})}"
    )
    return 0 if len(market_data) == len(flagged) else 1


def cmd_merge(input_path: Path) -> int:
    stdin_text = sys.stdin.read().strip()
    if not stdin_text:
        _log("ERROR: no envelope on stdin")
        return 1
    try:
        envelope = json.loads(stdin_text)
    except json.JSONDecodeError as e:
        _log(f"ERROR: invalid JSON on stdin: {e}")
        return 1

    raw = _load_raw(input_path)
    raw = _merge_envelope(raw, envelope)
    _save_raw(input_path, raw)

    pos_count = sum(len(v.get("holders") or []) for v in (raw.get("position_data") or {}).values())
    _log(
        f"OK: positions={pos_count}, "
        f"instruments={len(raw.get('position_data') or {})}, "
        f"users={len(raw.get('user_master_info') or {})}"
    )
    return 0


def cmd_validate(input_path: Path) -> int:
    raw = _load_raw(input_path)
    errors = _validate(raw)
    if errors:
        _log("FATAL: validation failed")
        for err in errors:
            _log(f"  !! {err}")
        return 1
    flagged = raw.get("flagged_assets") or []
    _log(f"OK: {len(flagged)} flagged asset(s) have complete data")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch + merge + validate risk intel raw input")
    parser.add_argument("command", choices=["fetch", "merge", "validate"])
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    args = parser.parse_args()

    if args.command == "fetch":
        return cmd_fetch(args.input)
    if args.command == "merge":
        return cmd_merge(args.input)
    if args.command == "validate":
        return cmd_validate(args.input)
    return 1


if __name__ == "__main__":
    sys.exit(main())
