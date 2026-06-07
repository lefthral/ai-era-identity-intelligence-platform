"""Singapore finance-director deepfake scam (Mar 2025).

Replays the documented attack:
- US$499,000 (S$670,000) transferred by a finance director of a multinational
- Deepfake CFO on a Zoom call instructed the transfer
- The transfer went to a local corporate account (which turned out to be a
  money-mule account)
- Funds were traced to Hong Kong bank accounts within 4 days
- $494,000+ were frozen, $5,000+ seized locally
- Recovery was successful due to rapid HSBC + Singapore Police (ASC) +
  Hong Kong Police (ADCC) cooperation via the FRONTIER+ initiative

The pattern emits a single transfer event with the documented metadata.
Unlike Arup, this is a one-shot attack — the velocity signal is not present.
The platform's job here is to catch the device/geo anomaly, the new-beneficiary
signal, the high amount relative to peer group, and the post-hoc mule-ring
inference.

References:
- Mothership.SG (Apr 1 2025)
- People Matters (Apr 9 2025)
- Singapore Police Force media release
"""

from __future__ import annotations

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

SINGAPORE_TRANSFER_USD = Decimal("499000")
SINGAPORE_TRANSFER_CURRENCY = Currency.USD
SINGAPORE_VICTIM_BANK = "HSBC"
SINGAPORE_MULE_BANK = "DBS-SG-MULE-01"
SINGAPORE_HK_OFFSHORE_BANK = "OFFSHORE-HK-99"


def _make_victim_account() -> Account:
    return Account(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        owner_person_id=UUID("44444444-4444-4444-4444-444444444444"),
        bank_identifier=SINGAPORE_VICTIM_BANK,
        opened_at=datetime(2015, 3, 10),
        country_code="SG",
        balance_band="1M-10M",
        is_dormant=False,
        is_mule=False,
    )


def _make_mule_account_sg() -> Account:
    """The first-hop mule account in Singapore (where the funds went first)."""
    return Account(
        id=UUID("55555555-5555-5555-5555-555555555555"),
        bank_identifier=SINGAPORE_MULE_BANK,
        opened_at=datetime.utcnow() - timedelta(days=14),  # Opened 2 weeks before attack
        country_code="SG",
        balance_band="0-10K",
        is_dormant=False,
        is_mule=True,
    )


def _make_hk_offshore_account() -> Account:
    """The second-hop offshore account in Hong Kong."""
    return Account(
        id=UUID("66666666-6666-6666-6666-666666666666"),
        bank_identifier=SINGAPORE_HK_OFFSHORE_BANK,
        opened_at=datetime.utcnow() - timedelta(days=45),
        country_code="HK",
        balance_band="0-10K",
        is_dormant=False,
        is_mule=True,
    )


def _make_targeted_device() -> Device:
    return Device(
        fingerprint="sg-finance-director-win-zoom-2025-03",
        device_type="laptop",
        os_family="Windows",
        browser_family="Zoom",
        first_seen=datetime(2024, 1, 1),
        last_seen=datetime.utcnow(),
        is_known_trusted=True,
    )


def _make_targeted_ip() -> IPAddress:
    return IPAddress(
        address="103.21.244.5",
        asn=134963,
        country_code="SG",
        is_proxy=False,
        is_tor_exit=False,
        is_datacenter=False,
    )


