"""Daily Parameter Review — orchestrator.

Runs all adapters, builds report.json, and uploads to Vercel Blob.

Usage:
    python -m runner.main              # run and upload
    python -m runner.main --dry-run    # run and print JSON, skip upload
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .adapters.price_limit import PriceLimitAdapter
from .adapters.mmr_futures import MMRFuturesAdapter
from .adapters.index_review import IndexReviewAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMA_CACHE = PROJECT_ROOT / "params_cli" / "price_limits" / "cache" / "ema_state.json"


def _log(msg: str):
    print(f"  [runner] {msg}", file=sys.stderr)


def _load_ema_data() -> dict:
    """Load cached EMA state if available."""
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
    """Build the top-level report.json manifest."""
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


def _upload_to_blob(chapters: list[dict], report: dict, date_str: str):
    """Upload all artifacts to Vercel Blob."""
    from . import blob

    prefix = f"reports/{date_str}"

    # 1. Upload report.json
    report_url = blob.upload(
        f"{prefix}/report.json",
        json.dumps(report, indent=2, ensure_ascii=False),
        "application/json",
    )
    _log(f"Uploaded report.json -> {report_url}")

    # 2. Upload chapter markdown files
    for ch in chapters:
        md_url = blob.upload(
            f"{prefix}/{ch['slug']}.md",
            ch["markdown"],
            "text/markdown",
        )
        _log(f"Uploaded {ch['slug']}.md -> {md_url}")

    # 3. Upload download assets
    for ch in chapters:
        for dl in ch.get("downloads", []):
            asset_url = blob.upload(
                f"{prefix}/assets/{dl['filename']}",
                dl["content"],
                "text/csv",
            )
            _log(f"Uploaded {dl['filename']} -> {asset_url}")

    # 4. Upload latest.json (points to current date)
    latest = {
        "date": date_str,
        "generated_at": report["generated_at"],
        "status": report["status"],
        "total_issues": report["total_issues"],
        "report_path": f"{prefix}/report.json",
    }
    latest_url = blob.upload(
        "reports/latest.json",
        json.dumps(latest, indent=2, ensure_ascii=False),
        "application/json",
    )
    _log(f"Uploaded latest.json -> {latest_url}")

    # 5. Update index.json (append date if new)
    try:
        existing_blobs = blob.list_blobs("reports/index.json")
        index_data = {"dates": []}
        if existing_blobs:
            # Try to fetch existing index
            from urllib.request import Request, urlopen
            for b in existing_blobs:
                if b.get("pathname") == "reports/index.json":
                    req = Request(b["url"], headers={"User-Agent": "runner/1.0"})
                    with urlopen(req, timeout=15) as resp:
                        index_data = json.loads(resp.read())
                    break
        if date_str not in index_data.get("dates", []):
            index_data.setdefault("dates", []).append(date_str)
            index_data["dates"].sort(reverse=True)
        index_url = blob.upload(
            "reports/index.json",
            json.dumps(index_data, indent=2, ensure_ascii=False),
            "application/json",
        )
        _log(f"Uploaded index.json -> {index_url}")
    except Exception as exc:
        _log(f"Warning: failed to update index.json: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Daily Parameter Review runner")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report JSON to stdout without uploading",
    )
    args = parser.parse_args()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _log(f"=== Daily Parameter Review — {date_str} ===")

    # 1. Load EMA data
    ema_data = _load_ema_data()

    # 2. Run adapters in sequence
    adapters = [
        PriceLimitAdapter(),
        MMRFuturesAdapter(),
        IndexReviewAdapter(),
    ]

    chapters = []
    for adapter in adapters:
        _log(f"Running adapter: {adapter.title} ({adapter.slug})...")
        chapter = adapter.execute(ema_data)
        chapters.append(chapter)
        _log(
            f"  -> {chapter['status']} | "
            f"{chapter['metrics']['issues_found']} issues | "
            f"{chapter['metrics']['instruments_scanned']} instruments"
        )

    # 3. Build report manifest
    report = _build_report(chapters, date_str)
    _log(
        f"Report: status={report['status']}, "
        f"total_issues={report['total_issues']}"
    )

    # 4. Output or upload
    if args.dry_run:
        # In dry-run mode, output the full report + chapters to stdout
        output = {
            "report": report,
            "chapters": chapters,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        _log("Dry run — skipping upload")
    else:
        _upload_to_blob(chapters, report, date_str)
        _log("Upload complete.")

    # Exit code: 0 if pass, 1 if any issues
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
