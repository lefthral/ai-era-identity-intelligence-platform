"""Baseline traffic generator.

Generates realistic bank-mix traffic so the model has a balanced training
set and the demo shows the system operating on a realistic distribution.

Mix (per 1000 events):
- 900 legitimate
- 80 standard fraud (card-not-present, account takeover, etc.)
- 15 money mule activity
- 5 deepfake-attack events (sparse — these are rare)

Each "user" is a synthetic Person with consistent behavior over time.
The generator maintains a session state so velocity features evolve
naturally across the synthetic time window.
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


def _get_faker():
    """Lazy faker loader so the rest of the platform can import this
    module without faker installed."""
    from faker import Faker

    return Faker


# High-risk jurisdiction list (FATF grey/black list, simplified for demo)
HIGH_RISK_COUNTRIES = {"IR", "KP", "MM", "SY", "YE", "AF", "LY", "SO"}
MEDIUM_RISK_COUNTRIES = {"RU", "VE", "NI", "ZW", "CU"}


class SyntheticPerson:
    """A synthetic person with stable behavior over the simulation."""

    def __init__(self, rng: random.Random, person_id: UUID):
        self.id = person_id
        self.rng = rng
        Faker = _get_faker()
        fake = Faker()
        Faker.seed(rng.randint(0, 2**32))
        self.name = fake.name()
        self.country = rng.choices(
            ["US", "GB", "DE", "FR", "SG", "JP", "AU", "CA", "IN", "BR"],
            weights=[35, 12, 8, 6, 6, 5, 4, 4, 12, 8],
        )[0]
        self.kyc_status = KYCStatus.VERIFIED
        self.account = self._make_account()
        self.device = self._make_device()
        self.ip = self._make_ip()
        self.typical_amount = Decimal(str(rng.uniform(50, 5000))).quantize(Decimal("0.01"))
        self.typical_hour = rng.randint(7, 22)  # Most people transact during the day
        self.typical_beneficiaries = [self._make_beneficiary() for _ in range(rng.randint(3, 8))]

    def _make_account(self) -> Account:
        return Account(
            id=uuid4(),
            owner_person_id=self.id,
            bank_identifier=self.rng.choice(["CHASE-US", "HSBC-UK", "DB-DE", "DBS-SG", "ANZ-AU"]),
            opened_at=datetime(self.rng.randint(2015, 2023), self.rng.randint(1, 12), 15),
            country_code=self.country,
            balance_band="10K-100K",
            is_dormant=False,
            is_mule=False,
        )

    def _make_device(self) -> Device:
        return Device(
            fingerprint=f"dev-{self.rng.randint(0, 10**10):010x}",
            device_type=self.rng.choice(["mobile", "laptop", "tablet"]),
            os_family=self.rng.choice(["iOS", "Android", "Windows", "macOS"]),
            browser_family=self.rng.choice(["Safari", "Chrome", "Firefox", "Edge"]),
            first_seen=datetime(2023, 1, 1),
            last_seen=datetime.utcnow(),
            is_known_trusted=True,
        )

    def _make_ip(self) -> IPAddress:
        return IPAddress(
            address=f"{self.rng.randint(1, 223)}.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}",
            asn=self.rng.randint(1000, 60000),
            country_code=self.country,
            is_proxy=False,
            is_tor_exit=False,
            is_datacenter=False,
        )

    def _make_beneficiary(self) -> Counterparty:
        return Counterparty(
            account_id=uuid4(),
            country_code=self.rng.choice(["US", "GB", "DE", "FR", "SG", "JP", "MX", "BR", "IN"]),
            is_new_beneficiary=False,
            account_age_days=self.rng.randint(180, 3000),
            bank_identifier="RECIPIENT-BANK",
            name_on_account="REGULAR-BENEFICIARY",
        )


def generate_baseline_events(
    seed: int = 42,
    n_users: int = 1000,
    n_events: int = 10000,
    start_time: datetime | None = None,
    duration_hours: int = 24,
) -> Iterator[PaymentEvent]:
    """Generate a realistic mix of events for the baseline."""
    rng = random.Random(seed)
    if start_time is None:
        # Anchor to a fixed date (2026-01-15 00:00 UTC) when a seed is
        # given, so the demo is reproducible. When no seed is provided,
        # use a rolling 24h window ending at "now".
        start_time = datetime(2026, 1, 15) - timedelta(hours=duration_hours)

    people = [SyntheticPerson(rng, uuid4()) for _ in range(n_users)]
    device_to_person = {p.device.fingerprint: p for p in people}

    # Mule ring: 5 persons share 2 devices. Used to evaluate the network features.
    mule_ring_devices = [f"mule-dev-{i:02d}" for i in range(2)]
    for i, p in enumerate(people[:5]):
        p.device = Device(
            fingerprint=mule_ring_devices[i % len(mule_ring_devices)],
            device_type="mobile",
            os_family="Android",
            browser_family=None,
            first_seen=datetime(2024, 6, 1),
            last_seen=datetime.utcnow(),
            is_known_trusted=False,
        )
        device_to_person[p.device.fingerprint] = p

    label_choices = (
        [GroundTruthLabel.LEGIT] * 900
        + [GroundTruthLabel.STANDARD_FRAUD] * 80
        + [GroundTruthLabel.MONEY_MULE] * 15
        + [GroundTruthLabel.DEEPFAKE_ATTACK] * 5
    )

    for i in range(n_events):
        label = rng.choice(label_choices)
        person = rng.choice(people)

        # Adjust the event based on label
        if label == GroundTruthLabel.LEGIT:
            amount = person.typical_amount * Decimal(str(rng.uniform(0.5, 2.0)))
            hour = (person.typical_hour + rng.randint(-2, 2)) % 24
            beneficiary = rng.choice(person.typical_beneficiaries)
            cross_border = False
            memo = "regular payment"
        elif label == GroundTruthLabel.STANDARD_FRAUD:
            amount = person.typical_amount * Decimal(str(rng.uniform(5, 20)))
            hour = rng.choice([2, 3, 4, 23])  # Off-hours
            beneficiary = Counterparty(
                account_id=uuid4(),
                country_code=person.country,
                is_new_beneficiary=True,
                account_age_days=rng.randint(1, 30),
                bank_identifier="FRAUD-BANK",
                name_on_account="UNKNOWN",
            )
            cross_border = False
            memo = "card-not-present"
        elif label == GroundTruthLabel.MONEY_MULE:
            amount = Decimal(str(rng.uniform(500, 5000))).quantize(Decimal("0.01"))
            hour = rng.randint(0, 23)
            beneficiary = Counterparty(
                account_id=uuid4(),
                country_code=rng.choice(["HK", "SG", "AE", "RU"]),
                is_new_beneficiary=True,
                account_age_days=rng.randint(2, 30),
                bank_identifier="MULE-BANK",
                name_on_account="MULE-RECEIVER",
            )
            cross_border = True
            memo = "internal transfer"
        else:  # DEEPFAKE_ATTACK
            amount = Decimal(str(rng.uniform(100000, 5000000))).quantize(Decimal("0.01"))
            hour = rng.choice([2, 3, 4])
            beneficiary = Counterparty(
                account_id=uuid4(),
                country_code=rng.choice(["HK", "CN", "RU", "AE"]),
                is_new_beneficiary=True,
                account_age_days=rng.randint(1, 14),
                bank_identifier="MULE-BANK",
                name_on_account="URGENT-BENEFICIARY",
            )
            cross_border = True
            memo = "URGENT CONFIDENTIAL"

        # Build event time spread over the window
        seconds_offset = int(rng.uniform(0, duration_hours * 3600))
        event_time = start_time + timedelta(seconds=seconds_offset)
        event_time = event_time.replace(hour=hour, minute=rng.randint(0, 59))

        actor = Actor(
            person_id=person.id,
            account_id=person.account.id,
            device=person.device,
            ip=person.ip,
            country_code=person.country,
        )

        yield PaymentEvent(
            event_id=uuid4(),
            event_type=EventType.PAYMENT_INITIATED,
            event_time=event_time,
            rail=rng.choice(
                [
                    RailType.CARD,
                    RailType.CARD,
                    RailType.CARD,
                    RailType.ACH,
                    RailType.SEPA,
                    RailType.WIRE,
                    RailType.FEDNOW,
                    RailType.RTP,
                ]
            ),
            actor=actor,
            counterparty=beneficiary,
            amount=MoneyAmount(value=amount.quantize(Decimal("0.01")), currency=Currency.USD),
            memo=memo,
            ground_truth_label=label,
            attack_pattern=None,
            synthetic_seed=seed + i,
            extra={"is_cross_border": cross_border},
        )


if __name__ == "__main__":
    print("Baseline traffic generator:")
    events = list(generate_baseline_events(n_events=10000))
    from collections import Counter

    label_counts = Counter(e.ground_truth_label for e in events)
    for label, count in label_counts.most_common():
        print(f"  {label.value:20s}  {count:5d}  ({count/len(events)*100:.1f}%)")
