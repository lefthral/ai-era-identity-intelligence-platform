"""Adapter factory.

Returns the appropriate concrete adapter for the configured target
(local | aws | gcp). The factory reads the ENVIRONMENT env var (set in
.env) and instantiates the right class.
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace

from src.infrastructure.adapters.interfaces import (
    EventConsumer,
    EventPublisher,
    OfflineFeatureStore,
    OnlineFeatureStore,
    OperationalStore,
)

logger = logging.getLogger(__name__)


def _resolve_target(target: str | None) -> str:
    env_value: str = target or os.getenv("ENVIRONMENT", "local") or "local"
    return env_value.lower()


def get_publisher(
    target: str | None = None, *, topic_or_stream: str = "identity-intel-events"
) -> EventPublisher:
    target = _resolve_target(target)
    if target == "aws":
        from src.infrastructure.adapters.aws.publisher import KinesisPublisher

        logger.info("Using AWS Kinesis publisher")
        return KinesisPublisher(stream_name=topic_or_stream)
    if target == "gcp":
        from src.infrastructure.adapters.gcp.publisher import PubSubPublisher

        logger.info("Using GCP Pub/Sub publisher")
        return PubSubPublisher(topic=topic_or_stream)
    from src.infrastructure.adapters.local.publisher import RedpandaPublisher

    logger.info("Using local Redpanda publisher")
    return RedpandaPublisher(topic=topic_or_stream)


# Alias used by scripts and external callers
get_event_publisher = get_publisher


def get_consumer(
    target: str | None = None, *, topic_or_stream: str = "identity-intel-events"
) -> EventConsumer:
    target = _resolve_target(target)
    if target == "aws":
        # The KinesisLambdaConsumer expects a Lambda event dict at
        # construction time (it processes one invocation's worth of
        # records). For a long-lived worker process against Kinesis
        # you'd want a KCL-based consumer; for the MVP we wrap the
        # Lambda consumer in a thin long-lived wrapper.
        from src.infrastructure.adapters.aws.consumer import KinesisPollingConsumer

        logger.info("Using AWS Kinesis (polling) consumer")
        return KinesisPollingConsumer(stream_name=topic_or_stream)
    # For local and GCP we use the Kafka-compatible Redpanda consumer
    # (GCP adapter delegates to Pub/Sub at the producer side; for a
    # long-lived worker process in GCP, swap this for a Pub/Sub pull
    # adapter — the EventConsumer interface is the same.)
    from src.infrastructure.adapters.local.consumer import RedpandaConsumer

    logger.info("Using local Redpanda consumer (target=%s)", target)
    return RedpandaConsumer(topic=topic_or_stream)


def get_offline_feature_store(target: str | None = None) -> OfflineFeatureStore:
    target = _resolve_target(target)
    if target == "aws":
        from src.infrastructure.adapters.aws.offline_features import S3OfflineFeatureStore

        return S3OfflineFeatureStore()
    if target == "gcp":
        from src.infrastructure.adapters.gcp.offline_features import GCSOfflineFeatureStore

        return GCSOfflineFeatureStore()
    from src.infrastructure.adapters.local.offline_features import MinIOOfflineFeatureStore

    return MinIOOfflineFeatureStore()


def get_online_feature_store(target: str | None = None) -> OnlineFeatureStore:
    target = _resolve_target(target)
    if target == "aws":
        from src.infrastructure.adapters.aws.online_features import DynamoDBOnlineFeatureStore

        return DynamoDBOnlineFeatureStore()
    if target == "gcp":
        from src.infrastructure.adapters.gcp.online_features import FirestoreOnlineFeatureStore

        return FirestoreOnlineFeatureStore()
    from src.infrastructure.adapters.local.online_features import PostgresOnlineFeatureStore

    return PostgresOnlineFeatureStore()


def get_operational_store(target: str | None = None) -> OperationalStore:
    """The operational store is Postgres everywhere — only the connection
    details differ. For now all targets return the SQLAlchemy repos."""
    from src.infrastructure.persistence.repos import (
        AuditLogRepository,
        CaseRepository,
        DecisionRepository,
        StatsRepository,
    )

    # Return a simple namespace exposing the four repositories
    return SimpleNamespace(  # type: ignore[return-value]
        decisions=DecisionRepository(),
        cases=CaseRepository(),
        audit=AuditLogRepository(),
        stats=StatsRepository(),
    )


__all__ = [
    "get_consumer",
    "get_event_publisher",
    "get_offline_feature_store",
    "get_online_feature_store",
    "get_operational_store",
    "get_publisher",
]
