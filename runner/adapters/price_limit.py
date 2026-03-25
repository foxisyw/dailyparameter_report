"""Price Limit adapter — full review with 4 rules.

Reuses core logic from daily_review.py (fetch, review, CSV generation)
but outputs the adapter contract schema instead of Lark cards.
"""

import csv
import io
import json
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# Create an unverified SSL context for macOS Python (certifi not always configured)
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except Exception:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

from .base import BaseAdapter

# ─── Config ─────────────────────────────────────────────────────────────────
TIMEOUT = 30
OKX_API = "https://www.okx.com/api/v5/public/instruments"
OKX_PRODUCTS_API = "https://www.okx.com/priapi/v5/public/products"
INST_TYPES = ["SPOT", "SWAP", "FUTURES"]
BATCH_SIZE = 50

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_FILE = PROJECT_ROOT / "params_cli" / "price_limits" / "assets_types.md"

# ─── Asset type defaults (from review methodology) ──────────────────────────
DEFAULTS = {
    "TradFi":           {"y_upper": 2,  "y_lower": 2,  "z_upper": 5,  "z_lower": 5},
    "Topcoins":         {"y_upper": 1,  "y_lower": 1,  "z_upper": 2,  "z_lower": 2},
    "Fiat":             {"y_upper": 1,  "y_lower": 1,  "z_upper": 2,  "z_lower": 2},
    "Altcoins_SWAP":    {"y_upper": 4,  "y_lower": 4,  "z_upper": 10, "z_lower": 30},
    "Altcoins_FUTURES": {"y_upper": 4,  "y_lower": 4,  "z_upper": 10, "z_lower": 30},
    "Altcoins_SPOT":    {"y_upper": 4,  "y_lower": 4,  "z_upper": 5,  "z_lower": 5},
}


def _log(msg: str):
    print(f"  [price-limit] {msg}", file=sys.stderr)


# ─── Stdlib HTTP helper ─────────────────────────────────────────────────────

def _api_get(url: str, params: dict | None = None) -> dict:
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = Request(url, headers={"User-Agent": "params-cli/1.0"})
    with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def _safe_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# ─── Data fetching ──────────────────────────────────────────────────────────

def fetch_instruments() -> list[dict]:
    all_inst = []
    for inst_type in INST_TYPES:
        _log(f"fetching {inst_type} instruments...")
        data = _api_get(OKX_API, {"instType": inst_type})
        if data.get("code") != "0":
            raise RuntimeError(f"OKX error for {inst_type}: {data.get('msg')}")
        for r in data["data"]:
            all_inst.append({
                "instId": r["instId"],
                "instType": r["instType"],
                "state": r.get("state", ""),
            })
    return all_inst


def fetch_xyz_params(instruments: list[dict]) -> list[dict]:
    by_type: dict[str, list[str]] = {}
    for inst in instruments:
        if inst["state"] != "live":
            continue
        by_type.setdefault(inst["instType"], []).append(inst["instId"])

    rows = []
    for inst_type, inst_ids in by_type.items():
        _log(f"fetching {inst_type} XYZ params ({len(inst_ids)} instruments)...")
        for i in range(0, len(inst_ids), BATCH_SIZE):
            batch = inst_ids[i : i + BATCH_SIZE]
            try:
                data = _api_get(OKX_PRODUCTS_API, {
                    "instType": inst_type,
                    "instId": ",".join(batch),
                    "includeType": "1",
                })
                if data.get("code") != "0" or not data.get("data"):
                    continue
                for r in data["data"]:
                    lpy1 = r.get("lpY1", "")
                    lpy2 = r.get("lpY2", "")
                    lpz1 = r.get("lpZ1", "")
                    lpz2 = r.get("lpZ2", "")
                    if not any([lpy1, lpy2, lpz1, lpz2]):
                        continue
                    rows.append({
                        "instId": r.get("instId", ""),
                        "instType": r.get("instType", inst_type),
                        "upper_Y_cap": _safe_float(lpy1),
                        "lower_Y_cap": _safe_float(lpy2),
                        "upper_Z_cap": _safe_float(lpz1),
                        "lower_Z_cap": _safe_float(lpz2),
                        # Keep raw values for CSV generation
                        "upper_X_cap": _safe_float(r.get("lpX1", "")),
                        "lower_X_cap": _safe_float(r.get("lpX2", "")),
                    })
            except Exception as e:
                _log(f"  batch failed: {e}")
    return rows


