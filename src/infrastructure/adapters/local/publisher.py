"""Local Redpanda publisher (Kafka API)."""

from __future__ import annotations

import json
import logging
import os

from src.domain.events import PaymentEvent
from src.infrastructure.adapters.interfaces import EventPublisher

logger = logging.getLogger(__name__)


class RedpandaPublisher(EventPublisher):
    def __init__(self, topic: str = "identity-intel-events", brokers: str | None = None):
        self.topic = topic
        self.brokers = brokers or os.getenv("LOCAL_REDPANDA_BROKERS", "localhost:9092")
        self._producer = None

    def _ensure_producer(self):
        if self._producer is None:
            try:
                from kafka import KafkaProducer

                self._producer = KafkaProducer(
                    bootstrap_servers=self.brokers.split(","),
                    value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                    key_serializer=lambda k: str(k).encode("utf-8") if k else None,
                    acks="all",
                    retries=3,
                )
                logger.info("Connected to Redpanda at %s", self.brokers)
            except Exception as e:
                logger.error("Failed to connect to Redpanda: %s", e)
                raise
        return self._producer

    def publish(self, event: PaymentEvent) -> None:
        producer = self._ensure_producer()
        producer.send(
            self.topic,
            key=str(event.actor.account_id),
            value=event.model_dump(mode="json"),
        )

    def publish_batch(self, events: list[PaymentEvent]) -> None:
        producer = self._ensure_producer()
        for event in events:
            producer.send(
                self.topic,
                key=str(event.actor.account_id),
                value=event.model_dump(mode="json"),
            )
        producer.flush()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.flush()
            self._producer.close()
            self._producer = None
