"""Model evaluation metrics and visualization for March Madness predictions."""

import logging
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console
from rich.table import Table
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

logger = logging.getLogger(__name__)
console = Console()


def evaluate_model(model, X_test, y_test) -> dict:
    """Evaluate a model on test data with multiple metrics.

    Args:
        model: Trained model with predict and predict_proba methods.
        X_test: Test features.
        y_test: Test labels.

    Returns:
        Dict with keys: brier_score, log_loss, accuracy, auc_roc.
    """
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    results = {
        "brier_score": brier_score_loss(y_test, y_prob),
        "log_loss": log_loss(y_test, y_prob),
        "accuracy": accuracy_score(y_test, y_pred),
        "auc_roc": roc_auc_score(y_test, y_prob),
    }

    logger.info(
        "Evaluation — Brier: %.4f | LogLoss: %.4f | Acc: %.4f | AUC: %.4f",
        results["brier_score"],
        results["log_loss"],
        results["accuracy"],
        results["auc_roc"],
    )

    return results


def leave_one_season_out_cv(
    model_builder: Callable,
    X,
    y,
    seasons,
    calibrate: bool = True,
) -> dict:
    """Perform leave-one-season-out cross-validation with optional calibration.

    For each unique season, trains on all other seasons and evaluates on
    the held-out season. Optionally applies temperature scaling calibration
    to improve probability estimates.

    Args:
        model_builder: Callable that takes (X_train, y_train) and returns
            a fitted model with predict/predict_proba methods.
        X: Full feature matrix (array-like).
        y: Full label array.
        seasons: Array of season identifiers aligned with X and y.
        calibrate: If True, applies temperature scaling to calibrate probabilities.

    Returns:
        Dict with:
            - 'mean': average metrics across all folds
            - 'folds': list of per-fold result dicts (each includes 'season')
    """
    from src.models.calibration import TemperatureScaling

    X = np.asarray(X)
    y = np.asarray(y)
    seasons = np.asarray(seasons)

    unique_seasons = np.unique(seasons)
    logger.info(
        "Leave-one-season-out CV with %d seasons: %s",
        len(unique_seasons),
        unique_seasons.tolist(),
    )

    fold_results = []

    for season in unique_seasons:
        train_mask = seasons != season
        test_mask = seasons == season

        X_train, y_train = X[train_mask], y[train_mask]
        X_test, y_test = X[test_mask], y[test_mask]

        if len(np.unique(y_test)) < 2:
            logger.warning("Season %s has only one class in test set, skipping.", season)
            continue

        logger.info(
            "Fold season=%s — train=%d, test=%d",
            season,
            len(y_train),
            len(y_test),
        )

        model = model_builder(X_train, y_train)

        # Apply temperature scaling calibration if requested
        if calibrate and len(X_train) >= 20:
            # Use last 20% of training data as calibration set
            calib_split = int(0.8 * len(X_train))
            X_calib = X_train[calib_split:]
            y_calib = y_train[calib_split:]

            y_prob_raw = model.predict_proba(X_test)[:, 1]
            scaler = TemperatureScaling()
            scaler.fit(model.predict_proba(X_calib)[:, 1], y_calib)
            y_prob_calibrated = scaler.calibrate(y_prob_raw)

            # Evaluate with calibrated probabilities
            fold_metrics = {
                "brier_score": brier_score_loss(y_test, y_prob_calibrated),
                "log_loss": log_loss(y_test, y_prob_calibrated),
                "accuracy": accuracy_score(y_test, model.predict(X_test)),
                "auc_roc": roc_auc_score(y_test, y_prob_calibrated),
            }
            logger.info(
                "Evaluation (calibrated) — Brier: %.4f | LogLoss: %.4f | Acc: %.4f | AUC: %.4f",
                fold_metrics["brier_score"],
                fold_metrics["log_loss"],
                fold_metrics["accuracy"],
                fold_metrics["auc_roc"],
            )
        else:
            fold_metrics = evaluate_model(model, X_test, y_test)

        fold_metrics["season"] = season
        fold_results.append(fold_metrics)

    # Compute average metrics
    metric_keys = ["brier_score", "log_loss", "accuracy", "auc_roc"]
    mean_metrics = {}
    for key in metric_keys:
        values = [f[key] for f in fold_results]
        mean_metrics[key] = float(np.mean(values))

    logger.info("LOSO CV mean metrics: %s", mean_metrics)

    return {
        "mean": mean_metrics,
        "folds": fold_results,
    }


