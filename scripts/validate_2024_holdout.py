"""Holdout validation on 2024 bracket using only 2019/2021-2023 training data.

This is Phase 0 of the diagnostic framework:
- Train on: 2019, 2021, 2022, 2023 (252 games)
- Test on: 2024 tournament bracket (63 games)
- Compare: 2024 performance vs 2025 performance

Goal: Determine if #1 seed underestimation is consistent across years (model issue)
or specific to 2025 (data quality/coverage issue).
"""

import logging
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.models.ensemble import build_ensemble, load_model

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("PHASE 0: 2024 HOLDOUT VALIDATION")
    logger.info("=" * 80)

    # Load clean training data (no 2025)
    all_data = pd.read_parquet('data/processed/matchup_training_no2025.parquet')

    # Split: train on 2019/2021-2023, holdout 2024
    train_seasons = [2019, 2021, 2022, 2023]
    train_data = all_data[all_data['season'].isin(train_seasons)]
    test_2024 = all_data[all_data['season'] == 2024]

    logger.info(f"\nTraining set composition:")
    logger.info(f"  Seasons: {train_seasons}")
    logger.info(f"  Total games: {len(train_data)}")
    for season in sorted(train_data['season'].unique()):
        count = len(train_data[train_data['season'] == season])
        logger.info(f"    {season}: {count} games")

    logger.info(f"\nHoldout test set (2024):")
    logger.info(f"  Total games: {len(test_2024)}")

    # Analyze #1 seed coverage in training data
    logger.info(f"\n#1 SEED COVERAGE (Training Data 2019/2021-2023):")
    one_seed_games = train_data[
        (train_data['team_a_seed'] == 1) | (train_data['team_b_seed'] == 1)
    ]

    one_seeds_a = one_seed_games[one_seed_games['team_a_seed'] == 1]['team_a'].unique()
    one_seeds_b = one_seed_games[one_seed_games['team_b_seed'] == 1]['team_b'].unique()
    all_training_one_seeds = set(one_seeds_a) | set(one_seeds_b)

    logger.info(f"  Unique #1 seeds: {len(all_training_one_seeds)}")
    logger.info(f"  Total #1 seed games: {len(one_seed_games)}")

    for team in sorted(all_training_one_seeds):
        count = len(one_seed_games[
            ((one_seed_games['team_a_seed'] == 1) & (one_seed_games['team_a'] == team)) |
            ((one_seed_games['team_b_seed'] == 1) & (one_seed_games['team_b'] == team))
        ])
        logger.info(f"    {team:15s}: {count:2d} games")

    # Check which #1 seeds appear in 2024 test set
    logger.info(f"\n#1 SEEDS IN 2024 TOURNAMENT:")
    one_seed_2024 = test_2024[
        (test_2024['team_a_seed'] == 1) | (test_2024['team_b_seed'] == 1)
    ]
    test_one_seeds_a = set(one_seed_2024[one_seed_2024['team_a_seed'] == 1]['team_a'].unique())
    test_one_seeds_b = set(one_seed_2024[one_seed_2024['team_b_seed'] == 1]['team_b'].unique())
    test_all_one_seeds = test_one_seeds_a | test_one_seeds_b

    logger.info(f"  Unique #1 seeds in 2024: {sorted(test_all_one_seeds)}")
    logger.info(f"  Coverage in training:")
    for team in sorted(test_all_one_seeds):
        in_training = team in all_training_one_seeds
        count = len(one_seed_games[
            ((one_seed_games['team_a_seed'] == 1) & (one_seed_games['team_a'] == team)) |
            ((one_seed_games['team_b_seed'] == 1) & (one_seed_games['team_b'] == team))
        ]) if in_training else 0
        status = f"{count} games" if count > 0 else "NOT IN TRAINING"
        logger.info(f"    {team:15s}: {status}")

    # Prepare features
    logger.info(f"\n" + "=" * 80)
    logger.info(f"PREPARING FEATURES")
    logger.info(f"=" * 80)

    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in train_data.columns
                    if c not in meta_cols and c != target_col]

    # Remove non-numeric
    non_numeric = train_data[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        logger.warning("Dropping non-numeric columns: %s", non_numeric)
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    # Prepare training set
    X_train = train_data[feature_cols].copy()
    all_nan_cols = X_train.columns[X_train.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X_train = X_train.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    X_train = X_train.fillna(X_train.median()).fillna(0)
    X_train_vals = X_train.values
    y_train = train_data[target_col].values

    # Prepare test set (2024)
    X_test = test_2024[feature_cols].copy()
    X_test = X_test.fillna(X_train.median()).fillna(0)
    X_test_vals = X_test.values
    y_test = test_2024[target_col].values

    logger.info(f"Training set: {X_train_vals.shape[0]} samples, {X_train_vals.shape[1]} features")
    logger.info(f"Test set (2024): {X_test_vals.shape[0]} samples, {X_test_vals.shape[1]} features")

    # Train model
    logger.info(f"\n" + "=" * 80)
    logger.info(f"TRAINING ENSEMBLE ON 2019/2021-2023")
    logger.info(f"=" * 80)

    ensemble = build_ensemble(X_train_vals, y_train)

    # Evaluate on training set
    train_acc = ensemble.score(X_train_vals, y_train)
    logger.info(f"Training accuracy: {train_acc:.4f}")

    # Evaluate on 2024 test set
    test_acc = ensemble.score(X_test_vals, y_test)
    logger.info(f"\n2024 Holdout accuracy: {test_acc:.4f}")

    # Get predictions with probabilities
    y_pred_proba = ensemble.predict_proba(X_test_vals)

    # Analyze #1 seed predictions on 2024
    logger.info(f"\n" + "=" * 80)
    logger.info(f"#1 SEED PREDICTIONS ON 2024 HOLDOUT")
    logger.info(f"=" * 80)

    one_seed_indices = np.where(
        (test_2024['team_a_seed'].values == 1) | (test_2024['team_b_seed'].values == 1)
    )[0]

    logger.info(f"Total #1 seed games in 2024: {len(one_seed_indices)}")

    one_seed_pred_probs = y_pred_proba[one_seed_indices, 1]  # Prob of team_a winning
    one_seed_accuracy = ensemble.score(X_test_vals[one_seed_indices], y_test[one_seed_indices])

    logger.info(f"#1 seed game accuracy: {one_seed_accuracy:.4f}")
    logger.info(f"#1 seed avg predicted prob (team_a): {one_seed_pred_probs.mean():.4f}")

    # Get predictions for championship by team
    logger.info(f"\n" + "=" * 80)
    logger.info(f"PREDICTED CHAMPIONSHIP ODDS (2024 Bracket)")
    logger.info(f"=" * 80)

    # Simple heuristic: use seed-weighted probabilities as proxy for championship
    # (Full Monte Carlo simulation would be better, but this gives quick comparison)

    team_first_round_idx = test_2024[test_2024['round'] == 'First Round'].index
    first_round_games = test_2024.loc[team_first_round_idx]

    unique_teams = set()
    for _, row in first_round_games.iterrows():
        unique_teams.add(row['team_a'])
        unique_teams.add(row['team_b'])

    logger.info(f"Unique teams in 2024 bracket: {len(unique_teams)}")

    # For each team, estimate championship odds as: avg win prob in their games * seed bonus
    team_odds = {}
    for team in sorted(unique_teams):
        team_games = test_2024[
            ((test_2024['team_a'] == team) | (test_2024['team_b'] == team))
        ]

        if len(team_games) == 0:
            continue

        # Get seed
        team_seed = None
        if len(team_games[team_games['team_a'] == team]) > 0:
            team_seed = team_games[team_games['team_a'] == team]['team_a_seed'].iloc[0]
        else:
            team_seed = team_games[team_games['team_b'] == team]['team_b_seed'].iloc[0]

        # Get average win probability
        team_game_indices = test_2024.index.isin(team_games.index)
        team_indices = np.where(team_game_indices)[0]

        avg_win_prob = 0.0
        count = 0
        for idx in team_indices:
            row = test_2024.iloc[idx]
            if row['team_a'] == team:
                avg_win_prob += y_pred_proba[idx, 1]
            else:
                avg_win_prob += 1 - y_pred_proba[idx, 1]
            count += 1

        avg_win_prob = avg_win_prob / count if count > 0 else 0.5

        # Simple seed-based bonus
        seed_bonus = 1.0 / (team_seed ** 0.5) if team_seed > 0 else 1.0

        odds = avg_win_prob * seed_bonus
        team_odds[team] = {'seed': team_seed, 'avg_win_prob': avg_win_prob, 'odds': odds}

    # Normalize odds to sum to 1
    total_odds = sum(o['odds'] for o in team_odds.values())
    for team in team_odds:
        team_odds[team]['championship_prob'] = (team_odds[team]['odds'] / total_odds) * 100

    # Sort by championship probability
    sorted_teams = sorted(team_odds.items(), key=lambda x: x[1]['championship_prob'], reverse=True)

    logger.info(f"\nTop 15 predicted championship odds:")
    for i, (team, odds) in enumerate(sorted_teams[:15], 1):
        logger.info(f"  {i:2d}. {team:20s} (#{odds['seed']}) {odds['championship_prob']:6.2f}%")

    # Load actual 2024 champion
    champ_round = test_2024[test_2024['round'] == 'Championship']
    if len(champ_round) > 0:
        # Try both 'winner' and 'winner_normalized' columns
        if 'winner' in champ_round.columns:
            actual_champion = champ_round['winner'].iloc[0]
        elif 'winner_normalized' in champ_round.columns:
            actual_champion = champ_round['winner_normalized'].iloc[0]
        else:
            actual_champion = None

        logger.info(f"\nActual 2024 Champion: {actual_champion}")
        if actual_champion and actual_champion in team_odds:
            logger.info(f"  Predicted odds: {team_odds[actual_champion]['championship_prob']:.2f}%")
            logger.info(f"  Seed: #{team_odds[actual_champion]['seed']}")
    else:
        logger.info(f"\nNo championship game found in test data")

    # Compare to 2025
    logger.info(f"\n" + "=" * 80)
    logger.info(f"COMPARISON: 2024 vs 2025 PREDICTIONS")
    logger.info(f"=" * 80)

    with open('data/predictions/bracket_predictions.json') as f:
        preds_2025 = json.load(f)

    logger.info(f"\n2025 Actual Results (from validation):")
    logger.info(f"  Champion: Florida (#1)")
    logger.info(f"  Final Four: Auburn, Duke, Florida, Houston (all #1 seeds)")

    logger.info(f"\n2025 Model Predictions:")
    if 'champion_probabilities' in preds_2025:
        champ_probs = sorted(preds_2025['champion_probabilities'].items(),
                           key=lambda x: x[1], reverse=True)
        for i, (team, prob) in enumerate(champ_probs[:8], 1):
            logger.info(f"  {i}. {team:20s}: {prob*100:6.2f}%")

    logger.info(f"\n" + "=" * 80)
    logger.info(f"PHASE 0 COMPLETE")
    logger.info(f"=" * 80)
    logger.info(f"\nKey finding:")
    logger.info(f"  - 2024 test accuracy: {test_acc:.4f}")
    logger.info(f"  - #1 seed game accuracy: {one_seed_accuracy:.4f}")
    logger.info(f"  - Did model underestimate #1 seeds in 2024? Check team odds above.")


if __name__ == "__main__":
    main()
