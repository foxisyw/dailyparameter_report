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


def _emoji(status: str) -> str:
    return {"pass": "\u2705", "warning": "\u26a0\ufe0f", "critical": "\u274c", "pending": "\u23f3"}.get(status, "\u2753")


def _color(status: str) -> str:
    return {"pass": "green", "warning": "orange", "critical": "red"}.get(status, "grey")


def build_card(report: dict, chapters: list[dict], date_str: str) -> dict:
    """Build a Lark Interactive Card with table-formatted summary."""
    status = report["status"]
    total_issues = report["total_issues"]
    total_instruments = sum(
        ch.get("metrics", {}).get("instruments_scanned", 0)
        for ch in report["chapters"]
    )
    status_text = {"pass": "All Clear", "warning": "Needs Attention", "critical": "Action Required"}.get(status, status.title())

    active = [ch for ch in chapters if ch["status"] != "pending"]
    pending = [ch for ch in chapters if ch["status"] == "pending"]

    elements = []

    # ── Overview metrics as column_set ──
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "grey",
        "columns": [
            _col(f"**{_emoji(status)} Status**\n{status_text}"),
            _col(f"**Instruments**\n{total_instruments:,}"),
            _col(f"**Issues**\n{total_issues}"),
            _col(f"**Sections**\n{len(active)} active / {len(pending)} pending"),
        ],
    })

    elements.append({"tag": "hr"})

    # ── Rule Results Table per active chapter ──
    for ch in active:
        instruments = ch.get("metrics", {}).get("instruments_scanned", 0)
        issues = ch.get("metrics", {}).get("issues_found", 0)
        ema = ch.get("metrics", {}).get("ema_coverage", 0)

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{_emoji(ch['status'])} {ch['title']}**  |  {instruments:,} instruments  |  EMA: {ema:,}  |  {issues} issues"},
        })

        # Rule table
        rules = ch.get("rule_blocks", [])
        if rules:
            # Build markdown table
            table_md = "| Rule | Status | Flagged |\n| --- | --- | --- |\n"
            for rb in rules:
                count = len(rb.get("table", {}).get("rows", [])) if rb.get("table") else 0
                table_md += f"| {rb['title']} | {_emoji(rb['status'])} {rb['status'].upper()} | {count} |\n"

            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": table_md},
            })

    # ── Pending chapters ──
    for ch in pending:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"{_emoji('pending')} **{ch['title']}** \u2014 Pending integration"},
        })

    # ── Recommended Changes Table ──
    for ch in active:
        rec = ch.get("recommended_changes")
        if rec and rec.get("rows"):
            elements.append({"tag": "hr"})

            rec_md = "**Recommended Changes**\n\n| Instrument | Change | Reason |\n| --- | --- | --- |\n"
            for row in rec["rows"][:8]:
                inst = row[0] if len(row) > 0 else ""
                change = row[1] if len(row) > 1 else ""
                reason = row[2] if len(row) > 2 else ""
                rec_md += f"| {inst} | {change} | {reason} |\n"
            if len(rec["rows"]) > 8:
                rec_md += f"\n... and {len(rec['rows']) - 8} more\n"

            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": rec_md},
            })

    elements.append({"tag": "hr"})

    # ── Buttons ──
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
                "text": {"tag": "plain_text", "content": "How It Works"},
                "type": "default",
                "url": f"{VERCEL_URL}/how-it-works.html",
            },
        ],
    })

    # ── Footer note ──
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"Generated {date_str} | OKX Parameter Management | Automated Daily Review"},
        ],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"Daily Parameter Review \u2014 {date_str}"},
                "template": _color(status),
            },
            "elements": elements,
        },
    }


def _col(content: str) -> dict:
    """Helper to build a column for column_set."""
    return {
        "tag": "column",
        "width": "weighted",
        "weight": 1,
        "vertical_align": "top",
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
