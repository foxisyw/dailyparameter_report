"""Index Review adapter — reviews index component quality via params_cli/index CLI."""

import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .base import BaseAdapter

CLI_DIR = Path(__file__).resolve().parent.parent.parent / "params_cli" / "index"
CLI_PATH = CLI_DIR / "cli.py"


def _log(msg: str):
    print(f"  [index-review] {msg}", file=sys.stderr)


def _run_cli(*args: str, timeout: int = 120) -> dict | None:
    """Run the index CLI and return parsed JSON stdout."""
    cmd = [sys.executable, str(CLI_PATH)] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(CLI_DIR))
        if result.returncode != 0:
            _log(f"CLI error (exit {result.returncode}): {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        _log(f"CLI failed: {e}")
        return None


# ─── Review Rules (simplified from review_methodology.md) ─────────────────

def _check_tradfi(idx: dict) -> list[str]:
    """TradFi rules: oracle coverage, weight cap, perpetuals, deviation."""
    issues = []
    comps = {c["exchange"] for c in idx.get("components", [])}
    alts = {a["exchange"] for a in idx.get("alternatives", [])}

    # TF-1: Oracle coverage
    for oracle in ("Pyth", "Ondo_TICKER", "dxFeed", "Binance_LINEAR_INDEX"):
        if oracle in alts and oracle not in comps:
            issues.append(f"TF-1: {oracle} available but not in components")

    # TF-3: Perpetual components
    for perp in ("Binance_LINEAR_PERPETUAL", "OKX_PERPETUAL"):
        if perp in alts and perp not in comps:
            alt_score = next((a.get("exchange_score", 0) for a in idx["alternatives"] if a["exchange"] == perp), 0)
            if alt_score >= 4:
                issues.append(f"TF-3: {perp} (score {alt_score}) available but not used")

    # TF-5: Min 3 components
    if idx.get("component_count", 0) < 3:
        issues.append(f"TF-5: only {idx.get('component_count', 0)} components (need ≥3)")

    # TF-6: Deviation check
    ema_max = idx.get("ema_max_deviation", 0)
    if ema_max > 0.5:
        issues.append(f"TF-6: ema_max_deviation {ema_max:.2f}% > 0.5%")

    return issues


def _check_topcoins(idx: dict) -> list[str]:
    """Topcoins: skip if healthy."""
    avg_dev = idx.get("ema_avg_deviation", 0)
    max_dev = idx.get("ema_max_deviation", 0)
    n = idx.get("component_count", 0)
    if avg_dev < 0.15 and max_dev < 0.3 and n >= 5:
        return []
    issues = []
    if avg_dev >= 0.15:
        issues.append(f"TC: ema_avg_deviation {avg_dev:.2f}% ≥ 0.15%")
    if max_dev >= 0.3:
        issues.append(f"TC: ema_max_deviation {max_dev:.2f}% ≥ 0.3%")
    if n < 5:
        issues.append(f"TC: only {n} components (need ≥5)")
    return issues


def _check_fiat(idx: dict) -> list[str]:
    """Fiat: skip if healthy."""
    avg_dev = idx.get("ema_avg_deviation", 0)
    max_dev = idx.get("ema_max_deviation", 0)
    n = idx.get("component_count", 0)
    if avg_dev < 0.1 and max_dev < 0.3 and n >= 3:
        return []
    issues = []
    if avg_dev >= 0.1:
        issues.append(f"Fiat: ema_avg_deviation {avg_dev:.2f}% ≥ 0.1%")
    if max_dev >= 0.3:
        issues.append(f"Fiat: ema_max_deviation {max_dev:.2f}% ≥ 0.3%")
    if n < 3:
        issues.append(f"Fiat: only {n} components (need ≥3)")
    return issues


def _check_altcoins(idx: dict) -> list[str]:
    """Altcoins: exchange diversity, deviation, staleness."""
    issues = []
    comps = idx.get("components", [])
    alts = idx.get("alternatives", [])
    comp_exchanges = {c["exchange"] for c in comps}

    # AL-1: Preferred exchanges missing
    for pref in ("OKX", "Binance", "Bybit"):
        alt_has = any(a["exchange"] == pref for a in alts)
        if alt_has and pref not in comp_exchanges:
            issues.append(f"AL-1: {pref} available but not in components")

    # AL-4: Min 3 distinct exchanges
    distinct = len({c["exchange"].split("_")[0] for c in comps})
    if distinct < 3:
        issues.append(f"AL-4: only {distinct} distinct exchanges (need ≥3)")

    # AL-5: Deviation & staleness
    avg_dev = idx.get("ema_avg_deviation", 0)
    max_dev = idx.get("ema_max_deviation", 0)
    avg_lag = idx.get("ema_avg_update_lag", 0)
    if avg_dev > 0.5:
        issues.append(f"AL-5: ema_avg_deviation {avg_dev:.2f}% > 0.5%")
    if max_dev > 1.5:
        issues.append(f"AL-5: ema_max_deviation {max_dev:.2f}% > 1.5%")
    if avg_lag > 300:
        issues.append(f"AL-5: ema_avg_update_lag {avg_lag:.0f}s > 300s")

    # Individual component deviation
    for c in comps:
        if c.get("ema_deviation", 0) > 2.0:
            issues.append(f"AL-5: {c['exchange']} {c['symbol']} deviation {c['ema_deviation']:.2f}% > 2%")

    return issues


RULE_CHECKERS = {
    "TradFi": _check_tradfi,
    "Topcoins": _check_topcoins,
    "Fiat": _check_fiat,
    "Altcoins": _check_altcoins,
}


class IndexReviewAdapter(BaseAdapter):

    @property
    def slug(self) -> str:
        return "index-review"

    @property
    def title(self) -> str:
        return "Index Review"

    def execute(self, ema_data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        # Call CLI review to get data file path (run twice: first=hints, second=data)
        _log("calling CLI review (hints pass)...")
        _run_cli("review", "--batch", "0")
        _log("calling CLI review (data pass)...")
        cli_output = _run_cli("review", "--batch", "0")

        if not cli_output or cli_output.get("status") != "ok":
            _log(f"CLI review failed: {cli_output}")
            return self._pending("CLI review failed or server not running.")

        data_file = cli_output.get("file_c")
        if not data_file or not Path(data_file).exists():
            _log(f"Data file not found: {data_file}")
            return self._pending("Review data file not generated.")

        total_flagged = cli_output.get("total_flagged", 0)
        total_indexes = cli_output.get("total_indexes", 0)
        ema_cov = cli_output.get("ema_coverage", 0)

        # Read the data file
        try:
            with open(data_file) as f:
                indexes = json.load(f)
        except Exception as e:
            _log(f"Error reading data file: {e}")
            return self._pending(f"Error reading data: {e}")

        _log(f"loaded {len(indexes)} indexes from {Path(data_file).name}")

        # Apply rules per asset type
        by_type: dict[str, list[dict]] = {"TradFi": [], "Topcoins": [], "Fiat": [], "Altcoins": []}
        pass_count = 0
        all_flagged: list[dict] = []

        for idx in indexes:
            asset_type = idx.get("assetsType", "Altcoins")
            checker = RULE_CHECKERS.get(asset_type, _check_altcoins)
            issues = checker(idx)
            if issues:
                entry = {
                    "index": idx["index"],
                    "assetsType": asset_type,
                    "issues": issues,
                    "component_count": idx.get("component_count", 0),
                    "ema_avg_deviation": idx.get("ema_avg_deviation", 0),
                    "ema_max_deviation": idx.get("ema_max_deviation", 0),
                    "components": idx.get("components", []),
                }
                by_type.setdefault(asset_type, []).append(entry)
                all_flagged.append(entry)
            else:
                pass_count += 1

        flag_count = len(all_flagged)
        _log(f"Review complete: {flag_count} flagged, {pass_count} pass")

        # Determine status
        has_critical = any(
            any("deviation" in iss.lower() and float(iss.split()[-1].rstrip("%")) > 1.0
                for iss in f["issues"] if "deviation" in iss.lower() and "%" in iss)
            for f in all_flagged
        )
        status = "critical" if has_critical else ("warning" if flag_count > 0 else "pass")

        # Build rule_blocks (one per asset type)
        rule_blocks = []
        for asset_type in ("TradFi", "Topcoins", "Fiat", "Altcoins"):
            flagged = by_type.get(asset_type, [])
            if not flagged:
                rule_blocks.append({
                    "ruleId": asset_type.lower(),
                    "title": f"{asset_type} Index Quality",
                    "status": "pass",
                    "description": f"All {asset_type} indexes pass quality checks.",
                    "table": None,
                    "note": None,
                })
                continue

            worst = "critical" if any(
                any("deviation" in i and "%" in i for i in f["issues"]) for f in flagged
            ) else "warning"

            rows = []
            for f in flagged[:20]:  # cap at 20 per type
                rows.append([
                    f["index"],
                    str(f["component_count"]),
                    f"{f['ema_avg_deviation']:.2f}%",
                    f"{f['ema_max_deviation']:.2f}%",
                    "; ".join(f["issues"][:3]),
                ])

            rule_blocks.append({
                "ruleId": asset_type.lower(),
                "title": f"{asset_type} Index Quality ({len(flagged)} flagged)",
                "status": worst,
                "description": f"{len(flagged)} {asset_type} indexes have issues.",
                "table": {
                    "headers": ["Index", "Components", "Avg Dev%", "Max Dev%", "Issues"],
                    "rows": rows,
                },
                "note": f"{len(flagged) - len(rows)} more not shown" if len(flagged) > 20 else None,
            })

        # Build recommended changes table (top 20 flagged)
        rec_rows = []
        for f in all_flagged[:20]:
            rec_rows.append([f["index"], f["assetsType"], "; ".join(f["issues"][:2])])

        recommended_changes = {
            "headers": ["Index", "Type", "Issues"],
            "rows": rec_rows,
        } if rec_rows else None

        # CSV download (summary)
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["index", "assetsType", "component_count", "ema_avg_deviation", "ema_max_deviation", "issues"])
        for f in all_flagged:
            writer.writerow([
                f["index"], f["assetsType"], f["component_count"],
                f"{f['ema_avg_deviation']:.4f}", f"{f['ema_max_deviation']:.4f}",
                "; ".join(f["issues"]),
            ])
        csv_content = csv_buf.getvalue()
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        # Component-level template CSV (20-column upload format)
        template_csv_content = ""
        try:
            sys.path.insert(0, str(CLI_DIR.parent))
            from index.fetcher import generate_adjustment
            components_spec = [
                {"index": f["index"], "components": f.get("components", [])}
                for f in all_flagged if f.get("components")
            ]
            if components_spec:
                result = generate_adjustment(components_spec)
                template_csv_content = Path(result["path"]).read_text()
                _log(f"Generated component template: {result['rows']} rows, {result['indexes']} indexes")
        except Exception as e:
            _log(f"Component template generation failed (non-fatal): {e}")
            template_csv_content = ""

        summary = (
            f"Scanned {total_indexes} indexes ({ema_cov} with EMA). "
            f"{flag_count} flagged, {pass_count} pass."
        )

        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "rules",
            "status": status,
            "summary": summary,
            "metrics": {
                "instruments_scanned": total_indexes,
                "ema_coverage": ema_cov,
                "issues_found": flag_count,
                "source": "params_cli/index CLI",
                "generated_at": now,
            },
            "metric_cards": [
                {"label": "Total Indexes", "value": str(total_indexes)},
                {"label": "EMA Coverage", "value": str(ema_cov)},
                {"label": "Flagged", "value": str(flag_count)},
                {"label": "Pass", "value": str(pass_count)},
            ],
            "rule_blocks": rule_blocks,
            "recommended_changes": recommended_changes,
            "downloads": ([
                {
                    "label": "Index Review Summary",
                    "filename": f"index_review_{date_str}.csv",
                    "content": csv_content,
                },
            ] + ([{
                    "label": "Index Components Template",
                    "filename": f"index_components_{date_str}.csv",
                    "content": template_csv_content,
            }] if template_csv_content else [])) if all_flagged else [],
            "markdown": f"# Index Review\n\n{summary}\n",
            "error": None,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }

    def _pending(self, reason: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "rules",
            "status": "pending",
            "summary": reason,
            "metrics": {
                "instruments_scanned": 0,
                "ema_coverage": 0,
                "issues_found": 0,
                "source": "n/a",
                "generated_at": now,
            },
            "metric_cards": [
                {"label": "Instruments", "value": "0"},
                {"label": "EMA Coverage", "value": "0"},
                {"label": "Issues", "value": "0"},
                {"label": "Source", "value": "n/a"},
            ],
            "rule_blocks": [],
            "recommended_changes": None,
            "downloads": [],
            "markdown": f"# Index Review\n\n**Status:** pending\n\n{reason}\n",
            "error": None,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }
