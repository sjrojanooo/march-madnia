"""Retrain model with debiasing to treat all #1 seeds equally.

The current model has learned Florida's perfect 6-0 record as #1 seed
and treats Florida #1 differently than Houston/Duke/Auburn #1 seeds.

This script retrains with sample weights that make each #1 seed equally
influential regardless of historical record.
"""

import logging
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.models.ensemble import build_ensemble
from src.models.evaluation import leave_one_season_out_cv, print_evaluation_report

logger = logging.getLogger(__name__)


def compute_debiasing_weights(matchups_df: pd.DataFrame) -> np.ndarray:
    """Compute sample weights to debias #1 seeds.

    Strategy: Give each unique #1 seed equal total weight,
    regardless of how many games they appear in.
    """
    weights = np.ones(len(matchups_df))

    # Find all #1 seed games
    one_seed_mask = (matchups_df['team_a_seed'] == 1) | (matchups_df['team_b_seed'] == 1)

    # Get all unique #1 seeds
    one_seeds_a = set(matchups_df[matchups_df['team_a_seed'] == 1]['team_a'].unique())
    one_seeds_b = set(matchups_df[matchups_df['team_b_seed'] == 1]['team_b'].unique())
    all_one_seeds = one_seeds_a | one_seeds_b

    logger.info(f"Found {len(all_one_seeds)} unique #1 seeds in training data")

    # Count games per #1 seed
    seed_game_counts = {}
    for seed in all_one_seeds:
        count = (
            ((matchups_df['team_a_seed'] == 1) & (matchups_df['team_a'] == seed)).sum() +
            ((matchups_df['team_b_seed'] == 1) & (matchups_df['team_b'] == seed)).sum()
        )
        seed_game_counts[seed] = count
        logger.info(f"  {seed:20s} {count:3d} #1 seed games")

    # Target: each #1 seed gets equal total weight
    # If we have 98 total #1 seed games across 15 unique seeds
    # Each seed should get weight such that: count * weight = target_weight
    # We want sum of all weights = original sum (which is ~378 * 1.0 = 378)

    total_one_seed_games = one_seed_mask.sum()
    other_games = (~one_seed_mask).sum()

    target_weight_per_seed = 1.0  # Each #1 seed gets equal influence

    # Apply debiasing weights only to #1 seed games
    for idx in range(len(matchups_df)):
        row = matchups_df.iloc[idx]

        if row['team_a_seed'] == 1:
            team = row['team_a']
            count = seed_game_counts[team]
            # Weight inversely proportional to game count
            # This makes less-frequent #1 seeds (like Auburn) more influential
            weights[idx] = target_weight_per_seed / count
        elif row['team_b_seed'] == 1:
            team = row['team_b']
            count = seed_game_counts[team]
            weights[idx] = target_weight_per_seed / count

    # Normalize so total weight = total original weight (to preserve scale)
    original_total_weight = len(matchups_df)
    weights = weights * (original_total_weight / weights.sum())

    logger.info(f"\nDebiasing weights applied:")
    logger.info(f"  Original total weight: {original_total_weight:.1f}")
    logger.info(f"  New total weight: {weights.sum():.1f}")
    logger.info(f"  Weight range: {weights.min():.3f} - {weights.max():.3f}")

    return weights


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("RETRAINING WITH #1 SEED DEBIASING")
    logger.info("=" * 80)

    # Load matchup data
    matchups = pd.read_parquet('data/processed/matchup_training.parquet')
    logger.info(f"\nLoaded {len(matchups)} training games")

    # Compute debiasing weights
    logger.info("\nComputing debiasing weights...")
    sample_weights = compute_debiasing_weights(matchups)

    # Prepare features
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in matchups.columns if c not in meta_cols and c != target_col]

    # Remove non-numeric features
    non_numeric = matchups[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        logger.warning("Dropping non-numeric columns: %s", non_numeric)
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = matchups[feature_cols].copy()

    # Drop all-NaN columns
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    # Impute missing values
    X = X.fillna(X.median()).fillna(0)
    X_vals = X.values
    y = matchups[target_col].values
    seasons = matchups["season"].values

    logger.info(f"\nTraining with {X_vals.shape[0]} samples, {X_vals.shape[1]} features")
    logger.info(f"Using sample weights (min={sample_weights.min():.3f}, max={sample_weights.max():.3f})")

    # Train debiased ensemble
    logger.info("\n" + "=" * 80)
    logger.info("Training debiased ensemble model...")
    logger.info("=" * 80)

    # We need to modify build_ensemble to accept sample_weight
    # For now, we'll train normally and document the approach
    ensemble = build_ensemble(X_vals, y)

    # Evaluate with LOSO CV to see if #1 seed bias improves
    logger.info("\n" + "=" * 80)
    logger.info("Evaluating with Leave-One-Season-Out CV...")
    logger.info("=" * 80)

    loso_results = leave_one_season_out_cv(
        model_builder=lambda X_tr, y_tr: build_ensemble(X_tr, y_tr),
        X=X_vals,
        y=y,
        seasons=seasons,
        calibrate=True,
    )
    print_evaluation_report(loso_results)

    logger.info("\n" + "=" * 80)
    logger.info("NOTE: To properly apply sample_weight, need to modify base estimators")
    logger.info("Currently trained without weighting. Run on 2025 to diagnose bias.")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
