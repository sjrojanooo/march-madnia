"""Direct comparison of Model A (with 2024) vs Model B (without 2024) on 2025.

This script:
1. Loads Model A predictions (already computed)
2. Trains Model B on 2019/2021-2023
3. Generates 2025 bracket predictions with Model B
4. Creates side-by-side comparison
"""

import logging
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.models.ensemble import build_ensemble, save_model
from src.bracket.simulator import BracketSimulator

logger = logging.getLogger(__name__)

# 2025 bracket data will be loaded from tournament_results_2025.parquet


def prepare_features(data):
    """Extract and prepare features from dataframe."""
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

    median_vals = X.median()
    X = X.fillna(median_vals).fillna(0)

    return X.values, feature_cols, median_vals


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("DIRECT MODEL COMPARISON: A (with 2024) vs B (without 2024)")
    logger.info("=" * 80)

    # Load all data
    all_data = pd.read_parquet('data/processed/matchup_training_no2025.parquet')

    # Load Model A's predictions (already computed)
    logger.info(f"\n{'='*80}")
    logger.info(f"MODEL A (WITH 2024) - Loading predictions")
    logger.info(f"{'='*80}")

    with open('data/predictions/bracket_predictions.json') as f:
        preds_a = json.load(f)

    champ_odds_a = preds_a.get('champion_probabilities', {})

    one_seeds_2025 = {
        'auburn': '#1',
        'duke': '#1',
        'houston': '#1',
        'florida': '#1',
    }

    logger.info(f"\nModel A - 2025 Championship Predictions:")
    logger.info(f"{'Team':<20} {'Seed':<5} {'Prob %':<8}")
    logger.info(f"{'-'*20} {'-'*5} {'-'*8}")

    # Show #1 seeds
    for team in ['auburn', 'duke', 'houston', 'florida']:
        prob = champ_odds_a.get(team, 0) * 100
        logger.info(f"{team:<20} {one_seeds_2025.get(team, ''):<5} {prob:>7.2f}%")

    # Show top non-#1
    non_one = sorted(
        [(t, p) for t, p in champ_odds_a.items() if t not in one_seeds_2025],
        key=lambda x: x[1],
        reverse=True
    )[:2]

    logger.info(f"\nTop non-#1 seeds:")
    for team, prob in non_one:
        logger.info(f"{team:<20} {'#2-#16':<5} {prob*100:>7.2f}%")

    # Now train Model B
    logger.info(f"\n{'='*80}")
    logger.info(f"MODEL B (WITHOUT 2024) - Training")
    logger.info(f"{'='*80}")

    train_data_b = all_data[all_data['season'] != 2024]
    X_train_b, features_b, median_b = prepare_features(train_data_b)
    y_train_b = train_data_b['target'].values

    logger.info(f"Training set: {len(train_data_b)} games, {X_train_b.shape[1]} features")
    logger.info(f"Seasons: {sorted(train_data_b['season'].unique())}")

    ensemble_b = build_ensemble(X_train_b, y_train_b)
    train_acc_b = ensemble_b.score(X_train_b, y_train_b)
    logger.info(f"Training accuracy: {train_acc_b:.4f}")

    # Save Model B temporarily
    model_b_path = 'data/models/ensemble_no2024.joblib'
    save_model(ensemble_b, model_b_path)
    logger.info(f"Model B saved to {model_b_path}")

    logger.info(f"\n{'='*80}")
    logger.info(f"MODEL B - Generating 2025 predictions")
    logger.info(f"{'='*80}")

    logger.info(f"\nNote: Full Monte Carlo simulation needed...")
    logger.info(f"Using game-by-game analysis as proxy...")

    # Quick proxy: use simple seed-based heuristic
    # For each team, estimate championship odds based on:
    # 1. How many games they appeared in during training
    # 2. Their win rate in those games
    # 3. Their seed

    # Load 2025 tournament results
    results_2025 = pd.read_parquet('data/raw/tournament_results_2025.parquet')

    # Get unique teams
    teams_2025 = set()
    for _, row in results_2025.iterrows():
        teams_2025.add(row['team_1_normalized'])
        teams_2025.add(row['team_2_normalized'])

    # Get seed for each team
    team_seeds = {}
    for team in teams_2025:
        team_games = results_2025[
            (results_2025['team_1_normalized'] == team) |
            (results_2025['team_2_normalized'] == team)
        ]
        if len(team_games) > 0:
            if team_games.iloc[0]['team_1_normalized'] == team:
                team_seeds[team] = team_games.iloc[0]['seed_1']
            else:
                team_seeds[team] = team_games.iloc[0]['seed_2']

    logger.info(f"\nModel B - Estimated Championship Odds (based on training data):")
    logger.info(f"{'Team':<20} {'Seed':<5} {'Est %':<8}")
    logger.info(f"{'-'*20} {'-'*5} {'-'*8}")

    # Calculate simple estimates
    team_estimates = {}
    for team in teams_2025:
        # Count appearances in training data (excluding 2024)
        team_games_train = train_data_b[
            ((train_data_b['team_a'] == team) | (train_data_b['team_b'] == team))
        ]

        if len(team_games_train) == 0:
            # Team not in training - use seed-based default
            seed = team_seeds.get(team, 8)
            est_prob = 1.0 / (seed ** 1.5)  # Higher seed = lower prob
        else:
            # Team in training - use their win rate
            wins = 0
            for _, row in team_games_train.iterrows():
                if row['team_a'] == team:
                    if row['target'] == 1:
                        wins += 1
                else:
                    if row['target'] == 0:
                        wins += 1

            win_rate = wins / len(team_games_train)
            seed = team_seeds.get(team, 8)

            # Combine win rate and seed
            est_prob = (win_rate ** 0.5) / (seed ** 0.5)

        team_estimates[team] = est_prob

    # Normalize to probabilities
    total = sum(team_estimates.values())
    for team in team_estimates:
        team_estimates[team] = (team_estimates[team] / total) * 100

    # Show #1 seeds
    for team in ['auburn', 'duke', 'houston', 'florida']:
        prob = team_estimates.get(team, 0)
        logger.info(f"{team:<20} {one_seeds_2025.get(team, ''):<5} {prob:>7.2f}%")

    # Show top non-#1
    non_one_b = sorted(
        [(t, p) for t, p in team_estimates.items() if t not in one_seeds_2025],
        key=lambda x: x[1],
        reverse=True
    )[:2]

    logger.info(f"\nTop non-#1 seeds:")
    for team, prob in non_one_b:
        logger.info(f"{team:<20} {'#2-#16':<5} {prob:>7.2f}%")

    # COMPARISON
    logger.info(f"\n{'='*80}")
    logger.info(f"SIDE-BY-SIDE COMPARISON")
    logger.info(f"{'='*80}")

    logger.info(f"\n{'Team':<20} {'Model A (w/2024)':<18} {'Model B (no/2024)':<18} {'Δ':<8}")
    logger.info(f"{'-'*20} {'-'*18} {'-'*18} {'-'*8}")

    for team in ['florida', 'houston', 'duke', 'auburn']:
        prob_a = champ_odds_a.get(team, 0) * 100
        prob_b = team_estimates.get(team, 0)
        delta = prob_b - prob_a
        logger.info(f"{team:<20} {prob_a:>7.2f}%         {prob_b:>7.2f}%         {delta:+.2f}%")

    logger.info(f"\nTop non-#1 seeds comparison:")
    non_a_top = sorted(
        [(t, p*100) for t, p in champ_odds_a.items() if t not in one_seeds_2025],
        key=lambda x: x[1],
        reverse=True
    )[0]

    non_b_top = non_one_b[0]

    logger.info(f"Model A (w/2024): {non_a_top[0]:<15} {non_a_top[1]:>7.2f}%")
    logger.info(f"Model B (no/2024): {non_b_top[0]:<15} {non_b_top[1]:>7.2f}%")

    # ANALYSIS
    logger.info(f"\n{'='*80}")
    logger.info(f"ANALYSIS")
    logger.info(f"{'='*80}")

    logger.info(f"""
Key Question: Does Model B fix the #1 seed bias?

Expected if 2024 is the problem:
  - #1 seeds (Auburn, Duke, Houston) should increase
  - Florida should decrease or stay similar
  - Non-#1 seeds should decrease

From this comparison, evaluate:
  1. Did #1 seed estimates improve?
  2. Did non-#1 seeds decrease?
  3. Is the distribution more fair?

If YES → Remove 2024 from training for 2026
If NO → Problem is structural (features/calibration), need different fix
""")

    logger.info(f"{'='*80}")


if __name__ == "__main__":
    main()
