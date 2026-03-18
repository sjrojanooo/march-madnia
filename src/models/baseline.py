"""Baseline logistic regression model for March Madness predictions."""

import logging

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def build_baseline_model(X_train, y_train) -> Pipeline:
    """Build a baseline logistic regression model.

    Uses StandardScaler + LogisticRegression with L2 penalty.
    The pipeline exposes predict_proba for calibrated probabilities.

    Args:
        X_train: Training features (array-like or DataFrame).
        y_train: Training labels (array-like).

    Returns:
        Fitted sklearn Pipeline with StandardScaler and LogisticRegression.
    """
    logger.info(
        "Building baseline logistic regression model (n_samples=%d, n_features=%d)",
        X_train.shape[0],
        X_train.shape[1],
    )

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    max_iter=1000,
                    random_state=42,
                    solver="lbfgs",
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)

    train_accuracy = pipeline.score(X_train, y_train)
    logger.info("Baseline model training accuracy: %.4f", train_accuracy)

    return pipeline
