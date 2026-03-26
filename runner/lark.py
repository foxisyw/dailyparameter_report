"""Send daily review summary to Lark via webhook (Interactive Card)."""

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
TIMEOUT = 15

# Webhook URLs — can be overridden via env var LARK_WEBHOOKS (comma-separated)
DEFAULT_WEBHOOKS = [
    "https://open.larksuite.com/open-apis/bot/v2/hook/f6726392-3780-407b-94c9-bf2ca1ec6774",
]


def _log(msg: str):
    print(f"  [lark] {msg}", file=sys.stderr)


def _get_webhooks() -> list[str]:
    env = os.environ.get("LARK_WEBHOOKS", "")
    if env:
        return [url.strip() for url in env.split(",") if url.strip()]
    return DEFAULT_WEBHOOKS


def _status_emoji(status: str) -> str:
    return {"pass": "\u2705", "warning": "\u26a0\ufe0f", "critical": "\u274c", "pending": "\u23f3"}.get(status, "\u2753")


def _status_color(status: str) -> str:
    return {"pass": "green", "warning": "orange", "critical": "red"}.get(status, "grey")


def build_card(report: dict, chapters: list[dict], date_str: str) -> dict:
    """Build a Lark Interactive Card for the daily review summary."""
    status = report["status"]
    total_issues = report["total_issues"]
    total_instruments = sum(ch.get("metrics", {}).get("instruments_scanned", 0) for ch in report["chapters"])

    # Header
    status_text = {"pass": "All Clear", "warning": "Needs Attention", "critical": "Action Required"}.get(status, status.title())
    header_template = _status_color(status)

    # Summary line
    active_chapters = [ch for ch in chapters if ch["status"] != "pending"]
    pending_chapters = [ch for ch in chapters if ch["status"] == "pending"]

    elements = []

    # Key metrics row
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": [
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**{_status_emoji(status)} Status**\n{status_text}"}},
            ]},
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Instruments**\n{total_instruments:,}"}},
            ]},
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Issues Found**\n{total_issues}"}},
            ]},
            {"tag": "column", "width": "weighted", "weight": 1, "vertical_align": "top", "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Sections**\n{len(active_chapters)} active / {len(pending_chapters)} pending"}},
            ]},
        ],
    })

    elements.append({"tag": "hr"})

    # Per-chapter breakdown
    for ch in chapters:
        ch_status = ch["status"]
        emoji = _status_emoji(ch_status)
        issues = ch.get("metrics", {}).get("issues_found", 0)
        instruments = ch.get("metrics", {}).get("instruments_scanned", 0)

        if ch_status == "pending":
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{emoji} **{ch['title']}** — Pending integration"},
            })
        else:
            # Build rule summary
            rule_lines = []
            for rb in ch.get("rule_blocks", []):
                rb_emoji = _status_emoji(rb["status"])
                count = len(rb.get("table", {}).get("rows", [])) if rb.get("table") else 0
                rule_lines.append(f"  {rb_emoji} {rb['title']}: {count} flagged")

            rule_text = "\n".join(rule_lines) if rule_lines else "  No rules executed"

            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{emoji} **{ch['title']}**\n{instruments:,} instruments scanned, {issues} issues\n{rule_text}"},
            })

    # Recommended changes summary
    for ch in active_chapters:
        rec = ch.get("recommended_changes")
        if rec and rec.get("rows"):
            elements.append({"tag": "hr"})
            rec_lines = [f"  \u2022 **{row[0]}**: {row[1]}" for row in rec["rows"][:5]]
            if len(rec["rows"]) > 5:
                rec_lines.append(f"  ... and {len(rec['rows']) - 5} more")
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**Recommended Changes**\n" + "\n".join(rec_lines)},
            })

    elements.append({"tag": "hr"})

    # Link to full report
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "View Full Report"},
                "type": "primary",
                "url": VERCEL_URL,
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "System Architecture"},
                "type": "default",
                "url": f"{VERCEL_URL}/how-it-works.html",
            },
        ],
    })

    # Note
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"Generated {date_str} \u2022 OKX Parameter Management \u2022 Automated Daily Review"},
        ],
    })

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"Daily Parameter Review \u2014 {date_str}"},
                "template": header_template,
            },
            "elements": elements,
        },
    }

    return card


def send(report: dict, chapters: list[dict], date_str: str):
    """Build card and send to all configured Lark webhooks."""
    webhooks = _get_webhooks()
    if not webhooks:
        _log("No Lark webhooks configured — skipping notification")
        return

    card = build_card(report, chapters, date_str)
    payload = json.dumps(card, ensure_ascii=False).encode("utf-8")

    for url in webhooks:
        try:
            req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
                body = json.loads(resp.read())
            if body.get("code") == 0 or body.get("StatusCode") == 0:
                _log(f"Sent to Lark webhook: ...{url[-8:]}")
            else:
                _log(f"Lark responded with: {body}")
        except (HTTPError, URLError, OSError) as exc:
            _log(f"Failed to send to Lark: {exc}")