# ─── Asset map ──────────────────────────────────────────────────────────────

def load_asset_map() -> dict[str, str]:
    asset_map: dict[str, str] = {}
    if not ASSETS_FILE.exists():
        _log(f"Assets file not found: {ASSETS_FILE}")
        return asset_map
    current_type = ""
    for line in ASSETS_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("# "):
            current_type = line[2:].strip()
        elif line and current_type:
            asset_map[line.upper()] = current_type
    return asset_map


def get_asset_type(inst_id: str, asset_map: dict[str, str]) -> str:
    base = inst_id.split("-")[0].upper()
    return asset_map.get(base, "Altcoins")


def get_defaults(asset_type: str, inst_type: str) -> dict:
    if asset_type == "Altcoins":
        key = f"Altcoins_{inst_type}"
        return DEFAULTS.get(key, DEFAULTS["Altcoins_SPOT"])
    return DEFAULTS.get(asset_type, DEFAULTS["Altcoins_SPOT"])


# ─── Review rules ───────────────────────────────────────────────────────────

def run_review(xyz_list: list[dict], ema_data: dict, asset_map: dict[str, str]) -> dict:
    findings = {
        "rule1_buffer_tight": [],
        "rule2_basis_asymmetric": [],
        "rule3_consistency": [],
        "rule4_z_le_y": [],
    }

    for row in xyz_list:
        inst_id = row["instId"]
        inst_type = row["instType"]
        y_upper = row["upper_Y_cap"]
        y_lower = row["lower_Y_cap"]
        z_upper = row["upper_Z_cap"]
        z_lower = row["lower_Z_cap"]
        asset_type = get_asset_type(inst_id, asset_map)
        ema = ema_data.get(inst_id, {})

        # Rule 4: Z cap must be > Y cap
        if z_upper > 0 and y_upper > 0 and z_upper <= y_upper:
            defaults = get_defaults(asset_type, inst_type)
            findings["rule4_z_le_y"].append({
                "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                "y_cap": y_upper, "z_cap": z_upper,
                "issue": f"upper_Z({z_upper}) <= upper_Y({y_upper})",
                "suggestion": f"Set Y={defaults['y_upper']}%, Z={defaults['z_upper']}%",
            })
        if z_lower > 0 and y_lower > 0 and z_lower <= y_lower:
            defaults = get_defaults(asset_type, inst_type)
            findings["rule4_z_le_y"].append({
                "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                "y_cap": y_lower, "z_cap": z_lower,
                "issue": f"lower_Z({z_lower}) <= lower_Y({y_lower})",
                "suggestion": f"Set Y={defaults['y_lower']}%, Z={defaults['z_lower']}%",
            })

        # Rule 3: Asset-type consistency
        defaults = get_defaults(asset_type, inst_type)
        if asset_type == "Altcoins":
            if inst_type in ("SWAP", "FUTURES"):
                if y_upper > defaults["y_upper"] * 2:
                    findings["rule3_consistency"].append({
                        "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                        "current_y": y_upper, "current_z": z_upper,
                        "expected_y": defaults["y_upper"], "expected_z": defaults["z_upper"],
                        "issue": f"Y_upper({y_upper}%) too high for {asset_type} perp (typical <={defaults['y_upper']}%)",
                    })
                if z_upper > defaults["z_upper"] * 3:
                    findings["rule3_consistency"].append({
                        "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                        "current_y": y_upper, "current_z": z_upper,
                        "expected_y": defaults["y_upper"], "expected_z": defaults["z_upper"],
                        "issue": f"Z_upper({z_upper}%) unusually high for {asset_type} perp (typical ~{defaults['z_upper']}%)",
                    })
        elif asset_type in ("TradFi", "Topcoins", "Fiat"):
            if y_upper > 0 and (y_upper > defaults["y_upper"] * 3 or y_upper < defaults["y_upper"] * 0.1):
                findings["rule3_consistency"].append({
                    "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                    "current_y": y_upper, "current_z": z_upper,
                    "expected_y": defaults["y_upper"], "expected_z": defaults["z_upper"],
                    "issue": f"Y_upper({y_upper}%) out of range for {asset_type} (typical ~{defaults['y_upper']}%)",
                })
            if z_upper > 0 and (z_upper > defaults["z_upper"] * 3 or z_upper < defaults["z_upper"] * 0.1):
                findings["rule3_consistency"].append({
                    "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                    "current_y": y_upper, "current_z": z_upper,
                    "expected_y": defaults["y_upper"], "expected_z": defaults["z_upper"],
                    "issue": f"Z_upper({z_upper}%) out of range for {asset_type} (typical ~{defaults['z_upper']}%)",
                })

        # EMA-based rules (only if EMA data available for this instrument)
        if not ema:
            continue

        basis = ema.get("basis")
        spread = ema.get("spread")
        limit_up_buf = ema.get("limitUp_buffer")
        limit_dn_buf = ema.get("limitDn_buffer")

        # Rule 1: Buffer too tight
        if limit_up_buf is not None and limit_up_buf < 0:
            spread_pct = (spread * 100) if spread else 0
            y_spread = y_upper + y_lower
            detail = f"limitUp_buffer={limit_up_buf * 100:.2f}%"
            if spread and y_spread > 0 and spread_pct > y_spread * 0.5:
                detail += f", B/A spread({spread_pct:.2f}%) vs Y spread({y_spread:.1f}%)"
            findings["rule1_buffer_tight"].append({
                "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                "limitUp_buffer": limit_up_buf, "limitDn_buffer": limit_dn_buf,
                "issue": detail, "suggestion": "Widen Y caps",
            })
        if limit_dn_buf is not None and limit_dn_buf < 0:
            spread_pct = (spread * 100) if spread else 0
            y_spread = y_upper + y_lower
            detail = f"limitDn_buffer={limit_dn_buf * 100:.2f}%"
            if spread and y_spread > 0 and spread_pct > y_spread * 0.5:
                detail += f", B/A spread({spread_pct:.2f}%) vs Y spread({y_spread:.1f}%)"
            findings["rule1_buffer_tight"].append({
                "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                "limitUp_buffer": limit_up_buf, "limitDn_buffer": limit_dn_buf,
                "issue": detail, "suggestion": "Widen Y caps",
            })

        # Rule 2: Asymmetric basis with symmetric caps
        if basis is not None and abs(basis) > 0.001:
            basis_pct = basis * 100
            if basis > 0 and z_upper > 0 and basis_pct > z_upper * 0.5:
                findings["rule2_basis_asymmetric"].append({
                    "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                    "basis_pct": basis_pct, "z_cap": z_upper,
                    "issue": f"basis={basis_pct:.2f}% vs upper_Z={z_upper}%",
                    "suggestion": "Widen upper Z cap to accommodate basis",
                })
            elif basis < 0 and z_lower > 0 and abs(basis_pct) > z_lower * 0.5:
                findings["rule2_basis_asymmetric"].append({
                    "instId": inst_id, "instType": inst_type, "assetType": asset_type,
                    "basis_pct": basis_pct, "z_cap": z_lower,
                    "issue": f"basis={basis_pct:.2f}% vs lower_Z={z_lower}%",
                    "suggestion": "Widen lower Z cap to accommodate basis",
                })

    return findings


