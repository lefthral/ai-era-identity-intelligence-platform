"""Lambda handler: feature computer.

Triggered by Kinesis events. For each event:
1. Computes the feature vector (velocity, jurisdictional, behavioral, network)
2. Writes offline features to S3 (Parquet, partitioned)
3. Writes online features to DynamoDB
4. Emits the enriched event to a downstream "scored-events" topic

The Lambda deployment package includes the domain, application, and
infrastructure modules from the src/ tree.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add the project root to sys.path so we can import src.*
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.features import FeatureComputer
from src.infrastructure.adapters.aws.consumer import KinesisLambdaConsumer
from src.infrastructure.adapters.factory import get_offline_feature_store, get_online_feature_store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# Module-level singleton (Lambda container reuse)
_feature_computer: FeatureComputer | None = None
_offline_store = None
_online_store = None


def _get_computer() -> FeatureComputer:
    global _feature_computer
    if _feature_computer is None:
        _feature_computer = FeatureComputer()
    return _feature_computer


def _get_stores():
    global _offline_store, _online_store
    if _offline_store is None:
        _offline_store = get_offline_feature_store("aws")
    if _online_store is None:
        _online_store = get_online_feature_store("aws")
    return _offline_store, _online_store


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point."""
    consumer = KinesisLambdaConsumer(event)
    computer = _get_computer()
    offline_store, online_store = _get_stores()

    processed = 0
    errors = 0
    for payment_event in consumer.consume():
        try:
            snapshot = computer.compute(payment_event)
            feature_dict = dict(zip(snapshot.feature_names, snapshot.feature_values, strict=True))

            # Persist online features
            online_store.put(
                entity_id=str(payment_event.actor.account_id),
                features=feature_dict,
                ttl_seconds=86400,
            )

            # Batch offline features (in production this would be batched
            # with a small buffer; for the Lambda handler we write per-event)
            try:
                offline_store.write_batch(
                    features=[
                        {
                            "entity_id": str(payment_event.actor.account_id),
                            "event_id": str(payment_event.event_id),
                            "event_time": payment_event.event_time.isoformat(),
                            **feature_dict,
                        }
                    ],
                    partition_key=datetime.utcnow(),
                )
            except Exception as e:
                logger.warning("Offline feature write failed: %s", e)

            processed += 1
        except Exception as e:
            logger.exception("Failed to process event: %s", e)
            errors += 1

    return {"processed": processed, "errors": errors}


# For local invocation
if __name__ == "__main__":
    import base64

    sample_event = {
        "Records": [
            {
                "kinesis": {
                    "data": base64.b64encode(
                        json.dumps(
                            {
                                "event_id": "00000000-0000-0000-0000-000000000001",
                                "event_type": "PAYMENT_INITIATED",
                                "event_time": datetime.utcnow().isoformat(),
                                "rail": "WIRE",
                                "actor": {
                                    "person_id": "00000000-0000-0000-0000-000000000002",
                                    "account_id": "00000000-0000-0000-0000-000000000003",
                                    "country_code": "US",
                                },
                                "counterparty": {
                                    "account_id": "00000000-0000-0000-0000-000000000004",
                                    "country_code": "HK",
                                    "is_new_beneficiary": True,
                                    "account_age_days": 5,
                                },
                                "amount": {"value": 500000, "currency": "USD"},
                                "ground_truth_label": "deepfake_attack",
                            }
                        ).encode()
                    ).decode(),
                    "partitionKey": "test",
                }
            }
        ]
    }
    print(json.dumps(handler(sample_event, None)))
