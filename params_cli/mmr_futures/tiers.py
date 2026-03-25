"""Unified position tier fetching and formatting across exchanges."""

import json
import os
from pathlib import Path
from typing import Any

from exchanges import (
    binance_get_leverage_brackets,
    bybit_get_risk_limit,
    okx_fetch_instruments,
    okx_get_position_tiers,
)


# ─────────────── Cache ───────────────

CACHE_DIR = Path(__file__).parent / "cache"


def _cache_key(exchange: str, symbol: str | None, unit: str) -> str:
    """Build a cache filename."""
    if symbol:
        safe_sym = symbol.replace("/", "_")
        return f"{exchange}_{safe_sym}_{unit}.json"
    return f"{exchange}_all_{unit}.json"


def _read_cache(key: str) -> Any | None:
    path = CACHE_DIR / key
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _write_cache(key: str, data: Any) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / key
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def refresh_cache(exchange: str, unit: str = "usd") -> None:
    """Fetch fresh data from exchange and update both all-tiers and per-symbol caches."""
    exchange = exchange.lower()
    # Fetch all tiers (this hits the API)
    all_data = _fetch_all_position_tiers(exchange, unit)
    # Cache the full result
    _write_cache(_cache_key(exchange, None, unit), all_data)
    # Also cache each symbol individually
    for symbol, tiers in all_data.items():
        _write_cache(_cache_key(exchange, symbol, unit), tiers)


# ─────────────── Unit types ───────────────
# "usd"       – notional in USD/USDT
# "coin"      – quantity in base coin (BTC, ETH, ...)
# "contracts" – number of contracts


def _okx_inst_lookup(inst_type: str) -> dict[str, dict[str, Any]]:
    """Build {instId: instrument} lookup for OKX."""
    instruments = okx_fetch_instruments(inst_type)
    return {inst["instId"]: inst for inst in instruments}


def get_position_tiers(
    exchange: str,
    symbol: str,
    unit: str = "usd",
) -> list[dict[str, Any]]:
    """Get position tiers for a specific instrument on an exchange.

    Reads from local cache if available; otherwise fetches from API and caches.

    Args:
        exchange: 'okx', 'binance', or 'bybit'
        symbol: instrument identifier
        unit: 'usd', 'coin', or 'contracts'

    Returns list of dicts with unified fields:
        tier, min_size, max_size, mmr, imr, max_leverage, unit
    """
    exchange = exchange.lower()
    key = _cache_key(exchange, symbol, unit)
    cached = _read_cache(key)
    if cached is not None:
        return cached

    tiers = _fetch_position_tiers(exchange, symbol, unit)
    _write_cache(key, tiers)
    return tiers


def _fetch_position_tiers(
    exchange: str,
    symbol: str,
    unit: str = "usd",
) -> list[dict[str, Any]]:
    """Fetch position tiers directly from exchange API (no cache)."""
    if exchange == "okx":
        return _get_okx_tiers(symbol, unit)
    elif exchange == "binance":
        return _get_binance_tiers(symbol, unit)
    elif exchange == "bybit":
        return _get_bybit_tiers(symbol, unit)
    else:
        raise ValueError(f"Unknown exchange: {exchange}")


def get_all_position_tiers(
    exchange: str,
    unit: str = "usd",
) -> dict[str, list[dict[str, Any]]]:
    """Get position tiers for ALL instruments on an exchange.

    Reads from local cache if available; otherwise fetches from API and caches.

    Returns {symbol: [tiers...]}.
    """
    exchange = exchange.lower()
    key = _cache_key(exchange, None, unit)
    cached = _read_cache(key)
    if cached is not None:
        return cached

    all_data = _fetch_all_position_tiers(exchange, unit)
    _write_cache(key, all_data)
    return all_data


def _fetch_all_position_tiers(
    exchange: str,
    unit: str = "usd",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch all position tiers directly from exchange API (no cache)."""
    if exchange == "okx":
        return _get_all_okx_tiers(unit)
    elif exchange == "binance":
        return _get_all_binance_tiers(unit)
    elif exchange == "bybit":
        return _get_all_bybit_tiers(unit)
    else:
        raise ValueError(f"Unknown exchange: {exchange}")


# ─────────────── OKX ───────────────


def _get_okx_tiers(symbol: str, unit: str) -> list[dict[str, Any]]:
    parts = symbol.split("-")
    inst_type = "SWAP" if parts[-1] == "SWAP" else "FUTURES"
    uly = f"{parts[0]}-{parts[1]}"

    # Fetch instrument info for contract value conversion
    instruments = okx_fetch_instruments(inst_type)
    inst_info = None
    for inst in instruments:
        if inst["instId"] == symbol:
            inst_info = inst
            break
    if not inst_info:
        raise ValueError(f"OKX instrument {symbol} not found")

    ct_val = float(inst_info["ctVal"])
    ct_val_ccy = inst_info["ctValCcy"]  # e.g. "BTC" or "USD"
    ct_type = inst_info["ctType"]  # "linear" or "inverse"

    raw_tiers = okx_get_position_tiers(inst_type, td_mode="cross", uly=uly)
    return [
        _convert_okx_tier(t, ct_val, ct_val_ccy, ct_type, unit) for t in raw_tiers
    ]


def _convert_okx_tier(
    tier: dict, ct_val: float, ct_val_ccy: str, ct_type: str, unit: str
) -> dict[str, Any]:
    contracts_min = float(tier["minSz"])
    contracts_max = float(tier["maxSz"])

    if unit == "contracts":
        min_sz, max_sz = contracts_min, contracts_max
    elif unit == "coin":
        if ct_type == "linear":
            # ctVal is in base coin (e.g. 0.01 BTC)
            min_sz = contracts_min * ct_val
            max_sz = contracts_max * ct_val
        else:
            # inverse: ctVal is in USD, need price context — just return contracts * ctVal
            # For inverse, coin amount depends on price. Return raw USD value.
            min_sz = contracts_min * ct_val
            max_sz = contracts_max * ct_val
    else:  # usd
        if ct_type == "linear":
            # ctVal in base coin — need price for USD, but we approximate:
            # For linear, we just return coin amount (it's USDT-settled, so coin ≈ USDT value)
            # Actually ct_val_ccy tells us: if BTC, multiply by price. But we don't have price.
            # Convention: return coin amount for linear (it IS the USDT notional ÷ price)
            min_sz = contracts_min * ct_val
            max_sz = contracts_max * ct_val
        else:
            # inverse: ctVal is in USD
            min_sz = contracts_min * ct_val
            max_sz = contracts_max * ct_val

    return {
        "tier": int(tier["tier"]),
        "min_size": min_sz,
        "max_size": max_sz,
        "mmr": float(tier["mmr"]),
        "imr": float(tier["imr"]),
        "max_leverage": float(tier["maxLever"]),
        "unit": _okx_unit_label(ct_type, ct_val_ccy, unit),
    }


def _okx_unit_label(ct_type: str, ct_val_ccy: str, unit: str) -> str:
    if unit == "contracts":
        return "contracts"
    if ct_type == "linear":
        return f"{ct_val_ccy}" if unit == "coin" else f"{ct_val_ccy}"
    else:
        return "USD" if unit == "usd" else f"{ct_val_ccy}"


def _get_all_okx_tiers(unit: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for inst_type in ("SWAP", "FUTURES"):
        instruments = okx_fetch_instruments(inst_type)
        # Group by underlying to avoid duplicate tier calls
        seen_uly: dict[str, list[dict]] = {}
        for inst in instruments:
            if inst["state"] != "live":
                continue
            uly = inst["uly"]
            if uly not in seen_uly:
                seen_uly[uly] = []
            seen_uly[uly].append(inst)

        for uly, insts in seen_uly.items():
            raw_tiers = okx_get_position_tiers(inst_type, td_mode="cross", uly=uly)
            for inst in insts:
                ct_val = float(inst["ctVal"])
                ct_val_ccy = inst["ctValCcy"]
                ct_type = inst["ctType"]
                tiers = [
                    _convert_okx_tier(t, ct_val, ct_val_ccy, ct_type, unit)
                    for t in raw_tiers
                ]
                result[inst["instId"]] = tiers

    return result


# ─────────────── Binance ───────────────


def _detect_binance_market(symbol: str) -> str:
    """Detect if symbol is usds-margined or coin-margined."""
    if symbol.endswith("USDT") or symbol.endswith("USDC") or symbol.endswith("BUSD"):
        return "usds"
    return "coin"


def _get_binance_tiers(symbol: str, unit: str) -> list[dict[str, Any]]:
    market = _detect_binance_market(symbol)
    data = binance_get_leverage_brackets(symbol=symbol, market=market)

    if not data:
        raise ValueError(f"No Binance data for {symbol}")

    # Response is a list; find our symbol
    brackets_data = None
    for item in data:
        if item["symbol"] == symbol:
            brackets_data = item
            break
    if not brackets_data:
        raise ValueError(f"Symbol {symbol} not found in Binance response")

    tiers = []
    for b in brackets_data["brackets"]:
        if market == "usds":
            min_sz = float(b["notionalFloor"])
            max_sz = float(b["notionalCap"])
            native_unit = "USDT"
        else:
            min_sz = float(b.get("qtyFloor", b.get("qtylFloor", 0)))
            max_sz = float(b.get("qtyCap", 0))
            native_unit = symbol.split("USD")[0]  # e.g. BTC from BTCUSD_PERP

        tiers.append({
            "tier": int(b["bracket"]),
            "min_size": min_sz,
            "max_size": max_sz,
            "mmr": float(b["maintMarginRatio"]),
            "imr": 1.0 / int(b["initialLeverage"]) if int(b["initialLeverage"]) > 0 else 1.0,
            "max_leverage": int(b["initialLeverage"]),
            "unit": native_unit if unit != "contracts" else "contracts (N/A for Binance)",
        })

    return tiers


def _get_all_binance_tiers(unit: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for market in ("usds", "coin"):
        try:
            data = binance_get_leverage_brackets(symbol=None, market=market)
        except RuntimeError:
            continue  # skip if no API keys

        for item in data:
            sym = item["symbol"]
            native_unit = "USDT" if market == "usds" else sym.split("USD")[0]
            tiers = []
            for b in item["brackets"]:
                if market == "usds":
                    min_sz = float(b["notionalFloor"])
                    max_sz = float(b["notionalCap"])
                else:
                    min_sz = float(b.get("qtyFloor", b.get("qtylFloor", 0)))
                    max_sz = float(b.get("qtyCap", 0))

                tiers.append({
                    "tier": int(b["bracket"]),
                    "min_size": min_sz,
                    "max_size": max_sz,
                    "mmr": float(b["maintMarginRatio"]),
                    "imr": 1.0 / int(b["initialLeverage"]) if int(b["initialLeverage"]) > 0 else 1.0,
                    "max_leverage": int(b["initialLeverage"]),
                    "unit": native_unit if unit != "contracts" else "contracts (N/A)",
                })
            result[sym] = tiers

    return result


# ─────────────── Bybit ───────────────


def _detect_bybit_category(symbol: str) -> str:
    if symbol.endswith("USDT") or symbol.endswith("USDC") or symbol.endswith("PERP"):
        return "linear"
    return "inverse"


def _get_bybit_tiers(symbol: str, unit: str) -> list[dict[str, Any]]:
    category = _detect_bybit_category(symbol)
    raw = bybit_get_risk_limit(category=category, symbol=symbol)

    if not raw:
        raise ValueError(f"No Bybit data for {symbol}")

    # Bybit tiers are cumulative — convert to ranged
    tiers = []
    prev_max = 0.0
    for i, item in enumerate(raw):
        max_sz = float(item["riskLimitValue"])
        native_unit = "USDT" if category == "linear" else symbol.replace("USD", "")

        tiers.append({
            "tier": i + 1,
            "min_size": prev_max,
            "max_size": max_sz,
            "mmr": float(item["maintenanceMargin"]),
            "imr": float(item["initialMargin"]),
            "max_leverage": float(item["maxLeverage"]),
            "unit": native_unit if unit != "contracts" else "contracts (N/A for Bybit)",
        })
        prev_max = max_sz

    return tiers


def _get_all_bybit_tiers(unit: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for category in ("linear", "inverse"):
        raw = bybit_get_risk_limit(category=category)

        # Group by symbol
        by_symbol: dict[str, list[dict]] = {}
        for item in raw:
            sym = item["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(item)

        for sym, items in by_symbol.items():
            native_unit = "USDT" if category == "linear" else sym.replace("USD", "")
            tiers = []
            prev_max = 0.0
            for i, item in enumerate(items):
                max_sz = float(item["riskLimitValue"])
                tiers.append({
                    "tier": i + 1,
                    "min_size": prev_max,
                    "max_size": max_sz,
                    "mmr": float(item["maintenanceMargin"]),
                    "imr": float(item["initialMargin"]),
                    "max_leverage": float(item["maxLeverage"]),
                    "unit": native_unit if unit != "contracts" else "contracts (N/A)",
                })
                prev_max = max_sz
            result[sym] = tiers

    return result
