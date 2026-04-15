"""Bootstrap EMA caches from OKX API snapshots.

Generates price-limit and index EMA cache files so the pipeline can run
without the local realtime servers. Uses a single API snapshot as initial
EMA values — not smoothed, but catches current anomalies.

Usage:
    python -m runner.bootstrap_ema          # both caches
    python -m runner.bootstrap_ema --only price-limit
    python -m runner.bootstrap_ema --only index
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
_PL_CACHE = _ROOT / "params_cli" / "price_limits" / "cache" / "ema_state.json"
_IX_CACHE = _ROOT / "params_cli" / "index" / "cache" / "ema_state.json"

OKX_BASE = "https://www.okx.com"
HEADERS = {"User-Agent": "params-cli/bootstrap"}
TIMEOUT = 30


def _log(msg: str):
    print(f"  [bootstrap-ema] {msg}", file=sys.stderr)


def _fetch(client: httpx.Client, path: str, params: dict | None = None):
    """Fetch from OKX API. Returns data field (list or dict depending on endpoint)."""
    url = f"{OKX_BASE}{path}"
    resp = client.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != "0":
        _log(f"  API error {path}: {body.get('msg', 'unknown')}")
        return [] if "index-components" not in path else {}
    return body.get("data", [] if "index-components" not in path else {})


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ─── Price-Limit EMA ────────────────────────────────────────────────


def _fetch_price_limit_one(inst_id: str) -> tuple[str, dict]:
    """Fetch buyLmt/sellLmt for a single instrument (thread-safe)."""
    try:
        with httpx.Client() as c:
            resp = c.get(f"{OKX_BASE}/api/v5/public/price-limit",
                         params={"instId": inst_id}, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == "0" and body.get("data"):
                d = body["data"][0]
                return inst_id, {"buyLmt": d.get("buyLmt", ""), "sellLmt": d.get("sellLmt", "")}
    except Exception:
        pass
    return inst_id, {}


def bootstrap_price_limit(client: httpx.Client) -> int:
    """Build price-limit EMA cache from current ticker + price-limit snapshots."""
    from concurrent.futures import ThreadPoolExecutor

    _log("Bootstrapping price-limit EMA...")

    ema_state: dict[str, dict] = {}
    ema_ts: dict[str, float] = {}
    now = time.time()

    # Focus on SWAP (perps have limit buffers) + FUTURES; skip SPOT for speed
    for inst_type in ("SWAP", "FUTURES"):
        tickers_raw = _fetch(client, "/api/v5/market/tickers", {"instType": inst_type})
        tickers = {t["instId"]: t for t in tickers_raw}
        _log(f"  {inst_type}: {len(tickers)} tickers")

        # Concurrent price limit fetch (10 threads)
        inst_ids = list(tickers.keys())
        limits: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = pool.map(_fetch_price_limit_one, inst_ids)
            for iid, lim in results:
                if lim:
                    limits[iid] = lim

        _log(f"  {inst_type}: {len(limits)} price limits fetched")

        for inst_id, tk in tickers.items():
            bid = _safe_float(tk.get("bidPx"))
            ask = _safe_float(tk.get("askPx"))
            idx_px = _safe_float(tk.get("sodUtc0"))  # fallback for index
            vol24h = _safe_float(tk.get("vol24h"))
            vol_ccy = _safe_float(tk.get("volCcy24h"))

            lim = limits.get(inst_id, {})
            buy_lmt = _safe_float(lim.get("buyLmt"))
            sell_lmt = _safe_float(lim.get("sellLmt"))

            # Compute derived values (same formulas as realtime_server.py:582-614)
            spread = None
            if bid and ask and (bid + ask) > 0:
                spread = (ask - bid) / ((bid + ask) / 2)

            basis = None
            if bid and ask and idx_px and idx_px > 0:
                mid = (bid + ask) / 2
                basis = (mid / idx_px) - 1

            limit_up_buf = None
            if buy_lmt and ask and ask > 0:
                limit_up_buf = (buy_lmt / ask) - 1

            limit_dn_buf = None
            if sell_lmt and bid and sell_lmt > 0:
                limit_dn_buf = (bid / sell_lmt) - 1

            ema = {}
            if basis is not None:
                ema["basis"] = basis
            if spread is not None:
                ema["spread"] = spread
            if limit_up_buf is not None:
                ema["limitUp_buffer"] = limit_up_buf
            if limit_dn_buf is not None:
                ema["limitDn_buffer"] = limit_dn_buf
            if vol24h is not None:
                ema["vol24h"] = vol24h
            if vol_ccy is not None:
                ema["volCcy24h"] = vol_ccy

            if ema:
                ema_state[inst_id] = ema
                ema_ts[inst_id] = now

    # Write cache file (same format as realtime_server.py:89-93)
    _PL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _PL_CACHE.write_text(json.dumps({
        "ema_state": ema_state,
        "ema_ts": ema_ts,
        "saved_at": now,
    }))
    _log(f"  Price-limit total: {len(ema_state)} instruments -> {_PL_CACHE}")
    return len(ema_state)


# ─── Index EMA ───────────────────────────────────────────────────────


def bootstrap_index(client: httpx.Client) -> int:
    """Build index EMA cache from current index tickers + components."""
    _log("Bootstrapping index EMA...")

    ema_index: dict[str, dict] = {}
    ema_comp: dict[str, dict] = {}
    ema_ts: dict[str, float] = {}
    now = time.time()

    # Fetch USDT index tickers (most important subset, ~300 indexes)
    # Fetching all 1300+ indexes hits OKX rate limits. USDT covers the
    # main crypto indexes which are the primary review targets.
    tickers: dict[str, float | None] = {}
    for qcy in ("USDT", "USD"):
        raw = _fetch(client, "/api/v5/market/index-tickers", {"quoteCcy": qcy})
        for t in raw:
            tickers[t["instId"]] = _safe_float(t.get("idxPx"))

    idx_list = list(tickers.keys())
    _log(f"  Found {len(idx_list)} USDT/USD index tickers")

    processed = 0
    failed = 0

    for i in range(0, len(idx_list), 2):
        batch = idx_list[i:i + 2]
        for idx_id in batch:
            idx_px = tickers.get(idx_id) or tickers.get(idx_id.upper())
            if not idx_px or idx_px <= 0:
                continue

            try:
                comp_data = None
                for attempt in range(3):
                    try:
                        comp_data = _fetch(client, "/api/v5/market/index-components", {"index": idx_id})
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        raise
                if not comp_data or not isinstance(comp_data, dict):
                    failed += 1
                    continue

                components = comp_data.get("components", [])

                if not components:
                    failed += 1
                    continue

                # Compute deviations
                deviations = []
                for c in components:
                    # OKX uses cnvPx (converted price) or symPx (symbol price)
                    c_px = _safe_float(c.get("cnvPx")) or _safe_float(c.get("symPx"))
                    if c_px is None or c_px <= 0:
                        continue
                    dev = abs(c_px - idx_px) / idx_px
                    deviations.append(dev)

                    # Component-level EMA
                    exchange = c.get("exch", c.get("exchange", ""))
                    symbol = c.get("symbol", "")
                    comp_key = f"{idx_id}|{exchange}:{symbol}"
                    ema_comp[comp_key] = {
                        "ema_deviation": dev,
                        "ema_update_lag": 0,
                    }
                    ema_ts[comp_key] = now

                if deviations:
                    ema_index[idx_id] = {
                        "ema_avg_deviation": sum(deviations) / len(deviations),
                        "ema_max_deviation": max(deviations),
                        "ema_avg_update_lag": 0,
                        "ema_stale_ratio": 0,
                    }
                    ema_ts[idx_id] = now
                    processed += 1

            except Exception as e:
                failed += 1
                if failed <= 3:
                    _log(f"  Warning: {idx_id}: {e}")

        # Rate limit: OKX index-components is rate-limited aggressively
        if i + 2 < len(idx_list):
            time.sleep(1.5)

    # Write cache file (same format as index/server.py:84-89)
    _IX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _IX_CACHE.write_text(json.dumps({
        "ema_index": ema_index,
        "ema_comp": ema_comp,
        "ema_ts": ema_ts,
        "saved_at": now,
    }))
    _log(f"  Index: {processed} indexes, {len(ema_comp)} components -> {_IX_CACHE}")
    if failed:
        _log(f"  ({failed} indexes skipped)")
    return processed


# ─── Main ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Bootstrap EMA caches from OKX API")
    parser.add_argument("--only", choices=["price-limit", "index"],
                        help="Only bootstrap one cache")
    args = parser.parse_args()

    client = httpx.Client()
    try:
        if args.only != "index":
            bootstrap_price_limit(client)
        if args.only != "price-limit":
            bootstrap_index(client)
    finally:
        client.close()

    _log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
