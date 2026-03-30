#!/usr/bin/env python3
"""Index Price Deviation CLI — agent-friendly interface.

JSON on stdout, progress/status on stderr.
Shows hints on first call; results on subsequent calls within 5 minutes.
"""

import json
import re
import sys
import time
from pathlib import Path

import click

CACHE_DIR = Path(__file__).parent / "cache"
HINTS_FILE = Path(__file__).parent / "hints.md"
LAST_CALL_FILE = CACHE_DIR / ".last_call.json"
HINTS_TTL = 300  # 5 minutes


# ─────────────── Hints system ───────────────


def _get_last_call(command: str) -> float:
    try:
        with open(LAST_CALL_FILE) as f:
            return json.load(f).get(command, 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def _set_last_call(command: str):
    data = {}
    try:
        with open(LAST_CALL_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    data[command] = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_CALL_FILE, "w") as f:
        json.dump(data, f)


def _get_hints(section: str) -> str | None:
    if not HINTS_FILE.exists():
        return None
    content = HINTS_FILE.read_text()
    pattern = rf"^# {re.escape(section)}\s*\n(.*?)(?=^# |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _check_hints(command: str) -> bool:
    """If command wasn't called in the last 5 minutes, output hints and return True."""
    now = time.time()
    if now - _get_last_call(command) > HINTS_TTL:
        hints = _get_hints(command)
        if hints:
            _out({
                "STATUS": "HINTS_ONLY",
                "retry": True,
                "command": command,
                "message": hints,
            })
        _set_last_call(command)
        return bool(hints)
    _set_last_call(command)
    return False


def _out(data, pretty: bool = True):
    """Write JSON to stdout."""
    if pretty:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        click.echo(json.dumps(data, ensure_ascii=False))


def _error(msg: str, code: int = 1):
    _out({"status": "error", "message": msg})
    sys.exit(code)


def _safe_f(v) -> float | None:
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


# ─────────────── CLI ───────────────


@click.group()
def cli():
    """Index Price Deviation CLI — monitor index price quality on OKX."""


@cli.command("help")
def help_cmd():
    """Show workflows and method list."""
    _out({
        "status": "ok",
        "workflows": {
            "Monitor": "server → ema [INDEX]",
            "QuickCheck": "snapshot [INDEX]",
            "SearchIndexes": "search QUERY",
            "InspectComponents": "components INDEX",
            "ReviewComponents": "markets COIN → generate-adjustment JSON",
            "ReviewQuality": "review [INDEX...] → (review script) → generate-adjustment",
        },
        "methods": {
            "help": "Show workflows and method list",
            "search": "Search indexes by keyword (e.g. search \"BTC USDT\")",
            "indexes": "List all real OKX indexes (derived from instruments)",
            "components": "Query index component setup (exchange, weight, symbol)",
            "server": "Start/stop/check the index deviation monitor server",
            "ema": "Query EMA of deviation metrics from server or cache",
            "snapshot": "Quick one-shot fetch of current index quality (no server needed)",
            "markets": "Fetch spot + perpetual markets for a coin from CoinMarketCap",
            "generate-adjustment": "Generate index_components CSV from selected components",
            "review": "Prepare data for index component quality review",
            "refresh-cache": "Clear cached data and re-fetch",
        },
    })


@cli.command("search")
@click.argument("query", required=False, default=None)
@click.option("--limit", default=20, help="Max results (default: 20)")
def search_cmd(query: str | None, limit: int):
    """Search indexes by query string.

    Matches against index name, base coin, quote currency, and asset type.
    Multiple tokens are AND-matched.

    Examples:
        ./cli.py search BTC
        ./cli.py search "BTC USDT"
        ./cli.py search tradfi
        ./cli.py search topcoins
        ./cli.py search "tradfi USD"
        ./cli.py search "ETH USD" --limit 5
    """
    if _check_hints("search"):
        return

    if not query:
        _error("Missing query argument. Usage: ./cli.py search \"BTC USDT\"")

    tokens = [t.upper() for t in re.split(r"[^a-zA-Z0-9]+", query) if t]
    if not tokens:
        _error("Empty query")

    # Build asset type map from assets_types.md
    ASSETS_FILE = Path(__file__).parent / "assets_types.md"
    asset_map: dict[str, str] = {}
    if ASSETS_FILE.exists():
        current_type = ""
        for line in ASSETS_FILE.read_text().splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                current_type = line_s[2:].strip()
            elif line_s and current_type:
                asset_map[line_s.upper()] = current_type

    from fetcher import get_indexes

    indexes = get_indexes()
    results = []
    for idx in indexes:
        parts = idx.split("-", 1)
        base = parts[0].upper() if parts else ""
        assets_type = asset_map.get(base, "Altcoins")
        match_str = f"{idx}-{assets_type}".upper()
        if all(token in match_str for token in tokens):
            results.append({
                "index": idx,
                "baseCoin": base,
                "quoteCcy": parts[1] if len(parts) > 1 else "",
                "assetsType": assets_type,
            })
    if limit > 0:
        results = results[:limit]
    _out({
        "status": "ok",
        "query": query,
        "tokens": tokens,
        "count": len(results),
        "data": results,
    })


@cli.command("indexes")
@click.option("--coin", default=None, help="Filter indexes by base coin")
@click.option("--limit", default=0, help="Max results (0=all)")
@click.option("--refresh", is_flag=True, help="Force refresh from OKX API")
def indexes_cmd(coin: str | None, limit: int, refresh: bool):
    """List all real OKX indexes (derived from SPOT + SWAP instruments)."""
    if _check_hints("indexes"):
        return

    from fetcher import get_indexes, get_coins

    indexes = get_indexes(force=refresh)
    if coin:
        coin = coin.upper()
        indexes = [idx for idx in indexes if idx.split("-", 1)[0] == coin]

    if limit > 0:
        indexes = indexes[:limit]

    coins = sorted(set(idx.split("-", 1)[0] for idx in indexes))

    _out({
        "status": "ok",
        "count": len(indexes),
        "unique_coins": len(coins),
        "indexes": indexes,
    })


@cli.command("server")
@click.option("--port", default=8785, help="WebSocket port (HTTP on port+1)")
@click.option("--interval", default=10.0, help="Polling interval in seconds")
@click.option("--stop", is_flag=True, help="Stop a running server")
def server_cmd(port: int, interval: float, stop: bool):
    """Start/stop/check the index deviation monitor server."""
    if not stop and _check_hints("server"):
        return

    import os
    import signal
    from server import read_server_status

    existing = read_server_status(port)

    if stop:
        if existing and existing.get("pid"):
            try:
                os.kill(existing["pid"], signal.SIGTERM)
                _out({"status": "ok", "message": f"Server (pid {existing['pid']}) stopped."})
            except Exception as e:
                _error(f"Failed to stop server: {e}")
        else:
            _out({"status": "ok", "message": "No running server found."})
        return

    http_port = port + 1

    if existing:
        _out({
            "status": "already_running",
            "pid": existing["pid"],
            "websocket": f"ws://localhost:{existing['port']}",
            "http": f"http://localhost:{existing['http_port']}",
            "endpoints": {
                "snapshot": f"http://localhost:{existing['http_port']}/snapshot",
                "index_detail": f"http://localhost:{existing['http_port']}/snapshot/{{index}}",
                "search": f"http://localhost:{existing['http_port']}/search?q={{query}}",
                "alerts": f"http://localhost:{existing['http_port']}/alerts",
                "health": f"http://localhost:{existing['http_port']}/health",
            },
            "indices": existing.get("indices", 0),
            "message": "Server is already running. Use --stop to shut it down.",
        })
        return

    import subprocess
    server_script = str(Path(__file__).parent / "server.py")
    log_file = str(CACHE_DIR / "index_server.log")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            [
                sys.executable, server_script,
                "--port", str(port),
                "--interval", str(interval),
            ],
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,
        )

    import time as _time
    for _ in range(30):
        _time.sleep(1)
        status = read_server_status(port)
        if status and status.get("indices", 0) > 0:
            break

    status = read_server_status(port)
    if status:
        _out({
            "status": "started",
            "pid": proc.pid,
            "websocket": f"ws://localhost:{port}",
            "http": f"http://localhost:{http_port}",
            "endpoints": {
                "snapshot": f"http://localhost:{http_port}/snapshot",
                "index_detail": f"http://localhost:{http_port}/snapshot/{{index}}",
                "search": f"http://localhost:{http_port}/search?q={{query}}",
                "alerts": f"http://localhost:{http_port}/alerts",
                "health": f"http://localhost:{http_port}/health",
            },
            "indices": status.get("indices", 0),
            "log": log_file,
            "message": "Server started in background.",
        })
    else:
        _out({
            "status": "starting",
            "pid": proc.pid,
            "websocket": f"ws://localhost:{port}",
            "http": f"http://localhost:{http_port}",
            "log": log_file,
            "message": "Server spawned but still loading first data cycle. Check /health in a few seconds.",
        })


