"""Targeted scrape for 2025-26 regular season stats (season=2026).

Scrapes team stats (basic/advanced/opponent), AP rankings, and player stats
for the 2025-26 regular season. This populates the raw data files needed
so the feature pipeline can build season=2026 rows, which the prediction
layer will use as fresh features (no overlap with training targets).

Saves/appends to existing season-combined parquet files in data/raw/.

Usage:
    python scripts/scrape_2026_season.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")

from src.scraping.sports_ref import (
    _filter_seasons,
    _save_parquet,
    scrape_all_ap_rankings,
    scrape_all_team_stats,
    scrape_targeted_player_stats,
    team_name_to_slug,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = PROJECT_ROOT / "data" / "raw"

SEASON = 2026

# 2026 bracket teams (from predict_bracket.py BRACKET_2026)
BRACKET_2026_TEAMS = [
    "duke", "siena", "ohio-state", "tcu", "st-johns", "northern-iowa",
    "kansas", "cal-baptist", "louisville", "south-florida", "michigan-state",
    "north-dakota-state", "ucla", "ucf", "connecticut", "furman",
    "arizona", "long-island-university", "villanova", "utah-state", "wisconsin",
    "high-point", "arkansas", "hawaii", "brigham-young", "nc-state", "texas",
    "gonzaga", "kennesaw-state", "miami-fl", "missouri", "purdue", "queens-nc",
    "florida", "lehigh", "prairie-view", "clemson", "iowa", "vanderbilt",
    "mcneese-state", "nebraska", "troy", "north-carolina", "virginia-commonwealth",
    "illinois", "pennsylvania", "saint-marys-ca", "texas-am", "houston", "idaho",
    "michigan", "howard", "umbc", "georgia", "saint-louis", "texas-tech",
    "akron", "alabama", "hofstra", "tennessee", "miami-oh", "southern-methodist",
    "virginia", "wright-state", "kentucky", "santa-clara", "iowa-state",
    "tennessee-state",
]


def build_target_slugs() -> list[str]:
    """Build union of historical tournament teams + 2026 bracket teams."""
    slugs: set[str] = set(BRACKET_2026_TEAMS)

    results_path = DATA_RAW / "tournament_results_all_seasons.parquet"
    if results_path.exists():
        df = pd.read_parquet(results_path)
        for col in ("team_1_normalized", "team_2_normalized"):
            if col in df.columns:
                for t in df[col].dropna().unique():
                    slugs.add(team_name_to_slug(t))
        logger.info("Including %d unique team slugs (historical + 2026 bracket)", len(slugs))
    else:
        logger.warning("tournament_results_all_seasons.parquet not found — using bracket teams only")

    return sorted(slugs)


def _append_or_replace_season(combined_path: Path, new_df: pd.DataFrame, season: int) -> None:
    """Append new_df to combined_path, replacing any existing rows for season."""
    if combined_path.exists():
        existing = pd.read_parquet(combined_path)
        if "season" in existing.columns:
            existing = existing[existing["season"] != season]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_parquet(combined_path, index=False)
    logger.info("Updated %s (%d total rows)", combined_path.name, len(combined))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 70)
    logger.info("SCRAPING SEASON %d (2025-26 regular season stats)", SEASON)
    logger.info("=" * 70)

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    seasons = _filter_seasons([SEASON])

    # ------------------------------------------------------------------
    # 1. Team stats (basic + advanced + opponent)
    # ------------------------------------------------------------------
    logger.info("\n--- Team stats ---")
    team_stats = scrape_all_team_stats(seasons)
    if not team_stats.empty:
        season_path = DATA_RAW / f"team_stats_{SEASON}.parquet"
        team_stats.to_parquet(season_path, index=False)
        logger.info("Saved %d rows → %s", len(team_stats), season_path.name)
        _append_or_replace_season(
            DATA_RAW / "team_stats_all_seasons.parquet", team_stats, SEASON
        )
    else:
        logger.warning("No team stats returned for season %d", SEASON)

    # ------------------------------------------------------------------
    # 2. AP Rankings
    # ------------------------------------------------------------------
    logger.info("\n--- AP Rankings ---")
    ap_rankings = scrape_all_ap_rankings(seasons)
    if not ap_rankings.empty:
        season_path = DATA_RAW / f"ap_rankings_{SEASON}.parquet"
        ap_rankings.to_parquet(season_path, index=False)
        logger.info("Saved %d rows → %s", len(ap_rankings), season_path.name)
        _append_or_replace_season(
            DATA_RAW / "ap_rankings_all_seasons.parquet", ap_rankings, SEASON
        )
    else:
        logger.warning("No AP rankings returned for season %d", SEASON)

    # ------------------------------------------------------------------
    # 3. Player stats (targeted: bracket + historical tournament teams)
    # ------------------------------------------------------------------
    logger.info("\n--- Player stats (targeted) ---")
    slugs = build_target_slugs()
    logger.info("Scraping %d team slugs for season %d", len(slugs), SEASON)

    player_stats = scrape_targeted_player_stats(slugs, SEASON)
    if not player_stats.empty:
        season_path = DATA_RAW / f"targeted_player_stats_{SEASON}.parquet"
        player_stats.to_parquet(season_path, index=False)
        logger.info("Saved %d rows → %s", len(player_stats), season_path.name)

        for combined_name in (
            "targeted_player_stats_all_seasons.parquet",
            "all_d1_player_stats_all_seasons.parquet",
        ):
            combined_path = DATA_RAW / combined_name
            if combined_path.exists():
                _append_or_replace_season(combined_path, player_stats, SEASON)
            else:
                logger.info(
                    "%s not found — skipping append (run scrape_tournament_teams.py first)",
                    combined_name,
                )
    else:
        logger.warning("No player stats returned for season %d", SEASON)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("\n" + "=" * 70)
    logger.info("DONE. Season %d data saved to data/raw/", SEASON)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. uv run python -m src.pipeline --stage features")
    logger.info("     → team_features.parquet will include season=2026 rows")
    logger.info("  2. python scripts/train_with2025.py")
    logger.info("     → trains on 2019, 2021-2023, 2025 (315 games)")
    logger.info("  3. python scripts/predict_bracket.py")
    logger.info("     → uses ensemble_with2025.joblib + season=2026 features (no leakage)")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
