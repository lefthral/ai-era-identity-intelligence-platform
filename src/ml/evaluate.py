"""Evaluate a trained XGBoost model on a held-out synthetic dataset.

Loads a model from disk and computes precision/recall/F1/AUC at multiple
thresholds, with a focus on the deepfake-attack class.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.ml.dataset import build_training_dataset
from src.ml.train import load_config

logger = logging.getLogger(__name__)


def evaluate_model(config: dict[str, Any], model_path: Path) -> dict[str, Any]:
    logger.info("Loading dataset for evaluation...")
    X, y, events = build_training_dataset(
        n_baseline=int(__import__("os").getenv("EVAL_BASELINE_EVENTS", "5000")),
    )

    model = xgb.Booster()
    model.load_model(str(model_path))
    dmatrix = xgb.DMatrix(X.values)
    y_proba = model.predict(dmatrix)

    # Compute metrics at multiple thresholds
    results: dict[str, Any] = {"thresholds": []}
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        y_pred = (y_proba >= threshold).astype(int)
        results["thresholds"].append(
            {
                "threshold": threshold,
                "precision": float(precision_score(y, y_pred, zero_division=0)),
                "recall": float(recall_score(y, y_pred, zero_division=0)),
                "f1": float(f1_score(y, y_pred, zero_division=0)),
            }
        )

    # Overall AUC
    results["auc"] = float(roc_auc_score(y, y_proba))

    # Deepfake-specific recall: what fraction of deepfake events get caught?
    deepfake_mask = np.array([e.ground_truth_label.value == "deepfake_attack" for e in events])
    if deepfake_mask.sum() > 0:
        # At the default threshold of 0.5
        caught = (y_proba[deepfake_mask] >= 0.5).mean()
        caught_high = (y_proba[deepfake_mask] >= 0.8).mean()
        results["deepfake_recall_at_0.5"] = float(caught)
        results["deepfake_recall_at_0.8"] = float(caught_high)
        results["deepfake_event_count"] = int(deepfake_mask.sum())

    # Arup-specific: what fraction of Arup events get caught?
    arup_mask = np.array(
        [e.attack_pattern == "arup" if e.attack_pattern else False for e in events]
    )
    if arup_mask.sum() > 0:
        results["arup_recall_at_0.5"] = float((y_proba[arup_mask] >= 0.5).mean())
        results["arup_recall_at_0.8"] = float((y_proba[arup_mask] >= 0.8).mean())
        results["arup_event_count"] = int(arup_mask.sum())

    # Singapore-specific
    sg_mask = np.array(
        [e.attack_pattern == "singapore" if e.attack_pattern else False for e in events]
    )
    if sg_mask.sum() > 0:
        results["singapore_recall_at_0.5"] = float((y_proba[sg_mask] >= 0.5).mean())
        results["singapore_recall_at_0.8"] = float((y_proba[sg_mask] >= 0.8).mean())
        results["singapore_event_count"] = int(sg_mask.sum())

    logger.info("AUC: %.4f", results["auc"])
    logger.info(
        "Deepfake recall @ 0.5: %.2f%% (%d events)",
        results.get("deepfake_recall_at_0.5", 0) * 100,
        results.get("deepfake_event_count", 0),
    )
    logger.info(
        "Arup recall @ 0.5: %.2f%% (%d events)",
        results.get("arup_recall_at_0.5", 0) * 100,
        results.get("arup_event_count", 0),
    )
    logger.info(
        "Singapore recall @ 0.5: %.2f%% (%d events)",
        results.get("singapore_recall_at_0.5", 0) * 100,
        results.get("singapore_event_count", 0),
    )

    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Evaluate XGBoost model")
    parser.add_argument("--config", type=Path, default=Path("configs/xgb_v1.yaml"))
    parser.add_argument("--model", type=Path, default=Path("models/xgb_v1.ubj"))
    args = parser.parse_args()
    config = load_config(args.config)
    results = evaluate_model(config, args.model)
    out = Path("models/eval_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Evaluation complete. Results written to {out}")


if __name__ == "__main__":
    main()
