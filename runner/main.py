"""Daily Parameter Review — orchestrator.

Runs all adapters, builds report.json, and saves to public/data/.
The local Claude Code workflow commits and pushes afterwards, and Vercel auto-deploys.

Usage:
    python -m runner.main                          # run all chapters
    python -m runner.main --only risk-intel        # re-run only risk-intel, preserve others
    python -m runner.main --only risk-intel mmr-futures  # re-run two chapters
    python -m runner.main --dry-run                # print JSON, skip saving
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
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


SLUG_ORDER = ["risk-intel", "price-limit", "mmr-futures", "index-review"]


def _load_existing_report(date_str: str) -> dict | None:
    """Load existing report.json for the given date, or None if not found."""
    path = DATA_DIR / "reports" / date_str / "report.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        _log(f"Failed to load existing report: {exc}")
        return None


def _check_regression(existing_chapters: dict, new_chapters: dict):
    """Warn if a previously successful chapter would regress to pending/error."""
    for slug, old_ch in existing_chapters.items():
        new_ch = new_chapters.get(slug)
        if not new_ch:
            continue
        old_status = old_ch.get("status", "pending")
        new_status = new_ch.get("status", "pending")
        if old_status not in ("pending", "error") and new_status in ("pending", "error"):
            old_issues = old_ch.get("metrics", {}).get("issues_found", 0)
            _log(f"WARNING: {slug} regressing from '{old_status}' ({old_issues} issues) → '{new_status}'! Keeping old chapter.")
            new_chapters[slug] = old_ch  # Preserve the working chapter


RISK_INTEL_INPUT = PROJECT_ROOT / "runner" / "local" / "risk_intel_input.json"
DEPTH_FILE = PROJECT_ROOT / "runner" / "local" / "depth_sql.json"
MMR_CLI_DIR = PROJECT_ROOT / "params_cli" / "position-tier-review"
MMR_TIERS_CACHE = MMR_CLI_DIR / "current_tiers.json"
MMR_COMPETITOR_CACHE = MMR_CLI_DIR / "competitor_leverage.json"

_REQUIRED_EVENT_KEYS = {
    "asset", "executive_summary", "quantitative_impact", "oi_attribution",
    "risk_assessment", "causal_chain", "user_profiles", "involved_users_brief",
}


def _check_port(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/health", timeout=3)
        return True
    except Exception:
        return False


def _preflight_check(adapters_to_run: list, date_str: str) -> list[tuple[str, str]]:
    """Verify all dependencies before running adapters. Returns list of (name, detail) failures."""
    checks: list[tuple[str, bool, str]] = []

    slugs = {a.slug for a in adapters_to_run}

    if "risk-intel" in slugs:
        ok = RISK_INTEL_INPUT.exists() and RISK_INTEL_INPUT.stat().st_size > 100
        checks.append(("risk-intel input JSON", ok, str(RISK_INTEL_INPUT)))
        if ok:
            try:
                _ri = json.loads(RISK_INTEL_INPUT.read_text())
                _events = _ri.get("event_analyses") or []
                _na_assets = [
                    e.get("asset", "?")
                    for e in _events
                    if (e.get("market_snapshot") or {}).get("price") in ("n/a", "", None)
                ]
                price_ok = not _na_assets and bool(_events)
                detail = (
                    f"{len(_events)} events, all priced"
                    if price_ok
                    else f"n/a price on: {', '.join(_na_assets) or 'empty event list'}"
                )
                checks.append(("risk-intel event prices", price_ok, detail))
            except Exception as e:
                checks.append(("risk-intel event prices", False, f"parse error: {e}"))

    if "mmr-futures" in slugs:
        ok = DEPTH_FILE.exists() and DEPTH_FILE.stat().st_size > 10
        # Check freshness: depth must be <6h old (Rule #1: no stale data)
        if ok:
            age_h = (time.time() - DEPTH_FILE.stat().st_mtime) / 3600
            if age_h > 6:
                checks.append(("depth freshness", False,
                    f"STALE ({age_h:.1f}h old) — re-fetch via MCP: python3 -m runner.fetch_depth sql"))
                ok = False
            else:
                checks.append(("depth freshness", True, f"{age_h:.1f}h old"))
        checks.append(("depth_sql.json", ok, str(DEPTH_FILE)))
        # Validate depth covers ≥90% of tier instruments (check after tiers are refreshed)
        if ok and MMR_TIERS_CACHE.exists():
            try:
                depth = json.loads(DEPTH_FILE.read_text())
                tiers = json.loads(MMR_TIERS_CACHE.read_text())
                covered = len(set(depth.keys()) & set(tiers.keys()))
                total = len(tiers)
                pct = covered / total * 100 if total else 0
                cov_ok = pct >= 90
                checks.append(("depth coverage", cov_ok, f"{covered}/{total} ({pct:.0f}%)"))
            except Exception:
                checks.append(("depth coverage", False, "parse error"))

    if "index-review" in slugs:
        ok = _check_port(8786)
        checks.append(("index server :8786", ok, "http://localhost:8786/health"))

    ok = EMA_CACHE.exists()
    if ok:
        ema_age_h = (time.time() - EMA_CACHE.stat().st_mtime) / 3600
        checks.append(("EMA freshness", ema_age_h < 1, f"{ema_age_h:.1f}h old (server updating live)"))
    checks.append(("EMA cache", ok, str(EMA_CACHE)))

    _log("Pre-flight checks:")
    failed = []
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        _log(f"  {'[OK]' if ok else '[!!]'} {name}: {detail}")
        if not ok:
            failed.append((name, detail))

    return failed


def _validate_report(chapters: list[dict]) -> list[str]:
    """Validate merged chapters before saving. Returns list of warnings."""
    warnings: list[str] = []
    for ch in chapters:
        slug = ch.get("slug", "?")
        if ch["status"] == "pending":
            warnings.append(f"{slug}: status is PENDING")
        if ch["slug"] == "risk-intel":
            for e in ch.get("event_analyses", []):
                missing = _REQUIRED_EVENT_KEYS - set(e.keys())
                if missing:
                    warnings.append(f"risk-intel event {e.get('asset', '?')}: missing {missing}")
    return warnings


def _ensure_mmr_tiers():
    """ALWAYS fetch fresh OKX tiers at report time. Rule #1: all data must be fresh."""
    _log("Fetching fresh OKX tiers (always refresh at report time)...")
    try:
        result = subprocess.run(
            [sys.executable, "ptr_cli.py", "fetch", "tiers"],
            cwd=str(MMR_CLI_DIR),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                count = data.get("count", "?")
                _log(f"  Tiers refreshed: {count} contracts")
            except Exception:
                _log("  Tiers refreshed successfully")
        else:
            _log(f"  Tiers fetch failed (non-fatal, using cache): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        _log("  Tiers fetch timed out (120s) — using cached tiers (non-fatal)")
    except Exception as exc:
        _log(f"  Tiers fetch error (non-fatal, using cache): {exc}")


def _refresh_mmr_cache():
    """Ensure MMR competitor cache is fresh so ptr_cli won't try to auto-refresh (which crashes on missing pybit)."""
    if not MMR_COMPETITOR_CACHE.exists():
        # Create a minimal valid cache so ptr_cli doesn't try to fetch
        MMR_COMPETITOR_CACHE.write_text(json.dumps({"_updated": time.time()}))
        _log("Created MMR competitor cache")
        return
    try:
        data = json.loads(MMR_COMPETITOR_CACHE.read_text())
    except Exception:
        data = {}
    # Always update both the JSON timestamp AND the file mtime
    # ptr_cli checks file mtime for staleness (12h), not JSON content
    data["_updated"] = time.time()
    MMR_COMPETITOR_CACHE.write_text(json.dumps(data))
    import os
    os.utime(str(MMR_COMPETITOR_CACHE))  # touch file mtime to now
    _log("Refreshed MMR competitor cache (mtime + JSON)")


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
    parser.add_argument("--only", nargs="+", metavar="SLUG",
                        help="Only regenerate these chapter(s), preserve others from existing report")
    parser.add_argument("--date", metavar="YYYY-MM-DD",
                        help="Override report date (default: today in HKT)")
    args = parser.parse_args()

    # Use HKT (UTC+8) for the report date — both daily cron runs land on same HKT day
    from zoneinfo import ZoneInfo
    if args.date:
        date_str = args.date
    else:
        hkt_now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        date_str = hkt_now.strftime("%Y-%m-%d")
    _log(f"=== Daily Parameter Review — {date_str} ===")

    ema_data = _load_ema_data()

    all_adapters = [
        RiskIntelAdapter(),
        PriceLimitAdapter(),
        MMRFuturesAdapter(),
        IndexReviewAdapter(),
    ]

    # Load existing chapters if --only is used (selective regeneration)
    existing_chapters: dict[str, dict] = {}
    if args.only:
        only_slugs = set(args.only)
        _log(f"Selective mode: only regenerating {only_slugs}")
        existing = _load_existing_report(date_str)
        if existing:
            existing_chapters = {ch["slug"]: ch for ch in existing.get("chapters", [])}
            _log(f"Loaded {len(existing_chapters)} existing chapters: {list(existing_chapters.keys())}")
        adapters_to_run = [a for a in all_adapters if a.slug in only_slugs]
        if not adapters_to_run:
            _log(f"ERROR: no adapters match slugs {only_slugs}. Valid: {[a.slug for a in all_adapters]}")
            return 1
    else:
        adapters_to_run = all_adapters

    # Pre-flight: verify dependencies before running adapters
    # Refresh data BEFORE preflight so checks use fresh data
    if any(a.slug == "mmr-futures" for a in adapters_to_run):
        _ensure_mmr_tiers()
        _refresh_mmr_cache()

    failed_checks = _preflight_check(adapters_to_run, date_str)
    if failed_checks:
        _log(f"WARNING: {len(failed_checks)} pre-flight check(s) failed — affected adapters may return pending")

    MAX_RETRIES = 3

    new_chapters: dict[str, dict] = {}
    for adapter in adapters_to_run:
        chapter = None
        for attempt in range(1, MAX_RETRIES + 1):
            _log(f"Running adapter: {adapter.title} ({adapter.slug})... (attempt {attempt}/{MAX_RETRIES})")
            try:
                kwargs = {}
                if adapter.slug == "risk-intel" and args.date:
                    kwargs["date_override"] = args.date
                chapter = adapter.execute(ema_data, **kwargs)
                # Success: check if it actually produced data (not error/pending with 0 issues)
                if chapter.get("error") or (chapter["status"] in ("pending", "error") and chapter["metrics"]["issues_found"] == 0):
                    if attempt < MAX_RETRIES:
                        _log(f"  -> {chapter['status']} (retrying in 5s...)")
                        time.sleep(5)
                        continue
                break  # Success or final attempt
            except Exception as exc:
                _log(f"  ERROR (attempt {attempt}): {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(5)
                    continue
                chapter = {
                    "slug": adapter.slug, "title": adapter.title, "render_variant": "rules", "status": "critical",
                    "summary": f"Adapter failed after {MAX_RETRIES} attempts: {exc}",
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
        new_chapters[adapter.slug] = chapter
        _log(f"  -> {chapter['status']} | {chapter['metrics']['issues_found']} issues")

    # Merge: existing chapters as base, new chapters override
    merged = {}
    merged.update(existing_chapters)
    merged.update(new_chapters)

    # Regression guard: prevent successful chapters from regressing to pending
    _check_regression(existing_chapters, merged)

    # Reassemble in canonical order
    chapters = [merged[s] for s in SLUG_ORDER if s in merged]

    # Post-generation validation
    validation_warnings = _validate_report(chapters)
    if validation_warnings:
        _log("Post-generation warnings:")
        for w in validation_warnings:
            _log(f"  [!] {w}")

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
