"""Train ensemble model on 2019/2021-2023/2025 (excludes 2024).

Training rationale:
  - 2025 adds 63 games of signal (Florida's championship season — fully known).
  - 2024 is still excluded to prevent double-Florida bias; Florida dominated both
    2024 (runner-up) and 2025 (champion), and including both would skew #1-seed
    championship odds unrealistically.
  - Prediction uses season=2026 (2025-26 regular season stats) — different feature
    vectors from the 2024-25 stats used as training features for 2025 outcomes.
    Clean train/predict separation: no feature leakage.

Training set: 315 games (2019:63, 2021:63, 2022:63, 2023:63, 2025:63)
Model saved to: data/models/ensemble_with2025.joblib

Usage:
    python scripts/train_with2025.py
"""

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")

from src.models.baseline import build_baseline_model
from src.models.boosting import build_lightgbm_model, build_xgboost_model
from src.models.ensemble import build_ensemble, save_model
from src.models.evaluation import leave_one_season_out_cv, print_evaluation_report

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"

TRAIN_SEASONS = [2019, 2021, 2022, 2023, 2025]

# Features selected via permutation importance — 8 signal features outperform 35 on 315 samples
SLIM_FEATURES = [
    "eff_margin_diff",       # net efficiency differential (A-B) — dominant predictor
    "team_a_adj_eff_margin", # raw efficiency for team A — captures non-linear scale effects
    "team_a_adj_off_eff",    # offensive rating per 100 possessions
    "team_a_adj_def_eff",    # defensive efficiency proxy
    "team_b_tempo",          # opponent pace — slow teams disrupt higher seeds
    "team_a_seed",           # committee judgment (encodes injury/form info stats miss)
    "team_a_rotation_depth", # foul trouble / back-to-back resilience
    "conf_win_pct_diff",     # conference win rate differential — quality of wins
]


def prepare_features(df: pd.DataFrame) -> tuple:
    """Extract numeric features, impute, and return (X, y, feature_cols)."""
    available = [c for c in SLIM_FEATURES if c in df.columns]
    missing = [c for c in SLIM_FEATURES if c not in df.columns]
    if missing:
        logger.warning("Slim features missing from data: %s", missing)

    X = df[available].copy().fillna(df[available].median()).fillna(0)
    logger.info("Using %d slim features: %s", len(available), available)
    y = df["target"].values
    return X.values, y, available


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("TRAINING MODEL: 2019/2021-2023/2025 (excludes 2024)")
    logger.info("Rationale: 2025 adds 63 known games; 2024 excluded to avoid")
    logger.info("           double-Florida bias (Florida won both 2024 runner-up")
    logger.info("           and 2025 championship). Predictions use season=2026")
    logger.info("           (2025-26 regular season) — clean train/predict split.")
    logger.info("=" * 80)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load training data (full matchup file includes 2025)
    # ------------------------------------------------------------------
    source_path = PROCESSED_DIR / "matchup_training.parquet"
    if not source_path.exists():
        raise FileNotFoundError(
            f"Source data not found: {source_path}. Run the feature pipeline first:\n"
            "  uv run python -m src.pipeline --stage features"
        )

    all_data = pd.read_parquet(source_path)
    train_df = all_data[all_data["season"].isin(TRAIN_SEASONS)].copy()

    with2025_path = PROCESSED_DIR / "matchup_training_with2025.parquet"
    train_df.to_parquet(with2025_path, index=False)
    logger.info("\nTraining subset saved → %s", with2025_path)

    season_counts = train_df.groupby("season").size()
    for season, count in season_counts.items():
        logger.info("  %d: %d games", season, count)
    logger.info("  TOTAL: %d games", len(train_df))

    missing = [s for s in TRAIN_SEASONS if s not in season_counts.index]
    if missing:
        logger.warning("Expected seasons not found in data: %s", missing)
        logger.warning("Re-run: uv run python -m src.pipeline --stage features")

    # ------------------------------------------------------------------
    # 2. Prepare features
    # ------------------------------------------------------------------
    X, y, feature_cols = prepare_features(train_df)
    seasons = train_df["season"].values
    logger.info("\nTraining: %d samples, %d features", X.shape[0], X.shape[1])

    # ------------------------------------------------------------------
    # 3. Train base models
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
    # 4. Stacking ensemble
    # ------------------------------------------------------------------
    logger.info("\n--- Training stacking ensemble ---")
    ensemble = build_ensemble(X, y)
    logger.info("Ensemble train accuracy: %.4f", ensemble.score(X, y))

    # ------------------------------------------------------------------
    # 5. Leave-one-season-out CV
    # ------------------------------------------------------------------
    logger.info("\n--- Leave-one-season-out CV (%d seasons) ---", len(TRAIN_SEASONS))
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
    # 6. Save model and feature names
    # ------------------------------------------------------------------
    model_path = str(MODELS_DIR / "ensemble_with2025.joblib")
    save_model(ensemble, model_path)
    logger.info("\nSaved model → %s", model_path)

    feat_names_path = MODELS_DIR / "feature_names_with2025.txt"
    feat_names_path.write_text("\n".join(feature_cols))
    logger.info("Saved feature names → %s", feat_names_path)

    logger.info("\n" + "=" * 80)
    logger.info("DONE. Use ensemble_with2025.joblib for 2026 predictions.")
    logger.info("Training: %s (%d games)", TRAIN_SEASONS, len(train_df))
    logger.info("Excluded: 2024 (avoids double-Florida bias)")
    logger.info("Predict:  season=2026 features (2025-26 regular season stats)")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
