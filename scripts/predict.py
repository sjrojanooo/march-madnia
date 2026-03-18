"""Generate bracket predictions via Monte Carlo simulation.

Consolidates predict_bracket.py into a parameterized, season-agnostic script.
Bracket data is loaded from config/brackets/ instead of being hardcoded.

Usage:
    uv run python scripts/predict.py --season 2026
    uv run python scripts/predict.py --bracket config/brackets/bracket_2026.json
    uv run python scripts/predict.py --season 2026 --model ensemble_with2025 --simulations 50000
"""

from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.config import load_bracket
from src.pipeline import run_prediction_pipeline

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate bracket predictions.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--season",
        type=int,
        default=2026,
        help="Tournament season (loads config/brackets/bracket_{season}.json, default: 2026)",
    )
    group.add_argument(
        "--bracket",
        help="Path to bracket JSON file",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=10_000,
        help="Number of Monte Carlo simulations (default: 10000)",
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

    # Load bracket
    if args.bracket:
        bracket_data = load_bracket(args.bracket)
        label = args.bracket
    else:
        bracket_data = load_bracket(args.season)
        label = f"season {args.season}"

    logger.info("Generating bracket predictions for %s (%d simulations) ...", label, args.simulations)
    run_prediction_pipeline(bracket_data)
    logger.info("Bracket prediction complete. Check data/predictions/ for outputs.")


if __name__ == "__main__":
    main()
