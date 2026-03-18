"""Scrape player stats for all teams that have appeared in tournament brackets.

Scope: union of historical tournament teams (2019/2021-2025) + 2026 bracket teams.
This gives ~188 teams × 6 seasons = ~1,128 pages at 20 req/min (~57 min).

Saves to:
  data/raw/targeted_player_stats_{season}.parquet  (per season)
  data/raw/targeted_player_stats_all_seasons.parquet (combined)

Usage:
    python scripts/scrape_tournament_teams.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")

from src.scraping.sports_ref import (
    VALID_SEASONS,
    _filter_seasons,
    _save_parquet,
    scrape_targeted_player_stats,
    team_name_to_slug,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = PROJECT_ROOT / "data" / "raw"


def build_target_team_slugs() -> list[str]:
    """Build the union of historical tournament teams + 2026 bracket teams."""
    slugs: set[str] = set()

    # 1. Historical tournament teams from results data
    results_path = DATA_RAW / "tournament_results_all_seasons.parquet"
    if results_path.exists():
        df = pd.read_parquet(results_path)
        for col in ("team_1_normalized", "team_2_normalized"):
            if col in df.columns:
                teams = df[col].dropna().unique()
                for t in teams:
                    slugs.add(team_name_to_slug(t))
        logger.info("Historical tournament teams: %d slugs so far", len(slugs))
    else:
        logger.warning("tournament_results_all_seasons.parquet not found")

    # 2. 2026 bracket teams from predictions file
    bracket_path = PROJECT_ROOT / "data" / "predictions" / "bracket_predictions.csv"
    if bracket_path.exists():
        df_bracket = pd.read_csv(bracket_path)
        for col in ("team_a", "team_b"):
            if col in df_bracket.columns:
                for t in df_bracket[col].dropna().unique():
                    slugs.add(team_name_to_slug(t))
        logger.info("After adding 2026 bracket teams: %d slugs total", len(slugs))
    else:
        logger.warning("bracket_predictions.csv not found — only historical teams will be scraped")

    return sorted(slugs)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 70)
    logger.info("TARGETED PLAYER STATS SCRAPE")
    logger.info("Scope: historical tournament teams + 2026 bracket teams")
    logger.info("=" * 70)

    slugs = build_target_team_slugs()
    logger.info("Target: %d unique team slugs", len(slugs))

    seasons = _filter_seasons(VALID_SEASONS)
    all_dfs: list[pd.DataFrame] = []

    for season in seasons:
        # Skip seasons where we already have targeted data cached
        season_path = DATA_RAW / f"targeted_player_stats_{season}.parquet"
        if season_path.exists():
            logger.info("Season %d already scraped, loading from cache", season)
            df = pd.read_parquet(season_path)
        else:
            df = scrape_targeted_player_stats(slugs, season)

        if not df.empty:
            all_dfs.append(df)

    if not all_dfs:
        logger.error("No player data collected. Check network and Sports Reference access.")
        return

    combined = pd.concat(all_dfs, ignore_index=True)
    out_path = DATA_RAW / "targeted_player_stats_all_seasons.parquet"
    combined.to_parquet(out_path, index=False)
    logger.info("Saved %d rows → %s", len(combined), out_path)
    logger.info("Seasons covered: %s", sorted(combined["season"].unique() if "season" in combined.columns else []))

    # Also write as the "all_d1" path that the pipeline prefers
    all_d1_path = DATA_RAW / "all_d1_player_stats_all_seasons.parquet"
    combined.to_parquet(all_d1_path, index=False)
    logger.info("Also saved as %s (pipeline fallback path)", all_d1_path)

    logger.info("=" * 70)
    logger.info("DONE — rebuild features next:")
    logger.info("  uv run python -m src.pipeline --stage features")
    logger.info("  python scripts/train_no2024.py")
    logger.info("  python scripts/predict_bracket.py")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
