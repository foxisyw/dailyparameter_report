#!/usr/bin/env python3
"""Index Price Deviation Monitor Server.

Fetches OKX index prices and their constituent component prices,
calculates quality metrics (deviation, staleness, component count),
and streams via WebSocket + HTTP.

Usage:
    python server.py [--port 8785] [--interval 10]
"""

import asyncio
import json
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

OKX_INDEX_TICKERS_API = "https://www.okx.com/api/v5/market/index-tickers"
OKX_INDEX_COMPONENTS_API = "https://www.okx.com/api/v5/market/index-components"
HEADERS = {"User-Agent": "params-cli/1.0"}
TIMEOUT = 30
COMPONENT_BATCH_CONCURRENCY = 5
COMPONENT_BATCH_SIZE = 40  # fetch components for this many indices per cycle
STALE_THRESHOLD_S = 60  # component considered stale after 60s without update
PID_FILE = Path(__file__).parent / "cache" / ".index_server.pid"
EMA_CACHE_FILE = Path(__file__).parent / "cache" / "ema_state.json"
EMA_TAU = 86400  # 24-hour time constant
EMA_SAVE_INTERVAL = 300  # save EMA to disk every 5 minutes
EMA_INDEX_FIELDS = ["ema_avg_deviation", "ema_max_deviation", "ema_avg_update_lag", "ema_stale_ratio"]
EMA_COMP_FIELDS = ["ema_deviation", "ema_update_lag"]
MARKET_CACHE_MAX_AGE = 86400  # 24h — refresh market cache if older
MARKET_CACHE_INTERVAL = 30  # seconds between refreshing one coin

# ─────────────── State ───────────────

snapshot: dict[str, dict[str, Any]] = {}  # index -> metrics + components
snapshot_ts: float = 0
connected_clients: set = set()
# Track component price history for update frequency estimation
_prev_components: dict[str, dict[str, str]] = {}  # index -> {exchange: last_price}
_component_update_times: dict[str, dict[str, float]] = {}  # index -> {exchange: last_change_ts}

# ─────────────── EMA state ───────────────
# Index-level: index_id -> {ema_field: value}
_ema_index: dict[str, dict[str, float]] = {}
# Component-level: "index_id|exchange:symbol" -> {ema_field: value}
_ema_comp: dict[str, dict[str, float]] = {}
# Timestamps: key -> last_update_ts
_ema_ts: dict[str, float] = {}
_ema_last_save: float = 0


def _load_ema_state():
    """Load persisted EMA state from disk."""
    global _ema_index, _ema_comp, _ema_ts, _ema_last_save
    if EMA_CACHE_FILE.exists():
        try:
            raw = json.loads(EMA_CACHE_FILE.read_text())
            _ema_index = raw.get("ema_index", {})
            _ema_comp = raw.get("ema_comp", {})
            _ema_ts = raw.get("ema_ts", {})
            _ema_last_save = raw.get("saved_at", 0)
            n_comp = len(_ema_comp)
            print(f"  Loaded EMA state: {len(_ema_index)} indices, {n_comp} components", file=sys.stderr)
        except Exception as e:
            print(f"  [warn] failed to load EMA state: {e}", file=sys.stderr)


def _save_ema_state(now: float):
    """Persist EMA state to disk."""
    global _ema_last_save
    EMA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMA_CACHE_FILE.write_text(json.dumps({
        "ema_index": _ema_index,
        "ema_comp": _ema_comp,
        "ema_ts": _ema_ts,
        "saved_at": now,
    }))
    _ema_last_save = now


def _apply_ema(store: dict, key: str, now: float, fields: list[str], values: dict[str, float | None]):
    """Generic EMA update for a keyed store (index or component)."""
    from math import exp

    if key not in store:
        store[key] = {}
        for f in fields:
            v = values.get(f)
            if v is not None:
                store[key][f] = v
        _ema_ts[key] = now
        return

    prev_ts = _ema_ts.get(key, now)
    dt = now - prev_ts
    if dt <= 0:
        dt = 1.0
    alpha = 1.0 - exp(-dt / EMA_TAU)

    for f in fields:
        v = values.get(f)
        if v is None:
            continue
        prev = store[key].get(f)
        if prev is not None:
            store[key][f] = alpha * v + (1 - alpha) * prev
        else:
            store[key][f] = v

    _ema_ts[key] = now


