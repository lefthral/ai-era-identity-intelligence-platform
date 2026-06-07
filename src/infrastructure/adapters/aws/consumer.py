"""AWS Kinesis consumers.

Two adapters:
- KinesisLambdaConsumer: invoked from Lambda with an event dict.
  Used by the lambdas/feature_computer, lambdas/graph_updater, and
  lambdas/scorer handlers.
- KinesisPollingConsumer: long-lived process that polls Kinesis
  shards. Used by the worker.py entry point on an EC2 t3.micro
  in the free-tier deployment.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Iterator

from src.domain.events import PaymentEvent
from src.infrastructure.adapters.interfaces import EventConsumer

logger = logging.getLogger(__name__)


class KinesisLambdaConsumer(EventConsumer):
    """Adapter for Lambda event source mappings from Kinesis."""

    def __init__(self, lambda_event: dict):
        self.lambda_event = lambda_event

    def consume(self, timeout_ms: int = 1000) -> Iterator[PaymentEvent]:
        for record in self.lambda_event.get("Records", []):
            try:
                payload = record["kinesis"]["data"]
                decoded = base64.b64decode(payload).decode("utf-8")
                yield PaymentEvent.model_validate(json.loads(decoded))
            except Exception as e:
                logger.exception("Failed to parse Kinesis record: %s", e)

    def commit(self) -> None:
        # Lambda commits offsets automatically via the event source mapping
        pass

    def close(self) -> None:
        pass


class KinesisPollingConsumer(EventConsumer):
    """Long-lived polling consumer against a Kinesis stream.

    For a real production deployment you'd use the KCL (Kinesis Client
    Library) which handles shard rebalancing, checkpointing to DynamoDB,
    and graceful failover. For the free-tier MVP we use boto3's
    get_shard_iterator + get_records polling loop, which is good enough
    for a single-shard stream.
    """

    def __init__(
        self,
        stream_name: str,
        region: str | None = None,
        shard_iterator_type: str = "TRIM_HORIZON",
        max_records_per_poll: int = 100,
    ):
        self.stream_name = stream_name
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.shard_iterator_type = shard_iterator_type
        self.max_records_per_poll = max_records_per_poll
        self._client = None
        self._shard_iterators: dict[str, str | None] = {}

    def _ensure_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("kinesis", region_name=self.region)
        return self._client

    def _ensure_shard_iterators(self) -> None:
        if self._shard_iterators:
            return
        client = self._ensure_client()
        resp = client.describe_stream(StreamName=self.stream_name)
        for shard in resp["StreamDescription"]["Shards"]:
            shard_id = shard["ShardId"]
            if shard_id.endswith("-closed"):  # Skip shards that have been resharded out
                continue
            try:
                iter_resp = client.get_shard_iterator(
                    StreamName=self.stream_name,
                    ShardId=shard_id,
                    ShardIteratorType=self.shard_iterator_type,
                )
                self._shard_iterators[shard_id] = iter_resp["ShardIterator"]
            except Exception as e:
                logger.warning("Failed to get iterator for shard %s: %s", shard_id, e)

    def consume(self, timeout_ms: int = 1000) -> Iterator[PaymentEvent]:
        self._ensure_shard_iterators()
        client = self._ensure_client()
        for shard_id, iterator in list(self._shard_iterators.items()):
            if not iterator:
                continue
            try:
                resp = client.get_records(ShardIterator=iterator, Limit=self.max_records_per_poll)
                self._shard_iterators[shard_id] = resp.get("NextShardIterator")
                for record in resp.get("Records", []):
                    try:
                        decoded = base64.b64decode(record["Data"]).decode("utf-8")
                        yield PaymentEvent.model_validate(json.loads(decoded))
                    except Exception as e:
                        logger.exception("Failed to parse Kinesis record: %s", e)
            except Exception as e:
                logger.warning("Kinesis poll failed for shard %s: %s", shard_id, e)
                self._shard_iterators[shard_id] = None

    def commit(self) -> None:
        # For polling without KCL we checkpoint explicitly. For the MVP we
        # rely on TRIM_HORIZON and Kinesis' 24h retention — adequate
        # for free-tier single-shard workloads.
        pass

    def close(self) -> None:
        self._client = None
        self._shard_iterators = {}


__all__ = ["KinesisLambdaConsumer", "KinesisPollingConsumer"]
