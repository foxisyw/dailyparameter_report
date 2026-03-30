"""Index CLI data fetching and generation logic.

Handles:
- OKX instrument-based index list derivation
- CoinGecko market/component alternative fetching
- Index component adjustment CSV generation
"""

import csv
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).parent / "cache"
SUPPORTED_EXCHANGES_CSV = Path(__file__).parent / "supported_exchanges.csv"

OKX_INSTRUMENTS_API = "https://www.okx.com/api/v5/public/instruments"
CMC_DATA_API = "https://api.coinmarketcap.com/data-api/v3"
CMC_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
HEADERS = {"User-Agent": "params-cli/1.0"}
HYPERLIQUID_INFO_API = "https://api.hyperliquid.xyz/info"


# ─────────────── Conversion logic ───────────────

CONVERSION_MAP = {
    ("USDT", "USD"): (1, "USDT-USD"),
    ("USDC", "USD"): (1, "USDC-USD"),
    ("BTC", "USD"): (1, "BTC-USD"),
    ("BTC", "USDT"): (1, "BTC-USDT"),
    ("ETH", "USD"): (1, "ETH-USD"),
    ("ETH", "USDT"): (1, "ETH-USDT"),
    ("USDT", "EUR"): (1, "USDT-EUR"),
    ("USD", "EUR"): (1, "USD-EUR"),
    ("USDT", "BTC"): (2, "BTC-USDT"),
    ("USDC", "BTC"): (2, "BTC-USDC"),
    ("USD", "BTC"): (2, "BTC-USD"),
    ("USDT", "USDC"): (1, "USDT-USDC"),
    ("USDC", "USDT"): (1, "USDC-USDT"),
    ("USDT", "TRY"): (1, "USDT-TRY"),
    ("USD", "TRY"): (1, "USD-TRY"),
    ("USDT", "AED"): (1, "USDT-AED"),
    ("USDT", "BRL"): (1, "USDT-BRL"),
    ("USDT", "AUD"): (1, "USDT-AUD"),
    ("USD", "USDT"): (1, "USD-USDT"),
    ("FDUSD", "USDT"): (1, "FDUSD-USDT"),
    ("FDUSD", "USD"): (1, "FDUSD-USD"),
    ("USDe", "USD"): (1, "USDe-USD"),
    ("USDe", "USDT"): (1, "USDe-USDT"),
    ("USDH", "USD"): (1, "USDH-USD"),
    ("USDH", "USDT"): (1, "USDH-USDT"),
    ("USDH", "USDC"): (1, "USDH-USDC"),
    ("USDe", "USDC"): (1, "USDe-USDC"),
}

TEMPLATE_FIELDS = [
    "index", "exchange", "symbol",
    "conversion type(1× 2÷ 0 noConversion)", "conversionIndex",
    "weight", "tier value", "priceMultiple", "emaLagMs",
    "uniqueExchangeAlias", "chainId", "tokenAddress", "poolAddress",
    "baseTokenAddress", "quoteTokenAddress", "subscribeName",
    "sharesMultiplierSource", "sharesMultiplierToken",
    "sharesMultiplierBenchmark", "conversionCheck",
]


# ─────────────── Index list from OKX instruments ───────────────


