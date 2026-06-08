"""Seed the database with realistic demo data.

Populates:
- 100K baseline events
- 15 Arup attack events
- 3 Singapore attack events
- The corresponding decisions
- 5 open cases for the most interesting BLOCK decisions

Use this when you want the Streamlit UI to look populated on first
load. Run after `make init-db` and `make init-neo4j`.

Usage:
    python -m scripts.seed_demo_data
    python -m scripts.seed_demo_data --baseline 500 --arup --singapore
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.features import FeatureComputer
from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events
from src.infrastructure.persistence import init_db
from src.infrastructure.persistence.repos import CaseRepository, DecisionRepository

logger = logging.getLogger("seed")


def seed(
    n_baseline: int,
    include_arup: bool,
    include_singapore: bool,
) -> int:
    init_db()
    decision_repo = DecisionRepository()
    case_repo = CaseRepository()

    events = []
    if n_baseline > 0:
        events.extend(generate_baseline_events(seed=42, n_events=n_baseline))
    if include_arup:
        events.extend(generate_arup_events(seed=20240115))
    if include_singapore:
        events.extend(generate_singapore_events(seed=20250326))
    events.sort(key=lambda e: e.event_time)
    logger.info("Scoring %d events...", len(events))

    computer = FeatureComputer()
    scorer = RealTimeScorer(
        model_path=None,
        model_version=ModelVersion(
            run_id="seed_v1",
            model_name="identity_intel_xgb",
            stage="Production",
            algorithm="heuristic",
            trained_at=datetime(2026, 1, 1, tzinfo=UTC),
            metrics={},
        ),
    )
    now = max(e.event_time for e in events)

    decisions_written = 0
    cases_opened = 0
    for event in events:
        try:
            computer.compute(event, now=now)
            decision = scorer.score(event)
            decision_repo.insert(decision, event)
            decisions_written += 1
            if decision.action.value in ("REVIEW", "BLOCK"):
                # Case is auto-opened inside decision_repo.insert
                cases_opened += 1
        except Exception as e:
            logger.exception("Failed to score %s: %s", event.event_id, e)

    logger.info(
        "Done. %d decisions written, %d cases opened. Actions: %s",
        decisions_written,
        cases_opened,
        dict(Counter(d.action.value for d in [scorer.score(e) for e in events[:100]])),
    )
    return decisions_written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed the database with demo data")
    parser.add_argument(
        "--baseline",
        type=int,
        default=2000,
        help="Number of baseline events to generate (0 to skip)",
    )
    parser.add_argument("--arup", action="store_true", help="Include Arup attack pattern")
    parser.add_argument("--singapore", action="store_true", help="Include Singapore attack pattern")
    args = parser.parse_args()
    seed(args.baseline, args.arup, args.singapore)


if __name__ == "__main__":
    main()
