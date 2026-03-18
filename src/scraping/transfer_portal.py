"""Transfer portal data scraping and roster continuity analysis.

Primary strategy: scrape publicly accessible transfer portal pages.
Fallback strategy: derive roster continuity metrics from player-level stats,
which is more reliable and works for all seasons (including pre-2021 when
portal data is sparse).
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd

from src.scraping.utils import PROJECT_ROOT, ScraperClient, ScraperConfig

logger = logging.getLogger(__name__)

OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "transfer_portal.parquet"

# ---------------------------------------------------------------------------
# Team-name normalisation
# ---------------------------------------------------------------------------

_TEAM_NAME_MAP: dict[str, str] = {
    "UConn": "Connecticut",
    "UCONN": "Connecticut",
    "UNC": "North Carolina",
    "USC": "Southern California",
    "LSU": "Louisiana State",
    "SMU": "Southern Methodist",
    "UCF": "Central Florida",
    "UNLV": "Nevada-Las Vegas",
    "VCU": "Virginia Commonwealth",
    "BYU": "Brigham Young",
    "TCU": "Texas Christian",
    "Ole Miss": "Mississippi",
    "Pitt": "Pittsburgh",
    "Miami (FL)": "Miami FL",
    "Miami (OH)": "Miami OH",
    "St. John's": "St Johns",
    "Saint John's": "St Johns",
    "St. Mary's": "St Marys",
    "Saint Mary's": "St Marys",
}


def normalize_team_name(name: str) -> str:
    """Normalise a team name to a canonical form."""
    stripped = name.strip()
    return _TEAM_NAME_MAP.get(stripped, stripped)


# ---------------------------------------------------------------------------
# 1) Scrape transfer portal data (best-effort)
# ---------------------------------------------------------------------------


async def _fetch_portal_page(client: ScraperClient, season: int) -> pd.DataFrame:
    """Attempt to scrape a single season of transfer portal data.

    Tries the ESPN transfer tracker endpoint which is publicly accessible and
    less aggressive with bot blocking than 247sports / On3.

    Returns a DataFrame with columns:
        team, season, incoming_transfers, outgoing_transfers,
        transfer_names, transfer_prior_ppg
    """
    url = (
        f"https://www.espn.com/mens-college-basketball/story/_/id/transfer-portal-tracker-{season}"
    )
    try:
        soup = await client.fetch_soup(url)
    except Exception:
        logger.info(
            "ESPN portal tracker unavailable for %d, trying alternate source",
            season,
        )
        return pd.DataFrame()

    # ESPN transfer tracker pages use a table structure.  The exact markup
    # changes between redesigns, so we attempt multiple selectors.
    rows: list[dict] = []
    table = soup.select_one("table.Table") or soup.find("table")
    if table is None:
        logger.debug("No table found on ESPN portal page for %d", season)
        return pd.DataFrame()

    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        try:
            player_name = cells[0].get_text(strip=True)
            from_team = normalize_team_name(cells[1].get_text(strip=True))
            to_team = normalize_team_name(cells[2].get_text(strip=True))
            ppg = 0.0
            if len(cells) > 3:
                try:
                    ppg = float(cells[3].get_text(strip=True))
                except (ValueError, TypeError):
                    ppg = 0.0

            # Record an outgoing transfer for the origin school
            rows.append(
                {
                    "team": from_team,
                    "season": season,
                    "direction": "outgoing",
                    "player_name": player_name,
                    "prior_ppg": ppg,
                }
            )
            # Record an incoming transfer for the destination school
            if to_team:
                rows.append(
                    {
                        "team": to_team,
                        "season": season,
                        "direction": "incoming",
                        "player_name": player_name,
                        "prior_ppg": ppg,
                    }
                )
        except (IndexError, AttributeError):
            continue

    if not rows:
        return pd.DataFrame()

    raw = pd.DataFrame(rows)

    # Aggregate to one row per team per season
    incoming = (
        raw[raw["direction"] == "incoming"]
        .groupby(["team", "season"])
        .agg(
            incoming_transfers=("player_name", "count"),
            incoming_names=("player_name", lambda x: "; ".join(x)),
            incoming_ppg=("prior_ppg", "mean"),
        )
        .reset_index()
    )
    outgoing = (
        raw[raw["direction"] == "outgoing"]
        .groupby(["team", "season"])
        .agg(
            outgoing_transfers=("player_name", "count"),
            outgoing_names=("player_name", lambda x: "; ".join(x)),
            outgoing_ppg=("prior_ppg", "mean"),
        )
        .reset_index()
    )

    merged = pd.merge(incoming, outgoing, on=["team", "season"], how="outer").fillna(
        {"incoming_transfers": 0, "outgoing_transfers": 0, "incoming_ppg": 0.0, "outgoing_ppg": 0.0}
    )
    merged["transfer_names"] = merged.apply(
        lambda r: "; ".join(
            filter(None, [str(r.get("incoming_names", "")), str(r.get("outgoing_names", ""))])
        ),
        axis=1,
    )
    merged["transfer_prior_ppg"] = (
        merged["incoming_ppg"].fillna(0) + merged["outgoing_ppg"].fillna(0)
    ) / 2

    result = merged[
        [
            "team",
            "season",
            "incoming_transfers",
            "outgoing_transfers",
            "transfer_names",
            "transfer_prior_ppg",
        ]
    ].copy()
    result["incoming_transfers"] = result["incoming_transfers"].astype(int)
    result["outgoing_transfers"] = result["outgoing_transfers"].astype(int)

    logger.info("Scraped %d portal rows for season %d", len(result), season)
    return result


def scrape_transfer_portal(season: int) -> pd.DataFrame:
    """Scrape transfer portal data for a single season.

    Parameters
    ----------
    season : int
        The NCAA season year (e.g. 2024 for the 2023-24 season).

    Returns
    -------
    pd.DataFrame
        Columns: team, season, incoming_transfers, outgoing_transfers,
        transfer_names, transfer_prior_ppg.
        Returns an empty DataFrame if scraping fails.
    """
    try:
        config = ScraperConfig(requests_per_minute=10, cache_ttl_seconds=86400 * 7)

        async def _run() -> pd.DataFrame:
            async with ScraperClient(config) as client:
                return await _fetch_portal_page(client, season)

        return asyncio.run(_run())
    except Exception as exc:
        logger.warning("Transfer portal scrape failed for %d: %s", season, exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 2) Roster continuity from player stats
# ---------------------------------------------------------------------------


def calculate_roster_continuity(
    current_roster: pd.DataFrame,
    prev_roster: pd.DataFrame,
) -> dict:
    """Calculate roster continuity between two consecutive seasons for a team.

    Parameters
    ----------
    current_roster : pd.DataFrame
        Player stats for the current season.  Must contain at least
        ``player_name`` (or ``player``), ``minutes`` (or ``mp``), and
        ``points`` (or ``pts``) columns.
    prev_roster : pd.DataFrame
        Player stats for the prior season (same team).

    Returns
    -------
    dict
        Keys: returning_minutes_pct, returning_scoring_pct, new_player_count.
    """

    # Normalise column names so we can handle varied schemas
    def _norm(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        col_map = {
            "player": "player_name",
            "mp": "minutes",
            "pts": "points",
            "min": "minutes",
            "ppg": "points",
        }
        df.columns = [col_map.get(c.lower(), c.lower()) for c in df.columns]
        for needed in ("player_name", "minutes", "points"):
            if needed not in df.columns:
                df[needed] = 0
        df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
        df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0)
        df["player_name"] = df["player_name"].astype(str).str.strip().str.lower()
        return df

    curr = _norm(current_roster)
    prev = _norm(prev_roster)

    if prev.empty or prev["minutes"].sum() == 0:
        return {
            "returning_minutes_pct": 0.0,
            "returning_scoring_pct": 0.0,
            "new_player_count": len(curr),
        }

    prev_total_min = prev["minutes"].sum()
    prev_total_pts = prev["points"].sum()

    # Players present in both seasons
    returning_players = set(curr["player_name"]) & set(prev["player_name"])

    prev_returning = prev[prev["player_name"].isin(returning_players)]
    returning_min = prev_returning["minutes"].sum()
    returning_pts = prev_returning["points"].sum()

    returning_minutes_pct = returning_min / prev_total_min if prev_total_min > 0 else 0.0
    returning_scoring_pct = returning_pts / prev_total_pts if prev_total_pts > 0 else 0.0
    new_player_count = len(set(curr["player_name"]) - set(prev["player_name"]))

    return {
        "returning_minutes_pct": round(returning_minutes_pct, 4),
        "returning_scoring_pct": round(returning_scoring_pct, 4),
        "new_player_count": new_player_count,
    }


# ---------------------------------------------------------------------------
# 3) Build portal / continuity features from player stats
# ---------------------------------------------------------------------------


def build_portal_features(
    player_stats: pd.DataFrame,
    seasons: list[int],
) -> pd.DataFrame:
    """Derive per-team roster-continuity features from player-level data.

    This is the **primary, reliable** approach that works for all seasons
    because it is computed from player stats rather than portal databases.

    Parameters
    ----------
    player_stats : pd.DataFrame
        Player-level stats across multiple seasons.  Expected columns
        (flexible naming): player_name/player, team, season/year,
        minutes/mp/min, points/pts/ppg, class_year (optional).
    seasons : list[int]
        Seasons to compute features for.  For each season *s* in this list
        the function looks back at season *s-1* to calculate continuity.

    Returns
    -------
    pd.DataFrame
        One row per team per season with columns:
        - team
        - season
        - roster_continuity (returning minutes %)
        - new_player_pct (freshmen + estimated transfers as % of rotation)
        - estimated_transfer_count
        - experience_turnover (1 - returning_minutes_pct)
    """
    # Normalise column names
    df = player_stats.copy()
    col_map = {
        "player": "player_name",
        "mp": "minutes",
        "min": "minutes",
        "pts": "points",
        "ppg": "points",
        "year": "season",
    }
    df.columns = [col_map.get(c.lower(), c.lower()) for c in df.columns]

    for needed in ("player_name", "team", "season", "minutes", "points"):
        if needed not in df.columns:
            logger.error("player_stats missing required column: %s", needed)
            return pd.DataFrame()

    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["points"] = pd.to_numeric(df["points"], errors="coerce").fillna(0)
    df["player_name"] = df["player_name"].astype(str).str.strip().str.lower()
    df["team"] = df["team"].apply(normalize_team_name)

    has_class = "class_year" in df.columns

    results: list[dict] = []

    for season in seasons:
        curr_season = df[df["season"] == season]
        prev_season = df[df["season"] == season - 1]

        if prev_season.empty:
            logger.debug("No prior season data for %d; skipping continuity", season)
            continue

        teams_this_season = curr_season["team"].unique()

        for team in teams_this_season:
            curr_team = curr_season[curr_season["team"] == team]
            prev_team = prev_season[prev_season["team"] == team]

            continuity = calculate_roster_continuity(curr_team, prev_team)

            # Rotation players = those with meaningful minutes (top 10 or > 10 min/game)
            rotation_threshold = curr_team["minutes"].quantile(0.3) if len(curr_team) > 3 else 0
            rotation = curr_team[curr_team["minutes"] >= rotation_threshold]
            rotation_size = max(len(rotation), 1)

            # Players on current roster who were NOT on the same team's prior roster
            prev_players = set(prev_team["player_name"])
            curr_players = set(curr_team["player_name"])
            new_players = curr_players - prev_players
            new_in_rotation = rotation[rotation["player_name"].isin(new_players)]

            # Freshman detection (if class_year available)
            freshman_count = 0
            if has_class:
                fr_labels = {"fr", "freshman", "fr.", "1"}
                freshman_count = len(
                    rotation[
                        rotation["class_year"].astype(str).str.strip().str.lower().isin(fr_labels)
                    ]
                )

            # Estimated transfers = new players who are NOT freshmen
            estimated_transfer_count = max(len(new_in_rotation) - freshman_count, 0)

            new_player_pct = len(new_in_rotation) / rotation_size

            results.append(
                {
                    "team": team,
                    "season": season,
                    "roster_continuity": continuity["returning_minutes_pct"],
                    "new_player_pct": round(new_player_pct, 4),
                    "estimated_transfer_count": estimated_transfer_count,
                    "experience_turnover": round(1.0 - continuity["returning_minutes_pct"], 4),
                }
            )

    if not results:
        logger.warning("build_portal_features produced no results")
        return pd.DataFrame()

    out = pd.DataFrame(results)
    logger.info(
        "Built portal features: %d rows across %d seasons",
        len(out),
        out["season"].nunique(),
    )
    return out


# ---------------------------------------------------------------------------
# 4) Bulk scrape helper
# ---------------------------------------------------------------------------


def scrape_all_portal_data(seasons: list[int]) -> pd.DataFrame:
    """Scrape transfer portal data for multiple seasons.

    Attempts live scraping first; returns whatever is available.  Seasons
    before 2021 will almost certainly return empty since the NCAA transfer
    portal did not exist in its current form.

    Parameters
    ----------
    seasons : list[int]
        Season years to scrape.

    Returns
    -------
    pd.DataFrame
        Combined portal data for all seasons that returned results.
        Saved to ``data/raw/transfer_portal.parquet``.
    """
    frames: list[pd.DataFrame] = []

    for season in sorted(seasons):
        if season < 2021:
            logger.info(
                "Skipping portal scrape for %d (pre-portal era); "
                "use build_portal_features() for roster continuity instead",
                season,
            )
            continue

        logger.info("Scraping transfer portal for season %d ...", season)
        result = scrape_transfer_portal(season)
        if not result.empty:
            frames.append(result)

    if not frames:
        logger.warning("No portal data scraped for any requested season")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["team"] = combined["team"].apply(normalize_team_name)

    # Persist to parquet
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUTPUT_PATH, index=False)
    logger.info(
        "Saved %d portal rows to %s",
        len(combined),
        OUTPUT_PATH,
    )

    return combined
