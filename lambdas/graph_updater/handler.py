"""Lambda handler: graph updater.

Triggered by Kinesis events. For each event, writes the entities and
relationships to Neo4j Aura. Runs Louvain community detection periodically
to identify suspected mule rings.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.adapters.aws.consumer import KinesisLambdaConsumer
from src.infrastructure.graph import get_graph_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)


_graph_client = None
_last_mule_ring_run: datetime | None = None


def _get_client():
    global _graph_client
    if _graph_client is None:
        _graph_client = get_graph_client()
        _graph_client.init_schema()
    return _graph_client


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    consumer = KinesisLambdaConsumer(event)
    client = _get_client()

    processed = 0
    errors = 0
    for payment_event in consumer.consume():
        try:
            client.upsert_event(payment_event)
            processed += 1
        except Exception as e:
            logger.exception("Graph upsert failed: %s", e)
            errors += 1

    # Run mule ring detection at most every 5 minutes
    global _last_mule_ring_run
    now = datetime.utcnow()
    if _last_mule_ring_run is None or (now - _last_mule_ring_run) > timedelta(minutes=5):
        try:
            rings = client.detect_mule_rings(min_community_size=3)
            logger.info("Detected %d suspected mule rings", len(rings))
            _last_mule_ring_run = now
        except Exception as e:
            logger.warning("Mule ring detection failed: %s", e)

    return {"processed": processed, "errors": errors}


if __name__ == "__main__":
    print(json.dumps(handler({"Records": []}, None)))
