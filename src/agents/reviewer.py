"""Reviewer agent — analyzes feature quality and identifies gaps.

The Reviewer reads the validation report, training data, and model feature
importances to produce a ReviewReport identifying what to fix or improve.
"""

from __future__ import annotations

import logging

from src.agents.schemas import FeatureIssue, ModelMetrics, ReviewReport
from src.agents.utils import (
    get_feature_importances,
    get_matchup_feature_definitions,
    get_training_data_summary,
    get_validation_report,
)

logger = logging.getLogger(__name__)


def run_reviewer(iteration: int, current_metrics: ModelMetrics) -> ReviewReport:
    """Analyze current feature quality and produce a ReviewReport.

    Reads from:
    - validation_report.json
    - matchup_training.parquet (summary)
    - Trained model feature importances

    Returns a ReviewReport with gaps and priority actions.
    """
    logger.info("Reviewer: analyzing features for iteration %d", iteration)

    # Gather inputs
    val_report = get_validation_report()
    data_summary = get_training_data_summary()
    importances = get_feature_importances()
    feature_defs = get_matchup_feature_definitions()

    # Identify issues
    issues: list[FeatureIssue] = []

    # Zero-variance features
    zero_var = val_report.get("zero_variance_features", [])
    for f in zero_var:
        issues.append(FeatureIssue(
            feature_name=f,
            issue_type="zero_variance",
            severity="high",
            detail=f"Feature '{f}' has near-zero variance (std < 0.01) and contributes no signal.",
        ))

    # High-null features
    null_audit = val_report.get("null_audit", {})
    high_null = [col for col, pct in null_audit.items() if pct > 0.20]
    for f in high_null:
        pct = null_audit[f]
        issues.append(FeatureIssue(
            feature_name=f,
            issue_type="high_null",
            severity="high" if pct > 0.50 else "medium",
            detail=f"Feature '{f}' has {pct:.1%} missing values.",
        ))

    # Weak target correlation
    weak_features = list(val_report.get("weak_target_features", {}).keys())
    for f in weak_features:
        corr = val_report["weak_target_features"][f]
        issues.append(FeatureIssue(
            feature_name=f,
            issue_type="weak_correlation",
            severity="low",
            detail=f"Feature '{f}' has near-zero target correlation ({corr:.6f}).",
        ))

    # Identify gaps — features that basketball domain expects but don't exist
    gaps = _identify_gaps(feature_defs, importances, val_report)

    # Priority actions based on issues
    priorities = _prioritize_actions(issues, gaps, importances)

    report = ReviewReport(
        iteration=iteration,
        metrics=current_metrics,
        zero_variance=zero_var,
        high_null=[col for col in high_null],
        weak_features=weak_features,
        feature_importances=importances,
        gaps_identified=gaps,
        priority_actions=priorities,
        issues=issues,
        total_features=len(data_summary.get("numeric_columns", [])),
        total_training_rows=data_summary.get("shape", {}).get("rows", 0),
    )

    logger.info(
        "Reviewer: %d issues found, %d gaps identified, %d priority actions",
        len(issues),
        len(gaps),
        len(priorities),
    )
    return report


def _identify_gaps(
    feature_defs: dict,
    importances: dict[str, float],
    val_report: dict,
) -> list[str]:
    """Identify missing feature areas based on domain knowledge."""
    gaps: list[str] = []

    existing_diff = set(feature_defs.get("diff_features", {}).keys())
    existing_raw = set(feature_defs.get("raw_feature_cols", []))

    # Check for basketball-relevant features that are absent
    desired_features = {
        "ft_rate_diff": "Free throw rate differential — crucial in close tournament games",
        "turnover_pct_diff": "Turnover percentage differential — pressure-related turnovers rise in March",
        "oreb_pct_diff": "Offensive rebound percentage — second chances matter in single-elimination",
        "assist_rate_diff": "Assist rate differential — ball movement quality indicator",
        "block_rate_diff": "Block rate differential — rim protection in half-court sets",
        "steal_rate_diff": "Steal rate differential — defensive pressure causing turnovers",
        "bench_scoring_diff": "Bench scoring differential — depth matters in back-to-back games",
        "sos_diff": "Strength of schedule differential — contextualizes win/loss records",
        "coach_tourney_exp_diff": "Coach tournament experience — managing pressure situations",
        "wins_diff": "Win count differential — raw record comparison",
        "def_reb_pct_diff": "Defensive rebound percentage — limiting second chances",
    }

    for feat_name, reason in desired_features.items():
        if feat_name not in existing_diff:
            gaps.append(f"Missing: {feat_name} — {reason}")

    # Check for zero-variance features that need replacement
    zero_var = val_report.get("zero_variance_features", [])
    if zero_var:
        gaps.append(
            f"Replace zero-variance features ({', '.join(zero_var)}) with "
            "properly computed alternatives"
        )

    # Check for high-null features that need better imputation or replacement
    null_audit = val_report.get("null_audit", {})
    severe_null = [col for col, pct in null_audit.items() if pct > 0.50]
    if severe_null:
        gaps.append(
            f"Fix data pipeline for severely missing features ({', '.join(severe_null)})"
        )

    return gaps


def _prioritize_actions(
    issues: list[FeatureIssue],
    gaps: list[str],
    importances: dict[str, float],
) -> list[str]:
    """Rank actions by expected impact on model performance."""
    priorities: list[str] = []

    # 1. Fix zero-variance features (currently contributing nothing)
    zero_var_issues = [i for i in issues if i.issue_type == "zero_variance"]
    if zero_var_issues:
        names = [i.feature_name for i in zero_var_issues]
        priorities.append(
            f"HIGH: Fix zero-variance features ({', '.join(names)}) — "
            "these features are dropped by auto-clean and contribute no signal"
        )

    # 2. Fix high-null features
    high_null_issues = [i for i in issues if i.issue_type == "high_null" and i.severity == "high"]
    if high_null_issues:
        names = [i.feature_name for i in high_null_issues]
        priorities.append(
            f"HIGH: Fix severely missing features ({', '.join(names)}) — "
            "over 50% data is missing"
        )

    # 3. Add high-impact domain features
    offensive_gaps = [g for g in gaps if any(k in g.lower() for k in ["turnover", "assist", "ft_rate", "oreb"])]
    if offensive_gaps:
        priorities.append(
            "MEDIUM: Add offensive efficiency features (FT rate, turnover %, "
            "offensive rebound %, assist rate) — strong tournament predictors"
        )

    defensive_gaps = [g for g in gaps if any(k in g.lower() for k in ["block", "steal", "def_reb"])]
    if defensive_gaps:
        priorities.append(
            "MEDIUM: Add defensive features (block rate, steal rate, "
            "defensive rebound %) — defense wins championships in March"
        )

    # 4. Experience and context features
    context_gaps = [g for g in gaps if any(k in g.lower() for k in ["coach", "sos", "bench"])]
    if context_gaps:
        priorities.append(
            "LOW: Add contextual features (coach experience, SOS, bench depth) — "
            "secondary signals for upset prediction"
        )

    return priorities
