"""Tests for the adapter factory and the cloud-agnostic interface contracts.

These tests do NOT need real cloud connections — they verify that:
- The factory returns the right concrete class for each target
- The interface methods are wired (callable, return correct types)
- The factory's ENVIRONMENT env var override works
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.adapters.factory import (
    get_consumer,
    get_event_publisher,
    get_offline_feature_store,
    get_online_feature_store,
    get_publisher,
)
from src.infrastructure.adapters.interfaces import (
    EventConsumer,
    EventPublisher,
    OfflineFeatureStore,
    OnlineFeatureStore,
)


def test_factory_returns_local_publisher_by_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    p = get_publisher()
    assert isinstance(p, EventPublisher)
    # Local target uses the RedpandaPublisher
    assert p.__class__.__name__ == "RedpandaPublisher"


def test_factory_returns_aws_publisher_when_target_aws(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    p = get_publisher("aws", topic_or_stream="test-stream")
    assert isinstance(p, EventPublisher)
    assert p.__class__.__name__ == "KinesisPublisher"


def test_factory_get_event_publisher_is_alias(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    a = get_publisher()
    b = get_event_publisher()
    assert type(a) is type(b)


def test_factory_returns_local_consumer_by_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    c = get_consumer()
    assert isinstance(c, EventConsumer)
    assert c.__class__.__name__ == "RedpandaConsumer"


def test_factory_returns_aws_consumer_when_target_aws(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    c = get_consumer("aws", topic_or_stream="test-stream")
    assert isinstance(c, EventConsumer)
    # AWS uses the long-lived polling consumer; for a Lambda handler
    # you'd use KinesisLambdaConsumer instead.
    assert c.__class__.__name__ in (
        "KinesisPollingConsumer",
        "KinesisLambdaConsumer",
        "KinesisConsumer",
    )


def test_factory_offline_feature_store_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = get_offline_feature_store()
    assert isinstance(s, OfflineFeatureStore)
    assert s.__class__.__name__ == "MinIOOfflineFeatureStore"


def test_factory_online_feature_store_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = get_online_feature_store()
    assert isinstance(s, OnlineFeatureStore)
    assert s.__class__.__name__ == "PostgresOnlineFeatureStore"


def test_factory_respects_env_var(monkeypatch):
    """When ENVIRONMENT=aws, the factory should return AWS classes
    even without a target arg."""
    monkeypatch.setenv("ENVIRONMENT", "aws")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    p = get_publisher()
    assert p.__class__.__name__ == "KinesisPublisher"


def test_factory_target_overrides_env(monkeypatch):
    """Explicit target should override the env var."""
    monkeypatch.setenv("ENVIRONMENT", "aws")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    p = get_publisher("local")
    assert p.__class__.__name__ == "RedpandaPublisher"


def test_publisher_interface_methods_exist():
    """Verify the EventPublisher ABC has the required methods."""
    assert hasattr(EventPublisher, "publish")
    assert hasattr(EventPublisher, "publish_batch")
    assert hasattr(EventPublisher, "close")


def test_consumer_interface_methods_exist():
    """Verify the EventConsumer ABC has the required methods."""
    assert hasattr(EventConsumer, "consume")
    assert hasattr(EventConsumer, "commit")
    assert hasattr(EventConsumer, "close")


def test_offline_feature_store_interface_methods_exist():
    assert hasattr(OfflineFeatureStore, "write_batch")
    assert hasattr(OfflineFeatureStore, "read")


def test_online_feature_store_interface_methods_exist():
    assert hasattr(OnlineFeatureStore, "put")
    assert hasattr(OnlineFeatureStore, "get")
