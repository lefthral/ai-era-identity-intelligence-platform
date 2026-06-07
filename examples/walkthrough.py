"""End-to-end walkthrough: no Docker, no external services required.

Runs the full pipeline (generate -> features -> rules -> score -> audit)
in a single process. Use this to demonstrate the project in an interview
or share a deterministic output snippet with a recruiter.

Run:
    python -m examples.walkthrough

Or with a model:
    python -m examples.walkthrough --use-model
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.features import FeatureComputer
from src.application.scoring import RealTimeScorer
from src.domain.decisions import DecisionAction, ModelVersion
from src.domain.events import GroundTruthLabel
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events

logger = logging.getLogger("walkthrough")


def banner(text: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}\n  {text}\n{bar}")


def stage1_generate() -> list:
    banner("Stage 1: Generate synthetic events")
    events = []
    events.extend(generate_baseline_events(seed=42, n_events=500))
    events.extend(generate_arup_events(seed=20240115))
    events.extend(generate_singapore_events(seed=20250326))
    events.sort(key=lambda e: e.event_time)
    print(f"  Generated {len(events)} events")
    print("    baseline: 500")
    print("    arup:     15 (HK mule chain, $25.6M)")
    print("    singapore: 3 ($499K + 2 follow-ups)")
    return events


def stage2_score(events: list, use_model: bool) -> tuple[list, list[float]]:
    banner(f"Stage 2: Compute features + score ({'XGBoost' if use_model else 'heuristic'})")
    computer = FeatureComputer()

    if use_model:
        model_path = Path("models/xgb_v1.ubj")
        if not model_path.exists():
            print(f"  Model file {model_path} not found; falling back to heuristic scorer")
            use_model = False

    scorer = RealTimeScorer(
        model_path=Path("models/xgb_v1.ubj") if use_model else None,
        model_version=ModelVersion(
            run_id="walkthrough_v1",
            model_name="identity_intel_xgb",
            stage="Production",
            algorithm="xgboost" if use_model else "heuristic",
            trained_at=datetime(2026, 1, 1, tzinfo=UTC),
            metrics={"auc": 0.97} if use_model else {},
        ),
    )

    decisions = []
    latencies_ms = []
    for event in events:
        t0 = time.perf_counter()
        snapshot = computer.compute(event)
        # Surface rule hits via the scorer's internal rule engine too
        # (RealTimeScorer.score does this; the line below is illustrative)
        decision = scorer.score(event)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
        decisions.append((event, decision, snapshot))

    print(f"  Scored {len(decisions)} events")
    p50 = statistics.median(latencies_ms)
    p99 = (
        statistics.quantiles(latencies_ms, n=100)[98]
        if len(latencies_ms) >= 100
        else max(latencies_ms)
    )
    print(f"  Latency p50: {p50:.2f}ms, p99: {p99:.2f}ms")
    return decisions, latencies_ms


def stage3_summarize(decisions: list) -> dict[str, Any]:
    banner("Stage 3: Decision summary")
    actions = Counter(d.action for _, d, _ in decisions)
    labels = Counter(e.ground_truth_label for e, _, _ in decisions)

    print("  Actions:")
    for action, count in actions.most_common():
        pct = 100 * count / len(decisions)
        print(f"    {action.value:8s} {count:5d}  ({pct:5.1f}%)")

    print("\n  Ground truth distribution:")
    for label, count in labels.most_common():
        print(f"    {label.value:25s} {count:5d}")

    # Confusion: how did we do on the deepfake events?
    deepfake_events = [
        (e, d) for e, d, _ in decisions if e.ground_truth_label == GroundTruthLabel.DEEPFAKE_ATTACK
    ]
    if deepfake_events:
        caught = sum(1 for _, d in deepfake_events if d.action != DecisionAction.ALLOW)
        blocked = sum(1 for _, d in deepfake_events if d.action == DecisionAction.BLOCK)
        print(
            f"\n  Deepfake attack recall: {caught}/{len(deepfake_events)} "
            f"({100 * caught / len(deepfake_events):.0f}%)"
        )
        print(
            f"  Deepfake BLOCK rate:    {blocked}/{len(deepfake_events)} "
            f"({100 * blocked / len(deepfake_events):.0f}%)"
        )

    # Arup-specific
    arup = [(e, d) for e, d, _ in decisions if getattr(e, "attack_pattern", None) == "arup"]
    if arup:
        caught = sum(1 for _, d in arup if d.action != DecisionAction.ALLOW)
        print(
            f"\n  Arup pattern ($25.6M, 15 wires): {caught}/{len(arup)} flagged "
            f"(caught ${sum(int(e.amount.value) for e, d in arup if d.action != DecisionAction.ALLOW) / 1_000_000:.1f}M)"
        )

    return {
        "total_events": len(decisions),
        "actions": {a.value: c for a, c in actions.items()},
        "labels": {lbl.value: c for lbl, c in labels.items()},
    }


def stage4_audit_sample(decisions: list) -> None:
    banner("Stage 4: Audit log sample (FS-AI RMF mapping)")
    print("  Every decision carries:")
    print("    - decision_id, event_id")
    print("    - model_version (run_id, model_name, stage, algorithm)")
    print("    - policy_version (policy_id, policy_hash)")
    print("    - final_score, xgb_score, rule_score")
    print("    - rule_hits (rule_id, severity, reason, evidence)")
    print("    - feature_snapshot (for replay)")
    print("    - data_lineage_event_id (OpenLineage)")

    blocked = [(e, d) for e, d, _s in decisions if d.action == DecisionAction.BLOCK]
    if blocked:
        print("\n  First BLOCK decision, full payload:")
        e, d = blocked[0]
        payload = {
            "decision_id": str(d.decision_id),
            "event_id": str(d.event_id),
            "actor_account": str(e.actor.account_id),
            "counterparty_country": e.counterparty.country_code,
            "amount": str(e.amount.value),
            "currency": e.amount.currency.value,
            "rail": e.rail.value,
            "action": d.action.value,
            "final_score": d.final_score,
            "xgb_score": d.xgb_score,
            "rule_score": d.rule_score,
            "rule_hits": [h.model_dump() for h in d.rule_hits],
            "model_version": {
                "run_id": d.model_version.run_id,
                "model_name": d.model_version.model_name,
                "stage": d.model_version.stage,
                "algorithm": d.model_version.algorithm,
            },
            "policy_version": {
                "policy_name": d.policy_version.policy_name,
                "policy_hash": d.policy_version.policy_hash,
                "rules_count": d.policy_version.rules_count,
            },
            "data_lineage_event_id": d.data_lineage_event_id,
        }
        print(json.dumps(payload, indent=2, default=str))


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    parser = argparse.ArgumentParser(description="End-to-end walkthrough")
    parser.add_argument(
        "--use-model", action="store_true", help="Use the trained XGBoost model if available"
    )
    args = parser.parse_args()

    events = stage1_generate()
    decisions, _ = stage2_score(events, use_model=args.use_model)
    summary = stage3_summarize(decisions)
    stage4_audit_sample(decisions)

    banner("Done")
    print("  Project:  /Users/aryanshinde/ai-era-identity-intelligence-platform")
    print("  Run UI:   make ui  (after `make start`)")
    print("  Run API:  make api")
    print("  Train:    make train")
    print()
    print("  Summary:", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
