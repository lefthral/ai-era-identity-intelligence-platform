"""Build a training dataset from synthetic events.

Replays the generators, computes features for each event, and assembles
a (X, y) pair for XGBoost training. The label is the event's
ground_truth_label, mapped to binary fraud (1) vs legit (0).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.application.features import FEATURE_NAMES, FeatureComputer
from src.domain.events import GroundTruthLabel, PaymentEvent
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events

logger = logging.getLogger(__name__)


# Label mapping
LABEL_TO_BINARY = {
    GroundTruthLabel.LEGIT: 0,
    GroundTruthLabel.STANDARD_FRAUD: 1,
    GroundTruthLabel.MONEY_MULE: 1,
    GroundTruthLabel.DEEPFAKE_ATTACK: 1,
    GroundTruthLabel.SYNTHETIC_IDENTITY: 1,
    GroundTruthLabel.UNKNOWN: -1,  # Excluded from training
}


def features_to_dataframe(features_list: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert a list of feature dicts to a DataFrame in canonical column order."""
    rows = []
    for f in features_list:
        rows.append([f.get(name, 0.0) for name in FEATURE_NAMES])
    return pd.DataFrame(rows, columns=FEATURE_NAMES)


def build_training_dataset(
    n_baseline: int = 10000,
    seed: int = 42,
) -> tuple[pd.DataFrame, np.ndarray, list[PaymentEvent]]:
    """Generate events, compute features, return (X_df, y_array, events)."""
    logger.info("Generating synthetic events...")
    all_events: list[PaymentEvent] = []
    all_events.extend(generate_baseline_events(seed=seed, n_events=n_baseline))
    all_events.extend(generate_arup_events(seed=seed))
    all_events.extend(generate_singapore_events(seed=seed))

    # Sort by event time so the rolling windows are computed correctly
    all_events.sort(key=lambda e: e.event_time)

    logger.info("Computing features for %d events...", len(all_events))
    computer = FeatureComputer()
    feature_dicts: list[dict[str, float]] = []
    labels: list[int] = []
    kept_events: list[PaymentEvent] = []
    for event in all_events:
        snapshot = computer.compute(event)
        feature_dicts.append(
            dict(zip(snapshot.feature_names, snapshot.feature_values, strict=True))
        )
        label = LABEL_TO_BINARY[event.ground_truth_label]
        if label == -1:
            continue
        labels.append(label)
        kept_events.append(event)

    X = features_to_dataframe(feature_dicts)
    # Filter out unknown-label rows
    X = X.iloc[: len(labels)]
    y = np.array(labels, dtype=np.int32)
    logger.info("Dataset: X=%s, y=%s (fraud rate: %.2f%%)", X.shape, y.shape, 100 * y.mean())
    return X, y, kept_events


__all__ = ["LABEL_TO_BINARY", "build_training_dataset", "features_to_dataframe"]
