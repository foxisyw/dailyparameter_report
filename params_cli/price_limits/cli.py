#!/usr/bin/env python3
"""OKX Price Limits CLI — agent-friendly interface.

JSON on stdout, progress/status on stderr.
Shows hints on first call; results on subsequent calls within 5 minutes.
"""

import json
import re
import sys
import time
from pathlib import Path

import click

from fetcher import (
    get_all_instruments,
    get_xyz_cap_params,
    get_xyz_cap_for_instrument,
    refresh_cache,
    generate_adjustment_file,
    CACHE_DIR,
)

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
                "status": "hints",
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


# ─────────────── CLI ───────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """OKX Price Limits CLI — fetch instruments and XYZ cap parameters."""
    if ctx.invoked_subcommand is None:
        hints = _get_hints("default")
        if hints:
            click.echo(hints)
        else:
            click.echo(ctx.get_help())


@cli.command("params")
@click.argument("inst_id", required=False)
@click.option("--type", "inst_type", type=click.Choice(["SPOT", "SWAP", "FUTURES", "all"], case_sensitive=False), default="all")
@click.option("--limit", default=0, help="Max rows (0=all)")
def params_cmd(inst_id: str | None, inst_type: str, limit: int):
    """Fetch XYZ cap parameters for instruments."""
    if _check_hints("params"):
        return

    if inst_id:
        data = get_xyz_cap_for_instrument(inst_id)
        if data is None:
            _error(f"No XYZ cap data found for {inst_id}")
        _out({"status": "ok", "count": 1, "data": [data]})
        return

    data = get_xyz_cap_params()
    if inst_type.lower() != "all":
        data = [d for d in data if d["instType"] == inst_type.upper()]
    if limit > 0:
        data = data[:limit]
    _out({"status": "ok", "count": len(data), "data": data})


@cli.command("search")
@click.argument("query", required=False, default=None)
@click.option("--limit", default=20, help="Max results (default: 20)")
def search_cmd(query: str | None, limit: int):
    """Search instruments by query string."""
    if _check_hints("search"):
        return

    if not query:
        _error("Missing query argument. Usage: ./cli.py search \"BTC SWAP\"")

    tokens = [t.upper() for t in re.split(r"[^a-zA-Z0-9]+", query) if t]
    if not tokens:
        _error("Empty query")

    # Build asset type map for matching
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

    instruments = get_all_instruments()
    results = []
    for inst in instruments:
        if inst.get("state") != "live":
            continue
        base = inst["instId"].split("-")[0].upper()
        assets_type = asset_map.get(base, "Altcoins")
        match_str = f"{inst['instId']}-{inst['instType']}-{assets_type}".upper()
        if all(token in match_str for token in tokens):
            results.append({
                "instId": inst["instId"],
                "instType": inst["instType"],
                "assetsType": assets_type,
            })
    if limit > 0:
        results = results[:limit]
    _out({"status": "ok", "query": query, "tokens": tokens, "count": len(results), "data": results})


@cli.command("refresh-cache")
@click.argument("inst_ids", nargs=-1)
@click.option("--type", "inst_type", type=click.Choice(["SPOT", "SWAP", "FUTURES"], case_sensitive=False), default=None)
def refresh_cache_cmd(inst_ids: tuple[str, ...], inst_type: str | None):
    """Clear and re-fetch cached data. Optionally filter by instrument IDs or type."""
    if _check_hints("refreshCache"):
        return
    result = refresh_cache(
        inst_ids=list(inst_ids) if inst_ids else None,
        inst_type=inst_type.upper() if inst_type else None,
    )
    _out({"status": "ok", "results": result})


@cli.command("generate-adjustment")
@click.argument("adjustments_json", required=False, default=None)
def generate_adjustment_cmd(adjustments_json: str | None):
    """Generate price limit adjustment CSV from a JSON array.

    Example: ./cli.py generate-adjustment '[{"symbol":"BTC-USDT-SWAP","z_upper":30}]'
    """
    if _check_hints("generateAdjustment"):
        return

    if not adjustments_json:
        _error("Missing JSON argument. Usage: ./cli.py generate-adjustment '[{\"symbol\":\"BTC-USDT-SWAP\",\"z_upper\":30}]'")
    try:
        adjustments = json.loads(adjustments_json)
    except json.JSONDecodeError as e:
        _error(f"Invalid JSON: {e}")
    if not isinstance(adjustments, list):
        _error("Argument must be a JSON array")
    for adj in adjustments:
        if "symbol" not in adj:
            _error(f"Each item must have a 'symbol' key, got: {adj}")
    result = generate_adjustment_file(adjustments)
    _out({"status": "ok", **result})


