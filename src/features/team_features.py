"""
Team-level feature engineering from scraped data.

Builds a unified feature set per team-season by merging team stats,
Torvik metrics, and AP rankings into a single DataFrame.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Sentinel value for unranked teams in AP polls
UNRANKED_FILL = 30

# Project root (two levels up from this file: src/features/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "team_features.parquet"


# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Lowercase, strip whitespace, and remove common suffixes for matching."""
    s = name.strip().lower()
    for suffix in (" st", " st.", " state"):
        if s.endswith(suffix):
            s = s[: -len(suffix)] + " state"
    s = s.replace(".", "").replace("'", "").replace("-", " ")
    return " ".join(s.split())


def _fuzzy_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on_season: str = "season",
    left_team: str = "team",
    right_team: str = "team",
    how: str = "left",
) -> pd.DataFrame:
    """Merge two DataFrames on (team, season) with normalised-name fallback.

    First tries an exact merge on the original team names.  For rows that
    don't match, falls back to joining on normalised names.
    """
    left = left.copy()
    right = right.copy()

    # Attempt 1: exact merge
    merged = left.merge(
        right,
        left_on=[left_team, on_season],
        right_on=[right_team, on_season],
        how=how,
        suffixes=("", "_right"),
    )

    # Identify unmatched rows (pick a column from the right side to check)
    right_cols = [c for c in right.columns if c not in (right_team, on_season)]
    if not right_cols:
        return merged

    indicator_col = right_cols[0]
    if f"{indicator_col}_right" in merged.columns:
        indicator_col = f"{indicator_col}_right"

    unmatched_mask = merged[indicator_col].isna()
    n_unmatched = unmatched_mask.sum()

    if n_unmatched == 0:
        # Drop duplicate team column from right if present
        drop_cols = [c for c in merged.columns if c.endswith("_right")]
        merged.drop(columns=drop_cols, inplace=True, errors="ignore")
        return merged

    logger.info(
        "Exact merge left %d unmatched rows; attempting normalised-name fallback.",
        n_unmatched,
    )

    # Attempt 2: normalised name merge for unmatched rows
    left["_norm_team"] = left[left_team].apply(_normalize_name)
    right["_norm_team"] = right[right_team].apply(_normalize_name)

    merged_fuzzy = left.merge(
        right,
        left_on=["_norm_team", on_season],
        right_on=["_norm_team", on_season],
        how=how,
        suffixes=("", "_right"),
    )

    # Clean up helper columns
    merged_fuzzy.drop(
        columns=["_norm_team"] + [c for c in merged_fuzzy.columns if c.endswith("_right")],
        inplace=True,
        errors="ignore",
    )
    left.drop(columns=["_norm_team"], inplace=True, errors="ignore")
    right.drop(columns=["_norm_team"], inplace=True, errors="ignore")

    return merged_fuzzy


# ---------------------------------------------------------------------------
# Conference strength
# ---------------------------------------------------------------------------