# ─── CSV generation (matches fetcher.py logic) ──────────────────────────────

def _pct_to_multiplier_upper(pct: float) -> str:
    return str(round(1 + pct / 100, 8))


def _pct_to_multiplier_lower(pct: float) -> str:
    return str(round(1 - pct / 100, 8))


def _format_task_object(inst_id: str, inst_type: str) -> str:
    if inst_type == "SPOT":
        return inst_id
    parts = inst_id.rsplit("-", 1)
    base = parts[0]
    suffix = parts[1] if len(parts) > 1 else ""
    base_parts = base.split("-")
    quote = base_parts[1] if len(base_parts) > 1 else ""
    margin_tag = "UM" if quote in ("USDT", "USDC") else "CM"
    if inst_type == "SWAP":
        return f"{base}_{margin_tag}-SWAP"
    return f"{base}_{margin_tag}-{suffix}"


def _generate_adjustment_csvs(
    xyz_list: list[dict],
    findings: dict,
    asset_map: dict[str, str],
) -> list[dict]:
    """Build adjustment CSVs for instruments that need changes.

    Returns a list of download dicts: {label, filename, content}.
    """
    # Collect instIds that have issues with suggested fixes
    needs_fix: dict[str, dict] = {}
    for f in findings["rule4_z_le_y"]:
        inst_id = f["instId"]
        if inst_id not in needs_fix:
            needs_fix[inst_id] = {}
    for f in findings["rule3_consistency"]:
        inst_id = f["instId"]
        if inst_id not in needs_fix:
            needs_fix[inst_id] = {}

    if not needs_fix:
        return []

    # Build a lookup from xyz_list
    xyz_map = {}
    for row in xyz_list:
        xyz_map[row["instId"]] = row

    spot_rows = []
    perp_rows = []

    for inst_id in needs_fix:
        row = xyz_map.get(inst_id)
        if row is None:
            continue
        inst_type = row["instType"]
        asset_type = get_asset_type(inst_id, asset_map)
        defaults = get_defaults(asset_type, inst_type)

        # Use defaults as the target values
        y_upper = defaults["y_upper"]
        y_lower = defaults["y_lower"]
        z_upper = defaults["z_upper"]
        z_lower = defaults["z_lower"]
        x_upper = row.get("upper_X_cap", 0)
        x_lower = row.get("lower_X_cap", 0)

        task_obj = _format_task_object(inst_id, inst_type)

        if inst_type == "SPOT":
            spot_rows.append({
                "Task Object": task_obj,
                "timeType": "IMMEDIATE",
                "Effective Time": "",
                "openMaxThresholdRate": _pct_to_multiplier_upper(x_upper),
                "openMinThresholdRate": _pct_to_multiplier_lower(x_lower),
                "limitMaxThresholdRate": _pct_to_multiplier_upper(y_upper),
                "limitMinThresholdRate": _pct_to_multiplier_lower(y_lower),
                "indexMaxThresholdRate": _pct_to_multiplier_upper(z_upper),
                "indexMinThresholdRate": _pct_to_multiplier_lower(z_lower),
            })
        else:
            perp_rows.append({
                "Task Object": task_obj,
                "timeType": "IMMEDIATE",
                "Effective Time": "",
                "openUpperLimit": _pct_to_multiplier_upper(x_upper),
                "openLowerLimit": _pct_to_multiplier_lower(x_lower),
                "afterOpenUpperLimit": _pct_to_multiplier_upper(y_upper),
                "afterOpenLowerLimit": _pct_to_multiplier_lower(y_lower),
                "afterOpenIndexUpperLimit": _pct_to_multiplier_upper(z_upper),
                "afterOpenIndexLowerLimit": _pct_to_multiplier_lower(z_lower),
                "preQuoteMaxJ1UpperLimit": "",
                "preQuoteMinJ2LowerLimit": "",
                "preQuoteC1": "",
                "preQuoteC2": "",
            })

    downloads = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")

    if spot_rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(spot_rows[0].keys()))
        writer.writeheader()
        writer.writerows(spot_rows)
        downloads.append({
            "label": f"Spot adjustment CSV ({len(spot_rows)} instruments)",
            "filename": f"pricelimit_adjustment_spot_{ts}.csv",
            "content": buf.getvalue(),
        })

    if perp_rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(perp_rows[0].keys()))
        writer.writeheader()
        writer.writerows(perp_rows)
        downloads.append({
            "label": f"Perp/Futures adjustment CSV ({len(perp_rows)} instruments)",
            "filename": f"pricelimit_adjustment_perp_{ts}.csv",
            "content": buf.getvalue(),
        })

    return downloads


