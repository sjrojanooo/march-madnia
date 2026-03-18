"""End-to-end pipeline for March Madness bracket prediction.

Pipeline stages:
    1. Scrape all data (or load from cache)
    2. Build features
    3. Validate features
    4. Train models
    5. Generate bracket predictions

Usage:
    python -m src.pipeline                    # run all stages
    python -m src.pipeline --stage scrape     # run only scraping
    python -m src.pipeline --stage features   # run only feature engineering
    python -m src.pipeline --stage validate   # run only validation
    python -m src.pipeline --stage train      # run only training
    python -m src.pipeline --stage predict    # run only prediction
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"
PREDICTIONS_DIR = PROJECT_ROOT / "data" / "predictions"

SEASONS = [2019, 2021, 2022, 2023, 2024, 2025, 2026]


# ---------------------------------------------------------------------------
# Stage 1: Scraping
# ---------------------------------------------------------------------------


def run_scraping_pipeline() -> None:
    """Run all scrapers and save raw data to data/raw/."""
    from src.scraping.sports_ref import (
        scrape_all_ap_rankings,
        scrape_all_player_stats,
        scrape_all_team_stats,
        scrape_all_tournament_results,
    )
    from src.scraping.torvik import (
        scrape_all_player_stats as scrape_torvik_players,
    )
    from src.scraping.torvik import (
        scrape_all_team_ratings,
    )
    from src.scraping.transfer_portal import scrape_all_portal_data

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=== Stage 1: Scraping ===")

    # Sports Reference scrapers
    logger.info("--- Sports Reference: Team Stats ---")
    team_stats = scrape_all_team_stats(SEASONS)
    logger.info("Team stats: %d rows", len(team_stats))

    logger.info("--- Sports Reference: Tournament Results ---")
    tourney = scrape_all_tournament_results(SEASONS)
    logger.info("Tournament results: %d rows", len(tourney))

    logger.info("--- Sports Reference: Player Stats ---")
    sr_players = scrape_all_player_stats(SEASONS)
    logger.info("SR player stats: %d rows", len(sr_players))

    logger.info("--- Sports Reference: AP Rankings ---")
    rankings = scrape_all_ap_rankings(SEASONS)
    logger.info("AP rankings: %d rows", len(rankings))

    # Torvik scrapers (Playwright-based, synchronous)
    logger.info("--- Torvik: Team Ratings ---")
    torvik_ratings = scrape_all_team_ratings(SEASONS)
    logger.info("Torvik ratings: %d rows", len(torvik_ratings))

    logger.info("--- Torvik: Player Stats ---")
    torvik_players = scrape_torvik_players(SEASONS)
    logger.info("Torvik players: %d rows", len(torvik_players))

    # Transfer portal
    logger.info("--- Transfer Portal ---")
    portal = scrape_all_portal_data(SEASONS)
    logger.info("Portal data: %d rows", len(portal))

    logger.info("=== Scraping complete ===")


# ---------------------------------------------------------------------------
# Stage 2: Feature Engineering
# ---------------------------------------------------------------------------


def run_feature_pipeline() -> pd.DataFrame:
    """Build all features from raw data and return the training matchup DataFrame.

    Loads parquet files from data/raw/, builds per-team and per-player features,
    assembles training matchups, and saves everything to data/processed/.

    Returns the training matchup DataFrame.
    """
    from src.features.matchup import build_training_matchups
    from src.features.momentum import build_momentum_features
    from src.features.player_features import build_player_features
    from src.features.portal_features import build_portal_features
    from src.features.team_features import build_team_features

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=== Stage 2: Feature Engineering ===")

    # ------------------------------------------------------------------
    # Load raw data
    # ------------------------------------------------------------------
    logger.info("Loading raw data from %s ...", RAW_DIR)

    team_stats_path = RAW_DIR / "team_stats_all_seasons.parquet"
    torvik_path = RAW_DIR / "torvik_ratings.parquet"
    ap_path = RAW_DIR / "ap_rankings_all_seasons.parquet"
    # Prefer all-D1 player stats (covers non-tournament teams like Cal Baptist,
    # Queens NC, Long Island) over the legacy tournament-only file.
    sr_players_path = RAW_DIR / "all_d1_player_stats_all_seasons.parquet"
    if not sr_players_path.exists():
        sr_players_path = RAW_DIR / "tournament_player_stats_all_seasons.parquet"
    torvik_players_path = RAW_DIR / "torvik_players.parquet"
    tourney_path = RAW_DIR / "tournament_results_all_seasons.parquet"
    portal_path = RAW_DIR / "transfer_portal.parquet"

    team_stats = pd.read_parquet(team_stats_path) if team_stats_path.exists() else pd.DataFrame()
    torvik = pd.read_parquet(torvik_path) if torvik_path.exists() else pd.DataFrame()
    ap_rankings = pd.read_parquet(ap_path) if ap_path.exists() else pd.DataFrame()
    sr_players = pd.read_parquet(sr_players_path) if sr_players_path.exists() else pd.DataFrame()
    torvik_players = (
        pd.read_parquet(torvik_players_path) if torvik_players_path.exists() else pd.DataFrame()
    )
    tournament_results = pd.read_parquet(tourney_path) if tourney_path.exists() else pd.DataFrame()
    portal_data = pd.read_parquet(portal_path) if portal_path.exists() else pd.DataFrame()

    # Prefer SR player stats (full box-score coverage, ~3k rows) over Torvik
    # (only top-50 per season, ~300 rows, missing key box-score columns).
    player_stats = sr_players if not sr_players.empty else torvik_players

    # SR data uses Sports Reference data-stat column names; remap to the
    # canonical names expected by build_player_features().
    if not player_stats.empty and "pts_per_g" in player_stats.columns:
        player_stats = player_stats.rename(
            columns={
                "team_id": "team",
                "name_display": "player",
                "pts_per_g": "pts",
                "trb_per_g": "reb",
                "ast_per_g": "ast",
                "stl_per_g": "stl",
                "blk_per_g": "blk",
                "tov_per_g": "tov",
                "mp_per_g": "mp",
            }
        )
        # Convert SR slug-format team names ("north-carolina") to display
        # names ("north carolina") to match the team features join key.
        if "team" in player_stats.columns:
            player_stats["team"] = (
                player_stats["team"].str.replace("-", " ").str.strip()
            )

    logger.info(
        "Loaded: team_stats=%d, torvik=%d, ap=%d, players=%d, tourney=%d, portal=%d",
        len(team_stats),
        len(torvik),
        len(ap_rankings),
        len(player_stats),
        len(tournament_results),
        len(portal_data),
    )

    # ------------------------------------------------------------------
    # Build features
    # ------------------------------------------------------------------
    logger.info("--- Building team features ---")
    team_features = build_team_features(team_stats, torvik, ap_rankings)
    logger.info("Team features: %d rows", len(team_features))

    # Reset index if team_features has (team, season) as index
    if team_features.index.names == ["team", "season"] or "team" not in team_features.columns:
        team_features = team_features.reset_index()

    logger.info("--- Building player features ---")
    player_features = (
        build_player_features(player_stats) if not player_stats.empty else pd.DataFrame()
    )
    logger.info("Player features: %d rows", len(player_features))

    logger.info("--- Building portal/continuity features ---")
    portal_features = build_portal_features(portal_data, player_stats)
    logger.info("Portal features: %d rows", len(portal_features))

    logger.info("--- Building momentum features ---")
    # Momentum needs team-level stats with wins/losses and adj_em
    momentum_input = team_features.copy()
    if not torvik.empty and "adj_em" in torvik.columns:
        if "adj_em" not in momentum_input.columns:
            torvik_slim = torvik[["team", "season", "adj_em"]].drop_duplicates()
            momentum_input = momentum_input.merge(
                torvik_slim,
                on=["team", "season"],
                how="left",
                suffixes=("", "_torvik"),
            )
    momentum_features = build_momentum_features(momentum_input, tournament_results)
    logger.info("Momentum features: %d rows", len(momentum_features))

    # ------------------------------------------------------------------
    # Save intermediate features
    # ------------------------------------------------------------------
    if not player_features.empty:
        player_features.to_parquet(PROCESSED_DIR / "player_features.parquet", index=False)
    portal_features.to_parquet(PROCESSED_DIR / "portal_features.parquet", index=False)
    momentum_features.to_parquet(PROCESSED_DIR / "momentum_features.parquet", index=False)

    # ------------------------------------------------------------------
    # Build training matchups
    # ------------------------------------------------------------------
    logger.info("--- Building training matchups ---")
    if tournament_results.empty:
        logger.error("No tournament results available; cannot build matchups.")
        return pd.DataFrame()

    matchups = build_training_matchups(
        team_features=team_features,
        player_features=player_features,
        portal_features=portal_features,
        momentum_features=momentum_features,
        tournament_results=tournament_results,
    )
    logger.info("Training matchups: %d rows, %d columns", len(matchups), len(matchups.columns))

    logger.info("=== Feature engineering complete ===")
    return matchups


# ---------------------------------------------------------------------------
# Stage 3: Validation
# ---------------------------------------------------------------------------


def run_validation(matchups: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Validate features before training.

    If matchups is None, loads from data/processed/matchup_training.parquet.

    Returns (cleaned_matchups, validation_report).
    """
    from src.features.validation import (
        auto_clean,
        print_validation_report,
        save_validation_report,
        validate_features,
    )

    logger.info("=== Stage 3: Validation ===")

    if matchups is None:
        matchups_path = PROCESSED_DIR / "matchup_training.parquet"
        if not matchups_path.exists():
            raise FileNotFoundError(
                f"No matchup data found at {matchups_path}. Run the feature pipeline first."
            )
        matchups = pd.read_parquet(matchups_path)
        logger.info("Loaded matchups from %s (%d rows)", matchups_path, len(matchups))

    # Run validation
    report = validate_features(matchups, target_col="target")

    # Print and save report
    try:
        print_validation_report(report)
    except ImportError:
        logger.info("Rich not available; printing summary instead.")
        logger.info("Validation status: %s (%d issues)", report["status"], report["total_issues"])

    save_validation_report(report, str(PROCESSED_DIR / "validation_report.json"))

    # Auto-clean (drop zero-variance, high-null, leakage features)
    cleaned = auto_clean(matchups, report)
    logger.info("Post-cleaning shape: %s", cleaned.shape)

    logger.info("=== Validation complete (status: %s) ===", report["status"])
    return cleaned, report