def _compute_conf_strength(torvik: pd.DataFrame) -> pd.DataFrame:
    """Mean adjusted efficiency margin per conference-season."""
    conf_strength = (
        torvik.groupby(["conference", "season"])["adj_em"]
        .mean()
        .reset_index()
        .rename(columns={"adj_em": "conf_strength"})
    )
    return conf_strength


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_team_features(
    team_stats: pd.DataFrame,
    torvik: pd.DataFrame,
    ap_rankings: pd.DataFrame,
) -> pd.DataFrame:
    """Build team-level features from scraped data sources.

    Uses Sports Reference (SR) stats as the primary feature source so that
    all seasons — including the current 2025-26 season (season=2026) — have
    consistent feature coverage.  Torvik data is accepted for backwards-
    compatibility but is NOT used for any features; only SR-derived proxies
    are computed.  This eliminates the train/predict distribution mismatch
    caused by Torvik having no 2026 data.

    SR → model feature mapping
    --------------------------
    adj_eff_margin  ← srs   (SR Simple Rating System, ~same scale as Torvik adj_em)
    adj_off_eff     ← off_rtg  (SR offensive rating per 100 possessions)
    adj_def_eff     ← off_rtg - srs  (derived; adj_em = adj_off - adj_def)
    tempo           ← pace  (SR possessions per 40 min)
    conf_strength   ← sos   (strength of schedule; Torvik conference unavailable in SR)

    Parameters
    ----------
    team_stats : pd.DataFrame
        Per-team-season basic and advanced stats (ppg, rpg, ortg, drtg, etc.).
    torvik : pd.DataFrame
        Accepted for interface compatibility but not used for features.
    ap_rankings : pd.DataFrame
        AP poll data with preseason_rank, final_rank, weeks_ranked.

    Returns
    -------
    pd.DataFrame
        One row per team-season with engineered features, saved to parquet.
    """
    logger.info("Building team features (SR-only mode — no Torvik dependency) ...")

    # ------------------------------------------------------------------
    # 0. Standardize team name columns across datasets
    # ------------------------------------------------------------------
    team_stats = team_stats.copy()
    ap_rankings = ap_rankings.copy()

    # SR data uses "school_name" / "school_normalized"; normalise to "team"
    if "school_normalized" in team_stats.columns and "team" not in team_stats.columns:
        team_stats["team"] = team_stats["school_normalized"]
    elif "school_name" in team_stats.columns and "team" not in team_stats.columns:
        team_stats["team"] = team_stats["school_name"]

    if "school_normalized" in ap_rankings.columns and "team" not in ap_rankings.columns:
        ap_rankings["team"] = ap_rankings["school_normalized"]
    elif "school_name" in ap_rankings.columns and "team" not in ap_rankings.columns:
        ap_rankings["team"] = ap_rankings["school_name"]

    if "team" in team_stats.columns:
        team_stats["team"] = team_stats["team"].str.lower().str.strip()
    if "team" in ap_rankings.columns:
        ap_rankings["team"] = ap_rankings["team"].str.lower().str.strip()

    logger.info(
        "Standardized names: team_stats=%d, ap=%d (Torvik not used)",
        len(team_stats),
        len(ap_rankings),
    )

    # ------------------------------------------------------------------
    # 1. Start with team_stats only (no Torvik merge)
    # ------------------------------------------------------------------
    merged = team_stats.copy()
    logger.info("Base stats: %d rows", len(merged))

    # ------------------------------------------------------------------
    # 2. Merge AP rankings
    # ------------------------------------------------------------------
    merged = _fuzzy_merge(merged, ap_rankings, on_season="season")
    logger.info("After AP merge: %d rows", len(merged))

    # ------------------------------------------------------------------
    # 3. Build feature columns
    # ------------------------------------------------------------------
    features = pd.DataFrame()
    features["team"] = merged["team"]
    features["season"] = merged["season"]

    # Efficiency metrics derived from SR (consistent across all seasons)
    # srs ≈ Torvik adj_em (net rating adjusted for schedule, scale ~-30 to +30)
    srs = pd.to_numeric(merged.get("srs"), errors="coerce")
    off_rtg = pd.to_numeric(merged.get("off_rtg"), errors="coerce")

    features["adj_eff_margin"] = srs
    features["adj_off_eff"] = off_rtg
    # adj_def_eff: lower is better; computed so that adj_off - adj_def = adj_em
    features["adj_def_eff"] = off_rtg - srs

    # Tempo proxy: SR pace (possessions per 40 min)
    features["tempo"] = pd.to_numeric(merged.get("pace"), errors="coerce")

    # Shooting (SR columns, available for all seasons including 2026)
    features["efg_pct"] = pd.to_numeric(merged.get("efg_pct"), errors="coerce")
    features["ts_pct"] = pd.to_numeric(merged.get("ts_pct"), errors="coerce")
    features["three_pt_pct"] = pd.to_numeric(merged.get("fg3_pct"), errors="coerce")

    # Rate stats
    features["three_pt_rate"] = pd.to_numeric(merged.get("fg3a_per_fga_pct"), errors="coerce")
    features["ft_rate"] = pd.to_numeric(merged.get("ft_rate"), errors="coerce")
    features["tov_rate"] = pd.to_numeric(merged.get("tov_pct"), errors="coerce")
    features["oreb_rate"] = pd.to_numeric(merged.get("orb_pct"), errors="coerce")
    features["dreb_rate"] = pd.to_numeric(merged.get("trb_pct"), errors="coerce")

    # Strength of schedule (SR sos)
    features["sos"] = pd.to_numeric(merged.get("sos"), errors="coerce")

    # quad1_wins not available from SR; fill with 0 (dropped by zero-variance filter anyway)
    features["quad1_wins"] = 0.0

    # Conference strength proxy: use sos (correlated with conference quality)
    # Torvik's conf-level adj_em is not available in SR; SOS is the best SR equivalent.
    features["conf_strength"] = pd.to_numeric(merged.get("sos"), errors="coerce")

    # Win/loss record (additional SR signal)
    features["win_loss_pct"] = pd.to_numeric(merged.get("win_loss_pct"), errors="coerce")
    features["wins"] = pd.to_numeric(merged.get("wins"), errors="coerce")

    # Conference regular season win rate (stronger quality signal than overall W%, avoids cupcake inflation)
    wins_conf = pd.to_numeric(merged.get("wins_conf"), errors="coerce")
    losses_conf = pd.to_numeric(merged.get("losses_conf"), errors="coerce")
    conf_games = wins_conf + losses_conf
    features["conf_win_pct"] = wins_conf / conf_games.replace(0, float("nan"))

    # AP rankings — fill unranked with UNRANKED_FILL
    features["ap_final_rank"] = merged.get("final_rank")
    features["ap_preseason_rank"] = merged.get("preseason_rank")
    features["ap_final_rank"] = features["ap_final_rank"].fillna(UNRANKED_FILL)
    features["ap_preseason_rank"] = features["ap_preseason_rank"].fillna(UNRANKED_FILL)
    features["ap_rank_trajectory"] = features["ap_preseason_rank"] - features["ap_final_rank"]
    features["weeks_ranked"] = merged.get("weeks_ranked", pd.Series(dtype="float64")).fillna(0)

    # ------------------------------------------------------------------
    # 5. Handle remaining missing values with sensible defaults
    # ------------------------------------------------------------------
    numeric_cols = features.select_dtypes(include="number").columns
    for col in numeric_cols:
        n_missing = features[col].isna().sum()
        if n_missing > 0:
            median_val = features[col].median()
            features[col] = features[col].fillna(median_val)
            logger.info(
                "Filled %d missing values in '%s' with median %.4f",
                n_missing,
                col,
                median_val if pd.notna(median_val) else 0.0,
            )

    # ------------------------------------------------------------------
    # 6. Set index and save
    # ------------------------------------------------------------------
    features = features.set_index(["team", "season"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUTPUT_PATH)
    logger.info("Saved team features to %s  (%d rows)", OUTPUT_PATH, len(features))

    return features
