"""MMR Futures adapter — calls params_cli/mmr_future/ptr_cli.py for real data."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .base import BaseAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MMR_CLI_DIR = PROJECT_ROOT / "params_cli" / "position-tier-review"
REVIEW_PKL = MMR_CLI_DIR / "review.pkl"
BATCH_PKL = MMR_CLI_DIR / "batch.pkl"
_RUNNER_LOCAL = Path(__file__).resolve().parent.parent / "local"
DEPTH_FILE = _RUNNER_LOCAL / "depth_sql.json"
SCOPES_TARGET = (
    Path.home() / ".claude" / "skills" / "position-tier-review" / "references" / "scopes.json"
)

# Category classification (from scopes.json default scope)
COMMODITY_SYMS = {"BZ", "CL", "NG", "XAG", "XAU", "XCU", "XPT", "XPD"}
STOCK_SYMS = {
    "AAPL", "AMD", "AMZN", "COIN", "GOOGL", "HOOD", "INTC", "META", "MSFT", "MSTR",
    "MU", "NFLX", "NVDA", "ORCL", "PLTR", "QQQ", "SNDK", "SPY", "TSLA", "TSM",
    "EWJ", "EWY", "CRCL",
}


def _ensure_scopes():
    """Ensure scopes.json and model.json are at the expected paths for ptr_cli.py."""
    # scopes.json for ptr_cli
    if not SCOPES_TARGET.exists():
        source = MMR_CLI_DIR / "scopes.json"
        if source.exists():
            SCOPES_TARGET.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, SCOPES_TARGET)

    # model.json for tier_calculator (hardcoded to ~/parameter review/model.json)
    model_target = Path.home() / "parameter review" / "model.json"
    if not model_target.exists():
        source = MMR_CLI_DIR / "model.json"
        if source.exists():
            model_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, model_target)


def _ensure_competitor_cache():
    """Create empty competitor cache if it doesn't exist (Binance/Bybit SDK may not be installed)."""
    cache = MMR_CLI_DIR / "competitor_leverage.json"
    if not cache.exists():
        cache.write_text("{}")


