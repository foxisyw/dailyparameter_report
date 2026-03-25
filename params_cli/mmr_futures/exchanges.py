"""Exchange API clients for fetching futures/perp position tiers."""

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from config import BINANCE_API_KEY, BINANCE_API_SECRET

TIMEOUT = 30


# ─────────────────────────── OKX ───────────────────────────


def okx_fetch_instruments(inst_type: str = "SWAP") -> list[dict[str, Any]]:
    """Fetch all OKX instruments for a given type (SWAP or FUTURES).

    Returns list of instrument dicts with fields:
      instId, ctVal, ctValCcy, ctType, settleCcy, uly, lever, state, ...
    """
    url = "https://www.okx.com/api/v5/public/instruments"
    params = {"instType": inst_type}
    resp = httpx.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "0":
        raise RuntimeError(f"OKX error: {data.get('msg')}")
    return data["data"]


def okx_get_position_tiers(
    inst_type: str,
    td_mode: str = "cross",
    uly: str | None = None,
    inst_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch OKX position tiers.

    For cross mode, pass uly (e.g. 'BTC-USDT').
    For isolated mode, pass instId (e.g. 'BTC-USDT-SWAP').
    Tiers have: tier, minSz, maxSz (in contracts), mmr, imr, maxLever.
    """
    url = "https://www.okx.com/api/v5/public/position-tiers"
    params: dict[str, str] = {"instType": inst_type, "tdMode": td_mode}
    if uly:
        params["uly"] = uly
    if inst_id:
        params["instId"] = inst_id
    resp = httpx.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "0":
        raise RuntimeError(f"OKX error: {data.get('msg')}")
    return data["data"]


def _okx_instrument_info(inst_id: str) -> dict[str, Any]:
    """Get a single OKX instrument's info."""
    # Determine instType from the ID pattern
    parts = inst_id.split("-")
    if len(parts) == 2:
        raise ValueError("Provide a futures/swap instId like BTC-USDT-SWAP")
    inst_type = "SWAP" if parts[-1] == "SWAP" else "FUTURES"
    instruments = okx_fetch_instruments(inst_type)
    for inst in instruments:
        if inst["instId"] == inst_id:
            return inst
    raise ValueError(f"Instrument {inst_id} not found")


# ─────────────────────────── Binance ───────────────────────────


def _binance_sign(params: dict[str, Any]) -> dict[str, Any]:
    """Add timestamp and HMAC-SHA256 signature to Binance request params."""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise RuntimeError(
            "Binance API key/secret not set. "
            "Export BINANCE_API_KEY and BINANCE_API_SECRET env vars."
        )
    params["timestamp"] = int(time.time() * 1000)
    query = urlencode(params)
    sig = hmac.new(
        BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256
    ).hexdigest()
    params["signature"] = sig
    return params


def binance_get_leverage_brackets(
    symbol: str | None = None, market: str = "usds"
) -> list[dict[str, Any]]:
    """Fetch Binance leverage brackets (position tiers).

    market: 'usds' for USDT-margined (/fapi), 'coin' for coin-margined (/dapi).
    Returns list of {symbol, brackets: [{bracket, initialLeverage, notionalCap/Floor or qtyCap/Floor, maintMarginRatio, cum}]}.
    """
    if market == "usds":
        base = "https://fapi.binance.com"
        path = "/fapi/v1/leverageBracket"
    else:
        base = "https://dapi.binance.com"
        path = "/dapi/v2/leverageBracket"

    params: dict[str, Any] = {}
    if symbol:
        params["symbol"] = symbol

    params = _binance_sign(params)
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    resp = httpx.get(f"{base}{path}", params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────── Bybit ───────────────────────────


def bybit_get_risk_limit(
    category: str = "linear", symbol: str | None = None
) -> list[dict[str, Any]]:
    """Fetch Bybit risk limit tiers.

    category: 'linear' or 'inverse'.
    Returns list of tier dicts: id, symbol, riskLimitValue, maintenanceMargin,
    initialMargin, maxLeverage, isLowestRisk.

    For linear: riskLimitValue is in USDT.
    For inverse: riskLimitValue is in base coin.
    """
    url = "https://api.bybit.com/v5/market/risk-limit"
    all_results: list[dict[str, Any]] = []
    cursor = ""

    while True:
        params: dict[str, str] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if cursor:
            params["cursor"] = cursor

        resp = httpx.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit error: {data.get('retMsg')}")

        result = data["result"]
        all_results.extend(result.get("list", []))

        cursor = result.get("nextPageCursor", "")
        if not cursor or symbol:
            break

    return all_results
