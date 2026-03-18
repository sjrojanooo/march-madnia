"""Run the full scraping pipeline.

Collects data from Sports Reference, Bart Torvik, and transfer portal
sources for all valid seasons (2019, 2021-2025). Raw data is saved as
parquet files under data/raw/.

Usage:
    python scripts/scrape_all.py
"""

import asyncio
import logging
import sys

sys.path.insert(0, ".")

from src.pipeline import run_scraping_pipeline

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting full scraping pipeline ...")
    asyncio.run(run_scraping_pipeline())
    logger.info("Scraping pipeline finished.")