@cli.command("config")
@click.argument("key", required=False)
@click.argument("value", required=False)
def config_cmd(key: str | None, value: str | None):
    """Get or set CLI configuration.

    Without arguments: show all config.
    With KEY: show that key's value.
    With KEY VALUE: set the key.

    Supported keys:
        lark_webhook_url    — Lark bot webhook URL for price limit alerts
        alert_threshold     — Buffer alert threshold (default: 0.02 = 2%)
        alert_cooldown      — Seconds between re-alerting same instrument (default: 3600)
    """
    from realtime_server import load_config, save_config

    config = load_config()

    if key is None:
        # Show all config
        if not config:
            _out({"status": "ok", "message": "No config set. Use: ./cli.py config <key> <value>", "data": {}})
        else:
            _out({"status": "ok", "data": config})
        return

    key = key.lower().strip()

    if value is None:
        # Get single key
        v = config.get(key)
        if v is None:
            _out({"status": "ok", "key": key, "value": None, "message": f"'{key}' is not set."})
        else:
            _out({"status": "ok", "key": key, "value": v})
        return

    # Set key
    VALID_KEYS = {"lark_webhook_url", "alert_threshold", "alert_cooldown"}
    if key not in VALID_KEYS:
        _error(f"Unknown config key '{key}'. Valid keys: {', '.join(sorted(VALID_KEYS))}")

    # Type coercion for numeric keys
    if key in ("alert_threshold", "alert_cooldown"):
        try:
            value = float(value)
        except ValueError:
            _error(f"'{key}' must be a number, got: {value}")

    config[key] = value
    save_config(config)
    _out({"status": "ok", "message": f"Set '{key}'.", "key": key, "value": value})


@cli.command("realtime")
@click.option("--port", default=8765, help="WebSocket port (HTTP on port+1)")
@click.option("--interval", default=5.0, help="Polling interval in seconds")
@click.option("--types", default="SWAP,SPOT,FUTURES", help="Instrument types to monitor")
@click.option("--stop", is_flag=True, help="Stop a running server")
def realtime_cmd(port: int, interval: float, types: str, stop: bool):
    """Start real-time price-limit monitor server (WebSocket + HTTP).

    Detects if server is already running — if so, returns the connection links.
    Use --stop to shut down a running server.
    """
    import os
    import signal
    from realtime_server import read_server_status, main as rt_main

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

    if existing:
        hp = existing['http_port']
        _out({
            "status": "already_running",
            "pid": existing["pid"],
            "websocket": f"ws://localhost:{existing['port']}",
            "http": f"http://localhost:{hp}",
            "endpoints": {
                "snapshot": f"http://localhost:{hp}/snapshot",
                "instrument": f"http://localhost:{hp}/snapshot/{{instId}}",
                "ema": f"http://localhost:{hp}/ema",
                "ema_instrument": f"http://localhost:{hp}/ema/{{instId}}",
                "ema_search": f"http://localhost:{hp}/ema?q={{query}}",
                "search": f"http://localhost:{hp}/search?q={{query}}",
                "alerts": f"http://localhost:{hp}/alerts",
                "health": f"http://localhost:{hp}/health",
            },
            "instruments": existing.get("instruments", 0),
            "message": "Server is already running. Use --stop to shut it down.",
        })
        return

    # Spawn server as a detached background process
    import subprocess
    server_script = str(Path(__file__).parent / "realtime_server.py")
    log_file = str(Path(__file__).parent / "cache" / "realtime_server.log")

    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            [
                sys.executable, server_script,
                "--port", str(port),
                "--interval", str(interval),
                "--types", types,
            ],
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,  # detach from terminal
        )

    # Wait a moment for the server to start, then verify
    import time as _time
    http_port = port + 1
    for _ in range(20):
        _time.sleep(1)
        status = read_server_status(port)
        if status and status.get("instruments", 0) > 0:
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
                "instrument": f"http://localhost:{http_port}/snapshot/{{instId}}",
                "ema": f"http://localhost:{http_port}/ema",
                "ema_instrument": f"http://localhost:{http_port}/ema/{{instId}}",
                "ema_search": f"http://localhost:{http_port}/ema?q={{query}}",
                "search": f"http://localhost:{http_port}/search?q={{query}}",
                "alerts": f"http://localhost:{http_port}/alerts",
                "health": f"http://localhost:{http_port}/health",
            },
            "instruments": status.get("instruments", 0),
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


