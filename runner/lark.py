"""Send daily review summary to Lark via webhook (Interactive Card with table)."""

import json
import os
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except Exception:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

VERCEL_URL = "https://dailyparameter-report.vercel.app"
DAILY_SALT = b'paramreview_daily_salt_2026'
TIMEOUT = 15


def get_daily_token(date_str: str) -> str:
    """Generate daily rotating token matching middleware.js logic."""
    import hmac as _hmac
    import hashlib as _hashlib
    sig = _hmac.new(DAILY_SALT, date_str.encode(), _hashlib.sha256).hexdigest()
    return f"pr_{date_str.replace('-', '')}_{sig[:8]}"

DEFAULT_WEBHOOKS = [
    "https://open.larksuite.com/open-apis/bot/v2/hook/f6726392-3780-407b-94c9-bf2ca1ec6774",
    "https://open.larksuite.com/open-apis/bot/v2/hook/af916a3f-d8d2-4629-a4a9-3d69d5408899",
]


def _log(msg: str):
    print(f"  [lark] {msg}", file=sys.stderr)


def _get_webhooks() -> list[str]:
    env = os.environ.get("LARK_WEBHOOKS", "")
    if env:
        return [url.strip() for url in env.split(",") if url.strip()]
    return DEFAULT_WEBHOOKS


def _emoji(status: str) -> str:
    return {"pass": "\u2705", "warning": "\u26a0\ufe0f", "critical": "\u274c", "pending": "\u23f3"}.get(status, "\u2753")


def _color(status: str) -> str:
    return {"pass": "green", "warning": "orange", "critical": "red"}.get(status, "grey")


def _status_text(status: str) -> str:
    return {"pass": "PASS", "warning": "WARNING", "critical": "CRITICAL"}.get(status, status.upper())


def _highest_risk_tier(chapter: dict) -> str:
    tiers = [str(user.get("risk_tier", "T1")).upper() for user in chapter.get("suspicious_users", [])]
    if "T4" in tiers:
        return "T4"
    if "T3" in tiers:
        return "T3"
    if "T2" in tiers:
        return "T2"
    return "T1"


def build_card(report: dict, chapters: list[dict], date_str: str) -> dict:
    """Build a Lark Interactive Card with native table component."""
    status = report["status"]
    total_issues = report["total_issues"]
    total_instruments = sum(
        ch.get("metrics", {}).get("instruments_scanned", 0)
        for ch in report["chapters"]
    )
    verdict = {"pass": "All Clear", "warning": "Needs Attention", "critical": "Action Required"}.get(status, status.title())

    active = [ch for ch in chapters if ch["status"] != "pending"]
    pending = [ch for ch in chapters if ch["status"] == "pending"]

    elements = []

    # ── Overview metrics (column_set) ──
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "grey",
        "columns": [
            _col(f"**Status**\n{verdict}"),
            _col(f"**Instruments**\n{total_instruments:,}"),
            _col(f"**Issues**\n{total_issues}"),
            _col(f"**Sections**\n{len(active)} active / {len(pending)} pending"),
        ],
    })

    elements.append({"tag": "hr"})

    # ── Per active chapter: header + native table ──
    for ch in active:
        if ch.get("render_variant") == "risk-intel":
            alert_types = len(ch.get("rule_blocks", []))
            flagged_users = len(ch.get("suspicious_users", []))
            highest_tier = _highest_risk_tier(ch)
            header = (
                f"**{ch['title']}**  |  {alert_types} alert types  |  "
                f"{flagged_users} suspicious users  |  Highest {highest_tier}"
            )
        else:
            instruments = ch.get("metrics", {}).get("instruments_scanned", 0)
            ema = ch.get("metrics", {}).get("ema_coverage", 0)
            issues = ch.get("metrics", {}).get("issues_found", 0)
            header = (
                f"**{ch['title']}**  |  {instruments:,} instruments  |  "
                f"EMA: {ema:,}  |  {issues} issues"
            )

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": header},
        })

        # Native table for rule results
        rules = ch.get("rule_blocks", [])
        if rules:
            table_rows = []
            for rb in rules:
                count = len(rb.get("table", {}).get("rows", [])) if rb.get("table") else 0
                table_rows.append({
                    "rule": rb["title"],
                    "status": [{"text": _status_text(rb["status"]),
                                "color": {"pass": "green", "warning": "orange", "critical": "red"}.get(rb["status"], "grey")}],
                    "flagged": count,
                })

            elements.append({
                "tag": "table",
                "page_size": 10,
                "row_height": "low",
                "header_style": {
                    "text_align": "left",
                    "text_size": "normal",
                    "background_style": "grey",
                    "text_color": "grey",
                    "bold": True,
                    "lines": 1,
                },
                "columns": [
                    {"name": "rule", "display_name": "Rule", "data_type": "text", "width": "auto"},
                    {"name": "status", "display_name": "Status", "data_type": "options", "width": "120px"},
                    {"name": "flagged", "display_name": "Flagged", "data_type": "number", "width": "120px"},
                ],
                "rows": table_rows,
            })

    # ── Pending chapters ──
    for ch in pending:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"{_emoji('pending')} **{ch['title']}** \u2014 {ch.get('summary', 'Pending integration')}"},
        })

    elements.append({"tag": "hr"})

    # ── Buttons ──
    elements.append({
        "tag": "action",
        "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "View Full Report"}, "type": "primary", "url": f"{VERCEL_URL}?pw={get_daily_token(date_str)}"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "How It Works"}, "type": "default", "url": f"{VERCEL_URL}/how-it-works.html"},
        ],
    })

    # ── Footer ──
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"Generated {date_str} | OKX Parameter Management | Automated Daily Review"}],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"Daily Parameter Review \u2014 {date_str}"},
                "template": _color(status),
            },
            "elements": elements,
        },
    }


def _col(content: str) -> dict:
    return {
        "tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top",
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
    }


def send(report: dict, chapters: list[dict], date_str: str):
    """Build card and send to all configured Lark webhooks."""
    webhooks = _get_webhooks()
    if not webhooks:
        _log("No Lark webhooks configured")
        return

    card = build_card(report, chapters, date_str)
    payload = json.dumps(card, ensure_ascii=False).encode("utf-8")

    for url in webhooks:
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
                body = json.loads(resp.read())
            if body.get("code") == 0 or body.get("StatusCode") == 0:
                _log(f"Sent to Lark: ...{url[-8:]}")
            else:
                _log(f"Lark response: {body}")
        except (HTTPError, URLError, OSError) as exc:
            _log(f"Failed to send to Lark: {exc}")