# ─── Markdown report ────────────────────────────────────────────────────────

def _build_markdown(
    findings: dict,
    total: int,
    ema_coverage: int,
    status: str,
    now: str,
) -> str:
    lines = [
        "# Price Limit Review",
        "",
        f"**Generated:** {now}  ",
        f"**Status:** {status}  ",
        f"**Instruments scanned:** {total}  ",
        f"**EMA coverage:** {ema_coverage}  ",
        "",
    ]

    total_issues = sum(len(v) for v in findings.values())
    lines.append(f"**Total issues found:** {total_issues}")
    lines.append("")

    # Rule 1
    r1 = findings["rule1_buffer_tight"]
    lines.append("## Rule 1: Buffer Too Tight")
    if r1:
        lines.append(f"{len(r1)} issue(s) found.")
        lines.append("")
        lines.append("| INSTRUMENT | LIMITUP_BUFFER | LIMITDN_BUFFER | STATUS |")
        lines.append("|---|---|---|---|")
        for f in r1:
            up = f.get("limitUp_buffer")
            dn = f.get("limitDn_buffer")
            up_s = f"{up * 100:.2f}%" if up is not None else "n/a"
            dn_s = f"{dn * 100:.2f}%" if dn is not None else "n/a"
            lines.append(f"| {f['instId']} | {up_s} | {dn_s} | warning |")
    else:
        lines.append("All instruments passed.")
    lines.append("")

    # Rule 2
    r2 = findings["rule2_basis_asymmetric"]
    lines.append("## Rule 2: Asymmetric Basis")
    if r2:
        lines.append(f"{len(r2)} issue(s) found.")
        lines.append("")
        lines.append("| INSTRUMENT | BASIS_EMA | RELEVANT Z CAP | STATUS |")
        lines.append("|---|---|---|---|")
        for f in r2:
            lines.append(f"| {f['instId']} | {f['basis_pct']:.2f}% | {f['z_cap']}% | warning |")
    else:
        lines.append("All instruments passed.")
    lines.append("")

    # Rule 3
    r3 = findings["rule3_consistency"]
    lines.append("## Rule 3: Asset-Type Consistency")
    if r3:
        lines.append(f"{len(r3)} issue(s) found.")
        lines.append("")
        lines.append("| INSTRUMENT | CURRENT Y | CURRENT Z | EXPECTED Y | EXPECTED Z | STATUS |")
        lines.append("|---|---|---|---|---|---|")
        for f in r3:
            lines.append(
                f"| {f['instId']} | {f['current_y']}% | {f['current_z']}% "
                f"| {f['expected_y']}% | {f['expected_z']}% | warning |"
            )
    else:
        lines.append("All instruments passed.")
    lines.append("")

    # Rule 4
    r4 = findings["rule4_z_le_y"]
    lines.append("## Rule 4: Z Cap <= Y Cap")
    if r4:
        lines.append(f"{len(r4)} issue(s) found.")
        lines.append("")
        lines.append("| INSTRUMENT | Y CAP | Z CAP | STATUS |")
        lines.append("|---|---|---|---|")
        for f in r4:
            lines.append(f"| {f['instId']} | {f['y_cap']}% | {f['z_cap']}% | critical |")
    else:
        lines.append("All instruments passed.")
    lines.append("")

    return "\n".join(lines)


