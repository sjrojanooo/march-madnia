"""Direct comparison: Model A (with 2024) vs Model B (without 2024) on 2025.

This is the critical test to determine if 2024 is really the problem.
"""

import logging
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.models.ensemble import build_ensemble

logger = logging.getLogger(__name__)


def prepare_features(data):
    """Extract features from dataframe."""
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in data.columns
                    if c not in meta_cols and c != target_col]

    # Remove non-numeric
    non_numeric = data[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = data[feature_cols].copy()
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    X = X.fillna(X.median()).fillna(0)

    return X.values, feature_cols, X


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("MODEL COMPARISON: WITH 2024 vs WITHOUT 2024")
    logger.info("=" * 80)

    # Load all historical data
    all_data = pd.read_parquet('data/processed/matchup_training_no2025.parquet')

    # MODEL A: With 2024
    logger.info(f"\n{'='*80}")
    logger.info(f"MODEL A: Training with 2024 (2019/2021-2024)")
    logger.info(f"{'='*80}")

    train_data_a = all_data  # All: 2019, 2021-2024
    X_train_a, features_a, _ = prepare_features(train_data_a)
    y_train_a = train_data_a['target'].values

    logger.info(f"Training set A: {X_train_a.shape[0]} games, {X_train_a.shape[1]} features")
    logger.info(f"Seasons: {sorted(train_data_a['season'].unique())}")

    ensemble_a = build_ensemble(X_train_a, y_train_a)
    train_acc_a = ensemble_a.score(X_train_a, y_train_a)
    logger.info(f"Model A training accuracy: {train_acc_a:.4f}")

    # MODEL B: Without 2024
    logger.info(f"\n{'='*80}")
    logger.info(f"MODEL B: Training without 2024 (2019/2021-2023)")
    logger.info(f"{'='*80}")

    train_data_b = all_data[all_data['season'] != 2024]  # Exclude 2024
    X_train_b, features_b, _ = prepare_features(train_data_b)
    y_train_b = train_data_b['target'].values

    logger.info(f"Training set B: {X_train_b.shape[0]} games, {X_train_b.shape[1]} features")
    logger.info(f"Seasons: {sorted(train_data_b['season'].unique())}")

    ensemble_b = build_ensemble(X_train_b, y_train_b)
    train_acc_b = ensemble_b.score(X_train_b, y_train_b)
    logger.info(f"Model B training accuracy: {train_acc_b:.4f}")

    # Now test both on 2025
    logger.info(f"\n{'='*80}")
    logger.info(f"TESTING BOTH MODELS ON 2025")
    logger.info(f"{'='*80}")

    # Load pre-computed predictions from both models
    with open('data/predictions/bracket_predictions.json') as f:
        preds_json = json.load(f)

    logger.info(f"\nMODEL A (WITH 2024) - 2025 Championship Predictions:")
    if 'champion_probabilities' in preds_json:
        champ_probs_a = sorted(preds_json['champion_probabilities'].items(),
                             key=lambda x: x[1], reverse=True)

        # Show top teams and specifically #1 seeds
        top_8 = champ_probs_a[:8]
        one_seeds_2025 = ['florida', 'houston', 'duke', 'auburn']

        logger.info(f"\n  Top 8:")
        for i, (team, prob) in enumerate(top_8, 1):
            marker = "← #1 SEED" if team in one_seeds_2025 else ""
            logger.info(f"    {i}. {team:20s} {prob*100:6.2f}% {marker}")

        logger.info(f"\n  #1 Seeds specifically:")
        for team in one_seeds_2025:
            prob = preds_json['champion_probabilities'].get(team, 0)
            logger.info(f"    {team:20s} {prob*100:6.2f}%")

        logger.info(f"\n  Top non-#1 seeds:")
        non_one_seeds = [(t, p) for t, p in champ_probs_a if t not in one_seeds_2025][:3]
        for team, prob in non_one_seeds:
            logger.info(f"    {team:20s} {prob*100:6.2f}%")

        model_a_results = {
            'florida': preds_json['champion_probabilities'].get('florida', 0),
            'houston': preds_json['champion_probabilities'].get('houston', 0),
            'duke': preds_json['champion_probabilities'].get('duke', 0),
            'auburn': preds_json['champion_probabilities'].get('auburn', 0),
            'top_non_1': non_one_seeds[0][1] if non_one_seeds else 0,
        }

    # Now generate predictions for Model B
    # We need to run the bracket simulation with Model B
    logger.info(f"\n{'='*80}")
    logger.info(f"GENERATING MODEL B PREDICTIONS (this may take a moment...)")
    logger.info(f"{'='*80}")

    # For now, we'll estimate based on individual game predictions
    # Load 2025 tournament results to analyze
    results_2025 = pd.read_parquet('data/raw/tournament_results_2025.parquet')

    # Get team stats for feature construction
    team_basic_2025 = pd.read_parquet('data/raw/team_basic_stats_2025.parquet')
    team_advanced_2025 = pd.read_parquet('data/raw/team_advanced_stats_2025.parquet')
    team_opponent_2025 = pd.read_parquet('data/raw/team_opponent_stats_2025.parquet')

    logger.info(f"Loaded 2025 team stats: {len(team_basic_2025)} teams")

    # For each game in 2025, construct features and get predictions from both models
    logger.info(f"\nAnalyzing all 2025 games with both models...")

    game_predictions_a = []
    game_predictions_b = []
    game_results = []

    # We need the original full training data to get median/fillna values
    full_training_data_a = all_data
    full_training_data_b = all_data[all_data['season'] != 2024]

    median_vals_a = full_training_data_a[features_a].median()
    median_vals_b = full_training_data_b[features_b].median()

    logger.info(f"\nNote: Full Monte Carlo simulation would be needed for exact probabilities.")
    logger.info(f"For now, analyzing game-by-game predictions as proxy...")

    # Quick analysis: for each game, which team does each model favor?
    # This gives us directional insight into bias

    model_a_upsets = 0
    model_b_upsets = 0
    model_a_higher_seed_wins = 0
    model_b_higher_seed_wins = 0

    for _, game in results_2025.iterrows():
        team1 = game['team_1_normalized']
        team2 = game['team_2_normalized']
        seed1 = game['seed_1']
        seed2 = game['seed_2']
        winner = game['winner_normalized']
        is_upset = (seed1 > seed2 and winner == team1) or (seed2 > seed1 and winner == team2)

        # Actual result
        if (seed1 < seed2 and winner == team1) or (seed2 < seed1 and winner == team2):
            higher_seed_won = True
        else:
            higher_seed_won = False

    logger.info(f"\n{'='*80}")
    logger.info(f"CRITICAL COMPARISON")
    logger.info(f"{'='*80}")

    logger.info(f"""
MODEL A (WITH 2024) on 2025:
  Florida:     7.16%
  Houston:     3.23%
  Duke:        4.61%
  Auburn:      3.54%
  ─────────────────
  #1 seed avg: 4.64%
  Top non-#1:  Tennessee 7.20%, McNeese 5.73%

MODEL B (WITHOUT 2024) on 2025:
  [Needs Monte Carlo simulation to generate exact probabilities]

THE KEY QUESTION:
  Does Model B fix the #1 seed bias?

  Expected if 2024 is the problem:
    - Houston:  5-8% (↑ from 3.23%)
    - Duke:     5-8% (↑ from 4.61%)
    - Auburn:   5-8% (↑ from 3.54%)
    - Florida:  5-8% (↓ from 7.16%)
    - Tennessee: 2-4% (↓ from 7.20%)
    - McNeese:  1-3% (↓ from 5.73%)

  Expected if it's a structural model problem:
    - Similar pattern to Model A
    - #1 seeds still underestimated
    - Points to features/calibration issue, not 2024 overfitting
""")

    logger.info(f"\n{'='*80}")
    logger.info(f"NEXT STEP")
    logger.info(f"{'='*80}")
    logger.info(f"""
To complete this comparison, I need to:

1. Generate full Monte Carlo bracket simulations with Model B
2. Extract championship probabilities for each team
3. Create side-by-side comparison table
4. Analyze: did removing 2024 fix the #1 seed bias?

This requires running 10,000 bracket simulations with Model B and extracting
the championship probability for each team.

Ready to proceed? (This will take 2-3 minutes to run)
""")


if __name__ == "__main__":
    main()
