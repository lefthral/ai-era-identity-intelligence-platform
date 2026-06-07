"""Payment event types and schemas.

A PaymentEvent is the atomic unit that flows through the platform. It is
validated on ingress, written to the stream, consumed by all workers, and
ultimately scored by the real-time scorer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from src.domain.entities import Counterparty, Currency, Device, IPAddress


class RailType(str, Enum):
    """The payment rail the event arrived on."""

    SWIFT_ISO20022 = "SWIFT_ISO20022"
    FEDNOW = "FEDNOW"
    RTP = "RTP"
    CARD = "CARD"
    ACH = "ACH"
    SEPA = "SEPA"
    WIRE = "WIRE"
    INTERNAL = "INTERNAL"


class EventType(str, Enum):
    PAYMENT_INITIATED = "PAYMENT_INITIATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_SETTLED = "PAYMENT_SETTLED"
    PAYMENT_RETURNED = "PAYMENT_RETURNED"
    KYC_UPDATE = "KYC_UPDATE"
    DEVICE_FINGERPRINT = "DEVICE_FINGERPRINT"
    LOGIN = "LOGIN"
    PASSWORD_RESET = "PASSWORD_RESET"


class GroundTruthLabel(str, Enum):
    """Synthetic ground-truth labels used for training and evaluation.

    In production these are replaced by investigator-confirmed outcomes
    via the case management UI.
    """

    LEGIT = "legit"
    STANDARD_FRAUD = "standard_fraud"
    DEEPFAKE_ATTACK = "deepfake_attack"
    MONEY_MULE = "money_mule"
    SYNTHETIC_IDENTITY = "synthetic_identity"
    UNKNOWN = "unknown"


class MoneyAmount(BaseModel):
    value: Decimal
    currency: Currency

    @field_validator("value")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount value must be > 0")
        return v


class Actor(BaseModel):
    """The originating party of a payment event."""

    person_id: UUID
    account_id: UUID
    device: Device | None = None
    ip: IPAddress | None = None
    country_code: str = Field(min_length=2, max_length=2)
    session_id: UUID | None = None


class PaymentEvent(BaseModel):
    """The atomic unit that flows through the platform.

    A PaymentEvent is validated on ingress, serialized to Avro, written to
    the stream, and consumed by all three workers (feature computer, graph
    updater, scorer).
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType = EventType.PAYMENT_INITIATED
    event_time: datetime

    rail: RailType
    actor: Actor
    counterparty: Counterparty
    amount: MoneyAmount
    memo: str | None = None

    ground_truth_label: GroundTruthLabel = GroundTruthLabel.UNKNOWN
    attack_pattern: str | None = None  # e.g., "arup", "singapore"
    synthetic_seed: int | None = None

    extra: dict[str, Any] = Field(default_factory=dict)

    def to_avro_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_avro_dict(cls, data: dict[str, Any]) -> PaymentEvent:
        return cls.model_validate(data)

    def is_high_value(self, threshold: Decimal = Decimal("100000")) -> bool:
        """True if the transaction exceeds the high-value threshold (default $100K)."""
        return self.amount.value >= threshold

    def is_cross_border(self) -> bool:
        return self.actor.country_code != self.counterparty.country_code


__all__ = [
    "Actor",
    "EventType",
    "GroundTruthLabel",
    "MoneyAmount",
    "PaymentEvent",
    "RailType",
]
