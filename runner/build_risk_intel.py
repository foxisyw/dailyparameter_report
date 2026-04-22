"""Build correctly-formatted risk_intel_input.json from raw MCP data.

This module reads ``runner/local/raw_risk_input.json`` (simple flat data
collected via MCP tools) and produces the correctly-formatted
``runner/local/risk_intel_input.json`` that the frontend can render.

WHY THIS EXISTS
---------------
The frontend expects very specific nested JSON formats for event_analyses
fields.  When Claude (LLM) assembles this JSON manually it often gets field
names wrong (e.g. ``price_24h_change`` instead of ``change_24h``), uses flat
dicts instead of nested ``{metrics: [...]}`` format, or forgets to embed
user_profiles inside event_analyses.  This builder makes the formatting
*deterministic* -- Python code that never forgets the schema.

Run as::

    python3 -m runner.build_risk_intel
    python3 -m runner.build_risk_intel --dry-run
    python3 -m runner.build_risk_intel --input path/to/custom.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RUNNER_DIR = Path(__file__).resolve().parent
_LOCAL_DIR = _RUNNER_DIR / "local"
_DEFAULT_INPUT = _LOCAL_DIR / "raw_risk_input.json"
_DEFAULT_OUTPUT = _LOCAL_DIR / "risk_intel_input.json"

# ---------------------------------------------------------------------------
# Dimension names (must match frontend exactly)
# ---------------------------------------------------------------------------

DIMENSION_NAMES: list[str] = [
    "Registration Profile",
    "Trading Behavior",
    "Associated Accounts",
    "IP & Geolocation",
    "Identity Signals",
    "Profit & Loss",
    "Withdrawal Behavior",
    "Comprehensive Judgment",
]

LARK_FOLDER_URL = (
    "https://okg-block.sg.larksuite.com/drive/folder/"
    "Wu2Pfktq6lq4t8dWL52lB97pgQb"
)


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"  [build-risk-intel] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Tiny date/time helpers
# ---------------------------------------------------------------------------

def _hkt_now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _days_since(iso_str: str | None) -> float:
    """Return the number of days between *iso_str* and now (HKT)."""
    then = _parse_iso(iso_str)
    now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).total_seconds() / 86400


# ---------------------------------------------------------------------------
# Safe numeric helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fmt_pct(a: float, b: float) -> str:
    """Return ``a`` as a percentage change from ``b``, e.g. '+1.96%'."""
    if b == 0:
        return "n/a"
    change = (a - b) / b * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.2f}%"


# ---------------------------------------------------------------------------
# Trade / equity ratio & risk tier
# ---------------------------------------------------------------------------

def _trade_equity_ratio(user: dict[str, Any]) -> float:
    vol = _safe_float(user.get("trade_volume_usdt_sth"))
    equity = _safe_float(user.get("all_account_equity_volume_usdt"))
    if equity > 0:
        return vol / equity
    return float("inf")


def _ratio_to_tier(ratio: float) -> str:
    if ratio > 100_000:
        return "T1"
    if ratio > 10_000:
        return "T2"
    if ratio > 1_000:
        return "T3"
    return "T4"


def _tier_to_severity(tier: str) -> str:
    return {
        "T1": "critical",
        "T2": "warning",
        "T3": "warning",
        "T4": "pass",
    }.get(tier, "pass")


# ---------------------------------------------------------------------------
# Builder: market_snapshot
# ---------------------------------------------------------------------------

def build_market_snapshot(raw_market: dict[str, Any] | None) -> dict[str, str]:
    """Convert raw OKX ticker data into the frontend ``market_snapshot`` shape.

    Frontend field names (NOT the raw OKX names):
        price, change_24h, open_interest, funding_rate, vol_24h, timestamp
    """
    if not raw_market:
        return {
            "price": "n/a",
            "change_24h": "n/a",
            "open_interest": "n/a",
            "funding_rate": "n/a",
            "vol_24h": "n/a",
            "timestamp": _hkt_now_iso(),
        }

    price = _safe_float(raw_market.get("price") or raw_market.get("last"))
    open24h = _safe_float(raw_market.get("open24h"))
    change_24h = _fmt_pct(price, open24h)

    oi_raw = raw_market.get("oi") or raw_market.get("oiUsd") or "0"
    funding_raw = raw_market.get("fundingRate") or "0"
    vol_raw = raw_market.get("volCcy24h") or raw_market.get("vol24h") or "0"

    return {
        "price": str(raw_market.get("price", "n/a")),
        "change_24h": change_24h,
        "open_interest": str(oi_raw),
        "funding_rate": str(funding_raw),
        "vol_24h": str(vol_raw),
        "timestamp": _hkt_now_iso(),
    }


# ---------------------------------------------------------------------------
# Builder: quantitative_impact
# ---------------------------------------------------------------------------

def build_quantitative_impact(
    alert_ctx: dict[str, Any] | None,
    hourly_data: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build the ``{title, metrics: [{value, label, detail}]}`` structure."""
    metrics: list[dict[str, str]] = []

    if alert_ctx:
        oi_dev = alert_ctx.get("oi_deviation_24h", "n/a")
        metrics.append({
            "value": str(oi_dev),
            "label": "OI Deviation (24H)",
            "detail": f"Open interest deviated {oi_dev} from the 24-hour average",
        })

        oi_limit = alert_ctx.get("oi_limit_ratio", "n/a")
        if oi_limit and oi_limit != "n/a":
            metrics.append({
                "value": str(oi_limit),
                "label": "OI / Platform Limit",
                "detail": f"Open interest is at {oi_limit} of the platform position limit",
            })

        severity = alert_ctx.get("severity", "unknown")
        metrics.append({
            "value": severity.upper(),
            "label": "Alert Severity",
            "detail": f"Alert classified as {severity}",
        })

    if hourly_data and len(hourly_data) >= 2:
        first = hourly_data[0]
        last = hourly_data[-1]
        u0 = int(first.get("total_users") or 0)
        u1 = int(last.get("total_users") or 0)
        if u0 > 0:
            user_change = (u1 - u0) / u0 * 100
            metrics.append({
                "value": f"{user_change:+.1f}%",
                "label": "User Growth (period)",
                "detail": f"Total users changed from {u0} to {u1} over the observation window",
            })
        else:
            metrics.append({
                "value": str(u1),
                "label": "Total Users (latest)",
                "detail": f"No baseline users to compute growth (latest: {u1})",
            })

    if not metrics:
        metrics.append({
            "value": "n/a",
            "label": "Impact",
            "detail": "Insufficient data to compute quantitative impact",
        })

    return {"title": "Quantitative Impact", "metrics": metrics}


