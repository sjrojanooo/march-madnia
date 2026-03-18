"""XGBoost and LightGBM gradient boosting models for March Madness predictions."""

import logging

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.model_selection import GridSearchCV
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

# Threshold below which we use a reduced search grid to avoid overfitting.
SMALL_DATASET_THRESHOLD = 500

# Full hyperparameter grids
XGBOOST_PARAM_GRID_FULL = {
    "max_depth": [3, 5, 7],
    "learning_rate": [0.01, 0.05, 0.1],
    "n_estimators": [100, 300, 500],
    "subsample": [0.7, 0.8],
}

XGBOOST_PARAM_GRID_SMALL = {
    "max_depth": [3, 5],
    "learning_rate": [0.05, 0.1],
    "n_estimators": [100, 300],
    "subsample": [0.8],
}

LIGHTGBM_PARAM_GRID_FULL = {
    "max_depth": [3, 5, 7],
    "learning_rate": [0.01, 0.05, 0.1],
    "n_estimators": [100, 300, 500],
    "num_leaves": [31, 63, 127],
}

LIGHTGBM_PARAM_GRID_SMALL = {
    "max_depth": [3, 5],
    "learning_rate": [0.05, 0.1],
    "n_estimators": [100, 300],
    "num_leaves": [31, 63],
}


def build_xgboost_model(
    X_train,
    y_train,
    X_val=None,
    y_val=None,
) -> XGBClassifier:
    """Build an XGBoost classifier with hyperparameter search.

    Uses GridSearchCV with 5-fold CV to find the best hyperparameters.
    If a validation set is provided, early stopping is used.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Optional validation features for early stopping.
        y_val: Optional validation labels for early stopping.

    Returns:
        Best XGBClassifier from the grid search.
    """
    n_samples = X_train.shape[0]
    is_small = n_samples < SMALL_DATASET_THRESHOLD
    param_grid = XGBOOST_PARAM_GRID_SMALL if is_small else XGBOOST_PARAM_GRID_FULL

    logger.info(
        "Building XGBoost model (n_samples=%d, grid_size=%s)",
        n_samples,
        "small" if is_small else "full",
    )

    base_model = XGBClassifier(
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )

    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        cv=5,
        scoring="neg_log_loss",
        n_jobs=-1,
        verbose=0,
    )

    grid_search.fit(X_train, y_train)

    best_model: XGBClassifier = grid_search.best_estimator_
    logger.info("XGBoost best params: %s", grid_search.best_params_)
    logger.info("XGBoost best CV log_loss: %.4f", -grid_search.best_score_)

    # Refit with early stopping if validation data is provided
    if X_val is not None and y_val is not None:
        logger.info("Refitting XGBoost with early stopping (patience=20)")
        best_params = grid_search.best_params_.copy()
        best_model = XGBClassifier(
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
            early_stopping_rounds=20,
            **best_params,
        )
        best_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        logger.info("XGBoost early-stopped at %d rounds", best_model.best_iteration)

    return best_model


def build_lightgbm_model(
    X_train,
    y_train,
    X_val: np.ndarray | None = None,
    y_val: np.ndarray | None = None,
) -> LGBMClassifier:
    """Build a LightGBM classifier with hyperparameter search.

    Uses GridSearchCV with 5-fold CV to find the best hyperparameters.
    If a validation set is provided, early stopping is used.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Optional validation features for early stopping.
        y_val: Optional validation labels for early stopping.

    Returns:
        Best LGBMClassifier from the grid search.
    """
    n_samples = X_train.shape[0]
    is_small = n_samples < SMALL_DATASET_THRESHOLD
    param_grid = LIGHTGBM_PARAM_GRID_SMALL if is_small else LIGHTGBM_PARAM_GRID_FULL

    logger.info(
        "Building LightGBM model (n_samples=%d, grid_size=%s)",
        n_samples,
        "small" if is_small else "full",
    )

    base_model = LGBMClassifier(
        verbose=-1,
        random_state=42,
    )

    grid_search = GridSearchCV(
        estimator=base_model,
        param_grid=param_grid,
        cv=5,
        scoring="neg_log_loss",
        n_jobs=-1,
        verbose=0,
    )

    grid_search.fit(X_train, y_train)

    best_model: LGBMClassifier = grid_search.best_estimator_
    logger.info("LightGBM best params: %s", grid_search.best_params_)
    logger.info("LightGBM best CV log_loss: %.4f", -grid_search.best_score_)

    # Refit with early stopping if validation data is provided
    if X_val is not None and y_val is not None:
        logger.info("Refitting LightGBM with early stopping (patience=20)")
        best_params = grid_search.best_params_.copy()
        best_model = LGBMClassifier(
            verbose=-1,
            random_state=42,
            **best_params,
        )
        best_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            eval_metric="logloss",
            callbacks=[
                __import__("lightgbm").early_stopping(stopping_rounds=20, verbose=False),
                __import__("lightgbm").log_evaluation(period=0),
            ],
        )
        logger.info("LightGBM early-stopped at %d rounds", best_model.best_iteration_)

    return best_model