# ─── Adapter class ──────────────────────────────────────────────────────────

class PriceLimitAdapter(BaseAdapter):

    @property
    def slug(self) -> str:
        return "price-limit"

    @property
    def title(self) -> str:
        return "Price Limit Review"

    def execute(self, ema_data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        try:
            # 1. Fetch instruments
            instruments = fetch_instruments()
            xyz_list = fetch_xyz_params(instruments)
            _log(f"Loaded {len(xyz_list)} instruments with XYZ params")

            # 2. Load asset map
            asset_map = load_asset_map()
            _log(f"Asset map: {len(asset_map)} entries")

            # 3. EMA coverage
            ema_coverage = 0
            if ema_data and xyz_list:
                covered = sum(1 for r in xyz_list if r["instId"] in ema_data)
                ema_coverage = covered

            # 4. Run review
            findings = run_review(xyz_list, ema_data, asset_map)
            total_issues = sum(len(v) for v in findings.values())
            _log(f"Review complete: {total_issues} issues found")

            # 5. Determine status
            r4_count = len(findings["rule4_z_le_y"])
            if r4_count > 0 or total_issues > 10:
                status = "critical"
            elif total_issues > 0:
                status = "warning"
            else:
                status = "pass"

            # 6. Build rule blocks
            rule_blocks = self._build_rule_blocks(findings, ema_data)

            # 7. Build recommended changes
            rec_changes = self._build_recommended_changes(findings, xyz_list, asset_map)

            # 8. Generate adjustment CSVs
            downloads = _generate_adjustment_csvs(xyz_list, findings, asset_map)

            # 9. Build markdown
            markdown = _build_markdown(
                findings, len(xyz_list), ema_coverage, status, now,
            )

            return {
                "slug": self.slug,
                "title": self.title,
                "status": status,
                "summary": (
                    f"Scanned {len(xyz_list)} instruments. "
                    f"Found {total_issues} issue(s) across 4 rules."
                ),
                "metrics": {
                    "instruments_scanned": len(xyz_list),
                    "ema_coverage": ema_coverage,
                    "issues_found": total_issues,
                    "source": "OKX API (live)",
                    "generated_at": now,
                },
                "rule_blocks": rule_blocks,
                "recommended_changes": rec_changes,
                "downloads": downloads,
                "markdown": markdown,
                "error": None,
            }

        except Exception as exc:
            _log(f"ERROR: {exc}")
            return {
                "slug": self.slug,
                "title": self.title,
                "status": "critical",
                "summary": f"Adapter failed: {exc}",
                "metrics": {
                    "instruments_scanned": 0,
                    "ema_coverage": 0,
                    "issues_found": 0,
                    "source": "OKX API (live)",
                    "generated_at": now,
                },
                "rule_blocks": [],
                "recommended_changes": None,
                "downloads": [],
                "markdown": f"# Price Limit Review\n\n**Error:** {exc}\n",
                "error": str(exc),
            }

    # ── Rule block builders ─────────────────────────────────────────────

    def _build_rule_blocks(self, findings: dict, ema_data: dict) -> list[dict]:
        blocks = []

        # Rule 1: Buffer Too Tight
        r1 = findings["rule1_buffer_tight"]
        r1_status = "warning" if r1 else "pass"
        r1_table = None
        if r1:
            rows = []
            for f in r1:
                up = f.get("limitUp_buffer")
                dn = f.get("limitDn_buffer")
                up_s = f"{up * 100:.2f}%" if up is not None else "n/a"
                dn_s = f"{dn * 100:.2f}%" if dn is not None else "n/a"
                rows.append([f["instId"], up_s, dn_s, "warning"])
            r1_table = {
                "headers": ["INSTRUMENT", "LIMITUP_BUFFER", "LIMITDN_BUFFER", "STATUS"],
                "rows": rows,
            }
        blocks.append({
            "ruleId": "rule-1",
            "title": "Buffer Too Tight",
            "status": r1_status,
            "description": (
                "Flags instruments where the EMA-derived limit price is already "
                "breaching or very close to the Y cap boundary, indicating the "
                "buffer is too tight for current market conditions."
            ),
            "table": r1_table,
            "note": None if ema_data else "Skipped — no EMA data available.",
        })

        # Rule 2: Asymmetric Basis
        r2 = findings["rule2_basis_asymmetric"]
        r2_status = "warning" if r2 else "pass"
        r2_table = None
        if r2:
            rows = []
            for f in r2:
                rows.append([
                    f["instId"],
                    f"{f['basis_pct']:.2f}%",
                    f"{f['z_cap']}%",
                    "warning",
                ])
            r2_table = {
                "headers": ["INSTRUMENT", "BASIS_EMA", "RELEVANT Z CAP", "STATUS"],
                "rows": rows,
            }
        blocks.append({
            "ruleId": "rule-2",
            "title": "Asymmetric Basis",
            "status": r2_status,
            "description": (
                "Flags perp instruments where the EMA basis is large relative "
                "to the Z cap, suggesting the cap should be widened on one side "
                "to accommodate the persistent premium/discount."
            ),
            "table": r2_table,
            "note": None if ema_data else "Skipped — no EMA data available.",
        })

        # Rule 3: Asset-Type Consistency
        r3 = findings["rule3_consistency"]
        r3_status = "warning" if r3 else "pass"
        r3_table = None
        if r3:
            rows = []
            for f in r3:
                rows.append([
                    f["instId"],
                    f"{f['current_y']}%",
                    f"{f['current_z']}%",
                    f"{f['expected_y']}%",
                    f"{f['expected_z']}%",
                    "warning",
                ])
            r3_table = {
                "headers": [
                    "INSTRUMENT", "CURRENT Y", "CURRENT Z",
                    "EXPECTED Y", "EXPECTED Z", "STATUS",
                ],
                "rows": rows,
            }
        blocks.append({
            "ruleId": "rule-3",
            "title": "Asset-Type Consistency",
            "status": r3_status,
            "description": (
                "Checks whether each instrument's Y/Z caps are consistent with "
                "the standard ranges for its asset type classification."
            ),
            "table": r3_table,
            "note": None,
        })

        # Rule 4: Z Cap <= Y Cap
        r4 = findings["rule4_z_le_y"]
        r4_status = "critical" if r4 else "pass"
        r4_table = None
        if r4:
            rows = []
            for f in r4:
                rows.append([
                    f["instId"],
                    f"{f['y_cap']}%",
                    f"{f['z_cap']}%",
                    "critical",
                ])
            r4_table = {
                "headers": ["INSTRUMENT", "Y CAP", "Z CAP", "STATUS"],
                "rows": rows,
            }
        blocks.append({
            "ruleId": "rule-4",
            "title": "Z Cap <= Y Cap",
            "status": r4_status,
            "description": (
                "The Z (index) cap must always be strictly greater than the Y "
                "(limit) cap. If Z <= Y the price limit hierarchy is broken."
            ),
            "table": r4_table,
            "note": None,
        })

        return blocks

    def _build_recommended_changes(
        self,
        findings: dict,
        xyz_list: list[dict],
        asset_map: dict[str, str],
    ) -> dict | None:
        """Aggregate all findings into a recommended changes table."""
        rows = []

        for f in findings["rule4_z_le_y"]:
            inst_id = f["instId"]
            rows.append([
                inst_id,
                f["suggestion"],
                f"Z cap ({f['z_cap']}%) <= Y cap ({f['y_cap']}%)",
            ])

        for f in findings["rule3_consistency"]:
            inst_id = f["instId"]
            rows.append([
                inst_id,
                f"Set Y={f['expected_y']}%, Z={f['expected_z']}%",
                f["issue"],
            ])

        for f in findings["rule1_buffer_tight"]:
            rows.append([
                f["instId"],
                f["suggestion"],
                f["issue"],
            ])

        for f in findings["rule2_basis_asymmetric"]:
            rows.append([
                f["instId"],
                f["suggestion"],
                f["issue"],
            ])

        if not rows:
            return None

        # De-duplicate by instrument (keep first occurrence)
        seen = set()
        unique_rows = []
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0])
                unique_rows.append(row)

        return {
            "headers": ["INSTRUMENT", "CHANGE", "REASON"],
            "rows": unique_rows,
        }
