"""Train the stacking ensemble model.

Consolidates train_with2025, train_no2024, train_debiased, and retrain_debiased
into a single parameterized script.

Usage:
    uv run python scripts/train.py                                # defaults: with2025 preset, slim features
    uv run python scripts/train.py --preset no2024                # named preset
    uv run python scripts/train.py --seasons 2019 2021 2022 2023 2025  # explicit seasons
    uv run python scripts/train.py --features all                 # use all numeric features
    uv run python scripts/train.py --features config/features/slim_8.txt
    uv run python scripts/train.py --name my_experiment           # -> ensemble_my_experiment.joblib
    uv run python scripts/train.py --debias                       # seed debiasing (experimental)
    uv run python scripts/train.py --skip-cv                      # skip LOSO CV
"""

from __future__ import annotations

import argparse
import logging
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.config import PROJECT_ROOT, load_features, load_seasons
from src.models.baseline import build_baseline_model
from src.models.boosting import build_lightgbm_model, build_xgboost_model
from src.models.ensemble import build_ensemble, save_model
from src.models.evaluation import leave_one_season_out_cv, print_evaluation_report

logger = logging.getLogger(__name__)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"


def prepare_features(
    df: pd.DataFrame,
    feature_list: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Extract numeric features, impute, and return (X, y, feature_cols).

    Parameters
    ----------
    df : DataFrame with feature columns + "target"
    feature_list : explicit list of columns to use, or None for all numeric
    """
    meta_cols = {"season", "round", "team_a", "team_b", "target"}

    if feature_list is not None:
        available = [c for c in feature_list if c in df.columns]
        missing = [c for c in feature_list if c not in df.columns]
        if missing:
            logger.warning("Requested features missing from data: %s", missing)
        feature_cols = available
    else:
        feature_cols = [c for c in df.columns if c not in meta_cols]
        non_numeric = df[feature_cols].select_dtypes(exclude="number").columns.tolist()
        if non_numeric:
            logger.warning("Dropping non-numeric columns: %s", non_numeric)
            feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = df[feature_cols].copy()

    # Drop all-NaN columns
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    X = X.fillna(X.median()).fillna(0)
    logger.info("Using %d features: %s", len(feature_cols), feature_cols)

    y = df["target"].values
    return X.values, y, feature_cols


def compute_seed_weights(matchups_df: pd.DataFrame) -> np.ndarray:
    """Compute sample weights to make each #1 seed equally influential."""
    weights = np.ones(len(matchups_df))

    # Count games per #1 seed
    seed_game_counts: dict[str, int] = {}
    for col_seed, col_team in [("team_a_seed", "team_a"), ("team_b_seed", "team_b")]:
        mask = matchups_df[col_seed] == 1
        for team in matchups_df.loc[mask, col_team].unique():
            team_mask = mask & (matchups_df[col_team] == team)
            seed_game_counts[team] = seed_game_counts.get(team, 0) + int(team_mask.sum())

    logger.info("Found %d unique #1 seeds in training data:", len(seed_game_counts))
    for team, count in sorted(seed_game_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info("  %20s %3d #1 seed games", team, count)

    # Apply equal weighting per #1 seed
    for idx in range(len(matchups_df)):
        row = matchups_df.iloc[idx]
        if row["team_a_seed"] == 1:
            weights[idx] = 1.0 / seed_game_counts[row["team_a"]]
        elif row["team_b_seed"] == 1:
            weights[idx] = 1.0 / seed_game_counts[row["team_b"]]

    weights = weights * (len(matchups_df) / weights.sum())
    logger.info("Weight range: %.3f - %.3f (mean=%.4f)", weights.min(), weights.max(), weights.mean())
    return weights


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the stacking ensemble model.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--preset",
        default="with2025",
        help="Season preset name from config/seasons.yaml (default: with2025)",
    )
    group.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        help="Explicit list of training seasons (e.g. 2019 2021 2022 2023 2025)",
    )
    parser.add_argument(
        "--features",
        default="slim",
        help="Feature set: 'slim' (default), 'all', or path to a feature list file",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Model name suffix (default: derived from preset/seasons)",
    )
    parser.add_argument(
        "--debias",
        action="store_true",
        help="Apply #1 seed debiasing weights (experimental)",
    )
    parser.add_argument(
        "--skip-cv",
        action="store_true",
        help="Skip leave-one-season-out cross-validation",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Resolve seasons
    if args.seasons:
        train_seasons = args.seasons
    else:
        train_seasons = load_seasons(args.preset)

    # Resolve features
    feature_list = load_features(args.features)

    # Resolve model name
    if args.name:
        model_name = args.name
    elif args.seasons:
        model_name = "custom_" + "_".join(str(s) for s in train_seasons)
    else:
        model_name = args.preset

    logger.info("=" * 80)
    logger.info("TRAINING MODEL: %s", model_name)
    logger.info("  Seasons: %s", train_seasons)
    logger.info("  Features: %s", "slim (8)" if feature_list else "all numeric")
    logger.info("  Debiasing: %s", "yes" if args.debias else "no")
    logger.info("=" * 80)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load training data
    # ------------------------------------------------------------------
    source_path = PROCESSED_DIR / "matchup_training.parquet"
    if not source_path.exists():
        logger.error(
            "Source data not found: %s. Run the feature pipeline first:\n"
            "  uv run python -m src.pipeline --stage features",
            source_path,
        )
        sys.exit(1)

    all_data = pd.read_parquet(source_path)
    train_df = all_data[all_data["season"].isin(train_seasons)].copy()

    if train_df.empty:
        logger.error("No training data for seasons %s", train_seasons)
        sys.exit(1)

    season_counts = train_df.groupby("season").size()
    for season, count in season_counts.items():
        logger.info("  %d: %d games", season, count)
    logger.info("  TOTAL: %d games", len(train_df))

    missing = [s for s in train_seasons if s not in season_counts.index]
    if missing:
        logger.warning("Expected seasons not found in data: %s", missing)

    # ------------------------------------------------------------------
    # 2. Prepare features
    # ------------------------------------------------------------------
    X, y, feature_cols = prepare_features(train_df, feature_list)
    seasons = train_df["season"].values
    logger.info("Training: %d samples, %d features", X.shape[0], X.shape[1])

    # ------------------------------------------------------------------
    # 3. Compute debiasing weights (optional)
    # ------------------------------------------------------------------
    sample_weight = None
    if args.debias:
        logger.info("Computing #1 seed debiasing weights...")
        sample_weight = compute_seed_weights(train_df)

    # ------------------------------------------------------------------
    # 4. Train base models
    # ------------------------------------------------------------------
    logger.info("\n--- Training baseline (Logistic Regression) ---")
    baseline = build_baseline_model(X, y)
    logger.info("Baseline train accuracy: %.4f", baseline.score(X, y))

    logger.info("\n--- Training XGBoost ---")
    xgb = build_xgboost_model(X, y)
    logger.info("XGBoost train accuracy: %.4f", xgb.score(X, y))

    logger.info("\n--- Training LightGBM ---")
    lgbm = build_lightgbm_model(X, y)
    logger.info("LightGBM train accuracy: %.4f", lgbm.score(X, y))

    # ------------------------------------------------------------------
    # 5. Stacking ensemble
    # ------------------------------------------------------------------
    logger.info("\n--- Training stacking ensemble ---")
    if sample_weight is not None:
        ensemble = build_ensemble(X, y, sample_weight=sample_weight)
    else:
        ensemble = build_ensemble(X, y)
    logger.info("Ensemble train accuracy: %.4f", ensemble.score(X, y))

    # ------------------------------------------------------------------
    # 6. Leave-one-season-out CV (optional)
    # ------------------------------------------------------------------
    if not args.skip_cv:
        logger.info("\n--- Leave-one-season-out CV (%d seasons) ---", len(set(seasons)))
        loso = leave_one_season_out_cv(
            model_builder=build_ensemble,
            X=X,
            y=y,
            seasons=seasons,
            calibrate=True,
        )
        try:
            print_evaluation_report(loso)
        except Exception:
            logger.info("LOSO mean accuracy: %.4f", loso.get("mean", {}).get("accuracy", 0))

    # ------------------------------------------------------------------
    # 7. Save model and feature names
    # ------------------------------------------------------------------
    model_path = str(MODELS_DIR / f"ensemble_{model_name}.joblib")
    save_model(ensemble, model_path)
    logger.info("Saved model -> %s", model_path)

    feat_names_path = MODELS_DIR / f"feature_names_{model_name}.txt"
    feat_names_path.write_text("\n".join(feature_cols))
    logger.info("Saved feature names -> %s", feat_names_path)

    logger.info("\n" + "=" * 80)
    logger.info("DONE: ensemble_%s.joblib (%d games, %d features)", model_name, len(train_df), len(feature_cols))
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
