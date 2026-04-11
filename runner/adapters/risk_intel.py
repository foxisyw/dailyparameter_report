"""Risk intelligence adapter — reads same-day locally generated risk-intel data."""

from __future__ import annotations

import json
from pathlib import Path

from .base import BaseAdapter
from ..risk_intel_utils import DATA_DIR, pending_risk_intel_chapter


class RiskIntelAdapter(BaseAdapter):

    @property
    def slug(self) -> str:
        return "risk-intel"

    @property
    def title(self) -> str:
        return "Risk Intelligence"

    def execute(self, ema_data: dict, *, date_override: str | None = None) -> dict:
        from zoneinfo import ZoneInfo
        from datetime import datetime

        date_str = date_override or datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d")
        payload_path = DATA_DIR / "reports" / date_str / "risk-intel.json"
        if not payload_path.exists():
            return pending_risk_intel_chapter(
                date_str,
                "Risk intel has not been generated locally for this report date.",
            )

        try:
            payload = json.loads(payload_path.read_text())
            chapter = payload.get("chapter", {})
        except Exception as exc:
            return {
                **pending_risk_intel_chapter(date_str, "Risk intel payload could not be parsed."),
                "status": "critical",
                "summary": f"Risk intel payload could not be parsed: {exc}",
                "error": str(exc),
            }

        chapter.setdefault("slug", self.slug)
        chapter.setdefault("title", self.title)
        chapter.setdefault("render_variant", "risk-intel")
        chapter.setdefault("metric_cards", [])
        chapter.setdefault("rule_blocks", [])
        chapter.setdefault("downloads", [])
        chapter.setdefault("suspicious_users", [])
        chapter.setdefault("user_profiles", [])
        chapter.setdefault("recommended_changes", None)
        return chapter
