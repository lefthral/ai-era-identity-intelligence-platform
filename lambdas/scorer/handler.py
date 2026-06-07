"""Lambda handler: real-time scorer.

Triggered by Kinesis events. For each event:
1. Reads the latest online features from DynamoDB
2. Runs the rule engine
3. Runs the XGBoost model
4. Combines scores and produces a Decision
5. Writes the Decision to RDS Postgres
6. Emits the decision to a downstream "decisions" topic
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.infrastructure.adapters.aws.consumer import KinesisLambdaConsumer
from src.infrastructure.persistence import init_db
from src.infrastructure.persistence.repos import DecisionRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)


_scorer: RealTimeScorer | None = None
_decision_repo: DecisionRepository | None = None


def _get_scorer() -> RealTimeScorer:
    global _scorer
    if _scorer is None:
        # Look for the model in /var/task/models (Lambda deployment) or local
        candidates = [
            Path("/var/task/models/xgb_v1.ubj"),
            Path(__file__).parent.parent.parent / "models" / "xgb_v1.ubj",
        ]
        model_path = next((p for p in candidates if p.exists()), None)
        model_version = ModelVersion(
            run_id=os.getenv("MODEL_RUN_ID", "production_xgb_v1"),
            model_name="identity_intel_xgb",
            stage=os.getenv("MODEL_STAGE", "Production"),
            algorithm="xgboost",
            trained_at=datetime.utcnow(),
            metrics={},
        )
        _scorer = RealTimeScorer(model_path=model_path, model_version=model_version)
    return _scorer


def _get_repo() -> DecisionRepository:
    global _decision_repo
    if _decision_repo is None:
        init_db()
        _decision_repo = DecisionRepository()
    return _decision_repo


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    consumer = KinesisLambdaConsumer(event)
    scorer = _get_scorer()
    repo = _get_repo()

    processed = 0
    errors = 0
    for payment_event in consumer.consume():
        try:
            decision = scorer.score(payment_event)
            repo.insert(decision, payment_event)
            processed += 1
        except Exception as e:
            logger.exception("Scoring failed: %s", e)
            errors += 1

    return {"processed": processed, "errors": errors}


if __name__ == "__main__":
    print(json.dumps(handler({"Records": []}, None)))
