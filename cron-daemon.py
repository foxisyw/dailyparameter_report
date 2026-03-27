#!/usr/bin/env python3
"""Lightweight cron daemon — replaces macOS launchd.

Runs in the background, writes a trigger file at 9:30 AM HKT daily.
The Claude Code /loop watcher picks it up and runs the full pipeline.

Usage:
  python3 cron-daemon.py          # run in foreground
  nohup python3 cron-daemon.py &  # run in background (survives terminal close)

Stop: kill $(cat /tmp/paramreview-daemon.pid)
"""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import httpx
except ImportError:
    httpx = None

HKT = ZoneInfo("Asia/Hong_Kong")
TRIGGER_HOUR = 9
TRIGGER_MINUTE = 30
WORKDIR = Path(__file__).resolve().parent
TRIGGER_FILE = WORKDIR / "runner" / "local" / ".cron_trigger"
INPUT_FILE = WORKDIR / "runner" / "local" / "risk_intel_input.json"
PID_FILE = Path("/tmp/paramreview-daemon.pid")
LOG_FILE = Path("/tmp/paramreview-cron.log")

# Server configurations
SERVERS = [
    {
        "name": "PriceLimit",
        "script": WORKDIR / "params_cli" / "price_limits" / "realtime_server.py",
        "port": 8765,
        "http_port": 8766,
        "health": "/health",
        "pid_file": Path("/tmp/pricelimit-server.pid"),
        "log_file": Path("/tmp/pricelimit-server.log"),
    },
    {
        "name": "Index",
        "script": WORKDIR / "params_cli" / "index" / "server.py",
        "port": 8785,
        "http_port": 8786,
        "health": "/health",
        "pid_file": Path("/tmp/index-server.pid"),
        "log_file": Path("/tmp/index-server.log"),
    },
]


def log(msg: str):
    ts = datetime.now(HKT).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[daemon] {ts} HKT — {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def check_server_health(server: dict) -> bool:
    """Check if a server is responding on its HTTP health endpoint."""
    url = f"http://localhost:{server['http_port']}{server['health']}"
    if httpx:
        try:
            resp = httpx.get(url, timeout=3)
            return resp.status_code == 200
        except Exception:
            return False
    else:
        import urllib.request
        try:
            req = urllib.request.urlopen(url, timeout=3)
            return req.status == 200
        except Exception:
            return False


def ensure_server_running(server: dict):
    """Start a server if it's not responding to health checks."""
    if check_server_health(server):
        return

    log(f"Starting {server['name']} server (port {server['port']})...")
    proc = subprocess.Popen(
        [sys.executable, str(server["script"]), "--port", str(server["port"])],
        stdout=open(server["log_file"], "a"),
        stderr=subprocess.STDOUT,
        cwd=str(server["script"].parent),
    )
    server["pid_file"].write_text(str(proc.pid))
    log(f"{server['name']} server started (PID {proc.pid})")

    # Wait up to 15s for health
    for _ in range(15):
        time.sleep(1)
        if check_server_health(server):
            log(f"{server['name']} server healthy")
            return
    log(f"WARNING: {server['name']} server not healthy after 15s")


def ensure_all_servers():
    """Make sure all data servers are running."""
    for server in SERVERS:
        ensure_server_running(server)


def write_trigger():
    """Delete stale input and write today's trigger file."""
    # Delete yesterday's stale input
    if INPUT_FILE.exists():
        INPUT_FILE.unlink()
        log("Deleted stale risk_intel_input.json")

    # Write trigger
    date_str = datetime.now(HKT).strftime("%Y-%m-%d")
    TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRIGGER_FILE.write_text(date_str + "\n")
    log(f"Trigger written: {date_str}")


def main():
    # Write PID file
    PID_FILE.write_text(str(os.getpid()))
    log(f"Daemon started (PID {os.getpid()}). Trigger at {TRIGGER_HOUR:02d}:{TRIGGER_MINUTE:02d} HKT daily.")

    # Start servers on daemon startup
    ensure_all_servers()

    # Handle graceful shutdown
    def shutdown(signum, frame):
        log("Daemon stopped.")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    triggered_today = False
    last_health_check = 0

    while True:
        now = datetime.now(HKT)

        # Reset at midnight
        if now.hour == 0 and now.minute == 0:
            triggered_today = False

        # Health check servers every 5 minutes
        if time.time() - last_health_check > 300:
            ensure_all_servers()
            last_health_check = time.time()

        # Fire at target time
        if now.hour == TRIGGER_HOUR and now.minute == TRIGGER_MINUTE and not triggered_today:
            log(f"=== Daily trigger firing at {now.strftime('%H:%M')} HKT ===")
            ensure_all_servers()  # Make sure servers are up before trigger
            write_trigger()
            triggered_today = True

        # Sleep 30 seconds between checks
        time.sleep(30)


if __name__ == "__main__":
    main()
