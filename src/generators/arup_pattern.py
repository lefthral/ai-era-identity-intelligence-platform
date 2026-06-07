"""Arup deepfake wire-fraud pattern (Jan 2024).

Replays the documented attack:
- 15 wire transfers in a single day
- Total $25.6M (HK$200M)
- Triggered by a multi-person deepfake Zoom call where the CFO and several
  colleagues were all synthetically generated
- Funds routed through 5+ Hong Kong mule accounts
- Funds unrecovered as of early 2025

The pattern generator emits:
- 1 initiating event from the compromised finance employee
- 15 sequential wire transfers, each going to a new mule account
- Each transfer is a separate event so the streaming pipeline sees them
  in order and can compute velocity features in real time

References:
- VerifyReal case study
- Hong Kong police disclosure (Feb 2024)
- CNN reporting (Feb 4 2024)
- WEF "Cybercrime: Lessons learned from a $25m deepfake attack" (Feb 2025)
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from src.domain.entities import (
    Account,
    Counterparty,
    Currency,
    Device,
    IPAddress,
)
from src.domain.events import (
    Actor,
    EventType,
    GroundTruthLabel,
    MoneyAmount,
    PaymentEvent,
    RailType,
)

# Documented totals from the Arup case
ARUP_TOTAL_USD = Decimal("25600000")
ARUP_TRANSFER_COUNT = 15
ARUP_TRANSFER_CURRENCY = Currency.USD

# Mule chain through Hong Kong
ARUP_MULE_COUNTRIES = ["HK", "HK", "HK", "HK", "HK", "CN", "SG"]
ARUP_VICTIM_COUNTRY = "GB"  # Arup is UK-headquartered
ARUP_FINANCE_EMPLOYEE_LOCATION = "HK"  # The targeted employee was in HK


def _make_victim_account() -> Account:
    return Account(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        owner_person_id=UUID("22222222-2222-2222-2222-222222222222"),
        bank_identifier="HSBC-HK",
        opened_at=datetime(2020, 1, 15),
        country_code="HK",
        balance_band="10M-100M",
        is_dormant=False,
        is_mule=False,
    )


def _make_mule_account(idx: int) -> Account:
    """Each mule account is brand new and tied to a specific mule ring."""
    return Account(
        id=UUID(int=0x99999999999999999999999999999990 + idx),
        bank_identifier=f"MULE-BANK-{idx:02d}",
        opened_at=datetime.utcnow() - timedelta(days=random.randint(2, 28)),
        country_code=random.choice(ARUP_MULE_COUNTRIES),
        balance_band="0-10K",
        is_dormant=False,
        is_mule=True,
    )


def _make_compromised_device() -> Device:
    return Device(
        fingerprint="arup-finance-employee-mac-chrome-2024-01",
        device_type="laptop",
        os_family="macOS",
        browser_family="Chrome",
        first_seen=datetime(2023, 6, 1),
        last_seen=datetime(2024, 1, 15, 9, 0, 0),
        is_known_trusted=True,  # The trusted device is exactly the vector
    )


def _make_compromised_ip() -> IPAddress:
    return IPAddress(
        address="203.198.123.45",
        asn=4760,
        country_code="HK",
        is_proxy=False,
        is_tor_exit=False,
        is_datacenter=False,
    )


def generate_arup_events(
    seed: int = 20240115,
    start_time: datetime | None = None,
) -> Iterator[PaymentEvent]:
    """Generate the Arup attack pattern as a stream of PaymentEvents.

    The events are ordered chronologically so the streaming pipeline can
    observe the velocity spike. Each event is a complete PaymentEvent
    ready to be put on the wire.
    """
    rng = random.Random(seed)
    if start_time is None:
        # The actual heist was on Jan 15 2024. We use a recent date for
        # demo purposes but keep the time-of-day shape.
        start_time = datetime.utcnow().replace(hour=14, minute=23, second=0, microsecond=0)

    victim_account = _make_victim_account()
    finance_employee_person_id = UUID("22222222-2222-2222-2222-222222222222")
    device = _make_compromised_device()
    ip = _make_compromised_ip()

    actor = Actor(
        person_id=finance_employee_person_id,
        account_id=victim_account.id,
        device=device,
        ip=ip,
        country_code=ARUP_FINANCE_EMPLOYEE_LOCATION,
    )

    # The 15 transfers in the actual case were not equal amounts.
    # Distribute $25.6M across 15 transfers with realistic skew (larger
    # earlier, smaller toward the end as the attacker probes the limit).
    base_amount = ARUP_TOTAL_USD / ARUP_TRANSFER_COUNT
    amounts: list[Decimal] = []
    remaining = ARUP_TOTAL_USD
    for i in range(ARUP_TRANSFER_COUNT - 1):
        # Each transfer is 0.6-1.4x the base, with larger ones first
        multiplier = Decimal(str(rng.uniform(0.6, 1.4)))
        amt = (base_amount * multiplier).quantize(Decimal("0.01"))
        amt = min(amt, remaining - Decimal("10000") * (ARUP_TRANSFER_COUNT - i - 1))
        amounts.append(amt)
        remaining -= amt
    amounts.append(remaining)

    # All 15 transfers happen between 14:23 and 16:45 on the same day —
    # a 2.5-hour window. This is the velocity spike the model should catch.
    # (We use minute units internally to keep offsets readable.)
    window_minutes = (16 * 60 + 45) - (14 * 60 + 23)  # 142 minutes total
    intervals_minutes = sorted(rng.sample(range(0, window_minutes), ARUP_TRANSFER_COUNT))
    intervals = [m * 60 for m in intervals_minutes]  # convert to seconds for timedelta

    for i, (amount, offset_seconds) in enumerate(zip(amounts, intervals, strict=True)):
        mule = _make_mule_account(i)
        counterparty = Counterparty(
            account_id=mule.id,
            account=mule,
            country_code=mule.country_code,
            is_new_beneficiary=True,
            account_age_days=(mule.opened_at and (datetime.utcnow() - mule.opened_at).days) or 0,
            bank_identifier=mule.bank_identifier,
            name_on_account=f"BENEFICIARY-{i:02d}",
        )

        yield PaymentEvent(
            event_id=uuid4(),
            event_type=EventType.PAYMENT_INITIATED,
            event_time=start_time + timedelta(seconds=offset_seconds),
            rail=RailType.SWIFT_ISO20022,
            actor=actor,
            counterparty=counterparty,
            amount=MoneyAmount(value=amount, currency=ARUP_TRANSFER_CURRENCY),
            memo=f"ACQUISITION-{i:02d}-URGENT" if i < 3 else f"RESTRUCTURING-PHASE-{i:02d}",
            ground_truth_label=GroundTruthLabel.DEEPFAKE_ATTACK,
            attack_pattern="arup",
            synthetic_seed=seed,
            extra={
                "case_reference": "ARUP-2024-01-15",
                "transfer_index": i + 1,
                "total_transfers": ARUP_TRANSFER_COUNT,
                "victim_company": "Arup Group (UK)",
                "deepfake_vector": "multi-person_video_call",
                "funds_recovered": False,
            },
        )


if __name__ == "__main__":
    print("Arup attack pattern (15 wires, $25.6M):")
    events = list(generate_arup_events())
    total = sum(e.amount.value for e in events)
    print(f"  {len(events)} events, total ${total:,.2f}")
    print(f"  Window: {events[0].event_time} -> {events[-1].event_time}")
    dests = {e.counterparty.country_code for e in events}
    print(f"  Mule destinations: {dests}")
