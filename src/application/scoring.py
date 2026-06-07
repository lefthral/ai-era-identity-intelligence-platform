"""Real-time scorer.

The scorer combines:
1. XGBoost model (probabilistic, trained on synthetic labels)
2. Rule engine (deterministic, hand-coded heuristics)

The final score is max(xgb_score, rule_score). Either source can flag
an event. This is the architectural separation required by IMF Notes
2026/004 and the U.S. Treasury FS-AI RMF.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import numpy as np

from src.application.features import FeatureComputer
from src.application.rules import RuleEngine
from src.domain.decisions import (
    Decision,
    DecisionAction,
    ModelVersion,
    RuleHit,
)
from src.domain.events import PaymentEvent

logger = logging.getLogger(__name__)


# Default thresholds (overridable via env or config)
DEFAULT_BLOCK_THRESHOLD = float(os.getenv("DECISION_BLOCK_THRESHOLD", "0.8"))
DEFAULT_REVIEW_THRESHOLD = float(os.getenv("DECISION_REVIEW_THRESHOLD", "0.5"))


def _rule_score_from_hits(hits: list[RuleHit]) -> float:
    """Convert rule hits to a 0-1 score by max severity."""
    if not hits:
        return 0.0
    severity_weights = {"critical": 1.0, "high": 0.85, "medium": 0.6, "low": 0.3}
    return max(severity_weights.get(h.severity, 0.5) for h in hits)


class RealTimeScorer:
    """Loads a trained XGBoost model and combines it with the rule engine."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        rule_engine: RuleEngine | None = None,
        feature_computer: FeatureComputer | None = None,
        model_version: ModelVersion | None = None,
        block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ) -> None:
        from xgboost import Booster

        self._model: Booster | None = None
        self._model_path = Path(model_path) if model_path else None
        self._rule_engine = rule_engine or RuleEngine()
        self._feature_computer = feature_computer or FeatureComputer()
        self._model_version = model_version or ModelVersion(
            run_id="heuristic_only",
            model_name="identity_intel_xgb",
            stage="Production",
            algorithm="heuristic_v0",
            trained_at=datetime.utcnow(),
            metrics={},
        )
        self._block_threshold = block_threshold
        self._review_threshold = review_threshold

        if self._model_path and self._model_path.exists():
            self._load_model(self._model_path)

    def _load_model(self, path: Path) -> None:
        try:
            import xgboost as xgb

            self._model = xgb.Booster()
            self._model.load_model(str(path))
            logger.info("Loaded XGBoost model from %s", path)
        except Exception as e:
            logger.warning("Could not load XGBoost model: %s. Using heuristic fallback.", e)
            self._model = None

    def score(self, event: PaymentEvent) -> Decision:
        # 1. Compute features
        feature_snapshot = self._feature_computer.compute(event)
        feature_dict = dict(
            zip(feature_snapshot.feature_names, feature_snapshot.feature_values, strict=True)
        )

        # 2. Evaluate rules
        rule_hits = self._rule_engine.evaluate(event, feature_dict)
        rule_score = _rule_score_from_hits(rule_hits)

        # 3. ML score (or heuristic fallback)
        if self._model is not None:
            try:
                import xgboost as xgb

                dmatrix = xgb.DMatrix(np.array([feature_snapshot.feature_values]))
                xgb_score = float(self._model.predict(dmatrix)[0])
            except Exception:
                logger.exception("XGBoost predict failed; using heuristic")
                xgb_score = self._heuristic_score(feature_dict, rule_hits)
        else:
            xgb_score = self._heuristic_score(feature_dict, rule_hits)

        # 4. Combine
        final_score = max(xgb_score, rule_score)

        # 5. Decide
        if final_score >= self._block_threshold:
            action = DecisionAction.BLOCK
        elif final_score >= self._review_threshold:
            action = DecisionAction.REVIEW
        else:
            action = DecisionAction.ALLOW

        # 6. Build explanation
        explanation = self._build_explanation(rule_hits, feature_dict, xgb_score, rule_score)

        return Decision(
            event_id=event.event_id,
            action=action,
            xgb_score=xgb_score,
            rule_score=rule_score,
            final_score=final_score,
            model_version=self._model_version,
            policy_version=self._rule_engine.policy_version,
            feature_snapshot=feature_snapshot,
            rule_hits=rule_hits,
            explanation=explanation,
        )

    def _heuristic_score(self, features: dict[str, float], hits: list[RuleHit]) -> float:
        """Naive weighted-sum heuristic used when no model is available."""
        score = 0.0
        score += min(features.get("amount_log", 0) / 7.0, 1.0) * 0.2
        score += features.get("is_high_risk_jurisdiction", 0) * 0.3
        score += features.get("mule_ring_member", 0) * 0.4
        score += min(abs(features.get("amount_zscore_user", 0)) / 10.0, 1.0) * 0.1
        score += features.get("first_time_beneficiary_high_amount", 0) * 0.2
        return float(min(score, 0.99))

    def _build_explanation(
        self,
        hits: list[RuleHit],
        features: dict[str, float],
        xgb_score: float,
        rule_score: float,
    ) -> str:
        parts: list[str] = []
        parts.append(f"XGBoost score: {xgb_score:.3f}. Rule score: {rule_score:.3f}.")
        if hits:
            parts.append(f"{len(hits)} rule(s) fired:")
            for h in hits:
                parts.append(f"  - [{h.severity.upper()}] {h.rule_id} {h.rule_name}: {h.reason}")
        else:
            parts.append("No rules fired.")
        top_features = sorted(features.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        parts.append("Top features by magnitude:")
        for name, value in top_features:
            parts.append(f"  - {name}: {value:.3f}")
        return "\n".join(parts)


def score_event(
    event: PaymentEvent,
    scorer: RealTimeScorer | None = None,
) -> Decision:
    if scorer is None:
        scorer = RealTimeScorer()
    return scorer.score(event)


__all__ = [
    "DEFAULT_BLOCK_THRESHOLD",
    "DEFAULT_REVIEW_THRESHOLD",
    "RealTimeScorer",
    "score_event",
]
