"""Scrape Bart Torvik college basketball ratings and player stats.

Source: barttorvik.com — advanced team ratings and player statistics,
freely accessible and similar in scope to KenPom.

Uses Playwright (headless browser) because Torvik has JS-based browser
verification that blocks plain HTTP clients.

Usage:
    from src.scraping.torvik import scrape_all_team_ratings, scrape_all_player_stats

    ratings = scrape_all_team_ratings([2019, 2021, 2022, 2023, 2024, 2025])
    players = scrape_all_player_stats([2024, 2025])
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

from src.scraping.utils import PROJECT_ROOT, PlaywrightScraper, parse_html

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEASONS = [2019, 2021, 2022, 2023, 2024, 2025]  # skip 2020 (COVID)

TEAM_RATINGS_URL = "https://barttorvik.com/team-tables.php?year={season}&type=pointed"
PLAYER_STATS_URL = "https://barttorvik.com/playerstat.php?year={season}&minmpg=10"

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"

# ---------------------------------------------------------------------------
# Team-name normalisation
# ---------------------------------------------------------------------------

TEAM_NAME_MAP: dict[str, str] = {
    "UConn": "Connecticut",
    "UCONN": "Connecticut",
    "USC": "Southern California",
    "LSU": "Louisiana State",
    "SMU": "Southern Methodist",
    "UCF": "Central Florida",
    "UNLV": "Nevada-Las Vegas",
    "VCU": "Virginia Commonwealth",
    "BYU": "Brigham Young",
    "TCU": "Texas Christian",
    "UNC": "North Carolina",
    "UNCG": "UNC Greensboro",
    "UNCW": "UNC Wilmington",
    "ETSU": "East Tennessee State",
    "MTSU": "Middle Tennessee",
    "UTSA": "UT San Antonio",
    "UTEP": "Texas-El Paso",
    "UAB": "Alabama-Birmingham",
    "Ole Miss": "Mississippi",
    "Pitt": "Pittsburgh",
    "UMass": "Massachusetts",
    "UNI": "Northern Iowa",
    "Miami FL": "Miami (FL)",
    "Miami OH": "Miami (OH)",
    "Saint Mary's": "Saint Mary's (CA)",
    "LIU": "Long Island University",
    "FIU": "Florida International",
    "SIUE": "SIU Edwardsville",
    "SIU": "Southern Illinois",
    "UTRGV": "UT Rio Grande Valley",
    "UIC": "Illinois-Chicago",
    "NIU": "Northern Illinois",
    "WKU": "Western Kentucky",
    "FGCU": "Florida Gulf Coast",
}


def normalize_team_name(name: str) -> str:
    """Normalise a Torvik team name to match Sports Reference conventions."""
    if not isinstance(name, str):
        return str(name) if name is not None else ""
    name = name.strip()
    return TEAM_NAME_MAP.get(name, name)


# ---------------------------------------------------------------------------
# Team Ratings
# ---------------------------------------------------------------------------

TEAM_RATING_COLS = [
    "rank",
    "team",
    "conference",
    "record",
    "adj_em",
    "adj_oe",
    "adj_oe_rank",
    "adj_de",
    "adj_de_rank",
    "tempo",
    "tempo_rank",
    "luck",
    "luck_rank",
    "adj_sos",
    "adj_sos_rank",
    "opp_adj_oe",
    "opp_adj_oe_rank",
    "opp_adj_de",
    "opp_adj_de_rank",
    "conf_record",
    "q1_record",
    "q2_record",
    "q3_record",
    "q4_record",
    "wab",
]

NUMERIC_TEAM_COLS = [
    "rank",
    "adj_em",
    "adj_oe",
    "adj_oe_rank",
    "adj_de",
    "adj_de_rank",
    "tempo",
    "tempo_rank",
    "luck",
    "luck_rank",
    "adj_sos",
    "adj_sos_rank",
    "opp_adj_oe",
    "opp_adj_oe_rank",
    "opp_adj_de",
    "opp_adj_de_rank",
    "wab",
]


def _split_record(record_str: str) -> tuple[int, int]:
    """Parse a 'W-L' string into (wins, losses)."""
    try:
        parts = record_str.strip().split("-")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 0, 0


def _try_extract_json_rows(html: str) -> list[list[str]] | None:
    """Attempt to extract table data from an embedded JavaScript array."""
    pattern = r"var\s+defined_data\s*=\s*(\[[\s\S]*?\]);"
    match = re.search(pattern, html)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.debug("Found JS data blob but failed to parse JSON")
    return None


def _parse_team_ratings_html(html: str, season: int) -> pd.DataFrame:
    """Parse team ratings from raw HTML table.

    The Torvik table has headers like: Rk, Team, Conf, G, Rec, AdjOE,
    AdjDE, Barthag, EFG%, EFGD%, TOR, TORD, ORB, DRB, FTR, FTRD,
    2P%, 2P%D, 3P%, 3P%D, 3PR, 3PRD, Adj T., WAB
    """
    soup = parse_html(html)
    table = soup.select_one("table")
    if table is None:
        logger.warning("Season %d: no table found in HTML", season)
        return pd.DataFrame()

    # Extract column names from the last header row (skip over-header)
    headers: list[str] = []
    thead = table.select_one("thead")
    if thead:
        for tr in thead.select("tr"):
            ths = tr.select("th")
            texts = [th.get_text(strip=True) for th in ths]
            # Use the row that has "Rk" or "Team" as a real header row
            if any(t in ("Rk", "Team", "Conf") for t in texts):
                headers = texts
                break

    # Parse data rows
    rows: list[list[str]] = []
    tbody = table.select_one("tbody")
    if tbody:
        for tr in tbody.select("tr"):
            cells = [td.get_text(strip=True) for td in tr.select("td")]
            if cells:
                rows.append(cells)

    if not rows:
        logger.warning("Season %d: table found but no data rows", season)
        return pd.DataFrame()

    logger.info("Season %d: parsed %d teams from HTML table", season, len(rows))

    # Build DataFrame using actual headers if available
    if headers and len(headers) == len(rows[0]):
        df = pd.DataFrame(rows, columns=headers)
    elif headers:
        # Column count mismatch — use as many headers as we can
        n = min(len(headers), len(rows[0]))
        col_names = headers[:n] + [f"col_{i}" for i in range(n, len(rows[0]))]
        df = pd.DataFrame(rows, columns=col_names)
    else:
        df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Normalise column names to lowercase snake_case
    col_map = {
        "Rk": "rank",
        "Team": "team",
        "Conf": "conference",
        "G": "games",
        "Rec": "record",
        "AdjOE": "adj_oe",
        "AdjDE": "adj_de",
        "Barthag": "barthag",
        "EFG%": "efg_pct",
        "EFGD%": "efgd_pct",
        "TOR": "tov_rate",
        "TORD": "tov_rate_def",
        "ORB": "orb_pct",
        "DRB": "drb_pct",
        "FTR": "ft_rate",
        "FTRD": "ft_rate_def",
        "2P%": "two_pt_pct",
        "2P%D": "two_pt_pct_def",
        "3P%": "three_pt_pct",
        "3P%D": "three_pt_pct_def",
        "3PR": "three_pt_rate",
        "3PRD": "three_pt_rate_def",
        "Adj T.": "tempo",
        "WAB": "wab",
    }
    df = df.rename(columns=col_map)

    # Compute AdjEM from AdjOE and AdjDE
    for col in df.columns:
        if col not in ("team", "conference", "record", "rank"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "adj_oe" in df.columns and "adj_de" in df.columns:
        df["adj_em"] = df["adj_oe"] - df["adj_de"]

    # Clean team names: strip seed/emoji suffixes like "Duke1 seed, ✅"
    if "team" in df.columns:
        df["team"] = df["team"].str.replace(r"\d+\s*seed.*$", "", regex=True).str.strip()
        df["team"] = df["team"].apply(normalize_team_name)

    # Explode record into wins/losses
    if "record" in df.columns:
        df[["wins", "losses"]] = df["record"].apply(lambda r: pd.Series(_split_record(str(r))))

    df["season"] = season
    return df


# ---------------------------------------------------------------------------
# Player Stats
# ---------------------------------------------------------------------------

PLAYER_STAT_COLS = [
    "rank",
    "player",
    "team",
    "conference",
    "class_year",
    "gp",
    "mpg",
    "ppg",
    "rpg",
    "apg",
    "ortg",
    "usage_pct",
    "efg_pct",
    "ts_pct",
    "bpm",
]

NUMERIC_PLAYER_COLS = [
    "rank",
    "gp",
    "mpg",
    "ppg",
    "rpg",
    "apg",
    "ortg",
    "usage_pct",
    "efg_pct",
    "ts_pct",
    "bpm",
]


def _parse_player_stats_html(html: str, season: int) -> pd.DataFrame:
    """Parse player stats from Torvik HTML.

    The player stats page has two tables — the second one contains actual
    player data. Data rows have columns:
    Rk, Pick, ClassYear, Height, Player, PPG, Team, Conf, G, Role, Min%,
    PRPG, D-PRPG, BPM, OBPM, DBPM, ORtg, D-Rtg, Usg, eFG, TS, ...
    """
    soup = parse_html(html)
    tables = soup.select("table")

    # Use the second table (first is filter dropdowns)
    if len(tables) < 2:
        # Fall back to first table if only one
        table = tables[0] if tables else None
    else:
        table = tables[1]

    if table is None:
        logger.warning("Season %d: no player table found", season)
        return pd.DataFrame()

    tbody = table.select_one("tbody")
    if not tbody:
        logger.warning("Season %d: player table has no tbody", season)
        return pd.DataFrame()

    rows: list[list[str]] = []
    for tr in tbody.select("tr"):
        cells = [td.get_text(strip=True) for td in tr.select("td")]
        if cells and len(cells) > 10:
            rows.append(cells)

    if not rows:
        logger.warning("Season %d: player table empty", season)
        return pd.DataFrame()

    logger.info("Season %d: parsed %d players from HTML table", season, len(rows))

    # Map the actual column positions (based on observed Torvik layout):
    # 0=Rk, 1=Pick, 2=Class, 3=Height, 4=Player, 5=JerseyNo/DraftPick,
    # 6=Team, 7=Conf, 8=GP, 9=Role, 10=Min%, 11=PRPG, 12=D-PRPG,
    # 13=BPM, 14=OBPM, 15=DBPM, 16=ORtg, 17=DRtg, 18=Usg%, 19=eFG%,
    # 20=TS%, 21=ORB%, 22=DRB%, 23=Ast%, 24=TO%
    col_map = {
        0: "rank",
        2: "class_year",
        3: "height",
        4: "player",
        6: "team",
        7: "conference",
        8: "gp",
        9: "role",
        10: "min_pct",
        11: "prpg",
        13: "bpm",
        14: "obpm",
        15: "dbpm",
        16: "ortg",
        17: "drtg",
        18: "usg_pct",
        19: "efg_pct",
        20: "ts_pct",
        21: "orb_pct",
        22: "drb_pct",
        23: "ast_pct",
        24: "tov_pct",
    }

    extracted: list[dict] = []
    for row in rows:
        entry = {}
        for idx, col_name in col_map.items():
            if idx < len(row):
                entry[col_name] = row[idx]
        if entry.get("player") and entry.get("team"):
            extracted.append(entry)

    if not extracted:
        logger.warning("Season %d: no valid player rows extracted", season)
        return pd.DataFrame()

    df = pd.DataFrame(extracted)

    # Coerce numeric columns
    numeric_cols = [
        "rank",
        "gp",
        "min_pct",
        "prpg",
        "bpm",
        "obpm",
        "dbpm",
        "ortg",
        "drtg",
        "usg_pct",
        "efg_pct",
        "ts_pct",
        "orb_pct",
        "drb_pct",
        "ast_pct",
        "tov_pct",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalise team names
    if "team" in df.columns:
        df["team"] = df["team"].apply(normalize_team_name)

    df["season"] = season
    return df


# ---------------------------------------------------------------------------
# Public API — synchronous, Playwright-based
# ---------------------------------------------------------------------------

_scraper: PlaywrightScraper | None = None


def _get_scraper() -> PlaywrightScraper:
    """Lazy-initialize the shared Playwright scraper."""
    global _scraper  # noqa: PLW0603
    if _scraper is None:
        _scraper = PlaywrightScraper()
    return _scraper


def scrape_team_ratings(season: int) -> pd.DataFrame:
    """Scrape Torvik team ratings for a single season."""
    if season == 2020:
        logger.warning("Skipping season 2020 — cancelled due to COVID-19")
        return pd.DataFrame()

    url = TEAM_RATINGS_URL.format(season=season)
    logger.info("Fetching Torvik team ratings for %d: %s", season, url)

    scraper = _get_scraper()
    html = scraper.get(url, wait_for="table", wait_ms=5000)
    return _parse_team_ratings_html(html, season)


def scrape_player_stats(season: int) -> pd.DataFrame:
    """Scrape Torvik player stats for a single season."""
    if season == 2020:
        logger.warning("Skipping season 2020 — cancelled due to COVID-19")
        return pd.DataFrame()

    url = PLAYER_STATS_URL.format(season=season)
    logger.info("Fetching Torvik player stats for %d: %s", season, url)

    scraper = _get_scraper()
    html = scraper.get(url, wait_for="table", wait_ms=5000)
    return _parse_player_stats_html(html, season)


def scrape_all_team_ratings(
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Scrape Torvik team ratings across multiple seasons.

    Returns a combined DataFrame with a ``season`` column.
    """
    seasons = [s for s in (seasons or VALID_SEASONS) if s != 2020]
    frames: list[pd.DataFrame] = []

    for season in seasons:
        try:
            df = scrape_team_ratings(season)
            if not df.empty:
                frames.append(df)
        except Exception:
            logger.exception("Failed to scrape team ratings for %d", season)

    if not frames:
        logger.warning("No team-rating data collected")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    _save_parquet(combined, OUTPUT_DIR / "torvik_ratings.parquet")
    return combined


def scrape_all_player_stats(
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Scrape Torvik player stats across multiple seasons.

    Returns a combined DataFrame with a ``season`` column.
    """
    seasons = [s for s in (seasons or VALID_SEASONS) if s != 2020]
    frames: list[pd.DataFrame] = []

    for season in seasons:
        try:
            df = scrape_player_stats(season)
            if not df.empty:
                frames.append(df)
        except Exception:
            logger.exception("Failed to scrape player stats for %d", season)

    if not frames:
        logger.warning("No player-stat data collected")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    _save_parquet(combined, OUTPUT_DIR / "torvik_players.parquet")
    return combined


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to Parquet, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info("Saved %d rows to %s", len(df), path)


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    logger.info("Scraping Torvik team ratings for seasons %s", VALID_SEASONS)
    ratings = scrape_all_team_ratings()
    logger.info("Team ratings shape: %s", ratings.shape)

    logger.info("Scraping Torvik player stats for seasons %s", VALID_SEASONS)
    players = scrape_all_player_stats()
    logger.info("Player stats shape: %s", players.shape)

    if _scraper:
        _scraper.close()
