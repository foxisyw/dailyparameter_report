"""Send Lark notification from the latest committed report.

Does NOT run any review — just reads public/data/reports/latest.json,
loads the full report, and sends the Lark card.

Usage:
    python -m runner.notify_lark
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "public" / "data"


def _log(msg: str):
    print(f"  [notify] {msg}", file=sys.stderr)


def main():
    from . import lark

    # Find latest report
    latest_path = DATA_DIR / "reports" / "latest.json"
    if not latest_path.exists():
        _log(f"No latest.json at {latest_path} — nothing to send")
        return 1

    latest = json.loads(latest_path.read_text())
    date_str = latest["date"]
    _log(f"Latest report: {date_str}")

    # Load full report
    report_path = DATA_DIR / "reports" / date_str / "report.json"
    if not report_path.exists():
        _log(f"Report not found at {report_path}")
        return 1

    data = json.loads(report_path.read_text())
    report = data["report"]
    chapters = data["chapters"]

    _log(f"Status: {report['status']}, issues: {report['total_issues']}")

    # Send
    lark.send(report, chapters, date_str)
    _log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