def update_index_ema(index_id: str, now: float, values: dict[str, float | None]):
    """Update index-level EMA."""
    _apply_ema(_ema_index, index_id, now, EMA_INDEX_FIELDS, values)


def update_comp_ema(index_id: str, exchange: str, symbol: str, now: float, values: dict[str, float | None]):
    """Update component-level EMA."""
    key = f"{index_id}|{exchange}:{symbol}"
    _apply_ema(_ema_comp, key, now, EMA_COMP_FIELDS, values)


def get_ema_snapshot() -> dict[str, dict]:
    """Get formatted EMA data for all indices (index-level + component-level)."""
    result = {}
    for index_id, ema in _ema_index.items():
        row = {"index": index_id}
        for field in EMA_INDEX_FIELDS:
            v = ema.get(field)
            row[field] = round(v, 6) if v is not None else None
        if index_id in _ema_ts:
            row["ema_updated"] = _ema_ts[index_id]

        # Attach component EMAs for this index
        comp_emas = []
        prefix = f"{index_id}|"
        for comp_key, comp_ema in _ema_comp.items():
            if not comp_key.startswith(prefix):
                continue
            exch_sym = comp_key[len(prefix):]  # "Binance:BTC/USDT"
            parts = exch_sym.split(":", 1)
            comp_row = {
                "exchange": parts[0] if parts else "",
                "symbol": parts[1] if len(parts) > 1 else "",
            }
            for field in EMA_COMP_FIELDS:
                v = comp_ema.get(field)
                comp_row[field] = round(v, 6) if v is not None else None
            if comp_key in _ema_ts:
                comp_row["ema_updated"] = _ema_ts[comp_key]
            comp_emas.append(comp_row)

        row["components"] = comp_emas
        result[index_id] = row
    return result


# ─────────────── Fetch helpers ───────────────


INDEX_QUOTE_CURRENCIES = ["USDT", "USDC", "USD", "EUR", "TRY", "BRL", "AUD", "AED", "BTC", "ETH", "SGD", "SOL"]


