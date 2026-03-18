"""
Scraper for Sports Reference college basketball data.

Collects team stats, tournament results, player stats, and AP rankings
from sports-reference.com/cbb/ for seasons 2019-2025 (excluding 2020).
"""

import contextlib
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, Comment

from src.scraping.utils import CachedScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sports-reference.com/cbb"
DATA_RAW_DIR = Path("data/raw")
VALID_SEASONS = [2019, 2021, 2022, 2023, 2024, 2025, 2026]
RATE_LIMIT_SECONDS = 60 / 20  # 20 requests per minute

# ---------------------------------------------------------------------------
# Team name / URL slug helpers
# ---------------------------------------------------------------------------

# Common display-name -> Sports Reference slug overrides.
# Sports Reference uses kebab-case school names in URLs.
TEAM_NAME_OVERRIDES: dict[str, str] = {
    "UConn": "connecticut",
    "Connecticut": "connecticut",
    "UNC": "north-carolina",
    "North Carolina": "north-carolina",
    "LSU": "louisiana-state",
    "Louisiana State": "louisiana-state",
    "USC": "southern-california",
    "Southern California": "southern-california",
    "UCF": "central-florida",
    "Central Florida": "central-florida",
    "UNLV": "nevada-las-vegas",
    "Ole Miss": "mississippi",
    "Pitt": "pittsburgh",
    "SMU": "southern-methodist",
    "VCU": "virginia-commonwealth",
    "BYU": "brigham-young",
    "TCU": "texas-christian",
    "UCSB": "uc-santa-barbara",
    "UCSD": "uc-san-diego",
    "UCI": "uc-irvine",
    "UCLA": "ucla",
    "Miami (FL)": "miami-fl",
    "Miami (OH)": "miami-oh",
    "St. John's": "st-johns-ny",
    "Saint Mary's": "saint-marys-ca",
    "St. Mary's": "saint-marys-ca",
    "Saint Joseph's": "saint-josephs",
    "St. Joseph's": "saint-josephs",
    "St. Bonaventure": "st-bonaventure",
    "St. Peter's": "saint-peters",
    "NC State": "north-carolina-state",
    "ETSU": "east-tennessee-state",
    "FAU": "florida-atlantic",
    "FDU": "fairleigh-dickinson",
    "UAB": "alabama-birmingham",
    "UIC": "illinois-chicago",
    "UTEP": "texas-el-paso",
    "UTSA": "texas-san-antonio",
    "UT Arlington": "texas-arlington",
    "NIU": "northern-illinois",
    "SIU": "southern-illinois",
    "SIU Edwardsville": "southern-illinois-edwardsville",
    "LIU": "long-island-university",
    "Murray St.": "murray-state",
    "San Diego St.": "san-diego-state",
    "Boise St.": "boise-state",
    "Colorado St.": "colorado-state",
    "Fresno St.": "fresno-state",
    "Michigan St.": "michigan-state",
    "Penn St.": "penn-state",
    "Ohio St.": "ohio-state",
    "Iowa St.": "iowa-state",
    "Kansas St.": "kansas-state",
    "Mississippi St.": "mississippi-state",
    "Arizona St.": "arizona-state",
    "Oregon St.": "oregon-state",
    "Washington St.": "washington-state",
    # Lowercase variants (as stored in normalized tournament results)
    "uconn": "connecticut",
    "unc": "north-carolina",
    "lsu": "louisiana-state",
    "usc": "southern-california",
    "vcu": "virginia-commonwealth",
    "byu": "brigham-young",
    "tcu": "texas-christian",
    "nc state": "north-carolina-state",
    "fdu": "fairleigh-dickinson",
    "pitt": "pittsburgh",
    "saint marys": "saint-marys-ca",
    "uc santa barbara": "uc-santa-barbara",
    "uc san diego": "uc-san-diego",
    "mcneese": "mcneese-state",
    "ole miss": "mississippi",
    "omaha": "nebraska-omaha",
    "louisiana": "louisiana-lafayette",
    "texas a&m": "texas-am",
    "texas a&m-corpus christi": "texas-am-corpus-christi",
    "siu-edwardsville": "southern-illinois-edwardsville",
    "smu": "southern-methodist",
    "ucf": "central-florida",
    "unlv": "nevada-las-vegas",
}

