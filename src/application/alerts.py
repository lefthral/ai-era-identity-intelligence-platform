"""Alerting rules.

The scorer emits alerts on interesting events. The rules below
encode the policy:

- Every BLOCK decision on a wire > $1M → critical alert
- Every detection of a documented attack pattern (Arup, Singapore)
  → critical alert
- Sustained BLOCK rate > 10% of decisions in a 5-min window →
  warning alert (model may be miscalibrated)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from src.domain.decisions import Decision, DecisionAction
from src.infrastructure.notifications import Alert, Notifier, get_notifier

logger = logging.getLogger(__name__)

# Thresholds
LARGE_WIRE_USD = 1_000_000
HIGH_BLOCK_RATE_THRESHOLD = 0.10
HIGH_BLOCK_RATE_WINDOW = 300  # 5 minutes


def _wire_amount_usd(decision: Decision) -> float:
    """The amount on the event that triggered this decision. We
    don't have it on the Decision object itself, so we return 0
    here; the caller is expected to have the event in scope.
    This is a placeholder for the integration layer."""
    return 0.0


def alert_on_block(decision: Decision, amount_usd: float, notifier: Notifier | None = None) -> None:
    """Called by the scorer worker after writing a BLOCK decision.

    Emits a critical alert if the wire is over the large-wire threshold.
    """
    if decision.action != DecisionAction.BLOCK:
        return
    notifier = notifier or get_notifier()
    severity = "critical" if amount_usd >= LARGE_WIRE_USD else "warning"
    notifier.send(
        Alert(
            title=f"Wire BLOCK: ${amount_usd:,.0f}",
            message=f"Decision {decision.decision_id} BLOCKed a wire of ${amount_usd:,.0f}.",
            severity=severity,
            source="scorer",
            timestamp=datetime.now(UTC),
            details={
                "decision_id": str(decision.decision_id),
                "event_id": str(decision.event_id),
                "final_score": decision.final_score,
                "xgb_score": decision.xgb_score,
                "rule_score": decision.rule_score,
                "rule_codes": [h.rule_id for h in decision.rule_hits],
                "model_version": decision.model_version.run_id,
            },
        )
    )


def alert_on_attack_pattern(
    decision: Decision, pattern_name: str, notifier: Notifier | None = None
) -> None:
    """Called when a known attack pattern is detected (Arup, Singapore, etc.)."""
    notifier = notifier or get_notifier()
    notifier.send(
        Alert(
            title=f"Attack pattern detected: {pattern_name}",
            message=f"Decision {decision.decision_id} matches the documented {pattern_name} attack pattern.",
            severity="critical",
            source="pattern_detector",
            timestamp=datetime.now(UTC),
            details={
                "decision_id": str(decision.decision_id),
                "event_id": str(decision.event_id),
                "pattern": pattern_name,
                "final_score": decision.final_score,
            },
        )
    )


def alert_on_high_block_rate(
    recent_decisions: Iterable[Decision], notifier: Notifier | None = None
) -> None:
    """Called by a periodic job (every 5 min). Emits a warning if the
    BLOCK rate is suspiciously high, which often means the model is
    miscalibrated or under attack."""
    decisions = list(recent_decisions)
    if not decisions:
        return
    blocks = sum(1 for d in decisions if d.action == DecisionAction.BLOCK)
    rate = blocks / len(decisions)
    if rate < HIGH_BLOCK_RATE_THRESHOLD:
        return
    notifier = notifier or get_notifier()
    notifier.send(
        Alert(
            title=f"High BLOCK rate: {rate:.1%}",
            message=f"{blocks}/{len(decisions)} decisions in the last {HIGH_BLOCK_RATE_WINDOW // 60} minutes were BLOCK. "
            f"Threshold is {HIGH_BLOCK_RATE_THRESHOLD:.0%}.",
            severity="warning",
            source="block_rate_monitor",
            timestamp=datetime.now(UTC),
            details={
                "block_count": blocks,
                "total_count": len(decisions),
                "block_rate": rate,
                "window_seconds": HIGH_BLOCK_RATE_WINDOW,
            },
        )
    )


__all__ = [
    "HIGH_BLOCK_RATE_THRESHOLD",
    "LARGE_WIRE_USD",
    "alert_on_attack_pattern",
    "alert_on_block",
    "alert_on_high_block_rate",
]
