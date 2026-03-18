"""
Transfer portal and roster continuity features.

Builds features capturing how roster turnover and transfer portal
activity affect team performance in a given season.
"""

import numpy as np
import pandas as pd

# League-average defaults when portal data is missing
_DEFAULT_ROSTER_CONTINUITY = 0.55
_DEFAULT_TRANSFER_COUNT = 3
_DEFAULT_NEW_PLAYER_PCT = 0.35
_DEFAULT_PER = 15.0  # approximate NCAA D1 league-average PER
_DEFAULT_EXPERIENCE_TURNOVER = 0.40


def _compute_continuity_from_players(
    player_stats: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate roster continuity from player-level data.

    For each team-season, computes the fraction of prior-season minutes
    that are returning.  Falls back to the league-average default when
    the player data is insufficient.
    """
    required_cols = {"team", "season", "minutes", "returning"}
    if not required_cols.issubset(player_stats.columns):
        return pd.DataFrame(columns=["team", "season", "roster_continuity"])

    df = player_stats.copy()

    # Total minutes per team-season
    total_min = df.groupby(["team", "season"])["minutes"].sum().rename("total_minutes")

    # Returning minutes
    returning_min = (
        df[df["returning"] == True]  # noqa: E712
        .groupby(["team", "season"])["minutes"]
        .sum()
        .rename("returning_minutes")
    )

    continuity = (
        pd.concat([total_min, returning_min], axis=1)
        .fillna(0)
        .assign(
            roster_continuity=lambda x: np.where(
                x["total_minutes"] > 0,
                x["returning_minutes"] / x["total_minutes"],
                _DEFAULT_ROSTER_CONTINUITY,
            )
        )
        .reset_index()[["team", "season", "roster_continuity"]]
    )

    return continuity


def build_portal_features(
    portal_data: pd.DataFrame,
    player_stats: pd.DataFrame,
) -> pd.DataFrame:
    """Build transfer-portal and roster-continuity features.

    Parameters
    ----------
    portal_data : pd.DataFrame
        Transfer portal / roster data with columns that may include:
        team, season, roster_continuity, new_player_pct,
        estimated_transfer_count, experience_turnover.
    player_stats : pd.DataFrame
        Player-level season stats used as a fallback for computing
        roster continuity when portal_data is incomplete.

    Returns
    -------
    pd.DataFrame
        One row per team-season with the following features:
        - roster_continuity
        - transfer_count
        - transfer_talent_score
        - portal_net_talent
        - new_player_pct
        - portal_impact
    """

    # ------------------------------------------------------------------
    # 1. Start from portal_data if available; otherwise build skeleton
    # ------------------------------------------------------------------
    if portal_data is not None and not portal_data.empty:
        df = portal_data[["team", "season"]].copy()

        # Roster continuity ------------------------------------------------
        if "roster_continuity" in portal_data.columns:
            df["roster_continuity"] = portal_data["roster_continuity"].values
        else:
            df["roster_continuity"] = np.nan

        # Transfer count ---------------------------------------------------
        if "estimated_transfer_count" in portal_data.columns:
            df["transfer_count"] = portal_data["estimated_transfer_count"].values
        else:
            df["transfer_count"] = np.nan

        # New-player percentage --------------------------------------------
        if "new_player_pct" in portal_data.columns:
            df["new_player_pct"] = portal_data["new_player_pct"].values
        else:
            df["new_player_pct"] = np.nan

        # Experience turnover (used for net-talent estimate) ----------------
        if "experience_turnover" in portal_data.columns:
            df["experience_turnover"] = portal_data["experience_turnover"].values
        else:
            df["experience_turnover"] = np.nan

    else:
        # No portal data at all -- build from player stats if possible
        df = pd.DataFrame(
            columns=[
                "team",
                "season",
                "roster_continuity",
                "transfer_count",
                "new_player_pct",
                "experience_turnover",
            ]
        )
        if player_stats is not None and not player_stats.empty:
            teams = player_stats[["team", "season"]].drop_duplicates()
            df = teams.copy()
            df["roster_continuity"] = np.nan
            df["transfer_count"] = np.nan
            df["new_player_pct"] = np.nan
            df["experience_turnover"] = np.nan

    if df.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "season",
                "roster_continuity",
                "transfer_count",
                "transfer_talent_score",
                "portal_net_talent",
                "new_player_pct",
                "portal_impact",
            ]
        )

    # ------------------------------------------------------------------
    # 2. Fill missing continuity from player-level data
    # ------------------------------------------------------------------
    if df["roster_continuity"].isna().any() and player_stats is not None and not player_stats.empty:
        player_cont = _compute_continuity_from_players(player_stats)
        if not player_cont.empty:
            df = df.merge(
                player_cont.rename(columns={"roster_continuity": "_player_cont"}),
                on=["team", "season"],
                how="left",
            )
            df["roster_continuity"] = df["roster_continuity"].fillna(df["_player_cont"])
            df.drop(columns=["_player_cont"], inplace=True)

    # ------------------------------------------------------------------
    # 3. Fill remaining NaNs with league-average defaults
    # ------------------------------------------------------------------
    df["roster_continuity"] = df["roster_continuity"].fillna(_DEFAULT_ROSTER_CONTINUITY)
    df["transfer_count"] = df["transfer_count"].fillna(_DEFAULT_TRANSFER_COUNT)
    df["new_player_pct"] = df["new_player_pct"].fillna(_DEFAULT_NEW_PLAYER_PCT)
    df["experience_turnover"] = df["experience_turnover"].fillna(_DEFAULT_EXPERIENCE_TURNOVER)

    # ------------------------------------------------------------------
    # 4. Derived features
    # ------------------------------------------------------------------

    # transfer_talent_score: avg prior-season PER of incoming transfers.
    # Without individual transfer PER data we default to league average.
    df["transfer_talent_score"] = _DEFAULT_PER

    # portal_net_talent: talent gained minus talent lost.
    # Proxy: (transfer_count * transfer_talent_score) - (experience_turnover * league_avg_PER)
    # A positive value means the team upgraded via the portal.
    df["portal_net_talent"] = (
        df["transfer_count"] * df["transfer_talent_score"]
        - df["experience_turnover"] * _DEFAULT_PER * df["transfer_count"]
    )

    # portal_impact: composite score combining continuity with a
    # transfer-talent boost.  Higher continuity is generally better,
    # but a big talent infusion via transfers can offset churn.
    talent_boost = (df["transfer_talent_score"] - _DEFAULT_PER) / _DEFAULT_PER
    df["portal_impact"] = df["roster_continuity"] * (1 + talent_boost)

    # ------------------------------------------------------------------
    # 5. Clean up and return
    # ------------------------------------------------------------------
    output_cols = [
        "team",
        "season",
        "roster_continuity",
        "transfer_count",
        "transfer_talent_score",
        "portal_net_talent",
        "new_player_pct",
        "portal_impact",
    ]

    return df[output_cols].reset_index(drop=True)
