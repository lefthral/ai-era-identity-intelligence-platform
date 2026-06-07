"""Feature computation.

The FeatureComputer consumes PaymentEvents from the stream, maintains a
sliding-window state per entity, and produces a FeatureSnapshot that the
scorer consumes. Both online (in-memory) and offline (S3/Parquet) paths
are supported.

The feature catalog is the canonical list of features the model uses.
Adding/removing features requires updating FEATURE_NAMES and re-training.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.decisions import FeatureSnapshot
from src.domain.events import PaymentEvent

logger = logging.getLogger(__name__)


# ── Feature catalog ─────────────────────────────────────────────────────
# The single source of truth for what the model sees. Order matters —
# the index in this list is the column index in the training matrix.

FEATURE_NAMES: list[str] = [
    # Velocity (5)
    "txns_last_1h",
    "txns_last_24h",
    "distinct_beneficiaries_24h",
    "amount_sum_24h",
    "cross_border_hops_24h",
    # Jurisdictional (4)
    "origin_country_risk_score",
    "destination_country_risk_score",
    "is_high_risk_jurisdiction",
    "jurisdiction_velocity_km_per_hour",
    # Behavioral (5)
    "amount_zscore_user",
    "amount_log",
    "time_of_day_zscore",
    "beneficiary_age_days",
    "first_time_beneficiary_high_amount",
    # Network (5)
    "shared_device_count",
    "shared_ip_count",
    "mule_ring_proximity_score",
    "mule_ring_member",
    "ego_network_degree",
]


# Country risk scores (simplified FATF-aligned)
COUNTRY_RISK = {
    "US": 0.0,
    "GB": 0.0,
    "DE": 0.0,
    "FR": 0.0,
    "JP": 0.0,
    "SG": 0.0,
    "AU": 0.0,
    "CA": 0.0,
    "HK": 0.2,
    "AE": 0.3,
    "CN": 0.4,
    "IN": 0.3,
    "BR": 0.4,
    "MX": 0.5,
    "RU": 0.7,
    "VE": 0.7,
    "IR": 0.9,
    "KP": 1.0,
    "MM": 0.9,
    "SY": 0.9,
    "YE": 0.9,
    "AF": 0.8,
    "LY": 0.8,
    "SO": 0.8,
}


@dataclass
class _EntityWindow:
    """Per-entity rolling state for feature computation."""

    events_1h: deque[PaymentEvent] = field(default_factory=deque)
    events_24h: deque[PaymentEvent] = field(default_factory=deque)
    amount_history: deque[Decimal] = field(default_factory=deque)  # 90-day history for z-score
    typical_amount: Decimal | None = None
    typical_amount_std: Decimal | None = None


class FeatureComputer:
    """Computes the feature vector for each incoming PaymentEvent.

    The state is in-memory for MVP. In production this would be backed by
    a RocksDB state store (Flink) or DynamoDB / Redis. The interface
    remains the same.
    """

    def __init__(self) -> None:
        self._state: dict[str, _EntityWindow] = defaultdict(_EntityWindow)
        self._mule_ring_members: set[str] = set()  # Updated by graph updater
        self._shared_device_counts: dict[str, int] = defaultdict(int)
        self._shared_ip_counts: dict[str, int] = defaultdict(int)
        self._now_provider = datetime.utcnow  # injectable for tests

    def register_mule_ring_member(self, account_id: str) -> None:
        """Called by the graph updater when mule ring membership is inferred."""
        self._mule_ring_members.add(account_id)

    def set_shared_device_count(self, device_fp: str, count: int) -> None:
        self._shared_device_counts[device_fp] = count

    def set_shared_ip_count(self, ip: str, count: int) -> None:
        self._shared_ip_counts[ip] = count

    def compute(self, event: PaymentEvent, now: datetime | None = None) -> FeatureSnapshot:
        if now is None:
            now = self._now_provider()
        window = self._state[str(event.actor.account_id)]
        self._update_window(window, event, now)
        features = self._extract_features(event, window, now)
        return FeatureSnapshot(
            feature_names=FEATURE_NAMES,
            feature_values=features,
            computed_at=now,
            online_store_version="v1",
        )

    def _update_window(self, window: _EntityWindow, event: PaymentEvent, now: datetime) -> None:
        # Update rolling windows (drop expired)
        cutoff_1h = now - timedelta(hours=1)
        cutoff_24h = now - timedelta(hours=24)
        while window.events_1h and window.events_1h[0].event_time < cutoff_1h:
            window.events_1h.popleft()
        while window.events_24h and window.events_24h[0].event_time < cutoff_24h:
            window.events_24h.popleft()
        window.events_1h.append(event)
        window.events_24h.append(event)

        # Update amount history
        window.amount_history.append(event.amount.value)
        if len(window.amount_history) > 1000:
            window.amount_history.popleft()

        # Compute typical amount stats (incremental — naive for MVP)
        if len(window.amount_history) > 20 and window.typical_amount is None:
            amounts = [float(a) for a in window.amount_history]
            mean = sum(amounts) / len(amounts)
            variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
            std = variance**0.5
            window.typical_amount = Decimal(str(mean))
            window.typical_amount_std = Decimal(str(std))

    def _extract_features(
        self,
        event: PaymentEvent,
        window: _EntityWindow,
        now: datetime,
    ) -> list[float]:
        # Velocity
        txns_1h = len(window.events_1h)
        txns_24h = len(window.events_24h)
        distinct_beneficiaries_24h = len({e.counterparty.account_id for e in window.events_24h})
        amount_sum_24h = float(sum((e.amount.value for e in window.events_24h), Decimal(0)))
        cross_border_hops_24h = sum(1 for e in window.events_24h if e.is_cross_border())

        # Jurisdictional
        origin_risk = COUNTRY_RISK.get(event.actor.country_code, 0.5)
        dest_risk = COUNTRY_RISK.get(event.counterparty.country_code, 0.5)
        is_high_risk = float(1.0 if max(origin_risk, dest_risk) >= 0.7 else 0.0)
        # Naive jurisdiction velocity: distance between actor and counterparty
        # in "jurisdictional hops" — count distinct countries in last 24h
        countries_24h = {e.actor.country_code for e in window.events_24h} | {
            e.counterparty.country_code for e in window.events_24h
        }
        jurisdiction_velocity = float(len(countries_24h))

        # Behavioral
        amount = float(event.amount.value)
        if window.typical_amount and window.typical_amount_std and window.typical_amount_std > 0:
            amount_zscore = (amount - float(window.typical_amount)) / float(
                window.typical_amount_std
            )
        else:
            amount_zscore = 0.0
        amount_log = float(__import__("math").log10(max(amount, 1.0)))
        hour = event.event_time.hour
        # Off-hours: 22:00 - 06:00 → positive z-score
        tod_zscore = abs(hour - 14) / 6.0  # 14:00 is "typical"
        beneficiary_age = float(event.counterparty.account_age_days)
        first_time_high = float(
            1.0 if event.counterparty.is_new_beneficiary and event.amount.value > 10000 else 0.0
        )

        # Network
        device_fp = event.actor.device.fingerprint if event.actor.device else ""
        ip_addr = event.actor.ip.address if event.actor.ip else ""
        shared_device_count = float(self._shared_device_counts.get(device_fp, 1))
        shared_ip_count = float(self._shared_ip_counts.get(ip_addr, 1))
        mule_ring_member = float(
            1.0 if str(event.actor.account_id) in self._mule_ring_members else 0.0
        )
        mule_ring_proximity = mule_ring_member  # Simplified
        ego_network_degree = float(len(window.events_24h))

        return [
            float(txns_1h),
            float(txns_24h),
            float(distinct_beneficiaries_24h),
            amount_sum_24h,
            float(cross_border_hops_24h),
            origin_risk,
            dest_risk,
            is_high_risk,
            jurisdiction_velocity,
            amount_zscore,
            amount_log,
            tod_zscore,
            beneficiary_age,
            first_time_high,
            shared_device_count,
            shared_ip_count,
            mule_ring_proximity,
            mule_ring_member,
            ego_network_degree,
        ]


def compute_features(
    event: PaymentEvent, computer: FeatureComputer | None = None
) -> FeatureSnapshot:
    if computer is None:
        computer = FeatureComputer()
    return computer.compute(event)


__all__ = ["COUNTRY_RISK", "FEATURE_NAMES", "FeatureComputer", "compute_features"]
