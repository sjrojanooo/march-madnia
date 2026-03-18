"""Basketball Analyst agent — domain expert translating gaps into feature ideas.

Uses hardcoded domain knowledge about tournament dynamics to produce
basketball-informed feature suggestions.
"""

from __future__ import annotations

import logging

from src.agents.schemas import AnalystSuggestion, FeatureSuggestion, ReviewReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain knowledge
# ---------------------------------------------------------------------------

TOURNAMENT_INSIGHTS = {
    "12_5_upsets": (
        "12-seed vs 5-seed upsets happen ~35% of the time. Key indicators: "
        "the 12-seed typically has a strong defensive identity and experienced guards "
        "who can handle pressure. FT shooting and turnover margin are critical."
    ),
    "defensive_efficiency": (
        "Tournament games shift to half-court offense as tempo slows. Teams that "
        "excel in half-court defense (low opponent eFG%, high block rate, contest "
        "rate) overperform their regular-season metrics."
    ),
    "guard_play": (
        "Guard-driven teams with low turnover rates and high assist-to-turnover "
        "ratios tend to advance further. Point guard quality is the single most "
        "important positional factor in March."
    ),
    "bench_depth": (
        "Back-to-back games in the tournament expose thin rotations. Teams with "
        "high bench minutes percentage and minimal drop-off from starters to "
        "reserves have a structural advantage in Sweet 16+."
    ),
    "coaching_experience": (
        "Coaches with multiple tournament appearances make better in-game "
        "adjustments. First-time tournament coaches underperform by ~3-5% "
        "against the spread."
    ),
    "ft_shooting": (
        "Close games (decided by <6 points) constitute ~40% of tournament games. "
        "Free throw percentage in the last 5 minutes correlates strongly with "
        "winning in these situations. Overall FT% is a strong proxy."
    ),
    "tempo_control": (
        "Teams that can dictate tempo (either speed up or slow down the game) "
        "based on matchup have a significant edge. The tempo flexibility metric "
        "(variance in game-by-game tempo) captures this adaptability."
    ),
    "rebounding_margin": (
        "Offensive rebounding creates second-chance points which are amplified "
        "in low-possession tournament games. A team grabbing 3+ more offensive "
        "rebounds per game has a significant edge."
    ),
}


def run_basketball_analyst(
    iteration: int,
    review_report: ReviewReport,
) -> AnalystSuggestion:
    """Generate domain-informed feature suggestions based on the Reviewer's gaps.

    Maps identified gaps to basketball-specific feature ideas with
    implementation hints.
    """
    logger.info("Basketball Analyst: generating suggestions for iteration %d", iteration)

    suggestions: list[FeatureSuggestion] = []
    gaps = review_report.gaps_identified
    priorities = review_report.priority_actions

    # Map gaps/priorities to concrete feature suggestions
    suggestions.extend(_suggest_from_gaps(gaps))
    suggestions.extend(_suggest_from_priorities(priorities, review_report))

    # Deduplicate by name
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s.name not in seen:
            seen.add(s.name)
            unique_suggestions.append(s)

    # Rank by expected impact
    impact_order = {"high": 0, "medium": 1, "low": 2}
    unique_suggestions.sort(key=lambda s: impact_order.get(s.expected_impact, 1))

    # Limit to top 5 per iteration to keep changes manageable
    unique_suggestions = unique_suggestions[:5]

    rationale = _build_domain_rationale(review_report, unique_suggestions)

    result = AnalystSuggestion(
        iteration=iteration,
        responding_to_gaps=gaps,
        feature_suggestions=unique_suggestions,
        domain_rationale=rationale,
    )

    logger.info(
        "Basketball Analyst: %d suggestions generated",
        len(unique_suggestions),
    )
    return result


