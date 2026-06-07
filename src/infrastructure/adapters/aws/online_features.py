"""DynamoDB-backed online feature store (free tier: 25GB)."""

from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Any

from src.infrastructure.adapters.interfaces import OnlineFeatureStore

logger = logging.getLogger(__name__)


def _to_dynamodb_item(d: dict[str, float]) -> dict[str, Any]:
    return {k: Decimal(str(v)) for k, v in d.items()}


def _from_dynamodb_item(d: dict[str, Any]) -> dict[str, float]:
    return {k: float(v) for k, v in d.items()}


class DynamoDBOnlineFeatureStore(OnlineFeatureStore):
    def __init__(self, table_name: str | None = None, region: str | None = None):
        self.table_name = table_name or os.getenv(
            "AWS_DYNAMODB_ONLINE_FEATURES", "identity-intel-online-features"
        )
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._table = None

    def _ensure_table(self):
        if self._table is None:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            self._table = dynamodb.Table(self.table_name)
        return self._table

    def put(self, entity_id: str, features: dict[str, float], ttl_seconds: int = 86400) -> None:
        table = self._ensure_table()
        table.put_item(
            Item={
                "entity_id": entity_id,
                "features": _to_dynamodb_item(features),
                "expires_at": int(time.time()) + ttl_seconds,
            }
        )

    def get(self, entity_id: str) -> dict[str, float] | None:
        table = self._ensure_table()
        resp = table.get_item(Key={"entity_id": entity_id})
        item = resp.get("Item")
        if not item:
            return None
        if int(item.get("expires_at", 0)) < int(time.time()):
            return None
        return _from_dynamodb_item(item["features"])
