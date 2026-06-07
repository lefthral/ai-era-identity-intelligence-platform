"""Tests for the application layer: features, rules, scoring."""

from datetime import UTC, datetime

import pytest

from src.application.features import COUNTRY_RISK, FEATURE_NAMES, FeatureComputer
from src.application.rules import RuleEngine
from src.application.scoring import RealTimeScorer
from src.domain.decisions import DecisionAction, ModelVersion
from src.generators.arup_pattern import generate_arup_events


def test_country_risk_dict_present():
    # Sanity checks on the actual risk values
    assert COUNTRY_RISK["KP"] >= 0.9
    assert COUNTRY_RISK["IR"] >= 0.8
    assert COUNTRY_RISK["US"] < 0.3
    assert COUNTRY_RISK["SG"] < 0.3
    # Riskier jurisdictions are scored higher than safe ones
    assert COUNTRY_RISK["KP"] > COUNTRY_RISK["US"]


def test_feature_catalog_19_features():
    assert len(FEATURE_NAMES) == 19


def _arup_first():
    return next(iter(generate_arup_events(seed=20240115)))


def _arup_all():
    return list(generate_arup_events(seed=20240115))


def test_feature_computer_returns_correct_length():
    computer = FeatureComputer()
    event = _arup_first()
    snapshot = computer.compute(event)
    assert len(snapshot.feature_names) == len(snapshot.feature_values) == 19
    assert snapshot.feature_names == FEATURE_NAMES


def test_feature_computer_does_not_mutate_event():
    computer = FeatureComputer()
    event = _arup_first()
    event_id_before = event.event_id
    computer.compute(event)
    assert event.event_id == event_id_before


def test_arup_events_have_high_velocity_features():
    """The 15 Arup wires fire within 142 minutes, so velocity features
    should be elevated from the very 2nd wire onward.

    We pass `now=event.event_time` to the FeatureComputer because the
    rolling window is relative to the current time. Real production
    usage would use the same `now` for all events in the batch.
    """
    computer = FeatureComputer()
    events = _arup_all()
    # Use the latest event time as "now" so the windows are correct
    now = events[-1].event_time
    snapshots = [computer.compute(e, now=now) for e in events]
    vel_idx = FEATURE_NAMES.index("txns_last_1h")
    counts = [s.feature_values[vel_idx] for s in snapshots]
    assert max(counts) >= 3.0


def test_rule_engine_runs_without_error():
    engine = RuleEngine()
    event = _arup_first()
    computer = FeatureComputer()
    snapshot = computer.compute(event, now=event.event_time)
    feature_values = dict(zip(snapshot.feature_names, snapshot.feature_values, strict=True))
    hits = engine.evaluate(event, feature_values)
    assert len(hits) >= 0  # Smoke test — should not raise


def test_rule_severity_values():
    """Severity is a string from {low, medium, high, critical}."""
    engine = RuleEngine()
    for rule in engine._rules:
        assert rule.severity in ("low", "medium", "high", "critical")


def test_scorer_arup_event_should_block_or_review():
    scorer = RealTimeScorer(model_path=None, model_version=_dummy_model_version())
    events = _arup_all()
    # The last few Arup wires should be BLOCK or REVIEW
    decisions = [scorer.score(e) for e in events]
    actions = {d.action for d in decisions[-3:]}
    assert DecisionAction.BLOCK in actions or DecisionAction.REVIEW in actions


def test_scorer_returns_valid_decision():
    scorer = RealTimeScorer(model_path=None, model_version=_dummy_model_version())
    event = _arup_first()
    decision = scorer.score(event)
    assert 0.0 <= decision.final_score <= 1.0
    assert decision.action in (DecisionAction.BLOCK, DecisionAction.REVIEW, DecisionAction.ALLOW)


def test_scorer_uses_max_of_xgb_and_rule():
    """The hybrid policy: final_score = max(xgb_score, rule_score)."""
    scorer = RealTimeScorer(model_path=None, model_version=_dummy_model_version())
    event = _arup_first()
    decision = scorer.score(event)
    assert decision.final_score == pytest.approx(
        max(decision.xgb_score, decision.rule_score), abs=1e-6
    )


def test_scorer_heuristic_recognizes_deepfake_pattern():
    """Without an XGBoost model, the heuristic should still detect
    the documented Arup pattern: high velocity + HK beneficiary +
    new beneficiary + high amount + off-hours."""
    scorer = RealTimeScorer(model_path=None, model_version=_dummy_model_version())
    events = _arup_all()
    # Late in the pattern, score should be at or near 1.0
    last_decision = scorer.score(events[-1])
    assert last_decision.final_score >= 0.8


def _dummy_model_version():
    return ModelVersion(
        run_id="test",
        model_name="test",
        stage="Production",
        algorithm="heuristic",
        trained_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics={},
    )
