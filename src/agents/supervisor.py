"""Supervisor agent — orchestrates the collaboration loop.

Decides the focus area for each iteration, evaluates results, and
determines whether to accept/reject changes.
"""

from __future__ import annotations

import logging

from src.agents.schemas import (
    CollaborationState,
    IterationRecord,
    MetricsDelta,
    ModelMetrics,
    NextAction,
    Status,
    SupervisorDecision,
)
from src.agents.utils import check_guardrails

logger = logging.getLogger(__name__)

# Accept criteria
MIN_BRIER_IMPROVEMENT = 0.002
MIN_ACCURACY_IMPROVEMENT = 0.005  # 0.5%


def decide_focus(state: CollaborationState) -> str:
    """Decide what the next iteration should focus on.

    Uses the history of past iterations to guide focus:
    - First iteration: fix zero-variance / high-null features
    - Subsequent: add new features based on gaps
    - If stalled: try different approach
    """
    iteration = state.current_iteration + 1

    if iteration == 1:
        return (
            "Fix data pipeline issues: zero-variance features (roster_continuity, "
            "experience_score, last10_winpct) and high-null features. These are "
            "currently dropped by auto-clean and represent lost signal."
        )

    if state.stalled_count >= 2:
        return (
            "Previous approaches stalled. Try a different strategy: "
            "consider removing weakly correlated features, or combine existing "
            "features into interaction terms, or focus on feature engineering "
            "from a different data source."
        )

    # Check what was tried before
    past_features = set()
    for record in state.history:
        past_features.update(record.features_added)

    if not past_features:
        return (
            "Add high-impact offensive efficiency features: turnover percentage, "
            "free throw rate, effective field goal percentage. These are strong "
            "tournament predictors based on basketball domain knowledge."
        )

    return (
        "Continue adding features based on remaining gaps. Focus on defensive "
        "features (block rate, steal rate) or contextual features (SOS, coaching "
        "experience) that haven't been tried yet."
    )


def evaluate_iteration(
    state: CollaborationState,
    metrics_before: ModelMetrics,
    metrics_after: ModelMetrics,
    new_features: list[str],
    removed_features: list[str],
) -> SupervisorDecision:
    """Evaluate whether an iteration's changes should be accepted.

    Accept criteria:
    - Brier score improves >= 0.002, OR
    - Accuracy improves >= 0.5%
    - WITHOUT degrading the other metric significantly
    - Guard rails must pass (AUC-ROC drop <= 0.01, log loss increase <= 0.02)
    """
    iteration = state.current_iteration

    delta = MetricsDelta(
        accuracy_delta=metrics_after.accuracy - metrics_before.accuracy,
        brier_delta=metrics_after.brier_score - metrics_before.brier_score,
        log_loss_delta=metrics_after.log_loss - metrics_before.log_loss,
        auc_roc_delta=metrics_after.auc_roc - metrics_before.auc_roc,
    )

    # Check guard rails first
    guardrails_passed, guardrails_reason = check_guardrails(metrics_before, metrics_after)
    if not guardrails_passed:
        return SupervisorDecision(
            iteration=iteration,
            accepted=False,
            reason=f"Guard rails violated: {guardrails_reason}",
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            delta=delta,
            next_action=NextAction.ROLLBACK_AND_RETRY,
        )

    # Check accept criteria
    # Brier score: LOWER is better, so improvement = negative delta
    brier_improved = -delta.brier_delta >= MIN_BRIER_IMPROVEMENT
    accuracy_improved = delta.accuracy_delta >= MIN_ACCURACY_IMPROVEMENT

    # Check for degradation
    brier_degraded = delta.brier_delta > MIN_BRIER_IMPROVEMENT  # Got worse
    accuracy_degraded = -delta.accuracy_delta > MIN_ACCURACY_IMPROVEMENT  # Got worse

    accepted = False
    reason = ""

    if brier_improved and not accuracy_degraded:
        accepted = True
        reason = (
            f"Accepted: Brier score improved by {-delta.brier_delta:.4f} "
            f"(threshold: {MIN_BRIER_IMPROVEMENT})"
        )
    elif accuracy_improved and not brier_degraded:
        accepted = True
        reason = (
            f"Accepted: Accuracy improved by {delta.accuracy_delta:.4f} "
            f"({delta.accuracy_delta * 100:.1f}%, threshold: {MIN_ACCURACY_IMPROVEMENT * 100:.1f}%)"
        )
    elif brier_improved and accuracy_improved:
        accepted = True
        reason = "Accepted: Both Brier score and accuracy improved"
    else:
        reason = (
            f"Rejected: Neither metric met threshold. "
            f"Brier delta: {delta.brier_delta:+.4f} (need <= {-MIN_BRIER_IMPROVEMENT}), "
            f"Accuracy delta: {delta.accuracy_delta:+.4f} (need >= {MIN_ACCURACY_IMPROVEMENT})"
        )

    # Determine next action
    next_action = _determine_next_action(state, accepted, metrics_after)

    decision = SupervisorDecision(
        iteration=iteration,
        accepted=accepted,
        reason=reason,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        delta=delta,
        next_action=next_action,
        focus_area=decide_focus(state) if next_action == NextAction.CONTINUE else "",
    )

    logger.info(
        "Supervisor: iteration %d %s — %s (next: %s)",
        iteration,
        "ACCEPTED" if accepted else "REJECTED",
        reason,
        next_action.value,
    )
    return decision


def update_state(
    state: CollaborationState,
    decision: SupervisorDecision,
    new_features: list[str],
    removed_features: list[str],
) -> CollaborationState:
    """Update the collaboration state after an iteration."""
    record = IterationRecord(
        iteration=state.current_iteration,
        accepted=decision.accepted,
        metrics=decision.metrics_after,
        features_added=new_features if decision.accepted else [],
        features_removed=removed_features if decision.accepted else [],
        reason=decision.reason,
    )
    state.history.append(record)

    if decision.accepted:
        state.stalled_count = 0
        # Update best metrics if this iteration is better
        if decision.metrics_after.brier_score < state.best_metrics.brier_score:
            state.best_metrics = decision.metrics_after
    else:
        state.stalled_count += 1

    # Update status based on next action
    if decision.next_action in (
        NextAction.STOP_TARGET_REACHED,
        NextAction.STOP_MAX_ITERATIONS,
        NextAction.STOP_STALLED,
    ):
        state.status = Status.COMPLETED
    elif decision.next_action == NextAction.CONTINUE:
        state.status = Status.RUNNING
    elif state.stalled_count >= state.max_stalls:
        state.status = Status.STALLED

    return state


def _determine_next_action(
    state: CollaborationState,
    accepted: bool,
    metrics_after: ModelMetrics,
) -> NextAction:
    """Decide whether to continue, stop, or rollback."""
    # Check if targets are reached
    if (
        metrics_after.accuracy >= state.target_accuracy
        and metrics_after.brier_score <= state.target_brier
    ):
        return NextAction.STOP_TARGET_REACHED

    # Check max iterations
    if state.current_iteration >= state.max_iterations:
        return NextAction.STOP_MAX_ITERATIONS

    # Check stall count (including this iteration if rejected)
    stalls = state.stalled_count + (0 if accepted else 1)
    if stalls >= state.max_stalls:
        return NextAction.STOP_STALLED

    # If rejected, rollback and try a different approach
    if not accepted:
        return NextAction.ROLLBACK_AND_RETRY

    return NextAction.CONTINUE
