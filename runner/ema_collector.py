"""EMA data collector — starts realtime server, waits for coverage, stops it.

Usage:
    python -m runner.ema_collector --timeout 900
"""

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REALTIME_SERVER = PROJECT_ROOT / "params_cli" / "price_limits" / "realtime_server.py"
EMA_CACHE = PROJECT_ROOT / "params_cli" / "price_limits" / "cache" / "ema_state.json"
HEALTH_URL = "http://127.0.0.1:8765/health"
POLL_INTERVAL = 30  # seconds
COVERAGE_THRESHOLD = 0.80  # 80%


def _log(msg: str):
    print(f"  [ema-collector] {msg}", file=sys.stderr)


def _check_health() -> dict | None:
    """Poll the realtime server health endpoint.

    Returns the JSON body on success, or None on failure.
    """
    try:
        req = Request(HEALTH_URL, headers={"User-Agent": "ema-collector/1.0"})
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError):
        return None


def collect(timeout: int = 900) -> dict:
    """Start the realtime server, wait for EMA coverage, return EMA data.

    Parameters
    ----------
    timeout : int
        Maximum seconds to wait for EMA coverage to reach the threshold.

    Returns
    -------
    dict
        The ``ema_state`` dict from ema_state.json, keyed by instId.
    """
    if not REALTIME_SERVER.exists():
        _log(f"Realtime server not found at {REALTIME_SERVER}")
        _log("Falling back to cached EMA data...")
        return _load_cached()

    _log(f"Starting realtime server: {REALTIME_SERVER}")
    proc = subprocess.Popen(
        [sys.executable, str(REALTIME_SERVER)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            elapsed = int(time.monotonic() - start)
            health = _check_health()

            if health is not None:
                coverage = health.get("ema_coverage", 0)
                total = health.get("total_instruments", 0)
                covered = health.get("ema_instruments", 0)
                _log(
                    f"[{elapsed}s] EMA coverage: {covered}/{total} "
                    f"({coverage * 100:.1f}%)"
                )

                if total > 0 and coverage >= COVERAGE_THRESHOLD:
                    _log("Coverage threshold reached!")
                    break
            else:
                _log(f"[{elapsed}s] Server not ready yet...")

            time.sleep(POLL_INTERVAL)
        else:
            _log(f"Timeout after {timeout}s — proceeding with available data")

    finally:
        _log("Stopping realtime server...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        _log("Server stopped.")

    return _load_cached()


def _load_cached() -> dict:
    """Load ema_state.json from disk."""
    if not EMA_CACHE.exists():
        _log(f"No EMA cache at {EMA_CACHE}")
        return {}
    try:
        raw = json.loads(EMA_CACHE.read_text())
        ema = raw.get("ema_state", {})
        _log(f"Loaded EMA data for {len(ema)} instruments")
        return ema
    except Exception as exc:
        _log(f"Failed to load EMA cache: {exc}")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Collect EMA data from realtime server")
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Max seconds to wait for EMA coverage (default: 900)",
    )
    args = parser.parse_args()

    ema_data = collect(timeout=args.timeout)
    # Print summary
    print(json.dumps({
        "instruments": len(ema_data),
        "status": "ok" if ema_data else "empty",
    }))


if __name__ == "__main__":
    main()