# Reverse lookup: slug -> canonical display name
SLUG_TO_DISPLAY: dict[str, str] = {}
for _display, _slug in TEAM_NAME_OVERRIDES.items():
    # Keep the first (most common) display name per slug
    if _slug not in SLUG_TO_DISPLAY:
        SLUG_TO_DISPLAY[_slug] = _display


def team_name_to_slug(name: str) -> str:
    """Convert a display team name to the Sports Reference URL slug.

    Examples:
        >>> team_name_to_slug("UConn")
        'connecticut'
        >>> team_name_to_slug("North Carolina")
        'north-carolina'
        >>> team_name_to_slug("Duke")
        'duke'
    """
    name = name.strip()
    if name in TEAM_NAME_OVERRIDES:
        return TEAM_NAME_OVERRIDES[name]
    # Case-insensitive fallback lookup
    name_lower = name.lower()
    if name_lower in TEAM_NAME_OVERRIDES:
        return TEAM_NAME_OVERRIDES[name_lower]
    # Default: lowercase, replace spaces/periods with hyphens, strip parens
    slug = name.lower()
    slug = re.sub(r"[.''()]", "", slug)
    slug = re.sub(r"[\s&]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def slug_to_team_name(slug: str) -> str:
    """Convert a Sports Reference URL slug back to a display name."""
    if slug in SLUG_TO_DISPLAY:
        return SLUG_TO_DISPLAY[slug]
    # Default: title-case the slug
    return slug.replace("-", " ").title()


def normalize_team_name(name: str) -> str:
    """Normalize a team name for consistent matching.

    Strips special characters, lowercases, and removes common suffixes like
    NCAA tournament seed indicators.
    """
    if not isinstance(name, str):
        return str(name) if name is not None else ""
    name = name.strip()
    # Remove seed numbers in parens, e.g. "(1)"
    name = re.sub(r"\(\d+\)", "", name).strip()
    # Remove trailing asterisks or other markers
    name = re.sub(r"[*\u00a0]+$", "", name).strip()
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s&-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Season validation
# ---------------------------------------------------------------------------


def _validate_season(season: int) -> None:
    """Raise ValueError if the season is invalid (e.g. 2020)."""
    if season == 2020:
        raise ValueError(
            "The 2020 NCAA tournament was cancelled due to COVID-19. "
            "Season 2020 is excluded from scraping."
        )
    if season < 2019 or season > 2026:
        logger.warning("Season %d is outside the expected range 2019-2026.", season)


def _filter_seasons(seasons: list[int]) -> list[int]:
    """Filter out invalid seasons and warn about them."""
    valid = []
    for s in seasons:
        if s == 2020:
            logger.info("Skipping 2020 season (COVID cancellation).")
            continue
        valid.append(s)
    return valid


# ---------------------------------------------------------------------------
# Shared HTML parsing helpers
# ---------------------------------------------------------------------------

_scraper: CachedScraper | None = None


def _get_scraper() -> CachedScraper:
    """Lazy-initialize the CachedScraper singleton."""
    global _scraper  # noqa: PLW0603
    if _scraper is None:
        _scraper = CachedScraper(rate_limit=RATE_LIMIT_SECONDS)
    return _scraper


def _fetch_page(url: str) -> BeautifulSoup:
    """Fetch a page through the cached scraper and return parsed soup."""
    scraper = _get_scraper()
    html = scraper.get(url)
    return BeautifulSoup(html, "html.parser")


def _normalize_school_column(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize the school name column from a parsed SR table.

    - Uses ``school_name`` (data-stat) as the column name.
    - Strips ``NCAA`` suffix that SR appends to tournament teams.
    - Drops aggregate rows (Overall / Average).
    - Adds a ``school_normalized`` column via ``normalize_team_name``.
    """
    # Ensure we have a school_name column
    if "school_name" not in df.columns:
        for candidate in ("school", "School", df.columns[1] if len(df.columns) > 1 else None):
            if candidate and candidate in df.columns:
                df = df.rename(columns={candidate: "school_name"})
                break

    if "school_name" not in df.columns:
        raise KeyError("Cannot find school name column in DataFrame")

    # Strip "NCAA" suffix (tournament indicator)
    df["school_name"] = (
        df["school_name"].astype(str).str.replace(r"NCAA$", "", regex=True).str.strip()
    )

    # Drop aggregate / divider rows
    df = df[
        ~df["school_name"].str.contains(r"^(?:NCAA|Overall|Average|School)$", case=False, na=False)
    ]
    df = df[df["school_name"].str.len() > 0].reset_index(drop=True)

    # Add normalized name
    df["school_normalized"] = df["school_name"].apply(normalize_team_name)

    return df


def _uncomment_tables(soup: BeautifulSoup) -> BeautifulSoup:
    """Sports Reference hides some tables inside HTML comments. Uncomment them."""
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in str(comment):
            fragment = BeautifulSoup(str(comment), "html.parser")
            comment.replace_with(fragment)
    return soup


def _parse_sr_table(soup: BeautifulSoup, table_id: str) -> pd.DataFrame:
    """Parse a Sports Reference HTML table into a DataFrame.

    Uses ``data-stat`` attributes on ``<th>``/``<td>`` elements as column
    names — these are the most reliable identifiers across Sports Reference
    pages and avoid issues with multi-level "over_header" rows.
    """
    table = soup.find("table", {"id": table_id})
    if table is None:
        raise ValueError(f"Table with id='{table_id}' not found on page.")

    # --- Determine column names from the non-over_header <thead> row ---
    thead = table.find("thead")
    columns: list[str] = []
    if thead:
        for tr in thead.find_all("tr"):
            classes = tr.get("class") or []
            if "over_header" in classes:
                continue
            cells = tr.find_all("th")
            cols = []
            for th in cells:
                stat = th.get("data-stat", th.get_text(strip=True))
                cols.append(stat)
            if cols:
                columns = cols
                break  # use the first non-over_header row

    # Fallback: build columns from text of the last header row
    if not columns and thead:
        last_tr = thead.find_all("tr")[-1]
        columns = [th.get_text(strip=True) for th in last_tr.find_all("th")]

    if not columns:
        raise ValueError(f"No header rows found in table '{table_id}'.")

    # De-duplicate column names
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            deduped.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            deduped.append(col)
    columns = deduped

    # --- Parse body rows using data-stat as keys ---
    tbody = table.find("tbody")
    if tbody is None:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, str]] = []
    for tr in tbody.find_all("tr"):
        classes = tr.get("class") or []
        if "thead" in classes or "over_header" in classes:
            continue
        cells = tr.find_all(["th", "td"])
        row: dict[str, str] = {}
        for cell in cells:
            stat = cell.get("data-stat", "")
            if stat:
                row[stat] = cell.get_text(strip=True)
        if row:
            rows.append(row)

    df = pd.DataFrame(rows)

    # Drop completely empty rows
    df = df.replace("", pd.NA).dropna(how="all").reset_index(drop=True)

    return df


def _clean_numeric_columns(df: pd.DataFrame, skip_cols: list[str] | None = None) -> pd.DataFrame:
    """Attempt to convert columns to numeric where possible."""
    skip = set(skip_cols or [])
    for col in df.columns:
        if col in skip:
            continue
        with contextlib.suppress(ValueError, TypeError):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _add_season_column(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Insert a 'season' column at position 0."""
    df.insert(0, "season", season)
    return df


def _save_parquet(df: pd.DataFrame, filename: str) -> Path:
    """Save a DataFrame to data/raw/ as parquet."""
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_RAW_DIR / filename
    df.to_parquet(path, index=False)
    logger.info("Saved %d rows to %s", len(df), path)
    return path


# ---------------------------------------------------------------------------
# 1. Team Stats Scraping
# ---------------------------------------------------------------------------


def scrape_team_basic_stats(season: int) -> pd.DataFrame:
    """Scrape per-game team stats (PPG, RPG, APG, FG%, 3P%, FT%, etc.).

    URL: https://www.sports-reference.com/cbb/seasons/men/{season}-school-stats.html

    Returns a DataFrame with one row per team.
    """
    _validate_season(season)
    url = f"{BASE_URL}/seasons/men/{season}-school-stats.html"
    logger.info("Scraping basic team stats for %d from %s", season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    df = _parse_sr_table(soup, "basic_school_stats")

    df = _normalize_school_column(df)

    df = _clean_numeric_columns(df, skip_cols=["school_name", "school_normalized"])
    df = _add_season_column(df, season)

    _save_parquet(df, f"team_basic_stats_{season}.parquet")
    return df


def scrape_team_advanced_stats(season: int) -> pd.DataFrame:
    """Scrape advanced team stats (ORtg, DRtg, SOS, SRS, Pace, eFG%, TS%, etc.).

    URL: https://www.sports-reference.com/cbb/seasons/men/{season}-advanced-school-stats.html
    """
    _validate_season(season)
    url = f"{BASE_URL}/seasons/men/{season}-advanced-school-stats.html"
    logger.info("Scraping advanced team stats for %d from %s", season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    df = _parse_sr_table(soup, "adv_school_stats")
    df = _normalize_school_column(df)

    df = _clean_numeric_columns(df, skip_cols=["school_name", "school_normalized"])
    df = _add_season_column(df, season)

    _save_parquet(df, f"team_advanced_stats_{season}.parquet")
    return df


def scrape_team_opponent_stats(season: int) -> pd.DataFrame:
    """Scrape opponent (defensive) team stats.

    URL: https://www.sports-reference.com/cbb/seasons/men/{season}-opponent-stats.html
    """
    _validate_season(season)
    url = f"{BASE_URL}/seasons/men/{season}-opponent-stats.html"
    logger.info("Scraping opponent stats for %d from %s", season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    df = _parse_sr_table(soup, "basic_opp_stats")
    df = _normalize_school_column(df)

    # Prefix opponent stat columns with "opp_" for clarity
    rename_map = {}
    for col in df.columns:
        if col not in ("school_name", "school_normalized", "season", "ranker"):
            rename_map[col] = f"opp_{col}"
    df = df.rename(columns=rename_map)

    df = _clean_numeric_columns(df, skip_cols=["school_name", "school_normalized"])
    df = _add_season_column(df, season)

    _save_parquet(df, f"team_opponent_stats_{season}.parquet")
    return df


# ---------------------------------------------------------------------------
# 2. Tournament Data
# ---------------------------------------------------------------------------


def scrape_tournament_results(season: int) -> pd.DataFrame:
    """Scrape NCAA tournament seeds, matchups, scores, and results.

    URL: https://www.sports-reference.com/cbb/postseason/men/{season}-ncaa.html

    Returns a DataFrame with columns:
        season, round, region, seed_1, team_1, score_1, seed_2, team_2, score_2, winner
    """
    _validate_season(season)
    url = f"{BASE_URL}/postseason/men/{season}-ncaa.html"
    logger.info("Scraping tournament results for %d from %s", season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    # Sports Reference renders the bracket inside <div id="brackets">
    # with child divs for each region (east, west, south, midwest)
    # plus a "national" div for Final Four and Championship.
    # Each region has <div class="round"> elements containing game divs.
    brackets_div = soup.find("div", id="brackets")
    if not brackets_div:
        logger.warning("No brackets container found for season %d.", season)
        return pd.DataFrame()

    # Collect all region divs
    region_ids = ["east", "west", "south", "midwest", "national"]
    region_divs = []
    for rid in region_ids:
        rdiv = brackets_div.find("div", id=rid)
        if rdiv:
            region_divs.append((rid, rdiv))

    if not region_divs:
        logger.warning("No region divs found for season %d.", season)
        return pd.DataFrame()

    # Round names per region (4 rounds) and national (2 rounds)
    regional_round_names = ["First Round", "Second Round", "Sweet 16", "Elite 8"]
    national_round_names = ["Final Four", "Championship"]

    games: list[dict] = []

    for region_name, region_div in region_divs:
        rounds = region_div.find_all("div", class_="round")
        if not rounds:
            continue

        if region_name == "national":
            rnames = national_round_names
        else:
            rnames = regional_round_names

        for round_idx, round_div in enumerate(rounds):
            round_name = rnames[round_idx] if round_idx < len(rnames) else f"Round {round_idx + 1}"

            # Each game is a direct-child div of the round div.
            game_divs = round_div.find_all("div", recursive=False)

            for game_div in game_divs:
                team_divs = [d for d in game_div.find_all("div", recursive=False)]
                if len(team_divs) < 2:
                    continue

                team_entries: list[dict] = []
                is_winner: list[bool] = []
                for td in team_divs[:2]:
                    seed_span = td.find("span")
                    seed = None
                    if seed_span:
                        seed_text = seed_span.get_text(strip=True)
                        if seed_text.isdigit():
                            seed = int(seed_text)

                    team_name = None
                    team_link = td.find("a", href=re.compile(r"/cbb/schools/"))
                    if team_link:
                        team_name = team_link.get_text(strip=True)

                    score = None
                    score_links = td.find_all("a", href=re.compile(r"/cbb/boxscores/"))
                    for sl in score_links:
                        text = sl.get_text(strip=True)
                        if text.isdigit():
                            score = int(text)
                            break

                    if team_name:
                        team_entries.append({"seed": seed, "team": team_name, "score": score})
                        is_winner.append("winner" in (td.get("class") or []))

                if len(team_entries) == 2:
                    t1, t2 = team_entries[0], team_entries[1]
                    if is_winner[0]:
                        winner = t1["team"]
                    elif is_winner[1]:
                        winner = t2["team"]
                    elif t1["score"] and t2["score"]:
                        winner = t1["team"] if t1["score"] > t2["score"] else t2["team"]
                    else:
                        winner = None

                    games.append(
                        {
                            "season": season,
                            "round": round_name,
                            "seed_1": t1["seed"],
                            "team_1": t1["team"],
                            "score_1": t1["score"],
                            "seed_2": t2["seed"],
                            "team_2": t2["team"],
                            "score_2": t2["score"],
                            "winner": winner,
                        }
                    )

    df = pd.DataFrame(games)
    if df.empty:
        logger.warning("No tournament games parsed for season %d.", season)
        return df

    df["team_1_normalized"] = df["team_1"].apply(normalize_team_name)
    df["team_2_normalized"] = df["team_2"].apply(normalize_team_name)
    df["winner_normalized"] = df["winner"].apply(normalize_team_name)

    _save_parquet(df, f"tournament_results_{season}.parquet")
    return df


def _parse_tournament_table_fallback(soup: BeautifulSoup, season: int) -> list[dict]:
    """Fallback parser that looks for table-structured tournament data."""
    games: list[dict] = []
    # Look for any table containing tournament game data
    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        if not tbody:
            continue
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 4:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            # Try to extract game info from row
            try:
                seed_match_1 = re.match(r"(\d+)\s*(.*)", texts[0])
                seed_match_2 = re.match(r"(\d+)\s*(.*)", texts[2])
                if seed_match_1 and seed_match_2:
                    s1, t1 = int(seed_match_1.group(1)), seed_match_1.group(2)
                    score1 = int(texts[1]) if texts[1].isdigit() else 0
                    s2, t2 = int(seed_match_2.group(1)), seed_match_2.group(2)
                    score2 = int(texts[3]) if texts[3].isdigit() else 0
                    winner = t1 if score1 > score2 else t2
                    games.append(
                        {
                            "season": season,
                            "round": "Unknown",
                            "seed_1": s1,
                            "team_1": t1,
                            "score_1": score1,
                            "seed_2": s2,
                            "team_2": t2,
                            "score_2": score2,
                            "winner": winner,
                        }
                    )
            except (ValueError, IndexError):
                continue
    return games


def _extract_tournament_teams(season: int) -> list[tuple[str, str]]:
    """Extract list of (team_display_name, team_slug) for tournament teams.

    Uses the tournament results page to find participating teams.
    """
    url = f"{BASE_URL}/postseason/men/{season}-ncaa.html"
    soup = _fetch_page(url)

    teams: set[str] = set()
    # Find all team links on the tournament page
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.match(r"/cbb/schools/([a-z0-9-]+)/", href)
        if match:
            teams.add(match.group(1))

    result = [(slug_to_team_name(slug), slug) for slug in sorted(teams)]
    logger.info("Found %d tournament teams for season %d.", len(result), season)
    return result


def _extract_all_d1_teams(season: int) -> list[tuple[str, str]]:
    """Extract list of (team_display_name, team_slug) for ALL D1 teams.

    Uses the school stats page which covers every D1 program, not just
    tournament participants. This ensures teams like Cal Baptist, Queens NC,
    and Long Island get player features even if they've never made the tournament.
    """
    url = f"{BASE_URL}/seasons/men/{season}-school-stats.html"
    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    teams: set[str] = set()
    # All D1 team links appear as /cbb/schools/{slug}/ in the school stats table
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        match = re.match(r"/cbb/schools/([a-z0-9-]+)/", href)
        if match:
            teams.add(match.group(1))

    result = [(slug_to_team_name(slug), slug) for slug in sorted(teams)]
    logger.info("Found %d D1 teams for season %d.", len(result), season)
    return result


# ---------------------------------------------------------------------------
# 3. Player Stats (for tournament teams)
# ---------------------------------------------------------------------------


def scrape_team_roster(team_id: str, season: int) -> pd.DataFrame:
    """Scrape top 8 players by minutes for a given team and season.

    URL: https://www.sports-reference.com/cbb/schools/{team_id}/men/{season}.html

    Per player: PTS, REB, AST, STL, BLK, TO, PER, Usage%, WS/40, BPM, TS%,
                class year, games started.
    """
    _validate_season(season)
    url = f"{BASE_URL}/schools/{team_id}/men/{season}.html"
    logger.info("Scraping roster for %s (%d) from %s", team_id, season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    # Try multiple table IDs - Sports Reference uses different IDs across seasons
    per_game_df = None
    for table_id in ("per_game", "players_per_game", "roster"):
        try:
            per_game_df = _parse_sr_table(soup, table_id)
            break
        except ValueError:
            continue

    if per_game_df is None or per_game_df.empty:
        logger.warning("No per-game table found for %s in %d.", team_id, season)
        return pd.DataFrame()

    # Try to get advanced stats table
    advanced_df = None
    for table_id in ("advanced", "players_advanced"):
        try:
            advanced_df = _parse_sr_table(soup, table_id)
            break
        except ValueError:
            continue

    # Clean the per-game DataFrame
    # The player name column may be "Player" or the first column
    player_col = "Player" if "Player" in per_game_df.columns else per_game_df.columns[0]

    # Remove total/team rows
    per_game_df = per_game_df[
        ~per_game_df[player_col].str.contains("Team|Total|Opponent", case=False, na=False)
    ].copy()

    # Convert minutes to numeric for sorting
    mp_col = None
    for candidate in ("MP", "MPG", "Min"):
        if candidate in per_game_df.columns:
            mp_col = candidate
            break

    if mp_col:
        per_game_df[mp_col] = pd.to_numeric(per_game_df[mp_col], errors="coerce")
        per_game_df = per_game_df.sort_values(mp_col, ascending=False).head(8)
    else:
        per_game_df = per_game_df.head(8)

    # Merge with advanced stats if available
    if advanced_df is not None and not advanced_df.empty:
        adv_player_col = "Player" if "Player" in advanced_df.columns else advanced_df.columns[0]
        # Keep only relevant advanced columns
        adv_cols_of_interest = [
            adv_player_col,
            "PER",
            "USG%",
            "WS/40",
            "BPM",
            "TS%",
            "eFG%",
            "ORB%",
            "DRB%",
            "TRB%",
            "AST%",
            "STL%",
            "BLK%",
            "TOV%",
        ]
        adv_cols_present = [c for c in adv_cols_of_interest if c in advanced_df.columns]
        if adv_cols_present:
            advanced_subset = advanced_df[adv_cols_present].copy()
            per_game_df = per_game_df.merge(
                advanced_subset,
                left_on=player_col,
                right_on=adv_player_col,
                how="left",
                suffixes=("", "_adv"),
            )

    per_game_df = _clean_numeric_columns(per_game_df, skip_cols=[player_col, "Class", "Pos"])
    per_game_df.insert(0, "team_id", team_id)
    per_game_df = _add_season_column(per_game_df, season)

    return per_game_df


def scrape_tournament_player_stats(season: int) -> pd.DataFrame:
    """Scrape player stats for all tournament teams in a given season."""
    _validate_season(season)
    logger.info("Scraping player stats for all tournament teams in %d.", season)

    teams = _extract_tournament_teams(season)
    all_rosters: list[pd.DataFrame] = []

    for display_name, slug in teams:
        try:
            roster = scrape_team_roster(slug, season)
            if not roster.empty:
                all_rosters.append(roster)
        except Exception:
            logger.exception(
                "Failed to scrape roster for %s (%s) in %d.", display_name, slug, season
            )
            continue

    if not all_rosters:
        logger.warning("No player data collected for season %d.", season)
        return pd.DataFrame()

    df = pd.concat(all_rosters, ignore_index=True)
    _save_parquet(df, f"tournament_player_stats_{season}.parquet")
    return df


def scrape_all_d1_player_stats(season: int) -> pd.DataFrame:
    """Scrape player stats for ALL D1 teams in a given season.

    Unlike scrape_tournament_player_stats, this covers every D1 program
    regardless of tournament participation. This eliminates null features
    for teams like Cal Baptist, Queens NC, Long Island, etc. that have never
    made the NCAA tournament but may appear in future brackets.
    """
    _validate_season(season)
    logger.info("Scraping player stats for ALL D1 teams in %d.", season)

    teams = _extract_all_d1_teams(season)
    all_rosters: list[pd.DataFrame] = []

    for display_name, slug in teams:
        try:
            roster = scrape_team_roster(slug, season)
            if not roster.empty:
                all_rosters.append(roster)
        except Exception:
            logger.exception(
                "Failed to scrape roster for %s (%s) in %d.", display_name, slug, season
            )
            continue

    if not all_rosters:
        logger.warning("No player data collected for season %d.", season)
        return pd.DataFrame()

    df = pd.concat(all_rosters, ignore_index=True)
    _save_parquet(df, f"all_d1_player_stats_{season}.parquet")
    return df


# ---------------------------------------------------------------------------
# 4. AP Rankings
# ---------------------------------------------------------------------------


def scrape_ap_rankings(season: int) -> pd.DataFrame:
    """Scrape weekly AP Top 25 poll data.

    URL: https://www.sports-reference.com/cbb/seasons/men/{season}-polls.html

    Returns a DataFrame with columns for each week's ranking plus
    summary columns: weeks_ranked, preseason_rank, final_rank.
    """
    _validate_season(season)
    url = f"{BASE_URL}/seasons/men/{season}-polls.html"
    logger.info("Scraping AP rankings for %d from %s", season, url)

    soup = _fetch_page(url)
    soup = _uncomment_tables(soup)

    # Try common table IDs for polls
    df = None
    for table_id in ("ap-polls", "ap-poll", "polls", "ap_poll"):
        try:
            df = _parse_sr_table(soup, table_id)
            break
        except ValueError:
            continue

    if df is None or df.empty:
        logger.warning("No AP poll table found for season %d.", season)
        return pd.DataFrame()

    df = _normalize_school_column(df)

    # Derive summary columns if not already present
    week_cols = [
        c for c in df.columns if re.match(r"(pre|final|week\d+|\d+|wk\s*\d+)", c, re.IGNORECASE)
    ]

    if "weeks_ranked" not in [c.lower().replace(" ", "_") for c in df.columns]:
        df["weeks_ranked"] = df[week_cols].apply(
            lambda row: row.notna().sum() if not row.empty else 0, axis=1
        )

    pre_col = next((c for c in week_cols if "pre" in c.lower()), None)
    final_col = next((c for c in week_cols if "final" in c.lower()), None)

    # If no explicit Pre/Final columns, use first and last week columns
    if not pre_col and week_cols:
        pre_col = week_cols[0]
    if not final_col and week_cols:
        final_col = week_cols[-1]

    if pre_col:
        df["preseason_rank"] = pd.to_numeric(df[pre_col], errors="coerce")
    if final_col:
        df["final_rank"] = pd.to_numeric(df[final_col], errors="coerce")

    df = _clean_numeric_columns(df, skip_cols=["school_name", "school_normalized"])
    df = _add_season_column(df, season)

    _save_parquet(df, f"ap_rankings_{season}.parquet")
    return df


# ---------------------------------------------------------------------------
# 5. Bulk Scraping Functions
# ---------------------------------------------------------------------------


def scrape_all_team_stats(
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Scrape basic, advanced, and opponent stats for all given seasons.

    Returns a merged DataFrame with one row per team-season.
    Saves intermediate per-season files and a combined file.
    """
    seasons = _filter_seasons(seasons or VALID_SEASONS)
    all_dfs: list[pd.DataFrame] = []

    for season in seasons:
        logger.info("Scraping all team stats for season %d...", season)
        try:
            basic = scrape_team_basic_stats(season)
            advanced = scrape_team_advanced_stats(season)
            opponent = scrape_team_opponent_stats(season)

            # Merge on season + normalized school name
            merge_keys = ["season", "school_normalized"]
            drop_cols = ["school_name", "ranker"]
            merged = basic.merge(
                advanced.drop(
                    columns=[c for c in drop_cols if c in advanced.columns], errors="ignore"
                ),
                on=merge_keys,
                how="outer",
                suffixes=("", "_adv"),
            )
            merged = merged.merge(
                opponent.drop(
                    columns=[c for c in drop_cols if c in opponent.columns], errors="ignore"
                ),
                on=merge_keys,
                how="outer",
                suffixes=("", "_opp"),
            )
            all_dfs.append(merged)
        except Exception:
            logger.exception("Failed to scrape team stats for season %d.", season)
            continue

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    _save_parquet(combined, "team_stats_all_seasons.parquet")
    return combined


def scrape_all_tournament_results(
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Scrape tournament results for all given seasons."""
    seasons = _filter_seasons(seasons or VALID_SEASONS)
    all_dfs: list[pd.DataFrame] = []

    for season in seasons:
        try:
            df = scrape_tournament_results(season)
            if not df.empty:
                all_dfs.append(df)
        except Exception:
            logger.exception("Failed to scrape tournament results for season %d.", season)
            continue

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    _save_parquet(combined, "tournament_results_all_seasons.parquet")
    return combined


def scrape_targeted_player_stats(
    team_slugs: list[str],
    season: int,
) -> pd.DataFrame:
    """Scrape player stats for a specific list of team slugs in one season.

    Used to cover a targeted set of teams (e.g. historical tournament participants
    plus current-year bracket entrants) without pulling all ~360 D1 programs.
    """
    _validate_season(season)
    logger.info(
        "Scraping player stats for %d targeted teams in %d.", len(team_slugs), season
    )

    all_rosters: list[pd.DataFrame] = []
    for slug in team_slugs:
        try:
            roster = scrape_team_roster(slug, season)
            if not roster.empty:
                all_rosters.append(roster)
        except Exception:
            logger.exception("Failed to scrape roster for %s in %d.", slug, season)

    if not all_rosters:
        logger.warning("No player data collected for season %d (targeted).", season)
        return pd.DataFrame()

    df = pd.concat(all_rosters, ignore_index=True)
    _save_parquet(df, f"targeted_player_stats_{season}.parquet")
    return df


def scrape_all_player_stats(
    seasons: list[int] | None = None,
    all_d1: bool = True,
) -> pd.DataFrame:
    """Scrape player stats across all given seasons.

    Args:
        seasons: Seasons to scrape. Defaults to all valid seasons.
        all_d1: If True (default), scrapes all D1 teams so that non-tournament
                programs like Cal Baptist and Queens NC get full player features.
                If False, scrapes tournament teams only (legacy behavior).
    """
    seasons = _filter_seasons(seasons or VALID_SEASONS)
    all_dfs: list[pd.DataFrame] = []

    for season in seasons:
        try:
            if all_d1:
                df = scrape_all_d1_player_stats(season)
            else:
                df = scrape_tournament_player_stats(season)
            if not df.empty:
                all_dfs.append(df)
        except Exception:
            logger.exception("Failed to scrape player stats for season %d.", season)
            continue

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    filename = "all_d1_player_stats_all_seasons.parquet" if all_d1 else "tournament_player_stats_all_seasons.parquet"
    _save_parquet(combined, filename)
    return combined


def scrape_all_ap_rankings(
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Scrape AP rankings for all given seasons."""
    seasons = _filter_seasons(seasons or VALID_SEASONS)
    all_dfs: list[pd.DataFrame] = []

    for season in seasons:
        try:
            df = scrape_ap_rankings(season)
            if not df.empty:
                all_dfs.append(df)
        except Exception:
            logger.exception("Failed to scrape AP rankings for season %d.", season)
            continue

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    _save_parquet(combined, "ap_rankings_all_seasons.parquet")
    return combined


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting Sports Reference scrape for seasons %s", VALID_SEASONS)

    logger.info("=== Team Stats ===")
    team_stats = scrape_all_team_stats()
    logger.info("Team stats: %d rows", len(team_stats))

    logger.info("=== Tournament Results ===")
    tourney = scrape_all_tournament_results()
    logger.info("Tournament results: %d rows", len(tourney))

    logger.info("=== Player Stats ===")
    players = scrape_all_player_stats()
    logger.info("Player stats: %d rows", len(players))

    logger.info("=== AP Rankings ===")
    rankings = scrape_all_ap_rankings()
    logger.info("AP rankings: %d rows", len(rankings))

    logger.info("Scraping complete.")
