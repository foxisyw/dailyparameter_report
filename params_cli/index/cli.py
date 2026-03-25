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
            "Monitor": "server → (subscribe via WS/HTTP endpoints)",
            "QuickCheck": "snapshot [INDEX]",
            "ReviewComponents": "markets COIN → generate-adjustment JSON",
        },
        "methods": {
            "help": "Show workflows and method list",
            "indexes": "List all real OKX indexes (derived from instruments)",
            "server": "Start/stop/check the index deviation monitor server",
            "snapshot": "Quick one-shot fetch of current index quality (no server needed)",
            "markets": "Fetch component alternatives for a coin from CoinGecko",
            "generate-adjustment": "Generate index_components CSV from selected components",
            "refresh-cache": "Clear cached data and re-fetch",
        },
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

    click.echo("Fetching index tickers...", err=True)
    tickers = {}
    for quote_ccy in ("USDT", "USDC"):
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
@click.option("--supported-only", is_flag=True, default=True, help="Only show supported exchanges (default)")
@click.option("--all", "show_all", is_flag=True, help="Show all exchanges including unsupported")
@click.option("--limit", default=0, help="Max results (0=all)")
@click.option("--recommend", is_flag=True, help="Show recommended top-5 components")
def markets_cmd(coin: str, supported_only: bool, show_all: bool, limit: int, recommend: bool):
    """Fetch component alternatives for a coin from CoinGecko.

    Returns available markets across exchanges with quality metrics
    (volume, B/A spread, trust score, etc).
    """
    if _check_hints("markets"):
        return

    from fetcher import fetch_markets_for_coin, recommend_components, load_exchange_scores

    coin = coin.upper()
    click.echo(f"Fetching markets for {coin}...", err=True)

    if recommend:
        selected = recommend_components(coin)
        if not selected:
            _error(f"No supported markets found for {coin}")
        _out({
            "status": "ok",
            "coin": coin,
            "count": len(selected),
            "recommended": [
                {
                    "exchange": m["exchange"],
                    "pair": m["pair"],
                    "volume_usd": m.get("volume_usd", ""),
                    "bid_ask_spread_pct": m.get("bid_ask_spread_pct", ""),
                    "trust_score": m.get("trust_score", ""),
                    "last_price": m.get("last_price", ""),
                }
                for m in selected
            ],
        })
        return

    markets = fetch_markets_for_coin(coin)
    if not markets:
        _error(f"No markets found for {coin}. Coin may not be on CoinGecko.")

    if not show_all:
        markets = [m for m in markets if m["supported"]]

    # Sort by volume descending
    markets.sort(key=lambda m: float(m.get("volume_usd") or 0), reverse=True)

    if limit > 0:
        markets = markets[:limit]

    exchange_scores = load_exchange_scores()

    _out({
        "status": "ok",
        "coin": coin,
        "count": len(markets),
        "data": [
            {
                "exchange": m["exchange"],
                "pair": m["pair"],
                "supported": m["supported"],
                "exchange_score": exchange_scores.get(m["exchange"], 0),
                "last_price": m.get("last_price", ""),
                "price_usd": m.get("price_usd", ""),
                "volume": m.get("volume", ""),
                "volume_usd": m.get("volume_usd", ""),
                "bid_ask_spread_pct": m.get("bid_ask_spread_pct", ""),
                "trust_score": m.get("trust_score", ""),
                "is_anomaly": m.get("is_anomaly", False),
                "is_stale": m.get("is_stale", False),
                "last_traded_at": m.get("last_traded_at", ""),
            }
            for m in markets
        ],
    })


@cli.command("generate-adjustment")
@click.argument("components_json")
def generate_adjustment_cmd(components_json: str):
    """Generate index_components CSV from selected components.

    Input JSON array where each item has:
      - index: "BTC-USD"
      - components: [{"exchange": "Binance", "pair": "BTC-USDT"}, ...]

    Example:
      python3 cli.py generate-adjustment '[
        {"index":"BTC-USD","components":[
          {"exchange":"Binance","pair":"BTC-USDT"},
          {"exchange":"Coinbase","pair":"BTC-USD"},
          {"exchange":"OKX","pair":"BTC-USDT"}
        ]},
        {"index":"ETH-USDT","components":[
          {"exchange":"Binance","pair":"ETH-USDT"},
          {"exchange":"OKX","pair":"ETH-USDT"}
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
    for name in ["indexes.json", "coingecko_coins_list.json"]:
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


if __name__ == "__main__":
    cli()