def generate_singapore_events(
    seed: int = 20250326,
    start_time: datetime | None = None,
) -> Iterator[PaymentEvent]:
    """Generate the Singapore attack pattern.

    Unlike Arup, this is a single-transfer attack. The platform must catch
    it on the basis of:
    - New beneficiary
    - High amount relative to user history
    - Time-of-day anomaly (3am SGT)
    - Post-hoc mule-ring inference

    We emit a sequence of events:
    1. The initial transfer to the SG mule
    2. A follow-up "attempted" second transfer for $1.4M (which is what
       triggered the victim to realize the scam, per the SPF report)
    3. The mule-to-HK hop (showing how the ring resolves)
    """
    if start_time is None:
        # The actual event was on Mar 26 2025. We use 03:00 SGT (20:00 UTC
        # previous day) which matches the "called at 3am" pattern.
        start_time = datetime.utcnow().replace(hour=3, minute=0, second=0, microsecond=0)

    victim = _make_victim_account()
    mule_sg = _make_mule_account_sg()
    hk_offshore = _make_hk_offshore_account()
    device = _make_targeted_device()
    ip = _make_targeted_ip()

    actor = Actor(
        person_id=UUID("44444444-4444-4444-4444-444444444444"),
        account_id=victim.id,
        device=device,
        ip=ip,
        country_code="SG",
    )

    # Event 1: The fraudulent transfer of $499K
    counterparty_sg = Counterparty(
        account_id=mule_sg.id,
        account=mule_sg,
        country_code="SG",
        is_new_beneficiary=True,
        account_age_days=14,
        bank_identifier=SINGAPORE_MULE_BANK,
        name_on_account="LOCAL-CORP-ACQUISITION-VEHICLE",
    )

    yield PaymentEvent(
        event_id=uuid4(),
        event_type=EventType.PAYMENT_INITIATED,
        event_time=start_time,
        rail=RailType.WIRE,
        actor=actor,
        counterparty=counterparty_sg,
        amount=MoneyAmount(value=SINGAPORE_TRANSFER_USD, currency=SINGAPORE_TRANSFER_CURRENCY),
        memo="CONFIDENTIAL ACQUISITION - URGENT",
        ground_truth_label=GroundTruthLabel.DEEPFAKE_ATTACK,
        attack_pattern="singapore",
        synthetic_seed=seed,
        extra={
            "case_reference": "SPF-2025-03-26-001",
            "deepfake_vector": "zoom_video_call",
            "impostor_role": "CFO",
            "funds_recovered_usd": 499000,
            "recovery_days": 4,
            "recovery_mechanism": "FRONTIER+ cross-border coordination",
        },
    )

    # Event 2: The follow-up request for $1.4M (the moment of realization)
    yield PaymentEvent(
        event_id=uuid4(),
        event_type=EventType.PAYMENT_INITIATED,
        event_time=start_time + timedelta(days=1, hours=8),
        rail=RailType.WIRE,
        actor=actor,
        counterparty=counterparty_sg,
        amount=MoneyAmount(value=Decimal("1400000"), currency=SINGAPORE_TRANSFER_CURRENCY),
        memo="FOLLOW-ON ROUND - AS DISCUSSED",
        ground_truth_label=GroundTruthLabel.DEEPFAKE_ATTACK,
        attack_pattern="singapore",
        synthetic_seed=seed,
        extra={
            "case_reference": "SPF-2025-03-26-001",
            "event_role": "realization_trigger",
            "note": "victim alerted HSBC when asked for additional $1.4M",
        },
    )

    # Event 3: The mule-to-HK hop (this is what the graph layer should detect)
    mule_actor = Actor(
        person_id=UUID("77777777-7777-7777-7777-777777777777"),
        account_id=mule_sg.id,
        device=Device(
            fingerprint="mule-device-01",
            device_type="mobile",
            os_family="Android",
            browser_family=None,
            first_seen=datetime.utcnow() - timedelta(days=10),
            last_seen=datetime.utcnow(),
            is_known_trusted=False,
        ),
        ip=IPAddress(
            address="103.21.244.99",
            asn=134963,
            country_code="SG",
            is_proxy=True,
            is_tor_exit=False,
            is_datacenter=False,
        ),
        country_code="SG",
    )

    yield PaymentEvent(
        event_id=uuid4(),
        event_type=EventType.PAYMENT_INITIATED,
        event_time=start_time + timedelta(hours=4),
        rail=RailType.SWIFT_ISO20022,
        actor=mule_actor,
        counterparty=Counterparty(
            account_id=hk_offshore.id,
            account=hk_offshore,
            country_code="HK",
            is_new_beneficiary=True,
            account_age_days=45,
            bank_identifier=SINGAPORE_HK_OFFSHORE_BANK,
            name_on_account="OFFSHORE-RECEIVING-01",
        ),
        amount=MoneyAmount(value=Decimal("494000"), currency=SINGAPORE_TRANSFER_CURRENCY),
        memo="INTERNAL TRANSFER",
        ground_truth_label=GroundTruthLabel.MONEY_MULE,
        attack_pattern="singapore",
        synthetic_seed=seed,
        extra={
            "case_reference": "SPF-2025-03-26-001",
            "event_role": "mule_to_offshore_hop",
            "jurisdiction_jump": "SG -> HK",
        },
    )


if __name__ == "__main__":
    print("Singapore attack pattern:")
    events = list(generate_singapore_events())
    for e in events:
        print(
            f"  ${e.amount.value:>12,.2f}  {e.actor.country_code} -> {e.counterparty.country_code}  ({e.attack_pattern}/{e.extra.get('event_role', 'main')})"
        )
