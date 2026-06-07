"""GCP Pub/Sub publisher (free tier: 10GB/month)."""

from __future__ import annotations

import json
import logging
import os

from src.domain.events import PaymentEvent
from src.infrastructure.adapters.interfaces import EventPublisher

logger = logging.getLogger(__name__)


class PubSubPublisher(EventPublisher):
    def __init__(self, topic: str | None = None, project_id: str | None = None):
        self.topic = topic or os.getenv("GCP_PUBSUB_TOPIC", "identity-intel-events")
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self._publisher = None

    def _ensure_publisher(self):
        if self._publisher is None:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
        return self._publisher

    def _topic_path(self) -> str:
        return self._ensure_publisher().topic_path(self.project_id, self.topic)

    def publish(self, event: PaymentEvent) -> None:
        publisher = self._ensure_publisher()
        data = json.dumps(event.model_dump(mode="json"), default=str).encode("utf-8")
        publisher.publish(self._topic_path(), data=data, account_id=str(event.actor.account_id))

    def publish_batch(self, events: list[PaymentEvent]) -> None:
        publisher = self._ensure_publisher()
        futures = []
        for event in events:
            data = json.dumps(event.model_dump(mode="json"), default=str).encode("utf-8")
            futures.append(publisher.publish(self._topic_path(), data=data))
        for f in futures:
            f.result()

    def close(self) -> None:
        # PublisherClient doesn't need explicit close
        self._publisher = None
