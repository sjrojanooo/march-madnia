"""Generate 2026 bracket predictions.

Loads the trained ensemble model and runs Monte Carlo simulations on the
2026 NCAA tournament bracket. Results are displayed via Rich tables and
exported to CSV/JSON under data/predictions/.

Usage:
    python scripts/predict_bracket.py
    python scripts/predict_bracket.py --simulations 50000
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.pipeline import run_prediction_pipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 2026 NCAA Tournament Bracket (placeholder -- update with Selection Sunday)
# ---------------------------------------------------------------------------
# Seeds are based on projected rankings heading into the 2026 tournament.
# Teams with " / " indicate play-in (First Four) matchups.

BRACKET_2026 = {
    "regions": {
        "East": {
            1: "duke",
            16: "siena",
            8: "ohio state",
            9: "tcu",
            5: "st. john's",
            12: "northern iowa",
            4: "kansas",
            13: "cal baptist",
            6: "louisville",
            11: "south florida",
            3: "michigan state",
            14: "north dakota state",
            7: "ucla",
            10: "ucf",
            2: "uconn",
            15: "furman",
        },
        "West": {
            1: "arizona",
            16: "long island",
            8: "villanova",
            9: "utah state",
            5: "wisconsin",
            12: "high point",
            4: "arkansas",
            13: "hawaii",
            6: "byu",
            11: "nc state / texas",
            3: "gonzaga",
            14: "kennesaw state",
            7: "miami",
            10: "missouri",
            2: "purdue",
            15: "queens",
        },
        "South": {
            1: "florida",
            16: "lehigh / prairie view a&m",
            8: "clemson",
            9: "iowa",
            5: "vanderbilt",
            12: "mcneese",
            4: "nebraska",
            13: "troy",
            6: "north carolina",
            11: "vcu",
            3: "illinois",
            14: "pennsylvania",
            7: "saint marys",
            10: "texas a&m",
            2: "houston",
            15: "idaho",
        },
        "Midwest": {
            1: "michigan",
            16: "howard / umbc",
            8: "georgia",
            9: "saint louis",
            5: "texas tech",
            12: "akron",
            4: "alabama",
            13: "hofstra",
            6: "tennessee",
            11: "miami (ohio) / smu",
            3: "virginia",
            14: "wright state",
            7: "kentucky",
            10: "santa clara",
            2: "iowa state",
            15: "tennessee state",
        },
    }
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 2026 bracket predictions.")
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
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Generating 2026 bracket predictions (%d simulations) ...", args.simulations)
    run_prediction_pipeline(BRACKET_2026)
    logger.info("Bracket prediction complete. Check data/predictions/ for outputs.")


if __name__ == "__main__":
    main()