def plot_calibration(
    model,
    X_test,
    y_test,
    save_path: str | None = None,
) -> None:
    """Plot a calibration curve (predicted probability vs actual win rate).

    Args:
        model: Trained model with predict_proba method.
        X_test: Test features.
        y_test: Test labels.
        save_path: If provided, save the plot to this path. Defaults to
            data/predictions/calibration_plot.png.
    """
    y_prob = model.predict_proba(X_test)[:, 1]

    fraction_of_positives, mean_predicted_value = calibration_curve(
        y_test, y_prob, n_bins=10, strategy="uniform"
    )

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(
        mean_predicted_value,
        fraction_of_positives,
        marker="o",
        linewidth=2,
        label="Model",
    )
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly calibrated")

    ax.set_xlabel("Mean Predicted Probability", fontsize=12)
    ax.set_ylabel("Fraction of Positives (Actual Win Rate)", fontsize=12)
    ax.set_title("Calibration Curve", fontsize=14)
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])

    plt.tight_layout()

    if save_path is None:
        save_path = "data/predictions/calibration_plot.png"

    output_path = Path(save_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info("Calibration plot saved to %s", output_path)


def plot_feature_importance(
    model,
    feature_names: list[str],
    top_n: int = 20,
    save_path: str | None = None,
) -> None:
    """Plot feature importance as a horizontal bar chart.

    For tree-based models, uses feature_importances_. For ensembles, attempts
    to extract importances from sub-estimators.

    Args:
        model: Trained model.
        feature_names: List of feature names matching model input.
        top_n: Number of top features to display.
        save_path: If provided, save the plot to this path. Defaults to
            data/predictions/feature_importance.png.
    """
    importances = _extract_feature_importances(model, len(feature_names))

    if importances is None:
        logger.warning("Could not extract feature importances from model.")
        return

    # Sort and take top N
    indices = np.argsort(importances)[::-1][:top_n]
    top_names = [feature_names[i] for i in indices]
    top_importances = importances[indices]

    # Reverse for horizontal bar chart (top feature at top)
    top_names = top_names[::-1]
    top_importances = top_importances[::-1]

    fig, ax = plt.subplots(figsize=(10, max(6, top_n * 0.35)))

    ax.barh(range(len(top_names)), top_importances, color="#2196F3", edgecolor="none")
    ax.set_yticks(range(len(top_names)))
    ax.set_yticklabels(top_names, fontsize=10)
    ax.set_xlabel("Importance", fontsize=12)
    ax.set_title(f"Top {top_n} Feature Importances", fontsize=14)
    ax.grid(True, axis="x", alpha=0.3)

    plt.tight_layout()

    if save_path is None:
        save_path = "data/predictions/feature_importance.png"

    output_path = Path(save_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info("Feature importance plot saved to %s", output_path)


def _extract_feature_importances(model, n_features: int):
    """Try to extract feature importances from various model types.

    Args:
        model: A trained model.
        n_features: Expected number of features.

    Returns:
        numpy array of importances, or None if extraction fails.
    """
    # Direct feature_importances_ (tree models)
    if hasattr(model, "feature_importances_"):
        return np.asarray(model.feature_importances_)

    # StackingClassifier — average importances from sub-estimators that have them
    if hasattr(model, "estimators_"):
        all_importances = []
        for estimator in model.estimators_:
            if hasattr(estimator, "feature_importances_"):
                imp = np.asarray(estimator.feature_importances_)
                # Normalize to [0, 1] before averaging
                imp_sum = imp.sum()
                if imp_sum > 0:
                    imp = imp / imp_sum
                all_importances.append(imp)

        if all_importances:
            return np.mean(all_importances, axis=0)

    # Pipeline — check last step
    if hasattr(model, "named_steps"):
        last_step = list(model.named_steps.values())[-1]
        return _extract_feature_importances(last_step, n_features)

    return None


def print_evaluation_report(results: dict) -> None:
    """Pretty-print evaluation results using Rich tables.

    Args:
        results: Dict of metric_name -> value (e.g., from evaluate_model).
            Can also be the output of leave_one_season_out_cv with 'mean'
            and 'folds' keys.
    """
    # Handle LOSO CV results
    if "mean" in results and "folds" in results:
        _print_loso_report(results)
        return

    # Simple results dict
    table = Table(title="Model Evaluation Results", show_header=True)
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="green", justify="right")

    metric_display = {
        "brier_score": "Brier Score",
        "log_loss": "Log Loss",
        "accuracy": "Accuracy",
        "auc_roc": "AUC-ROC",
    }

    for key, value in results.items():
        display_name = metric_display.get(key, key)
        if isinstance(value, float):
            table.add_row(display_name, f"{value:.4f}")
        else:
            table.add_row(display_name, str(value))

    console.print(table)


def _print_loso_report(results: dict) -> None:
    """Print leave-one-season-out CV report."""
    # Per-fold table
    fold_table = Table(title="Leave-One-Season-Out CV Results", show_header=True)
    fold_table.add_column("Season", style="cyan", justify="center")
    fold_table.add_column("Brier", style="white", justify="right")
    fold_table.add_column("LogLoss", style="white", justify="right")
    fold_table.add_column("Accuracy", style="white", justify="right")
    fold_table.add_column("AUC-ROC", style="white", justify="right")

    for fold in results["folds"]:
        fold_table.add_row(
            str(fold["season"]),
            f"{fold['brier_score']:.4f}",
            f"{fold['log_loss']:.4f}",
            f"{fold['accuracy']:.4f}",
            f"{fold['auc_roc']:.4f}",
        )

    # Add mean row
    mean = results["mean"]
    fold_table.add_row(
        "[bold]Mean[/bold]",
        f"[bold]{mean['brier_score']:.4f}[/bold]",
        f"[bold]{mean['log_loss']:.4f}[/bold]",
        f"[bold]{mean['accuracy']:.4f}[/bold]",
        f"[bold]{mean['auc_roc']:.4f}[/bold]",
    )

    console.print(fold_table)
