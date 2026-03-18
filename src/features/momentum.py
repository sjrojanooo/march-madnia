"""
Late-season momentum features.

Builds features that capture how a team is performing heading into
(and during) the postseason, using season-level stats as proxies
when game-by-game data is unavailable.
"""

import numpy as np
import pandas as pd


def _conf_tourney_code(result: str) -> int:
    """Map a conference tournament result string to a numeric code.

    Returns
    -------
    int
        0 = early exit / first round / unknown
        1 = semifinal
        2 = final (runner-up)
        3 = champion
    """
    if pd.isna(result):
        return 0

    val = str(result).strip().lower()

    champion_keywords = {"champion", "champ", "winner", "won", "1st"}
    final_keywords = {"final", "runner-up", "runner up", "runnerup", "2nd", "finals"}
    semi_keywords = {"semi", "semifinal", "semi-final", "3rd", "4th"}

    if any(kw in val for kw in champion_keywords):
        return 3
    if any(kw in val for kw in final_keywords):
        return 2
    if any(kw in val for kw in semi_keywords):
        return 1
    return 0


def build_momentum_features(
    team_stats: pd.DataFrame,
    tournament_results: pd.DataFrame,
) -> pd.DataFrame:
    """Build late-season momentum features.

    Parameters
    ----------
    team_stats : pd.DataFrame
        Season-level team statistics.  Expected columns include at
        least ``team``, ``season``, and as many of the following as
        available: ``wins``, ``losses``, ``ppg`` (points per game),
        ``adj_em`` (adjusted efficiency margin), ``last10_wins``,
        ``last10_losses``, ``conf_avg_ppg``.
    tournament_results : pd.DataFrame
        Conference and NCAA tournament outcomes.  Expected columns:
        ``team``, ``season``, ``conf_tourney_result``.

    Returns
    -------
    pd.DataFrame
        One row per team-season with features:
        - last10_winpct
        - conf_tourney_result
        - scoring_trend
        - efficiency_trend
    """

    # ------------------------------------------------------------------
    # 1. Build base dataframe from team_stats
    # ------------------------------------------------------------------
    if team_stats is None or team_stats.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "season",
                "last10_winpct",
                "conf_tourney_result",
                "scoring_trend",
                "efficiency_trend",
            ]
        )

    df = team_stats[["team", "season"]].copy()

    # ------------------------------------------------------------------
    # 2. last10_winpct
    # ------------------------------------------------------------------
    # Prefer explicit last-10 record if available; otherwise fall back
    # to overall win percentage as a proxy.
    if "last10_wins" in team_stats.columns and "last10_losses" in team_stats.columns:
        l10_wins = team_stats["last10_wins"].fillna(0)
        l10_losses = team_stats["last10_losses"].fillna(0)
        l10_total = l10_wins + l10_losses
        df["last10_winpct"] = np.where(l10_total > 0, l10_wins / l10_total, np.nan)
    else:
        df["last10_winpct"] = np.nan

    # Fall back to overall win% where last-10 is unavailable
    if df["last10_winpct"].isna().any():
        if {"wins", "losses"}.issubset(team_stats.columns):
            total_games = team_stats["wins"].fillna(0) + team_stats["losses"].fillna(0)
            overall_pct = np.where(
                total_games > 0,
                team_stats["wins"].fillna(0) / total_games,
                0.5,
            )
            df["last10_winpct"] = df["last10_winpct"].fillna(pd.Series(overall_pct, index=df.index))
        else:
            df["last10_winpct"] = df["last10_winpct"].fillna(0.5)

    # ------------------------------------------------------------------
    # 3. conf_tourney_result
    # ------------------------------------------------------------------
    if tournament_results is not None and not tournament_results.empty:
        if "conf_tourney_result" in tournament_results.columns:
            tr = tournament_results[["team", "season", "conf_tourney_result"]].copy()
            tr["conf_tourney_result"] = tr["conf_tourney_result"].apply(_conf_tourney_code)
            df = df.merge(tr, on=["team", "season"], how="left")
        else:
            df["conf_tourney_result"] = 0
    else:
        df["conf_tourney_result"] = 0

    df["conf_tourney_result"] = df["conf_tourney_result"].fillna(0).astype(int)

    # ------------------------------------------------------------------
    # 4. scoring_trend
    # ------------------------------------------------------------------
    # Proxy: team PPG relative to conference average PPG.
    # A positive value means the team is outscoring the typical
    # conference opponent.
    if "ppg" in team_stats.columns:
        if "conf_avg_ppg" in team_stats.columns:
            conf_avg = team_stats["conf_avg_ppg"].fillna(team_stats["ppg"].mean())
        else:
            # Use the overall mean as the conference-average proxy
            conf_avg = team_stats["ppg"].mean()

        df["scoring_trend"] = (team_stats["ppg"].fillna(0) - conf_avg).values
    else:
        df["scoring_trend"] = 0.0

    # ------------------------------------------------------------------
    # 5. efficiency_trend
    # ------------------------------------------------------------------
    # Proxy: percentile rank of AdjEM across all teams in the season.
    # 1.0 = best efficiency margin, 0.0 = worst.
    if "adj_em" in team_stats.columns:
        adj_em = team_stats[["team", "season", "adj_em"]].copy()
        df["efficiency_trend"] = adj_em.groupby("season")["adj_em"].rank(pct=True).values
    else:
        # Without AdjEM, fall back to overall win-pct percentile rank
        if {"wins", "losses"}.issubset(team_stats.columns):
            total = team_stats["wins"].fillna(0) + team_stats["losses"].fillna(0)
            win_pct = np.where(total > 0, team_stats["wins"].fillna(0) / total, 0.5)
            temp = team_stats[["team", "season"]].copy()
            temp["_wpct"] = win_pct
            df["efficiency_trend"] = temp.groupby("season")["_wpct"].rank(pct=True).values
        else:
            df["efficiency_trend"] = 0.5

    # ------------------------------------------------------------------
    # 6. Return clean output
    # ------------------------------------------------------------------
    output_cols = [
        "team",
        "season",
        "last10_winpct",
        "conf_tourney_result",
        "scoring_trend",
        "efficiency_trend",
    ]

    return df[output_cols].reset_index(drop=True)
