"""Tag OKX instruments by predefined rules."""

import json
import sys
from pathlib import Path
from typing import Any

import httpx

TIMEOUT = 30
CACHE_DIR = Path(__file__).parent / "cache"
RULES_FILE = Path(__file__).parent / "rules.json"
OKX_API = "https://www.okx.com/api/v5/public/instruments"
INST_TYPES = ["SPOT", "SWAP", "FUTURES"]

PRODUCT_TYPE_MAP = {
    "SPOT": "Spot",
    "SWAP": "Perpetual Swap",
    "FUTURES": "Expiry Futures",
}


# ─────────────── Cache helpers ───────────────


def _read_cache(filename: str) -> Any | None:
    path = CACHE_DIR / filename
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _write_cache(filename: str, data: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / filename, "w") as f:
        json.dump(data, f, indent=2)


def _clear_cache() -> None:
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob("*.json"):
        if f.name.startswith("."):
            continue
        f.unlink()


# ─────────────── Instruments ───────────────


def _fetch_instruments_from_api() -> list[dict[str, Any]]:
    """Fetch all instruments from OKX public API."""
    all_instruments = []
    for inst_type in INST_TYPES:
        print(f"  fetching {inst_type} instruments...", file=sys.stderr)
        resp = httpx.get(
            OKX_API,
            params={"instType": inst_type},
            headers={"User-Agent": "params-cli/1.0"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise RuntimeError(f"OKX error for {inst_type}: {data.get('msg')}")
        for r in data["data"]:
            all_instruments.append({
                "instId": r["instId"],
                "instType": r["instType"],
                "productType": PRODUCT_TYPE_MAP.get(r["instType"], r["instType"]),
                "state": r.get("state", ""),
                "baseCcy": r.get("baseCcy", ""),
                "quoteCcy": r.get("quoteCcy", ""),
                "settleCcy": r.get("settleCcy", ""),
                "listTime": r.get("listTime", ""),
                "expTime": r.get("expTime", ""),
                "ctType": r.get("ctType", ""),
            })
    return all_instruments


def get_all_instruments(force: bool = False) -> list[dict[str, Any]]:
    """Get all OKX instruments. Uses cache unless force=True or no cache exists."""
    cache_file = "instruments.json"
    if not force:
        cached = _read_cache(cache_file)
        if cached is not None:
            return cached
    data = _fetch_instruments_from_api()
    _write_cache(cache_file, data)
    return data


# ─────────────── Rules engine ───────────────


def _load_rules() -> list[dict[str, Any]]:
    """Load tagging rules from rules.json."""
    if not RULES_FILE.exists():
        raise FileNotFoundError(f"Rules file not found: {RULES_FILE}")
    with open(RULES_FILE) as f:
        data = json.load(f)
    return data.get("tags", [])


def _eval_condition(inst: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Evaluate a single condition against an instrument."""
    field_val = inst.get(cond["field"], "")
    op = cond["op"]
    expected = cond["value"]

    if op == "eq":
        return field_val == expected
    elif op == "neq":
        return field_val != expected
    elif op == "in":
        return field_val in expected
    elif op == "not_in":
        return field_val not in expected
    elif op == "contains":
        return expected in field_val
    elif op == "not_contains":
        return expected not in field_val
    elif op == "startswith":
        return field_val.startswith(expected)
    elif op == "endswith":
        return field_val.endswith(expected)
    elif op == "regex":
        import re
        return bool(re.search(expected, field_val))
    else:
        return False


def _eval_rule(inst: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Evaluate whether an instrument matches a rule."""
    conditions = rule.get("conditions", [])
    if not conditions:
        return False
    match_mode = rule.get("match", "all")
    if match_mode == "all":
        return all(_eval_condition(inst, c) for c in conditions)
    elif match_mode == "any":
        return any(_eval_condition(inst, c) for c in conditions)
    return False


def tag_instrument(inst: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Apply all matching rules to an instrument, returning it with tags."""
    if rules is None:
        rules = _load_rules()
    tags = []
    for rule in rules:
        if _eval_rule(inst, rule):
            tags.append(rule["name"])
    return {**inst, "tags": tags}


def tag_instruments(instruments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply tagging rules to a list of instruments."""
    rules = _load_rules()
    return [tag_instrument(inst, rules) for inst in instruments]


# ─────────────── Public methods ───────────────


def get_all_tagged() -> list[dict[str, Any]]:
    """Get all instruments with tags applied (from cache)."""
    instruments = get_all_instruments()
    return tag_instruments(instruments)


def get_tagged_by_ids(inst_ids: list[str]) -> list[dict[str, Any]]:
    """Get specified instruments with tags (from cache)."""
    instruments = get_all_instruments()
    id_set = set(inst_ids)
    matched = [inst for inst in instruments if inst["instId"] in id_set]
    return tag_instruments(matched)


def get_tagged_by_tag(tag_name: str) -> list[dict[str, Any]]:
    """Get all instruments that have a specific tag."""
    tagged = get_all_tagged()
    return [inst for inst in tagged if tag_name in inst["tags"]]


def list_rules() -> list[dict[str, str]]:
    """List all available tagging rules with descriptions."""
    rules = _load_rules()
    return [{"name": r["name"], "description": r.get("description", "")} for r in rules]


def refresh_cache() -> dict[str, Any]:
    """Clear cache and re-fetch all instruments from OKX API."""
    _clear_cache()
    print("Refreshing instruments...", file=sys.stderr)
    try:
        instruments = get_all_instruments(force=True)
        return {
            "refreshed": True,
            "instrument_count": len(instruments),
            "types": {t: len([i for i in instruments if i["instType"] == t]) for t in INST_TYPES},
        }
    except Exception as e:
        print(f"  failed: {e}", file=sys.stderr)
        return {"refreshed": False, "error": str(e)}