def _suggest_from_gaps(gaps: list[str]) -> list[FeatureSuggestion]:
    """Convert identified gaps into concrete feature suggestions."""
    suggestions: list[FeatureSuggestion] = []

    for gap in gaps:
        gap_lower = gap.lower()

        if "turnover" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="turnover_pct_diff",
                description=(
                    "Differential in turnover percentage (turnovers per 100 possessions). "
                    "Lower is better — teams that protect the ball under tournament pressure advance."
                ),
                data_source="team_stats (tov_per_g, possessions) or torvik_ratings",
                implementation_hint=(
                    "Compute turnover_pct = tov / (fga + 0.44 * fta + tov) for each team. "
                    "Add to team_features.py, register as diff in matchup.py."
                ),
                expected_impact="high",
                rationale=TOURNAMENT_INSIGHTS["guard_play"],
            ))

        if "ft_rate" in gap_lower or "free throw" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="ft_rate_diff",
                description=(
                    "Free throw rate differential (FTA / FGA). Measures ability to get "
                    "to the line and convert. Critical in close tournament games."
                ),
                data_source="team_stats (fta, fga columns)",
                implementation_hint=(
                    "Compute ft_rate = fta / fga for each team. "
                    "Add to team_features.py, register as diff in matchup.py."
                ),
                expected_impact="high",
                rationale=TOURNAMENT_INSIGHTS["ft_shooting"],
            ))

        if "oreb" in gap_lower or "offensive rebound" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="oreb_pct_diff",
                description=(
                    "Offensive rebound percentage differential. Second-chance points "
                    "are amplified in low-possession tournament games."
                ),
                data_source="team_stats (orb, drb or orb_per_g columns)",
                implementation_hint=(
                    "Compute oreb_pct = orb / (orb + opp_drb). If opponent DRB not available, "
                    "use orb_per_g directly. Add to team_features.py."
                ),
                expected_impact="medium",
                rationale=TOURNAMENT_INSIGHTS["rebounding_margin"],
            ))

        if "assist" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="assist_rate_diff",
                description=(
                    "Assist rate differential. Higher assist rates indicate better ball "
                    "movement and team offense quality."
                ),
                data_source="team_stats (ast, fgm or ast_per_g columns)",
                implementation_hint=(
                    "Compute assist_rate = ast / fgm (assisted field goals ratio). "
                    "Add to team_features.py, register as diff in matchup.py."
                ),
                expected_impact="medium",
                rationale=TOURNAMENT_INSIGHTS["guard_play"],
            ))

        if "block" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="block_rate_diff",
                description=(
                    "Block rate differential. Rim protection forces opponents into "
                    "tougher shots in half-court tournament play."
                ),
                data_source="team_stats (blk, opp_fga or blk_per_g columns)",
                implementation_hint=(
                    "Compute block_rate = blk / opp_fga if available, else use blk_per_g. "
                    "Add to team_features.py, register as diff in matchup.py."
                ),
                expected_impact="medium",
                rationale=TOURNAMENT_INSIGHTS["defensive_efficiency"],
            ))

        if "steal" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="steal_rate_diff",
                description=(
                    "Steal rate differential. Active hands create live-ball turnovers "
                    "and transition opportunities."
                ),
                data_source="team_stats (stl or stl_per_g columns)",
                implementation_hint=(
                    "Use stl_per_g directly or compute stl / possessions. "
                    "Add to team_features.py, register as diff in matchup.py."
                ),
                expected_impact="medium",
                rationale=TOURNAMENT_INSIGHTS["defensive_efficiency"],
            ))

        if "bench" in gap_lower or "depth" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="bench_scoring_pct",
                description=(
                    "Percentage of scoring from non-starters. Higher bench contribution "
                    "indicates depth resilience for back-to-back tournament games."
                ),
                data_source="player_stats (pts, minutes for starters vs bench)",
                implementation_hint=(
                    "Aggregate player_stats: bench_pts = sum(pts for non-top-5-minute players). "
                    "bench_scoring_pct = bench_pts / total_pts. Add to player_features.py."
                ),
                expected_impact="low",
                rationale=TOURNAMENT_INSIGHTS["bench_depth"],
            ))

        if "coach" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="coach_tourney_exp_diff",
                description=(
                    "Coach tournament experience differential. Experienced coaches "
                    "make better adjustments under tournament pressure."
                ),
                data_source="Would require new data source (coaching records)",
                implementation_hint=(
                    "This requires scraping coach tournament appearance data. "
                    "Could proxy with team's tournament appearances in last 5 years "
                    "from tournament_results."
                ),
                expected_impact="low",
                rationale=TOURNAMENT_INSIGHTS["coaching_experience"],
            ))

        if "sos" in gap_lower or "strength of schedule" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="sos_diff",
                description=(
                    "Strength of schedule differential. Contextualizes win/loss "
                    "records and efficiency metrics."
                ),
                data_source="torvik_ratings or team_stats (SOS column if available)",
                implementation_hint=(
                    "Check torvik_ratings for SOS column. If not available, "
                    "approximate from conference_strength + opponent efficiency."
                ),
                expected_impact="medium",
                rationale="SOS normalizes performance across conferences of varying quality.",
            ))

        if "zero-variance" in gap_lower or "zero_variance" in gap_lower:
            suggestions.append(FeatureSuggestion(
                name="fix_zero_variance_pipeline",
                description=(
                    "Fix the data pipeline for features that are currently zero-variance: "
                    "roster_continuity, experience_score, last10_winpct. These features "
                    "are valuable but their computation is producing constant values."
                ),
                data_source="portal_features, momentum_features, player_features pipelines",
                implementation_hint=(
                    "Debug why these features produce constant values. Common causes: "
                    "join failures (team name mismatches), missing raw data, or "
                    "default-value fallbacks overwriting real data."
                ),
                expected_impact="high",
                rationale=(
                    "These features (momentum, experience, roster continuity) are "
                    "strong tournament predictors when computed correctly."
                ),
            ))

    return suggestions


