"""Notifications.

Concrete implementations of the `Notifier` interface for each
channel. The factory at `get_notifier()` selects the right one
based on the `ALERT_CHANNEL` env var.
"""

from src.infrastructure.notifications.channels import (
    NoopNotifier,
    PagerDutyNotifier,
    SlackNotifier,
)
from src.infrastructure.notifications.interfaces import Alert, Notifier


def get_notifier(channel: str | None = None) -> Notifier:
    """Factory: returns the right Notifier for the configured channel.

    channel: "noop" (default, logs only) | "slack" | "pagerduty"
    """
    import os

    channel_env: str = channel or os.getenv("ALERT_CHANNEL", "noop") or "noop"
    resolved = channel_env.lower()
    if resolved == "slack":
        return SlackNotifier()
    if resolved == "pagerduty":
        return PagerDutyNotifier()
    return NoopNotifier()


__all__ = [
    "Alert",
    "NoopNotifier",
    "Notifier",
    "PagerDutyNotifier",
    "SlackNotifier",
    "get_notifier",
]
