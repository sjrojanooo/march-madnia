"""Feature Improvement agent — implements code changes to feature modules.

Reads the ReviewReport and AnalystSuggestions, then produces a FeatureProposal
with specific code changes to implement the suggested features.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.agents.schemas import (
    AnalystSuggestion,
    ChangeType,
    FeatureChange,
    FeatureProposal,
    ReviewReport,
)
from src.agents.utils import get_matchup_feature_definitions, read_source_file

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_feature_agent(
    iteration: int,
    review_report: ReviewReport,
    analyst_suggestion: AnalystSuggestion,
) -> FeatureProposal:
    """Generate code changes to implement suggested features.

    Reads current source code and produces a FeatureProposal with changes
    that can be applied to improve the feature set.
    """
    logger.info("Feature Agent: generating proposal for iteration %d", iteration)

    current_defs = get_matchup_feature_definitions()
    changes: list[FeatureChange] = []
    new_features: list[str] = []
    modified_features: list[str] = []
    removed_features: list[str] = []

    # Read current source files for context
    team_features_src = read_source_file("src/features/team_features.py")
    matchup_src = read_source_file("src/features/matchup.py")
    player_features_src = read_source_file("src/features/player_features.py")

    for suggestion in analyst_suggestion.feature_suggestions:
        change = _implement_suggestion(
            suggestion=suggestion,
            current_defs=current_defs,
            team_features_src=team_features_src,
            matchup_src=matchup_src,
            player_features_src=player_features_src,
        )
        if change is not None:
            changes.append(change)
            if change.change_type == ChangeType.ADD:
                new_features.append(suggestion.name)
            elif change.change_type == ChangeType.MODIFY:
                modified_features.append(suggestion.name)

    # Generate matchup.py registration changes
    matchup_changes = _generate_matchup_registration(new_features, current_defs)
    changes.extend(matchup_changes)

    # Build summary
    diff_summary = _build_diff_summary(changes)

    proposal = FeatureProposal(
        iteration=iteration,
        changes=changes,
        new_features=new_features,
        modified_features=modified_features,
        removed_features=removed_features,
        code_diff_summary=diff_summary,
    )

    logger.info(
        "Feature Agent: %d changes proposed (%d new, %d modified)",
        len(changes),
        len(new_features),
        len(modified_features),
    )
    return proposal


def _implement_suggestion(
    suggestion,
    current_defs: dict,
    team_features_src: str,
    matchup_src: str,
    player_features_src: str,
) -> FeatureChange | None:
    """Generate a FeatureChange for a single suggestion."""
    name = suggestion.name

    # Skip meta-suggestions that aren't direct features
    if name == "fix_zero_variance_pipeline":
        return _generate_pipeline_fix(suggestion)

    # Check if this is a team-level feature
    if suggestion.data_source and any(
        src in suggestion.data_source.lower()
        for src in ["team_stats", "torvik"]
    ):
        return _generate_team_feature(name, suggestion, team_features_src)

    # Player-level feature
    if suggestion.data_source and "player" in suggestion.data_source.lower():
        return _generate_player_feature(name, suggestion, player_features_src)

    # Default: team feature
    return _generate_team_feature(name, suggestion, team_features_src)


def _generate_team_feature(
    name: str,
    suggestion,
    current_src: str,
) -> FeatureChange:
    """Generate code to add a team-level feature to team_features.py."""
    # Map feature names to computation code
    feature_code = _get_feature_computation_code(name)

    return FeatureChange(
        file_path="src/features/team_features.py",
        change_type=ChangeType.ADD,
        description=f"Add {name}: {suggestion.description}",
        code_snippet=feature_code,
    )


def _generate_player_feature(
    name: str,
    suggestion,
    current_src: str,
) -> FeatureChange:
    """Generate code to add a player-level feature to player_features.py."""
    feature_code = _get_feature_computation_code(name)

    return FeatureChange(
        file_path="src/features/player_features.py",
        change_type=ChangeType.ADD,
        description=f"Add {name}: {suggestion.description}",
        code_snippet=feature_code,
    )


def _generate_pipeline_fix(suggestion) -> FeatureChange:
    """Generate a fix for zero-variance pipeline issues."""
    return FeatureChange(
        file_path="src/features/team_features.py",
        change_type=ChangeType.MODIFY,
        description=(
            "Fix zero-variance features by debugging data pipeline joins. "
            "Check team name normalization, merge keys, and default value fallbacks."
        ),
        code_snippet=(
            "# Debug: log actual values before and after merge for these features:\n"
            "# - roster_continuity (from portal_features)\n"
            "# - experience_score (from player_features)\n"
            "# - last10_winpct (from momentum_features)\n"
            "# Check if team name format matches between data sources.\n"
            "# Common issue: one source uses 'north-carolina', another uses 'north carolina'"
        ),
    )


def _generate_matchup_registration(
    new_features: list[str],
    current_defs: dict,
) -> list[FeatureChange]:
    """Generate changes to register new features in matchup.py."""
    changes: list[FeatureChange] = []

    existing_diffs = set(current_defs.get("diff_features", {}).keys())
    existing_raw = set(current_defs.get("raw_feature_cols", []))

    # Map feature diff names to their source column names
    feature_source_map = {
        "turnover_pct_diff": "turnover_pct",
        "ft_rate_diff": "ft_rate",
        "oreb_pct_diff": "oreb_pct",
        "assist_rate_diff": "assist_rate",
        "block_rate_diff": "block_rate",
        "steal_rate_diff": "steal_rate",
        "efg_pct_diff": "efg_pct",
        "sos_diff": "sos",
        "wins_diff": "wins",
        "def_reb_pct_diff": "def_reb_pct",
        "bench_scoring_pct": "bench_scoring_pct",
        "coach_tourney_exp_diff": "coach_tourney_exp",
    }

    new_diffs = {}
    new_raw = []

    for feat_name in new_features:
        if feat_name in feature_source_map and feat_name not in existing_diffs:
            source_col = feature_source_map[feat_name]
            new_diffs[feat_name] = source_col
            if source_col not in existing_raw:
                new_raw.append(source_col)

    if new_diffs:
        diff_snippet = "# Add to DIFF_FEATURES dict:\n"
        for diff_name, src_col in new_diffs.items():
            diff_snippet += f'    "{diff_name}": "{src_col}",\n'

        changes.append(FeatureChange(
            file_path="src/features/matchup.py",
            change_type=ChangeType.MODIFY,
            description=f"Register {len(new_diffs)} new differential features in DIFF_FEATURES",
            code_snippet=diff_snippet,
        ))

    if new_raw:
        raw_snippet = "# Add to RAW_FEATURE_COLS list:\n"
        for col in new_raw:
            raw_snippet += f'    "{col}",\n'

        changes.append(FeatureChange(
            file_path="src/features/matchup.py",
            change_type=ChangeType.MODIFY,
            description=f"Register {len(new_raw)} new raw feature columns in RAW_FEATURE_COLS",
            code_snippet=raw_snippet,
        ))

    return changes


def _get_feature_computation_code(name: str) -> str:
    """Return implementation code for a named feature."""
    code_map = {
        "turnover_pct_diff": (
            "# Turnover percentage: turnovers per possession\n"
            "if 'tov' in df.columns and 'fga' in df.columns:\n"
            "    possessions = df['fga'] + 0.44 * df.get('fta', 0) + df['tov']\n"
            "    df['turnover_pct'] = np.where(possessions > 0, df['tov'] / possessions, 0.0)\n"
            "elif 'tov_per_g' in df.columns and 'fga_per_g' in df.columns:\n"
            "    poss = df['fga_per_g'] + 0.44 * df.get('fta_per_g', 0) + df['tov_per_g']\n"
            "    df['turnover_pct'] = np.where(poss > 0, df['tov_per_g'] / poss, 0.0)\n"
        ),
        "ft_rate_diff": (
            "# Free throw rate: FTA / FGA\n"
            "if 'fta' in df.columns and 'fga' in df.columns:\n"
            "    df['ft_rate'] = np.where(df['fga'] > 0, df['fta'] / df['fga'], 0.0)\n"
            "elif 'fta_per_g' in df.columns and 'fga_per_g' in df.columns:\n"
            "    df['ft_rate'] = np.where(\n"
            "        df['fga_per_g'] > 0, df['fta_per_g'] / df['fga_per_g'], 0.0\n"
            "    )\n"
        ),
        "oreb_pct_diff": (
            "# Offensive rebound percentage\n"
            "if 'orb_per_g' in df.columns:\n"
            "    df['oreb_pct'] = df['orb_per_g']\n"
            "elif 'orb' in df.columns:\n"
            "    df['oreb_pct'] = df['orb']\n"
        ),
        "assist_rate_diff": (
            "# Assist rate: assists / field goals made\n"
            "if 'ast' in df.columns and 'fg' in df.columns:\n"
            "    df['assist_rate'] = np.where(df['fg'] > 0, df['ast'] / df['fg'], 0.0)\n"
            "elif 'ast_per_g' in df.columns and 'fg_per_g' in df.columns:\n"
            "    df['assist_rate'] = np.where(\n"
            "        df['fg_per_g'] > 0, df['ast_per_g'] / df['fg_per_g'], 0.0\n"
            "    )\n"
        ),
        "block_rate_diff": (
            "# Block rate (blocks per game as proxy)\n"
            "if 'blk_per_g' in df.columns:\n"
            "    df['block_rate'] = df['blk_per_g']\n"
            "elif 'blk' in df.columns:\n"
            "    df['block_rate'] = df['blk']\n"
        ),
        "steal_rate_diff": (
            "# Steal rate (steals per game as proxy)\n"
            "if 'stl_per_g' in df.columns:\n"
            "    df['steal_rate'] = df['stl_per_g']\n"
            "elif 'stl' in df.columns:\n"
            "    df['steal_rate'] = df['stl']\n"
        ),
        "efg_pct_diff": (
            "# Effective field goal percentage: (FG + 0.5 * FG3) / FGA\n"
            "if 'fg' in df.columns and 'fg3' in df.columns and 'fga' in df.columns:\n"
            "    df['efg_pct'] = np.where(\n"
            "        df['fga'] > 0, (df['fg'] + 0.5 * df['fg3']) / df['fga'], 0.0\n"
            "    )\n"
        ),
        "sos_diff": (
            "# Strength of schedule\n"
            "if 'sos' in df.columns:\n"
            "    pass  # Already available\n"
            "elif 'conf_strength' in df.columns:\n"
            "    df['sos'] = df['conf_strength']  # Proxy with conference strength\n"
        ),
        "bench_scoring_pct": (
            "# Bench scoring percentage from player stats\n"
            "# Compute: (total team points - top 5 players' points) / total team points\n"
            "# This is computed in player_features aggregation\n"
        ),
        "fix_zero_variance_pipeline": (
            "# Debug pipeline joins for zero-variance features\n"
            "# Check team name normalization across data sources\n"
        ),
    }

    return code_map.get(name, f"# Implementation needed for: {name}\n")


def _build_diff_summary(changes: list[FeatureChange]) -> str:
    """Build a human-readable summary of all proposed changes."""
    if not changes:
        return "No changes proposed."

    lines = [f"Total changes: {len(changes)}"]
    for change in changes:
        lines.append(
            f"  [{change.change_type.value}] {change.file_path}: {change.description}"
        )
    return "\n".join(lines)
