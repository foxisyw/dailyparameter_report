#!/usr/bin/env python3
"""CLI to fetch collateral ratio / discount rate tiers from OKX, Binance, and Bybit."""

import argparse
import hmac
import hashlib
import json
import math
import os
import sys
import time
import requests

# ── Cache directory ──────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# ── Binance API credentials ──────────────────────────────────────────────────
BN_API_KEY = "IporE8vZLMzcwokOzn4WMjs4eKSLrrIaEnRtZ7GC3BRJYL7CNAcV9X6Ai0eKktx0"
BN_API_SECRET = "foHGHFSn5JVUgEAixpJXQ78H52r40z4b3IkYgy48GhxtmkeMgG9SimSDtiOBBsSh"


# ══════════════════════════════════════════════════════════════════════════════
#  Fetchers – raw API calls
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_okx_raw():
    """OKX discount-rate tiers (public, no auth).
    Tiers are in **coin terms** (maxAmt = coin quantity)."""
    url = "https://www.okx.com/api/v5/public/discount-rate-interest-free-quota"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]


def _fetch_binance_raw():
    """Binance PM-Pro tiered collateral rate (requires API key + HMAC).
    Tiers are in **USD terms** (tierCap = USD value)."""
    base = "https://api.binance.com"
    endpoint = "/sapi/v2/portfolio/collateralRate"
    params = {"timestamp": int(time.time() * 1000)}
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    sig = hmac.new(BN_API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()
    params["signature"] = sig
    headers = {"X-MBX-APIKEY": BN_API_KEY}
    resp = requests.get(base + endpoint, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fetch_bybit_raw():
    """Bybit tiered collateral ratio (public, no auth).
    Tiers are in **coin terms** (maxQty = coin quantity)."""
    url = "https://api.bybit.com/v5/spot-margin-trade/collateral"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["list"]


# ══════════════════════════════════════════════════════════════════════════════
#  Normalisation helpers
# ══════════════════════════════════════════════════════════════════════════════

def _normalise_okx(raw, terms):
    """Return list of {coin, tiers:[{cap, ratio}]}.
    OKX native caps are coin-denominated."""
    results = []
    for entry in raw:
        coin = entry["ccy"]
        if not entry.get("details"):
            continue
        tiers = []
        for d in entry["details"]:
            cap = d["maxAmt"]              # coin qty (string, "" = unlimited)
            ratio = float(d["discountRate"])
            cap_val = float(cap) if cap != "" else math.inf
            tiers.append({"cap": cap_val, "ratio": ratio})
        results.append({"coin": coin, "tiers": tiers, "native_terms": "coin"})
    return results


def _normalise_binance(raw, terms):
    """Return list of {coin, tiers:[{cap, ratio}]}.
    Binance native caps are USD-denominated."""
    results = []
    for entry in raw:
        coin = entry["asset"]
        info = entry.get("collateralInfo", [])
        if not info:
            continue
        tiers = []
        for d in info:
            cap = d["tierCap"]             # USD (string, "" = unlimited)
            ratio = float(d["collateralRate"])
            cap_val = float(cap) if cap != "" else math.inf
            tiers.append({"cap": cap_val, "ratio": ratio})
        results.append({"coin": coin, "tiers": tiers, "native_terms": "usd"})
    return results


def _normalise_bybit(raw, terms):
    """Return list of {coin, tiers:[{cap, ratio}]}.
    Bybit native caps are coin-denominated."""
    results = []
    for entry in raw:
        coin = entry["currency"]
        ratio_list = entry.get("collateralRatioList", [])
        if not ratio_list:
            continue
        tiers = []
        for d in ratio_list:
            cap = d["maxQty"]              # coin qty (string, "" = unlimited)
            ratio = float(d["collateralRatio"])
            cap_val = float(cap) if cap != "" else math.inf
            tiers.append({"cap": cap_val, "ratio": ratio})
        results.append({"coin": coin, "tiers": tiers, "native_terms": "coin"})
    return results


EXCHANGE_MAP = {
    "okx":     {"fetch": _fetch_okx_raw,     "normalise": _normalise_okx},
    "binance": {"fetch": _fetch_binance_raw,  "normalise": _normalise_binance},
    "bybit":   {"fetch": _fetch_bybit_raw,    "normalise": _normalise_bybit},
}


# ══════════════════════════════════════════════════════════════════════════════
#  Cache helpers
# ══════════════════════════════════════════════════════════════════════════════

def _cache_path(exchange: str) -> str:
    return os.path.join(CACHE_DIR, f"{exchange}.json")


def _read_cache(exchange: str):
    """Return cached raw data for *exchange*, or None if no cache exists."""
    path = _cache_path(exchange)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def _write_cache(exchange: str, data):
    """Write raw API data to the local cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(exchange), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _fetch_raw(exchange: str, force_refresh: bool = False):
    """Return raw data for *exchange*: from cache if available, else fetch & cache.

    If *force_refresh* is True, always fetch from the API and update the cache.
    """
    if not force_refresh:
        cached = _read_cache(exchange)
        if cached is not None:
            return cached
    raw = EXCHANGE_MAP[exchange]["fetch"]()
    _write_cache(exchange, raw)
    return raw


def refresh_cache(exchange: str | None = None):
    """Re-fetch data from the API and update the local cache.

    If *exchange* is None, refresh all exchanges.
    Returns a dict mapping exchange name → True on success.
    """
    exchanges = [exchange] if exchange else list(EXCHANGE_MAP.keys())
    results = {}
    for ex in exchanges:
        _fetch_raw(ex, force_refresh=True)
        results[ex] = True
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  Core methods (the three the user asked for)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_collateral_coins(exchange: str) -> list[str]:
    """Return a sorted list of every collateral-eligible coin on *exchange*."""
    cfg = EXCHANGE_MAP[exchange]
    raw = _fetch_raw(exchange)
    normalised = cfg["normalise"](raw, None)
    return sorted(item["coin"] for item in normalised)


def get_collateral_tiers(exchange: str, coin: str, terms: str = "native") -> dict:
    """Return discount / collateral-rate tiers for *coin* on *exchange*.

    *terms*: "usd" | "coin" | "native" (keep whatever the exchange provides).
    The returned dict looks like:
        {"coin": "BTC", "terms": "usd", "tiers": [{"cap": 500000, "ratio": 1.0}, ...]}
    """
    cfg = EXCHANGE_MAP[exchange]
    raw = _fetch_raw(exchange)
    normalised = cfg["normalise"](raw, terms)

    for item in normalised:
        if item["coin"].upper() == coin.upper():
            cap_label = terms if terms != "native" else item["native_terms"]
            return {
                "coin": item["coin"],
                "terms": cap_label,
                "tiers": _format_tiers(item["tiers"]),
            }
    return None


def get_all_collateral_tiers(exchange: str, terms: str = "native") -> list[dict]:
    """Return tiers for **every** collateral coin on *exchange*.

    *terms*: "usd" | "coin" | "native".
    """
    cfg = EXCHANGE_MAP[exchange]
    raw = _fetch_raw(exchange)
    normalised = cfg["normalise"](raw, terms)

    results = []
    for item in normalised:
        cap_label = terms if terms != "native" else item["native_terms"]
        results.append({
            "coin": item["coin"],
            "terms": cap_label,
            "tiers": _format_tiers(item["tiers"]),
        })
    return sorted(results, key=lambda x: x["coin"])


def _format_tiers(tiers):
    """Replace inf with 'unlimited' for JSON-friendliness."""
    out = []
    for t in tiers:
        cap = t["cap"]
        out.append({
            "cap": cap if cap != math.inf else "unlimited",
            "ratio": t["ratio"],
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def _print_json(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_list(args):
    coins = fetch_all_collateral_coins(args.exchange)
    print(f"Collateral coins on {args.exchange.upper()} ({len(coins)} total):\n")
    for c in coins:
        print(f"  {c}")


def cmd_tiers(args):
    result = get_collateral_tiers(args.exchange, args.coin, args.terms)
    if result is None:
        print(f"Coin '{args.coin}' not found on {args.exchange.upper()}", file=sys.stderr)
        sys.exit(1)
    _print_json(result)


def cmd_all(args):
    results = get_all_collateral_tiers(args.exchange, args.terms)
    _print_json(results)


def cmd_refresh_cache(args):
    exchange = args.exchange if args.exchange != "all" else None
    results = refresh_cache(exchange)
    for ex in results:
        print(f"  ✓ {ex}")
    print(f"\nCache refreshed ({len(results)} exchange(s)).")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch collateral / discount-rate tiers from OKX, Binance, Bybit."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── list ──
    p_list = sub.add_parser("list", help="List all collateral-eligible coins on an exchange")
    p_list.add_argument("exchange", choices=["okx", "binance", "bybit"])
    p_list.set_defaults(func=cmd_list)

    # ── tiers ──
    p_tiers = sub.add_parser("tiers", help="Get discount tiers for a specific coin")
    p_tiers.add_argument("exchange", choices=["okx", "binance", "bybit"])
    p_tiers.add_argument("coin", help="Coin symbol, e.g. BTC, ETH, SOL")
    p_tiers.add_argument(
        "--terms", choices=["usd", "coin", "native"], default="native",
        help="Express tier caps in USD or coin quantity (default: native = whatever the exchange provides)",
    )
    p_tiers.set_defaults(func=cmd_tiers)

    # ── all ──
    p_all = sub.add_parser("all", help="Get tiers for every collateral coin on an exchange")
    p_all.add_argument("exchange", choices=["okx", "binance", "bybit"])
    p_all.add_argument(
        "--terms", choices=["usd", "coin", "native"], default="native",
        help="Express tier caps in USD or coin quantity (default: native)",
    )
    p_all.set_defaults(func=cmd_all)

    # ── refresh-cache ──
    p_refresh = sub.add_parser("refresh-cache", help="Re-fetch data from APIs and update local cache")
    p_refresh.add_argument(
        "exchange", choices=["okx", "binance", "bybit", "all"], default="all", nargs="?",
        help="Exchange to refresh, or 'all' (default: all)",
    )
    p_refresh.set_defaults(func=cmd_refresh_cache)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
