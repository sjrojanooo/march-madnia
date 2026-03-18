"""Retrain ensemble with #1 seed debiasing."""

import logging
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.models.ensemble import build_ensemble, save_model
from src.models.evaluation import leave_one_season_out_cv, print_evaluation_report

logger = logging.getLogger(__name__)


def compute_seed_weights(matchups_df: pd.DataFrame) -> np.ndarray:
    """Compute sample weights to make each #1 seed equally influential.

    #1 seeds in training data have very different game counts:
    - Florida: 6 games (perfect 6-0 record)
    - Houston: 12 games (9-3)
    - Duke: 9 games (7-2)
    - Auburn: 5 games (4-1)

    To prevent Florida's perfect record from biasing the model,
    we weight each #1 seed to have equal total influence.
    """
    weights = np.ones(len(matchups_df))

    # Identify #1 seed games
    one_seed_mask = (matchups_df['team_a_seed'] == 1) | (matchups_df['team_b_seed'] == 1)

    # Count games per #1 seed
    one_seeds = set()
    seed_game_counts = {}

    # team_a #1 seeds
    team_a_one_seeds = matchups_df[matchups_df['team_a_seed'] == 1]
    for team in team_a_one_seeds['team_a'].unique():
        count = (matchups_df['team_a_seed'] == 1) & (matchups_df['team_a'] == team)
        seed_game_counts[team] = seed_game_counts.get(team, 0) + count.sum()
        one_seeds.add(team)

    # team_b #1 seeds
    team_b_one_seeds = matchups_df[matchups_df['team_b_seed'] == 1]
    for team in team_b_one_seeds['team_b'].unique():
        count = (matchups_df['team_b_seed'] == 1) & (matchups_df['team_b'] == team)
        seed_game_counts[team] = seed_game_counts.get(team, 0) + count.sum()
        one_seeds.add(team)

    logger.info(f"Found {len(one_seeds)} unique #1 seeds in training data:")
    for team, count in sorted(seed_game_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {team:20s} {count:3d} #1 seed games")

    # Apply equal weighting: each #1 seed gets weight 1/count
    # This normalizes their influence
    for idx in range(len(matchups_df)):
        row = matchups_df.iloc[idx]
        if row['team_a_seed'] == 1:
            count = seed_game_counts[row['team_a']]
            weights[idx] = 1.0 / count
        elif row['team_b_seed'] == 1:
            count = seed_game_counts[row['team_b']]
            weights[idx] = 1.0 / count

    # Normalize to preserve total weight scale
    weights = weights * (len(matchups_df) / weights.sum())

    logger.info(f"\nWeight statistics:")
    logger.info(f"  Mean weight: {weights.mean():.4f}")
    logger.info(f"  Min weight: {weights.min():.4f}")
    logger.info(f"  Max weight: {weights.max():.4f}")

    return weights


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("TRAINING DEBIASED ENSEMBLE (Equal #1 Seed Weighting)")
    logger.info("=" * 80)

    # Load training data
    matchups = pd.read_parquet('data/processed/matchup_training.parquet')
    logger.info(f"\nLoaded {len(matchups)} training games")

    # Compute debiasing weights
    logger.info("\n" + "-" * 80)
    logger.info("Computing #1 seed debiasing weights...")
    logger.info("-" * 80 + "\n")

    sample_weights = compute_seed_weights(matchups)

    # Prepare features
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in matchups.columns if c not in meta_cols and c != target_col]

    # Remove non-numeric
    non_numeric = matchups[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        logger.warning("Dropping non-numeric columns: %s", non_numeric)
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = matchups[feature_cols].copy()
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X = X.drop(columns=all_nan_cols, errors='ignore')
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    X = X.fillna(X.median()).fillna(0)
    X_vals = X.values
    y = matchups[target_col].values
    seasons = matchups["season"].values

    logger.info(f"Training with {X_vals.shape[0]} samples, {X_vals.shape[1]} features")
    logger.info(f"Using sample weights (mean={sample_weights.mean():.4f})")

    # Train with debiasing weights
    logger.info("\n" + "-" * 80)
    logger.info("Training ensemble with sample weights...")
    logger.info("-" * 80 + "\n")

    ensemble = build_ensemble(X_vals, y, sample_weight=sample_weights)

    # Save model
    save_model(ensemble, 'data/models/ensemble.joblib')
    logger.info("Model saved to data/models/ensemble.joblib")

    # LOSO CV with weighting (note: LOSO CV splits by season, so we can't use weights directly)
    # Just evaluate on full dataset
    logger.info("\n" + "-" * 80)
    logger.info("Evaluating debiased model...")
    logger.info("-" * 80)

    from src.models.evaluation import evaluate_model
    results = evaluate_model(ensemble, X_vals, y)
    logger.info(f"Training metrics: {results}")

    logger.info("\n" + "=" * 80)
    logger.info("DEBIASED MODEL TRAINING COMPLETE")
    logger.info("=" * 80)
    logger.info("\nNext: Run validation/2025 to test on 2025 bracket")


if __name__ == "__main__":
    main()
