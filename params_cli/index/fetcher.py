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
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_DELAY = 6  # seconds between CoinGecko calls (free tier)
HEADERS = {"User-Agent": "params-cli/1.0"}

# ─────────────── Symbol → CoinGecko ID mapping ───────────────

SYMBOL_OVERRIDES: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2",
    "SHIB": "shiba-inu",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "FIL": "filecoin",
    "ICP": "internet-computer",
    "ETC": "ethereum-classic",
    "NEAR": "near",
    "FTM": "fantom",
    "GRT": "the-graph",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "AXS": "axie-infinity",
    "FLOW": "flow",
    "LUNA": "terra-luna-2",
    "OP": "optimism",
    "ARB": "arbitrum",
    "SUI": "sui",
    "SEI": "sei-network",
    "TIA": "celestia",
    "TON": "the-open-network",
    "WLD": "worldcoin-wld",
    "PEPE": "pepe",
    "FLOKI": "floki",
    "BONK": "bonk",
    "WIF": "dogwifcoin",
    "INJ": "injective-protocol",
    "TRX": "tron",
    "CRO": "crypto-com-chain",
    "BNB": "binancecoin",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AAVE": "aave",
    "MKR": "maker",
    "APE": "apecoin",
    "COMP": "compound-governance-token",
    "SNX": "havven",
    "CRV": "curve-dao-token",
    "SUSHI": "sushi",
    "YFI": "yearn-finance",
    "1INCH": "1inch",
    "ENS": "ethereum-name-service",
    "LDO": "lido-dao",
    "RPL": "rocket-pool",
    "SSV": "ssv-network",
    "EIGEN": "eigenlayer",
    "PENDLE": "pendle",
    "ENA": "ethena",
    "W": "wormhole",
    "JUP": "jupiter-exchange-solana",
    "JTO": "jito-governance-token",
    "PYTH": "pyth-network",
    "ONDO": "ondo-finance",
    "RAY": "raydium",
    "RENDER": "render-token",
    "FET": "fetch-ai",
    "TAO": "bittensor",
    "GALA": "gala",
    "IMX": "immutable-x",
    "STX": "blockstack",
    "APT": "aptos",
    "ALGO": "algorand",
    "VET": "vechain",
    "HBAR": "hedera-hashgraph",
    "THETA": "theta-token",
    "KAS": "kaspa",
    "CORE": "coredaoorg",
}


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
    """Fetch OKX SPOT + SWAP instruments. Returns {spot: [...], perpetual: [...]}."""
    result = {"spot": [], "perpetual": []}
    for inst_type, key in [("SPOT", "spot"), ("SWAP", "perpetual")]:
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


def extract_indexes(data: dict) -> list[str]:
    """Derive unique index names from spot and perpetual instruments.

    Rules:
      - Spot "BTC-USDT" → index "BTC-USDT"
      - Swap "TSLA-USDT-SWAP" → strip "-SWAP" → "TSLA-USDT"
      - Swap "BTC-USD_UM-SWAP" → strip "-SWAP" then "_UM" → "BTC-USD"
    """
    indexes: set[str] = set()

    for inst in data.get("spot", []):
        inst_id = inst.get("instId", "")
        if inst_id and inst.get("state") == "live":
            indexes.add(inst_id)

    for inst in data.get("perpetual", []):
        inst_id = inst.get("instId", "")
        if inst_id and inst.get("state") == "live":
            index = inst_id.removesuffix("-SWAP")
            if "_" in index:
                index = index[: index.rfind("_")]
            indexes.add(index)

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


# ─────────────── CoinGecko market fetching ───────────────


def _score_coin(coin: dict) -> int:
    """Score a CoinGecko coin entry to pick the 'real' coin for a symbol."""
    cid = coin["id"]
    name = coin["name"]
    score = 0
    if any(w in cid for w in ["bridged", "wrapped", "wormhole", "peg", "osmosis-all"]):
        score -= 200
    score -= cid.count("-") * 15
    score -= len(name.split()) * 5
    score -= len(cid)
    return score