async def fetch_index_tickers(client: httpx.AsyncClient) -> dict[str, dict]:
    """Fetch all index tickers across all quote currencies → {index: {idxPx, ...}}."""
    tickers = {}

    async def _fetch_quote(quote_ccy: str):
        try:
            resp = await client.get(
                OKX_INDEX_TICKERS_API,
                params={"quoteCcy": quote_ccy},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "0":
                print(f"  [warn] index tickers {quote_ccy}: {data.get('msg')}", file=sys.stderr)
                return
            for t in data.get("data", []):
                tickers[t["instId"]] = {
                    "idxPx": t.get("idxPx", ""),
                    "high24h": t.get("high24h", ""),
                    "low24h": t.get("low24h", ""),
                    "open24h": t.get("open24h", ""),
                    "sodUtc0": t.get("sodUtc0", ""),
                    "sodUtc8": t.get("sodUtc8", ""),
                    "ts": t.get("ts", ""),
                }
        except Exception as e:
            print(f"  [warn] index tickers {quote_ccy} failed: {e}", file=sys.stderr)

    await asyncio.gather(*[_fetch_quote(q) for q in INDEX_QUOTE_CURRENCIES])
    return tickers


async def fetch_index_components(
    client: httpx.AsyncClient, index_ids: list[str]
) -> dict[str, dict]:
    """Fetch component data for each index → {index: {last, components: [...]}}."""
    results = {}
    sem = asyncio.Semaphore(COMPONENT_BATCH_CONCURRENCY)

    async def _fetch_one(index_id: str, delay: float):
        await asyncio.sleep(delay)
        async with sem:
            try:
                resp = await client.get(
                    OKX_INDEX_COMPONENTS_API,
                    params={"index": index_id},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == "0" and data.get("data"):
                    d = data["data"]
                    components = d.get("components", [])
                    if components:
                        results[index_id] = {
                            "last": d.get("last", ""),
                            "components": components,
                            "ts": d.get("ts", ""),
                        }
            except httpx.TimeoutException:
                pass
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(2)  # back off on rate limit
                else:
                    print(f"  [warn] components {index_id}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"  [warn] components {index_id}: {e}", file=sys.stderr)

    # Stagger requests with 0.1s delay each to avoid rate limiting
    await asyncio.gather(*[_fetch_one(idx, i * 0.1) for i, idx in enumerate(index_ids)])
    return results


def _safe_float(v) -> float | None:
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


def compute_quality_metrics(
    index_id: str, index_px: float, components: list[dict], now: float
) -> dict:
    """Compute quality metrics for an index from its components."""
    global _prev_components, _component_update_times

    if index_id not in _prev_components:
        _prev_components[index_id] = {}
    if index_id not in _component_update_times:
        _component_update_times[index_id] = {}

    prev = _prev_components[index_id]
    update_times = _component_update_times[index_id]

    deviations = []
    update_lags = []
    stale_count = 0
    component_details = []

    for comp in components:
        exchange = comp.get("exch", "unknown")
        symbol = comp.get("symbol", "")
        sym_px = _safe_float(comp.get("symPx"))
        cnv_px = _safe_float(comp.get("cnvPx"))

        # Use converted price (accounts for USD→USDT conversion) if available
        comp_px = cnv_px or sym_px

        # Deviation from index
        deviation_pct = None
        if comp_px and index_px and index_px > 0:
            deviation_pct = ((comp_px - index_px) / index_px) * 100

        # Track update frequency by detecting price changes
        comp_key = f"{exchange}:{symbol}"
        current_price_str = comp.get("symPx", "")
        if comp_key in prev and prev[comp_key] != current_price_str:
            update_times[comp_key] = now
        elif comp_key not in update_times:
            update_times[comp_key] = now  # first observation
        prev[comp_key] = current_price_str

        # Update lag = seconds since last price change
        last_change = update_times.get(comp_key, now)
        lag = now - last_change

        if lag > STALE_THRESHOLD_S:
            stale_count += 1

        if deviation_pct is not None:
            deviations.append(abs(deviation_pct))
        update_lags.append(lag)

        component_details.append({
            "exchange": exchange,
            "symbol": symbol,
            "symPx": comp.get("symPx", ""),
            "cnvPx": comp.get("cnvPx", ""),
            "comp_px": round(comp_px, 8) if comp_px else None,
            "deviation_pct": round(deviation_pct, 4) if deviation_pct is not None else None,
            "update_lag_s": round(lag, 1),
            "is_stale": lag > STALE_THRESHOLD_S,
            "weight": _safe_float(comp.get("wgt")),
        })

    return {
        "component_count": len(components),
        "avg_deviation_pct": round(sum(deviations) / len(deviations), 4) if deviations else None,
        "max_deviation_pct": round(max(deviations), 4) if deviations else None,
        "avg_update_lag_s": round(sum(update_lags) / len(update_lags), 1) if update_lags else None,
        "stale_components": stale_count,
        "components": component_details,
    }


def build_snapshot(
    tickers: dict[str, dict], comp_data: dict[str, dict], now: float
) -> dict[str, dict]:
    """Merge index tickers + components and compute quality metrics."""
    rows = {}
    for index_id, tk in tickers.items():
        index_px = _safe_float(tk["idxPx"])
        cd = comp_data.get(index_id, {})
        components = cd.get("components", [])

        if index_px and components:
            metrics = compute_quality_metrics(index_id, index_px, components, now)
        else:
            metrics = {
                "component_count": len(components),
                "avg_deviation_pct": None,
                "max_deviation_pct": None,
                "avg_update_lag_s": None,
                "stale_components": 0,
                "components": [],
            }

        rows[index_id] = {
            "index": index_id,
            "idxPx": tk["idxPx"],
            "high24h": tk.get("high24h", ""),
            "low24h": tk.get("low24h", ""),
            "ts": tk.get("ts", ""),
            **{k: v for k, v in metrics.items() if k != "components"},
            "components": metrics["components"],
        }
    return rows


# ─────────────── Polling loop ───────────────


async def poll_loop(interval: float):
    """Periodically fetch data and broadcast to WebSocket clients.

    Components are fetched in rotating batches (COMPONENT_BATCH_SIZE per cycle)
    to avoid overwhelming the OKX API. Accumulated component data persists
    across cycles, so all indices eventually get component data.
    """
    global snapshot, snapshot_ts

    # Persistent component data accumulated across cycles
    all_comp_data: dict[str, dict] = {}
    batch_offset = 0

    # Load real index list from OKX instruments (not all index-tickers)
    from fetcher import get_indexes
    real_indexes = set(get_indexes())
    print(f"  Loaded {len(real_indexes)} real indexes from OKX instruments", file=sys.stderr)

    # Load persisted EMA state
    _load_ema_state()

    async with httpx.AsyncClient(headers=HEADERS) as client:
        while True:
            t0 = time.monotonic()
            now = time.time()
            ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

            # 1) Fetch all index tickers, filtered to real indexes
            tickers = await fetch_index_tickers(client)
            tickers = {k: v for k, v in tickers.items() if k in real_indexes}
            t_tick = time.monotonic()

            # 2) Fetch components for a rotating batch of indices
            index_ids = list(tickers.keys())
            if index_ids:
                batch_start = batch_offset % len(index_ids)
                batch = index_ids[batch_start:batch_start + COMPONENT_BATCH_SIZE]
                # Wrap around if needed
                if len(batch) < COMPONENT_BATCH_SIZE:
                    batch += index_ids[:COMPONENT_BATCH_SIZE - len(batch)]
                batch_offset += COMPONENT_BATCH_SIZE

                new_comp_data = await fetch_index_components(client, batch)
                all_comp_data.update(new_comp_data)
                # Remove stale entries for indices no longer in tickers
                all_comp_data = {k: v for k, v in all_comp_data.items() if k in tickers}
            t_comp = time.monotonic()

            # 3) Build snapshot with quality metrics
            snapshot = build_snapshot(tickers, all_comp_data, now)
            snapshot_ts = now

            # 3b) Update EMA for each index and its components
            for index_id, row in snapshot.items():
                if row.get("component_count", 0) > 0:
                    comp_count = row["component_count"]
                    # Index-level EMA
                    update_index_ema(index_id, now, {
                        "ema_avg_deviation": row.get("avg_deviation_pct"),
                        "ema_max_deviation": row.get("max_deviation_pct"),
                        "ema_avg_update_lag": row.get("avg_update_lag_s"),
                        "ema_stale_ratio": (row.get("stale_components", 0) / comp_count * 100) if comp_count else None,
                    })
                    # Component-level EMA
                    for comp in row.get("components", []):
                        update_comp_ema(index_id, comp.get("exchange", ""), comp.get("symbol", ""), now, {
                            "ema_deviation": abs(comp["deviation_pct"]) if comp.get("deviation_pct") is not None else None,
                            "ema_update_lag": comp.get("update_lag_s"),
                        })

            # Save EMA state periodically
            if now - _ema_last_save >= EMA_SAVE_INTERVAL:
                _save_ema_state(now)

            elapsed = time.monotonic() - t0
            alert_count = sum(
                1 for v in snapshot.values()
                if (v.get("max_deviation_pct") or 0) > 2
                or v.get("stale_components", 0) > 0
            )
            comp_coverage = sum(1 for v in snapshot.values() if v.get("component_count", 0) > 0)
            print(
                f"  [{ts_str}] {len(tickers)} indices ({t_tick - t0:.1f}s) "
                f"+ batch {len(new_comp_data) if index_ids else 0}/{COMPONENT_BATCH_SIZE} "
                f"({t_comp - t_tick:.1f}s) "
                f"coverage={comp_coverage}/{len(tickers)} "
                f"= {elapsed:.1f}s total | {alert_count} alerts | "
                f"{len(connected_clients)} ws clients",
                file=sys.stderr,
            )

            # 4) Broadcast summary (without full component details) to WS clients
            summary = {}
            for k, v in snapshot.items():
                summary[k] = {kk: vv for kk, vv in v.items() if kk != "components"}
            msg = json.dumps({
                "type": "snapshot",
                "ts": snapshot_ts,
                "count": len(snapshot),
                "data": summary,
            })
            if connected_clients:
                await asyncio.gather(
                    *[_ws_send(ws, msg) for ws in connected_clients],
                    return_exceptions=True,
                )

            # 5) Sleep until next interval
            sleep_time = max(0, interval - (time.monotonic() - t0))
            await asyncio.sleep(sleep_time)


async def _ws_send(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        connected_clients.discard(ws)


# ─────────────── WebSocket handler ───────────────


async def ws_handler(websocket):
    """Handle WebSocket connection."""
    connected_clients.add(websocket)
    peer = websocket.remote_address
    print(f"  [ws] client connected: {peer}", file=sys.stderr)

    # Send current snapshot immediately (summary only)
    if snapshot:
        summary = {}
        for k, v in snapshot.items():
            summary[k] = {kk: vv for kk, vv in v.items() if kk != "components"}
        await websocket.send(json.dumps({
            "type": "snapshot",
            "ts": snapshot_ts,
            "count": len(snapshot),
            "data": summary,
        }))

    try:
        async for message in websocket:
            try:
                cmd = json.loads(message)
                if cmd.get("type") == "query":
                    q = cmd.get("filter", "").upper()
                    include_components = cmd.get("components", False)
                    filtered = {}
                    for k, v in snapshot.items():
                        if q and q not in k.upper():
                            continue
                        if include_components:
                            filtered[k] = v
                        else:
                            filtered[k] = {kk: vv for kk, vv in v.items() if kk != "components"}
                    await websocket.send(json.dumps({
                        "type": "query_result",
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


async def http_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Minimal HTTP handler for REST endpoints."""
    request_line = await reader.readline()
    while True:
        line = await reader.readline()
        if line == b"\r\n" or line == b"\n" or not line:
            break

    path = request_line.decode().split(" ")[1] if request_line else "/"

    if path == "/snapshot" or path == "/snapshot/":
        # Summary: all indices without component details
        summary = {}
        for k, v in snapshot.items():
            summary[k] = {kk: vv for kk, vv in v.items() if kk != "components"}
        body = json.dumps({
            "ts": snapshot_ts,
            "count": len(snapshot),
            "data": summary,
        }, indent=2)
        status = "200 OK"

    elif path.startswith("/snapshot/"):
        index_id = path.split("/snapshot/")[1].strip("/")
        if index_id in snapshot:
            body = json.dumps(snapshot[index_id], indent=2)
            status = "200 OK"
        else:
            body = json.dumps({"error": f"index {index_id} not found"})
            status = "404 Not Found"

    elif path.startswith("/search"):
        q = ""
        if "?" in path:
            params = dict(
                p.split("=", 1) for p in path.split("?")[1].split("&") if "=" in p
            )
            q = params.get("q", "").upper()
        filtered = {}
        for k, v in snapshot.items():
            if q and q not in k.upper():
                continue
            filtered[k] = {kk: vv for kk, vv in v.items() if kk != "components"}
        body = json.dumps({
            "filter": q,
            "count": len(filtered),
            "data": filtered,
        }, indent=2)
        status = "200 OK"

    elif path == "/ema" or path == "/ema/":
        ema_data = get_ema_snapshot()
        # Support ?q= filter
        q = ""
        if "?" in path:
            params = dict(
                p.split("=", 1) for p in path.split("?")[1].split("&") if "=" in p
            )
            q = params.get("q", "").upper()
        if q:
            ema_data = {k: v for k, v in ema_data.items() if q in k.upper()}
        body = json.dumps({
            "count": len(ema_data),
            "data": ema_data,
        }, indent=2)
        status = "200 OK"

    elif path.startswith("/ema/"):
        index_id = path.split("/ema/")[1].strip("/").split("?")[0]
        ema_data = get_ema_snapshot()
        if index_id in ema_data:
            body = json.dumps(ema_data[index_id], indent=2)
            status = "200 OK"
        else:
            body = json.dumps({"error": f"no EMA data for {index_id}"})
            status = "404 Not Found"

    elif path.startswith("/alerts"):
        threshold = 2.0  # default 2%
        if "?" in path:
            params = dict(
                p.split("=", 1) for p in path.split("?")[1].split("&") if "=" in p
            )
            try:
                threshold = float(params.get("threshold", "2"))
            except ValueError:
                pass
        alerts = {}
        for k, v in snapshot.items():
            max_dev = v.get("max_deviation_pct") or 0
            stale = v.get("stale_components", 0)
            if abs(max_dev) > threshold or stale > 0:
                alerts[k] = v  # include components for alerts
        body = json.dumps({
            "threshold_pct": threshold,
            "count": len(alerts),
            "data": alerts,
        }, indent=2)
        status = "200 OK"

    elif path == "/" or path == "/health":
        body = json.dumps({
            "status": "ok",
            "indices": len(snapshot),
            "ts": snapshot_ts,
            "endpoints": [
                "GET /snapshot - all indices (summary)",
                "GET /snapshot/{index} - single index with component details",
                "GET /ema - EMA of deviation metrics for all indices",
                "GET /ema/{index} - EMA of deviation metrics for one index",
                "GET /ema?q=BTC - filter EMA data by keyword",
                "GET /search?q=BTC - filter indices",
                "GET /alerts - indices with high deviation or stale components",
                "GET /alerts?threshold=1 - custom deviation threshold (%)",
                "GET /health - server status",
                "WS  ws://localhost:<port> - WebSocket stream",
            ],
        }, indent=2)
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
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps({
        "pid": os.getpid(),
        "port": port,
        "http_port": port + 1,
        "started": time.time(),
    }))


def _remove_pid():
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def read_server_status(port: int = 8785) -> dict | None:
    """Check if server is already running. Returns info dict or None."""
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
                "indices": health.get("indices", 0),
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


# ─────────────── Background market cache refresh ───────────────


async def market_cache_loop():
    """Gradually refresh expired {COIN}_markets.json cache files.

    Runs alongside the main poll loop. Each cycle refreshes one coin
    whose cache is older than MARKET_CACHE_MAX_AGE, then sleeps.
    """
    from fetcher import get_indexes, fetch_markets_for_coin, CACHE_DIR

    # Wait for main loop to start first
    await asyncio.sleep(10)

    # Coins that don't need market data (stablecoins/fiat)
    SKIP_COINS = {"USDT", "USDC", "USD", "EUR", "TRY", "BRL", "AUD", "AED", "SGD"}

    while True:
        try:
            indexes = get_indexes()
            coins = sorted(set(
                idx.split("-", 1)[0].upper() for idx in indexes
            ) - SKIP_COINS)

            # Find the coin with the oldest (or missing) cache
            oldest_coin = None
            oldest_ts = float("inf")
            for coin in coins:
                cache_file = CACHE_DIR / f"{coin}_markets.json"
                if not cache_file.exists():
                    oldest_coin = coin
                    break
                try:
                    data = json.loads(cache_file.read_text())
                    ts = data.get("ts", 0)
                except (json.JSONDecodeError, KeyError):
                    ts = 0
                if ts < oldest_ts:
                    oldest_ts = ts
                    oldest_coin = coin

            # Refresh if cache is expired or missing
            if oldest_coin and (time.time() - oldest_ts > MARKET_CACHE_MAX_AGE):
                print(f"  [cache] Refreshing markets for {oldest_coin}...", file=sys.stderr)
                try:
                    await asyncio.to_thread(fetch_markets_for_coin, oldest_coin, True)
                    print(f"  [cache] {oldest_coin} done", file=sys.stderr)
                except Exception as e:
                    print(f"  [cache] {oldest_coin} failed: {e}", file=sys.stderr)
            else:
                # All caches are fresh — check again in 5 minutes
                await asyncio.sleep(300)
                continue

        except Exception as e:
            print(f"  [cache] Error in market cache loop: {e}", file=sys.stderr)

        await asyncio.sleep(MARKET_CACHE_INTERVAL)


# ─────────────── Main ───────────────


@click.command()
@click.option("--port", default=8785, help="WebSocket port (HTTP = port+1)")
@click.option("--interval", default=10.0, help="Polling interval in seconds")
def main(port: int, interval: float):
    """Start the index price deviation monitor server."""
    http_port = port + 1

    print(f"Index Price Deviation Monitor", file=sys.stderr)
    print(f"  WebSocket : ws://localhost:{port}", file=sys.stderr)
    print(f"  HTTP API  : http://localhost:{http_port}", file=sys.stderr)
    print(f"  Interval  : {interval}s", file=sys.stderr)
    print(f"  Stale threshold: {STALE_THRESHOLD_S}s", file=sys.stderr)
    print(f"  Concurrency: {COMPONENT_BATCH_CONCURRENCY} parallel requests", file=sys.stderr)
    print(f"", file=sys.stderr)

    _write_pid(port)

    async def run():
        ws_server = await ws_serve(ws_handler, "0.0.0.0", port)
        http_server = await asyncio.start_server(
            http_handler, "0.0.0.0", http_port
        )

        print(f"  Servers started. Ctrl+C to stop.\n", file=sys.stderr)

        # Start background market cache refresh
        cache_task = asyncio.create_task(market_cache_loop())

        try:
            await poll_loop(interval)
        except asyncio.CancelledError:
            pass
        finally:
            cache_task.cancel()
            _save_ema_state(time.time())
            ws_server.close()
            http_server.close()
            _remove_pid()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n  Shutting down.", file=sys.stderr)
        _remove_pid()


if __name__ == "__main__":
    main()
