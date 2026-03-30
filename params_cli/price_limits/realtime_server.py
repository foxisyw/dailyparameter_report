#!/usr/bin/env python3
"""Real-time OKX price-limit monitor server.

Fetches best bid/ask, index price, buyLimit/sellLimit for all live instruments,
calculates spread, basis, limit buffers, and their EMAs (τ=24h).
Streams via WebSocket + HTTP. Persists EMA state to disk every 5 minutes.

Usage:
    python realtime_server.py [--port 8765] [--interval 5] [--types SWAP,SPOT]
"""

import asyncio
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import httpx
import websockets
from websockets.asyncio.server import serve as ws_serve

# ─────────────── Config ───────────────

OKX_TICKERS_API = "https://www.okx.com/api/v5/market/tickers"
OKX_INDEX_TICKERS_API = "https://www.okx.com/api/v5/market/index-tickers"
OKX_PRICE_LIMIT_API = "https://www.okx.com/api/v5/public/price-limit"
BINANCE_SPOT_API = "https://api.binance.com/api/v3/ticker/price"
BINANCE_PERP_API = "https://fapi.binance.com/fapi/v1/ticker/price"
BYBIT_TICKERS_API = "https://api.bybit.com/v5/market/tickers"
HEADERS = {"User-Agent": "params-cli/1.0"}
TIMEOUT = 15
CACHE_DIR = Path(__file__).parent / "cache"
PID_FILE = CACHE_DIR / ".realtime_server.pid"
EMA_CACHE_FILE = CACHE_DIR / "ema_state.json"
PRICE_LIMIT_BATCH_CONCURRENCY = 20
INDEX_QUOTE_CCYS = ["USDT", "USD", "USDC", "BTC"]
KNOWN_QUOTES = ["USDT", "USDC", "BUSD", "BTC", "ETH", "DAI", "TUSD", "USD", "EUR", "TRY", "BRL"]
EMA_TAU = 86400.0  # 24 hours in seconds
EMA_SAVE_INTERVAL = 300  # save EMA cache every 5 minutes
CONFIG_FILE = CACHE_DIR / "config.json"
ALERT_CACHE_FILE = CACHE_DIR / "alert_cache.json"
ALERT_BUFFER_THRESHOLD = 0.02  # 2% — trigger when buffer < this
ALERT_COOLDOWN = 3600  # 1 hour — don't re-alert same instrument within this window

# ─────────────── State ───────────────

snapshot: dict[str, dict[str, Any]] = {}  # instId -> row
snapshot_ts: float = 0
connected_clients: set = set()

# EMA state: {instId: {field: ema_value}} and last update timestamp
ema_state: dict[str, dict[str, float]] = {}
ema_ts: dict[str, float] = {}  # instId -> last EMA update timestamp
_last_ema_save: float = 0

# Alert state: {instId: {reason: last_sent_timestamp}}
_alert_cache: dict[str, dict[str, float]] = {}

EMA_FIELDS = ["basis", "spread", "limitUp_buffer", "limitDn_buffer", "vol24h", "volCcy24h"]


# ─────────────── EMA helpers ───────────────


def _load_ema_cache():
    """Load persisted EMA state from disk."""
    global ema_state, ema_ts
    if EMA_CACHE_FILE.exists():
        try:
            data = json.loads(EMA_CACHE_FILE.read_text())
            ema_state = data.get("ema_state", {})
            ema_ts = data.get("ema_ts", {})
            print(f"  Loaded EMA cache: {len(ema_state)} instruments", file=sys.stderr)
        except Exception as e:
            print(f"  [warn] failed to load EMA cache: {e}", file=sys.stderr)


def _save_ema_cache():
    """Persist EMA state to disk."""
    global _last_ema_save
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        EMA_CACHE_FILE.write_text(json.dumps({
            "ema_state": ema_state,
            "ema_ts": ema_ts,
            "saved_at": time.time(),
        }))
        _last_ema_save = time.time()
    except Exception as e:
        print(f"  [warn] failed to save EMA cache: {e}", file=sys.stderr)


def _maybe_save_ema_cache():
    """Save EMA cache if enough time has passed."""
    if time.time() - _last_ema_save >= EMA_SAVE_INTERVAL:
        _save_ema_cache()