@cli.command("snapshot")
@click.argument("index_id", required=False)
@click.option("--limit", default=0, help="Max results (0=all)")
@click.option("--sort", type=click.Choice(["deviation", "components", "staleness", "name"]), default="deviation")
def snapshot_cmd(index_id: str | None, limit: int, sort: str):
    """One-shot fetch of index quality metrics (no server needed)."""
    if _check_hints("snapshot"):
        return

    import httpx as _httpx

    headers = {"User-Agent": "params-cli/1.0"}

    from server import INDEX_QUOTE_CURRENCIES

    click.echo("Fetching index tickers...", err=True)
    tickers = {}
    for quote_ccy in INDEX_QUOTE_CURRENCIES:
        try:
            resp = _httpx.get(
                "https://www.okx.com/api/v5/market/index-tickers",
                params={"quoteCcy": quote_ccy},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            ticker_data = resp.json()
            if ticker_data.get("code") == "0":
                for t in ticker_data.get("data", []):
                    tickers[t["instId"]] = t
        except Exception as e:
            click.echo(f"  [warn] {quote_ccy} tickers: {e}", err=True)

    if not tickers:
        _error("Failed to fetch any index tickers")

    # Filter to real indexes only
    from fetcher import get_indexes
    real_indexes = set(get_indexes())
    tickers = {k: v for k, v in tickers.items() if k in real_indexes}

    if index_id:
        index_id = index_id.upper()
        if index_id not in tickers:
            _error(f"Index {index_id} not found. Available: {len(tickers)} indexes.")

        click.echo(f"Fetching components for {index_id}...", err=True)
        try:
            resp = _httpx.get(
                "https://www.okx.com/api/v5/market/index-components",
                params={"index": index_id},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            comp_data = resp.json()
        except Exception as e:
            _error(f"Failed to fetch components: {e}")

        if comp_data.get("code") != "0" or not comp_data.get("data"):
            _error(f"No component data for {index_id}")

        d = comp_data["data"]
        index_px = float(tickers[index_id].get("idxPx", "0"))
        components = d.get("components", [])

        comp_details = []
        deviations = []
        for comp in components:
            sym_px = _safe_f(comp.get("symPx"))
            cnv_px = _safe_f(comp.get("cnvPx"))
            comp_px = cnv_px or sym_px
            dev = ((comp_px - index_px) / index_px * 100) if comp_px and index_px else None
            if dev is not None:
                deviations.append(abs(dev))
            comp_details.append({
                "exchange": comp.get("exch", ""),
                "symbol": comp.get("symbol", ""),
                "symPx": comp.get("symPx", ""),
                "cnvPx": comp.get("cnvPx", ""),
                "comp_px": round(comp_px, 8) if comp_px else None,
                "deviation_pct": round(dev, 4) if dev is not None else None,
                "weight": _safe_f(comp.get("wgt")),
            })

        _out({
            "status": "ok",
            "index": index_id,
            "idxPx": tickers[index_id].get("idxPx", ""),
            "component_count": len(components),
            "avg_deviation_pct": round(sum(deviations) / len(deviations), 4) if deviations else None,
            "max_deviation_pct": round(max(deviations), 4) if deviations else None,
            "components": comp_details,
        })
        return

    # All indexes — summary only
    click.echo(f"Found {len(tickers)} indexes. Computing summaries...", err=True)

    results = []
    for idx, tk in tickers.items():
        results.append({
            "index": idx,
            "idxPx": tk.get("idxPx", ""),
            "high24h": tk.get("high24h", ""),
            "low24h": tk.get("low24h", ""),
        })

    results.sort(key=lambda x: x["index"])
    if limit > 0:
        results = results[:limit]

    _out({
        "status": "ok",
        "count": len(results),
        "note": "Use 'snapshot INDEX_ID' for component-level quality metrics",
        "data": results,
    })


@cli.command("markets")
@click.argument("coin")
@click.option("--category", type=click.Choice(["all", "spot", "perpetual", "oracle"], case_sensitive=False), default="all", help="Market category")
@click.option("--supported-only", is_flag=True, default=True, help="Only show supported exchanges (default)")
@click.option("--all", "show_all", is_flag=True, help="Show all exchanges including unsupported")
@click.option("--limit", default=0, help="Max results (0=all)")
@click.option("--recommend", is_flag=True, help="Show recommended top-5 spot components")
def markets_cmd(coin: str, category: str, supported_only: bool, show_all: bool, limit: int, recommend: bool):
    """Fetch spot + perpetual markets for a coin from CoinMarketCap.

    Returns available markets across exchanges with quality metrics
    (price, volume, depth, open interest, basis, funding rate).
    """
    if _check_hints("markets"):
        return

    from fetcher import fetch_markets_for_coin, recommend_components

    coin = coin.upper()
    click.echo(f"Fetching markets for {coin}...", err=True)

    if recommend:
        selected = recommend_components(coin)
        if not selected:
            _error(f"No supported spot markets found for {coin}")
        _out({
            "status": "ok",
            "coin": coin,
            "count": len(selected),
            "recommended": [
                {
                    "exchange": m["exchange"],
                    "symbol": m.get("symbol", ""),
                    "category": m.get("category"),
                    "exchange_score": m.get("exchange_score", 0),
                    "price": m.get("price"),
                    "volume_usd": m.get("volume_usd"),
                    "depth_minus2_pct": m.get("depth_minus2_pct"),
                    "depth_plus2_pct": m.get("depth_plus2_pct"),
                }
                for m in selected
            ],
        })
        return

    markets = fetch_markets_for_coin(coin)
    if not markets:
        _error(f"No markets found for {coin}. Coin may not be on CoinMarketCap.")

    if category.lower() != "all":
        markets = [m for m in markets if m.get("category") == category.lower()]

    if not show_all:
        markets = [m for m in markets if m["supported"]]

    # Sort by volume descending
    markets.sort(key=lambda m: float(m.get("volume_usd") or 0), reverse=True)

    if limit > 0:
        markets = markets[:limit]

    def _format_market(m: dict) -> dict:
        row = {
            "exchange": m["exchange"],
            "symbol": m.get("symbol", ""),
            "category": m.get("category"),
            "supported": m["supported"],
            "exchange_score": m.get("exchange_score", 0),
            "rank": m.get("rank"),
            "price": m.get("price"),
            "volume_usd": m.get("volume_usd"),
            "volume_base": m.get("volume_base"),
            "depth_minus2_pct": m.get("depth_minus2_pct"),
            "depth_plus2_pct": m.get("depth_plus2_pct"),
            "effective_liquidity": m.get("effective_liquidity"),
            "outlier_detected": m.get("outlier_detected", False),
            "price_excluded": m.get("price_excluded", False),
            "last_updated": m.get("last_updated"),
        }
        # Add perpetual-specific fields when present
        if m.get("category") == "perpetual":
            row["open_interest_usd"] = m.get("open_interest_usd")
            row["index_price"] = m.get("index_price")
            row["index_basis"] = m.get("index_basis")
            row["funding_rate"] = m.get("funding_rate")
        # Add vendor-specific fields for oracle sources
        if m.get("category") == "oracle":
            for k in ("subscribeName", "vendor_state", "vendor_description",
                       "vendor_asset_type", "vendor_type", "vendor_country"):
                if m.get(k) is not None:
                    row[k] = m[k]
        # subscribeName for non-oracle markets (e.g. Hyperliquid perps)
        if m.get("category") != "oracle" and m.get("subscribeName"):
            row["subscribeName"] = m["subscribeName"]
        return row

    _out({
        "status": "ok",
        "coin": coin,
        "count": len(markets),
        "data": [_format_market(m) for m in markets],
    })


@cli.command("generate-adjustment")
@click.argument("components_json")
def generate_adjustment_cmd(components_json: str):
    """Generate index_components CSV from selected components.

    Input JSON array where each item has:
      - index: "BTC-USD"
      - components: array of component objects

    Required per component: exchange, symbol (BASE/QUOTE or BASE-QUOTE)
    Optional per component: weight, subscribeName, emaLagMs, priceMultiple,
      conversionType, conversionIndex, tier, uniqueExchangeAlias,
      conversionCheck, sharesMultiplierSource/Token/Benchmark,
      chainId, tokenAddress, poolAddress, baseTokenAddress, quoteTokenAddress

    If omitted, conversionType/conversionIndex/tier are auto-derived.
    sharesMultiplier fields are auto-derived for Ondo token pairs (base ending
    in "ON", e.g. TSLAON → source=Ondo, token=TSLA, benchmark=1.001).

    Examples:
      # Simple crypto index
      python3 cli.py generate-adjustment '[
        {"index":"BTC-USD","components":[
          {"exchange":"Binance","symbol":"BTC/USDT"},
          {"exchange":"Coinbase","symbol":"BTC/USD"}
        ]}
      ]'

      # TradFi with oracle vendors
      python3 cli.py generate-adjustment '[
        {"index":"TSLA-USDT","components":[
          {"exchange":"Pyth","symbol":"TSLA/USD","subscribeName":"Equity.US.TSLA/USD"},
          {"exchange":"Ondo_TICKER","symbol":"TSLA/USD"},
          {"exchange":"dxFeed","symbol":"TSLA/USD","subscribeName":"TSLA:USLF24"},
          {"exchange":"Binance_LINEAR_INDEX","symbol":"TSLA/USDT"},
          {"exchange":"Binance_LINEAR_PERPETUAL","symbol":"TSLA/USDT"},
          {"exchange":"OKX_PERPETUAL","symbol":"TSLA/USDT"}
        ]}
      ]'

      # Ondo tokenized equity (sharesMultiplier auto-derived from ON suffix)
      python3 cli.py generate-adjustment '[
        {"index":"TSLAON-USDT","components":[
          {"exchange":"Gate","symbol":"TSLAON/USDT"},
          {"exchange":"Bitget","symbol":"TSLAON/USDT"}
        ]}
      ]'
    """
    if _check_hints("generateAdjustment"):
        return

    try:
        spec = json.loads(components_json)
    except json.JSONDecodeError as e:
        _error(f"Invalid JSON: {e}")

    if not isinstance(spec, list):
        _error("Argument must be a JSON array")

    for item in spec:
        if "index" not in item:
            _error(f"Each item must have an 'index' key, got: {item}")
        if "components" not in item or not isinstance(item["components"], list):
            _error(f"Each item must have a 'components' array, got: {item}")

    from fetcher import generate_adjustment

    result = generate_adjustment(spec)
    _out({"status": "ok", **result})


@cli.command("refresh-cache")
@click.option("--markets", "coin_markets", default=None,
              help="Refresh market cache for a coin (or 'all' for every coin in the index list)")
@click.option("--clear-all", is_flag=True, help="Clear all cached data (no re-fetch)")
def refresh_cache_cmd(coin_markets: str | None, clear_all: bool):
    """Clear cached data and optionally re-fetch.

    --markets COIN  : clear + re-fetch markets for one coin
    --markets all   : clear + re-fetch markets for ALL coins in index list (slow!)
    --clear-all     : wipe all cache files
    (no flags)      : clear indexes + coin list cache
    """
    if _check_hints("refreshCache"):
        return

    from fetcher import fetch_markets_for_coin, get_coins, get_indexes

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if clear_all:
        cleared = []
        for f in CACHE_DIR.glob("*.json"):
            if f.name.startswith("."):
                continue
            f.unlink()
            cleared.append(f.name)
        _out({
            "status": "ok",
            "cleared": cleared,
            "message": f"Cleared {len(cleared)} cache files.",
        })
        return

    if coin_markets:
        if coin_markets.lower() == "all":
            # Refresh markets for ALL coins in the index list
            coins = get_coins()
            click.echo(f"Refreshing markets for {len(coins)} coins...", err=True)
            refreshed = []
            failed = []
            for i, coin in enumerate(coins):
                click.echo(f"  [{i+1}/{len(coins)}] {coin}...", err=True)
                # Clear existing cache
                cache_file = CACHE_DIR / f"{coin}_markets.json"
                if cache_file.exists():
                    cache_file.unlink()
                try:
                    markets = fetch_markets_for_coin(coin)
                    supported = sum(1 for m in markets if m["supported"])
                    click.echo(f"    → {len(markets)} markets ({supported} supported)", err=True)
                    refreshed.append({"coin": coin, "markets": len(markets), "supported": supported})
                except Exception as e:
                    click.echo(f"    → failed: {e}", err=True)
                    failed.append(coin)
            _out({
                "status": "ok",
                "refreshed": len(refreshed),
                "failed": len(failed),
                "failed_coins": failed if failed else None,
                "data": refreshed,
            })
        else:
            # Refresh markets for a single coin
            coin = coin_markets.upper()
            cache_file = CACHE_DIR / f"{coin}_markets.json"
            if cache_file.exists():
                cache_file.unlink()

            click.echo(f"Refreshing markets for {coin}...", err=True)
            try:
                markets = fetch_markets_for_coin(coin)
                supported = [m for m in markets if m["supported"]]
                _out({
                    "status": "ok",
                    "coin": coin,
                    "markets": len(markets),
                    "supported": len(supported),
                    "message": f"Refreshed {coin}: {len(markets)} markets ({len(supported)} supported).",
                })
            except Exception as e:
                _error(f"Failed to refresh {coin}: {e}")
        return

    # Default: clear indexes + coin list cache and re-fetch indexes
    cleared = []
    for name in ["indexes.json", "cmc_coin_map.json"]:
        f = CACHE_DIR / name
        if f.exists():
            f.unlink()
            cleared.append(name)

    click.echo("Re-fetching index list from OKX...", err=True)
    indexes = get_indexes(force=True)
    coins = get_coins()

    _out({
        "status": "ok",
        "cleared": cleared,
        "indexes": len(indexes),
        "coins": len(coins),
        "message": f"Refreshed index list: {len(indexes)} indexes, {len(coins)} unique coins.",
    })


@cli.command("ema")
@click.argument("index_ids", nargs=-1)
@click.option("--port", default=8785, help="Server WebSocket port (HTTP on port+1)")
def ema_cmd(index_ids: tuple[str, ...], port: int):
    """Query EMA of deviation metrics from the running server.

    Reads from the live server if running, otherwise falls back to the
    cached EMA state on disk.

    Examples:
        ./cli.py ema                          # all indexes
        ./cli.py ema BTC-USDT                 # specific index(es)
    """
    if _check_hints("ema"):
        return

    import httpx as _httpx
    from server import read_server_status, EMA_CACHE_FILE, EMA_INDEX_FIELDS, EMA_COMP_FIELDS

    http_port = port + 1
    source = None
    data = {}

    # Try live server first
    server = read_server_status(port)
    if server:
        try:
            if index_ids:
                for iid in index_ids:
                    resp = _httpx.get(f"http://localhost:{http_port}/ema/{iid}", timeout=5)
                    if resp.status_code == 200:
                        data[iid] = resp.json()
                    else:
                        click.echo(f"  [warn] no EMA data for {iid}", err=True)
            else:
                resp = _httpx.get(f"http://localhost:{http_port}/ema", timeout=10)
                if resp.status_code == 200:
                    body = resp.json()
                    data = body.get("data", {})
            source = "live"
        except Exception as e:
            click.echo(f"  [warn] live server query failed: {e}, falling back to cache", err=True)

    # Fall back to cached EMA file
    if not data:
        if EMA_CACHE_FILE.exists():
            try:
                cache = json.loads(EMA_CACHE_FILE.read_text())
                raw_index = cache.get("ema_index", {})
                raw_comp = cache.get("ema_comp", {})
                raw_ts = cache.get("ema_ts", {})
                for idx_id, ema in raw_index.items():
                    row = {"index": idx_id}
                    for field in EMA_INDEX_FIELDS:
                        v = ema.get(field)
                        row[field] = round(v, 6) if v is not None else None
                    if idx_id in raw_ts:
                        row["ema_updated"] = raw_ts[idx_id]
                    # Attach component EMAs
                    comp_emas = []
                    prefix = f"{idx_id}|"
                    for comp_key, comp_ema in raw_comp.items():
                        if not comp_key.startswith(prefix):
                            continue
                        exch_sym = comp_key[len(prefix):]
                        parts = exch_sym.split(":", 1)
                        comp_row = {
                            "exchange": parts[0] if parts else "",
                            "symbol": parts[1] if len(parts) > 1 else "",
                        }
                        for field in EMA_COMP_FIELDS:
                            v = comp_ema.get(field)
                            comp_row[field] = round(v, 6) if v is not None else None
                        if comp_key in raw_ts:
                            comp_row["ema_updated"] = raw_ts[comp_key]
                        comp_emas.append(comp_row)
                    row["components"] = comp_emas
                    data[idx_id] = row
                source = "cache"
                if index_ids:
                    data = {k: v for k, v in data.items() if k in index_ids}
            except Exception as e:
                _error(f"Failed to read EMA cache: {e}")
        else:
            _error("No running server and no EMA cache found. Start the server with: ./cli.py server")

    _out({
        "status": "ok",
        "source": source,
        "count": len(data),
        "data": data,
    })


@cli.command("components")
@click.argument("index_id", required=False)
@click.option("--coin", default=None, help="Filter by base coin")
@click.option("--limit", default=0, help="Max results (0=all)")
def components_cmd(index_id: str | None, coin: str | None, limit: int):
    """Query index component configuration (exchange, weight, symbol, conversion).

    Fetches current component setup from OKX index-components API.

    Examples:
        ./cli.py components BTC-USDT           # single index components
        ./cli.py components --coin ETH          # all ETH-* index components
        ./cli.py components --limit 5           # first 5 indexes
    """
    if _check_hints("components"):
        return

    import httpx as _httpx

    headers = {"User-Agent": "params-cli/1.0"}

    from fetcher import get_indexes

    if index_id:
        # Single index mode
        index_id = index_id.upper()
        click.echo(f"Fetching components for {index_id}...", err=True)
        try:
            resp = _httpx.get(
                "https://www.okx.com/api/v5/market/index-components",
                params={"index": index_id},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            comp_data = resp.json()
        except Exception as e:
            _error(f"Failed to fetch components: {e}")

        if comp_data.get("code") != "0" or not comp_data.get("data"):
            _error(f"No component data for {index_id}")

        d = comp_data["data"]
        components = d.get("components", [])

        comp_details = []
        for comp in components:
            comp_details.append({
                "exchange": comp.get("exch", ""),
                "symbol": comp.get("symbol", ""),
                "symPx": comp.get("symPx", ""),
                "cnvPx": comp.get("cnvPx", ""),
                "weight": _safe_f(comp.get("wgt")),
            })

        _out({
            "status": "ok",
            "index": index_id,
            "last": d.get("last", ""),
            "component_count": len(components),
            "components": comp_details,
        })
        return

    # Multi-index mode: fetch components for each matching index
    indexes = get_indexes()
    if coin:
        coin = coin.upper()
        indexes = [idx for idx in indexes if idx.split("-", 1)[0] == coin]
    if limit > 0:
        indexes = indexes[:limit]

    if not indexes:
        _error("No matching indexes found.")

    click.echo(f"Fetching components for {len(indexes)} indexes...", err=True)

    results = []
    for i, idx in enumerate(indexes):
        click.echo(f"  [{i+1}/{len(indexes)}] {idx}...", err=True)
        try:
            resp = _httpx.get(
                "https://www.okx.com/api/v5/market/index-components",
                params={"index": idx},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            comp_data = resp.json()
            if comp_data.get("code") == "0" and comp_data.get("data"):
                d = comp_data["data"]
                components = d.get("components", [])
                results.append({
                    "index": idx,
                    "last": d.get("last", ""),
                    "component_count": len(components),
                    "components": [
                        {
                            "exchange": c.get("exch", ""),
                            "symbol": c.get("symbol", ""),
                            "weight": _safe_f(c.get("wgt")),
                        }
                        for c in components
                    ],
                })
        except Exception as e:
            click.echo(f"    [warn] {idx}: {e}", err=True)
        # Brief delay to avoid rate limiting
        import time as _time
        _time.sleep(0.15)

    _out({
        "status": "ok",
        "count": len(results),
        "data": results,
    })


@cli.command("review")
@click.argument("index_ids", nargs=-1)
@click.option("--batch", default=30, help="Max indexes per output batch (0=unlimited)")
@click.option("--offset", "batch_offset", default=0, help="Skip first N flagged indexes")
@click.option("--type", "asset_type", default=None, help="Filter by asset type: TradFi, Topcoins, Fiat, Altcoins")
def review_cmd(index_ids: tuple[str, ...], batch: int, batch_offset: int, asset_type: str | None):
    """Prepare data for index component quality review.

    Optionally pass index IDs to scope the review to specific indexes.
    When no index IDs given, pre-filters to only indexes with potential issues.

    First call: outputs hints (workflow instructions).
    Second call: generates data source file and outputs file paths.
    """
    if _check_hints("review"):
        return

    import csv
    import hashlib
    import io
    from datetime import datetime

    from server import EMA_CACHE_FILE, EMA_INDEX_FIELDS, EMA_COMP_FIELDS

    BASE_DIR = Path(__file__).parent
    REVIEW_DIR = BASE_DIR / "review"
    ASSETS_FILE = BASE_DIR / "assets_types.md"

    # ── File A: methodology (static) ──
    file_a = BASE_DIR / "review_methodology.md"
    if not file_a.exists():
        _error(f"Review methodology file not found: {file_a}")

    # ── File B: script path (hash-based name, always deleted so agent regenerates) ──
    methodology_content = file_a.read_text()
    short_hash = hashlib.sha256(methodology_content.encode()).hexdigest()[:8]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    file_b = REVIEW_DIR / f"{short_hash}.py"
    if file_b.exists():
        file_b.unlink()

    # ── Parse assets_types.md ──
    asset_map: dict[str, str] = {}
    if ASSETS_FILE.exists():
        current_type = ""
        for line in ASSETS_FILE.read_text().splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                current_type = line_s[2:].strip()
            elif line_s and current_type:
                asset_map[line_s.upper()] = current_type

    # ── Load snapshot from server (try HTTP directly on default port) ──
    import subprocess as _subprocess

    click.echo("Fetching and loading markets data...", err=True)

    snapshot_data = {}
    server_http_port = 8786  # default HTTP port (WS port + 1)
    _server_live = False
    try:
        result = _subprocess.run(
            ["curl", "-s", f"http://localhost:{server_http_port}/health"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            health = json.loads(result.stdout)
            if health.get("status") == "ok":
                _server_live = True
                result = _subprocess.run(
                    ["curl", "-s", f"http://localhost:{server_http_port}/snapshot"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    snapshot_data = json.loads(result.stdout).get("data", {})
    except Exception:
        pass

    # ── Load EMA state ──
    ema_index = {}
    ema_comp = {}
    if EMA_CACHE_FILE.exists():
        try:
            raw = json.loads(EMA_CACHE_FILE.read_text())
            ema_index = raw.get("ema_index", {})
            ema_comp = raw.get("ema_comp", {})
        except Exception:
            pass

    if not ema_index:
        try:
            result = _subprocess.run(
                ["curl", "-s", f"http://localhost:{server_http_port}/ema"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                live_ema = json.loads(result.stdout).get("data", {})
                for idx_id, row in live_ema.items():
                    ema_index[idx_id] = {f: row.get(f) for f in EMA_INDEX_FIELDS if row.get(f) is not None}
        except Exception:
            pass

    # ── Get index list ──
    from fetcher import get_indexes, fetch_markets_for_coin, load_exchange_scores, CACHE_DIR as _CACHE_DIR
    indexes = get_indexes()

    # ── Filter by specified indexes ──
    if index_ids:
        idx_set = {iid.upper() for iid in index_ids}
        indexes = [idx for idx in indexes if idx.upper() in idx_set]

    # ── PRE-FILTER using EMA data (before any expensive fetches) ──
    # When running full review (no specific index_ids), skip healthy indexes early
    # so we don't waste time fetching snapshots/markets for them.
    total_all = len(indexes)
    skipped_healthy = 0
    if not index_ids:
        pre_filtered = []
        for idx in indexes:
            base = idx.split("-", 1)[0].upper()
            at = asset_map.get(base, "Altcoins")

            # Apply asset type filter early
            if asset_type and at.lower() != asset_type.lower():
                continue

            ema = ema_index.get(idx, {})
            ema_avg = ema.get("ema_avg_deviation")
            ema_max = ema.get("ema_max_deviation")
            stale = ema.get("ema_stale_ratio")
            # Estimate component count from EMA comp keys
            prefix = f"{idx}|"
            comp_count = sum(1 for k in ema_comp if k.startswith(prefix))

            if at == "Topcoins":
                # Skip if deviation is healthy and has enough components
                # (stale_ratio is often inflated by server restarts, so don't gate on it)
                if (ema_avg is not None and ema_avg < 0.15
                        and ema_max is not None and ema_max < 0.3
                        and comp_count >= 5):
                    skipped_healthy += 1
                    continue
            elif at == "Fiat":
                if (ema_avg is not None and ema_avg < 0.1
                        and ema_max is not None and ema_max < 0.3
                        and comp_count >= 3):
                    skipped_healthy += 1
                    continue

            pre_filtered.append(idx)
        indexes = pre_filtered
        if skipped_healthy:
            click.echo(f"  Skipped {skipped_healthy} healthy Topcoins/Fiat indexes", err=True)
    elif asset_type:
        indexes = [idx for idx in indexes
                   if asset_map.get(idx.split("-", 1)[0].upper(), "Altcoins").lower() == asset_type.lower()]

    # ── Apply batch pagination (before expensive fetches) ──
    total_flagged = len(indexes)
    if batch_offset > 0:
        indexes = indexes[batch_offset:]
    if batch > 0:
        indexes = indexes[:batch]

    click.echo(f"  Processing {len(indexes)} indexes (of {total_flagged} flagged, {total_all} total)", err=True)

    # ── Fetch detailed snapshots (only for batch) ──
    detailed_snapshots = {}
    if _server_live:
        for idx in indexes:
            try:
                result = _subprocess.run(
                    ["curl", "-s", f"http://localhost:{server_http_port}/snapshot/{idx}"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    detail = json.loads(result.stdout)
                    if "components" in detail:
                        detailed_snapshots[idx] = detail
            except Exception:
                pass

    # ── Load alternative markets (only for coins in batch) ──
    SKIP_COINS = {"USDT", "USDC", "USD", "EUR", "TRY", "BRL", "AUD", "AED", "SGD"}
    unique_coins = sorted(set(idx.split("-", 1)[0].upper() for idx in indexes))
    explicitly_requested = {iid.split("-", 1)[0].upper() for iid in index_ids} if index_ids else set()
    coins_to_fetch = [c for c in unique_coins if c not in SKIP_COINS or c in explicitly_requested]

    def _load_markets_cached(coin: str) -> list[dict]:
        """Read market cache file. Returns cached data if exists (any age), else fetches."""
        cache_file = _CACHE_DIR / f"{coin}_markets.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                markets = data.get("markets", [])
                if markets:
                    age_h = (time.time() - data.get("ts", 0)) / 3600
                    if age_h > 24:
                        click.echo(f"    [cache] {coin}: stale ({age_h:.0f}h old), using anyway", err=True)
                    return markets
            except (json.JSONDecodeError, KeyError):
                pass
        # No cache — must fetch
        click.echo(f"    [fetch] {coin}: no cache, fetching from CMC...", err=True)
        return fetch_markets_for_coin(coin, quiet=True)

    alt_by_coin: dict[str, list[dict]] = {}
    ex_scores = load_exchange_scores()
    for coin in coins_to_fetch:
        try:
            markets = _load_markets_cached(coin)
            alts = []
            for m in markets:
                if not m.get("supported"):
                    continue
                if m.get("outlier_detected") or m.get("price_excluded"):
                    continue
                alt = {
                    "exchange": m["exchange"],
                    "symbol": m.get("symbol", ""),
                    "category": m.get("category", ""),
                    "exchange_score": m.get("exchange_score", 0),
                    "volume_usd": m.get("volume_usd"),
                    "depth_minus2_pct": m.get("depth_minus2_pct"),
                    "depth_plus2_pct": m.get("depth_plus2_pct"),
                }
                if m.get("subscribeName"):
                    alt["subscribeName"] = m["subscribeName"]
                if m.get("category") == "perpetual":
                    alt["open_interest_usd"] = m.get("open_interest_usd")
                alts.append(alt)
            alt_by_coin[coin] = alts
        except Exception as e:
            click.echo(f"    [warn] {coin}: {e}", err=True)
            alt_by_coin[coin] = []

    # ── Build and write File C (JSON) ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_c = REVIEW_DIR / f"review_data_{ts}.json"

    rows = []
    for idx in indexes:
        parts = idx.split("-", 1)
        base = parts[0].upper()
        quote = parts[1] if len(parts) > 1 else ""
        assets_type = asset_map.get(base, "Altcoins")

        snap = snapshot_data.get(idx, {})
        ema = ema_index.get(idx, {})

        detail = detailed_snapshots.get(idx, {})
        snap_comps = detail.get("components", [])

        ema_comp_lookup = {}
        prefix = f"{idx}|"
        for comp_key, comp_ema in ema_comp.items():
            if comp_key.startswith(prefix):
                exch_sym = comp_key[len(prefix):]
                ema_comp_lookup[exch_sym] = comp_ema

        comp_list = []
        if snap_comps:
            for c in snap_comps:
                exchange = c.get("exchange", "")
                symbol = c.get("symbol", "")
                comp_row = {
                    "exchange": exchange,
                    "symbol": symbol,
                    "weight": c.get("weight"),
                    "symPx": c.get("symPx"),
                    "cnvPx": c.get("cnvPx"),
                    "deviation_pct": c.get("deviation_pct"),
                }
                ema_key = f"{exchange}:{symbol}"
                if ema_key in ema_comp_lookup:
                    for f in EMA_COMP_FIELDS:
                        v = ema_comp_lookup[ema_key].get(f)
                        comp_row[f] = round(v, 6) if v is not None else None
                comp_list.append(comp_row)
        else:
            for comp_key, comp_ema in ema_comp.items():
                if not comp_key.startswith(prefix):
                    continue
                exch_sym = comp_key[len(prefix):]
                comp_parts = exch_sym.split(":", 1)
                comp_row = {
                    "exchange": comp_parts[0] if comp_parts else "",
                    "symbol": comp_parts[1] if len(comp_parts) > 1 else "",
                }
                for f in EMA_COMP_FIELDS:
                    v = comp_ema.get(f)
                    comp_row[f] = round(v, 6) if v is not None else None
                comp_list.append(comp_row)

        row = {
            "index": idx,
            "baseCoin": base,
            "quoteCcy": quote,
            "assetsType": assets_type,
            "component_count": snap.get("component_count", len(comp_list)),
            "idxPx": snap.get("idxPx", ""),
            "ema_avg_deviation": round(ema["ema_avg_deviation"], 6) if "ema_avg_deviation" in ema else None,
            "ema_max_deviation": round(ema["ema_max_deviation"], 6) if "ema_max_deviation" in ema else None,
            "ema_avg_update_lag": round(ema["ema_avg_update_lag"], 2) if "ema_avg_update_lag" in ema else None,
            "ema_stale_ratio": round(ema["ema_stale_ratio"], 2) if "ema_stale_ratio" in ema else None,
            "components": comp_list,
            "alternatives": alt_by_coin.get(base, []),
        }
        rows.append(row)

    file_c.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    # ── Output ──
    result = {
        "status": "ok",
        "file_a": str(file_a),
        "file_b": str(file_b),
        "file_c": str(file_c),
        "file_b_exists": file_b.exists(),
        "indexes_in_batch": len(rows),
        "total_flagged": total_flagged,
        "total_indexes": total_all,
        "ema_coverage": sum(1 for idx in indexes if idx in ema_index),
        "snapshot_coverage": sum(1 for idx in indexes if idx in snapshot_data),
    }
    if batch > 0 and total_flagged > batch_offset + len(rows):
        result["next_offset"] = batch_offset + len(rows)
        result["remaining"] = total_flagged - (batch_offset + len(rows))
    _out(result)


if __name__ == "__main__":
    cli()
