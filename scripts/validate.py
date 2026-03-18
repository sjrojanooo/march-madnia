"""Validate model accuracy on a holdout tournament season.

Consolidates validate_2025, validate_2025_final, validate_2025_without_2024,
validate_2024_holdout, compare_models_2025, and direct_model_comparison into
a single parameterized script.

Usage:
    uv run python scripts/validate.py --holdout 2025
    uv run python scripts/validate.py --holdout 2025 --train-preset no2024
    uv run python scripts/validate.py --holdout 2025 --bracket config/brackets/bracket_2025.json --actuals config/brackets/results_2025.json
    uv run python scripts/validate.py --holdout 2024 --train-seasons 2019 2021 2022 2023
    uv run python scripts/validate.py --model data/models/ensemble_with2025.joblib --holdout 2025
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.config import PROJECT_ROOT, load_bracket, load_features, load_results, load_seasons
from src.models.ensemble import build_ensemble, load_model
from src.models.evaluation import evaluate_model

logger = logging.getLogger(__name__)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"


def prepare_features(
    df: pd.DataFrame,
    feature_list: list[str] | None = None,
    medians: pd.Series | None = None,
) -> tuple[np.ndarray, list[str], pd.Series]:
    """Extract numeric features, impute, return (X, feature_cols, medians)."""
    meta_cols = {"season", "round", "team_a", "team_b", "target"}

    if feature_list is not None:
        feature_cols = [c for c in feature_list if c in df.columns]
    else:
        feature_cols = [c for c in df.columns if c not in meta_cols]
        non_numeric = df[feature_cols].select_dtypes(exclude="number").columns.tolist()
        if non_numeric:
            feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = df[feature_cols].copy()
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    computed_medians = X.median()
    fill_medians = medians if medians is not None else computed_medians
    X = X.fillna(fill_medians).fillna(0)

    return X.values, feature_cols, computed_medians


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate model on holdout tournament season.")
    parser.add_argument(
        "--holdout",
        type=int,
        required=True,
        help="Season to hold out for testing (e.g. 2025)",
    )
    train_group = parser.add_mutually_exclusive_group()
    train_group.add_argument(
        "--train-preset",
        help="Season preset for training (from config/seasons.yaml)",
    )
    train_group.add_argument(
        "--train-seasons",
        type=int,
        nargs="+",
        help="Explicit list of training seasons",
    )
    parser.add_argument(
        "--model",
        help="Path to a pre-trained model (.joblib). If provided, skips training.",
    )
    parser.add_argument(
        "--features",
        default="all",
        help="Feature set: 'slim', 'all' (default), or path to feature list file",
    )
    parser.add_argument(
        "--bracket",
        help="Path to bracket JSON for bracket simulation validation",
    )
    parser.add_argument(
        "--actuals",
        help="Path to actual results JSON for comparison",
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

    holdout = args.holdout
    feature_list = load_features(args.features)

    logger.info("=" * 80)
    logger.info("VALIDATION: holdout=%d", holdout)
    logger.info("=" * 80)

    # ------------------------------------------------------------------
    # Mode 1: Bracket simulation (if --bracket provided)
    # ------------------------------------------------------------------
    if args.bracket:
        from src.pipeline import run_prediction_pipeline

        bracket_data = load_bracket(args.bracket)
        logger.info("Running bracket simulation on %s ...", args.bracket)
        run_prediction_pipeline(bracket_data)

        if args.actuals:
            actuals = load_results(args.actuals)
            logger.info("\nACTUAL RESULTS:")
            logger.info("  Champion: %s", actuals.get("champion"))
            logger.info("  Runner-up: %s", actuals.get("runner_up"))
            for team_info in actuals.get("final_four", []):
                logger.info("  Final Four: %s (#%d)", team_info["team"], team_info["seed"])

        logger.info("\n" + "=" * 80)
        logger.info("BRACKET VALIDATION COMPLETE")
        logger.info("Check data/predictions/ for detailed outputs")
        logger.info("=" * 80)
        return

    # ------------------------------------------------------------------
    # Mode 2: Holdout accuracy test (train on subset, test on holdout)
    # ------------------------------------------------------------------

    # Determine training seasons
    if args.model:
        # Using pre-trained model — still need data for holdout evaluation
        pass
    elif args.train_seasons:
        train_seasons = args.train_seasons
    elif args.train_preset:
        train_seasons = load_seasons(args.train_preset)
    else:
        # Default: use all available seasons except holdout
        all_seasons = load_seasons("all")
        train_seasons = [s for s in all_seasons if s != holdout]

    # Load data
    source_path = PROCESSED_DIR / "matchup_training.parquet"
    if not source_path.exists():
        # Fallback to legacy file
        source_path = PROCESSED_DIR / "matchup_training_no2025.parquet"
    if not source_path.exists():
        logger.error("No matchup data found. Run feature pipeline first.")
        sys.exit(1)

    all_data = pd.read_parquet(source_path)

    # Split train/test
    test_df = all_data[all_data["season"] == holdout].copy()
    if test_df.empty:
        logger.error("No data found for holdout season %d", holdout)
        sys.exit(1)

    if args.model:
        # Load pre-trained model
        model = load_model(args.model)
        logger.info("Loaded pre-trained model: %s", args.model)

        # Load feature names if available
        model_stem = Path(args.model).stem
        feat_path = MODELS_DIR / f"feature_names_{model_stem.replace('ensemble_', '')}.txt"
        if feat_path.exists():
            feature_list = feat_path.read_text().strip().split("\n")
            logger.info("Loaded %d feature names from %s", len(feature_list), feat_path)

        X_test, feature_cols, _ = prepare_features(test_df, feature_list)
        y_test = test_df["target"].values
    else:
        train_df = all_data[all_data["season"].isin(train_seasons)].copy()
        if train_df.empty:
            logger.error("No training data for seasons %s", train_seasons)
            sys.exit(1)

        logger.info("\nTraining set:")
        season_counts = train_df.groupby("season").size()
        for season, count in season_counts.items():
            logger.info("  %d: %d games", season, count)
        logger.info("  TOTAL: %d games", len(train_df))
        logger.info("\nHoldout set (%d): %d games", holdout, len(test_df))

        # Prepare features
        X_train, feature_cols, train_medians = prepare_features(train_df, feature_list)
        y_train = train_df["target"].values

        X_test, _, _ = prepare_features(test_df, feature_list, medians=train_medians)
        y_test = test_df["target"].values

        logger.info("Train: %d samples, %d features", X_train.shape[0], X_train.shape[1])
        logger.info("Test: %d samples, %d features", X_test.shape[0], X_test.shape[1])

        # Train
        logger.info("\n--- Training ensemble ---")
        model = build_ensemble(X_train, y_train)
        train_acc = model.score(X_train, y_train)
        logger.info("Training accuracy: %.4f", train_acc)

    # ------------------------------------------------------------------
    # Evaluate on holdout
    # ------------------------------------------------------------------
    logger.info("\n" + "=" * 80)
    logger.info("HOLDOUT EVALUATION (season=%d)", holdout)
    logger.info("=" * 80)

    test_acc = model.score(X_test, y_test)
    logger.info("Holdout accuracy: %.4f", test_acc)

    results = evaluate_model(model, X_test, y_test)
    logger.info("Holdout metrics: %s", results)

    # #1 seed analysis
    if "team_a_seed" in test_df.columns:
        one_seed_mask = (test_df["team_a_seed"].values == 1) | (test_df["team_b_seed"].values == 1)
        if one_seed_mask.any():
            one_seed_acc = model.score(X_test[one_seed_mask], y_test[one_seed_mask])
            logger.info("#1 seed game accuracy: %.4f (%d games)", one_seed_acc, one_seed_mask.sum())

    # Show actuals if provided
    if args.actuals:
        actuals = load_results(args.actuals)
        logger.info("\nACTUAL RESULTS:")
        logger.info("  Champion: %s", actuals.get("champion"))
        logger.info("  Runner-up: %s", actuals.get("runner_up"))
        for team_info in actuals.get("final_four", []):
            logger.info("  Final Four: %s (#%d)", team_info["team"], team_info["seed"])

    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
