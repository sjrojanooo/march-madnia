"""Train models with a validation gate.

Runs the feature engineering pipeline, validates the resulting feature matrix,
and trains the stacking ensemble model if validation passes. The trained model
is saved to data/models/ensemble.joblib.

Usage:
    python scripts/train.py
    python scripts/train.py --skip-validation   # bypass the validation gate
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.pipeline import run_feature_pipeline, run_training_pipeline, run_validation

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build features, validate, and train models.")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip the validation gate and train regardless of data quality.",
    )
    parser.add_argument(
        "--skip-features",
        action="store_true",
        help="Skip feature building and load existing matchup data from disk.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Step 1: Build features
    matchups = None
    if not args.skip_features:
        logger.info("Step 1/3: Building features ...")
        matchups = run_feature_pipeline()
        if matchups.empty:
            logger.error("Feature pipeline produced no matchups. Aborting.")
            sys.exit(1)
        logger.info("Features built: %d matchup rows", len(matchups))
    else:
        logger.info("Step 1/3: Skipping feature build (--skip-features)")

    # Step 2: Validate
    if not args.skip_validation:
        logger.info("Step 2/3: Validating features ...")
        matchups, report = run_validation(matchups)

        # Hard-fail if target leakage is detected
        if report.get("target_leakage"):
            logger.error(
                "TARGET LEAKAGE DETECTED: %s. Fix before training.",
                report["target_leakage"],
            )
            sys.exit(1)

        # Warn but continue on other issues
        if report.get("total_issues", 0) > 0:
            logger.warning(
                "Validation found %d issues (status: %s). Proceeding with training.",
                report["total_issues"],
                report["status"],
            )
    else:
        logger.info("Step 2/3: Skipping validation (--skip-validation)")

    # Step 3: Train
    logger.info("Step 3/3: Training models ...")
    run_training_pipeline(matchups)
    logger.info("Training complete. Model ready for predictions.")


if __name__ == "__main__":
    main()
