"""CLI to generate and publish synthetic events to the local stack.

Examples:
    # Generate and publish 1000 baseline events to Redpanda
    python -m scripts.generate_events --pattern baseline --count 1000

    # Generate the Arup attack pattern (15 wires, $25.6M)
    python -m scripts.generate_events --pattern arup

    # Generate the Singapore attack pattern (3 wires, $1.9M)
    python -m scripts.generate_events --pattern singapore

    # Generate a mix: 10K baseline + arup + singapore
    python -m scripts.generate_events --pattern mix
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events
from src.infrastructure.adapters.factory import get_event_publisher

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Generate and publish synthetic events")
    parser.add_argument(
        "--pattern",
        choices=["baseline", "arup", "singapore", "mix"],
        default="mix",
    )
    parser.add_argument("--count", type=int, default=10000, help="Baseline event count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--target",
        default="local",
        choices=["local", "aws", "gcp"],
        help="Publish target (cloud adapter)",
    )
    args = parser.parse_args()

    publisher = get_event_publisher(args.target)

    all_events = []
    if args.pattern == "baseline":
        all_events = generate_baseline_events(seed=args.seed, n_events=args.count)
    elif args.pattern == "arup":
        all_events = generate_arup_events(seed=args.seed)
    elif args.pattern == "singapore":
        all_events = generate_singapore_events(seed=args.seed)
    elif args.pattern == "mix":
        all_events.extend(generate_baseline_events(seed=args.seed, n_events=args.count))
        all_events.extend(generate_arup_events(seed=args.seed))
        all_events.extend(generate_singapore_events(seed=args.seed))
        # Sort so the rolling windows are computed correctly downstream
        all_events.sort(key=lambda e: e.event_time)

    logger.info("Publishing %d events to %s ...", len(all_events), args.target)
    publisher.publish_batch(all_events)
    publisher.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
