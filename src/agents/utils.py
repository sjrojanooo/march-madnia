"""Pipeline helpers for the agent collaboration loop.

Provides functions to run evaluation, apply feature changes, and rollback.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.agents.schemas import ModelMetrics

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"


def run_evaluation_pipeline() -> ModelMetrics:
    """Run features → validate → train → LOSO CV and return mean metrics.

    Shells out to the training script so that any code changes to feature
    modules are picked up fresh. Returns the LOSO CV mean metrics.
    """
    logger.info("Running evaluation pipeline ...")

    result = subprocess.run(
        [sys.executable, "scripts/train.py", "--log-level", "INFO"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=600,
    )

    if result.returncode != 0:
        logger.error(
            "Evaluation pipeline failed:\nstdout: %s\nstderr: %s",
            result.stdout,
            result.stderr,
        )
        raise RuntimeError(f"Evaluation pipeline exited with code {result.returncode}")

    # Parse LOSO metrics from training output
    return _parse_loso_metrics(result.stdout + result.stderr)


def _parse_loso_metrics(output: str) -> ModelMetrics:
    """Extract LOSO CV mean metrics from pipeline log output.

    Looks for the log line:
        LOSO CV mean metrics: {'brier_score': ..., ...}

    Parses using regex to avoid eval/exec.
    """
    for line in output.split("\n"):
        if "LOSO CV mean metrics:" not in line:
            continue

        # Extract individual metric values with regex
        accuracy = _extract_float(line, r"'accuracy':\s*([\d.]+)")
        brier = _extract_float(line, r"'brier_score':\s*([\d.]+)")
        logloss = _extract_float(line, r"'log_loss':\s*([\d.]+)")
        auc = _extract_float(line, r"'auc_roc':\s*([\d.]+)")

        if accuracy is not None:
            return ModelMetrics(
                accuracy=accuracy,
                brier_score=brier or 1.0,
                log_loss=logloss or 1.0,
                auc_roc=auc or 0.5,
            )

    logger.warning("Could not find LOSO metrics in output; returning defaults")
    return ModelMetrics()


def _extract_float(text: str, pattern: str) -> float | None:
    """Extract a float value from text using a regex pattern."""
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def get_current_metrics() -> ModelMetrics:
    """Get current model metrics by running the pipeline inline (no subprocess).

    Uses the existing pipeline functions directly for faster execution.
    """
    from src.models.ensemble import build_ensemble
    from src.models.evaluation import leave_one_season_out_cv
    from src.pipeline import run_feature_pipeline, run_validation

    matchups = run_feature_pipeline()
    if matchups.empty:
        raise RuntimeError("Feature pipeline produced no matchups")

    matchups, _report = run_validation(matchups)

    # Prepare features
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in matchups.columns if c not in meta_cols and c != target_col]
    non_numeric = matchups[feature_cols].select_dtypes(exclude="number").columns.tolist()
    feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = matchups[feature_cols].copy()
    all_nan_cols = X.columns[X.isna().all()].tolist()
    X = X.drop(columns=all_nan_cols)
    X = X.fillna(X.median()).fillna(0)

    X_arr = X.values
    y = matchups[target_col].values
    seasons = matchups["season"].values

    loso = leave_one_season_out_cv(
        model_builder=build_ensemble,
        X=X_arr,
        y=y,
        seasons=seasons,
    )

    mean = loso["mean"]
    return ModelMetrics(
        accuracy=mean["accuracy"],
        brier_score=mean["brier_score"],
        log_loss=mean["log_loss"],
        auc_roc=mean["auc_roc"],
    )


def get_validation_report() -> dict:
    """Load the most recent validation report from disk."""
    report_path = PROCESSED_DIR / "validation_report.json"
    if not report_path.exists():
        return {}
    return json.loads(report_path.read_text())


def get_feature_importances() -> dict[str, float]:
    """Extract feature importances from the trained model.

    Returns dict mapping feature name to importance score.
    """
    from src.models.ensemble import load_model
    from src.models.evaluation import _extract_feature_importances

    model_path = MODELS_DIR / "ensemble.joblib"
    feature_names_path = MODELS_DIR / "feature_names.txt"

    if not model_path.exists() or not feature_names_path.exists():
        return {}

    model = load_model(str(model_path))
    feature_names = feature_names_path.read_text().strip().split("\n")
    importances = _extract_feature_importances(model, len(feature_names))

    if importances is None:
        return {}

    return {name: float(imp) for name, imp in zip(feature_names, importances)}


def get_training_data_summary() -> dict:
    """Load training matchup data and return summary statistics."""
    matchup_path = PROCESSED_DIR / "matchup_training.parquet"
    if not matchup_path.exists():
        return {}

    df = pd.read_parquet(matchup_path)
    numeric_df = df.select_dtypes(include=[np.number])

    return {
        "shape": {"rows": len(df), "cols": len(df.columns)},
        "columns": list(df.columns),
        "numeric_columns": list(numeric_df.columns),
        "null_counts": {
            col: int(df[col].isna().sum())
            for col in df.columns
            if df[col].isna().sum() > 0
        },
        "seasons": sorted(df["season"].unique().tolist()) if "season" in df.columns else [],
    }


def check_guardrails(before: ModelMetrics, after: ModelMetrics) -> tuple[bool, str]:
    """Check whether the new metrics violate guard rails.

    Guard rails:
    - AUC-ROC must not drop > 0.01
    - Log loss must not increase > 0.02

    Returns (passed, reason).
    """
    auc_drop = before.auc_roc - after.auc_roc
    logloss_increase = after.log_loss - before.log_loss

    violations = []
    if auc_drop > 0.01:
        violations.append(f"AUC-ROC dropped by {auc_drop:.4f} (max allowed: 0.01)")
    if logloss_increase > 0.02:
        violations.append(f"Log loss increased by {logloss_increase:.4f} (max allowed: 0.02)")

    if violations:
        return False, "; ".join(violations)
    return True, "All guard rails passed"


def read_source_file(path: str) -> str:
    """Read a source file relative to the project root."""
    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        return ""
    return full_path.read_text()


def get_matchup_feature_definitions() -> dict:
    """Read current DIFF_FEATURES and RAW_FEATURE_COLS from matchup.py."""
    from src.features.matchup import DIFF_FEATURES, RAW_FEATURE_COLS, SPECIAL_DIFF_FEATURES

    return {
        "diff_features": dict(DIFF_FEATURES),
        "raw_feature_cols": list(RAW_FEATURE_COLS),
        "special_diff_features": list(SPECIAL_DIFF_FEATURES),
    }
