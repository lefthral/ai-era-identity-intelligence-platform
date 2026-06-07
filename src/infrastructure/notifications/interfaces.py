"""Notification channels.

Alerting is an infrastructure concern. The application code (e.g.,
the scorer) emits alerts via the `Notifier` interface. Concrete
implementations fan out to Slack, PagerDuty, email, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Alert:
    """A single alert emitted by the platform."""

    title: str
    message: str
    severity: str  # "info" | "warning" | "critical"
    source: str  # which component raised it (e.g., "scorer", "graph")
    timestamp: datetime
    details: dict[str, Any]


class Notifier(ABC):
    """The contract for all notification channels."""

    @abstractmethod
    def send(self, alert: Alert) -> None: ...

    @abstractmethod
    def send_batch(self, alerts: list[Alert]) -> None: ...


__all__ = ["Alert", "Notifier"]