def fetch_coin_list() -> dict[str, str]:
    """Fetch CoinGecko /coins/list → symbol->id mapping."""
    cache_file = CACHE_DIR / "coingecko_coins_list.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Cache for 24h
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data.get("ts", 0) < 86400:
                return data["map"]
        except (json.JSONDecodeError, KeyError):
            pass

    for attempt in range(3):
        resp = httpx.get(f"{COINGECKO_BASE}/coins/list", headers=HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"    Rate limited on coins/list, waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        raise RuntimeError("CoinGecko rate limited after 3 retries on coins/list")
    coins = resp.json()

    by_symbol: dict[str, list[dict]] = {}
    for coin in coins:
        sym = coin["symbol"].upper()
        by_symbol.setdefault(sym, []).append(coin)

    symbol_map: dict[str, str] = {}
    for sym, candidates in by_symbol.items():
        if sym in SYMBOL_OVERRIDES:
            symbol_map[sym] = SYMBOL_OVERRIDES[sym]
        else:
            best = max(candidates, key=_score_coin)
            symbol_map[sym] = best["id"]

    cache_file.write_text(json.dumps({"ts": time.time(), "map": symbol_map}))
    return symbol_map


def fetch_coin_tickers(coin_id: str) -> list[dict]:
    """Fetch all tickers for a coin from CoinGecko (handles pagination, retries)."""
    all_tickers = []
    page = 1
    max_retries = 3
    while True:
        for attempt in range(max_retries):
            try:
                resp = httpx.get(
                    f"{COINGECKO_BASE}/coins/{coin_id}/tickers",
                    params={"page": page, "order": "volume_desc"},
                    headers=HEADERS,
                    timeout=60,
                )
                if resp.status_code == 429:
                    print("    Rate limited, waiting 60s...", file=sys.stderr)
                    time.sleep(60)
                    continue
                if resp.status_code == 404:
                    return all_tickers
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                wait = 15 * (attempt + 1)
                print(f"    Error: {e}, retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
        else:
            break

        tickers = data.get("tickers", [])
        if not tickers:
            break
        all_tickers.extend(tickers)
        if len(tickers) < 100:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_tickers


def fetch_markets_for_coin(coin: str) -> list[dict]:
    """Fetch CoinGecko markets for a single coin, cross-referenced with supported exchanges.

    Returns list of market dicts with quality metrics. Uses 6h cache.
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

    # Check if coin list is cached to avoid unnecessary delay
    coin_list_cached = (CACHE_DIR / "coingecko_coins_list.json").exists()
    symbol_map = fetch_coin_list()
    cg_id = symbol_map.get(coin)
    if not cg_id:
        return []

    exchange_map = load_supported_exchanges()

    # Only delay if coin list was served from cache (otherwise the API call already took time)
    if coin_list_cached:
        time.sleep(REQUEST_DELAY)
    else:
        time.sleep(REQUEST_DELAY * 2)  # extra buffer after fresh coin list fetch
    tickers = fetch_coin_tickers(cg_id)

    markets = []
    for t in tickers:
        exchange_id = t.get("market", {}).get("identifier", "")
        exchange_name = t.get("market", {}).get("name", "")
        base = t.get("base", "")
        target = t.get("target", "")
        pair = f"{base}-{target}" if base and target else ""

        converted_last = t.get("converted_last", {})
        converted_volume = t.get("converted_volume", {})

        supported_info = exchange_map.get(exchange_id)
        supported_name = supported_info["name"] if supported_info else None

        markets.append({
            "coin": coin,
            "exchange": supported_name or exchange_name,
            "pair": pair,
            "supported": bool(supported_name),
            "coingecko_exchange_id": exchange_id,
            "last_price": t.get("last", ""),
            "price_usd": converted_last.get("usd", ""),
            "volume": t.get("volume", ""),
            "volume_usd": converted_volume.get("usd", ""),
            "bid_ask_spread_pct": t.get("bid_ask_spread_percentage", ""),
            "trust_score": t.get("trust_score", ""),
            "is_anomaly": t.get("is_anomaly", False),
            "is_stale": t.get("is_stale", False),
            "last_traded_at": t.get("last_traded_at", ""),
        })

    cache_file.write_text(json.dumps({"ts": time.time(), "markets": markets}))
    return markets


# ─────────────── Component picking ───────────────


def score_to_tier(score: int) -> int:
    """Map exchange score to tier value."""
    if score >= 5:
        return 4
    if score >= 4:
        return 3
    return 2


def get_conversion(pair_target: str, index_quote: str) -> tuple[int, str]:
    """Return (conversion_type, conversionIndex) for a pair target and index quote."""
    if pair_target == index_quote:
        return (0, "")
    key = (pair_target, index_quote)
    if key in CONVERSION_MAP:
        return CONVERSION_MAP[key]
    return (1, f"{pair_target}-{index_quote}")


def rank_ticker(ticker: dict, exchange_scores: dict[str, int]) -> float:
    """Score a ticker for ranking. Higher = better."""
    score = 0.0
    exchange = ticker["exchange"]
    ex_score = exchange_scores.get(exchange, 1)
    volume_usd = float(ticker.get("volume_usd") or 0)
    spread = float(ticker.get("bid_ask_spread_pct") or 999)

    score += ex_score * 1_000_000
    score += min(volume_usd, 10_000_000_000) / 1000
    if spread < 999:
        score += max(0, (1 - spread) * 100_000)
    if ticker.get("is_stale"):
        score -= 5_000_000
    if ticker.get("is_anomaly"):
        score -= 5_000_000

    return score


def recommend_components(coin: str, max_components: int = 5) -> list[dict]:
    """Pick best component alternatives for a coin using two-round selection."""
    markets = fetch_markets_for_coin(coin)
    exchange_scores = load_exchange_scores()

    candidates = [
        m for m in markets
        if m["supported"]
        and not m.get("is_anomaly")
        and not m.get("is_stale")
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
        key = (best["exchange"], best["pair"])
        if key not in used_keys:
            selected.append(best)
            used_keys.add(key)

    # Round 2: fill remaining from all unpicked pairs
    if len(selected) < max_components:
        remaining = [t for t in candidates if (t["exchange"], t["pair"]) not in used_keys]
        remaining.sort(key=lambda t: rank_ticker(t, exchange_scores), reverse=True)
        for t in remaining:
            if len(selected) >= max_components:
                break
            key = (t["exchange"], t["pair"])
            if key not in used_keys:
                selected.append(t)
                used_keys.add(key)

    return selected


# ─────────────── Adjustment file generation ───────────────


def generate_adjustment(components_spec: list[dict]) -> dict:
    """Generate index_components CSV from a component specification.

    Each item in components_spec should have:
      - index: e.g. "BTC-USD"
      - components: list of {exchange, pair} dicts
        e.g. [{"exchange": "Binance", "pair": "BTC-USDT"}, ...]

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
        _, quote = parts

        for comp in spec.get("components", []):
            exchange = comp["exchange"]
            pair = comp.get("pair", "")
            pair_parts = pair.split("-", 1)
            if len(pair_parts) != 2:
                continue
            pair_base, pair_target = pair_parts
            symbol = f"{pair_base}/{pair_target}"
            conv_type, conv_index = get_conversion(pair_target, quote)
            ex_score = exchange_scores.get(exchange, 1)
            tier = score_to_tier(ex_score)

            output_rows.append({
                "index": index,
                "exchange": exchange,
                "symbol": symbol,
                "conversion type(1× 2÷ 0 noConversion)": conv_type,
                "conversionIndex": conv_index,
                "weight": "",
                "tier value": tier,
                "priceMultiple": 1,
                "emaLagMs": 0,
                "uniqueExchangeAlias": "",
                "chainId": "",
                "tokenAddress": "",
                "poolAddress": "",
                "baseTokenAddress": "",
                "quoteTokenAddress": "",
                "subscribeName": "",
                "sharesMultiplierSource": "",
                "sharesMultiplierToken": "",
                "sharesMultiplierBenchmark": "",
                "conversionCheck": "TRUE",
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