def _run_cli(args: list[str], timeout: int = 180) -> dict:
    result = subprocess.run(
        [sys.executable, "ptr_cli.py"] + args,
        cwd=str(MMR_CLI_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"ptr_cli {' '.join(args)} produced no output. stderr: {result.stderr[:300]}")
    return json.loads(result.stdout)


def _categorize(name: str) -> str:
    base = name.split("-")[0]
    if base in COMMODITY_SYMS:
        return "Commodity"
    if base in STOCK_SYMS:
        return "Equity"
    return "Crypto"


def _change_str(row) -> str:
    lvg = row.get("should_adjust_lvg", "") or ""
    amt = row.get("should_adjust_amt", "") or ""
    curr = int(row.get("current_leverage") or 0)
    sugg = int(row.get("suggested_leverage") or 0)
    if lvg and amt:
        inc_dir = "↑" if amt == "should increase" else "↓"
        return f"{curr}x → {sugg}x + Inc {inc_dir}"
    if lvg:
        return f"{curr}x → {sugg}x"
    if amt:
        return "Inc " + ("↑" if amt == "should increase" else "↓")
    return ""


def _reason_str(row) -> str:
    lvg = row.get("should_adjust_lvg", "") or ""
    amt = row.get("should_adjust_amt", "") or ""
    ratio = row.get("current_inc_ratio")
    parts = []
    if lvg:
        cls = int(row.get("class") or 4)
        parts.append(f"Depth → level {cls}")
    if amt and ratio is not None and ratio == ratio:  # guard NaN
        if amt == "should increase":
            parts.append(f"ratio {ratio:.1%} < 10%")
        else:
            parts.append(f"ratio {ratio:.1%} > 50%")
    return "; ".join(parts)


def _rows_from_df(df, include_category: bool = False) -> list[list[str]]:
    rows = []
    for _, row in df.iterrows():
        change = _change_str(row)
        if not change:
            continue
        if include_category:
            rows.append([
                row["name"], _categorize(row["name"]), change, _reason_str(row), "HIGH",
            ])
        else:
            rows.append([row["name"], change, _reason_str(row), "HIGH"])
    return rows


class MMRFuturesAdapter(BaseAdapter):

    @property
    def slug(self) -> str:
        return "mmr-futures"

    @property
    def title(self) -> str:
        return "MMR Futures Review"

    def execute(self, ema_data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        if not DEPTH_FILE.exists():
            return self._pending_chapter(
                now,
                "Depth data not available — re-run cron to fetch via MCP (Step 5b).",
            )

        try:
            _ensure_scopes()
            _ensure_competitor_cache()
            return self._run_review(now)
        except Exception as exc:
            return self._error_chapter(now, str(exc))

    def _run_review(self, now: str) -> dict:
        import pandas as pd  # available via ptr_cli dependencies

        # Step 1: Run review pipeline
        review_json = _run_cli(["review", "--depth", str(DEPTH_FILE)])
        if review_json.get("status") == "ERROR":
            raise RuntimeError(review_json.get("message", "ptr_cli review failed"))

        data_summary = review_json.get("data_summary", {})
        adj_summary = review_json.get("adjustment_summary", {})
        total_contracts = data_summary.get("total_contracts", 0)
        in_scope = data_summary.get("in_scope", 0)
        needs_adj = adj_summary.get("needs_adjustment", 0)

        # Step 2: Run moderate scope
        scope_json = _run_cli(["scope", "moderate"])
        if scope_json.get("status") == "ERROR":
            raise RuntimeError(scope_json.get("message", "ptr_cli scope failed"))

        batch_count = scope_json.get("contract_count", 0)
        breakdown = scope_json.get("breakdown", {})

        # Step 3: Read batch DataFrame
        if not BATCH_PKL.exists():
            raise RuntimeError("batch.pkl not found after scope command")

        batch = pd.read_pickle(str(BATCH_PKL))

        # Split into categories
        lev_df = batch[batch["should_adjust_lvg"] != ""].copy()
        ratio_df = batch[batch["should_adjust_amt"] != ""].copy()
        commodity_df = batch[batch["name"].apply(lambda n: n.split("-")[0] in COMMODITY_SYMS)].copy()
        crypto_lev_df = lev_df[lev_df["name"].apply(lambda n: n.split("-")[0] not in COMMODITY_SYMS)].copy()
        crypto_ratio_df = ratio_df[ratio_df["name"].apply(lambda n: n.split("-")[0] not in COMMODITY_SYMS)].copy()

        lev_count = len(lev_df)
        ratio_count = len(ratio_df)
        commodity_count = len(commodity_df)

        # Build rule_blocks
        all_rows = _rows_from_df(batch, include_category=True)
        lev_rows = _rows_from_df(crypto_lev_df)
        ratio_rows = _rows_from_df(crypto_ratio_df)
        commodity_rows = _rows_from_df(commodity_df)

        rule_blocks = [
            {
                "ruleId": "all_changes",
                "title": "All Changes",
                "count": batch_count,
                "description": (
                    f"Contracts flagged by rule checks: leverage mismatch, ratio <10% or >50%, "
                    f"competitor cap. {batch_count} of {needs_adj} total model adjustments."
                ),
                "status": "warning" if batch_count > 0 else "pass",
                "table": {
                    "headers": ["INSTRUMENT", "CATEGORY", "CHANGE", "REASON", "PRIORITY"],
                    "rows": all_rows,
                },
            },
            {
                "ruleId": "leverage",
                "title": "Leverage",
                "count": lev_count,
                "category_group": "CRYPTO PERPS",
                "description": "Contracts where depth-based tier model suggests a leverage change.",
                "status": "warning" if lev_count > 0 else "pass",
                "table": {
                    "headers": ["INSTRUMENT", "CHANGE", "REASON", "PRIORITY"],
                    "rows": lev_rows,
                } if lev_rows else None,
            },
            {
                "ruleId": "ratio",
                "title": "Ratio",
                "count": ratio_count,
                "category_group": "CRYPTO PERPS",
                "description": "Contracts where inc_ratio is <10% (increment too tight) or >50% (too wide).",
                "status": "warning" if ratio_count > 0 else "pass",
                "table": {
                    "headers": ["INSTRUMENT", "CHANGE", "REASON", "PRIORITY"],
                    "rows": ratio_rows,
                } if ratio_rows else None,
            },
            {
                "ruleId": "equity",
                "title": "Equity",
                "count": 0,
                "category_group": "EQUITY PERPS",
                "description": "Equity perp review uses index robustness model. Run equity review separately.",
                "status": "pending",
                "table": None,
            },
            {
                "ruleId": "commodity",
                "title": "Commodity",
                "count": commodity_count,
                "category_group": "COMMODITIES",
                "description": f"{len(COMMODITY_SYMS)} instruments, {commodity_count} adjustments.",
                "status": "warning" if commodity_count > 0 else "pass",
                "table": {
                    "headers": ["INSTRUMENT", "CHANGE", "REASON", "PRIORITY"],
                    "rows": commodity_rows,
                } if commodity_rows else None,
            },
        ]

        overall_status = "warning" if batch_count > 0 else "pass"
        lev_up = breakdown.get("leverage_upgrade", 0)
        lev_dn = breakdown.get("leverage_downgrade", 0)
        amt_up = breakdown.get("amount_increase", 0)
        amt_dn = breakdown.get("amount_decrease", 0)

        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "mmr-futures",
            "status": overall_status,
            "summary": (
                f"{batch_count} adjustments found across {in_scope} instruments. "
                f"Leverage: ↑{lev_up} ↓{lev_dn}. Amount: ↑{amt_up} ↓{amt_dn}."
            ),
            "metrics": {
                "instruments_scanned": total_contracts,
                "ema_coverage": in_scope,
                "issues_found": batch_count,
                "source": "OKX Tiers + Depth SQL",
                "generated_at": now,
            },
            "metric_cards": [
                {"label": "Instruments", "value": str(total_contracts)},
                {"label": "In Scope", "value": str(in_scope)},
                {"label": "Adjustments", "value": str(batch_count)},
                {"label": "Source", "value": "Depth SQL + OKX API"},
            ],
            "rule_blocks": rule_blocks,
            "recommended_changes": None,
            "downloads": [],
            "markdown": (
                f"# MMR Futures Review\n\n"
                f"**Status:** {overall_status}\n\n"
                f"{batch_count} adjustments across {in_scope} in-scope instruments.\n"
            ),
            "error": None,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }

    def _pending_chapter(self, now: str, reason: str) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "mmr-futures",
            "status": "pending",
            "summary": reason,
            "metrics": {
                "instruments_scanned": 0, "ema_coverage": 0, "issues_found": 0,
                "source": "n/a", "generated_at": now,
            },
            "metric_cards": [
                {"label": "Instruments", "value": "0"},
                {"label": "In Scope", "value": "0"},
                {"label": "Adjustments", "value": "0"},
                {"label": "Source", "value": "n/a"},
            ],
            "rule_blocks": [],
            "recommended_changes": None,
            "downloads": [],
            "markdown": f"# MMR Futures Review\n\n**Pending:** {reason}\n",
            "error": None,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }

    def _error_chapter(self, now: str, error: str) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "mmr-futures",
            "status": "warning",
            "summary": f"MMR Futures review encountered an error: {error}",
            "metrics": {
                "instruments_scanned": 0, "ema_coverage": 0, "issues_found": 0,
                "source": "error", "generated_at": now,
            },
            "metric_cards": [
                {"label": "Instruments", "value": "0"},
                {"label": "In Scope", "value": "0"},
                {"label": "Adjustments", "value": "0"},
                {"label": "Source", "value": "error"},
            ],
            "rule_blocks": [],
            "recommended_changes": None,
            "downloads": [],
            "markdown": f"# MMR Futures Review\n\n**Error:** {error}\n",
            "error": error,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }
