"""CLI wrapper for the multi-agent feature improvement system.

Usage:
    uv run python scripts/run_agents.py --max-iterations 5
    uv run python scripts/run_agents.py --max-iterations 1 --resume
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.agents.runner import run_collaboration_loop


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the multi-agent feature improvement loop.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum number of iterations (default: 10)",
    )
    parser.add_argument(
        "--target-accuracy",
        type=float,
        default=0.72,
        help="Target LOSO accuracy to stop at (default: 0.72)",
    )
    parser.add_argument(
        "--target-brier",
        type=float,
        default=0.190,
        help="Target LOSO Brier score to stop at (default: 0.190)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previously saved state instead of starting fresh.",
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

    state = run_collaboration_loop(
        max_iterations=args.max_iterations,
        target_accuracy=args.target_accuracy,
        target_brier=args.target_brier,
        resume=args.resume,
    )

    # Exit with non-zero if failed
    if state.status.value == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