@cli.command("ema")
@click.argument("inst_ids", nargs=-1)
@click.option("--type", "inst_type", type=click.Choice(["SPOT", "SWAP", "FUTURES", "all"], case_sensitive=False), default="all")
@click.option("--port", default=8765, help="Server WebSocket port (HTTP on port+1)")
def ema_cmd(inst_ids: tuple[str, ...], inst_type: str, port: int):
    """Query EMA values from the running realtime server.

    Reads from the live server if running, otherwise falls back to the
    cached EMA state on disk.

    Examples:
        ./cli.py ema                          # all instruments
        ./cli.py ema BTC-USDT-SWAP            # specific instrument(s)
        ./cli.py ema --type SWAP              # filter by type
    """
    import httpx as _httpx
    from realtime_server import (
        read_server_status,
        EMA_CACHE_FILE,
        EMA_FIELDS,
    )

    http_port = port + 1
    source = None
    data = {}

    # Try live server first
    server = read_server_status(port)
    if server:
        try:
            if inst_ids:
                # Fetch each instrument individually and merge
                for iid in inst_ids:
                    resp = _httpx.get(f"http://localhost:{http_port}/ema/{iid}", timeout=5)
                    if resp.status_code == 200:
                        row = resp.json()
                        data[iid] = row
                    else:
                        print(f"  [warn] no EMA data for {iid}", file=sys.stderr)
            else:
                q = "" if inst_type.lower() == "all" else ""
                resp = _httpx.get(f"http://localhost:{http_port}/ema", timeout=10)
                if resp.status_code == 200:
                    body = resp.json()
                    data = body.get("data", {})
            source = "live"
        except Exception as e:
            print(f"  [warn] live server query failed: {e}, falling back to cache", file=sys.stderr)

    # Fall back to cached EMA file
    if not data:
        if EMA_CACHE_FILE.exists():
            try:
                cache = json.loads(EMA_CACHE_FILE.read_text())
                raw_state = cache.get("ema_state", {})
                raw_ts = cache.get("ema_ts", {})
                # Format like get_ema_snapshot
                for inst_id, ema in raw_state.items():
                    row = {"instId": inst_id}
                    for field in EMA_FIELDS:
                        v = ema.get(field)
                        if v is not None:
                            row[field] = round(v, 8)
                            row[f"{field}_pct"] = round(v * 100, 4)
                        else:
                            row[field] = None
                            row[f"{field}_pct"] = None
                    if inst_id in raw_ts:
                        row["ema_updated"] = raw_ts[inst_id]
                    data[inst_id] = row
                source = "cache"
                if inst_ids:
                    data = {k: v for k, v in data.items() if k in inst_ids}
            except Exception as e:
                _error(f"Failed to read EMA cache: {e}")
        else:
            _error("No running server and no EMA cache found. Start the server with: ./cli.py realtime")

    # Filter by instType if needed (need snapshot data for type info)
    if inst_type.lower() != "all" and not inst_ids:
        target = inst_type.upper()
        if source == "live" and server:
            # Fetch snapshot to get instType mapping
            try:
                resp = _httpx.get(f"http://localhost:{http_port}/snapshot", timeout=10)
                if resp.status_code == 200:
                    snap = resp.json().get("data", {})
                    typed_ids = {k for k, v in snap.items() if v.get("instType") == target}
                    data = {k: v for k, v in data.items() if k in typed_ids}
            except Exception:
                pass
        else:
            # Best-effort filter from instId patterns
            # SWAP: XXX-YYY-SWAP, FUTURES: XXX-YYY-YYMMDD, SPOT: XXX-YYY
            def _guess_type(iid: str) -> str:
                parts = iid.split("-")
                if len(parts) == 3 and parts[2] == "SWAP":
                    return "SWAP"
                if len(parts) == 3 and parts[2].isdigit():
                    return "FUTURES"
                if len(parts) == 2:
                    return "SPOT"
                return ""
            data = {k: v for k, v in data.items() if _guess_type(k) == target}

    _out({
        "status": "ok",
        "source": source,
        "count": len(data),
        "data": data,
    })


