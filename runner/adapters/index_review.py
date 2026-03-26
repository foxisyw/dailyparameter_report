"""Index Review adapter — stub, pending integration."""

from datetime import datetime, timezone

from .base import BaseAdapter


class IndexReviewAdapter(BaseAdapter):

    @property
    def slug(self) -> str:
        return "index-review"

    @property
    def title(self) -> str:
        return "Index Review"

    def execute(self, ema_data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "slug": self.slug,
            "title": self.title,
            "render_variant": "rules",
            "status": "pending",
            "summary": "Integration pending — ETA March 28, 2026.",
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
            "markdown": (
                "# Index Review\n\n"
                "**Status:** pending\n\n"
                "Integration ETA: **March 28, 2026**.\n"
            ),
            "error": None,
            "source_document": None,
            "suspicious_users": [],
            "user_profiles": [],
        }
