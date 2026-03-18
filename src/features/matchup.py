"""Head-to-head matchup feature generation for model training and prediction.

Each row represents one game between two teams, with differential features
(team_a - team_b) as the primary signals and raw prefixed features for
non-linear tree-model interactions.

Usage:
    from src.features.matchup import build_training_matchups, build_prediction_matchup

    training_df = build_training_matchups(
        team_features, player_features, portal_features,
        momentum_features, tournament_results,
    )

    pred_row = build_prediction_matchup(team_a_dict, team_b_dict)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "matchup_training.parquet"

# ---------------------------------------------------------------------------
# Tournament nickname -> full team name normalization
# ---------------------------------------------------------------------------
# Tournament results store abbreviated/nickname names; team_features uses full
# names from Torvik/SR. This map bridges the gap so joins succeed.

TOURNEY_NAME_MAP: dict[str, str] = {
    "uconn": "connecticut",
    "unc": "north carolina",
    "unc greensboro": "north carolina greensboro",
    "unc asheville": "north carolina asheville",
    "unc wilmington": "north carolina wilmington",
    "lsu": "louisiana state",
    "usc": "southern california",
    "vcu": "virginia commonwealth",
    "byu": "brigham young",
    "tcu": "texas christian",
    "smu": "southern methodist",
    "ucf": "central florida",
    "unlv": "nevada las vegas",
    "ole miss": "mississippi",
    "pitt": "pittsburgh",
    "saint marys": "saint marys ca",
    "mcneese": "mcneese state",
    "fdu": "fairleigh dickinson",
    "omaha": "nebraska omaha",
    "louisiana": "louisiana lafayette",
    "nc state": "north carolina state",
    "texas a&m": "texas am",
    "texas a&m-corpus christi": "texas am corpus christi",
    "siu-edwardsville": "southern illinois edwardsville",
    "ucsb": "uc santa barbara",
    "ucsd": "uc san diego",
    "uci": "uc irvine",
    "fau": "florida atlantic",
    "utep": "texas el paso",
    "utsa": "texas san antonio",
    "liu": "long island university",
    "st. john's": "st johns ny",
    "miami fl": "miami fl",
    "miami oh": "miami oh",
}


def _normalize_tourney_name(name: str) -> str:
    """Map tournament nickname to full team name used in features."""
    n = str(name).lower().strip()
    return TOURNEY_NAME_MAP.get(n, n)

# ---------------------------------------------------------------------------
# Differential feature definitions
# ---------------------------------------------------------------------------

# Each entry maps the output column name to the source column expected in the
# merged per-team feature set.  All differentials are computed as (A - B).
DIFF_FEATURES: dict[str, str] = {
    "eff_margin_diff": "adj_eff_margin",
    "off_eff_diff": "adj_off_eff",
    "def_eff_diff": "adj_def_eff",
    "xfactor_diff": "xfactor_score",
    "portal_stability_diff": "roster_continuity",
    "ap_rank_diff": "ap_final_rank",
    "seed_diff": "seed",
    "experience_diff": "experience_score",
    "star_power_diff": "star_power",
    "momentum_diff": "last10_winpct",
    "depth_diff": "rotation_depth",
    "quad1_wins_diff": "quad1_wins",
    "conf_win_pct_diff": "conf_win_pct",
}

# These two are computed with special logic rather than simple subtraction.
SPECIAL_DIFF_FEATURES = {"tempo_mismatch", "style_clash"}

# All raw feature columns that get prefixed with team_a_ / team_b_
RAW_FEATURE_COLS: list[str] = [
    "adj_eff_margin",
    "adj_off_eff",
    "adj_def_eff",
    "tempo",
    "three_pt_rate",
    "xfactor_score",
    "roster_continuity",
    "ap_final_rank",
    "seed",
    "experience_score",
    "star_power",
    "last10_winpct",
    "rotation_depth",
    "quad1_wins",
    "conf_win_pct",
]


# ---------------------------------------------------------------------------
# Fuzzy matching fallback
# ---------------------------------------------------------------------------


def _fuzzy_match(name: str, candidates: pd.Series, threshold: int = 80) -> str | None:
    """Return the best fuzzy match for *name* among *candidates*.

    Uses ``thefuzz`` (formerly ``fuzzywuzzy``) if available; falls back to a
    simple normalised-substring heuristic so the pipeline never hard-fails on
    a missing optional dependency.
    """
    try:
        from thefuzz import fuzz  # type: ignore[import-untyped]

        best_score = 0
        best_match: str | None = None
        for candidate in candidates.unique():
            score = fuzz.token_sort_ratio(name, candidate)
            if score > best_score:
                best_score = score
                best_match = candidate
        if best_score >= threshold:
            return best_match
        return None
    except ImportError:
        # Lightweight fallback: normalise both sides and look for containment
        norm = name.lower().strip().replace(".", "").replace("'", "")
        for candidate in candidates.unique():
            cnorm = str(candidate).lower().strip().replace(".", "").replace("'", "")
            if norm == cnorm or norm in cnorm or cnorm in norm:
                return candidate
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merge_team_features(
    games: pd.DataFrame,
    team_col: str,
    seed_col: str,
    features: pd.DataFrame,
    prefix: str,
) -> pd.DataFrame:
    """Left-join a team's features onto the games DataFrame.

    Joins on (team, season) with a fuzzy-matching fallback for name
    mismatches.  Feature columns are prefixed with *prefix* (e.g.
    ``team_a_`` or ``team_b_``).
    """
    # Ensure join keys exist
    if "season" not in features.columns or "team" not in features.columns:
        logger.error(
            "Features DataFrame missing 'season' or 'team' column; available columns: %s",
            list(features.columns),
        )
        return games

    feat = features.copy()

    # Attempt exact merge first
    merged = games.merge(
        feat,
        left_on=[team_col, "season"],
        right_on=["team", "season"],
        how="left",
        suffixes=("", f"_{prefix}"),
    )

    # Identify rows that failed to merge (all feature columns are NaN)
    sample_col = next((c for c in feat.columns if c not in ("team", "season")), None)
    if sample_col is not None:
        unmatched_mask = merged[sample_col].isna()
        unmatched_count = unmatched_mask.sum()

        if unmatched_count > 0:
            logger.info(
                "%d/%d rows unmatched after exact join for %s; attempting fuzzy fallback",
                unmatched_count,
                len(merged),
                prefix,
            )
            for idx in merged.index[unmatched_mask]:
                team_name = merged.loc[idx, team_col]
                season_val = merged.loc[idx, "season"]
                season_feat = feat[feat["season"] == season_val]
                if season_feat.empty:
                    continue
                match = _fuzzy_match(str(team_name), season_feat["team"])
                if match is not None:
                    row = season_feat[season_feat["team"] == match].iloc[0]
                    for col in feat.columns:
                        if col not in ("team", "season"):
                            merged.loc[idx, col] = row[col]
                    logger.debug(
                        "Fuzzy matched '%s' -> '%s' (season %d)",
                        team_name,
                        match,
                        season_val,
                    )

    # Rename feature columns with the prefix
    rename_map: dict[str, str] = {}
    for col in feat.columns:
        if col not in ("team", "season"):
            src = col if col in merged.columns else f"{col}_{prefix}"
            if src in merged.columns:
                rename_map[src] = f"{prefix}{col}"
    merged = merged.rename(columns=rename_map)

    # Carry the seed from the games table into the prefixed column
    if seed_col in games.columns:
        merged[f"{prefix}seed"] = merged[seed_col]

    # Drop the extra 'team' column introduced by the merge
    team_dup = f"team_{prefix}"
    if team_dup in merged.columns:
        merged = merged.drop(columns=[team_dup])
    if "team" in merged.columns and team_col != "team":
        merged = merged.drop(columns=["team"], errors="ignore")

    return merged


def _assemble_team_features(
    team_features: pd.DataFrame,
    player_features: pd.DataFrame,
    portal_features: pd.DataFrame,
    momentum_features: pd.DataFrame,
) -> pd.DataFrame:
    """Merge all per-team feature sources into a single wide DataFrame.

    Returns a DataFrame keyed on (team, season) with columns matching the
    names expected by ``DIFF_FEATURES`` and ``RAW_FEATURE_COLS``.
    """
    combined = team_features.copy()

    # Ensure join keys
    for df, name in [
        (player_features, "player_features"),
        (portal_features, "portal_features"),
        (momentum_features, "momentum_features"),
    ]:
        if df is None or df.empty:
            logger.warning("%s is empty; skipping merge", name)
            continue
        if "team" not in df.columns or "season" not in df.columns:
            logger.warning("%s missing team/season columns; skipping merge", name)
            continue
        # Drop overlapping columns (except join keys) to avoid collisions
        overlap = set(combined.columns) & set(df.columns) - {"team", "season"}
        df_clean = df.drop(columns=list(overlap), errors="ignore")
        combined = combined.merge(df_clean, on=["team", "season"], how="left")

    # Fill missing feature columns with sensible defaults so diffs don't
    # propagate NaN everywhere.
    for col in RAW_FEATURE_COLS:
        if col not in combined.columns:
            logger.debug("Feature column '%s' missing; filling with 0", col)
            combined[col] = 0.0

    return combined


def _compute_diffs(row: pd.Series) -> pd.Series:
    """Compute all differential and special features for a single matchup row."""
    diffs: dict[str, float] = {}

    # Standard differentials (A - B)
    for diff_name, src_col in DIFF_FEATURES.items():
        a_val = row.get(f"team_a_{src_col}", np.nan)
        b_val = row.get(f"team_b_{src_col}", np.nan)
        try:
            diffs[diff_name] = float(a_val) - float(b_val)
        except (TypeError, ValueError):
            diffs[diff_name] = np.nan

    # tempo_mismatch: absolute difference in tempo
    a_tempo = row.get("team_a_tempo", np.nan)
    b_tempo = row.get("team_b_tempo", np.nan)
    try:
        diffs["tempo_mismatch"] = abs(float(a_tempo) - float(b_tempo))
    except (TypeError, ValueError):
        diffs["tempo_mismatch"] = np.nan

    # style_clash: 3PT rate difference (captures stylistic mismatch)
    a_3pt = row.get("team_a_three_pt_rate", np.nan)
    b_3pt = row.get("team_b_three_pt_rate", np.nan)
    try:
        diffs["style_clash"] = float(a_3pt) - float(b_3pt)
    except (TypeError, ValueError):
        diffs["style_clash"] = np.nan

    return pd.Series(diffs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_training_matchups(
    team_features: pd.DataFrame,
    player_features: pd.DataFrame,
    portal_features: pd.DataFrame,
    momentum_features: pd.DataFrame,
    tournament_results: pd.DataFrame,
) -> pd.DataFrame:
    """Create the training dataset from historical tournament games.

    For each tournament game the function:
    1. Looks up both teams' pre-computed features for that season.
    2. Randomly assigns which team is "A" vs "B" (avoids ordering bias).
    3. Computes differential features (team_a - team_b).
    4. Sets the target: 1 if team_a won, 0 if team_b won.
    5. Includes raw prefixed features for tree-model non-linear interactions.

    Parameters
    ----------
    team_features : pd.DataFrame
        Team-level features with at least ``team``, ``season``, and the
        columns referenced by ``DIFF_FEATURES`` / ``RAW_FEATURE_COLS``.
    player_features : pd.DataFrame
        Aggregated player-level features (``team``, ``season``, plus
        ``star_power``, ``experience``, ``depth``, etc.).
    portal_features : pd.DataFrame
        Roster continuity / transfer portal features (``team``, ``season``,
        ``roster_continuity``, etc.).
    momentum_features : pd.DataFrame
        Late-season momentum features (``team``, ``season``, ``momentum``,
        etc.).
    tournament_results : pd.DataFrame
        Historical game results with columns: ``season``, ``round``,
        ``team_1`` (or ``team_a``), ``team_2`` (or ``team_b``),
        ``seed_1`` (or ``seed_a``), ``seed_2`` (or ``seed_b``),
        ``score_1`` (or ``score_a``), ``score_2`` (or ``score_b``),
        ``winner``.

    Returns
    -------
    pd.DataFrame
        One row per game with differential features, raw prefixed features,
        metadata columns (``season``, ``round``), and a binary ``target``
        column (1 = team_a won).
    """
    logger.info("Building training matchups from %d tournament games", len(tournament_results))

    # --- Normalise tournament_results column names -------------------------
    tr = tournament_results.copy()
    col_renames: dict[str, str] = {}
    for old, new in [
        ("team_a", "team_a"),
        ("team_1", "team_a"),
        ("team_b", "team_b"),
        ("team_2", "team_b"),
        ("seed_a", "seed_a"),
        ("seed_1", "seed_a"),
        ("seed_b", "seed_b"),
        ("seed_2", "seed_b"),
        ("score_a", "score_a"),
        ("score_1", "score_a"),
        ("score_b", "score_b"),
        ("score_2", "score_b"),
    ]:
        if old in tr.columns and new not in tr.columns:
            col_renames[old] = new
    tr = tr.rename(columns=col_renames)

    required = {"season", "team_a", "team_b", "winner"}
    missing = required - set(tr.columns)
    if missing:
        raise ValueError(f"tournament_results is missing required columns: {missing}")

    # --- Use normalized (lowercased) team names for joining with features ---
    # Tournament results contain display names (e.g. "UConn") in team_a/team_b
    # and lowercased names (e.g. "connecticut") in *_normalized columns.
    # Feature DataFrames use lowercased names in their "team" column.
    # Overwrite team_a/team_b/winner with the normalized versions so exact
    # joins succeed without falling through to slow fuzzy matching.
    if "team_1_normalized" in tr.columns:
        tr["team_a"] = tr["team_1_normalized"]
    if "team_2_normalized" in tr.columns:
        tr["team_b"] = tr["team_2_normalized"]
    if "winner_normalized" in tr.columns:
        tr["winner"] = tr["winner_normalized"]

    # Apply nickname -> full name normalization so joins match team_features
    for col in ("team_a", "team_b", "winner"):
        if col in tr.columns:
            tr[col] = tr[col].apply(_normalize_tourney_name)

    # --- Randomise A/B assignment to prevent ordering bias -----------------
    rng = np.random.default_rng(seed=42)
    swap_mask = rng.random(len(tr)) > 0.5

    for col_a, col_b in [
        ("team_a", "team_b"),
        ("seed_a", "seed_b"),
        ("score_a", "score_b"),
    ]:
        if col_a in tr.columns and col_b in tr.columns:
            tr.loc[swap_mask, [col_a, col_b]] = tr.loc[swap_mask, [col_b, col_a]].values

    # --- Assemble unified per-team features --------------------------------
    all_features = _assemble_team_features(
        team_features,
        player_features,
        portal_features,
        momentum_features,
    )

    # --- Merge features for team_a -----------------------------------------
    merged = _merge_team_features(
        tr,
        team_col="team_a",
        seed_col="seed_a",
        features=all_features,
        prefix="team_a_",
    )

    # --- Merge features for team_b -----------------------------------------
    merged = _merge_team_features(
        merged,
        team_col="team_b",
        seed_col="seed_b",
        features=all_features,
        prefix="team_b_",
    )

    # --- Compute differential features -------------------------------------
    diff_df = merged.apply(_compute_diffs, axis=1)
    merged = pd.concat([merged, diff_df], axis=1)

    # --- Target variable ---------------------------------------------------
    merged["target"] = (merged["team_a"] == merged["winner"]).astype(int)

    # --- Select final columns ----------------------------------------------
    meta_cols = ["season", "round", "team_a", "team_b"]
    diff_cols = list(DIFF_FEATURES.keys()) + ["tempo_mismatch", "style_clash"]
    raw_a_cols = [f"team_a_{c}" for c in RAW_FEATURE_COLS]
    raw_b_cols = [f"team_b_{c}" for c in RAW_FEATURE_COLS]

    all_cols = meta_cols + diff_cols + raw_a_cols + raw_b_cols + ["target"]
    # Keep only columns that actually exist (some may be missing if data is
    # incomplete).
    final_cols = [c for c in all_cols if c in merged.columns]
    result = merged[final_cols].copy()

    # --- Persist to parquet ------------------------------------------------
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=False)
    logger.info(
        "Saved %d training matchup rows (%d features) to %s",
        len(result),
        len(final_cols) - len(meta_cols) - 1,  # exclude meta + target
        OUTPUT_PATH,
    )

    return result


def build_prediction_matchup(
    team_a_features: dict,
    team_b_features: dict,
) -> pd.DataFrame:
    """Build a single matchup feature row for prediction.

    Given two teams' pre-computed feature dictionaries, compute the same
    differential and raw features used during training.

    Parameters
    ----------
    team_a_features : dict
        Feature dict for team A.  Keys should match ``RAW_FEATURE_COLS``
        (e.g. ``adj_em``, ``tempo``, ``seed``, etc.).
    team_b_features : dict
        Feature dict for team B.

    Returns
    -------
    pd.DataFrame
        A single-row DataFrame with the same column schema as the training
        data (excluding ``season``, ``round``, ``team_a``, ``team_b``,
        and ``target``).
    """
    row: dict[str, float] = {}

    # Raw features (prefixed)
    for col in RAW_FEATURE_COLS:
        row[f"team_a_{col}"] = float(team_a_features.get(col, 0.0))
        row[f"team_b_{col}"] = float(team_b_features.get(col, 0.0))

    # Standard differentials
    for diff_name, src_col in DIFF_FEATURES.items():
        a_val = float(team_a_features.get(src_col, 0.0))
        b_val = float(team_b_features.get(src_col, 0.0))
        row[diff_name] = a_val - b_val

    # Special differentials
    a_tempo = float(team_a_features.get("tempo", 0.0))
    b_tempo = float(team_b_features.get("tempo", 0.0))
    row["tempo_mismatch"] = abs(a_tempo - b_tempo)

    a_3pt = float(team_a_features.get("three_pt_rate", 0.0))
    b_3pt = float(team_b_features.get("three_pt_rate", 0.0))
    row["style_clash"] = a_3pt - b_3pt

    # Assemble in the canonical column order
    diff_cols = list(DIFF_FEATURES.keys()) + ["tempo_mismatch", "style_clash"]
    raw_a_cols = [f"team_a_{c}" for c in RAW_FEATURE_COLS]
    raw_b_cols = [f"team_b_{c}" for c in RAW_FEATURE_COLS]
    ordered_cols = diff_cols + raw_a_cols + raw_b_cols

    return pd.DataFrame([row], columns=ordered_cols)