def update_ema(inst_id: str, now: float, values: dict[str, float | None]):
    """Update EMA for one instrument. values = {field_name: current_value}."""
    prev_ts = ema_ts.get(inst_id)
    prev_ema = ema_state.get(inst_id, {})

    new_ema = {}
    for field in EMA_FIELDS:
        x = values.get(field)
        if x is None:
            # keep previous EMA if current value missing
            if field in prev_ema:
                new_ema[field] = prev_ema[field]
            continue
        if field not in prev_ema or prev_ts is None:
            # first observation — seed EMA
            new_ema[field] = x
        else:
            dt = now - prev_ts
            if dt <= 0:
                new_ema[field] = prev_ema[field]
            else:
                alpha = 1.0 - math.exp(-dt / EMA_TAU)
                new_ema[field] = alpha * x + (1.0 - alpha) * prev_ema[field]

    ema_state[inst_id] = new_ema
    ema_ts[inst_id] = now


_VOLUME_FIELDS = {"vol24h", "volCcy24h"}


def get_ema_snapshot() -> dict[str, dict[str, Any]]:
    """Return current EMA values for all instruments."""
    result = {}
    for inst_id, ema in ema_state.items():
        row = {"instId": inst_id}
        for field in EMA_FIELDS:
            v = ema.get(field)
            if field in _VOLUME_FIELDS:
                # Volume fields: no pct conversion
                row[field] = round(v, 4) if v is not None else None
            else:
                if v is not None:
                    row[field] = round(v, 8)
                    row[f"{field}_pct"] = round(v * 100, 4)
                else:
                    row[field] = None
                    row[f"{field}_pct"] = None
        if inst_id in ema_ts:
            row["ema_updated"] = ema_ts[inst_id]
        result[inst_id] = row
    return result


# ─────────────── Config helpers ───────────────


def load_config() -> dict:
    """Load config from disk."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(config: dict):
    """Save config to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


# ─────────────── Lark alert helpers ───────────────


def _load_alert_cache():
    """Load sent-alert cache from disk."""
    global _alert_cache
    if ALERT_CACHE_FILE.exists():
        try:
            _alert_cache = json.loads(ALERT_CACHE_FILE.read_text())
        except Exception:
            _alert_cache = {}


