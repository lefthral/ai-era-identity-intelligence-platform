"""Application layer: use cases that orchestrate domain and infrastructure."""

# Lazy import: api requires fastapi. Import via `from src.application.api import app`
# only when actually serving the API. Module-level imports here stay
# dependency-light so that the rest of the platform can be exercised
# without fastapi/uvicorn installed (useful for ML training, tests, walkthroughs).
from src.application.features import FeatureComputer, compute_features
from src.application.rules import RuleEngine, evaluate_rules
from src.application.scoring import RealTimeScorer, score_event

__all__ = [
    "FeatureComputer",
    "RealTimeScorer",
    "RuleEngine",
    "compute_features",
    "evaluate_rules",
    "score_event",
]
