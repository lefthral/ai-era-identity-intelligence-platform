"""Unified event generator runner.

Used by `scripts/generate_events.py` and by tests. Wraps the three
pattern generators behind a single interface that can target either
local Redpanda or AWS Kinesis.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Literal

from src.domain.events import PaymentEvent
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events

logger = logging.getLogger(__name__)


def generate_events(
    pattern: Literal["arup", "singapore", "baseline", "all"],
    *,
    seed: int = 42,
    n_baseline_events: int = 10000,
) -> Iterator[PaymentEvent]:
    """Yield events from the specified pattern generator."""
    if pattern == "arup":
        yield from generate_arup_events(seed=seed)
    elif pattern == "singapore":
        yield from generate_singapore_events(seed=seed)
    elif pattern == "baseline":
        yield from generate_baseline_events(seed=seed, n_events=n_baseline_events)
    elif pattern == "all":
        # Mix in a realistic order: baseline first, then Arup (the spike),
        # then Singapore (one-shot), then more baseline
        yield from generate_baseline_events(seed=seed, n_events=n_baseline_events // 4)
        yield from generate_arup_events(seed=seed)
        yield from generate_baseline_events(seed=seed, n_events=n_baseline_events // 4)
        yield from generate_singapore_events(seed=seed)
        yield from generate_baseline_events(seed=seed, n_events=n_baseline_events // 2)
    else:
        raise ValueError(f"Unknown pattern: {pattern}")


def publish_events(
    events: Iterator[PaymentEvent],
    target: Literal["local", "aws", "stdout"],
    *,
    rate_per_second: float = 100.0,
    topic_or_stream: str = "identity-intel-events",
) -> int:
    """Publish events to the target. Returns the count published."""
    from src.infrastructure.adapters.factory import get_publisher

    publisher = get_publisher(target, topic_or_stream=topic_or_stream)
    interval = 1.0 / rate_per_second if rate_per_second > 0 else 0
    count = 0
    started = time.time()

    try:
        for event in events:
            publisher.publish(event)
            count += 1
            if count % 500 == 0:
                elapsed = time.time() - started
                logger.info(
                    "published %d events in %.1fs (%.0f ev/s)",
                    count,
                    elapsed,
                    count / elapsed,
                )
            if interval > 0:
                time.sleep(interval)
    finally:
        publisher.close()

    elapsed = time.time() - started
    logger.info(
        "Published %d events in %.1fs (%.0f ev/s avg)", count, elapsed, count / max(elapsed, 0.01)
    )
    return count