def _save_alert_cache():
    """Persist sent-alert cache to disk."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ALERT_CACHE_FILE.write_text(json.dumps(_alert_cache))
    except Exception as e:
        print(f"  [warn] failed to save alert cache: {e}", file=sys.stderr)


def _should_alert(inst_id: str, reason: str, now: float, cooldown: float = ALERT_COOLDOWN) -> bool:
    """Check if we should send an alert (not sent recently for this reason)."""
    last_sent = _alert_cache.get(inst_id, {}).get(reason, 0)
    return (now - last_sent) >= cooldown


def _mark_alerted(inst_id: str, reason: str, now: float):
    """Record that we sent an alert."""
    _alert_cache.setdefault(inst_id, {})[reason] = now


def _prune_alert_cache(now: float):
    """Remove stale entries older than 2x cooldown."""
    cutoff = now - ALERT_COOLDOWN * 2
    for inst_id in list(_alert_cache):
        reasons = _alert_cache[inst_id]
        for reason in list(reasons):
            if reasons[reason] < cutoff:
                del reasons[reason]
        if not reasons:
            del _alert_cache[inst_id]


async def _send_lark_alert(webhook_url: str, alerts: list[dict]):
    """Send alert message to Lark bot webhook."""
    if not alerts:
        return

    lines = []
    for a in alerts:
        buf_val = a["buffer_pct"]
        lines.append(f"• **{a['instId']}** ({a['instType']}) — {a['reason']}: **{buf_val:.2f}%** (threshold: {ALERT_BUFFER_THRESHOLD * 100:.1f}%)")

    ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = (
        f"**⚠️ Price Limit Buffer Alert**\n"
        f"Time: {ts_str}\n"
        f"Instruments: {len(alerts)}\n\n"
        + "\n".join(lines)
    )

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "Price Limit Buffer Alert"},
                "template": "red",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                print(f"  [alert] sent {len(alerts)} alerts to Lark", file=sys.stderr)
            else:
                print(f"  [alert] Lark webhook returned {resp.status_code}: {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"  [alert] failed to send Lark alert: {e}", file=sys.stderr)


async def check_and_alert(snap: dict[str, dict]):
    """Check snapshot for abnormal buffers and send Lark alerts."""
    config = load_config()
    webhook_url = config.get("lark_webhook_url")
    if not webhook_url:
        return

    threshold = float(config.get("alert_threshold", ALERT_BUFFER_THRESHOLD))
    cooldown = float(config.get("alert_cooldown", ALERT_COOLDOWN))

    now = time.time()
    pending_alerts = []

    for inst_id, row in snap.items():
        limit_up = row.get("limitUp_buffer")
        limit_dn = row.get("limitDn_buffer")

        if limit_up is not None and limit_up < threshold:
            reason = "limitUp_buffer_low"
            if _should_alert(inst_id, reason, now, cooldown):
                pending_alerts.append({
                    "instId": inst_id,
                    "instType": row.get("instType", ""),
                    "reason": "Upper limit buffer low",
                    "buffer_pct": limit_up * 100,
                })
                _mark_alerted(inst_id, reason, now)

        if limit_dn is not None and limit_dn < threshold:
            reason = "limitDn_buffer_low"
            if _should_alert(inst_id, reason, now, cooldown):
                pending_alerts.append({
                    "instId": inst_id,
                    "instType": row.get("instType", ""),
                    "reason": "Lower limit buffer low",
                    "buffer_pct": limit_dn * 100,
                })
                _mark_alerted(inst_id, reason, now)

    if pending_alerts:
        await _send_lark_alert(webhook_url, pending_alerts)
        _save_alert_cache()

    # Prune stale entries periodically
    _prune_alert_cache(now)


# ─────────────── Fetch helpers ───────────────


async def fetch_all_tickers(
    client: httpx.AsyncClient, inst_types: list[str]
) -> dict[str, dict]:
    """Fetch tickers for all inst_types, return {instId: {bidPx, askPx, last}}."""
    tickers = {}

    async def _fetch_type(inst_type: str):
        try:
            resp = await client.get(
                OKX_TICKERS_API,
                params={"instType": inst_type},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                print(f"  [warn] tickers {inst_type}: {data.get('msg')}", file=sys.stderr)
                return
            for t in data.get("data", []):
                tickers[t["instId"]] = {
                    "bidPx": t.get("bidPx", ""),
                    "askPx": t.get("askPx", ""),
                    "last": t.get("last", ""),
                    "vol24h": t.get("vol24h", ""),
                    "volCcy24h": t.get("volCcy24h", ""),
                    "instType": t.get("instType", inst_type),
                }
        except Exception as e:
            print(f"  [warn] tickers {inst_type} failed: {e}", file=sys.stderr)

    await asyncio.gather(*[_fetch_type(t) for t in inst_types])
    return tickers


async def fetch_index_tickers(client: httpx.AsyncClient) -> dict[str, float]:
    """Fetch index prices for all quote currencies.

    Returns {instId: idxPx} where instId is like 'BTC-USDT', 'ETH-USD', etc.
    """
    index_prices = {}

    async def _fetch_qc(qc: str):
        try:
            resp = await client.get(
                OKX_INDEX_TICKERS_API,
                params={"quoteCcy": qc},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                return
            for t in data.get("data", []):
                px = t.get("idxPx", "")
                if px:
                    try:
                        index_prices[t["instId"]] = float(px)
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            print(f"  [warn] index tickers {qc} failed: {e}", file=sys.stderr)

    await asyncio.gather(*[_fetch_qc(qc) for qc in INDEX_QUOTE_CCYS])
    return index_prices


# ─────────────── Cross-exchange normalization ───────────────

import re

_LEADING_MULT_RE = re.compile(r"^(\d+)([A-Z]{2,})$")
_TRAILING_MULT_RE = re.compile(r"^([A-Z]{2,})(\d+)$")


def extract_multiplier(base: str) -> tuple[str, int]:
    """Extract multiplier from base symbol.

    '1000SHIB' → ('SHIB', 1000)
    'SHIB1000' → ('SHIB', 1000)
    'BTC'      → ('BTC', 1)
    '1INCH'    → ('1INCH', 1)  (num < 10 → not a multiplier)
    """
    m = _LEADING_MULT_RE.match(base)
    if m:
        num = int(m.group(1))
        if num >= 10:
            return m.group(2), num
    m = _TRAILING_MULT_RE.match(base)
    if m:
        num = int(m.group(2))
        if num >= 10:
            return m.group(1), num
    return base, 1


def normalize_binance_bybit(symbol: str) -> tuple[str, int]:
    """Normalize Binance/Bybit symbol to (canonical 'BASE-QUOTE', multiplier).

    '1000SHIBUSDT' → ('SHIB-USDT', 1000)
    'BTCUSDT'      → ('BTC-USDT', 1)
    """
    upper = symbol.upper()
    for quote in KNOWN_QUOTES:
        if upper.endswith(quote) and len(upper) > len(quote):
            raw_base = upper[: -len(quote)]
            base, mult = extract_multiplier(raw_base)
            return f"{base}-{quote}", mult
    return upper, 1


def normalize_okx_symbol(inst_id: str) -> tuple[str, int]:
    """Normalize OKX instId to (canonical 'BASE-QUOTE', multiplier).

    'BTC-USDT-SWAP' → ('BTC-USDT', 1)
    'SHIB-USDT'     → ('SHIB-USDT', 1)
    """
    parts = inst_id.split("-")
    if len(parts) >= 2:
        base, mult = extract_multiplier(parts[0])
        return f"{base}-{parts[1]}", mult
    return inst_id, 1


# ─────────────── Cross-exchange fetch helpers ───────────────


async def fetch_binance_tickers(
    client: httpx.AsyncClient,
) -> dict[str, dict[str, float]]:
    """Fetch Binance spot + perp prices. Returns {canonical_symbol: {spot, perp}}."""
    result: dict[str, dict[str, float]] = {}

    async def _fetch_spot():
        try:
            resp = await client.get(BINANCE_SPOT_API, timeout=TIMEOUT)
            resp.raise_for_status()
            for t in resp.json():
                sym, mult = normalize_binance_bybit(t["symbol"])
                px = float(t["price"]) / mult
                result.setdefault(sym, {})["spot"] = px
        except Exception as e:
            print(f"  [warn] binance spot failed: {e}", file=sys.stderr)

    async def _fetch_perp():
        try:
            resp = await client.get(BINANCE_PERP_API, timeout=TIMEOUT)
            resp.raise_for_status()
            for t in resp.json():
                sym, mult = normalize_binance_bybit(t["symbol"])
                px = float(t["price"]) / mult
                result.setdefault(sym, {})["perp"] = px
        except Exception as e:
            print(f"  [warn] binance perp failed: {e}", file=sys.stderr)

    await asyncio.gather(_fetch_spot(), _fetch_perp())
    return result


async def fetch_bybit_tickers(
    client: httpx.AsyncClient,
) -> dict[str, dict[str, float]]:
    """Fetch Bybit spot + linear prices. Returns {canonical_symbol: {spot, perp}}."""
    result: dict[str, dict[str, float]] = {}

    async def _fetch(category: str, field: str):
        try:
            resp = await client.get(
                BYBIT_TICKERS_API,
                params={"category": category},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            for t in data.get("result", {}).get("list", []):
                sym, mult = normalize_binance_bybit(t["symbol"])
                px = float(t["lastPrice"]) / mult
                result.setdefault(sym, {})[field] = px
        except Exception as e:
            print(f"  [warn] bybit {category} failed: {e}", file=sys.stderr)

    await asyncio.gather(_fetch("spot", "spot"), _fetch("linear", "perp"))
    return result


def _inst_id_to_index_key(inst_id: str) -> str:
    """Map instrument ID to its index ticker key.

    BTC-USDT-SWAP -> BTC-USDT
    BTC-USDT      -> BTC-USDT  (spot)
    BTC-USD-250321 -> BTC-USD  (futures)
    """
    parts = inst_id.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return inst_id


async def fetch_price_limits(
    client: httpx.AsyncClient, inst_ids: list[str]
) -> dict[str, dict]:
    """Fetch buyLmt/sellLmt for given instIds with concurrency limit."""
    limits = {}
    sem = asyncio.Semaphore(PRICE_LIMIT_BATCH_CONCURRENCY)

    async def _fetch_one(inst_id: str):
        async with sem:
            try:
                resp = await client.get(
                    OKX_PRICE_LIMIT_API,
                    params={"instId": inst_id},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == "0" and data.get("data"):
                    d = data["data"][0]
                    limits[inst_id] = {
                        "buyLmt": d.get("buyLmt", ""),
                        "sellLmt": d.get("sellLmt", ""),
                    }
            except Exception:
                pass

    await asyncio.gather(*[_fetch_one(iid) for iid in inst_ids])
    return limits


def _safe_float(v: str) -> float | None:
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


def build_snapshot(
    tickers: dict[str, dict],
    limits: dict[str, dict],
    index_prices: dict[str, float],
    binance_prices: dict[str, dict[str, float]] | None = None,
    bybit_prices: dict[str, dict[str, float]] | None = None,
) -> dict[str, dict]:
    """Merge tickers + price limits + index + cross-exchange prices, compute derived fields."""
    rows = {}
    now = time.time()
    bn = binance_prices or {}
    bb = bybit_prices or {}

    for inst_id, tk in tickers.items():
        bid = _safe_float(tk["bidPx"])
        ask = _safe_float(tk["askPx"])
        lim = limits.get(inst_id, {})
        buy_lmt = _safe_float(lim.get("buyLmt", ""))
        sell_lmt = _safe_float(lim.get("sellLmt", ""))

        # Index price lookup
        idx_key = _inst_id_to_index_key(inst_id)
        idx_px = index_prices.get(idx_key)

        # Cross-exchange price lookup (normalized canonical symbol)
        canonical, okx_mult = normalize_okx_symbol(inst_id)
        bn_entry = bn.get(canonical, {})
        bb_entry = bb.get(canonical, {})
        bn_spot = bn_entry.get("spot")
        bn_perp = bn_entry.get("perp")
        bybit_spot = bb_entry.get("spot")
        bybit_perp = bb_entry.get("perp")

        # B/A spread = (ask - bid) / mid
        spread = None
        if bid and ask and (bid + ask) > 0:
            spread = (ask - bid) / ((bid + ask) / 2)

        # basis = (mid / index) - 1
        basis = None
        if bid and ask and idx_px and idx_px > 0:
            mid = (bid + ask) / 2
            basis = (mid / idx_px) - 1

        # limitUp_buffer = (buyLmt / bestAsk) - 1
        limit_up_buf = None
        if buy_lmt and ask and ask > 0:
            limit_up_buf = (buy_lmt / ask) - 1

        # limitDn_buffer = (bidPx / sellLmt) - 1
        limit_dn_buf = None
        if sell_lmt and bid and sell_lmt > 0:
            limit_dn_buf = (bid / sell_lmt) - 1

        # Volume
        vol24h = _safe_float(tk.get("vol24h", ""))
        vol_ccy_24h = _safe_float(tk.get("volCcy24h", ""))

        # Update EMA
        update_ema(inst_id, now, {
            "basis": basis,
            "spread": spread,
            "limitUp_buffer": limit_up_buf,
            "limitDn_buffer": limit_dn_buf,
            "vol24h": vol24h,
            "volCcy24h": vol_ccy_24h,
        })
        ema = ema_state.get(inst_id, {})

        # OKX last price (normalized by multiplier for cross-exchange comparison)
        okx_last = _safe_float(tk["last"])
        okx_last_norm = okx_last / okx_mult if okx_last is not None else None

        rows[inst_id] = {
            "instId": inst_id,
            "instType": tk.get("instType", ""),
            "bidPx": tk["bidPx"],
            "askPx": tk["askPx"],
            "last": tk["last"],
            "idxPx": str(idx_px) if idx_px is not None else "",
            "buyLmt": lim.get("buyLmt", ""),
            "sellLmt": lim.get("sellLmt", ""),
            # Cross-exchange prices (all normalized to same unit)
            "bnSpot": bn_spot,
            "bnPerp": bn_perp,
            "bybitSpot": bybit_spot,
            "bybitPerp": bybit_perp,
            # Cross-exchange spread vs OKX last (%)
            "spreadOkxBn": round((bn_spot - okx_last_norm) / okx_last_norm * 100, 4)
                if bn_spot is not None and okx_last_norm else None,
            "spreadOkxBybit": round((bybit_spot - okx_last_norm) / okx_last_norm * 100, 4)
                if bybit_spot is not None and okx_last_norm else None,
            # Existing derived fields
            "basis": round(basis, 8) if basis is not None else None,
            "basis_pct": round(basis * 100, 4) if basis is not None else None,
            "spread": round(spread, 8) if spread is not None else None,
            "spread_bps": round(spread * 10000, 2) if spread is not None else None,
            "limitUp_buffer": round(limit_up_buf, 6) if limit_up_buf is not None else None,
            "limitUp_buffer_pct": round(limit_up_buf * 100, 4) if limit_up_buf is not None else None,
            "limitDn_buffer": round(limit_dn_buf, 6) if limit_dn_buf is not None else None,
            "limitDn_buffer_pct": round(limit_dn_buf * 100, 4) if limit_dn_buf is not None else None,
            # EMA values
            "basis_ema": round(ema["basis"], 8) if "basis" in ema else None,
            "basis_ema_pct": round(ema["basis"] * 100, 4) if "basis" in ema else None,
            "spread_ema": round(ema["spread"], 8) if "spread" in ema else None,
            "spread_ema_bps": round(ema["spread"] * 10000, 2) if "spread" in ema else None,
            "limitUp_buffer_ema": round(ema["limitUp_buffer"], 6) if "limitUp_buffer" in ema else None,
            "limitUp_buffer_ema_pct": round(ema["limitUp_buffer"] * 100, 4) if "limitUp_buffer" in ema else None,
            "limitDn_buffer_ema": round(ema["limitDn_buffer"], 6) if "limitDn_buffer" in ema else None,
            "limitDn_buffer_ema_pct": round(ema["limitDn_buffer"] * 100, 4) if "limitDn_buffer" in ema else None,
            # 24h volume
            "vol24h": vol24h,
            "volCcy24h": vol_ccy_24h,
            "vol24h_ema": round(ema["vol24h"], 4) if "vol24h" in ema else None,
            "volCcy24h_ema": round(ema["volCcy24h"], 4) if "volCcy24h" in ema else None,
        }
    return rows


# ─────────────── Polling loop ───────────────


async def poll_loop(interval: float, inst_types: list[str]):
    """Periodically fetch data and broadcast to WebSocket clients."""
    global snapshot, snapshot_ts

    async with httpx.AsyncClient(headers=HEADERS) as client:
        while True:
            t0 = time.monotonic()
            ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

            # 1) Fetch OKX tickers + index + Binance + Bybit in parallel
            tickers_task = fetch_all_tickers(client, inst_types)
            index_task = fetch_index_tickers(client)
            bn_task = fetch_binance_tickers(client)
            bb_task = fetch_bybit_tickers(client)
            tickers, index_prices, bn_prices, bb_prices = await asyncio.gather(
                tickers_task, index_task, bn_task, bb_task
            )
            t_tick = time.monotonic()

            # 2) Fetch price limits (parallel, per-instrument)
            inst_ids = list(tickers.keys())
            limits = await fetch_price_limits(client, inst_ids)
            t_lim = time.monotonic()

            # 3) Build snapshot (includes EMA update + cross-exchange prices)
            snapshot = build_snapshot(tickers, limits, index_prices, bn_prices, bb_prices)
            snapshot_ts = time.time()

            # 4) Maybe save EMA cache
            _maybe_save_ema_cache()

            # 4b) Check alerts and send to Lark if configured
            await check_and_alert(snapshot)

            elapsed = time.monotonic() - t0
            print(
                f"  [{ts_str}] {len(tickers)} tickers + {len(index_prices)} idx "
                f"+ {len(bn_prices)} bn + {len(bb_prices)} bb ({t_tick - t0:.1f}s) "
                f"+ {len(limits)} limits ({t_lim - t_tick:.1f}s) "
                f"= {elapsed:.1f}s total | {len(connected_clients)} ws clients",
                file=sys.stderr,
            )

            # 5) Broadcast to WebSocket clients
            msg = json.dumps({
                "type": "snapshot",
                "ts": snapshot_ts,
                "count": len(snapshot),
                "data": snapshot,
            })
            if connected_clients:
                await asyncio.gather(
                    *[_ws_send(ws, msg) for ws in connected_clients],
                    return_exceptions=True,
                )

            # 6) Sleep until next interval
            sleep_time = max(0, interval - (time.monotonic() - t0))
            await asyncio.sleep(sleep_time)


async def _ws_send(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        connected_clients.discard(ws)


# ─────────────── WebSocket handler ───────────────


async def ws_handler(websocket):
    """Handle WebSocket connection: send current snapshot, then stream updates."""
    connected_clients.add(websocket)
    peer = websocket.remote_address
    print(f"  [ws] client connected: {peer}", file=sys.stderr)

    if snapshot:
        await websocket.send(json.dumps({
            "type": "snapshot",
            "ts": snapshot_ts,
            "count": len(snapshot),
            "data": snapshot,
        }))

    try:
        async for message in websocket:
            try:
                cmd = json.loads(message)
                if cmd.get("type") == "query":
                    q = cmd.get("filter", "").upper()
                    filtered = {
                        k: v for k, v in snapshot.items()
                        if q in k.upper()
                    } if q else snapshot
                    await websocket.send(json.dumps({
                        "type": "query_result",
                        "filter": q,
                        "count": len(filtered),
                        "data": filtered,
                    }))
                elif cmd.get("type") == "ema":
                    q = cmd.get("filter", "").upper()
                    ema_snap = get_ema_snapshot()
                    filtered = {
                        k: v for k, v in ema_snap.items()
                        if q in k.upper()
                    } if q else ema_snap
                    await websocket.send(json.dumps({
                        "type": "ema_result",
                        "filter": q,
                        "count": len(filtered),
                        "data": filtered,
                    }))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"  [ws] client disconnected: {peer}", file=sys.stderr)


# ─────────────── HTTP handler ───────────────


def _parse_query_params(path: str) -> dict[str, str]:
    """Parse query string from path."""
    if "?" not in path:
        return {}
    return dict(p.split("=", 1) for p in path.split("?")[1].split("&") if "=" in p)


async def http_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Minimal HTTP handler."""
    request_line = await reader.readline()
    while True:
        line = await reader.readline()
        if line == b"\r\n" or line == b"\n" or not line:
            break

    path = request_line.decode().split(" ")[1] if request_line else "/"
    base_path = path.split("?")[0]

    if base_path == "/snapshot" or base_path == "/snapshot/":
        body = json.dumps({
            "ts": snapshot_ts,
            "count": len(snapshot),
            "data": snapshot,
        })
        status = "200 OK"
    elif base_path.startswith("/snapshot/"):
        inst_id = base_path.split("/snapshot/")[1].strip("/")
        if inst_id in snapshot:
            body = json.dumps(snapshot[inst_id])
            status = "200 OK"
        else:
            body = json.dumps({"error": f"instrument {inst_id} not found"})
            status = "404 Not Found"
    elif base_path == "/ema" or base_path == "/ema/":
        params = _parse_query_params(path)
        q = params.get("q", "").upper()
        ema_snap = get_ema_snapshot()
        filtered = {k: v for k, v in ema_snap.items() if q in k.upper()} if q else ema_snap
        body = json.dumps({
            "ts": time.time(),
            "tau_hours": EMA_TAU / 3600,
            "filter": q or None,
            "count": len(filtered),
            "data": filtered,
        })
        status = "200 OK"
    elif base_path.startswith("/ema/"):
        inst_id = base_path.split("/ema/")[1].strip("/")
        ema_snap = get_ema_snapshot()
        if inst_id in ema_snap:
            body = json.dumps(ema_snap[inst_id])
            status = "200 OK"
        else:
            body = json.dumps({"error": f"no EMA data for {inst_id}"})
            status = "404 Not Found"
    elif base_path.startswith("/search"):
        params = _parse_query_params(path)
        q = params.get("q", "").upper()
        filtered = {k: v for k, v in snapshot.items() if q in k.upper()} if q else snapshot
        body = json.dumps({
            "filter": q,
            "count": len(filtered),
            "data": filtered,
        })
        status = "200 OK"
    elif base_path == "/alerts" or base_path == "/alerts/":
        threshold = 0.02
        alerts = {
            k: v for k, v in snapshot.items()
            if (v.get("limitUp_buffer") is not None and v["limitUp_buffer"] < threshold)
            or (v.get("limitDn_buffer") is not None and v["limitDn_buffer"] < threshold)
        }
        body = json.dumps({
            "threshold_pct": threshold * 100,
            "count": len(alerts),
            "data": alerts,
        })
        status = "200 OK"
    elif base_path == "/" or base_path == "/health":
        body = json.dumps({
            "status": "ok",
            "instruments": len(snapshot),
            "ema_instruments": len(ema_state),
            "ts": snapshot_ts,
            "endpoints": [
                "GET /snapshot - full snapshot",
                "GET /snapshot/{instId} - single instrument",
                "GET /ema - all EMA values",
                "GET /ema/{instId} - single instrument EMA",
                "GET /ema?q=BTC - filter EMA by keyword",
                "GET /search?q=BTC - filter instruments",
                "GET /alerts - instruments near price limits",
                "GET /health - server status",
                "WS  ws://localhost:<port> - WebSocket stream",
            ],
        })
        status = "200 OK"
    else:
        body = json.dumps({"error": "not found"})
        status = "404 Not Found"

    response = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: application/json\r\n"
        f"Access-Control-Allow-Origin: *\r\n"
        f"Content-Length: {len(body.encode())}\r\n"
        f"\r\n"
        f"{body}"
    )
    writer.write(response.encode())
    await writer.drain()
    writer.close()


