"""Long-running consumer worker.

Subscribes to the event topic and runs the full pipeline:
  1. Compute features
  2. Update the graph
  3. Score with rules + XGBoost
  4. Persist the decision

Used both locally (against Redpanda) and in production (against Kinesis via
the Lambda scorer handler — this worker is for environments where a
long-lived process is preferred, e.g., EC2 t3.micro in the AWS free tier).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.features import FeatureComputer
from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.infrastructure.adapters.factory import (
    get_consumer,
    get_offline_feature_store,
    get_online_feature_store,
)
from src.infrastructure.graph import get_graph_client
from src.infrastructure.persistence import init_db
from src.infrastructure.persistence.repos import DecisionRepository

logger = logging.getLogger(__name__)


_running = True


def _shutdown(*_args: object) -> None:
    global _running
    logger.info("Shutting down worker...")
    _running = False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    env = os.getenv("ENVIRONMENT", "local")
    logger.info("Starting worker in env=%s", env)

    consumer = get_consumer(env)
    computer = FeatureComputer()
    online_store = get_online_feature_store(env)
    offline_store = get_offline_feature_store(env)
    graph = get_graph_client()
    graph.init_schema()

    model_path = Path(os.getenv("MODEL_PATH", "models/xgb_v1.ubj"))
    if not model_path.exists():
        logger.warning("Model file %s not found; scorer will use heuristic fallback", model_path)
    model_version = ModelVersion(
        run_id=os.getenv("MODEL_RUN_ID", "production_xgb_v1"),
        model_name="identity_intel_xgb",
        stage=os.getenv("MODEL_STAGE", "Production"),
        algorithm="xgboost",
        trained_at=datetime.now(UTC),
        metrics={},
    )
    scorer = RealTimeScorer(model_path=model_path, model_version=model_version)

    init_db()
    decision_repo = DecisionRepository()

    offline_buffer: list[dict] = []
    OFFLINE_FLUSH = int(os.getenv("OFFLINE_FLUSH", "100"))

    def _flush_offline() -> None:
        nonlocal offline_buffer
        if not offline_buffer:
            return
        try:
            offline_store.write_batch(offline_buffer, partition_key=datetime.now(UTC))
            offline_buffer = []
        except Exception as e:
            logger.warning("Offline flush failed: %s", e)

    import atexit

    atexit.register(_flush_offline)

    while _running:
        for event in consumer.consume(timeout_ms=1000):
            try:
                # 1. Compute features
                snapshot = computer.compute(event)
                feature_dict = dict(
                    zip(snapshot.feature_names, snapshot.feature_values, strict=True)
                )

                # 2. Update graph
                try:
                    graph.upsert_event(event)
                except Exception as e:
                    logger.warning("Graph update failed: %s", e)

                # 3. Persist online features
                online_store.put(
                    entity_id=str(event.actor.account_id),
                    features=feature_dict,
                    ttl_seconds=86400,
                )

                # 4. Buffer offline features
                offline_buffer.append(
                    {
                        "entity_id": str(event.actor.account_id),
                        "event_id": str(event.event_id),
                        "event_time": event.event_time.isoformat(),
                        **feature_dict,
                    }
                )
                if len(offline_buffer) >= OFFLINE_FLUSH:
                    _flush_offline()

                # 5. Score
                decision = scorer.score(event)

                # 6. Persist
                decision_repo.insert(decision, event)
            except Exception as e:
                logger.exception("Error processing event: %s", e)
        # Brief idle sleep
        if _running:
            import time

            time.sleep(0.05)


if __name__ == "__main__":
    main()