# ---------------------------------------------------------------------------
# Stage 4: Training
# ---------------------------------------------------------------------------


def run_training_pipeline(matchups: pd.DataFrame | None = None) -> object:
    """Train all models and evaluate. Returns the best ensemble model.

    If matchups is None, loads from data/processed/matchup_training.parquet.
    """
    from src.models.baseline import build_baseline_model
    from src.models.boosting import build_lightgbm_model, build_xgboost_model
    from src.models.ensemble import build_ensemble, save_model
    from src.models.evaluation import (
        evaluate_model,
        leave_one_season_out_cv,
        plot_calibration,
        plot_feature_importance,
        print_evaluation_report,
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=== Stage 4: Training ===")

    if matchups is None:
        matchups_path = PROCESSED_DIR / "matchup_training.parquet"
        if not matchups_path.exists():
            raise FileNotFoundError(
                f"No matchup data found at {matchups_path}. Run the feature pipeline first."
            )
        matchups = pd.read_parquet(matchups_path)
        logger.info("Loaded matchups from %s (%d rows)", matchups_path, len(matchups))

    # Separate features, target, and metadata
    meta_cols = ["season", "round", "team_a", "team_b"]
    target_col = "target"

    feature_cols = [c for c in matchups.columns if c not in meta_cols and c != target_col]
    non_numeric = matchups[feature_cols].select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        logger.warning("Dropping non-numeric feature columns: %s", non_numeric)
        feature_cols = [c for c in feature_cols if c not in non_numeric]

    X = matchups[feature_cols].copy()

    # Drop columns that are entirely NaN or non-numeric leftovers
    all_nan_cols = X.columns[X.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        X = X.drop(columns=all_nan_cols)
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]

    # Impute remaining missing values with column medians, then 0 for any residual
    n_missing = X.isna().sum().sum()
    if n_missing > 0:
        logger.info("Imputing %d missing values with column medians", n_missing)
        X = X.fillna(X.median()).fillna(0)

    X = X.values
    y = matchups[target_col].values
    seasons = matchups["season"].values if "season" in matchups.columns else None

    logger.info("Training with %d samples, %d features", X.shape[0], X.shape[1])

    # ------------------------------------------------------------------
    # 1. Baseline model
    # ------------------------------------------------------------------
    logger.info("--- Training baseline (Logistic Regression) ---")
    baseline = build_baseline_model(X, y)
    baseline_results = evaluate_model(baseline, X, y)
    logger.info("Baseline train metrics: %s", baseline_results)

    # ------------------------------------------------------------------
    # 2. XGBoost
    # ------------------------------------------------------------------
    logger.info("--- Training XGBoost ---")
    xgb_model = build_xgboost_model(X, y)
    xgb_results = evaluate_model(xgb_model, X, y)
    logger.info("XGBoost train metrics: %s", xgb_results)

    # ------------------------------------------------------------------
    # 3. LightGBM
    # ------------------------------------------------------------------
    logger.info("--- Training LightGBM ---")
    lgbm_model = build_lightgbm_model(X, y)
    lgbm_results = evaluate_model(lgbm_model, X, y)
    logger.info("LightGBM train metrics: %s", lgbm_results)

    # ------------------------------------------------------------------
    # 4. Stacking ensemble
    # ------------------------------------------------------------------
    logger.info("--- Training stacking ensemble ---")
    ensemble = build_ensemble(X, y)
    ensemble_results = evaluate_model(ensemble, X, y)
    logger.info("Ensemble train metrics: %s", ensemble_results)

    # ------------------------------------------------------------------
    # 5. Leave-one-season-out cross-validation
    # ------------------------------------------------------------------
    if seasons is not None:
        logger.info("--- Leave-one-season-out CV (ensemble) ---")
        loso_results = leave_one_season_out_cv(
            model_builder=build_ensemble,
            X=X,
            y=y,
            seasons=seasons,
        )
        try:
            print_evaluation_report(loso_results)
        except ImportError:
            logger.info("LOSO CV mean: %s", loso_results["mean"])

    # ------------------------------------------------------------------
    # 6. Save the ensemble model and generate plots
    # ------------------------------------------------------------------
    model_path = str(MODELS_DIR / "ensemble.joblib")
    save_model(ensemble, model_path)
    logger.info("Ensemble model saved to %s", model_path)

    # Save feature names for prediction
    feature_names_path = MODELS_DIR / "feature_names.txt"
    feature_names_path.write_text("\n".join(feature_cols))
    logger.info("Feature names saved to %s", feature_names_path)

    # Calibration plot
    try:
        plot_calibration(
            ensemble,
            X,
            y,
            save_path=str(PREDICTIONS_DIR / "calibration_plot.png"),
        )
    except Exception as exc:
        logger.warning("Could not generate calibration plot: %s", exc)

    # Feature importance plot
    try:
        plot_feature_importance(
            ensemble,
            feature_cols,
            save_path=str(PREDICTIONS_DIR / "feature_importance.png"),
        )
    except Exception as exc:
        logger.warning("Could not generate feature importance plot: %s", exc)

    logger.info("=== Training complete ===")
    return ensemble


# ---------------------------------------------------------------------------
# Stage 5: Prediction
# ---------------------------------------------------------------------------


def run_prediction_pipeline(bracket_data: dict) -> None:
    """Generate 2026 bracket predictions using a trained model.

    Parameters
    ----------
    bracket_data : dict
        Bracket structure with ``"regions"`` key mapping region names to
        ``{seed: team_name}`` dicts.
    """
    from src.bracket.simulator import BracketSimulator
    from src.bracket.visualizer import (
        export_csv,
        export_json,
        print_bracket,
        print_championship_odds,
        print_upset_alerts,
    )
    from src.models.ensemble import load_model

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=== Stage 5: Prediction ===")

    # ------------------------------------------------------------------
    # 1. Load the trained model
    # ------------------------------------------------------------------
    # Model preference order:
    #   1. ensemble_with2025.joblib — trained on 2019/2021-2023/2025 (315 games),
    #      predicts with season=2026 features (no feature leakage).
    #   2. ensemble_no2024.joblib  — trained on 2019/2021-2023 only (252 games).
    #   3. ensemble.joblib         — legacy fallback.
    with2025_path = MODELS_DIR / "ensemble_with2025.joblib"
    no2024_path = MODELS_DIR / "ensemble_no2024.joblib"
    default_path = MODELS_DIR / "ensemble.joblib"
    if with2025_path.exists():
        model_path = str(with2025_path)
    elif no2024_path.exists():
        model_path = str(no2024_path)
    else:
        model_path = str(default_path)
    logger.info("Loading model from %s", model_path)
    model = load_model(model_path)

    # ------------------------------------------------------------------
    # 2. Load team features for the current season
    # ------------------------------------------------------------------
    team_features_path = PROCESSED_DIR / "team_features.parquet"
    player_features_path = PROCESSED_DIR / "player_features.parquet"
    portal_features_path = PROCESSED_DIR / "portal_features.parquet"
    momentum_features_path = PROCESSED_DIR / "momentum_features.parquet"

    team_features_df = (
        pd.read_parquet(team_features_path) if team_features_path.exists() else pd.DataFrame()
    )
    player_features_df = (
        pd.read_parquet(player_features_path) if player_features_path.exists() else pd.DataFrame()
    )
    portal_features_df = (
        pd.read_parquet(portal_features_path) if portal_features_path.exists() else pd.DataFrame()
    )
    momentum_features_df = (
        pd.read_parquet(momentum_features_path)
        if momentum_features_path.exists()
        else pd.DataFrame()
    )

    # Reset multi-index if needed
    for df_name in (
        "team_features_df",
        "player_features_df",
        "portal_features_df",
        "momentum_features_df",
    ):
        df = locals()[df_name]
        if "team" not in df.columns and df.index.names and "team" in df.index.names:
            locals()[df_name] = df.reset_index()

    # Use the latest season available for prediction features
    latest_season = max(SEASONS)
    logger.info("Using season %d features for predictions", latest_season)

    # ------------------------------------------------------------------
    # 3. Build per-team feature dicts for the simulator
    # ------------------------------------------------------------------
    # Merge all feature sources for the latest season
    all_features = team_features_df.copy()
    if "team" not in all_features.columns and all_features.index.names:
        all_features = all_features.reset_index()

    for df, _name in [
        (player_features_df, "player"),
        (portal_features_df, "portal"),
        (momentum_features_df, "momentum"),
    ]:
        if df.empty or "team" not in df.columns:
            continue
        overlap = set(all_features.columns) & set(df.columns) - {"team", "season"}
        df_clean = df.drop(columns=list(overlap), errors="ignore")
        all_features = all_features.merge(df_clean, on=["team", "season"], how="left")

    # Filter to latest season
    if "season" in all_features.columns:
        current = all_features[all_features["season"] == latest_season].copy()
    else:
        current = all_features.copy()

    logger.info("Current season features: %d teams", len(current))

    # Convert to dict keyed by team name
    team_features_dict: dict[str, dict] = {}
    for _, row in current.iterrows():
        team_name = row.get("team", "")
        if not team_name:
            continue
        feat = row.drop(labels=["team", "season"], errors="ignore").to_dict()
        # Convert any non-numeric values to 0
        for k, v in feat.items():
            try:
                feat[k] = float(v)
            except (TypeError, ValueError):
                feat[k] = 0.0
        team_features_dict[team_name] = feat

    # ------------------------------------------------------------------
    # 4. Inject seed information from the bracket
    # ------------------------------------------------------------------
    # Feature dict keys are lowercased; bracket uses display names.
    # Build a lookup: lowercase name → feature dict entry.
    # Also remap bracket team names to the lowercased versions.
    bracket_for_sim = {"regions": {}}
    for region_name, seeds_teams in bracket_data["regions"].items():
        region_mapped: dict[str, str] = {}
        for seed, team_name in seeds_teams.items():
            primary_name = team_name.split("/")[0].strip()
            lookup_name = primary_name.lower()

            if lookup_name not in team_features_dict:
                # Try common substitutions using the same map as matchup builder
                from src.features.matchup import TOURNEY_NAME_MAP
                alias_map = {
                    **TOURNEY_NAME_MAP,
                    "cal baptist": "california baptist",
                    "long island": "long island university",
                    "miami": "miami fl",
                    "queens": "queens nc",
                    "tcu": "texas christian",
                    "nc state": "north carolina state",
                    "nc state / texas": "north carolina state",
                    "miami (ohio) / smu": "miami oh",
                    "howard / umbc": "howard",
                    "lehigh / prairie view a&m": "lehigh",
                }
                canonical = alias_map.get(lookup_name)
                if canonical and canonical in team_features_dict:
                    lookup_name = canonical

            if lookup_name not in team_features_dict:
                logger.warning(
                    "Team '%s' (lookup='%s') not found in features; using defaults",
                    primary_name,
                    lookup_name,
                )
                team_features_dict[lookup_name] = {}

            team_features_dict[lookup_name]["seed"] = float(seed)
            region_mapped[str(seed)] = lookup_name

        bracket_for_sim["regions"][region_name] = region_mapped

    n_with_features = sum(
        1 for v in team_features_dict.values() if len(v) > 2
    )
    logger.info(
        "Bracket teams with real features: %d / %d",
        n_with_features,
        sum(len(r) for r in bracket_for_sim["regions"].values()),
    )

    # ------------------------------------------------------------------
    # 6. Load trained feature names for column alignment
    # ------------------------------------------------------------------
    with2025_feat_path = MODELS_DIR / "feature_names_with2025.txt"
    no2024_feat_path = MODELS_DIR / "feature_names_no2024.txt"
    if with2025_feat_path.exists():
        feature_names_path = with2025_feat_path
    elif no2024_feat_path.exists():
        feature_names_path = no2024_feat_path
    else:
        feature_names_path = MODELS_DIR / "feature_names.txt"
    feature_names = None
    if feature_names_path.exists():
        feature_names = feature_names_path.read_text().strip().split("\n")
        logger.info("Loaded %d trained feature names from %s", len(feature_names), feature_names_path.name)

    # ------------------------------------------------------------------
    # 7. Run Monte Carlo simulation
    # ------------------------------------------------------------------
    logger.info("Running bracket simulation ...")
    simulator = BracketSimulator(
        model=model,
        team_features=team_features_dict,
        n_simulations=10_000,
        seed=42,
        feature_names=feature_names,
    )
    results = simulator.simulate(bracket_for_sim)

    # ------------------------------------------------------------------
    # 7. Display and export results
    # ------------------------------------------------------------------
    print_bracket(results)
    print_championship_odds(results, top_n=16)
    print_upset_alerts(results)

    export_csv(results, str(PREDICTIONS_DIR / "bracket_predictions.csv"))
    export_json(results, str(PREDICTIONS_DIR / "bracket_predictions.json"))

    logger.info("=== Prediction complete ===")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the complete pipeline or individual stages."""
    parser = argparse.ArgumentParser(
        description="March Madness bracket prediction pipeline",
    )
    parser.add_argument(
        "--stage",
        choices=["scrape", "features", "validate", "train", "predict", "agents", "all"],
        default="all",
        help="Which pipeline stage to run (default: all)",
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

    stage = args.stage

    if stage in ("scrape", "all"):
        run_scraping_pipeline()

    matchups = None
    if stage in ("features", "all"):
        matchups = run_feature_pipeline()

    if stage in ("validate", "all"):
        matchups, report = run_validation(matchups)

    if stage in ("train", "all"):
        run_training_pipeline(matchups)

    if stage == "agents":
        from src.agents.runner import run_collaboration_loop

        run_collaboration_loop()
        return

    if stage in ("predict", "all"):
        # For the "predict" stage run standalone, use a default bracket
        # In practice, scripts/predict_bracket.py passes the real bracket
        logger.info("Predict stage requires bracket data. Use scripts/predict_bracket.py.")
        if stage == "all":
            logger.info(
                "Skipping predict in 'all' mode -- run scripts/predict_bracket.py "
                "with the final bracket."
            )


if __name__ == "__main__":
    main()