@cli.command("review")
@click.argument("inst_ids", nargs=-1)
def review_cmd(inst_ids: tuple[str, ...]):
    """Prepare data for price limit parameter review.

    Optionally pass instrument IDs to scope the review to specific instruments.

    First call: outputs hints (workflow instructions).
    Second call: generates data source file and outputs file paths.
    """
    if _check_hints("review"):
        return

    import hashlib
    from datetime import datetime

    BASE_DIR = Path(__file__).parent
    REVIEW_DIR = BASE_DIR / "review"
    ASSETS_FILE = BASE_DIR / "assets_types.md"
    XYZ_CACHE = CACHE_DIR / "xyz_cap_params.json"
    EMA_CACHE = CACHE_DIR / "ema_state.json"

    # ── File A: methodology (static) ──
    file_a = BASE_DIR / "review_methodology.md"
    if not file_a.exists():
        _error(f"Review methodology file not found: {file_a}")

    # ── File B: script path (hash-based name, not generated here) ──
    methodology_content = file_a.read_text()
    short_hash = hashlib.sha256(methodology_content.encode()).hexdigest()[:8]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    file_b = REVIEW_DIR / f"{short_hash}.py"

    # Always remove the script so agent regenerates it fresh each run
    if file_b.exists():
        file_b.unlink()

    # ── Parse assets_types.md ──
    asset_map: dict[str, str] = {}  # base currency -> asset type
    if ASSETS_FILE.exists():
        current_type = ""
        for line in ASSETS_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("# "):
                current_type = line[2:].strip()
            elif line and current_type:
                asset_map[line.upper()] = current_type

    # ── Load XYZ cap params ──
    if not XYZ_CACHE.exists():
        _error("XYZ cap params cache not found. Run: ./cli.py refresh-cache")
    xyz_list = json.loads(XYZ_CACHE.read_text())
    xyz_map = {r["instId"]: r for r in xyz_list}

    # ── Load EMA state ──
    ema_data = {}
    ema_saved_at = None
    if EMA_CACHE.exists():
        raw = json.loads(EMA_CACHE.read_text())
        ema_data = raw.get("ema_state", {})
        ema_saved_at = raw.get("saved_at")

    # ── Resolve asset type for an instId ──
    def _get_asset_type(inst_id: str) -> str:
        base = inst_id.split("-")[0].upper()
        if base in asset_map:
            return asset_map[base]
        return "Altcoins"

    # ── Filter by specified instruments ──
    if inst_ids:
        inst_id_set = {iid.upper() for iid in inst_ids}
        xyz_map = {k: v for k, v in xyz_map.items() if k.upper() in inst_id_set}

    # ── Build and write File C (CSV) ──
    import csv
    import io

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_c = REVIEW_DIR / f"review_data_{ts}.csv"

    fieldnames = [
        "instType", "instId", "upper_Y_cap", "lower_Y_cap",
        "upper_Z_cap", "lower_Z_cap", "assetsType",
        "basis_ema", "spread_ema", "limitUp_buffer_ema", "limitDn_buffer_ema",
        "volCcy24h_ema",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()

    rows = []
    for inst_id, xyz in xyz_map.items():
        ema = ema_data.get(inst_id, {})
        asset_type = _get_asset_type(inst_id)

        def _fmt(v):
            if v is None:
                return ""
            return f"{v * 100:.4f}%"

        vol_ccy = ema.get("volCcy24h")
        vol_ccy_str = "" if vol_ccy is None else f"{vol_ccy:.2f}"

        row = {
            "instType": xyz.get("instType", ""),
            "instId": inst_id,
            "upper_Y_cap": xyz.get("upper_Y_cap", ""),
            "lower_Y_cap": xyz.get("lower_Y_cap", ""),
            "upper_Z_cap": xyz.get("upper_Z_cap", ""),
            "lower_Z_cap": xyz.get("lower_Z_cap", ""),
            "assetsType": asset_type,
            "basis_ema": _fmt(ema.get("basis")),
            "spread_ema": _fmt(ema.get("spread")),
            "limitUp_buffer_ema": _fmt(ema.get("limitUp_buffer")),
            "limitDn_buffer_ema": _fmt(ema.get("limitDn_buffer")),
            "volCcy24h_ema": vol_ccy_str,
        }
        writer.writerow(row)
        rows.append(row)

    file_c.write_text(buf.getvalue())

    # ── Output ──
    _out({
        "status": "ok",
        "file_a": str(file_a),
        "file_b": str(file_b),
        "file_c": str(file_c),
        "file_b_exists": file_b.exists(),
        "instruments": len(rows),
        "ema_coverage": sum(1 for iid in xyz_map if iid in ema_data),
    })


if __name__ == "__main__":
    cli()
