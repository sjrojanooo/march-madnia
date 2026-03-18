"""Scrape team/player stats and AP rankings for a specific season.

Consolidates scrape_2026_season.py into a parameterized, season-agnostic script.
Bracket team slugs can optionally be loaded from config/brackets/ to target
player stat scraping.

Usage:
    uv run python scripts/scrape_season.py --season 2026
    uv run python scripts/scrape_season.py --season 2025 --bracket config/brackets/bracket_2025.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")

from src.config import PROJECT_ROOT, load_bracket
from src.scraping.sports_ref import (
    _filter_seasons,
    scrape_all_ap_rankings,
    scrape_all_team_stats,
    scrape_targeted_player_stats,
    team_name_to_slug,
)

logger = logging.getLogger(__name__)

DATA_RAW = PROJECT_ROOT / "data" / "raw"


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


def build_target_slugs(season: int, bracket_data: dict | None = None) -> list[str]:
    """Build union of historical tournament teams + bracket teams."""
    slugs: set[str] = set()

    # Add bracket teams if provided
    if bracket_data and "regions" in bracket_data:
        for region_seeds in bracket_data["regions"].values():
            for team_name in region_seeds.values():
                for part in str(team_name).split("/"):
                    slugs.add(team_name_to_slug(part.strip()))

    # Add historical tournament teams
    results_path = DATA_RAW / "tournament_results_all_seasons.parquet"
    if results_path.exists():
        df = pd.read_parquet(results_path)
        for col in ("team_1_normalized", "team_2_normalized"):
            if col in df.columns:
                for t in df[col].dropna().unique():
                    slugs.add(team_name_to_slug(t))
        logger.info("Including %d unique team slugs (historical + bracket)", len(slugs))
    elif not slugs:
        logger.warning("No tournament results or bracket data — scraping all D1 teams")

    return sorted(slugs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape season stats.")
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season to scrape (e.g. 2026 = 2025-26 academic year)",
    )
    parser.add_argument(
        "--bracket",
        help="Path to bracket JSON for targeted player stat scraping",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    season = args.season
    bracket_data = load_bracket(args.bracket) if args.bracket else None

    logger.info("=" * 70)
    logger.info("SCRAPING SEASON %d (%d-%d regular season stats)", season, season - 1, season)
    logger.info("=" * 70)

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    seasons = _filter_seasons([season])

    # ------------------------------------------------------------------
    # 1. Team stats (basic + advanced + opponent)
    # ------------------------------------------------------------------
    logger.info("\n--- Team stats ---")
    team_stats = scrape_all_team_stats(seasons)
    if not team_stats.empty:
        season_path = DATA_RAW / f"team_stats_{season}.parquet"
        team_stats.to_parquet(season_path, index=False)
        logger.info("Saved %d rows -> %s", len(team_stats), season_path.name)
        _append_or_replace_season(
            DATA_RAW / "team_stats_all_seasons.parquet", team_stats, season
        )
    else:
        logger.warning("No team stats returned for season %d", season)

    # ------------------------------------------------------------------
    # 2. AP Rankings
    # ------------------------------------------------------------------
    logger.info("\n--- AP Rankings ---")
    ap_rankings = scrape_all_ap_rankings(seasons)
    if not ap_rankings.empty:
        season_path = DATA_RAW / f"ap_rankings_{season}.parquet"
        ap_rankings.to_parquet(season_path, index=False)
        logger.info("Saved %d rows -> %s", len(ap_rankings), season_path.name)
        _append_or_replace_season(
            DATA_RAW / "ap_rankings_all_seasons.parquet", ap_rankings, season
        )
    else:
        logger.warning("No AP rankings returned for season %d", season)

    # ------------------------------------------------------------------
    # 3. Player stats (targeted)
    # ------------------------------------------------------------------
    logger.info("\n--- Player stats (targeted) ---")
    slugs = build_target_slugs(season, bracket_data)
    if slugs:
        logger.info("Scraping %d team slugs for season %d", len(slugs), season)
        player_stats = scrape_targeted_player_stats(slugs, season)
        if not player_stats.empty:
            season_path = DATA_RAW / f"targeted_player_stats_{season}.parquet"
            player_stats.to_parquet(season_path, index=False)
            logger.info("Saved %d rows -> %s", len(player_stats), season_path.name)

            for combined_name in (
                "targeted_player_stats_all_seasons.parquet",
                "all_d1_player_stats_all_seasons.parquet",
            ):
                combined_path = DATA_RAW / combined_name
                if combined_path.exists():
                    _append_or_replace_season(combined_path, player_stats, season)
        else:
            logger.warning("No player stats returned for season %d", season)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("\n" + "=" * 70)
    logger.info("DONE. Season %d data saved to data/raw/", season)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. uv run python -m src.pipeline --stage features")
    logger.info("  2. uv run python scripts/train.py")
    logger.info("  3. uv run python scripts/predict.py --season %d", season)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
