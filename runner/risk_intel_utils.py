"""Helpers for local risk intelligence generation and chapter formatting."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "public" / "data"
FIXTURE_PATH = PROJECT_ROOT / "runner" / "fixtures" / "risk_intel_fixture.json"
LOCAL_INPUT_PATH = PROJECT_ROOT / "runner" / "local" / "risk_intel_input.json"
LARK_FOLDER_URL = (
    "https://okg-block.sg.larksuite.com/drive/folder/"
    "Wu2Pfktq6lq4t8dWL52lB97pgQb"
)

SECTION_DEFS = [
    {
        "id": "index_alarm",
        "title": "Index Alarm",
        "keywords": ("index alarm", "指数报警", "指数"),
        "default_description": "Summarizes component-price anomalies and missing quotes.",
    },
    {
        "id": "price_limit_p4",
        "title": "Price Limit P4",
        "keywords": ("price limit", "price limit — p4", "price limit - p4", "限价"),
        "default_description": "Summarizes hard-cap and inner-band triggers with affected contracts.",
    },
    {
        "id": "collateral_coin",
        "title": "Collateral Coin Risk",
        "keywords": ("collateral coin", "小币抵押"),
        "default_description": "Summarizes borrow-limit pressure and collateral restrictions.",
    },
    {
        "id": "platform_oi",
        "title": "Platform OI",
        "keywords": ("platform oi", "oi报警", "open interest"),
        "default_description": "Summarizes OI deviations, concentration, and platform limit pressure.",
    },
]

DIMENSION_NAMES = [
    "Registration Profile",
    "Trading Behavior",
    "Associated Accounts",
    "IP & Geolocation",
    "Identity Signals",
    "Profit & Loss",
    "Withdrawal Behavior",
    "Comprehensive Judgment",
]

ALERT_ROW_HEADERS = ["ASSET", "DETAILS", "USERS", "STATUS"]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hkt_date_str() -> str:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d")


def parse_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -•\t")


def normalize_rule_status(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if any(token in raw for token in ("🔴", "critical", "high", "高")):
        return "critical"
    if any(token in raw for token in ("🟠", "🟡", "warning", "warn", "medium", "low", "中", "低")):
        return "warning"
    if any(token in raw for token in ("pending", "待")):
        return "pending"
    if any(token in raw for token in ("missing", "缺")):
        return "missing"
    if any(token in raw for token in ("pass", "clear", "normal", "无", "✅")):
        return "pass"
    return "warning"


def normalize_risk_tier(value: str | None) -> str:
    raw = (value or "").strip().upper()
    mapping = {
        "T1": "T1",
        "LOW": "T1",
        "PASS": "T1",
        "T2": "T2",
        "MEDIUM": "T2",
        "WARNING": "T2",
        "T3": "T3",
        "HIGH": "T3",
        "CRITICAL": "T4",
        "T4": "T4",
    }
    if raw in mapping:
        return mapping[raw]
    if "🔴" in raw or "CRITICAL" in raw:
        return "T4"
    if "HIGH" in raw or "🟠" in raw:
        return "T3"
    if "MEDIUM" in raw or "LOW" in raw or "🟡" in raw:
        return "T2"
    return "T1"


def tier_rank(value: str | None) -> int:
    return {"T1": 1, "T2": 2, "T3": 3, "T4": 4}.get(normalize_risk_tier(value), 1)


def tier_to_status(value: str | None) -> str:
    tier = normalize_risk_tier(value)
    if tier == "T4":
        return "critical"
    if tier in {"T2", "T3"}:
        return "warning"
    return "pass"


def detect_section(line: str) -> dict[str, Any] | None:
    lowered = clean_text(line).lower()
    if not any(marker in line for marker in ("**", "##", "1️⃣", "2️⃣", "3️⃣", "4️⃣")):
        return None
    for section in SECTION_DEFS:
        if any(keyword in lowered for keyword in section["keywords"]):
            return section
    return None


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section = detect_section(line)
        if section:
            current = section["id"]
            continue
        if current:
            sections[current].append(raw_line.rstrip())
    return sections


def extract_user_refs(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    paired_uids: set[str] = set()
    paired_master_ids: set[str] = set()

    pair_pattern = re.compile(
        r"(?:UID|uid)\s*[:=]?\s*(\d{15,20}).*?"
        r"(?:master_user_id|user_id)\s*[:=]?\s*(\d{5,12})",
        re.IGNORECASE,
    )
    for uid, master_user_id in pair_pattern.findall(text):
        key = (uid, master_user_id)
        if key not in seen:
            seen.add(key)
            paired_uids.add(uid)
            paired_master_ids.add(master_user_id)
            refs.append({"uid": uid, "master_user_id": master_user_id})

    for uid in re.findall(r"(?<!\d)(\d{18})(?!\d)", text):
        if uid in paired_uids:
            continue
        key = (uid, "")
        if key not in seen:
            seen.add(key)
            refs.append({"uid": uid, "master_user_id": ""})

    for master_user_id in re.findall(
        r"(?:master_user_id|user_id)\s*[:=]?\s*(\d{5,12})",
        text,
        flags=re.IGNORECASE,
    ):
        if master_user_id in paired_master_ids:
            continue
        key = ("", master_user_id)
        if key not in seen:
            seen.add(key)
            refs.append({"uid": "", "master_user_id": master_user_id})

    return refs


def extract_critical_assets(text: str) -> list[dict[str, Any]]:
    """Extract assets flagged as 🔴 critical or 🟠 medium risk from the risk document.

    Returns a list of dicts: {asset, severity, context, source_section}
    These are the assets that need event analysis + user profiling.
    """
    all_candidates: list[dict[str, Any]] = []
    lines = text.splitlines()
    current_section = ""
    noise_words = {"AI", "IN", "AT", "OR", "IF", "OF", "ON", "TO", "BY", "IS", "IT",
                   "OK", "HK", "US", "EU", "OI", "API", "USD", "USDT", "USDC", "VIP2",
                   "VIP6", "UTC", "P4", "OKX", "EUR", "TRY", "CC", "BZ", "MU", "OL",
                   "CRCL", "ATH", "ETF", "APP", "ABS", "MAX", "CAP", "FRP", "ASK", "BID"}

    for line in lines:
        stripped = line.strip()
        for sd in SECTION_DEFS:
            lowered = stripped.lower()
            if any(kw in lowered for kw in sd["keywords"]) and any(m in stripped for m in ("**", "##", "1️⃣", "2️⃣", "3️⃣", "4️⃣")):
                current_section = sd["id"]

        if "🔴" not in stripped and "🟠" not in stripped:
            continue

        # Only actionable sections
        if current_section not in ("price_limit_p4", "platform_oi", "collateral_coin"):
            continue

        severity = "critical" if "🔴" in stripped else "warning"
        asset_patterns = [
            r"\b([A-Z][A-Z0-9]{1,10}(?:-(?:USDT|USD|USDC))?(?:[-_](?:UM-)?SWAP)?)\b",
            r"(?:^|[\s（(,、])([A-Z][A-Z0-9]{2,10})\b",
        ]
        for pattern in asset_patterns:
            for match in re.findall(pattern, stripped):
                asset = match.strip().upper()
                if len(asset) < 3 or asset in noise_words:
                    continue
                inst_id = asset
                if not any(suffix in asset for suffix in ("-SWAP", "-USDT", "-USD")):
                    inst_id = f"{asset}-USDT-SWAP"
                elif asset.endswith("-USDT") or asset.endswith("-USD"):
                    inst_id = f"{asset}-SWAP"

                all_candidates.append({
                    "asset": asset,
                    "instId": inst_id,
                    "severity": severity,
                    "context": stripped[:200],
                    "source_section": current_section,
                })

    # Deduplicate by instId, keeping the highest severity
    best: dict[str, dict[str, Any]] = {}
    for c in all_candidates:
        key = c["instId"]
        if key not in best or (c["severity"] == "critical" and best[key]["severity"] != "critical"):
            best[key] = c
    results = list(best.values())

    results.sort(key=lambda x: (0 if x["severity"] == "critical" else 1))
    return results


def extract_assets(text: str) -> list[str]:
    assets: list[str] = []
    seen: set[str] = set()

    patterns = [
        r"\b[A-Z][A-Z0-9]{1,}(?:-[A-Z0-9_]+)+(?:-SWAP|_UM-SWAP|_CM-SWAP)?\b",
        r"(?:币种|合约|标的)\s*[:：]\s*([A-Z][A-Z0-9-]{1,40})",
        r"^[\s>*-]*[🔴🟠🟡✅⚠️]?\s*([A-Z][A-Z0-9-]{1,40})\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.MULTILINE):
            asset = match if isinstance(match, str) else match[0]
            asset = asset.strip().upper()
            if asset and asset not in seen:
                seen.add(asset)
                assets.append(asset)
    return assets


def summarize_section_lines(lines: list[str]) -> str:
    summary_lines: list[str] = []
    for line in lines:
        cleaned = clean_text(line)
        if not cleaned:
            continue
        if cleaned.startswith("💡") or "建议" in cleaned:
            break
        if cleaned.startswith(("①", "②", "③")):
            continue
        summary_lines.append(cleaned)
        if len(summary_lines) == 2:
            break
    return " ".join(summary_lines)


def looks_like_finding(line: str) -> bool:
    cleaned = clean_text(line)
    if not cleaned:
        return False
    if "AI汇总" in cleaned or "原始报警为准" in cleaned:
        return False
    if cleaned[:1] in {"🔴", "🟠", "🟡", "✅", "⚠"}:
        return True
    return any(
        token in cleaned
        for token in (
            "🔴",
            "🟠",
            "🟡",
            "UID",
            "uid",
            "master_user_id",
            "币种",
            "合约",
            "borrow/limit",
            "OI",
            "Z cap",
        )
    )


def parse_finding_line(line: str, fallback_asset: str) -> dict[str, Any]:
    assets = extract_assets(line)
    asset = assets[0] if assets else fallback_asset
    user_refs = extract_user_refs(line)
    status = normalize_rule_status(line)
    users_text_parts = []
    for ref in user_refs:
        parts = []
        if ref.get("uid"):
            parts.append(f"UID {ref['uid']}")
        if ref.get("master_user_id"):
            parts.append(f"MID {ref['master_user_id']}")
        if parts:
            users_text_parts.append(" / ".join(parts))
    return {
        "asset": asset,
        "detail": clean_text(line),
        "status": status,
        "user_refs": user_refs,
        "users_text": ", ".join(users_text_parts) or "—",
    }


def build_rule_block(section: dict[str, Any], lines: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary = summarize_section_lines(lines) or section["default_description"]
    findings = [
        parse_finding_line(line, section["title"])
        for line in lines
        if looks_like_finding(line)
    ]
    statuses = [finding["status"] for finding in findings]
    status = "critical" if "critical" in statuses else "warning" if findings else "pass"
    table = None
    if findings:
        table = {
            "headers": ALERT_ROW_HEADERS,
            "rows": [
                [item["asset"], item["detail"], item["users_text"], item["status"]]
                for item in findings
            ],
        }

    suspicious: list[dict[str, Any]] = []
    for idx, item in enumerate(findings):
        for ref in item["user_refs"]:
            suspicious.append(
                {
                    "uid": ref.get("uid", ""),
                    "master_user_id": ref.get("master_user_id", ""),
                    "risk_tier": normalize_risk_tier(item["status"]),
                    "source_alert": section["id"],
                    "reason": item["detail"],
                    "order": idx,
                }
            )

    block = {
        "ruleId": section["id"],
        "title": section["title"],
        "status": status,
        "description": summary,
        "table": table,
        "note": None if findings else "No flagged entries parsed from the selected document.",
    }
    return block, suspicious


def pick_latest_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not documents:
        return None
    ordered = sorted(
        documents,
        key=lambda doc: (parse_iso(doc.get("modified_at")).timestamp(), doc.get("title", "")),
        reverse=True,
    )
    return ordered[0]


def aggregate_suspicious_users(
    candidates: list[dict[str, Any]],
    profiles: dict[str, Any],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(candidates):
        key = item.get("uid") or item.get("master_user_id")
        if not key:
            continue
        existing = merged.get(key)
        profile_hint = profiles.get(item.get("uid")) or profiles.get(item.get("master_user_id")) or {}
        if existing is None:
            merged[key] = {
                "uid": item.get("uid") or profile_hint.get("uid", ""),
                "master_user_id": item.get("master_user_id") or profile_hint.get("master_user_id", ""),
                "risk_tier": normalize_risk_tier(item.get("risk_tier")),
                "source_alert": item.get("source_alert", ""),
                "reason": item.get("reason", ""),
                "mentions": 1,
                "first_seen": idx,
            }
            continue
        existing["mentions"] += 1
        if tier_rank(item.get("risk_tier")) > tier_rank(existing["risk_tier"]):
            existing["risk_tier"] = normalize_risk_tier(item.get("risk_tier"))
            existing["reason"] = item.get("reason", existing["reason"])
            existing["source_alert"] = item.get("source_alert", existing["source_alert"])
        if not existing.get("uid") and item.get("uid"):
            existing["uid"] = item["uid"]
        if not existing.get("master_user_id") and item.get("master_user_id"):
            existing["master_user_id"] = item["master_user_id"]

    users = list(merged.values())
    users.sort(
        key=lambda item: (
            tier_rank(item.get("risk_tier")),
            item.get("mentions", 0),
            -item.get("first_seen", 0),
        ),
        reverse=True,
    )
    return users


def normalize_dimension(dimension: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": dimension.get("name", "Unnamed Dimension"),
        "severity": normalize_rule_status(dimension.get("severity")),
        "signals": [clean_text(signal) for signal in dimension.get("signals", []) if clean_text(signal)],
    }


def fallback_profile(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": user.get("uid", ""),
        "master_user_id": user.get("master_user_id", ""),
        "overall_risk_tier": normalize_risk_tier(user.get("risk_tier")),
        "executive_summary": "Profile data not generated in this environment.",
        "dimensions": [
            {
                "name": name,
                "severity": "pending",
                "signals": ["Pending local Claude Code risk profiling output."],
            }
            for name in DIMENSION_NAMES
        ],
        "key_evidence": [clean_text(user.get("reason"))] if user.get("reason") else [],
        "local_artifact_ref": "",
    }


def validate_profiles_complete(profiles: dict[str, Any], suspicious_users: list[dict[str, Any]]) -> list[str]:
    """Check that all top-5 suspicious users have real profile data.
    Returns list of error messages. Empty list = all good."""
    errors: list[str] = []
    for user in suspicious_users[:5]:
        uid = user.get("uid", "")
        mid = user.get("master_user_id", "")
        lookup = profiles.get(uid) or profiles.get(mid)
        label = uid or mid or "unknown"
        if lookup is None:
            errors.append(f"User {label}: NO profile data at all. Must query via Data Query MCP.")
            continue
        dims = lookup.get("dimensions", [])
        filled = sum(1 for d in dims if d.get("severity") not in ("pending", None, ""))
        if filled < 4:
            errors.append(f"User {label}: Only {filled}/8 dimensions filled. Need at least 4 real dimensions.")
        if not lookup.get("executive_summary") or "pending" in lookup.get("executive_summary", "").lower():
            errors.append(f"User {label}: executive_summary is missing or pending.")
    return errors


def validate_event_analyses(event_analyses: list[dict[str, Any]]) -> list[str]:
    """Validate that event_analyses are complete with RCA + embedded user profiles.
    Returns list of error messages. Empty list = all good."""
    REQUIRED_KEYS = {"asset", "severity", "executive_summary", "causal_chain", "user_profiles"}
    errors: list[str] = []
    if not event_analyses:
        return errors  # Empty event_analyses is valid on quiet days (no flagged assets)
    for i, ea in enumerate(event_analyses):
        asset = ea.get("asset", f"event[{i}]")
        missing = REQUIRED_KEYS - set(ea.keys())
        if missing:
            errors.append(f"{asset}: missing required keys: {missing}")
        cc = ea.get("causal_chain", [])
        if len(cc) < 2:
            errors.append(f"{asset}: causal_chain has {len(cc)} steps, need at least 2.")
        ups = ea.get("user_profiles", [])
        if not ups:
            errors.append(f"{asset}: user_profiles is EMPTY. Must include 8-dimension profiles for key users.")
        for j, up in enumerate(ups):
            dims = up.get("dimensions", [])
            filled = sum(1 for d in dims if d.get("severity") not in ("pending", None, ""))
            if filled < 4:
                uid = up.get("uid", up.get("master_user_id", f"user[{j}]"))
                errors.append(f"{asset} → user {uid}: only {filled}/8 dimensions filled in event profile.")
    return errors


def build_user_profiles(
    suspicious_users: list[dict[str, Any]],
    profiles: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for user in suspicious_users[:5]:
        lookup = profiles.get(user.get("uid")) or profiles.get(user.get("master_user_id"))
        if lookup is None:
            results.append(fallback_profile(user))
            continue
        dimensions = [normalize_dimension(item) for item in lookup.get("dimensions", [])]
        if not dimensions:
            dimensions = fallback_profile(user)["dimensions"]
        results.append(
            {
                "uid": lookup.get("uid") or user.get("uid", ""),
                "master_user_id": lookup.get("master_user_id") or user.get("master_user_id", ""),
                "overall_risk_tier": normalize_risk_tier(
                    lookup.get("overall_risk_tier") or user.get("risk_tier")
                ),
                "executive_summary": clean_text(
                    lookup.get("executive_summary") or user.get("reason")
                ),
                "dimensions": dimensions,
                "key_evidence": [
                    clean_text(item)
                    for item in lookup.get("key_evidence", [])
                    if clean_text(item)
                ],
                "local_artifact_ref": lookup.get("local_artifact_ref", ""),
            }
        )
    return results


def chapter_metric_cards(
    alert_types: int,
    flagged_alerts: int,
    suspicious_users: list[dict[str, Any]],
) -> list[dict[str, str]]:
    highest_tier = max(
        (normalize_risk_tier(item.get("risk_tier")) for item in suspicious_users),
        default="T1",
        key=tier_rank,
    )
    return [
        {"label": "Alert Types", "value": str(alert_types)},
        {"label": "Flagged Alerts", "value": str(flagged_alerts)},
        {"label": "Suspicious Users", "value": str(len(suspicious_users))},
        {"label": "Highest Risk", "value": highest_tier},
    ]


def build_risk_intel_chapter(input_data: dict[str, Any], date_str: str) -> dict[str, Any]:
    now = iso_now()
    documents = input_data.get("folder_documents", [])
    profiles = input_data.get("profiles", {})
    selected = pick_latest_document(documents)
    if selected is None:
        return pending_risk_intel_chapter(
            date_str,
            "No Lark document snapshot was available for local risk intelligence generation.",
        )

    sections = split_sections(selected.get("content", ""))
    rule_blocks: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for section in SECTION_DEFS:
        block, extracted = build_rule_block(section, sections.get(section["id"], []))
        rule_blocks.append(block)
        candidates.extend(extracted)

    # Merge candidates from document parsing with explicit overrides from MCP queries
    override_users = input_data.get("suspicious_users_override", [])
    candidates.extend(override_users)

    suspicious_users = aggregate_suspicious_users(candidates, profiles)
    user_profiles = build_user_profiles(suspicious_users, profiles)

    flagged_alerts = sum(len(block.get("table", {}).get("rows", [])) for block in rule_blocks if block.get("table"))
    highest_tier = max(
        (normalize_risk_tier(item.get("risk_tier")) for item in suspicious_users),
        default="T1",
        key=tier_rank,
    )
    if any(block["status"] == "critical" for block in rule_blocks) or highest_tier == "T4":
        status = "critical"
    elif suspicious_users or any(block["status"] == "warning" for block in rule_blocks):
        status = "warning"
    else:
        status = "pass"

    source_document = {
        "title": selected.get("title", "Latest Lark risk document"),
        "url": selected.get("url", LARK_FOLDER_URL),
        "modified_at": selected.get("modified_at", now),
        "selected_by": "latest_modified_desc",
    }
    summary = (
        f"{len(rule_blocks)} alert types analyzed. "
        f"{flagged_alerts} flagged alert(s) parsed. "
        f"{len(suspicious_users)} suspicious user(s) highlighted."
    )

    # Event analyses (from OKX Trade MCP market data + alert narrative)
    event_analyses = input_data.get("event_analyses", [])

    return {
        "slug": "risk-intel",
        "title": "Risk Intelligence",
        "render_variant": "risk-intel",
        "status": status,
        "summary": summary,
        "event_analyses": event_analyses,
        "metrics": {
            "instruments_scanned": flagged_alerts,
            "ema_coverage": len(rule_blocks),
            "issues_found": flagged_alerts + len(suspicious_users),
            "source": source_document["title"],
            "generated_at": now,
        },
        "metric_cards": chapter_metric_cards(len(rule_blocks), flagged_alerts, suspicious_users),
        "rule_blocks": rule_blocks,
        "recommended_changes": None,
        "downloads": [],
        "markdown": build_markdown(summary, source_document, suspicious_users, user_profiles),
        "error": None,
        "source_document": source_document,
        "suspicious_users": suspicious_users,
        "user_profiles": user_profiles,
    }


def build_markdown(
    summary: str,
    source_document: dict[str, Any],
    suspicious_users: list[dict[str, Any]],
    user_profiles: list[dict[str, Any]],
) -> str:
    lines = [
        "# Risk Intelligence",
        "",
        f"**Summary:** {summary}",
        f"**Source document:** {source_document.get('title', 'n/a')}",
        "",
        "## Suspicious Users",
    ]
    if not suspicious_users:
        lines.append("No suspicious users highlighted.")
    else:
        for user in suspicious_users:
            label = user.get("uid") or user.get("master_user_id") or "unknown"
            lines.append(f"- {label} — {user.get('risk_tier', 'T1')} — {user.get('reason', '')}")
    lines.append("")
    lines.append("## Deep Profiles")
    if not user_profiles:
        lines.append("No user profiles generated.")
    else:
        for profile in user_profiles:
            label = profile.get("uid") or profile.get("master_user_id") or "unknown"
            lines.append(
                f"- {label} — {profile.get('overall_risk_tier', 'T1')} — "
                f"{profile.get('executive_summary', '')}"
            )
    return "\n".join(lines)


def pending_risk_intel_chapter(date_str: str, reason: str) -> dict[str, Any]:
    now = iso_now()
    return {
        "slug": "risk-intel",
        "title": "Risk Intelligence",
        "render_variant": "risk-intel",
        "status": "pending",
        "summary": reason,
        "metrics": {
            "instruments_scanned": 0,
            "ema_coverage": 0,
            "issues_found": 0,
            "source": "Claude Code local generation",
            "generated_at": now,
        },
        "metric_cards": [
            {"label": "Alert Types", "value": "0"},
            {"label": "Flagged Alerts", "value": "0"},
            {"label": "Suspicious Users", "value": "0"},
            {"label": "Highest Risk", "value": "T1"},
        ],
        "rule_blocks": [],
        "recommended_changes": None,
        "downloads": [],
        "markdown": f"# Risk Intelligence\n\n**Status:** pending\n\n{reason}\n",
        "error": None,
        "source_document": {
            "title": "No source document selected",
            "url": LARK_FOLDER_URL,
            "modified_at": now,
            "selected_by": "latest_modified_desc",
        },
        "suspicious_users": [],
        "user_profiles": [],
    }


def risk_intel_payload(chapter: dict[str, Any], date_str: str) -> dict[str, Any]:
    return {
        "date": date_str,
        "generated_at": chapter["metrics"]["generated_at"],
        "chapter": chapter,
    }