def fetch_okx_instruments() -> dict:
    """Fetch OKX SPOT + SWAP + FUTURES instruments. Returns {spot: [...], perpetual: [...], futures: [...]}."""
    result = {"spot": [], "perpetual": [], "futures": []}
    for inst_type, key in [("SPOT", "spot"), ("SWAP", "perpetual"), ("FUTURES", "futures")]:
        try:
            resp = httpx.get(
                OKX_INSTRUMENTS_API,
                params={"instType": inst_type},
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == "0":
                result[key] = data.get("data", [])
        except Exception as e:
            print(f"  [warn] instruments {inst_type}: {e}", file=sys.stderr)
    return result


def _inst_to_index(inst_id: str, inst_type: str) -> str:
    """Derive index name from an instrument ID.

    Rules:
      - Spot "BTC-USDT" → "BTC-USDT"
      - Swap "TSLA-USDT-SWAP" → strip "-SWAP" → "TSLA-USDT"
      - Swap "BTC-USD_UM-SWAP" → strip "-SWAP" then "_UM" → "BTC-USD"
      - Futures "BTC-USDT-250328" → strip last segment → "BTC-USDT"
      - Futures "BTC-USD_CM-250328" → strip last segment + "_CM" → "BTC-USD"
    """
    if inst_type == "SPOT":
        return inst_id
    if inst_type == "SWAP":
        index = inst_id.removesuffix("-SWAP")
        if "_" in index:
            index = index[: index.rfind("_")]
        return index
    if inst_type == "FUTURES":
        # e.g. BTC-USDT-250328 -> BTC-USDT, BTC-USD_CM-250328 -> BTC-USD
        parts = inst_id.rsplit("-", 1)
        index = parts[0]
        if "_" in index:
            index = index[: index.rfind("_")]
        return index
    return inst_id


def extract_indexes(data: dict) -> list[str]:
    """Derive unique index names from spot, perpetual, and futures instruments."""
    indexes: set[str] = set()

    for inst in data.get("spot", []):
        inst_id = inst.get("instId", "")
        if inst_id and inst.get("state") == "live":
            indexes.add(_inst_to_index(inst_id, "SPOT"))

    for inst in data.get("perpetual", []):
        inst_id = inst.get("instId", "")
        if inst_id and inst.get("state") == "live":
            indexes.add(_inst_to_index(inst_id, "SWAP"))

    for inst in data.get("futures", []):
        inst_id = inst.get("instId", "")
        if inst_id and inst.get("state") == "live":
            indexes.add(_inst_to_index(inst_id, "FUTURES"))

    return sorted(indexes)


def extract_coins(indexes: list[str]) -> list[str]:
    """Extract unique base coins from index names."""
    coins: set[str] = set()
    for idx in indexes:
        coin = idx.split("-", 1)[0]
        if coin:
            coins.add(coin)
    return sorted(coins)


def get_indexes(force: bool = False) -> list[str]:
    """Get the real OKX index list (cached)."""
    cache_file = CACHE_DIR / "indexes.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:  # 24h cache
                return data["indexes"]
        except (json.JSONDecodeError, KeyError):
            pass

    instruments = fetch_okx_instruments()
    indexes = extract_indexes(instruments)
    cache_file.write_text(json.dumps({
        "ts": time.time(),
        "count": len(indexes),
        "indexes": indexes,
    }))
    return indexes


def get_coins(force: bool = False) -> list[str]:
    """Get unique base coins from index list."""
    return extract_coins(get_indexes(force=force))


# ─────────────── Supported exchanges ───────────────


def load_supported_exchanges() -> dict[str, dict]:
    """Load supported_exchanges.csv → {coingecko_id: {name, score, type}}."""
    mapping: dict[str, dict] = {}
    if not SUPPORTED_EXCHANGES_CSV.exists():
        return mapping
    with open(SUPPORTED_EXCHANGES_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            cg_id = row.get("coingecko_id", "").strip()
            if cg_id:
                mapping[cg_id] = {
                    "name": row["supported_markets"],
                    "score": int(row.get("score", 1)),
                    "type": row.get("type", ""),
                }
    return mapping


def load_exchange_types() -> dict[str, str]:
    """Load exchange name → type mapping from supported_exchanges.csv."""
    types: dict[str, str] = {}
    if not SUPPORTED_EXCHANGES_CSV.exists():
        return types
    with open(SUPPORTED_EXCHANGES_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            types[row["supported_markets"]] = row.get("type", "")
    return types


# CMC exchange name → our canonical base name (case/spelling differences)
_CMC_NAME_MAP: dict[str, str] = {
    "KuCoin": "Kucoin",
    "MEXC": "Mxc",
    "Coinbase Exchange": "Coinbase",
    "BitMart": "Bitmart",
    "Crypto.com Exchange": "Crypto",
    "BtcTurk | Kripto": "BTCTurk",
    "BingX": "BingX",
}

# CMC exchange name → perpetual name suffix mapping
# Maps base canonical names to their _LINEAR_PERPETUAL / _PERPETUAL suffixed forms
_PERP_NAME_MAP: dict[str, str] = {
    "Binance": "Binance_LINEAR_PERPETUAL",
    "OKX": "OKX_PERPETUAL",
    "Bybit": "Bybit_LINEAR_PERPETUAL",
    "Hyperliquid": "Hyperliquid_LINEAR_PERPETUAL",
    "Gate": "Gate_LINEAR_PERPETUAL",
    "Bitget": "Bitget_LINEAR_PERPETUAL",
    "Mxc": "Mxc_LINEAR_PERPETUAL",
    "Kucoin": "Kucoin_LINEAR_PERPETUAL",
}


def map_exchange_name(cmc_name: str, category: str) -> str:
    """Map a CMC exchange name + category to our canonical exchange name.

    First normalizes CMC name to our canonical base name, then:
    Spot/oracle: use canonical base name.
    Perpetual: append _LINEAR_PERPETUAL or _PERPETUAL suffix.
    """
    canonical = _CMC_NAME_MAP.get(cmc_name, cmc_name)
    if category == "perpetual":
        return _PERP_NAME_MAP.get(canonical, f"{canonical}_LINEAR_PERPETUAL")
    return canonical


def format_symbol(pair: str, exchange: str = "") -> str:
    """Normalize pair to standard symbol format.

    Input can be 'BTC-USDT', 'BTC/USDT', 'cash:TSLA-USD', etc.
    Output depends on exchange:
      - OKX_PERPETUAL: 'BTC-USDT-SWAP'
      - Others: 'BTC/USDT'
    """
    # Strip known prefixes like 'cash:', 'xyz:', 'flx:', 'km:'
    if ":" in pair:
        pair = pair.split(":", 1)[1]
    # Normalize to slash first for parsing
    normalized = pair.replace("-", "/") if "/" not in pair else pair
    # OKX perpetuals use instId format: BASE-QUOTE-SWAP
    if exchange == "OKX_PERPETUAL" and "/" in normalized:
        base, quote = normalized.split("/", 1)
        return f"{base}-{quote}-SWAP"
    return normalized


def fetch_hyperliquid_universe() -> dict[str, str]:
    """Fetch Hyperliquid perp universe and return {uppercase_name: raw_name} mapping.

    All Hyperliquid perps are USDC-quoted. Asset names are bare tickers
    (e.g. "BTC", "ETH", "kPEPE"). Cached for 24 hours.
    """
    cache_file = CACHE_DIR / "hyperliquid_universe.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:  # 24h cache
                return data["universe"]
        except (json.JSONDecodeError, KeyError):
            pass

    try:
        resp = httpx.post(
            HYPERLIQUID_INFO_API,
            json={"type": "meta"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        meta = resp.json()
    except Exception as e:
        print(f"  Warning: failed to fetch Hyperliquid universe: {e}", file=sys.stderr)
        return {}

    universe = {}
    for asset in meta.get("universe", []):
        name = asset.get("name", "")
        if name:
            universe[name.upper()] = name

    cache_file.write_text(json.dumps({"ts": time.time(), "universe": universe}))
    return universe


def load_exchange_scores() -> dict[str, int]:
    """Load exchange name → score mapping."""
    scores: dict[str, int] = {}
    if not SUPPORTED_EXCHANGES_CSV.exists():
        return scores
    with open(SUPPORTED_EXCHANGES_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            scores[row["supported_markets"]] = int(row.get("score", 1))
    return scores


# ─────────────── CoinMarketCap market fetching ───────────────


def resolve_cmc_coin(symbol: str) -> dict | None:
    """Quickly resolve a single coin symbol to its CMC slug without building the full map.

    Checks the cached coin map first. If not cached, fetches the raw CMC map
    and picks the best match for this symbol only (no full OKX disambiguation).
    For ambiguous symbols, picks the entry with OKX pairs or best market cap rank.
    """
    # Try cached map first
    cache_file = CACHE_DIR / "cmc_coin_map.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:
                return data["map"].get(symbol.upper())
        except (json.JSONDecodeError, KeyError):
            pass

    # Fetch raw CMC map (single HTTP call, no disambiguation)
    print(f"  Looking up {symbol} on CMC...", file=sys.stderr)
    try:
        resp = httpx.get(
            f"{CMC_DATA_API}/map/all",
            params={"cryptoType": "all", "isActive": 1, "start": 1, "limit": 10000},
            headers=CMC_HEADERS,
            timeout=60,
        )
        resp.raise_for_status()
        coins = resp.json().get("data", {}).get("cryptoCurrencyMap", [])
    except Exception as e:
        print(f"  Warning: CMC map fetch failed: {e}", file=sys.stderr)
        return None

    # Find all entries matching this symbol
    matches = [
        {"slug": c["slug"], "id": c["id"], "name": c.get("name", ""), "rank": c.get("rank")}
        for c in coins if c["symbol"].upper() == symbol.upper()
    ]

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Multiple matches — quick OKX probe for just this symbol
    ranked = sorted(matches, key=lambda e: e["rank"] if e["rank"] is not None else 999999)
    for entry in ranked:
        for category in ("spot", "perpetual"):
            try:
                r = httpx.get(
                    f"{CMC_DATA_API}/cryptocurrency/market-pairs/latest",
                    params={"slug": entry["slug"], "start": 1, "limit": 100,
                            "category": category, "centerType": "all"},
                    headers=CMC_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    pairs = r.json().get("data", {}).get("marketPairs", [])
                    if any(p.get("exchangeName") == "OKX" for p in pairs):
                        print(f"  {symbol} → {entry['name']} (OKX {category})", file=sys.stderr)
                        return entry
            except Exception:
                pass
            time.sleep(0.2)

    # No OKX match — use best-ranked
    return ranked[0]


def fetch_cmc_coin_map() -> dict[str, dict]:
    """Fetch CMC full coin map → {SYMBOL: {slug, id, name}}. Cached 24h.

    Uses the map/all endpoint which includes ALL coins (including unranked
    commodities, derivatives, etc.) — not just market-cap-ranked ones.

    For duplicate symbols, resolves by checking which CMC coin has market
    pairs on OKX. Falls back to highest market cap rank.
    """
    cache_file = CACHE_DIR / "cmc_coin_map.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:
                return data["map"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("  Fetching CMC coin map...", file=sys.stderr)
    resp = httpx.get(
        f"{CMC_DATA_API}/map/all",
        params={"cryptoType": "all", "isActive": 1, "start": 1, "limit": 10000},
        headers=CMC_HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    coins = resp.json().get("data", {}).get("cryptoCurrencyMap", [])

    # Group all entries by symbol
    from collections import defaultdict
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for c in coins:
        sym = c["symbol"].upper()
        by_symbol[sym].append({
            "slug": c["slug"],
            "id": c["id"],
            "name": c.get("name", ""),
            "rank": c.get("rank"),
        })

    # For symbols with only one entry, use it directly
    # For duplicates, resolve using OKX exchange presence
    symbol_map: dict[str, dict] = {}
    duplicates: dict[str, list[dict]] = {}

    for sym, entries in by_symbol.items():
        if len(entries) == 1:
            symbol_map[sym] = entries[0]
        else:
            duplicates[sym] = entries

    # Resolve duplicates: for each symbol, sort candidates by market cap rank
    # (best first), probe CMC market-pairs to find the one with OKX pairs.
    # If none has OKX pairs, exclude the symbol entirely.
    if duplicates:
        # Only probe OKX-traded symbols; skip the rest
        okx_coins = set()
        try:
            indexes = get_indexes()
            okx_coins = set(idx.split("-", 1)[0] for idx in indexes)
        except Exception:
            pass

        relevant_dupes = {s: e for s, e in duplicates.items() if s in okx_coins}
        # Non-OKX duplicates are not mapped — no way to disambiguate reliably

        if relevant_dupes:
            print(f"  Resolving {len(relevant_dupes)} ambiguous symbols against OKX...", file=sys.stderr)
            for sym, entries in relevant_dupes.items():
                # Sort by rank: best (lowest number) first, unranked last
                ranked = sorted(entries, key=lambda e: e["rank"] if e["rank"] is not None else 999999)
                resolved = False

                for entry in ranked:
                    # Check spot then perpetual on OKX
                    for category in ("spot", "perpetual"):
                        try:
                            r = httpx.get(
                                f"{CMC_DATA_API}/cryptocurrency/market-pairs/latest",
                                params={
                                    "slug": entry["slug"],
                                    "start": 1, "limit": 100,
                                    "category": category,
                                    "centerType": "all",
                                },
                                headers=CMC_HEADERS,
                                timeout=15,
                            )
                            if r.status_code == 200:
                                pairs = r.json().get("data", {}).get("marketPairs", [])
                                has_okx = any(p.get("exchangeName") == "OKX" for p in pairs)
                                if has_okx:
                                    symbol_map[sym] = entry
                                    resolved = True
                                    print(f"    {sym} → {entry['name']} (OKX {category})", file=sys.stderr)
                                    break
                        except Exception:
                            pass
                        time.sleep(0.2)
                    if resolved:
                        break

                if not resolved:
                    # No candidate has OKX pairs — don't map this symbol
                    print(f"    {sym} → (no OKX pairs found, skipped)", file=sys.stderr)

    cache_file.write_text(json.dumps({"ts": time.time(), "map": symbol_map}))
    print(f"  Cached {len(symbol_map)} CMC coins", file=sys.stderr)
    return symbol_map


# ─────────────── TradFi vendor fetching (Pyth, Ondo, dxFeed) ───────────────

PYTH_SYMBOLS_URL = "https://history.pyth-lazer.dourolabs.app/history/v1/symbols"
DXFEED_IPF_URL = "https://tools.dxfeed.com/ipf"
DXFEED_AUTH = ("okx_exchange", "gah0QuenaeVaiy")

# Ondo's API is not publicly accessible; maintain a known ticker list.
# These are the tickers Ondo Global Markets supports for tokenized equities.
ONDO_TICKERS: set[str] = {
    "AAPL", "AMZN", "COIN", "GOOGL", "INTC", "META", "MSFT", "MSTR",
    "NFLX", "NVDA", "TSLA", "AMD", "PLTR", "SPY", "QQQ", "HOOD",
}


def _load_tradfi_coins() -> set[str]:
    """Load TradFi coin symbols from assets_types.md."""
    assets_file = Path(__file__).parent / "assets_types.md"
    coins: set[str] = set()
    if assets_file.exists():
        in_tradfi = False
        for line in assets_file.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                in_tradfi = stripped[2:].strip().lower() == "tradfi"
            elif stripped and in_tradfi:
                coins.add(stripped.upper())
    return coins


def fetch_pyth_tickers() -> dict[str, dict]:
    """Fetch Pyth Lazer symbols → {TICKER: {symbol, state, description, quote_currency}}.

    Filters to active equities, metals, commodities, FX. Cached 24h.
    """
    cache_file = CACHE_DIR / "pyth_tickers.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:
                return data["tickers"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("  Fetching Pyth Lazer symbols...", file=sys.stderr)
    resp = httpx.get(PYTH_SYMBOLS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    symbols = resp.json()

    tickers: dict[str, dict] = {}
    for s in symbols:
        state = s.get("state", "")
        if state == "coming_soon" or state == "inactive":
            continue
        symbol = s.get("symbol", "")
        # Parse: "Equity.US.TSLA/USD" → ticker=TSLA, or "Metal.XAU/USD" → ticker=XAU
        parts = symbol.rsplit(".", 1)
        if len(parts) != 2:
            continue
        pair_part = parts[1]  # "TSLA/USD" or "XAU/USD"
        ticker = pair_part.split("/")[0] if "/" in pair_part else pair_part
        if not ticker:
            continue
        tickers[ticker.upper()] = {
            "symbol": symbol,
            "state": state,
            "description": s.get("description", ""),
            "quote_currency": s.get("quote_currency", ""),
            "asset_type": s.get("asset_type", ""),
        }

    cache_file.write_text(json.dumps({"ts": time.time(), "tickers": tickers}))
    print(f"  Pyth: {len(tickers)} active tickers", file=sys.stderr)
    return tickers


def fetch_dxfeed_tickers() -> dict[str, dict]:
    """Fetch dxFeed IPF symbols → {TICKER: {symbol, type, currency, country}}.

    Cached 24h.
    """
    cache_file = CACHE_DIR / "dxfeed_tickers.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:
                return data["tickers"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("  Fetching dxFeed IPF...", file=sys.stderr)
    resp = httpx.get(DXFEED_IPF_URL, auth=DXFEED_AUTH, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Parse IPF format: header lines start with #, data lines are CSV
    headers_map: dict[str, list[str]] = {}
    tickers: dict[str, dict] = {}

    for line in resp.text.splitlines():
        if line.startswith("#"):
            parts = line.split("::=", 1)
            if len(parts) == 2:
                typename = parts[0].lstrip("#")
                headers_map[typename] = parts[1].split(",")
        elif line.strip():
            fields = line.split(",")
            if len(fields) >= 2:
                inst_type = fields[0]
                raw_symbol = fields[1]
                # Extract ticker: "TSLA:USLF24" → "TSLA"
                ticker = raw_symbol.split(":")[0] if ":" in raw_symbol else raw_symbol
                if not ticker:
                    continue
                col_names = headers_map.get(inst_type, [])
                row = {}
                if len(col_names) >= 4:
                    row["type"] = inst_type
                    row["raw_symbol"] = raw_symbol
                    row["currency"] = fields[col_names.index("CURRENCY")] if "CURRENCY" in col_names and col_names.index("CURRENCY") < len(fields) else ""
                    row["country"] = fields[col_names.index("COUNTRY")] if "COUNTRY" in col_names and col_names.index("COUNTRY") < len(fields) else ""
                else:
                    row = {"type": inst_type, "raw_symbol": raw_symbol}
                tickers[ticker.upper()] = row

    cache_file.write_text(json.dumps({"ts": time.time(), "tickers": tickers}))
    print(f"  dxFeed: {len(tickers)} tickers", file=sys.stderr)
    return tickers


def fetch_tradfi_vendors(coin: str) -> list[dict]:
    """For a TradFi coin, check availability across Pyth, Ondo_TICKER, dxFeed.

    Returns list of vendor market dicts.
    """
    tradfi_coins = _load_tradfi_coins()
    if coin not in tradfi_coins:
        return []

    exchange_scores = load_exchange_scores()
    results = []

    # Pyth
    pyth = fetch_pyth_tickers()
    if coin in pyth:
        info = pyth[coin]
        results.append({
            "coin": coin,
            "exchange": "Pyth",
            "symbol": f"{coin}/{info.get('quote_currency', 'USD')}",
            "category": "oracle",
            "supported": "Pyth" in exchange_scores,
            "exchange_score": exchange_scores.get("Pyth", 0),
            "rank": None,
            "price": None,
            "volume_usd": None,
            "volume_base": None,
            "depth_minus2_pct": None,
            "depth_plus2_pct": None,
            "effective_liquidity": None,
            "last_updated": None,
            "outlier_detected": False,
            "price_excluded": False,
            "volume_excluded": False,
            "subscribeName": info.get("symbol"),
            "vendor_state": info.get("state"),
            "vendor_description": info.get("description"),
            "vendor_asset_type": info.get("asset_type"),
        })

    # Ondo_TICKER — no subscribeName needed
    if coin in ONDO_TICKERS:
        results.append({
            "coin": coin,
            "exchange": "Ondo_TICKER",
            "symbol": f"{coin}/USD",
            "category": "oracle",
            "supported": "Ondo_TICKER" in exchange_scores,
            "exchange_score": exchange_scores.get("Ondo_TICKER", 0),
            "rank": None,
            "price": None,
            "volume_usd": None,
            "volume_base": None,
            "depth_minus2_pct": None,
            "depth_plus2_pct": None,
            "effective_liquidity": None,
            "last_updated": None,
            "outlier_detected": False,
            "price_excluded": False,
            "volume_excluded": False,
        })

    # dxFeed
    dxfeed = fetch_dxfeed_tickers()
    if coin in dxfeed:
        info = dxfeed[coin]
        results.append({
            "coin": coin,
            "exchange": "dxFeed",
            "symbol": f"{coin}/{info.get('currency', 'USD')}",
            "category": "oracle",
            "supported": "dxFeed" in exchange_scores,
            "exchange_score": exchange_scores.get("dxFeed", 0),
            "rank": None,
            "price": None,
            "volume_usd": None,
            "volume_base": None,
            "depth_minus2_pct": None,
            "depth_plus2_pct": None,
            "effective_liquidity": None,
            "last_updated": None,
            "outlier_detected": False,
            "price_excluded": False,
            "volume_excluded": False,
            "subscribeName": info.get("raw_symbol"),
            "vendor_type": info.get("type"),
            "vendor_country": info.get("country"),
        })

    return results


def _fetch_cmc_market_pairs(slug: str, category: str, limit: int = 100, max_pages: int = 5) -> list[dict]:
    """Fetch market pairs from CMC data-api for a given slug and category (spot/perpetual).

    Caps at max_pages pages (default 500 pairs) to avoid endless pagination for
    high-volume coins like USDT.
    """
    all_pairs = []
    start = 1
    page = 0
    while page < max_pages:
        resp = httpx.get(
            f"{CMC_DATA_API}/cryptocurrency/market-pairs/latest",
            params={
                "slug": slug,
                "start": start,
                "limit": limit,
                "category": category,
                "centerType": "all",
                "sort": "cmc_rank_advanced",
            },
            headers=CMC_HEADERS,
            timeout=30,
        )
        if resp.status_code == 429:
            print(f"    CMC rate limited, waiting 10s...", file=sys.stderr)
            time.sleep(10)
            continue
        resp.raise_for_status()
        data = resp.json()
        pairs = data.get("data", {}).get("marketPairs", [])
        if not pairs:
            break
        all_pairs.extend(pairs)
        if len(pairs) < limit:
            break
        start += limit
        page += 1
        time.sleep(0.5)  # brief pause between pages
    return all_pairs


def fetch_markets_for_coin(coin: str, quiet: bool = False) -> list[dict]:
    """Fetch spot + perpetual markets for a coin from CoinMarketCap.

    Returns list of market dicts with quality metrics. Uses 6h cache.
    Set quiet=True to suppress per-coin progress messages.
    """
    cache_file = CACHE_DIR / f"{coin}_markets.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 21600:  # 6h cache
                return data["markets"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Fast path: resolve just this coin instead of building the full map
    coin_info = resolve_cmc_coin(coin)
    if not coin_info:
        return []

    slug = coin_info["slug"]
    exchange_scores = load_exchange_scores()

    markets = []

    for category in ("spot", "perpetual"):
        if not quiet:
            print(f"  Fetching {category} markets for {coin} ({slug})...", file=sys.stderr)
        pairs = _fetch_cmc_market_pairs(slug, category)
        for p in pairs:
            cmc_exchange = p.get("exchangeName", "")
            exchange = map_exchange_name(cmc_exchange, category)
            raw_pair = p.get("marketPair", "")
            symbol = format_symbol(raw_pair, exchange) if raw_pair else ""

            supported = exchange in exchange_scores

            row = {
                "coin": coin,
                "exchange": exchange,
                "symbol": symbol,
                "_raw_pair": raw_pair,
                "_quote_currency_id": p.get("quoteCurrencyId"),
                "category": category,
                "supported": supported,
                "exchange_score": exchange_scores.get(exchange, 0),
                "rank": p.get("rank"),
                "price": p.get("price"),
                "volume_usd": p.get("volumeUsd"),
                "volume_base": p.get("volumeBase"),
                "volume_quote": p.get("volumeQuote"),
                "depth_minus2_pct": p.get("depthUsdNegativeTwo"),
                "depth_plus2_pct": p.get("depthUsdPositiveTwo"),
                "effective_liquidity": p.get("effectiveLiquidity"),
                "last_updated": p.get("lastUpdated"),
                "outlier_detected": bool(p.get("outlierDetected")),
                "price_excluded": bool(p.get("priceExcluded")),
                "volume_excluded": bool(p.get("volumeExcluded")),
            }

            # Perpetual-specific fields
            if category == "perpetual":
                row["open_interest_usd"] = p.get("openInterestUsd")
                row["index_price"] = p.get("indexPrice")
                row["index_basis"] = p.get("indexBasis")
                row["funding_rate"] = p.get("fundingRate")

            markets.append(row)

    # Fix Hyperliquid perpetual markets: CMC reports all quotes as "USD" but
    # each prefix (market type) settles in a different stablecoin.
    # Map by prefix — more reliable than CMC's quoteCurrencyId which is inconsistent.
    #   (none) = USDC  — standard Hyperliquid perps
    #   cash:  = USDT  — cash-settled
    #   xyz:   = USDC  — XYZ vaults
    #   flx:   = USDH  — FLX / Hyperliquid native stablecoin
    #   km:    = USDH  — Keom vaults
    #   hyna:  = USDe  — Ethena USDe vaults
    _HL_PREFIX_QUOTE = {
        "cash": "USDT",
        "xyz": "USDC",
        "flx": "USDH",
        "km": "USDH",
        "hyna": "USDe",
    }
    _HL_DEFAULT_QUOTE = "USDC"  # standard perps (no prefix)

    for m in markets:
        if m.get("exchange") != "Hyperliquid_LINEAR_PERPETUAL":
            continue
        raw = m.pop("_raw_pair", "")
        m.pop("_quote_currency_id", None)
        sym = m.get("symbol", "")
        base = sym.split("/")[0] if "/" in sym else sym
        # Derive prefix and quote
        if ":" in raw:
            prefix = raw.split(":", 1)[0]
            quote = _HL_PREFIX_QUOTE.get(prefix, _HL_DEFAULT_QUOTE)
            m["subscribeName"] = f"{prefix}:{base}"
        else:
            quote = _HL_DEFAULT_QUOTE
            m["subscribeName"] = base
        m["symbol"] = f"{base}/{quote}"

    # TradFi vendors (Pyth, Ondo, dxFeed)
    vendor_markets = fetch_tradfi_vendors(coin)
    markets.extend(vendor_markets)

    # Binance_LINEAR_INDEX: available for any TradFi coin that has a Binance perpetual
    tradfi_coins = _load_tradfi_coins()
    if coin in tradfi_coins:
        has_binance_perp = any(
            m.get("exchange") == "Binance_LINEAR_PERPETUAL" for m in markets
        )
        if has_binance_perp:
            # Derive symbol from the Binance perp symbol
            binance_perp = next(
                m for m in markets if m.get("exchange") == "Binance_LINEAR_PERPETUAL"
            )
            markets.append({
                "coin": coin,
                "exchange": "Binance_LINEAR_INDEX",
                "symbol": binance_perp.get("symbol", f"{coin}/USDT"),
                "category": "oracle",
                "supported": "Binance_LINEAR_INDEX" in exchange_scores,
                "exchange_score": exchange_scores.get("Binance_LINEAR_INDEX", 0),
                "rank": None,
                "price": None,
                "volume_usd": None,
                "volume_base": None,
                "depth_minus2_pct": None,
                "depth_plus2_pct": None,
                "effective_liquidity": None,
                "last_updated": None,
                "outlier_detected": False,
                "price_excluded": False,
                "volume_excluded": False,
            })

    # Clean up internal fields before caching
    for m in markets:
        m.pop("_raw_pair", None)
        m.pop("_quote_currency_id", None)

    cache_file.write_text(json.dumps({"ts": time.time(), "markets": markets}))
    return markets


# ─────────────── Component picking ───────────────


def _load_exchange_tier_map() -> dict[str, int]:
    """Load exchange→tier mapping from exchange_tiers.csv."""
    import csv
    tier_file = Path(__file__).parent / "exchange_tiers.csv"
    mapping: dict[str, int] = {}
    if tier_file.exists():
        with open(tier_file) as f:
            for row in csv.DictReader(f):
                mapping[row["exchange"]] = int(row["tierValue"])
    return mapping


EXCHANGE_TIER_MAP: dict[str, int] = _load_exchange_tier_map()


def exchange_to_tier(exchange: str) -> int:
    """Look up tier value for an exchange. Falls back to 2 if unknown."""
    return EXCHANGE_TIER_MAP.get(exchange, 2)


def _get_index_set() -> set[str]:
    """Load the real OKX index list as a set (cached in module)."""
    if not hasattr(_get_index_set, "_cache"):
        _get_index_set._cache = set(get_indexes())
    return _get_index_set._cache


def get_conversion(pair_target: str, index_quote: str) -> tuple[int, str]:
    """Return (conversion_type, conversionIndex) for a pair target and index quote.

    Conversion types:
      0: No conversion (pair quote == index quote)
      1: Multiply  — idxPx = symPx × conversionIndex price
      2: Divide    — idxPx = symPx ÷ conversionIndex price
      3: Count backwards — idxPx = 1 ÷ symPx (no conversionIndex needed)
      4: Be divided — idxPx = conversionIndex price ÷ symPx

    Only uses conversionIndex values that exist in the real OKX index list.
    No approximate substitutions (e.g. USD≠USDT) — conversion must be exact.
    Returns a warning if no valid conversion exists.
    """
    if pair_target == index_quote:
        return (0, "")

    index_set = _get_index_set()

    # Type 1: multiply — idxPx = symPx × (pair_target/index_quote price)
    fwd = f"{pair_target}-{index_quote}"
    if fwd in index_set:
        return (1, fwd)

    # Type 2: divide — idxPx = symPx ÷ (index_quote/pair_target price)
    rev = f"{index_quote}-{pair_target}"
    if rev in index_set:
        return (2, rev)

    # Check hardcoded map as fallback (validated)
    key = (pair_target, index_quote)
    if key in CONVERSION_MAP:
        conv_type, conv_index = CONVERSION_MAP[key]
        if conv_index in index_set:
            return (conv_type, conv_index)

    # No valid conversion exists
    print(
        f"  Warning: no valid conversionIndex for {pair_target}→{index_quote} "
        f"(neither {fwd} nor {rev} exist in index list)",
        file=sys.stderr,
    )
    return (1, fwd)


def rank_ticker(ticker: dict, exchange_scores: dict[str, int]) -> float:
    """Score a ticker for ranking. Higher = better."""
    score = 0.0
    exchange = ticker["exchange"]
    ex_score = exchange_scores.get(exchange, 1)
    volume_usd = float(ticker.get("volume_usd") or 0)
    depth = float(ticker.get("depth_minus2_pct") or 0) + float(ticker.get("depth_plus2_pct") or 0)

    score += ex_score * 1_000_000
    score += min(volume_usd, 10_000_000_000) / 1000
    score += min(depth, 100_000_000) / 100  # depth bonus
    if ticker.get("outlier_detected"):
        score -= 5_000_000
    if ticker.get("price_excluded"):
        score -= 5_000_000

    return score


def recommend_components(coin: str, max_components: int = 5) -> list[dict]:
    """Pick best spot component alternatives for a coin using two-round selection."""
    markets = fetch_markets_for_coin(coin)
    exchange_scores = load_exchange_scores()

    # Only spot markets for index components, exclude flagged
    candidates = [
        m for m in markets
        if m["supported"]
        and m.get("category") == "spot"
        and not m.get("outlier_detected")
        and not m.get("price_excluded")
    ]
    if not candidates:
        return []

    selected: list[dict] = []
    used_keys: set[tuple] = set()

    # Round 1: score>=4 exchanges, best single pair per exchange
    good_exchanges = {ex for ex, sc in exchange_scores.items() if sc >= 4}
    round1_by_exchange: dict[str, list[dict]] = {}
    for t in candidates:
        if t["exchange"] in good_exchanges:
            round1_by_exchange.setdefault(t["exchange"], []).append(t)

    for ex in sorted(round1_by_exchange, key=lambda e: exchange_scores.get(e, 0), reverse=True):
        if len(selected) >= max_components:
            break
        ex_tickers = round1_by_exchange[ex]
        best = max(ex_tickers, key=lambda t: rank_ticker(t, exchange_scores))
        key = (best["exchange"], best["symbol"])
        if key not in used_keys:
            selected.append(best)
            used_keys.add(key)

    # Round 2: fill remaining from all unpicked pairs
    if len(selected) < max_components:
        remaining = [t for t in candidates if (t["exchange"], t["symbol"]) not in used_keys]
        remaining.sort(key=lambda t: rank_ticker(t, exchange_scores), reverse=True)
        for t in remaining:
            if len(selected) >= max_components:
                break
            key = (t["exchange"], t["symbol"])
            if key not in used_keys:
                selected.append(t)
                used_keys.add(key)

    return selected


# ─────────────── Adjustment file generation ───────────────


def generate_adjustment(components_spec: list[dict]) -> dict:
    """Generate index_components CSV from a component specification.

    Each item in components_spec should have:
      - index: e.g. "BTC-USD"
      - components: list of component dicts

    Required per component:
      - exchange: canonical exchange name (e.g. "Binance", "Pyth", "OKX_PERPETUAL")
      - symbol: trading pair in BASE/QUOTE format (e.g. "BTC/USDT")
                OR pair in BASE-QUOTE format (auto-converted to slash)

    Optional per component (auto-derived if omitted):
      - weight: component weight (left empty for OKX to auto-assign if omitted)
      - conversionType: 0=none, 1=multiply, 2=divide (auto-derived from symbol vs index quote)
      - conversionIndex: e.g. "USDT-USD" (auto-derived)
      - tier: tier value (auto-derived from exchange score if omitted)
      - priceMultiple: price multiplier (default 1)
      - emaLagMs: EMA lag in milliseconds (default 0)
      - subscribeName: vendor feed identifier (e.g. "Equity.US.TSLA/USD" for Pyth)
      - uniqueExchangeAlias: alias for the exchange
      - conversionCheck: "TRUE" or "FALSE" (default "TRUE")
      - sharesMultiplierSource/Token/Benchmark: auto-derived for Ondo token pairs
        (base ending in "ON", e.g. TSLAON → source=Ondo, token=TSLA, benchmark=1.001)
      - chainId, tokenAddress, poolAddress, baseTokenAddress, quoteTokenAddress: on-chain fields

    Returns {path, rows, indexes} dict.
    """
    exchange_scores = load_exchange_scores()
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"index_components_{ts}.csv"

    output_rows: list[dict] = []

    for spec in components_spec:
        index = spec["index"]
        parts = index.split("-", 1)
        if len(parts) != 2:
            continue
        _, index_quote = parts

        for comp in spec.get("components", []):
            exchange = comp.get("exchange", "")
            # Accept both "symbol" (BASE/QUOTE) and "pair" (BASE-QUOTE)
            raw_symbol = comp.get("symbol", "") or comp.get("pair", "")
            # Normalize to slash for parsing
            normalized = raw_symbol.replace("-", "/") if "/" not in raw_symbol else raw_symbol
            if not normalized or "/" not in normalized:
                continue

            pair_base, pair_target = normalized.split("/", 1)
            # Format output symbol per exchange convention
            symbol = format_symbol(normalized, exchange)

            # Auto-derive conversion if not explicitly set
            if "conversionType" in comp:
                conv_type = comp["conversionType"]
                conv_index = comp.get("conversionIndex", "")
            else:
                conv_type, conv_index = get_conversion(pair_target, index_quote)

            # Auto-derive tier from exchange lookup if not set
            if "tier" in comp:
                tier = comp["tier"]
            else:
                tier = exchange_to_tier(exchange)

            # Auto-derive sharesMultiplier fields for Ondo tokenized pairs.
            # Ondo tokens have base ending in "ON" (e.g. TSLAON, NVDAON).
            # The underlying ticker is the base without "ON" suffix.
            sm_source = comp.get("sharesMultiplierSource", "")
            sm_token = comp.get("sharesMultiplierToken", "")
            sm_benchmark = comp.get("sharesMultiplierBenchmark", "")
            if not sm_source and pair_base.upper().endswith("ON"):
                underlying = pair_base[:-2].upper()
                if underlying in ONDO_TICKERS:
                    sm_source = "Ondo"
                    sm_token = underlying
                    sm_benchmark = sm_benchmark or "1.001"

            output_rows.append({
                "index": index,
                "exchange": exchange,
                "symbol": symbol,
                "conversion type(1× 2÷ 0 noConversion)": conv_type,
                "conversionIndex": conv_index,
                "weight": comp.get("weight", ""),
                "tier value": tier,
                "priceMultiple": comp.get("priceMultiple", 1),
                "emaLagMs": comp.get("emaLagMs", 0),
                "uniqueExchangeAlias": comp.get("uniqueExchangeAlias", ""),
                "chainId": comp.get("chainId", ""),
                "tokenAddress": comp.get("tokenAddress", ""),
                "poolAddress": comp.get("poolAddress", ""),
                "baseTokenAddress": comp.get("baseTokenAddress", ""),
                "quoteTokenAddress": comp.get("quoteTokenAddress", ""),
                "subscribeName": comp.get("subscribeName", ""),
                "sharesMultiplierSource": sm_source,
                "sharesMultiplierToken": sm_token,
                "sharesMultiplierBenchmark": sm_benchmark,
                "conversionCheck": comp.get("conversionCheck", "TRUE"),
            })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)

    return {
        "path": str(output_path),
        "rows": len(output_rows),
        "indexes": len(components_spec),
    }
