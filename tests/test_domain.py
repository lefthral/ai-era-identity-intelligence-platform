"""Tests for the domain entities and event Pydantic models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.entities import (
    Account,
    Counterparty,
    Currency,
    Device,
    KYCStatus,
)
from src.domain.events import (
    Actor,
    EventType,
    GroundTruthLabel,
    MoneyAmount,
    PaymentEvent,
    RailType,
)


def _actor() -> Actor:
    return Actor(
        person_id="00000000-0000-0000-0000-000000000001",
        account_id="00000000-0000-0000-0000-000000000002",
        country_code="US",
        kyc_status=KYCStatus.VERIFIED,
    )


def _counterparty() -> Counterparty:
    return Counterparty(
        account_id="00000000-0000-0000-0000-000000000003",
        country_code="HK",
        is_new_beneficiary=True,
        account_age_days=5,
    )


def test_amount_validates_currency():
    a = MoneyAmount(value=Decimal("1000"), currency=Currency.USD)
    assert a.value == Decimal("1000")
    assert a.currency == Currency.USD


def test_amount_negative_rejected():
    with pytest.raises(ValidationError):
        MoneyAmount(value=Decimal("-1"), currency=Currency.USD)


def test_actor_validates_country_code():
    a = _actor()
    assert a.country_code == "US"


def test_payment_event_minimal_valid():
    e = PaymentEvent(
        event_id="00000000-0000-0000-0000-000000000099",
        event_type=EventType.PAYMENT_INITIATED,
        event_time=datetime(2024, 1, 15, 14, 23, tzinfo=UTC),
        rail=RailType.WIRE,
        actor=_actor(),
        counterparty=_counterparty(),
        amount=MoneyAmount(value=Decimal("1000"), currency=Currency.USD),
        ground_truth_label=GroundTruthLabel.LEGIT,
    )
    assert e.rail == RailType.WIRE
    assert e.ground_truth_label == GroundTruthLabel.LEGIT


def test_payment_event_serializes_to_json():
    e = PaymentEvent(
        event_id="00000000-0000-0000-0000-000000000099",
        event_type=EventType.PAYMENT_INITIATED,
        event_time=datetime(2024, 1, 15, 14, 23, tzinfo=UTC),
        rail=RailType.WIRE,
        actor=_actor(),
        counterparty=_counterparty(),
        amount=MoneyAmount(value=Decimal("1000"), currency=Currency.USD),
        ground_truth_label=GroundTruthLabel.LEGIT,
    )
    j = e.model_dump_json()
    assert isinstance(j, str)
    assert "WIRE" in j


def test_rail_enum_values():
    assert RailType.WIRE.value == "WIRE"
    assert RailType.ACH.value == "ACH"
    assert RailType.SEPA.value == "SEPA"
    assert RailType.CARD.value == "CARD"


def test_ground_truth_label_enum():
    assert GroundTruthLabel.LEGIT.value == "legit"
    assert GroundTruthLabel.DEEPFAKE_ATTACK.value == "deepfake_attack"
    assert GroundTruthLabel.MONEY_MULE.value == "money_mule"
    assert GroundTruthLabel.SYNTHETIC_IDENTITY.value == "synthetic_identity"
    assert GroundTruthLabel.STANDARD_FRAUD.value == "standard_fraud"


def test_device_model_optional():
    d = Device(
        fingerprint="d-1",
        device_type="mobile",
        first_seen=datetime(2024, 1, 1, tzinfo=UTC),
        last_seen=datetime(2024, 1, 2, tzinfo=UTC),
    )
    assert d.fingerprint == "d-1"
    assert d.is_known_trusted is False


def test_account_model():
    a = Account(
        bank_identifier="BANK-001",
        opened_at=datetime(2020, 1, 1, tzinfo=UTC),
        country_code="US",
    )
    assert a.bank_identifier == "BANK-001"
    assert a.country_code == "US"
