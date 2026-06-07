"""AWS Kinesis publisher (free tier: 1M records/month)."""

from __future__ import annotations

import json
import logging
import os

from src.domain.events import PaymentEvent
from src.infrastructure.adapters.interfaces import EventPublisher

logger = logging.getLogger(__name__)


class KinesisPublisher(EventPublisher):
    def __init__(self, stream_name: str | None = None, region: str | None = None):
        self.stream_name = stream_name or os.getenv("AWS_KINESIS_STREAM", "identity-intel-events")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("kinesis", region_name=self.region)
        return self._client

    def publish(self, event: PaymentEvent) -> None:
        client = self._ensure_client()
        client.put_record(
            StreamName=self.stream_name,
            Data=json.dumps(event.model_dump(mode="json"), default=str).encode("utf-8"),
            PartitionKey=str(event.actor.account_id),
        )

    def publish_batch(self, events: list[PaymentEvent]) -> None:
        client = self._ensure_client()
        # Kinesis PutRecords supports up to 500 records per call
        for i in range(0, len(events), 500):
            batch = events[i : i + 500]
            client.put_records(
                StreamName=self.stream_name,
                Records=[
                    {
                        "Data": json.dumps(e.model_dump(mode="json"), default=str).encode("utf-8"),
                        "PartitionKey": str(e.actor.account_id),
                    }
                    for e in batch
                ],
            )

    def close(self) -> None:
        self._client = None
