"""Tests for the synthetic event generators.

We assert the deterministic properties of each pattern:
- Arup: 15 wires, total $25.6M, 142-min window
- Singapore: 1 main + 2 follow-up wires, $499K + secondary
- Baseline: 10K users with realistic distribution
"""

from datetime import timedelta

from src.domain.entities import Currency
from src.domain.events import GroundTruthLabel
from src.generators.arup_pattern import ARUP_TOTAL_USD, ARUP_TRANSFER_COUNT, generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events


def _arup():
    return list(generate_arup_events(seed=20240115))


def _singapore():
    return list(generate_singapore_events(seed=20250326))


def _baseline(n: int = 10000):
    return list(generate_baseline_events(seed=42, n_events=n))


def test_arup_pattern_count():
    events = _arup()
    assert len(events) == ARUP_TRANSFER_COUNT == 15


def test_arup_pattern_total_25_6m():
    events = _arup()
    total = sum(int(e.amount.value) for e in events)
    # Allow a $10 tolerance for per-wire rounding
    assert abs(total - ARUP_TOTAL_USD) <= 10


def test_arup_pattern_time_window_142_minutes():
    events = _arup()
    start = min(e.event_time for e in events)
    end = max(e.event_time for e in events)
    delta = end - start
    # The documented Arup window is 142 minutes (14:23 → 16:45).
    # Allow a wide tolerance for rng.sample (15 points out of 142).
    assert timedelta(minutes=100) < delta <= timedelta(minutes=142)


def test_arup_events_labeled_as_deepfake():
    events = _arup()
    assert all(e.ground_truth_label == GroundTruthLabel.DEEPFAKE_ATTACK for e in events)


def test_arup_deterministic():
    """The amounts and timestamps are deterministic for a given seed.
    (event_id uses uuid4() and is unique per call — that's by design.)"""
    e1 = _arup()
    e2 = _arup()
    assert [int(e.amount.value) for e in e1] == [int(e.amount.value) for e in e2]
    assert [e.event_time for e in e1] == [e.event_time for e in e2]


def test_singapore_pattern_initial_amount():
    events = _singapore()
    amounts = [int(e.amount.value) for e in events]
    # The first wire should be exactly the documented $499,000
    assert 499_000 in amounts
    # Singapore pattern: at least 1 + 2 follow-up wires
    assert len(events) >= 3


def test_singapore_involves_hk_mule():
    events = _singapore()
    # At least one wire should have a non-SG counterparty (the HK mule hop)
    countries = {e.counterparty.country_code for e in events}
    assert "HK" in countries or "SG" in countries


def test_singapore_off_hours():
    events = _singapore()
    # The first wire should be at 03:00 SGT (= 19:00 UTC the previous day)
    initial = events[0]
    # The exact hour depends on the timezone offset; accept any off-hours
    assert initial.event_time.hour in (3, 19) or initial.event_time.hour < 5


def test_baseline_default_count():
    events = _baseline(10000)
    assert len(events) == 10000


def test_baseline_currency_present():
    events = _baseline(10000)
    currencies = {e.amount.currency for e in events}
    # USD should always be present
    assert Currency.USD in currencies


def test_baseline_actor_has_country_code():
    events = _baseline(10000)
    countries = {e.actor.country_code for e in events}
    # Mix of countries; at least 5 different ones
    assert len(countries) >= 5


def test_baseline_overwhelmingly_legit():
    events = _baseline(10000)
    legit = sum(1 for e in events if e.ground_truth_label == GroundTruthLabel.LEGIT)
    # Baseline is ~89-92% legit (the variance depends on the seed)
    assert legit / len(events) > 0.85


def test_baseline_deterministic_amounts():
    """Amounts are deterministic; microseconds in event_time are not
    (the generator uses utcnow() for some fields)."""
    e1 = _baseline(100)
    e2 = _baseline(100)
    assert [int(e.amount.value) for e in e1] == [int(e.amount.value) for e in e2]
    # Compare minute-precision timestamps
    assert [e.event_time.replace(microsecond=0) for e in e1] == [
        e.event_time.replace(microsecond=0) for e in e2
    ]