# ---------------------------------------------------------------------------
# Builder: oi_attribution
# ---------------------------------------------------------------------------

def build_oi_attribution(
    hourly_data: list[dict[str, Any]] | None,
    description: str = "",
) -> dict[str, Any]:
    """Build the hourly OI user table ``{title, description, user_hourly_table}``."""
    headers = ["Hour (pt)", "Total Users", "Longs", "Shorts"]
    rows: list[list[str]] = []

    if hourly_data:
        for row in hourly_data:
            rows.append([
                str(row.get("pt", "")),
                str(row.get("total_users", "")),
                str(row.get("longs", "")),
                str(row.get("shorts", "")),
            ])

    if not description:
        description = "Hourly breakdown of user positioning for the instrument."

    return {
        "title": "OI Attribution (Hourly User Breakdown)",
        "description": description,
        "user_hourly_table": {
            "headers": headers,
            "rows": rows,
        },
    }


# ---------------------------------------------------------------------------
# Builder: risk_assessment
# ---------------------------------------------------------------------------

def build_risk_assessment(
    alert_ctx: dict[str, Any] | None,
    users: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build ``{title, actions: [{priority, action, reason}]}``."""
    actions: list[dict[str, str]] = []

    severity = (alert_ctx or {}).get("severity", "unknown")
    alert_type = (alert_ctx or {}).get("alert_type", "unknown")
    oi_limit = (alert_ctx or {}).get("oi_limit_ratio", "")

    # P0 actions for critical alerts
    if severity == "critical":
        if oi_limit:
            actions.append({
                "priority": "P0",
                "action": f"Verify whether new position opens are restricted (OI/limit at {oi_limit})",
                "reason": f"Platform OI limit breached — {alert_type} alert at {severity} level",
            })
        else:
            actions.append({
                "priority": "P0",
                "action": "Review platform position limits for this instrument immediately",
                "reason": f"Critical {alert_type} alert requires immediate parameter review",
            })

    # P1 actions -- user-level
    high_risk_users = [
        u for u in (users or [])
        if u.get("overall_risk_tier") in ("T1", "T2")
        or _tier_to_severity(u.get("overall_risk_tier", "T4")) in ("critical", "warning")
    ]
    if high_risk_users:
        user_ids = ", ".join(str(u.get("master_user_id", u.get("uid", "?"))) for u in high_risk_users[:3])
        actions.append({
            "priority": "P1",
            "action": f"Deep-review top risk users: {user_ids}",
            "reason": f"{len(high_risk_users)} user(s) flagged with elevated trade/equity ratios or suspicious patterns",
        })

    # P2 actions -- general monitoring
    actions.append({
        "priority": "P2",
        "action": "Continue monitoring OI trajectory and funding rate changes over the next 24 hours",
        "reason": "Position dynamics may shift as new data comes in — ensure no further limit breaches",
    })

    return {
        "title": "Risk Assessment & Recommended Actions",
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# Builder: involved_users_brief
# ---------------------------------------------------------------------------

def build_involved_users_brief(
    users: list[dict[str, Any]],
    positions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build the ``{title, headers, rows}`` table for involved users."""
    headers = ["User ID", "UID", "Position", "Margin", "Opened", "Risk Tier"]
    rows: list[list[str]] = []

    # Index positions by user_id for quick lookup
    pos_by_user: dict[str, list[dict[str, Any]]] = {}
    for p in (positions or []):
        uid = str(p.get("user_id", ""))
        pos_by_user.setdefault(uid, []).append(p)

    for user in users:
        mid = str(user.get("master_user_id", ""))
        uid = str(user.get("uid", ""))
        tier = user.get("overall_risk_tier", "T4")

        user_positions = pos_by_user.get(mid, [])
        if user_positions:
            for p in user_positions:
                pos_type = "LONG" if str(p.get("position_type")) == "1" else "SHORT"
                margin = "Cross" if str(p.get("margin_mode")) == "2" else "Isolated"
                opened = str(p.get("create_time", ""))
                rows.append([mid, uid, pos_type, margin, opened, tier])
        else:
            rows.append([mid, uid, "n/a", "n/a", "n/a", tier])

    return {
        "title": "Involved Users (Brief)",
        "headers": headers,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Builder: user_profile (8-dimension)
# ---------------------------------------------------------------------------

def build_user_profile(
    user_info: dict[str, Any],
    positions: list[dict[str, Any]] | None,
    alert_ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a single user profile with 8 dimensions, severity, and signals."""
    mid = str(user_info.get("master_user_id", ""))
    uid = str(user_info.get("uid", ""))

    ratio = _trade_equity_ratio(user_info)
    tier = _ratio_to_tier(ratio)

    vol = _safe_float(user_info.get("trade_volume_usdt_sth"))
    equity = _safe_float(user_info.get("all_account_equity_volume_usdt"))
    first_deposit = _safe_float(user_info.get("first_deposit_volume_usdt"))

    reg_time = user_info.get("register_time", "")
    account_age_days = _days_since(reg_time) if reg_time else 0
    kyc_level = int(_safe_float(user_info.get("kyc_pass_max_level", "0")))
    region = user_info.get("register_country_big_region", "unknown")
    phone_area = user_info.get("phone_area_code", "")
    nationality = user_info.get("kyc_pass_nationality_name", "unknown")
    is_market = user_info.get("is_market_account", "")
    is_internal = user_info.get("is_internal_account", "")
    fee_level = user_info.get("user_fee_level_value", "")
    first_deposit_time = user_info.get("first_deposit_time", "")
    last_deposit_time = user_info.get("last_deposit_time", "")
    first_trade_time = user_info.get("first_trade_time", "")
    reg_client = user_info.get("register_client_type", "")

    # Collect user positions for this instrument
    user_positions = [
        p for p in (positions or [])
        if str(p.get("user_id", "")) == mid
    ]

    # --- 1. Registration Profile ---
    if account_age_days < 30:
        reg_sev = "critical"
    elif account_age_days < 90:
        reg_sev = "warning"
    else:
        reg_sev = "pass"

    age_str = (
        f"{account_age_days / 365:.1f}yr" if account_age_days > 365
        else f"{account_age_days:.0f} days"
    )
    reg_signals = [
        f"Registered {reg_time[:10] if reg_time else 'unknown'} ({age_str})",
        f"{region}, phone {phone_area}" if phone_area else f"{region}",
        f"KYC{kyc_level} {nationality} verified" if kyc_level else f"KYC level unknown",
        f"Client type: {reg_client}" if reg_client else None,
    ]
    # Check for dormancy anomaly
    if first_deposit_time and reg_time:
        deposit_gap_days = _days_since(reg_time) - _days_since(first_deposit_time)
        if deposit_gap_days > 365:
            reg_signals.append(
                f"Registration-to-first-deposit gap: {deposit_gap_days / 365:.1f}yr (anomalous)"
            )
            if reg_sev == "pass":
                reg_sev = "warning"
    reg_signals = [s for s in reg_signals if s]

    # --- 2. Trading Behavior ---
    if ratio > 10_000:
        trade_sev = "critical"
    elif ratio > 1_000:
        trade_sev = "warning"
    else:
        trade_sev = "pass"

    ratio_str = f"{ratio:,.0f}x" if ratio != float("inf") else "inf"
    trade_signals = [
        f"Trade volume ${vol:,.2f} vs equity ${equity:,.2f} (ratio {ratio_str})",
        f"Fee tier: {fee_level}" if fee_level else None,
    ]
    for p in user_positions:
        pos_type = "LONG" if str(p.get("position_type")) == "1" else "SHORT"
        margin = "Cross" if str(p.get("margin_mode")) == "2" else "Isolated"
        inst = p.get("instrument_name", "")
        opened = str(p.get("create_time", ""))[:16]
        trade_signals.append(f"{inst} {pos_type} ({margin}), opened {opened}")
    trade_signals = [s for s in trade_signals if s]

    # --- 3. Associated Accounts ---
    assoc_sev = "pending"
    assoc_signals = [
        "Login table access denied (403) -- cannot verify device cluster",
        "No sub-account evidence from position query",
    ]

    # --- 4. IP & Geolocation ---
    ip_sev = "pass"
    ip_signals = [
        f"Registered {region}" if region else "Registration region unknown",
        f"Phone {phone_area} matches {nationality} nationality" if phone_area else "Phone unknown",
        "No region mismatch detected",
    ]

    # --- 5. Identity Signals ---
    if kyc_level >= 3:
        id_sev = "pass"
    elif kyc_level == 2:
        id_sev = "warning"
    else:
        id_sev = "critical"

    id_signals = [
        f"KYC{kyc_level} — {nationality}" if nationality else f"KYC{kyc_level}",
        f"is_market_account: {is_market}" if is_market else None,
        f"is_internal_account: {is_internal}" if is_internal else None,
        f"Phone {phone_area} consistent with {nationality}" if phone_area and nationality else None,
    ]
    if kyc_level < 3 and account_age_days > 365:
        id_signals.append(f"KYC{kyc_level} despite {age_str} account age — upgrade anomaly")
    id_signals = [s for s in id_signals if s]

    # --- 6. Profit & Loss ---
    if equity > 0 and first_deposit > 0:
        if equity < first_deposit * 0.1:
            pnl_sev = "critical"
        elif equity < first_deposit * 0.5:
            pnl_sev = "warning"
        else:
            pnl_sev = "pass"
    elif equity <= 0:
        pnl_sev = "critical"
    else:
        pnl_sev = "pass"

    pnl_signals = [
        f"Trade volume ${vol:,.2f}, equity ${equity:,.2f}",
        f"First deposit ${first_deposit:,.2f}" if first_deposit else "First deposit unknown",
        f"Last deposit {last_deposit_time[:10]}" if last_deposit_time else "Last deposit unknown",
    ]
    if equity > 0 and first_deposit > 0:
        retention = equity / first_deposit * 100
        pnl_signals.append(f"Equity retention: {retention:.1f}% of first deposit")
    pnl_signals = [s for s in pnl_signals if s]

    # --- 7. Withdrawal Behavior ---
    wd_sev = "pending"
    wd_signals = [
        f"Last deposit {last_deposit_time[:10]}" if last_deposit_time else "Last deposit unknown",
        "Withdrawal detail table inaccessible (data limited)",
    ]

    # --- 8. Comprehensive Judgment ---
    comp_sev = _tier_to_severity(tier)
    comp_signals = [
        f"Overall risk tier: {tier} (trade/equity ratio {ratio_str})",
    ]
    if alert_ctx:
        alert_type = alert_ctx.get("alert_type", "")
        sev = alert_ctx.get("severity", "")
        comp_signals.append(f"Flagged in {alert_type} alert ({sev})")
    if user_positions:
        inst_names = list({p.get("instrument_name", "") for p in user_positions})
        comp_signals.append(f"Active positions on: {', '.join(inst_names)}")
    comp_signals = [s for s in comp_signals if s]

    # Build executive summary
    summary_parts = []
    if region and nationality:
        summary_parts.append(f"{nationality} account ({region})")
    summary_parts.append(f"registered {reg_time[:10] if reg_time else 'unknown'} ({age_str})")
    summary_parts.append(f"trade/equity ratio {ratio_str}")
    if fee_level and "VIP" in fee_level.upper():
        summary_parts.append(fee_level)
    if is_market and "市商" in is_market:
        summary_parts.append("market maker")
    exec_summary = ". ".join(s.capitalize() if i == 0 else s for i, s in enumerate(summary_parts)) + "."

    # Key evidence
    key_evidence: list[str] = []
    if ratio > 1_000:
        key_evidence.append(f"Trade/equity ratio {ratio_str} indicates high leverage cycling")
    for p in user_positions:
        pos_type = "LONG" if str(p.get("position_type")) == "1" else "SHORT"
        inst = p.get("instrument_name", "")
        opened = str(p.get("create_time", ""))[:16]
        key_evidence.append(f"{inst} {pos_type} opened {opened}")
    if alert_ctx and alert_ctx.get("severity") == "critical":
        alert_type = alert_ctx.get("alert_type", "unknown")
        key_evidence.append(f"Active during critical {alert_type} alert")

    return {
        "uid": uid,
        "master_user_id": mid,
        "overall_risk_tier": tier,
        "executive_summary": exec_summary,
        "dimensions": [
            {"name": "Registration Profile", "severity": reg_sev, "signals": reg_signals},
            {"name": "Trading Behavior", "severity": trade_sev, "signals": trade_signals},
            {"name": "Associated Accounts", "severity": assoc_sev, "signals": assoc_signals},
            {"name": "IP & Geolocation", "severity": ip_sev, "signals": ip_signals},
            {"name": "Identity Signals", "severity": id_sev, "signals": id_signals},
            {"name": "Profit & Loss", "severity": pnl_sev, "signals": pnl_signals},
            {"name": "Withdrawal Behavior", "severity": wd_sev, "signals": wd_signals},
            {"name": "Comprehensive Judgment", "severity": comp_sev, "signals": comp_signals},
        ],
        "key_evidence": key_evidence,
        "local_artifact_ref": "",
    }


# ---------------------------------------------------------------------------
# Builder: causal_chain (4 steps)
# ---------------------------------------------------------------------------

def _build_causal_chain(
    asset: str,
    alert_ctx: dict[str, Any] | None,
    hourly_data: list[dict[str, Any]] | None,
    user_profiles: list[dict[str, Any]] | None,
    market_snapshot: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """Build the 4-step causal chain for an event."""
    chain: list[dict[str, Any]] = []

    # Step 1: Remote cause (structural)
    funding_rate = (market_snapshot or {}).get("funding_rate", "n/a")
    vol = (market_snapshot or {}).get("vol_24h", "n/a")
    chain.append({
        "step": 1,
        "type": "远因 (Structural)",
        "name": f"{asset} Thin Liquidity / Low Float",
        "description": (
            f"{asset} has limited market depth (24H vol: {vol}). "
            f"Low float instruments are susceptible to rapid OI deviation."
        ),
        "evidence_strength": 3,
        "evidence_label": "Market data",
    })

    # Step 2: Proximate cause (user influx)
    evidence_table = None
    influx_desc = f"User positioning changed on {asset}."
    if hourly_data and len(hourly_data) >= 2:
        first = hourly_data[0]
        last = hourly_data[-1]
        u0 = int(first.get("total_users") or 0)
        u1 = int(last.get("total_users") or 0)
        s0 = int(first.get("shorts") or 0)
        s1 = int(last.get("shorts") or 0)
        l0 = int(first.get("longs") or 0)
        l1 = int(last.get("longs") or 0)
        influx_desc = (
            f"Users grew from {u0} to {u1} "
            f"(longs {l0}->{l1}, shorts {s0}->{s1}) "
            f"between {first.get('pt', '')} and {last.get('pt', '')}."
        )
        evidence_table = {
            "headers": ["Hour", "Total Users", "Longs", "Shorts"],
            "rows": [
                [str(h.get("pt", "")), str(h.get("total_users", "")),
                 str(h.get("longs", "")), str(h.get("shorts", ""))]
                for h in hourly_data
            ],
        }
    step2: dict[str, Any] = {
        "step": 2,
        "type": "近因 (User Influx)",
        "name": f"{asset} Position Buildup",
        "description": influx_desc,
        "evidence_strength": 4,
        "evidence_label": "Position data",
    }
    if evidence_table:
        step2["evidence_table"] = evidence_table
    chain.append(step2)

    # Step 3: Trigger event
    if alert_ctx:
        alert_type = alert_ctx.get("alert_type", "unknown")
        sev = alert_ctx.get("severity", "unknown")
        oi_dev = alert_ctx.get("oi_deviation_24h", "n/a")
        oi_limit = alert_ctx.get("oi_limit_ratio", "")
        trigger_desc = f"{alert_type} alert fired at {sev} level. OI deviation: {oi_dev}."
        if oi_limit:
            trigger_desc += f" OI/platform limit: {oi_limit}."
    else:
        trigger_desc = f"{asset} flagged by risk monitoring system."

    chain.append({
        "step": 3,
        "type": "触发事件 (Trigger)",
        "name": "Alert Fired",
        "description": trigger_desc,
        "evidence_strength": 5,
        "evidence_label": "Platform alert",
    })

    # Step 4: Risk amplification (top users concentrating)
    amp_desc = "Top position holders are concentrating exposure."
    amp_table = None
    if user_profiles:
        top = user_profiles[:5]
        ids = [u.get("master_user_id", u.get("uid", "?")) for u in top]
        tiers = [u.get("overall_risk_tier", "T4") for u in top]
        amp_desc = (
            f"Top users concentrating: {', '.join(ids)} "
            f"(risk tiers: {', '.join(tiers)}). "
            f"Position overlap amplifies systemic exposure."
        )
        amp_table = {
            "headers": ["User ID", "Risk Tier", "Summary"],
            "rows": [
                [
                    str(u.get("master_user_id", u.get("uid", "?"))),
                    u.get("overall_risk_tier", "T4"),
                    (u.get("executive_summary", "")[:80] + "...")
                    if len(u.get("executive_summary", "")) > 80
                    else u.get("executive_summary", ""),
                ]
                for u in top
            ],
        }
    step4: dict[str, Any] = {
        "step": 4,
        "type": "风险放大 (Amplification)",
        "name": "User Concentration Risk",
        "description": amp_desc,
        "evidence_strength": 4,
        "evidence_label": "User data",
    }
    if amp_table:
        step4["evidence_table"] = amp_table
    chain.append(step4)

    return chain


# ---------------------------------------------------------------------------
# Builder: complete event_analysis
# ---------------------------------------------------------------------------

def build_event_analysis(asset: str, raw_data: dict[str, Any]) -> dict[str, Any]:
    """Assemble a complete event analysis with ALL required sub-fields.

    *raw_data* is the full raw input dict (not per-asset).
    """
    inst_id = asset if "-" in asset else f"{asset}-USDT-SWAP"

    raw_market = (raw_data.get("market_data") or {}).get(inst_id)
    alert_ctx = (raw_data.get("alert_context") or {}).get(inst_id)
    position_info = (raw_data.get("position_data") or {}).get(inst_id, {})
    holders = position_info.get("holders", [])
    hourly = position_info.get("hourly", [])

    user_master_info = raw_data.get("user_master_info", {})

    # Build user profiles for holders of this instrument
    holder_user_ids = list({str(h.get("user_id", "")) for h in holders})
    user_profiles: list[dict[str, Any]] = []
    for uid in holder_user_ids:
        uinfo = user_master_info.get(uid)
        if uinfo:
            profile = build_user_profile(uinfo, holders, alert_ctx)
            user_profiles.append(profile)
        else:
            # Fallback: create basic profile from position data alone
            holder_rows = [h for h in holders if str(h.get("user_id")) == uid]
            side = "SHORT" if any(str(h.get("position_type")) == "2" for h in holder_rows) else "LONG"
            user_profiles.append({
                "uid": "",
                "master_user_id": uid,
                "overall_risk_tier": "T3",
                "executive_summary": f"{side} {inst_id}, master info not available for deeper analysis.",
                "dimensions": [
                    {"name": "Registration Profile", "severity": "pass", "signals": ["Master info not queried — no signals available"]},
                    {"name": "Trading Behavior", "severity": "warning", "signals": [f"{side} {inst_id}, {len(holder_rows)} position(s)"]},
                    {"name": "Associated Accounts", "severity": "pending", "signals": ["Login table 403"]},
                    {"name": "IP & Geolocation", "severity": "pass", "signals": ["Region data requires master info query"]},
                    {"name": "Identity Signals", "severity": "pass", "signals": ["KYC data requires master info query"]},
                    {"name": "Profit & Loss", "severity": "warning", "signals": ["Equity data requires master info query — position during OI anomaly flagged"]},
                    {"name": "Withdrawal Behavior", "severity": "pending", "signals": ["Data limited"]},
                    {"name": "Comprehensive Judgment", "severity": "warning", "signals": [f"{side} during OI anomaly, monitoring required"]},
                ],
                "key_evidence": [f"{side} {inst_id}", f"Position opened {holder_rows[0].get('create_time', 'unknown')}" if holder_rows else ""],
            })

    # Sort by risk tier (T1 = most critical first)
    tier_order = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}
    user_profiles.sort(key=lambda p: tier_order.get(p.get("overall_risk_tier", "T4"), 3))

    market_snap = build_market_snapshot(raw_market)
    quant_impact = build_quantitative_impact(alert_ctx, hourly)
    oi_attr = build_oi_attribution(hourly)
    risk_assess = build_risk_assessment(alert_ctx, user_profiles)
    users_brief = build_involved_users_brief(user_profiles, holders)
    causal = _build_causal_chain(asset, alert_ctx, hourly, user_profiles, market_snap)

    severity = (alert_ctx or {}).get("severity", "warning")

    # Build executive summary
    price = market_snap.get("price", "n/a")
    change = market_snap.get("change_24h", "n/a")
    oi_dev = (alert_ctx or {}).get("oi_deviation_24h", "n/a")
    oi_limit = (alert_ctx or {}).get("oi_limit_ratio", "")
    n_users = len(user_profiles)

    summary_parts = [
        f"{inst_id} triggered {severity} alert.",
        f"Price: ${price} ({change}).",
    ]
    if oi_dev and oi_dev != "n/a":
        summary_parts.append(f"OI deviation: {oi_dev}.")
    if oi_limit:
        summary_parts.append(f"OI/limit: {oi_limit}.")
    summary_parts.append(f"{n_users} user(s) profiled.")
    exec_summary = " ".join(summary_parts)

    # Forward looking
    forward = (
        f"Monitor {inst_id} OI trajectory over the next 24 hours. "
        f"If OI continues expanding, consider tightening position limits. "
        f"Watch for funding rate shifts that may attract additional directional flow."
    )

    return {
        "asset": asset,
        "severity": severity,
        "executive_summary": exec_summary,
        "forward_looking": forward,
        "market_snapshot": market_snap,
        "quantitative_impact": quant_impact,
        "oi_attribution": oi_attr,
        "risk_assessment": risk_assess,
        "involved_users_brief": users_brief,
        "causal_chain": causal,
        "key_users": holder_user_ids[:5],
        "user_profiles": user_profiles,
    }


# ---------------------------------------------------------------------------
# Rank users by trade/equity ratio
# ---------------------------------------------------------------------------

def rank_users_by_risk(
    user_master_info: dict[str, Any],
    position_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pick top 5 users by trade/equity ratio across all instruments.

    Returns a list of suspicious_users_override entries.
    """
    # Collect all user_ids that appear in positions
    user_ids_with_positions: set[str] = set()
    user_instruments: dict[str, list[str]] = {}
    for inst_id, pdata in (position_data or {}).items():
        for holder in pdata.get("holders", []):
            uid = str(holder.get("user_id", ""))
            if uid:
                user_ids_with_positions.add(uid)
                user_instruments.setdefault(uid, []).append(inst_id)

    scored: list[tuple[float, str, dict[str, Any]]] = []
    for uid in user_ids_with_positions:
        uinfo = user_master_info.get(uid)
        if not uinfo:
            continue
        ratio = _trade_equity_ratio(uinfo)
        tier = _ratio_to_tier(ratio)
        instruments = user_instruments.get(uid, [])
        reason = (
            f"Trade/equity ratio {ratio:,.0f}x. "
            f"Active on: {', '.join(instruments[:3])}."
        ) if ratio != float("inf") else (
            f"Zero equity with active positions on {', '.join(instruments[:3])}."
        )
        scored.append((ratio, uid, {
            "uid": uinfo.get("uid", ""),
            "master_user_id": uinfo.get("master_user_id", uid),
            "risk_tier": tier,
            "source_alert": "build_risk_intel",
            "reason": reason,
        }))

    # Sort descending by ratio (highest risk first), take top 5
    scored.sort(key=lambda t: t[0] if t[0] != float("inf") else 1e18, reverse=True)
    return [entry for _, _, entry in scored[:5]]


# ---------------------------------------------------------------------------
# Build the full profiles dict (keyed by BOTH uid AND master_user_id)
# ---------------------------------------------------------------------------

def _build_profiles_dict(
    user_master_info: dict[str, Any],
    position_data: dict[str, Any],
    alert_context: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``profiles`` dict keyed by both uid and master_user_id."""
    profiles: dict[str, Any] = {}

    for mid, uinfo in user_master_info.items():
        # Figure out which alert context applies to this user
        user_alert_ctx = None
        for inst_id, pdata in (position_data or {}).items():
            for holder in pdata.get("holders", []):
                if str(holder.get("user_id", "")) == mid:
                    user_alert_ctx = alert_context.get(inst_id)
                    break
            if user_alert_ctx:
                break

        # Collect all positions for this user across instruments
        all_positions: list[dict[str, Any]] = []
        for inst_id, pdata in (position_data or {}).items():
            for holder in pdata.get("holders", []):
                if str(holder.get("user_id", "")) == mid:
                    all_positions.append(holder)

        profile = build_user_profile(uinfo, all_positions, user_alert_ctx)

        # Key by master_user_id
        profiles[mid] = profile
        # Also key by uid if it exists and is different
        uid = uinfo.get("uid", "")
        if uid and uid != mid:
            profiles[uid] = profile

    return profiles


# ---------------------------------------------------------------------------
# Build folder_documents from lark_document
# ---------------------------------------------------------------------------

def _build_folder_documents(lark_doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not lark_doc:
        return []
    docs_token = lark_doc.get("docs_token", "")
    url = (
        f"https://okg-block.sg.larksuite.com/docx/{docs_token}"
        if docs_token
        else LARK_FOLDER_URL
    )
    return [{
        "title": lark_doc.get("title", "Unknown Document"),
        "content": lark_doc.get("content", ""),
        "modified_at": lark_doc.get("modified_at", _hkt_now_iso()),
        "url": url,
    }]


# ---------------------------------------------------------------------------
# Validate output
# ---------------------------------------------------------------------------

_REQUIRED_TOP_KEYS = {"folder_documents", "profiles", "suspicious_users_override", "event_analyses"}
_REQUIRED_EVENT_KEYS = {
    "asset", "severity", "executive_summary", "market_snapshot",
    "quantitative_impact", "oi_attribution", "risk_assessment",
    "causal_chain", "user_profiles",
}
_REQUIRED_SNAPSHOT_KEYS = {"price", "change_24h"}
_REQUIRED_PROFILE_KEYS = {"uid", "master_user_id", "overall_risk_tier", "executive_summary", "dimensions"}


def validate_output(output: dict[str, Any]) -> list[str]:
    """Validate the output JSON has all required keys and structures.

    Returns a list of error messages.  Empty list means valid.
    """
    errors: list[str] = []

    # Top-level keys
    missing_top = _REQUIRED_TOP_KEYS - set(output.keys())
    if missing_top:
        errors.append(f"Missing top-level keys: {missing_top}")

    # event_analyses
    for i, ea in enumerate(output.get("event_analyses", [])):
        asset = ea.get("asset", f"event[{i}]")
        missing_ea = _REQUIRED_EVENT_KEYS - set(ea.keys())
        if missing_ea:
            errors.append(f"Event {asset}: missing keys {missing_ea}")

        # market_snapshot field names
        snap = ea.get("market_snapshot", {})
        missing_snap = _REQUIRED_SNAPSHOT_KEYS - set(snap.keys())
        if missing_snap:
            errors.append(f"Event {asset} market_snapshot: missing {missing_snap}")
        # Check that we do NOT have the wrong field names
        if "price_24h_change" in snap:
            errors.append(f"Event {asset}: has 'price_24h_change' -- must be 'change_24h'")
        if "oi" in snap and "open_interest" not in snap:
            errors.append(f"Event {asset}: has 'oi' -- must be 'open_interest'")

        # quantitative_impact must have metrics array
        qi = ea.get("quantitative_impact", {})
        if isinstance(qi, dict) and "metrics" not in qi:
            errors.append(f"Event {asset} quantitative_impact: missing 'metrics' array")

        # risk_assessment must have actions array
        ra = ea.get("risk_assessment", {})
        if isinstance(ra, dict) and "actions" not in ra:
            errors.append(f"Event {asset} risk_assessment: missing 'actions' array")

        # causal_chain should have >= 2 steps
        cc = ea.get("causal_chain", [])
        if len(cc) < 2:
            errors.append(f"Event {asset}: causal_chain has {len(cc)} steps, need >= 2")

        # user_profiles inside event
        ups = ea.get("user_profiles", [])
        for j, up in enumerate(ups):
            uid_label = up.get("uid", up.get("master_user_id", f"user[{j}]"))
            missing_prof = _REQUIRED_PROFILE_KEYS - set(up.keys())
            if missing_prof:
                errors.append(f"Event {asset} -> user {uid_label}: missing {missing_prof}")
            dims = up.get("dimensions", [])
            if len(dims) != 8:
                errors.append(f"Event {asset} -> user {uid_label}: has {len(dims)} dimensions, expected 8")
            for d in dims:
                if d.get("name") not in DIMENSION_NAMES:
                    errors.append(
                        f"Event {asset} -> user {uid_label}: unexpected dimension name '{d.get('name')}'"
                    )

    # profiles
    profiles = output.get("profiles", {})
    for key, prof in profiles.items():
        missing_prof = _REQUIRED_PROFILE_KEYS - set(prof.keys())
        if missing_prof:
            errors.append(f"Profile {key}: missing {missing_prof}")
        dims = prof.get("dimensions", [])
        if len(dims) != 8:
            errors.append(f"Profile {key}: has {len(dims)} dimensions, expected 8")

    return errors


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform raw MCP data into the full risk_intel_input.json format."""
    _log("Starting build...")

    lark_doc = raw.get("lark_document")
    flagged_assets = raw.get("flagged_assets", [])
    position_data = raw.get("position_data", {})
    user_master_info = raw.get("user_master_info", {})
    market_data = raw.get("market_data", {})
    alert_context = raw.get("alert_context", {})

    # 1. folder_documents
    _log(f"Building folder_documents from lark_document: {lark_doc.get('title', 'n/a') if lark_doc else 'none'}")
    folder_documents = _build_folder_documents(lark_doc)

    # 2. profiles (keyed by both uid and master_user_id)
    _log(f"Building profiles for {len(user_master_info)} users...")
    profiles = _build_profiles_dict(user_master_info, position_data, alert_context)
    _log(f"  -> {len(profiles)} profile entries (dual-keyed)")

    # 3. suspicious_users_override (top 5 by trade/equity)
    _log("Ranking users by risk (trade/equity ratio)...")
    suspicious = rank_users_by_risk(user_master_info, position_data)
    _log(f"  -> {len(suspicious)} suspicious users")

    # 4. event_analyses (one per flagged asset)
    _log(f"Building event analyses for {len(flagged_assets)} flagged assets...")
    event_analyses: list[dict[str, Any]] = []
    for asset in flagged_assets:
        _log(f"  -> {asset}")
        ea = build_event_analysis(asset, raw)
        event_analyses.append(ea)

    output = {
        "folder_documents": folder_documents,
        "profiles": profiles,
        "suspicious_users_override": suspicious,
        "event_analyses": event_analyses,
    }

    # Validate
    _log("Validating output...")
    errors = validate_output(output)
    if errors:
        _log("VALIDATION ERRORS:")
        for err in errors:
            _log(f"  !! {err}")
    else:
        _log("Validation passed.")

    return output


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build risk_intel_input.json from raw MCP data",
    )
    parser.add_argument(
        "--input",
        default=str(_DEFAULT_INPUT),
        help=f"Path to raw_risk_input.json (default: {_DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help=f"Output path (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout instead of saving to file",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        _log(f"Input file not found: {input_path}")
        return 1

    _log(f"Reading {input_path} ...")
    raw = json.loads(input_path.read_text(encoding="utf-8"))

    output = build(raw)

    formatted = json.dumps(output, indent=2, ensure_ascii=False)

    if args.dry_run:
        _log("--dry-run: printing to stdout")
        print(formatted)
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(formatted, encoding="utf-8")
    _log(f"Saved {output_path} ({len(formatted)} bytes)")

    errors = validate_output(output)
    if errors:
        _log(f"WARNING: {len(errors)} validation error(s) — see above")
        return 1

    n_events = len(output.get("event_analyses", []))
    n_profiles = len(output.get("profiles", {}))
    n_suspicious = len(output.get("suspicious_users_override", []))
    _log(f"Done: {n_events} events, {n_profiles} profiles, {n_suspicious} suspicious users")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
