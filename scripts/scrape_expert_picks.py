"""Scrape or load expert bracket picks for NCAA March Madness.

Collects expert bracket predictions from ESPN, CBS Sports, and Yahoo Sports.
Since expert articles have unpredictable HTML, the recommended path is to
provide a hand-entered JSON file via --manual-picks.

Usage:
    # Load from manual picks (recommended)
    python scripts/scrape_expert_picks.py --manual-picks data/predictions/expert_picks_manual.json

    # Attempt scraping from all sources
    python scripts/scrape_expert_picks.py

    # Scrape only ESPN and CBS
    python scripts/scrape_expert_picks.py --sources espn cbs

    # Specify season
    python scripts/scrape_expert_picks.py --season 2026
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.scraping.expert_picks import (
    EXPERT_PERSONAS,
    scrape_all_expert_picks,
)

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape or load expert bracket picks for March Madness.",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="Tournament season year (default: 2026)",
    )
    parser.add_argument(
        "--manual-picks",
        type=Path,
        default=None,
        help="Path to manual picks JSON file (recommended over scraping)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["espn", "cbs", "yahoo"],
        default=None,
        help="Sources to scrape (default: all). Ignored if --manual-picks is provided.",
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

    logger.info("=" * 60)
    logger.info("Expert Picks Scraper — Season %d", args.season)
    logger.info("=" * 60)

    if args.manual_picks:
        logger.info("Manual picks file: %s", args.manual_picks)
    else:
        sources = args.sources or ["espn", "cbs", "yahoo"]
        logger.info("Sources: %s", ", ".join(sources))

    logger.info("Known experts: %d", len(EXPERT_PERSONAS))
    for eid, persona in EXPERT_PERSONAS.items():
        logger.info("  %s — %s (%s)", eid, persona["name"], persona["source"])

    logger.info("-" * 60)

    # Run the orchestrator
    result = scrape_all_expert_picks(
        season=args.season,
        manual_picks_path=args.manual_picks,
        sources=args.sources,
    )

    # Report results
    metadata = result.get("metadata", {})
    experts = result.get("experts", {})

    logger.info("-" * 60)
    logger.info("Results:")
    logger.info("  Load method: %s", metadata.get("load_method", "unknown"))
    logger.info("  Experts loaded: %d", len(experts))

    if experts:
        for eid, data in experts.items():
            total_picks = sum(
                len(rp) for rp in data.get("picks_by_round", {}).values()
            )
            champion = data.get("champion", "N/A")
            ff = data.get("final_four", [])
            logger.info(
                "  %s (%s): %d picks, champion=%s, final_four=%s",
                data.get("expert_name", eid),
                data.get("source", "?"),
                total_picks,
                champion,
                ff,
            )
    else:
        logger.warning(
            "No expert picks loaded. Create a manual picks file at "
            "data/predictions/expert_picks_manual.json"
        )

    if metadata.get("warning"):
        logger.warning("Note: %s", metadata["warning"])

    logger.info("=" * 60)
    logger.info("Output: data/predictions/expert_picks.json")
    logger.info("Output: data/predictions/expert_picks.parquet")
    logger.info("Done.")


if __name__ == "__main__":
    main()