# ─────────────── PID file helpers ───────────────


def _write_pid(port: int):
    """Write current process info to PID file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps({
        "pid": os.getpid(),
        "port": port,
        "http_port": port + 1,
        "started": time.time(),
    }))


def _remove_pid():
    """Remove PID file on shutdown."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def read_server_status(port: int = 8765) -> dict | None:
    """Check if a server is already running. Returns info dict or None."""
    info = None
    if PID_FILE.exists():
        try:
            info = json.loads(PID_FILE.read_text())
        except Exception:
            pass

    http_port = info["http_port"] if info else port + 1

    try:
        resp = httpx.get(f"http://localhost:{http_port}/health", timeout=3)
        if resp.status_code == 200:
            health = resp.json()
            return {
                "pid": info.get("pid") if info else None,
                "port": info.get("port", port) if info else port,
                "http_port": http_port,
                "started": info.get("started") if info else None,
                "instruments": health.get("instruments", 0),
                "ts": health.get("ts", 0),
            }
    except Exception:
        pass

    if info:
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return info
            except (OSError, ProcessLookupError):
                _remove_pid()
    return None


# ─────────────── Main ───────────────


@click.command()
@click.option("--port", default=8765, help="WebSocket port (HTTP = port+1)")
@click.option("--interval", default=5.0, help="Polling interval in seconds")
@click.option(
    "--types",
    default="SWAP,SPOT,FUTURES",
    help="Comma-separated instrument types to monitor",
)
def main(port: int, interval: float, types: str):
    """Start the real-time OKX price-limit monitor server."""
    inst_types = [t.strip().upper() for t in types.split(",") if t.strip()]
    http_port = port + 1

    print(f"Real-time Price Limit Monitor (OKX + Binance + Bybit)", file=sys.stderr)
    print(f"  WebSocket : ws://localhost:{port}", file=sys.stderr)
    print(f"  HTTP API  : http://localhost:{http_port}", file=sys.stderr)
    print(f"  Interval  : {interval}s", file=sys.stderr)
    print(f"  Types     : {inst_types}", file=sys.stderr)
    print(f"  Exchanges : OKX (primary) + Binance + Bybit", file=sys.stderr)
    print(f"  EMA τ     : {EMA_TAU / 3600}h", file=sys.stderr)
    print(f"", file=sys.stderr)

    _write_pid(port)
    _load_ema_cache()
    _load_alert_cache()

    async def run():
        ws_server = await ws_serve(ws_handler, "0.0.0.0", port)
        http_server = await asyncio.start_server(
            http_handler, "0.0.0.0", http_port
        )

        print(f"  Servers started. Ctrl+C to stop.\n", file=sys.stderr)

        try:
            await poll_loop(interval, inst_types)
        except asyncio.CancelledError:
            pass
        finally:
            _save_ema_cache()
            ws_server.close()
            http_server.close()
            _remove_pid()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n  Saving EMA cache and shutting down.", file=sys.stderr)
        _save_ema_cache()
        _remove_pid()


if __name__ == "__main__":
    main()
