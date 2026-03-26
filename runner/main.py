"""Daily Parameter Review — orchestrator.

Runs all adapters, builds report.json, and saves to public/data/.
The local Claude Code workflow commits and pushes afterwards, and Vercel auto-deploys.

Usage:
    python -m runner.main              # run and save to public/data/
    python -m runner.main --dry-run    # run and print JSON, skip saving
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .adapters.price_limit import PriceLimitAdapter
from .adapters.risk_intel import RiskIntelAdapter
from .adapters.mmr_futures import MMRFuturesAdapter
from .adapters.index_review import IndexReviewAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMA_CACHE = PROJECT_ROOT / "params_cli" / "price_limits" / "cache" / "ema_state.json"
DATA_DIR = PROJECT_ROOT / "public" / "data"


def _log(msg: str):
    print(f"  [runner] {msg}", file=sys.stderr)


def _load_ema_data() -> dict:
    if not EMA_CACHE.exists():
        _log(f"No EMA cache at {EMA_CACHE} — EMA-based rules will be skipped")
        return {}
    try:
        raw = json.loads(EMA_CACHE.read_text())
        ema = raw.get("ema_state", {})
        _log(f"Loaded EMA data for {len(ema)} instruments")
        return ema
    except Exception as exc:
        _log(f"Failed to load EMA cache: {exc}")
        return {}


def _build_report(chapters: list[dict], date_str: str) -> dict:
    overall_status = "pass"
    for ch in chapters:
        if ch["status"] == "critical":
            overall_status = "critical"
            break
        if ch["status"] == "warning":
            overall_status = "warning"

    total_issues = sum(ch["metrics"]["issues_found"] for ch in chapters)

    return {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "total_issues": total_issues,
        "chapters": [
            {
                "slug": ch["slug"],
                "title": ch["title"],
                "status": ch["status"],
                "summary": ch["summary"],
                "metrics": ch["metrics"],
            }
            for ch in chapters
        ],
    }


def _save_report(chapters: list[dict], report: dict, date_str: str):
    """Save report data to public/data/ for Vercel static serving."""
    date_dir = DATA_DIR / "reports" / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    # Full report with chapters
    full = {"report": report, "chapters": chapters}
    (date_dir / "report.json").write_text(
        json.dumps(full, indent=2, ensure_ascii=False)
    )
    _log(f"Saved {date_dir / 'report.json'}")

    # Chapter markdown files
    for ch in chapters:
        (date_dir / f"{ch['slug']}.md").write_text(ch.get("markdown", ""))

    # Download assets
    assets_dir = date_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    for ch in chapters:
        for dl in ch.get("downloads", []):
            (assets_dir / dl["filename"]).write_text(dl["content"])
            _log(f"Saved {dl['filename']}")

    # latest.json — points to current date
    latest = {
        "date": date_str,
        "generated_at": report["generated_at"],
        "status": report["status"],
        "total_issues": report["total_issues"],
    }
    reports_dir = DATA_DIR / "reports"
    (reports_dir / "latest.json").write_text(
        json.dumps(latest, indent=2, ensure_ascii=False)
    )
    _log("Saved latest.json")

    # index.json — list of all report dates
    index_path = reports_dir / "index.json"
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text())
        except Exception:
            index_data = {"dates": []}
    else:
        index_data = {"dates": []}

    if date_str not in index_data["dates"]:
        index_data["dates"].append(date_str)
        index_data["dates"].sort(reverse=True)

    index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False))
    _log("Saved index.json")


def main():
    parser = argparse.ArgumentParser(description="Daily Parameter Review runner")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON, skip saving")
    parser.add_argument("--no-lark", action="store_true", help="Skip Lark notification")
    args = parser.parse_args()

    # Use HKT (UTC+8) for the report date — both daily cron runs land on same HKT day
    from zoneinfo import ZoneInfo
    hkt_now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    date_str = hkt_now.strftime("%Y-%m-%d")
    _log(f"=== Daily Parameter Review — {date_str} ===")

    ema_data = _load_ema_data()

    adapters = [
        RiskIntelAdapter(),       # Risk Intelligence is the main/default section
        PriceLimitAdapter(),
        MMRFuturesAdapter(),
        IndexReviewAdapter(),
    ]

    chapters = []
    for adapter in adapters:
        _log(f"Running adapter: {adapter.title} ({adapter.slug})...")
        try:
            chapter = adapter.execute(ema_data)
        except Exception as exc:
            _log(f"  ERROR: {exc}")
            chapter = {
                "slug": adapter.slug, "title": adapter.title, "render_variant": "rules", "status": "critical",
                "summary": f"Adapter failed: {exc}",
                "metrics": {"instruments_scanned": 0, "ema_coverage": 0, "issues_found": 0,
                            "source": "error", "generated_at": datetime.now(timezone.utc).isoformat()},
                "metric_cards": [
                    {"label": "Instruments", "value": "0"},
                    {"label": "EMA Coverage", "value": "0"},
                    {"label": "Issues", "value": "0"},
                    {"label": "Source", "value": "error"},
                ],
                "rule_blocks": [], "recommended_changes": None, "downloads": [],
                "markdown": "", "error": str(exc), "source_document": None,
                "suspicious_users": [], "user_profiles": [],
            }
        chapters.append(chapter)
        _log(f"  -> {chapter['status']} | {chapter['metrics']['issues_found']} issues")

    report = _build_report(chapters, date_str)
    _log(f"Report: status={report['status']}, total_issues={report['total_issues']}")

    if args.dry_run:
        print(json.dumps({"report": report, "chapters": chapters}, indent=2, ensure_ascii=False))
        _log("Dry run — skipping save")
    else:
        _save_report(chapters, report, date_str)
        _log("Report saved.")

        if args.no_lark:
            _log("Lark notification skipped (--no-lark)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
