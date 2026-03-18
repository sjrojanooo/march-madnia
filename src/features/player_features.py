"""Compute X-factor player features from rotation analysis.

For each team-season, analyzes the top 7-8 rotation players and derives
features that capture star power, depth, experience, balance, and defensive
anchoring.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROTATION_SIZE = 8

CLASS_YEAR_MAP: dict[str, int] = {
    "fr": 1,
    "freshman": 1,
    "so": 2,
    "sophomore": 2,
    "jr": 3,
    "junior": 3,
    "sr": 4,
    "senior": 4,
    "grad": 4,
    "graduate": 4,
    "gr": 4,
    "rs fr": 1,
    "rs so": 2,
    "rs jr": 3,
    "rs sr": 4,
}

OUTPUT_PATH = Path("data/processed/player_features.parquet")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _map_class_year(raw: str | float | None) -> int:
    """Convert a class-year string to a numeric value (1-4).

    Returns 2 (sophomore-level) as a fallback when the value is missing or
    unrecognised so that missing data does not dominate the experience score.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return 2
    key = str(raw).strip().lower()
    return CLASS_YEAR_MAP.get(key, 2)


def _estimate_per(row: pd.Series) -> float:
    """Rough PER estimate from box-score stats when the real value is missing.

    Uses a simplified linear combination that correlates with PER.  This is
    intentionally conservative -- it will never be as accurate as the real
    metric, but it keeps the pipeline running when advanced stats are absent.
    """
    pts = row.get("pts", 0) or 0
    reb = row.get("reb", 0) or 0
    ast = row.get("ast", 0) or 0
    stl = row.get("stl", 0) or 0
    blk = row.get("blk", 0) or 0
    tov = row.get("tov", 0) or 0
    mp = row.get("mp", 1) or 1  # avoid division by zero
    per_approx = (pts + reb + ast + stl + blk - tov) / max(mp, 1) * 40
    # Clamp to a reasonable range
    return float(np.clip(per_approx, 0, 40))


def _estimate_bpm(row: pd.Series) -> float:
    """Rough BPM estimate from box-score stats when the real value is missing."""
    pts = row.get("pts", 0) or 0
    reb = row.get("reb", 0) or 0
    ast = row.get("ast", 0) or 0
    stl = row.get("stl", 0) or 0
    blk = row.get("blk", 0) or 0
    tov = row.get("tov", 0) or 0
    mp = row.get("mp", 1) or 1
    # Simple per-minute composite scaled to approximate BPM range
    bpm_approx = ((pts + reb + ast + stl + blk - tov) / max(mp, 1) * 40 - 15) / 3
    return float(np.clip(bpm_approx, -10, 15))


def _fill_advanced_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing PER and BPM with estimates derived from basic stats."""
    df = df.copy()

    if "per" not in df.columns:
        df["per"] = np.nan
    if "bpm" not in df.columns:
        df["bpm"] = np.nan
    if "usg_pct" not in df.columns:
        df["usg_pct"] = np.nan

    mask_per = df["per"].isna()
    if mask_per.any():
        logger.info("Estimating PER for %d rows with missing values.", mask_per.sum())
        df.loc[mask_per, "per"] = df.loc[mask_per].apply(_estimate_per, axis=1)

    mask_bpm = df["bpm"].isna()
    if mask_bpm.any():
        logger.info("Estimating BPM for %d rows with missing values.", mask_bpm.sum())
        df.loc[mask_bpm, "bpm"] = df.loc[mask_bpm].apply(_estimate_bpm, axis=1)

    # Default usage rate to league-average 20% when missing
    df["usg_pct"] = df["usg_pct"].fillna(20.0)

    return df


def _min_max_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize a Series to [0, 1]. Returns 0.5 for constant series."""
    smin, smax = series.min(), series.max()
    if smax == smin:
        return pd.Series(0.5, index=series.index)
    return (series - smin) / (smax - smin)


# ---------------------------------------------------------------------------
# Per-group feature computation
# ---------------------------------------------------------------------------


