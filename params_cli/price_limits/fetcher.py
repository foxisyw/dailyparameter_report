"""Fetch and cache OKX instruments and XYZ cap parameters."""

import csv
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

TIMEOUT = 30
CACHE_DIR = Path(__file__).parent / "cache"
OKX_API = "https://www.okx.com/api/v5/public/instruments"
OKX_PRODUCTS_API = "https://www.okx.com/priapi/v5/public/products"
INST_TYPES = ["SPOT", "SWAP", "FUTURES"]

PRODUCT_TYPE_MAP = {
    "SPOT": "Spot",
    "SWAP": "Perpetual Swap",
    "FUTURES": "Expiry Futures",
    "MARGIN": "Margin",
    "OPTION": "Option",
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
    """Delete all cached data files (preserves non-data files like .last_call.json)."""
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.glob("*.json"):
        if f.name.startswith("."):
            continue
        f.unlink()


# ─────────────── Instruments ───────────────


def _fetch_instruments_from_api() -> list[dict[str, Any]]:
    """Fetch all instruments from OKX public API (SPOT + SWAP + FUTURES)."""
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


# ─────────────── XYZ Cap Params (from OKX API) ───────────────


_PRODUCTS_BATCH_SIZE = 50  # OKX limit: max 50 instIds per request


def _fetch_xyz_from_api() -> list[dict[str, Any]]:
    """Fetch XYZ cap params for all instruments via OKX priapi products endpoint.

    Uses batched requests (50 instIds per call) to avoid per-instrument overhead.
    """
    instruments = get_all_instruments()
    rows = []

    # Group live instruments by type
    by_type: dict[str, list[str]] = {}
    for inst in instruments:
        if inst["state"] != "live":
            continue
        by_type.setdefault(inst["instType"], []).append(inst["instId"])

    for inst_type, inst_ids in by_type.items():
        n_batches = (len(inst_ids) + _PRODUCTS_BATCH_SIZE - 1) // _PRODUCTS_BATCH_SIZE
        print(
            f"  fetching {inst_type} XYZ params ({len(inst_ids)} instruments, {n_batches} batches)...",
            file=sys.stderr,
        )
        for i in range(0, len(inst_ids), _PRODUCTS_BATCH_SIZE):
            batch = inst_ids[i : i + _PRODUCTS_BATCH_SIZE]
            try:
                resp = httpx.get(
                    OKX_PRODUCTS_API,
                    params={
                        "instType": inst_type,
                        "instId": ",".join(batch),
                        "includeType": "1",
                    },
                    headers={"User-Agent": "params-cli/1.0"},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "0" or not data.get("data"):
                    continue
                for r in data["data"]:
                    lpx1 = r.get("lpX1", "")
                    lpx2 = r.get("lpX2", "")
                    lpy1 = r.get("lpY1", "")
                    lpy2 = r.get("lpY2", "")
                    lpz1 = r.get("lpZ1", "")
                    lpz2 = r.get("lpZ2", "")
                    if not any([lpx1, lpx2, lpy1, lpy2, lpz1, lpz2]):
                        continue
                    rows.append({
                        "instId": r.get("instId", ""),
                        "instType": r.get("instType", inst_type),
                        "upper_X_cap": lpx1,
                        "lower_X_cap": lpx2,
                        "upper_Y_cap": lpy1,
                        "lower_Y_cap": lpy2,
                        "upper_Z_cap": lpz1,
                        "lower_Z_cap": lpz2,
                    })
            except Exception as e:
                print(f"    batch failed: {e}", file=sys.stderr)
                continue
    return rows


def get_xyz_cap_params(force: bool = False) -> list[dict[str, Any]]:
    """Get X/Y/Z cap parameters from cache or live OKX API."""
    cache_file = "xyz_cap_params.json"
    if not force:
        cached = _read_cache(cache_file)
        if cached is not None:
            return cached

    rows = _fetch_xyz_from_api()
    _write_cache(cache_file, rows)
    return rows


def get_xyz_cap_for_instrument(inst_id: str) -> dict[str, Any] | None:
    """Get X/Y/Z cap params for a specific instrument."""
    all_caps = get_xyz_cap_params()
    for r in all_caps:
        if r["instId"] == inst_id:
            return r
    return None


def _fetch_xyz_for_instruments(inst_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch XYZ cap params for specific instruments from OKX API and update cache."""
    # Resolve instType for each instId from the instruments cache
    instruments = get_all_instruments()
    id_to_type = {inst["instId"]: inst["instType"] for inst in instruments}

    # Group by type for batching
    by_type: dict[str, list[str]] = {}
    unknown = []
    for inst_id in inst_ids:
        inst_type = id_to_type.get(inst_id)
        if inst_type:
            by_type.setdefault(inst_type, []).append(inst_id)
        else:
            unknown.append(inst_id)

    if unknown:
        print(f"  warning: unknown instIds (not in instruments cache): {unknown}", file=sys.stderr)

    fetched = []
    for inst_type, ids in by_type.items():
        for i in range(0, len(ids), _PRODUCTS_BATCH_SIZE):
            batch = ids[i : i + _PRODUCTS_BATCH_SIZE]
            try:
                resp = httpx.get(
                    OKX_PRODUCTS_API,
                    params={
                        "instType": inst_type,
                        "instId": ",".join(batch),
                        "includeType": "1",
                    },
                    headers={"User-Agent": "params-cli/1.0"},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "0" or not data.get("data"):
                    continue
                for r in data["data"]:
                    fetched.append({
                        "instId": r.get("instId", ""),
                        "instType": r.get("instType", inst_type),
                        "upper_X_cap": r.get("lpX1", ""),
                        "lower_X_cap": r.get("lpX2", ""),
                        "upper_Y_cap": r.get("lpY1", ""),
                        "lower_Y_cap": r.get("lpY2", ""),
                        "upper_Z_cap": r.get("lpZ1", ""),
                        "lower_Z_cap": r.get("lpZ2", ""),
                    })
            except Exception as e:
                print(f"    batch failed: {e}", file=sys.stderr)
                continue

    # Update cache: merge fetched into existing cache
    cache_file = "xyz_cap_params.json"
    existing = _read_cache(cache_file) or []
    existing_map = {r["instId"]: r for r in existing}
    for r in fetched:
        existing_map[r["instId"]] = r
    merged = list(existing_map.values())
    _write_cache(cache_file, merged)

    return fetched


# ─────────────── Refresh cache ───────────────


def refresh_cache(
    inst_ids: list[str] | None = None,
    inst_type: str | None = None,
) -> dict[str, bool]:
    """Refresh cached data.

    - No args: clear all cache, re-fetch everything.
    - inst_ids: refresh only those specific instruments (fast).
    - inst_type: refresh only instruments of that type.
    """
    result = {}

    if inst_ids:
        # Selective refresh: only specified instruments
        print(f"Refreshing {len(inst_ids)} instrument(s)...", file=sys.stderr)
        try:
            fetched = _fetch_xyz_for_instruments(inst_ids)
            result["xyz_cap_params"] = len(fetched) > 0
            result["refreshed"] = [r["instId"] for r in fetched]
        except Exception as e:
            result["xyz_cap_params"] = False
            print(f"  failed: {e}", file=sys.stderr)
        return result

    if inst_type:
        # Refresh all instruments of a specific type
        print(f"Refreshing {inst_type} instruments...", file=sys.stderr)
        instruments = get_all_instruments()
        ids = [i["instId"] for i in instruments if i["instType"] == inst_type and i["state"] == "live"]
        try:
            fetched = _fetch_xyz_for_instruments(ids)
            result["xyz_cap_params"] = len(fetched) > 0
            result["count"] = len(fetched)
        except Exception as e:
            result["xyz_cap_params"] = False
            print(f"  failed: {e}", file=sys.stderr)
        return result

    # Full refresh
    _clear_cache()

    print("Refreshing instruments...", file=sys.stderr)
    try:
        get_all_instruments(force=True)
        result["instruments"] = True
    except Exception as e:
        result["instruments"] = False
        print(f"  failed: {e}", file=sys.stderr)

    print("Refreshing XYZ cap params...", file=sys.stderr)
    try:
        get_xyz_cap_params(force=True)
        result["xyz_cap_params"] = True
    except Exception as e:
        result["xyz_cap_params"] = False
        print(f"  failed: {e}", file=sys.stderr)

    return result


# ─────────────── Generate adjustment file ───────────────

OUTPUT_DIR = Path(__file__).parent / "output"

# Map from user-friendly JSON keys to internal param names
_PARAM_KEY_MAP = {
    "x_upper": "upper_X_cap",
    "x_lower": "lower_X_cap",
    "y_upper": "upper_Y_cap",
    "y_lower": "lower_Y_cap",
    "z_upper": "upper_Z_cap",
    "z_lower": "lower_Z_cap",
}


def _pct_to_multiplier_upper(pct: str | float) -> str:
    """Convert percentage to upper multiplier: X% -> 1 + X/100."""
    return str(round(1 + float(pct) / 100, 8))


def _pct_to_multiplier_lower(pct: str | float) -> str:
    """Convert percentage to lower multiplier: X% -> 1 - X/100."""
    return str(round(1 - float(pct) / 100, 8))


def _format_task_object(inst_id: str, inst_type: str) -> str:
    """Format instId into the Task Object column value expected by OKX.

    Perp/Futures: BTC-USDT -> BTC-USDT_UM-SWAP, BTC-USD -> BTC-USD_CM-SWAP
    Spot: pass through as-is.
    """
    if inst_type == "SPOT":
        return inst_id
    # For SWAP/FUTURES, the instId is like BTC-USDT-SWAP or BTC-USD-SWAP
    # Task Object format: BTC-USDT_UM-SWAP or BTC-USD_CM-SWAP
    parts = inst_id.rsplit("-", 1)  # ["BTC-USDT", "SWAP"] or ["BTC-USDT", "250321"]
    base = parts[0]  # "BTC-USDT"
    suffix = parts[1] if len(parts) > 1 else ""
    # Determine UM (USDT-margined) vs CM (coin-margined)
    base_parts = base.split("-")
    quote = base_parts[1] if len(base_parts) > 1 else ""
    margin_tag = "UM" if quote in ("USDT", "USDC") else "CM"
    if inst_type == "SWAP":
        return f"{base}_{margin_tag}-SWAP"
    # FUTURES: suffix is the expiry date
    return f"{base}_{margin_tag}-{suffix}"


def generate_adjustment_file(adjustments: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a price limit adjustment CSV file.

    Each adjustment dict should have:
      - symbol: instrument ID (e.g. "BTC-USDT-SWAP")
      - Optional override keys: x_upper, x_lower, y_upper, y_lower, z_upper, z_lower
        (percentage values, e.g. z_upper=30 means 30%)

    For each symbol, fetches current params live from API, then applies overrides.
    Returns dict with file path and details.
    """
    # Collect all symbols and refresh their params from API
    symbols = [adj["symbol"] for adj in adjustments]
    print(f"Refreshing params for {len(symbols)} instrument(s)...", file=sys.stderr)
    _fetch_xyz_for_instruments(symbols)

    # Build rows
    spot_rows = []
    perp_rows = []

    for adj in adjustments:
        symbol = adj["symbol"]
        current = get_xyz_cap_for_instrument(symbol)
        if current is None:
            print(f"  warning: no params found for {symbol}, skipping", file=sys.stderr)
            continue

        inst_type = current["instType"]

        # Merge: start with current values, apply overrides
        params = {
            "upper_X_cap": current["upper_X_cap"],
            "lower_X_cap": current["lower_X_cap"],
            "upper_Y_cap": current["upper_Y_cap"],
            "lower_Y_cap": current["lower_Y_cap"],
            "upper_Z_cap": current["upper_Z_cap"],
            "lower_Z_cap": current["lower_Z_cap"],
        }
        for json_key, param_key in _PARAM_KEY_MAP.items():
            if json_key in adj:
                params[param_key] = str(adj[json_key])

        task_obj = _format_task_object(symbol, inst_type)

        if inst_type == "SPOT":
            spot_rows.append({
                "Task Object": task_obj,
                "timeType": "IMMEDIATE",
                "Effective Time": "",
                "openMaxThresholdRate": _pct_to_multiplier_upper(params["upper_X_cap"]),
                "openMinThresholdRate": _pct_to_multiplier_lower(params["lower_X_cap"]),
                "limitMaxThresholdRate": _pct_to_multiplier_upper(params["upper_Y_cap"]),
                "limitMinThresholdRate": _pct_to_multiplier_lower(params["lower_Y_cap"]),
                "indexMaxThresholdRate": _pct_to_multiplier_upper(params["upper_Z_cap"]),
                "indexMinThresholdRate": _pct_to_multiplier_lower(params["lower_Z_cap"]),
            })
        else:
            perp_rows.append({
                "Task Object": task_obj,
                "timeType": "IMMEDIATE",
                "Effective Time": "",
                "openUpperLimit": _pct_to_multiplier_upper(params["upper_X_cap"]),
                "openLowerLimit": _pct_to_multiplier_lower(params["lower_X_cap"]),
                "afterOpenUpperLimit": _pct_to_multiplier_upper(params["upper_Y_cap"]),
                "afterOpenLowerLimit": _pct_to_multiplier_lower(params["lower_Y_cap"]),
                "afterOpenIndexUpperLimit": _pct_to_multiplier_upper(params["upper_Z_cap"]),
                "afterOpenIndexLowerLimit": _pct_to_multiplier_lower(params["lower_Z_cap"]),
                "preQuoteMaxJ1UpperLimit": "",
                "preQuoteMinJ2LowerLimit": "",
                "preQuoteC1": "",
                "preQuoteC2": "",
            })

    # Write CSV files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    written_files = []

    if spot_rows:
        spot_file = OUTPUT_DIR / f"pricelimit_adjustment_spot_{ts}.csv"
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(spot_rows[0].keys()))
        writer.writeheader()
        writer.writerows(spot_rows)
        spot_file.write_text(buf.getvalue())
        written_files.append({"path": str(spot_file), "type": "spot", "count": len(spot_rows)})

    if perp_rows:
        perp_file = OUTPUT_DIR / f"pricelimit_adjustment_perp_{ts}.csv"
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(perp_rows[0].keys()))
        writer.writeheader()
        writer.writerows(perp_rows)
        perp_file.write_text(buf.getvalue())
        written_files.append({"path": str(perp_file), "type": "perp", "count": len(perp_rows)})

    return {
        "files": written_files,
        "total_instruments": len(spot_rows) + len(perp_rows),
        "skipped": len(adjustments) - len(spot_rows) - len(perp_rows),
    }
