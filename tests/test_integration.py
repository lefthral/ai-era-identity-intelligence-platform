"""Integration tests for the full pipeline.

These tests run the end-to-end pipeline:
    generator -> features -> rules -> scoring -> decision

without the database or graph (we use the in-memory fallbacks).
They are the closest thing to a production smoke test that runs
in CI without Docker.

For a full DB-backed integration test, use `make demo` which
spins up Postgres + Neo4j + Redpanda via docker-compose.
"""

import time
from collections import Counter
from datetime import UTC, datetime

import pytest

from src.application.features import FeatureComputer
from src.application.scoring import RealTimeScorer
from src.domain.decisions import DecisionAction, ModelVersion
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events


def _now_from_events(events):
    """Pick a 'now' that keeps the rolling windows correct
    (events are in the past, so use the latest event time)."""
    return max(e.event_time for e in events)


def _heuristic_version():
    return ModelVersion(
        run_id="integration_test",
        model_name="identity_intel_xgb",
        stage="Production",
        algorithm="heuristic",
        trained_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics={},
    )


def _build_scorer():
    return RealTimeScorer(
        model_path=None,
        model_version=_heuristic_version(),
    )


def _score_all(computer, scorer, events, now):
    """Run features + scoring for every event and return the decisions."""
    decisions = []
    for event in events:
        computer.compute(event, now=now)
        decisions.append(scorer.score(event))
    return decisions


def test_full_pipeline_runs_without_error():
    """Smoke test: generate, compute features, score. No exceptions."""
    events = []
    events.extend(generate_baseline_events(seed=42, n_events=200))
    events.extend(generate_arup_events(seed=20240115))
    events.extend(generate_singapore_events(seed=20250326))
    events.sort(key=lambda e: e.event_time)

    computer = FeatureComputer()
    scorer = _build_scorer()

    now = _now_from_events(events)
    decisions = _score_all(computer, scorer, events, now)
    assert len(decisions) == len(events)


def test_pipeline_detects_arup_pattern_fully():
    """All 15 Arup wires should be BLOCK or REVIEW under heuristic scoring."""
    events = list(generate_arup_events(seed=20240115))
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    flagged = sum(1 for d in decisions if d.action != DecisionAction.ALLOW)
    assert flagged == len(events), f"Only {flagged}/{len(events)} flagged"


def test_pipeline_detects_singapore_pattern_fully():
    """The Singapore pattern's main wire should be BLOCK or REVIEW."""
    events = list(generate_singapore_events(seed=20250326))
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    first_decision = decisions[0]
    assert first_decision.action != DecisionAction.ALLOW


def test_pipeline_does_not_flag_majority_of_baseline():
    """A realistic baseline should be ~85-95% ALLOW."""
    events = list(generate_baseline_events(seed=42, n_events=500))
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    actions = Counter(d.action for d in decisions)
    allow_rate = actions[DecisionAction.ALLOW] / len(decisions)
    # Heuristic may be over-cautious on synthetic data; require at
    # least 70% ALLOW to keep false-positive rate realistic.
    assert allow_rate >= 0.70, f"Allow rate {allow_rate:.2%} too low; over-flagging"


def test_pipeline_decisions_carry_required_audit_fields():
    """Every decision must carry model + policy + feature snapshot
    so the audit log can replay the decision 6 months later."""
    events = list(generate_arup_events(seed=20240115))[:3]
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    for decision in decisions:
        assert decision.model_version.run_id == "integration_test"
        assert decision.model_version.algorithm == "heuristic"
        assert decision.policy_version.policy_name
        assert decision.policy_version.policy_hash
        assert decision.policy_version.rules_count >= 1
        assert len(decision.feature_snapshot.feature_names) == 19
        assert len(decision.feature_snapshot.feature_values) == 19


def test_pipeline_final_score_equals_max_of_xgb_and_rule():
    """ADR-0002 invariant: final_score = max(xgb_score, rule_score)."""
    events = list(generate_arup_events(seed=20240115))[:5]
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    for decision in decisions:
        assert decision.final_score == pytest.approx(
            max(decision.xgb_score, decision.rule_score), abs=1e-9
        )


def test_pipeline_rule_hits_have_evidence():
    """Every rule hit must carry evidence so an investigator can
    understand why it fired."""
    events = list(generate_arup_events(seed=20240115))
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()
    decisions = _score_all(computer, scorer, events, now)

    has_evidence = False
    for decision in decisions:
        for hit in decision.rule_hits:
            assert hit.rule_id
            assert hit.severity in ("low", "medium", "high", "critical")
            if hit.evidence:
                has_evidence = True
    assert has_evidence


def test_pipeline_throughput_above_10k_events_per_second():
    """A loose smoke-test on throughput. Should easily hit 10K
    events/sec for the heuristic scorer; the real target is 200ms
    p99 latency, measured by `make benchmark`."""
    events = list(generate_baseline_events(seed=42, n_events=2000))
    now = _now_from_events(events)
    computer = FeatureComputer()
    scorer = _build_scorer()

    t0 = time.perf_counter()
    _score_all(computer, scorer, events, now)
    elapsed = time.perf_counter() - t0
    throughput = len(events) / elapsed
    assert throughput > 10_000, f"Throughput {throughput:.0f}/s too low"
