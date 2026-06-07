"""Local Redpanda consumer (Kafka API)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator

from src.domain.events import PaymentEvent
from src.infrastructure.adapters.interfaces import EventConsumer

logger = logging.getLogger(__name__)


class RedpandaConsumer(EventConsumer):
    def __init__(
        self,
        topic: str = "identity-intel-events",
        group_id: str = "identity-intel-consumer",
        brokers: str | None = None,
    ):
        self.topic = topic
        self.group_id = group_id
        self.brokers = brokers or os.getenv("LOCAL_REDPANDA_BROKERS", "localhost:9092")
        self._consumer = None

    def _ensure_consumer(self):
        if self._consumer is None:
            from kafka import KafkaConsumer

            self._consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.brokers.split(","),
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )
        return self._consumer

    def consume(self, timeout_ms: int = 1000) -> Iterator[PaymentEvent]:
        consumer = self._ensure_consumer()
        for msg in consumer:
            try:
                yield PaymentEvent.model_validate(msg.value)
            except Exception as e:
                logger.exception("Failed to parse event: %s", e)

    def commit(self) -> None:
        if self._consumer is not None:
            self._consumer.commit()

    def close(self) -> None:
        if self._consumer is not None:
            self._consumer.close()
            self._consumer = None
