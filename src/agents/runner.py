"""Main collaboration loop — orchestrates all four agents iteratively.

Each iteration:
1. Supervisor decides focus area
2. Reviewer analyzes features and produces quality report
3. Basketball Analyst generates domain-informed suggestions
4. Feature Agent implements code changes (proposal only — no auto-apply)
5. Re-run pipeline to get new LOSO metrics
6. Supervisor accepts/rejects and updates state

All artifacts are persisted to data/agents/iteration_NNN/.
"""

from __future__ import annotations

import logging

from src.agents.basketball_analyst import run_basketball_analyst
from src.agents.feature_agent import run_feature_agent
from src.agents.reviewer import run_reviewer
from src.agents.schemas import CollaborationState, ModelMetrics, NextAction, Status
from src.agents.state import (
    init_state,
    iteration_dir,
    load_state,
    save_artifact,
    save_state,
)
from src.agents.supervisor import decide_focus, evaluate_iteration, update_state
from src.agents.utils import get_current_metrics

logger = logging.getLogger(__name__)


def run_collaboration_loop(
    max_iterations: int = 10,
    target_accuracy: float = 0.72,
    target_brier: float = 0.190,
    resume: bool = False,
) -> CollaborationState:
    """Run the multi-agent collaboration loop.

    Parameters
    ----------
    max_iterations : int
        Maximum number of iterations before stopping.
    target_accuracy : float
        Stop when LOSO accuracy reaches this threshold.
    target_brier : float
        Stop when LOSO Brier score reaches this threshold.
    resume : bool
        If True, resume from saved state. Otherwise start fresh.

    Returns
    -------
    CollaborationState
        Final state with history and best metrics.
    """
    # Initialize or resume state
    state = None
    if resume:
        state = load_state()
        if state is not None:
            logger.info(
                "Resuming from iteration %d (status: %s)",
                state.current_iteration,
                state.status.value,
            )

    if state is None:
        logger.info("Starting fresh collaboration loop")
        logger.info("Getting baseline metrics ...")
        baseline = get_current_metrics()
        logger.info(
            "Baseline: accuracy=%.4f, brier=%.4f, auc_roc=%.4f, log_loss=%.4f",
            baseline.accuracy,
            baseline.brier_score,
            baseline.auc_roc,
            baseline.log_loss,
        )
        state = init_state(
            baseline_metrics=baseline,
            max_iterations=max_iterations,
            target_accuracy=target_accuracy,
            target_brier=target_brier,
        )

    state.status = Status.RUNNING
    save_state(state)

    # Main loop
    while state.current_iteration < max_iterations:
        state.current_iteration += 1
        iteration = state.current_iteration

        logger.info("=" * 60)
        logger.info("ITERATION %d / %d", iteration, max_iterations)
        logger.info("=" * 60)

        try:
            decision = _run_single_iteration(state, iteration)
        except Exception:
            logger.exception("Iteration %d failed", iteration)
            state.status = Status.FAILED
            save_state(state)
            break

        # Update state
        state = update_state(
            state,
            decision,
            new_features=decision.focus_area.split(", ") if decision.accepted else [],
            removed_features=[],
        )
        save_state(state)

        # Check stop conditions
        if decision.next_action != NextAction.CONTINUE and decision.next_action != NextAction.ROLLBACK_AND_RETRY:
            logger.info("Stopping: %s", decision.next_action.value)
            break

        if decision.next_action == NextAction.ROLLBACK_AND_RETRY:
            logger.info(
                "Iteration %d rejected (stall %d/%d). Will retry with different focus.",
                iteration,
                state.stalled_count,
                state.max_stalls,
            )
            if state.stalled_count >= state.max_stalls:
                logger.info("Max stalls reached. Stopping.")
                state.status = Status.STALLED
                save_state(state)
                break

    # Final summary
    _print_summary(state)
    return state


def _run_single_iteration(
    state: CollaborationState,
    iteration: int,
) -> ...:
    """Execute one full iteration of the agent loop."""
    # Metrics before this iteration
    metrics_before = state.best_metrics if state.history else state.baseline_metrics

    # Step 1: Supervisor decides focus
    focus = decide_focus(state)
    logger.info("Focus: %s", focus)
    save_artifact(iteration, "focus.txt", focus)

    # Step 2: Reviewer analyzes features
    logger.info("Running Reviewer ...")
    review_report = run_reviewer(iteration, metrics_before)
    save_artifact(iteration, "review_report.json", review_report.model_dump_json(indent=2))

    # Step 3: Basketball Analyst generates suggestions
    logger.info("Running Basketball Analyst ...")
    analyst_suggestion = run_basketball_analyst(iteration, review_report)
    save_artifact(
        iteration,
        "analyst_suggestion.json",
        analyst_suggestion.model_dump_json(indent=2),
    )

    # Step 4: Feature Agent generates proposal
    logger.info("Running Feature Agent ...")
    feature_proposal = run_feature_agent(iteration, review_report, analyst_suggestion)
    save_artifact(
        iteration,
        "feature_proposal.json",
        feature_proposal.model_dump_json(indent=2),
    )

    # Step 5: Re-run pipeline (note: Feature Agent produces proposals but does
    # not auto-apply them — metrics_after will equal metrics_before until
    # proposals are applied manually or by an auto-apply step)
    logger.info("Re-running evaluation pipeline ...")
    try:
        metrics_after = get_current_metrics()
    except Exception:
        logger.exception("Evaluation pipeline failed; using previous metrics")
        metrics_after = metrics_before

    # Step 6: Supervisor evaluates
    logger.info("Running Supervisor evaluation ...")
    decision = evaluate_iteration(
        state=state,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        new_features=feature_proposal.new_features,
        removed_features=feature_proposal.removed_features,
    )
    save_artifact(
        iteration,
        "supervisor_decision.json",
        decision.model_dump_json(indent=2),
    )

    return decision


def _print_summary(state: CollaborationState) -> None:
    """Print a summary of the collaboration run."""
    logger.info("=" * 60)
    logger.info("COLLABORATION SUMMARY")
    logger.info("=" * 60)
    logger.info("Status: %s", state.status.value)
    logger.info("Total iterations: %d", state.current_iteration)
    logger.info(
        "Baseline: accuracy=%.4f, brier=%.4f",
        state.baseline_metrics.accuracy,
        state.baseline_metrics.brier_score,
    )
    logger.info(
        "Best: accuracy=%.4f, brier=%.4f",
        state.best_metrics.accuracy,
        state.best_metrics.brier_score,
    )

    accepted = sum(1 for r in state.history if r.accepted)
    rejected = sum(1 for r in state.history if not r.accepted)
    logger.info("Accepted iterations: %d, Rejected: %d", accepted, rejected)

    if state.history:
        logger.info("History:")
        for record in state.history:
            status = "ACCEPTED" if record.accepted else "REJECTED"
            logger.info(
                "  Iteration %d: %s — accuracy=%.4f, brier=%.4f — %s",
                record.iteration,
                status,
                record.metrics.accuracy,
                record.metrics.brier_score,
                record.reason,
            )
