"""
Scraper for expert bracket picks from ESPN, CBS Sports, and Yahoo Sports.

Expert bracket picks are typically embedded in editorial articles with
unpredictable HTML structures. This module attempts scraping known
bracketology pages but primarily relies on a manual JSON fallback for
reliable data ingestion.

Exports picks to both Parquet (flat, one row per game slot per expert)
and JSON (nested, grouped by expert and round).

Usage:
    from src.scraping.expert_picks import scrape_all_expert_picks

    picks = scrape_all_expert_picks(season=2026)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.scraping.sports_ref import normalize_team_name, team_name_to_slug
from src.scraping.utils import CachedScraper, PlaywrightScraper, parse_html

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PREDICTIONS_DIR = PROJECT_ROOT / "data" / "predictions"
DEFAULT_MANUAL_PICKS_PATH = DATA_PREDICTIONS_DIR / "expert_picks_manual.json"

# ---------------------------------------------------------------------------
# Expert Personas
# ---------------------------------------------------------------------------

EXPERT_PERSONAS: dict[str, dict[str, str]] = {
    "joe_lunardi_espn": {
        "name": "Joe Lunardi",
        "source": "espn",
        "url": "https://www.espn.com/mens-college-basketball/bracketology",
        "description": "ESPN's bracketology pioneer; trusts seeds, favors blue bloods",
    },
    "jay_bilas_espn": {
        "name": "Jay Bilas",
        "source": "espn",
        "url": "https://www.espn.com/mens-college-basketball/story/_/id/bracket-predictions",
        "description": "ESPN analyst; values athleticism, picks upsets where talent > seed",
    },
    "gary_parrish_cbs": {
        "name": "Gary Parrish",
        "source": "cbs",
        "url": "https://www.cbssports.com/college-basketball/bracketology/",
        "description": "CBS Sports; skeptical of mid-majors, heavy on Quad 1 records",
    },
    "matt_norlander_cbs": {
        "name": "Matt Norlander",
        "source": "cbs",
        "url": "https://www.cbssports.com/college-basketball/news/march-madness-bracket-predictions/",
        "description": "CBS Sports; values coaching experience, systematic approach",
    },
    "yahoo_expert": {
        "name": "Yahoo Expert",
        "source": "yahoo",
        "url": "https://sports.yahoo.com/college-basketball/bracket/",
        "description": "Yahoo Sports; contrarian picks, more upsets",
    },
}

# ---------------------------------------------------------------------------
# Display-name overrides for expert sources
# ---------------------------------------------------------------------------
# Expert articles use informal names that differ from Sports Reference slugs.
# These supplement the overrides in sports_ref.py.

EXPERT_NAME_OVERRIDES: dict[str, str] = {
    # Common expert shorthand -> bracket_predictions.json slug format
    "UConn": "connecticut",
    "uconn": "connecticut",
    "UCONN": "connecticut",
    "St. John's": "st johns ny",
    "St Johns": "st johns ny",
    "st. john's": "st johns ny",
    "Saint John's": "st johns ny",
    "BYU": "brigham young",
    "byu": "brigham young",
    "Miami (FL)": "miami fl",
    "Miami FL": "miami fl",
    "miami (fl)": "miami fl",
    "Miami": "miami fl",
    "Miami (OH)": "miami (ohio)",
    "miami (oh)": "miami (ohio)",
    "SMU": "smu",
    "VCU": "vcu",
    "UCF": "ucf",
    "LSU": "louisiana state",
    "lsu": "louisiana state",
    "USC": "southern california",
    "UNC": "north carolina",
    "unc": "north carolina",
    "NC State": "north carolina state",
    "nc state": "north carolina state",
    "FAU": "florida atlantic",
    "FDU": "fairleigh dickinson",
    "UAB": "alabama birmingham",
    "Ole Miss": "mississippi",
    "ole miss": "mississippi",
    "Pitt": "pittsburgh",
    "pitt": "pittsburgh",
    "Michigan St.": "michigan state",
    "Michigan St": "michigan state",
    "Ohio St.": "ohio state",
    "Ohio St": "ohio state",
    "Iowa St.": "iowa state",
    "Iowa St": "iowa state",
    "Penn St.": "penn state",
    "Penn St": "penn state",
    "San Diego St.": "san diego state",
    "San Diego St": "san diego state",
    "Boise St.": "boise state",
    "Boise St": "boise state",
    "Kansas St.": "kansas state",
    "Kansas St": "kansas state",
    "Colorado St.": "colorado state",
    "Colorado St": "colorado state",
    "Mississippi St.": "mississippi state",
    "Mississippi St": "mississippi state",
    "Arizona St.": "arizona state",
    "Arizona St": "arizona state",
    "Saint Mary's": "saint marys",
    "St. Mary's": "saint marys",
    "saint mary's": "saint marys",
    "Saint Marys": "saint marys",
    "Texas A&M": "texas a&m",
    "texas a&m": "texas a&m",
    "TAMU": "texas a&m",
    "TCU": "tcu",
    "tcu": "tcu",
    "UCLA": "ucla",
    "ucla": "ucla",
    "McNeese": "mcneese",
    "UNLV": "nevada las vegas",
    "Long Island": "long island",
    "LIU": "long island",
}

# Round ordering for Parquet export
ROUND_ORDER = ["R64", "R32", "S16", "E8", "FF", "Championship"]


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


def normalize_expert_pick(name: str) -> str:
    """Convert an expert-article display name to a slug matching bracket_predictions.json.

    The bracket_predictions.json uses space-separated lowercase slugs
    (e.g., "st johns ny", "brigham young", "miami fl", "iowa state").

    This function first checks expert-specific overrides, then falls back
    to the Sports Reference normalize + slug pipeline, and finally applies
    a simple lowering/cleaning pass.

    Args:
        name: Raw team name as it appears in an expert article or manual JSON.

    Returns:
        Lowercase slug matching bracket_predictions.json format.
    """
    if not name or not isinstance(name, str):
        return ""

    name = name.strip()

    # 1. Check expert-specific overrides first (case-sensitive, then insensitive)
    if name in EXPERT_NAME_OVERRIDES:
        return EXPERT_NAME_OVERRIDES[name]

    name_lower = name.lower().strip()
    if name_lower in EXPERT_NAME_OVERRIDES:
        return EXPERT_NAME_OVERRIDES[name_lower]

    # 2. Try the sports_ref normalize pipeline
    #    team_name_to_slug returns hyphenated slugs; bracket_predictions.json
    #    uses space-separated slugs, so convert hyphens to spaces.
    try:
        sr_slug = team_name_to_slug(name)
        # Convert SR hyphenated slug to bracket_predictions format
        return sr_slug.replace("-", " ")
    except Exception:
        pass

    # 3. Fallback: simple lowercase cleaning
    cleaned = normalize_team_name(name)
    return cleaned


# ---------------------------------------------------------------------------
# ESPN scraper
# ---------------------------------------------------------------------------


def scrape_espn_picks(season: int = 2026) -> list[dict]:
    """Attempt to scrape expert bracket picks from ESPN.

    ESPN bracket picks are typically embedded in editorial articles with
    unpredictable HTML structures. This function attempts to parse known
    bracketology pages but will return an empty list if the page structure
    doesn't match expectations.

    Args:
        season: Tournament season year.

    Returns:
        List of pick dicts with keys: expert_id, expert_name, source,
        season, round, region, game_slot, winner, scraped_at.
        Returns empty list if scraping fails.
    """
    picks: list[dict] = []
    scraped_at = datetime.now(UTC).isoformat()

    for expert_id in ["joe_lunardi_espn", "jay_bilas_espn"]:
        persona = EXPERT_PERSONAS[expert_id]
        url = persona["url"]

        logger.info("Attempting to scrape ESPN picks for %s from %s", persona["name"], url)

        try:
            scraper = PlaywrightScraper()
            try:
                html = scraper.get(url, wait_ms=5000)
                soup = parse_html(html)

                # ESPN bracket pages have inconsistent structure.
                # Look for common patterns: tables, bracket divs, pick lists.
                bracket_tables = soup.select("table.bracket, .bracket-table, .bracketology")
                if not bracket_tables:
                    logger.warning(
                        "No bracket structure found on ESPN page for %s. "
                        "Page structure may have changed. Use manual picks fallback.",
                        persona["name"],
                    )
                    continue

                # Attempt to parse bracket table rows
                for table in bracket_tables:
                    rows = table.select("tr")
                    for row in rows:
                        cells = row.select("td")
                        if len(cells) >= 2:
                            # Heuristic: look for team names in cells
                            team_text = cells[0].get_text(strip=True)
                            if team_text:
                                winner = normalize_expert_pick(team_text)
                                if winner:
                                    picks.append(
                                        {
                                            "expert_id": expert_id,
                                            "expert_name": persona["name"],
                                            "source": "espn",
                                            "season": season,
                                            "round": "unknown",
                                            "region": "unknown",
                                            "game_slot": "unknown",
                                            "winner": winner,
                                            "scraped_at": scraped_at,
                                        }
                                    )

            finally:
                scraper.close()

        except Exception as exc:
            logger.warning(
                "Failed to scrape ESPN picks for %s: %s. Use manual picks fallback.",
                persona["name"],
                exc,
            )

    if picks:
        logger.info("Scraped %d raw ESPN picks (may need manual verification)", len(picks))
    else:
        logger.info("No ESPN picks scraped. Use --manual-picks for reliable data.")

    return picks


# ---------------------------------------------------------------------------
# CBS Sports scraper
# ---------------------------------------------------------------------------


def scrape_cbs_picks(season: int = 2026) -> list[dict]:
    """Attempt to scrape expert bracket picks from CBS Sports.

    CBS bracket predictions are typically in article format with embedded
    bracket images or interactive widgets. This scraper attempts to find
    structured pick data but will return an empty list if the page
    structure doesn't match expectations.

    Args:
        season: Tournament season year.

    Returns:
        List of pick dicts. Returns empty list if scraping fails.
    """
    picks: list[dict] = []
    scraped_at = datetime.now(UTC).isoformat()

    scraper = CachedScraper(rate_limit=3.0)
    try:
        for expert_id in ["gary_parrish_cbs", "matt_norlander_cbs"]:
            persona = EXPERT_PERSONAS[expert_id]
            url = persona["url"]

            logger.info("Attempting to scrape CBS picks for %s from %s", persona["name"], url)

            try:
                html = scraper.get(url)
                soup = parse_html(html)

                # CBS bracket pages use various structures.
                # Look for bracket containers, pick lists, or article sections.
                bracket_sections = soup.select(
                    ".bracket-container, .bracket-picks, "
                    ".article-body .bracket, [data-bracket]"
                )
                if not bracket_sections:
                    logger.warning(
                        "No bracket structure found on CBS page for %s. "
                        "Page structure may have changed. Use manual picks fallback.",
                        persona["name"],
                    )
                    continue

                # Attempt to parse any structured pick data found
                for section in bracket_sections:
                    team_elements = section.select(
                        ".team-name, .pick-team, .bracket-team, span.team"
                    )
                    for elem in team_elements:
                        team_text = elem.get_text(strip=True)
                        if team_text:
                            winner = normalize_expert_pick(team_text)
                            if winner:
                                picks.append(
                                    {
                                        "expert_id": expert_id,
                                        "expert_name": persona["name"],
                                        "source": "cbs",
                                        "season": season,
                                        "round": "unknown",
                                        "region": "unknown",
                                        "game_slot": "unknown",
                                        "winner": winner,
                                        "scraped_at": scraped_at,
                                    }
                                )

            except Exception as exc:
                logger.warning(
                    "Failed to scrape CBS picks for %s: %s. Use manual picks fallback.",
                    persona["name"],
                    exc,
                )

    finally:
        scraper.close()

    if picks:
        logger.info("Scraped %d raw CBS picks (may need manual verification)", len(picks))
    else:
        logger.info("No CBS picks scraped. Use --manual-picks for reliable data.")

    return picks


# ---------------------------------------------------------------------------
# Yahoo Sports scraper
# ---------------------------------------------------------------------------


def scrape_yahoo_picks(season: int = 2026) -> list[dict]:
    """Attempt to scrape expert bracket picks from Yahoo Sports.

    Tries CachedScraper first (faster), falls back to PlaywrightScraper
    for JS-rendered content.

    Args:
        season: Tournament season year.

    Returns:
        List of pick dicts. Returns empty list if scraping fails.
    """
    picks: list[dict] = []
    scraped_at = datetime.now(UTC).isoformat()
    expert_id = "yahoo_expert"
    persona = EXPERT_PERSONAS[expert_id]
    url = persona["url"]

    logger.info("Attempting to scrape Yahoo picks from %s", url)

    html = None

    # Try CachedScraper first (no JS rendering)
    scraper = CachedScraper(rate_limit=3.0)
    try:
        html = scraper.get(url)
        soup = parse_html(html)

        # Check if we got meaningful content (not a JS-only shell)
        bracket_content = soup.select(
            ".bracket, .picks-container, [data-bracket], "
            ".tournament-bracket"
        )
        if not bracket_content:
            logger.info("Yahoo page appears JS-rendered, trying Playwright fallback")
            html = None
    except Exception as exc:
        logger.warning("CachedScraper failed for Yahoo: %s", exc)
        html = None
    finally:
        scraper.close()

    # Playwright fallback for JS-rendered pages
    if html is None:
        pw_scraper = PlaywrightScraper()
        try:
            html = pw_scraper.get(url, wait_ms=5000)
        except Exception as exc:
            logger.warning(
                "Playwright also failed for Yahoo: %s. Use manual picks fallback.", exc
            )
            return []
        finally:
            pw_scraper.close()

    # Parse whatever HTML we got
    try:
        soup = parse_html(html)
        bracket_sections = soup.select(
            ".bracket, .picks-container, .tournament-bracket, "
            "[data-bracket], .matchup"
        )

        if not bracket_sections:
            logger.warning(
                "No bracket structure found on Yahoo page. "
                "Use manual picks fallback."
            )
            return []

        for section in bracket_sections:
            team_elements = section.select(
                ".team-name, .pick-team, .bracket-team, span.team"
            )
            for elem in team_elements:
                team_text = elem.get_text(strip=True)
                if team_text:
                    winner = normalize_expert_pick(team_text)
                    if winner:
                        picks.append(
                            {
                                "expert_id": expert_id,
                                "expert_name": persona["name"],
                                "source": "yahoo",
                                "season": season,
                                "round": "unknown",
                                "region": "unknown",
                                "game_slot": "unknown",
                                "winner": winner,
                                "scraped_at": scraped_at,
                            }
                        )

    except Exception as exc:
        logger.warning("Failed to parse Yahoo HTML: %s. Use manual picks fallback.", exc)

    if picks:
        logger.info("Scraped %d raw Yahoo picks (may need manual verification)", len(picks))
    else:
        logger.info("No Yahoo picks scraped. Use --manual-picks for reliable data.")

    return picks


# ---------------------------------------------------------------------------
# Manual picks loader (primary reliable path)
# ---------------------------------------------------------------------------


def load_manual_picks(path: Path, season: int = 2026) -> dict:
    """Load hand-entered expert picks from a JSON file.

    This is the primary reliable path for ingesting expert picks, since
    expert articles have unpredictable HTML structures.

    The JSON file should follow the schema defined in
    data/predictions/expert_picks_manual.json.

    Args:
        path: Path to the manual picks JSON file.
        season: Tournament season year (used for validation).

    Returns:
        Dict with "metadata" and "experts" keys, matching the export schema.

    Raises:
        FileNotFoundError: If the manual picks file doesn't exist.
        ValueError: If the file is malformed or fails validation.
    """
    if not path.exists():
        raise FileNotFoundError(f"Manual picks file not found: {path}")

    logger.info("Loading manual picks from %s", path)

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # Validate top-level structure
    if "experts" not in raw:
        raise ValueError(
            f"Manual picks file must have an 'experts' key. Found: {list(raw.keys())}"
        )

    metadata = raw.get("metadata", {})
    file_season = metadata.get("season", season)
    if file_season != season:
        logger.warning(
            "Manual picks file is for season %d but requested season is %d",
            file_season,
            season,
        )

    # Normalize all team names in picks
    experts = {}
    for expert_id, expert_data in raw["experts"].items():
        if expert_id not in EXPERT_PERSONAS:
            logger.warning("Unknown expert_id '%s' in manual picks — skipping", expert_id)
            continue

        normalized = {
            "expert_name": expert_data.get(
                "expert_name", EXPERT_PERSONAS[expert_id]["name"]
            ),
            "source": expert_data.get(
                "source", EXPERT_PERSONAS[expert_id]["source"]
            ),
            "champion": normalize_expert_pick(expert_data.get("champion", "")),
            "final_four": [
                normalize_expert_pick(t) for t in expert_data.get("final_four", [])
            ],
            "elite_8": [
                normalize_expert_pick(t) for t in expert_data.get("elite_8", [])
            ],
            "picks_by_round": {},
        }

        picks_by_round = expert_data.get("picks_by_round", {})
        for round_name, round_picks in picks_by_round.items():
            normalized["picks_by_round"][round_name] = {
                slot: normalize_expert_pick(winner)
                for slot, winner in round_picks.items()
            }

        experts[expert_id] = normalized

    result = {
        "metadata": {
            "season": season,
            "expert_count": len(experts),
            "scraped_at": datetime.now(UTC).isoformat(),
            "sources": sorted({e["source"] for e in experts.values()}),
            "load_method": "manual",
        },
        "experts": experts,
    }

    logger.info(
        "Loaded manual picks for %d experts: %s",
        len(experts),
        ", ".join(experts.keys()),
    )

    return result


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------


def _picks_to_parquet_rows(picks: dict, season: int) -> list[dict]:
    """Flatten the nested picks dict into Parquet-ready rows.

    One row per game slot per expert.
    """
    rows = []
    scraped_at = picks.get("metadata", {}).get(
        "scraped_at", datetime.now(UTC).isoformat()
    )

    for expert_id, expert_data in picks.get("experts", {}).items():
        expert_name = expert_data.get("expert_name", "")
        source = expert_data.get("source", "")

        for round_name, round_picks in expert_data.get("picks_by_round", {}).items():
            for game_slot, winner in round_picks.items():
                # Determine region from game_slot
                region = "national"
                for r in ["East", "West", "South", "Midwest"]:
                    if game_slot.startswith(r):
                        region = r
                        break

                rows.append(
                    {
                        "expert_name": expert_name,
                        "expert_id": expert_id,
                        "source": source,
                        "season": season,
                        "round": round_name,
                        "region": region,
                        "game_slot": game_slot,
                        "winner": winner,
                        "scraped_at": scraped_at,
                    }
                )

    return rows


def export_expert_picks(picks: dict, season: int) -> Path:
    """Write expert picks to JSON and Parquet files.

    Args:
        picks: Nested picks dict with "metadata" and "experts" keys.
        season: Tournament season year.

    Returns:
        Path to the exported JSON file.
    """
    DATA_PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # JSON export
    json_path = DATA_PREDICTIONS_DIR / "expert_picks.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(picks, f, indent=2, ensure_ascii=False)
    logger.info("Exported expert picks JSON to %s", json_path)

    # Parquet export
    rows = _picks_to_parquet_rows(picks, season)
    if rows:
        df = pd.DataFrame(rows)
        # Enforce column order
        cols = [
            "expert_name",
            "expert_id",
            "source",
            "season",
            "round",
            "region",
            "game_slot",
            "winner",
            "scraped_at",
        ]
        df = df[cols]
        parquet_path = DATA_PREDICTIONS_DIR / "expert_picks.parquet"
        df.to_parquet(parquet_path, index=False)
        logger.info(
            "Exported expert picks Parquet to %s (%d rows)", parquet_path, len(df)
        )
    else:
        logger.warning("No pick rows to export to Parquet")

    return json_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def scrape_all_expert_picks(
    season: int = 2026,
    manual_picks_path: Path | None = None,
    sources: list[str] | None = None,
) -> dict:
    """Orchestrate expert pick collection from all sources with fallback.

    Strategy:
    1. If manual_picks_path is provided and exists, load it as the primary source.
    2. Otherwise, attempt to scrape from enabled sources (espn, cbs, yahoo).
    3. Scraped picks are best-effort and likely incomplete; manual JSON is
       the recommended path for reliable bracket data.

    Args:
        season: Tournament season year.
        manual_picks_path: Path to manual picks JSON. If None, uses default location.
        sources: List of sources to scrape ("espn", "cbs", "yahoo"). None = all.

    Returns:
        Nested dict with "metadata" and "experts" keys.
    """
    enabled_sources = set(sources or ["espn", "cbs", "yahoo"])

    # Try manual picks first (primary reliable path)
    manual_path = manual_picks_path or DEFAULT_MANUAL_PICKS_PATH
    if manual_path.exists():
        logger.info("Found manual picks file at %s — using as primary source", manual_path)
        try:
            picks = load_manual_picks(manual_path, season=season)
            export_expert_picks(picks, season)
            return picks
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to load manual picks: %s. Falling back to scraping.", exc)

    # Fallback: attempt scraping
    logger.info("No manual picks available. Attempting to scrape from: %s", enabled_sources)

    all_scraped: list[dict] = []

    if "espn" in enabled_sources:
        all_scraped.extend(scrape_espn_picks(season))

    if "cbs" in enabled_sources:
        all_scraped.extend(scrape_cbs_picks(season))

    if "yahoo" in enabled_sources:
        all_scraped.extend(scrape_yahoo_picks(season))

    if not all_scraped:
        logger.warning(
            "No picks scraped from any source. Create a manual picks file at %s "
            "or provide one via --manual-picks.",
            DEFAULT_MANUAL_PICKS_PATH,
        )
        return {
            "metadata": {
                "season": season,
                "expert_count": 0,
                "scraped_at": datetime.now(UTC).isoformat(),
                "sources": [],
                "load_method": "scrape_failed",
            },
            "experts": {},
        }

    # Assemble scraped picks into the export schema.
    # Scraped picks have "unknown" game_slot/round values, so they're
    # partial and need manual verification.
    experts: dict[str, dict] = {}
    scraped_at = datetime.now(UTC).isoformat()

    for pick in all_scraped:
        eid = pick["expert_id"]
        if eid not in experts:
            experts[eid] = {
                "expert_name": pick["expert_name"],
                "source": pick["source"],
                "champion": "",
                "final_four": [],
                "elite_8": [],
                "picks_by_round": {},
            }

        round_name = pick.get("round", "unknown")
        slot = pick.get("game_slot", "unknown")
        if round_name not in experts[eid]["picks_by_round"]:
            experts[eid]["picks_by_round"][round_name] = {}
        experts[eid]["picks_by_round"][round_name][slot] = pick["winner"]

    result = {
        "metadata": {
            "season": season,
            "expert_count": len(experts),
            "scraped_at": scraped_at,
            "sources": sorted(enabled_sources & {e["source"] for e in experts.values()}),
            "load_method": "scraped",
            "warning": "Scraped picks may be incomplete. Verify against manual picks.",
        },
        "experts": experts,
    }

    export_expert_picks(result, season)
    return result