def _suggest_from_priorities(
    priorities: list[str],
    review_report: ReviewReport,
) -> list[FeatureSuggestion]:
    """Generate additional suggestions based on priority actions."""
    suggestions: list[FeatureSuggestion] = []

    for priority in priorities:
        p_lower = priority.lower()

        if "offensive efficiency" in p_lower and not any(
            s.name == "efg_pct_diff" for s in suggestions
        ):
            suggestions.append(FeatureSuggestion(
                name="efg_pct_diff",
                description=(
                    "Effective field goal percentage differential. Weights 3-pointers "
                    "at 1.5x to capture true shooting efficiency."
                ),
                data_source="team_stats (fg, fga, fg3 columns)",
                implementation_hint=(
                    "Compute eFG% = (FG + 0.5 * FG3) / FGA. May already exist as "
                    "efg_pct in team_features — check if it's being passed through to matchup."
                ),
                expected_impact="high",
                rationale="eFG% is one of the four factors of basketball and a top predictor.",
            ))

    return suggestions


def _build_domain_rationale(
    review_report: ReviewReport,
    suggestions: list[FeatureSuggestion],
) -> str:
    """Build a narrative rationale for the suggested changes."""
    parts = [
        f"Iteration {review_report.iteration} analysis: "
        f"{review_report.total_features} features, "
        f"{review_report.total_training_rows} training rows.",
    ]

    if review_report.zero_variance:
        parts.append(
            f"Critical: {len(review_report.zero_variance)} features have zero variance "
            "and are being auto-dropped. Fixing the data pipeline for these features "
            "should be the top priority."
        )

    if review_report.high_null:
        parts.append(
            f"{len(review_report.high_null)} features have >20% missing data, "
            "reducing effective training signal."
        )

    parts.append(
        f"Recommending {len(suggestions)} feature changes based on tournament dynamics: "
        + ", ".join(s.name for s in suggestions)
        + "."
    )

    return " ".join(parts)
