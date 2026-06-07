"""Train the XGBoost fraud classifier with MLflow tracking.

Usage:
    python -m src.ml.train --config configs/xgb_v1.yaml
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow
import mlflow.xgboost
import pandas as pd
import xgboost as xgb
import yaml
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from src.ml.dataset import build_training_dataset

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "model": {
        "name": "identity_intel_xgb",
        "stage": "Production",
        "params": {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": 6,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "scale_pos_weight": 5,  # Fraud is rare
            "random_state": 42,
        },
    },
    "training": {
        "test_size": 0.2,
        "random_state": 42,
        "early_stopping_rounds": 20,
    },
    "mlflow": {
        "tracking_uri": "http://localhost:5000",
        "experiment_name": "identity_intel_fraud",
    },
    "output": {
        "model_path": "models/xgb_v1.ubj",
    },
}


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.info("Config %s not found; using defaults", path)
        return DEFAULT_CONFIG
    with open(path) as f:
        cfg = yaml.safe_load(f)
    # Merge with defaults (shallow)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def train_model(config: dict[str, Any]) -> str:
    """Train and log to MLflow. Returns the run_id."""
    mlflow_cfg = config["mlflow"]
    mlflow.set_tracking_uri(mlflow_cfg["tracking_uri"])
    mlflow.set_experiment(mlflow_cfg["experiment_name"])

    logger.info("Building training dataset...")
    X, y, _ = build_training_dataset(
        n_baseline=int(os.getenv("TRAIN_BASELINE_EVENTS", "10000")),
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=config["training"]["test_size"],
        random_state=config["training"]["random_state"],
        stratify=y,
    )
    logger.info(
        "Train: %s, Test: %s (fraud rate train: %.2f%%, test: %.2f%%)",
        X_train.shape,
        X_test.shape,
        100 * y_train.mean(),
        100 * y_test.mean(),
    )

    model_cfg = config["model"]
    params = model_cfg["params"]
    output_path = Path(config["output"]["model_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with mlflow.start_run(run_name=f"xgb_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}") as run:
        mlflow.set_tag("model_stage", model_cfg["stage"])
        mlflow.set_tag("model_type", "xgboost")
        mlflow.log_params(params)
        mlflow.log_param("test_size", config["training"]["test_size"])
        mlflow.log_param("n_features", X.shape[1])
        mlflow.log_param("fraud_rate_train", float(y_train.mean()))
        mlflow.log_param("fraud_rate_test", float(y_test.mean()))

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dtest = xgb.DMatrix(X_test, label=y_test)

        model = xgb.train(
            params,
            dtrain,
            num_boost_round=params.pop("n_estimators", 200),
            evals=[(dtrain, "train"), (dtest, "test")],
            early_stopping_rounds=config["training"]["early_stopping_rounds"],
            verbose_eval=50,
        )

        # Predictions
        y_pred_proba = model.predict(dtest)
        y_pred = (y_pred_proba >= 0.5).astype(int)

        # Metrics
        auc = roc_auc_score(y_test, y_pred_proba)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        mlflow.log_metric("test_auc", auc)
        mlflow.log_metric("test_precision_at_0.5", precision)
        mlflow.log_metric("test_recall_at_0.5", recall)
        mlflow.log_metric("test_f1_at_0.5", f1)

        logger.info("Test AUC: %.4f", auc)
        logger.info("Test precision@0.5: %.4f", recall)
        logger.info("Test recall@0.5: %.4f", recall)
        logger.info("Test F1@0.5: %.4f", f1)
        logger.info("\n%s", classification_report(y_test, y_pred, target_names=["legit", "fraud"]))

        # Feature importance
        importance = model.get_score(importance_type="gain")
        importance_df = pd.DataFrame(
            [(f, importance.get(f"f{i}", 0.0)) for i, f in enumerate(X.columns)],
            columns=["feature", "importance"],
        ).sort_values("importance", ascending=False)
        importance_df.to_csv("models/feature_importance.csv", index=False)
        mlflow.log_artifact("models/feature_importance.csv")

        # Save model
        model.save_model(str(output_path))
        mlflow.log_artifact(str(output_path))

        # Register model
        try:
            mlflow.xgboost.log_model(
                xgb_model=model,
                artifact_path="model",
                registered_model_name=model_cfg["name"],
            )
        except Exception as e:
            logger.warning(
                "Model registration failed (MLflow may not have registry backend): %s", e
            )

        run_id = run.info.run_id
        logger.info("Training complete. Run ID: %s", run_id)
        return run_id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Train XGBoost fraud classifier")
    parser.add_argument("--config", type=Path, default=Path("configs/xgb_v1.yaml"))
    args = parser.parse_args()
    config = load_config(args.config)
    run_id = train_model(config)
    print(f"Trained model. Run ID: {run_id}")


if __name__ == "__main__":
    main()
