"""Adapter interfaces.

These are the abstract contracts the application layer depends on.
Concrete implementations live in adapters/aws, adapters/gcp, adapters/local.

The pattern: business logic depends on these interfaces; cloud-specific
SDKs are confined to the adapter implementations. This is what makes
the platform multi-cloud-portable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import Any


class EventPublisher(ABC):
    """Publishes PaymentEvents to a streaming backbone."""

    @abstractmethod
    def publish(self, event) -> None: ...

    @abstractmethod
    def publish_batch(self, events: list) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class EventConsumer(ABC):
    """Consumes PaymentEvents from a streaming backbone."""

    @abstractmethod
    def consume(self, timeout_ms: int = 1000) -> Iterator: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class OfflineFeatureStore(ABC):
    """Stores historical feature snapshots in S3/GCS as Parquet."""

    @abstractmethod
    def write_batch(self, features: list[dict[str, Any]], partition_key: datetime) -> None: ...

    @abstractmethod
    def read(self, entity_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]: ...


class OnlineFeatureStore(ABC):
    """Stores current feature values for low-latency reads (DynamoDB/Firestore)."""

    @abstractmethod
    def put(self, entity_id: str, features: dict[str, float], ttl_seconds: int = 86400) -> None: ...

    @abstractmethod
    def get(self, entity_id: str) -> dict[str, float] | None: ...


class OperationalStore(ABC):
    """Stores cases, decisions, and the audit log (Postgres/Cloud SQL)."""

    @abstractmethod
    def execute(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execute_write(self, query: str, params: dict[str, Any]) -> None: ...


class ModelRegistry(ABC):
    """MLflow-backed model registry."""

    @abstractmethod
    def get_production_model(self, model_name: str) -> tuple[Any, str]: ...

    @abstractmethod
    def promote(self, run_id: str, stage: str) -> None: ...


__all__ = [
    "EventConsumer",
    "EventPublisher",
    "ModelRegistry",
    "OfflineFeatureStore",
    "OnlineFeatureStore",
    "OperationalStore",
]
