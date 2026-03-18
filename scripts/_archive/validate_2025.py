"""Validate model accuracy on 2025 NCAA tournament."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.pipeline import run_prediction_pipeline

logger = logging.getLogger(__name__)

# 2025 NCAA Tournament Bracket (from tournament results)
BRACKET_2025 = {
    "regions": {
        "East": {
            1: "duke",
            2: "alabama",
            3: "wisconsin",
            4: "arizona",
            5: "oregon",
            6: "byu",
            7: "saint marys",
            8: "mississippi state",
            9: "baylor",
            10: "vanderbilt",
            11: "vcu",
            12: "liberty",
            13: "akron",
            14: "montana",
            15: "robert morris",
            16: "mount st marys",
        },
        "West": {
            1: "florida",
            2: "st johns ny",
            3: "texas tech",
            4: "maryland",
            5: "memphis",
            6: "missouri",
            7: "kansas",
            8: "uconn",
            9: "oklahoma",
            10: "arkansas",
            11: "drake",
            12: "colorado state",
            13: "grand canyon",
            14: "unc wilmington",
            15: "omaha",
            16: "norfolk state",
        },
        "South": {
            1: "auburn",
            2: "michigan state",
            3: "iowa state",
            4: "texas a&m",
            5: "michigan",
            6: "ole miss",
            7: "marquette",
            8: "louisville",
            9: "creighton",
            10: "new mexico",
            11: "unc",
            12: "uc san diego",
            13: "yale",
            14: "lipscomb",
            15: "bryant",
            16: "alabama state",
        },
        "Midwest": {
            1: "houston",
            2: "tennessee",
            3: "kentucky",
            4: "purdue",
            5: "clemson",
            6: "illinois",
            7: "ucla",
            8: "gonzaga",
            9: "georgia",
            10: "utah state",
            11: "xavier",
            12: "mcneese",
            13: "high point",
            14: "troy",
            15: "wofford",
            16: "siu-edwardsville",
        },
    }
}

# 2025 Actual Results
ACTUAL_2025 = {
    "champion": "florida",
    "runner_up": "houston",
    "final_four": [
        {"team": "florida", "seed": 1},
        {"team": "houston", "seed": 1},
        {"team": "auburn", "seed": 1},
        {"team": "duke", "seed": 1},
    ],
    "semifinals": [
        {"winner": "florida", "loser": "auburn"},
        {"winner": "houston", "loser": "duke"},
    ]
}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 80)
    logger.info("VALIDATING 2025 BRACKET PREDICTIONS")
    logger.info("=" * 80)

    logger.info("\n2025 ACTUAL RESULTS:")
    logger.info(f"  Champion: {ACTUAL_2025['champion']}")
    logger.info(f"  Runner-up: {ACTUAL_2025['runner_up']}")
    logger.info("  Final Four (all #1 seeds):")
    for team_info in ACTUAL_2025['final_four']:
        logger.info(f"    - {team_info['team']} (#{team_info['seed']})")

    logger.info("\n" + "=" * 80)
    logger.info("Running model on 2025 bracket...")
    logger.info("=" * 80 + "\n")

    run_prediction_pipeline(BRACKET_2025)

    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION COMPLETE")
    logger.info("Check data/predictions/ for detailed outputs and comparison")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