def _compute_group_features(group: pd.DataFrame) -> pd.Series:
    """Compute all player-derived features for a single team-season group.

    Expects ``group`` to already be sorted by minutes (descending) and trimmed
    to the top ``ROTATION_SIZE`` players.
    """
    # --- Star power: best player's PER * usage / 100 ---
    best_idx = group["per"].idxmax()
    star_power = group.loc[best_idx, "per"] * group.loc[best_idx, "usg_pct"] / 100

    # --- Top-3 composite: average PER of top 3 scorers ---
    top3 = group.nlargest(min(3, len(group)), "pts")
    top3_composite = top3["per"].mean()

    # --- Rotation depth: StdDev of minutes among rotation ---
    rotation_depth = group["mp"].std(ddof=0) if len(group) > 1 else 0.0

    # --- Experience score: minutes-weighted class year ---
    class_numeric = group["class_year"].map(_map_class_year)
    total_mp = group["mp"].sum()
    if total_mp > 0:
        experience_score = (class_numeric * group["mp"]).sum() / total_mp
    else:
        experience_score = class_numeric.mean()

    # --- Tournament experience proxy: count of JR+ in rotation ---
    tournament_exp = int((class_numeric >= 3).sum())

    # --- Scoring balance: HHI of scoring shares ---
    team_pts = group["pts"].sum()
    if team_pts > 0:
        shares = group["pts"] / team_pts
        scoring_balance = (shares**2).sum()
    else:
        scoring_balance = 1.0  # degenerate case

    # --- Defensive anchor: best individual BPM ---
    defensive_anchor = group["bpm"].max()

    # --- Star player individual stats ---
    # Top scorer's raw PPG
    top_scorer_idx = group["pts"].idxmax()
    star_ppg = group.loc[top_scorer_idx, "pts"]

    # Star's share of total team scoring
    team_pts = group["pts"].sum()
    star_contribution_pct = star_ppg / team_pts if team_pts > 0 else 0.0

    # BPM gap between #1 and #2 player (star irreplaceability)
    bpm_sorted = group["bpm"].nlargest(2).values
    top2_bpm_gap = float(bpm_sorted[0] - bpm_sorted[1]) if len(bpm_sorted) >= 2 else 0.0

    return pd.Series(
        {
            "star_power": star_power,
            "top3_composite": top3_composite,
            "rotation_depth": rotation_depth,
            "experience_score": experience_score,
            "tournament_exp": tournament_exp,
            "scoring_balance": scoring_balance,
            "defensive_anchor": defensive_anchor,
            "star_ppg": star_ppg,
            "star_contribution_pct": star_contribution_pct,
            "top2_bpm_gap": top2_bpm_gap,
        }
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_player_features(player_stats: pd.DataFrame) -> pd.DataFrame:
    """Build X-factor player features for every team-season.

    Parameters
    ----------
    player_stats : pd.DataFrame
        Per-player season stats.  Expected columns (at minimum):
        ``player, team, season, pts, reb, ast, stl, blk, tov, mp,
        class_year``.  Advanced columns ``per, usg_pct, bpm`` are used
        when present; otherwise they are estimated from basic stats.

    Returns
    -------
    pd.DataFrame
        One row per (team, season) with the following features:
        ``star_power, top3_composite, rotation_depth, experience_score,
        tournament_exp, scoring_balance, defensive_anchor, xfactor_score``.
    """
    logger.info("Building player features from %d player-season rows.", len(player_stats))

    df = player_stats.copy()

    # Ensure required columns exist with safe defaults
    for col in ("pts", "reb", "ast", "stl", "blk", "tov", "mp"):
        if col not in df.columns:
            logger.warning("Column '%s' missing -- filling with 0.", col)
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "class_year" not in df.columns:
        logger.warning("Column 'class_year' missing -- defaulting to 'SO'.")
        df["class_year"] = "SO"

    df = _fill_advanced_stats(df)

    # Keep only top ROTATION_SIZE players per team-season by minutes
    df = df.sort_values("mp", ascending=False)
    rotation = df.groupby(["team", "season"], group_keys=False).head(ROTATION_SIZE)
    logger.info(
        "Retained %d rotation players across %d team-seasons.",
        len(rotation),
        rotation.groupby(["team", "season"]).ngroups,
    )

    # Compute per-group features
    features = (
        rotation.groupby(["team", "season"], group_keys=False)
        .apply(_compute_group_features)
        .reset_index()
    )

    # --- X-factor composite score ---
    # Depth: lower std-dev is better, so invert
    depth_inv = -features["rotation_depth"]
    # Balance: lower HHI is better, so invert
    balance_inv = -features["scoring_balance"]

    features["xfactor_score"] = (
        _min_max_normalize(features["star_power"])
        + _min_max_normalize(depth_inv)
        + _min_max_normalize(features["experience_score"])
        + _min_max_normalize(balance_inv)
        + _min_max_normalize(features["defensive_anchor"])
        + _min_max_normalize(features["star_ppg"])
    )

    logger.info(
        "X-factor score range: %.3f - %.3f",
        features["xfactor_score"].min(),
        features["xfactor_score"].max(),
    )

    # Persist
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUTPUT_PATH, index=False)
    logger.info("Saved player features to %s", OUTPUT_PATH)

    return features
