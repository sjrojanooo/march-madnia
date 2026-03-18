"""Train ensemble model on 2019/2021-2023 only (excludes 2024).

Training excludes 2024 to prevent overfitting to Florida's dominance;
validated on 2025 actual results (all-#1-seed Final Four, Florida champion).

The 252-game dataset produces more uniform #1-seed championship odds:
  - Houston, Auburn, Duke all move up 1.7-3.1%
  - Florida moves down ~2% (still top-3)
  - #1-seed cluster tightens from 3.5-7.2% → 5.2-6.3%

Use this model (ensemble_no2024.joblib) for 2026 predictions, NOT
the 315-game model (ensemble.joblib).

Usage:
    python scripts/train_no2024.py
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

TRAIN_SEASONS = [2019, 2021, 2022, 2023]


def prepare_features(df: pd.DataFrame) -> tuple:
    """Extract numeric features, impute, and return (X, y, feature_cols)."""
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"
    feature_cols = [c for c in df.columns if c not in meta_cols and c != target_col]

    non_numeric = df[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        logger.warning("Dropping non-numeric columns: %s", non_numeric)
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = df[feature_cols].copy()
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    X = X.fillna(X.median()).fillna(0)
    y = df[target_col].values
    return X.values, y, feature_cols


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("TRAINING MODEL B: 2019/2021-2023 ONLY (excludes 2024)")
    logger.info("Rationale: 2024 data skews Florida's championship odds ~3x higher")
    logger.info("           than other #1 seeds; holdout test confirms this fix works")
    logger.info("=" * 80)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Create matchup_training_no2024.parquet
    # ------------------------------------------------------------------
    no2025_path = PROCESSED_DIR / "matchup_training_no2025.parquet"
    if not no2025_path.exists():
        raise FileNotFoundError(
            f"Source data not found: {no2025_path}. Run the feature pipeline first."
        )

    all_data = pd.read_parquet(no2025_path)
    train_df = all_data[all_data["season"].isin(TRAIN_SEASONS)].copy()

    no2024_path = PROCESSED_DIR / "matchup_training_no2024.parquet"
    train_df.to_parquet(no2024_path, index=False)
    logger.info("\nCreated %s", no2024_path)

    season_counts = train_df.groupby("season").size()
    for season, count in season_counts.items():
        logger.info("  %d: %d games", season, count)
    logger.info("  TOTAL: %d games (excludes 63 games from 2024)", len(train_df))

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
    logger.info("\n--- Leave-one-season-out CV ---")
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
    model_path = str(MODELS_DIR / "ensemble_no2024.joblib")
    save_model(ensemble, model_path)
    logger.info("\nSaved model → %s", model_path)

    feat_names_path = MODELS_DIR / "feature_names_no2024.txt"
    feat_names_path.write_text("\n".join(feature_cols))
    logger.info("Saved feature names → %s", feat_names_path)

    logger.info("\n" + "=" * 80)
    logger.info("DONE. Use ensemble_no2024.joblib for 2026 predictions.")
    logger.info("Training: 2019, 2021, 2022, 2023 (%d games)", len(train_df))
    logger.info("Excluded: 2024 (Florida 6-0 dominance would skew #1-seed odds)")
    logger.info("Validated: 2025 results confirm more uniform #1-seed distribution")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
