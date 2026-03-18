"""Stacking ensemble model for March Madness predictions."""

import logging
from pathlib import Path

import joblib
from lightgbm import LGBMClassifier
from sklearn.ensemble import StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)


def build_ensemble(X_train, y_train, sample_weight=None) -> StackingClassifier:
    """Build a stacking ensemble classifier.

    Level 0 estimators:
        - LogisticRegression (with StandardScaler via Pipeline would be ideal,
          but StackingClassifier handles raw features; LR still works well)
        - XGBClassifier
        - LGBMClassifier

    Level 1 meta-learner:
        - LogisticRegression

    Uses 5-fold CV to generate meta-features for the stacking layer.

    Args:
        X_train: Training features.
        y_train: Training labels.

    Returns:
        Fitted StackingClassifier.
    """
    logger.info(
        "Building stacking ensemble (n_samples=%d, n_features=%d)",
        X_train.shape[0],
        X_train.shape[1],
    )

    estimators = [
        (
            "lr",
            Pipeline([
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(
                    C=0.1,
                    penalty="l2",
                    max_iter=1000,
                    random_state=42,
                    solver="lbfgs",
                )),
            ]),
        ),
        (
            "xgb",
            XGBClassifier(
                use_label_encoder=False,
                eval_metric="logloss",
                max_depth=3,           # was 5 — shallower trees overfit less
                learning_rate=0.05,
                n_estimators=150,      # was 300 — fewer trees on small dataset
                subsample=0.8,
                colsample_bytree=0.7,  # random feature subsampling per tree
                min_child_weight=3,    # require 3+ samples per leaf
                random_state=42,
                verbosity=0,
            ),
        ),
        (
            "lgbm",
            LGBMClassifier(
                max_depth=3,           # was 5
                learning_rate=0.05,
                n_estimators=150,      # was 300
                num_leaves=15,         # was 63 — 2^3=8 theoretical max, 15 gives headroom
                colsample_bytree=0.7,
                min_child_samples=10,  # require 10+ samples per leaf
                verbose=-1,
                random_state=42,
            ),
        ),
    ]

    meta_learner = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            C=0.1,
            max_iter=1000,
            random_state=42,
            solver="lbfgs",
        )),
    ])

    ensemble = StackingClassifier(
        estimators=estimators,
        final_estimator=meta_learner,
        cv=5,
        stack_method="predict_proba",
        passthrough=False,
        n_jobs=-1,
    )

    logger.info("Fitting stacking ensemble...")
    if sample_weight is not None:
        logger.info("Using sample weights to debias #1 seeds")
        ensemble.fit(X_train, y_train, sample_weight=sample_weight)
    else:
        ensemble.fit(X_train, y_train)

    train_accuracy = ensemble.score(X_train, y_train)
    logger.info("Stacking ensemble training accuracy: %.4f", train_accuracy)

    return ensemble


def save_model(model, path: str) -> None:
    """Save a trained model to disk using joblib.

    Args:
        model: The trained model/pipeline to save.
        path: File path for the saved model (e.g., 'models/ensemble.joblib').
    """
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, filepath)
    logger.info("Model saved to %s", filepath)


def load_model(path: str):
    """Load a trained model from disk using joblib.

    Args:
        path: File path of the saved model.

    Returns:
        The loaded model/pipeline.

    Raises:
        FileNotFoundError: If the model file does not exist.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Model file not found: {filepath}")

    model = joblib.load(filepath)
    logger.info("Model loaded from %s", filepath)
    return model
