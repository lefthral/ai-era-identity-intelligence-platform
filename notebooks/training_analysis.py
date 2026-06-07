"""Training analysis script.

A script version of the training analysis notebook. Runs without
Jupyter so it can be in CI. Produces a `models/analysis.json`
artifact that the Streamlit UI can display.

This is a *study* of the synthetic data, not production training.
For production training use `python -m src.ml.train`.

Run:
    python -m notebooks.training_analysis
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.features import COUNTRY_RISK, FEATURE_NAMES
from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events

logger = logging.getLogger("analysis")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # 1. Build a labeled dataset
    logger.info("Building dataset...")
    events = []
    events.extend(generate_baseline_events(seed=42, n_events=2000))
    events.extend(generate_arup_events(seed=20240115))
    events.extend(generate_singapore_events(seed=20250326))
    events.sort(key=lambda e: e.event_time)
    logger.info("  Total: %d events", len(events))

    label_dist = Counter(e.ground_truth_label.value for e in events)
    logger.info("  Labels: %s", dict(label_dist))

    # 2. Score with the heuristic and compute per-class metrics
    from src.application.features import FeatureComputer

    computer = FeatureComputer()
    scorer = RealTimeScorer(model_path=None, model_version=_heuristic_version())
    now = max(e.event_time for e in events)

    tp = Counter()
    fp = Counter()
    fn = Counter()
    tn = Counter()
    scores_by_label: dict[str, list[float]] = {}

    for event in events:
        try:
            computer.compute(event, now=now)
            decision = scorer.score(event)
        except Exception as e:
            logger.warning("Skipping %s: %s", event.event_id, e)
            continue
        label = event.ground_truth_label.value
        scores_by_label.setdefault(label, []).append(decision.final_score)
        is_fraud = label != "legit"
        is_caught = decision.action.value != "ALLOW"
        if is_fraud and is_caught:
            tp[label] += 1
        elif is_fraud and not is_caught:
            fn[label] += 1
        elif not is_fraud and is_caught:
            fp[label] += 1
        else:
            tn[label] += 1

    # 3. Compute per-class metrics
    metrics = {}
    for label in label_dist:
        positives = tp[label] + fn[label]
        negatives = fp[label] + tn[label]
        recall = (tp[label] / positives) if positives else 0.0
        precision = (tp[label] / (tp[label] + fp[label])) if (tp[label] + fp[label]) else 0.0
        fpr = (fp[label] / negatives) if negatives else 0.0
        metrics[label] = {
            "n_total": label_dist[label],
            "n_caught": tp[label],
            "n_missed": fn[label],
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "false_positive_rate": round(fpr, 4),
            "score_mean": (
                round(sum(scores_by_label[label]) / len(scores_by_label[label]), 4)
                if scores_by_label.get(label)
                else 0.0
            ),
        }

    # 4. Country risk coverage check
    origin_countries = Counter(e.actor.country_code for e in events)
    dest_countries = Counter(e.counterparty.country_code for e in events)
    high_risk_dest = sum(
        1 for e in events if COUNTRY_RISK.get(e.counterparty.country_code, 0) >= 0.7
    )
    logger.info(
        "  High-risk destination events: %d / %d (%.1f%%)",
        high_risk_dest,
        len(events),
        100 * high_risk_dest / len(events),
    )

    # 5. Feature availability
    feature_check = dict.fromkeys(FEATURE_NAMES, 0)
    for event in events:
        try:
            snap = computer.compute(event, now=now)
            for n, v in zip(snap.feature_names, snap.feature_values, strict=True):
                if v is not None:
                    feature_check[n] += 1
        except Exception:
            pass

    # 6. Write the report
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "n_events": len(events),
            "label_distribution": dict(label_dist),
            "unique_actor_countries": len(origin_countries),
            "unique_counterparty_countries": len(dest_countries),
            "high_risk_destination_pct": round(100 * high_risk_dest / len(events), 2),
        },
        "metrics_by_label": metrics,
        "feature_availability": {
            name: {"events_with_value": n, "pct": round(100 * n / len(events), 2)}
            for name, n in feature_check.items()
        },
        "scorer": {
            "algorithm": "heuristic",
            "note": "Heuristic scorer used because no trained model is bundled. "
            "Run `make train` to fit an XGBoost model and re-run analysis.",
        },
    }

    out_path = Path("models/analysis.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info("Wrote %s", out_path)
    logger.info("Per-class recall:")
    for label, m in metrics.items():
        logger.info(
            "  %-25s recall=%.2f%%  precision=%.2f%%  fpr=%.2f%%",
            label,
            m["recall"] * 100,
            m["precision"] * 100,
            m["false_positive_rate"] * 100,
        )


def _heuristic_version():
    return ModelVersion(
        run_id="analysis_v1",
        model_name="identity_intel_xgb",
        stage="Production",
        algorithm="heuristic",
        trained_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics={},
    )


if __name__ == "__main__":
    main()
