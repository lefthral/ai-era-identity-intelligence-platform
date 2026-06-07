"""Concrete notifier implementations."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.infrastructure.notifications.interfaces import Alert, Notifier

logger = logging.getLogger(__name__)


class NoopNotifier(Notifier):
    """A notifier that just logs. The default for dev and tests."""

    def send(self, alert: Alert) -> None:
        logger.info(
            "[ALERT/%s] %s — %s",
            alert.severity,
            alert.title,
            alert.message,
        )

    def send_batch(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            self.send(alert)


class SlackNotifier(Notifier):
    """Posts alerts to a Slack incoming webhook.

    Configure with:
        SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    """

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")

    def send(self, alert: Alert) -> None:
        import httpx

        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set; dropping alert %s", alert.title)
            return
        emoji = {
            "info": ":information_source:",
            "warning": ":warning:",
            "critical": ":rotating_light:",
        }.get(alert.severity, ":bell:")
        payload: dict[str, Any] = {
            "text": f"{emoji} *{alert.title}*",
            "attachments": [
                {
                    "color": {"info": "#36a64f", "warning": "#daa038", "critical": "#d00000"}[
                        alert.severity
                    ],
                    "fields": [
                        {"title": "Severity", "value": alert.severity, "short": True},
                        {"title": "Source", "value": alert.source, "short": True},
                        {"title": "Message", "value": alert.message, "short": False},
                    ],
                }
            ],
        }
        if alert.details:
            fields: list[dict[str, Any]] = payload["attachments"][0]["fields"]
            fields.append(
                {
                    "title": "Details",
                    "value": json.dumps(alert.details, default=str)[:500],
                    "short": False,
                }
            )
        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=5.0)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("Slack post failed: %s", e)

    def send_batch(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            self.send(alert)


class PagerDutyNotifier(Notifier):
    """Triggers a PagerDuty incident via the Events API v2.

    Configure with:
        PAGERDUTY_ROUTING_KEY=...
    """

    def __init__(self, routing_key: str | None = None):
        self.routing_key = routing_key or os.getenv("PAGERDUTY_ROUTING_KEY")

    def send(self, alert: Alert) -> None:
        import httpx

        if not self.routing_key:
            logger.warning("PAGERDUTY_ROUTING_KEY not set; dropping alert %s", alert.title)
            return
        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": f"{alert.source}:{alert.title}",
            "payload": {
                "summary": alert.message,
                "source": alert.source,
                "severity": alert.severity,
                "custom_details": alert.details,
            },
        }
        try:
            resp = httpx.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.exception("PagerDuty post failed: %s", e)

    def send_batch(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            self.send(alert)


__all__ = ["NoopNotifier", "PagerDutyNotifier", "SlackNotifier"]
