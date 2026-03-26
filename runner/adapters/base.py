"""Base adapter contract for daily review chapters."""

from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class that every review adapter must implement.

    Each adapter produces one "chapter" of the daily report.  The chapter dict
    follows a fixed schema so the orchestrator and front-end can consume any
    adapter output without special-casing.
    """

    @property
    @abstractmethod
    def slug(self) -> str:
        """URL-friendly identifier, e.g. 'price-limit'."""
        ...

    @property
    @abstractmethod
    def title(self) -> str:
        """Human-readable chapter title, e.g. 'Price Limit Review'."""
        ...

    @abstractmethod
    def execute(self, ema_data: dict) -> dict:
        """Run the review and return a chapter dict.

        Parameters
        ----------
        ema_data : dict
            Keyed by instId.  Each value is a dict with optional keys:
            ``basis``, ``spread``, ``limitUp_buffer``, ``limitDn_buffer``.
            May be empty if no EMA state is available.

        Returns
        -------
        dict
            Must conform to the following schema::

                {
                    "slug": str,
                    "title": str,
                    "render_variant": "rules" | "risk-intel",
                    "status": "pass" | "warning" | "critical" | "pending",
                    "summary": str,
                    "metrics": {
                        "instruments_scanned": int,
                        "ema_coverage": int,
                        "issues_found": int,
                        "source": str,
                        "generated_at": str,        # ISO 8601
                    },
                    "rule_blocks": [
                        {
                            "ruleId": str,
                            "title": str,
                            "status": "pass" | "warning" | "critical",
                            "description": str,
                            "table": {
                                "headers": list[str],
                                "rows": list[list[str]],
                            } | None,
                            "note": str | None,
                        },
                    ],
                    "metric_cards": [
                        {
                            "label": str,
                            "value": str,
                        }
                    ],
                    "recommended_changes": {
                        "headers": list[str],
                        "rows": list[list[str]],
                    } | None,
                    "downloads": [
                        {
                            "label": str,
                            "filename": str,
                            "content": str,
                        },
                    ],
                    "source_document": {
                        "title": str,
                        "url": str,
                        "modified_at": str,
                        "selected_by": str,
                    } | None,
                    "suspicious_users": [
                        {
                            "uid": str,
                            "master_user_id": str,
                            "risk_tier": str,
                            "source_alert": str,
                            "reason": str,
                        }
                    ],
                    "user_profiles": [
                        {
                            "uid": str,
                            "master_user_id": str,
                            "overall_risk_tier": str,
                            "executive_summary": str,
                            "dimensions": list[dict],
                            "key_evidence": list[str],
                            "local_artifact_ref": str,
                        }
                    ],
                    "markdown": str,
                    "error": str | None,
                }
        """
        ...
