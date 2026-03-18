"""Pydantic models for inter-agent communication artifacts.

Each agent reads the prior agent's output and writes its own structured artifact.
These schemas ensure valid handoffs and provide a full audit trail.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class ModelMetrics(BaseModel):
    """Standard evaluation metrics from LOSO CV."""

    accuracy: float = 0.0
    brier_score: float = 1.0
    log_loss: float = 1.0
    auc_roc: float = 0.5


class MetricsDelta(BaseModel):
    """Change in metrics between iterations."""

    accuracy_delta: float = 0.0
    brier_delta: float = 0.0
    log_loss_delta: float = 0.0
    auc_roc_delta: float = 0.0


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


class FeatureIssue(BaseModel):
    """A single feature quality issue identified by the Reviewer."""

    feature_name: str
    issue_type: str = Field(
        description="One of: zero_variance, high_null, weak_correlation, high_vif, skewed"
    )
    severity: str = Field(default="medium", description="low, medium, or high")
    detail: str = ""


class ReviewReport(BaseModel):
    """Output of the Reviewer agent."""

    iteration: int
    metrics: ModelMetrics
    zero_variance: list[str] = Field(default_factory=list)
    high_null: list[str] = Field(default_factory=list)
    weak_features: list[str] = Field(default_factory=list)
    feature_importances: dict[str, float] = Field(default_factory=dict)
    gaps_identified: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    issues: list[FeatureIssue] = Field(default_factory=list)
    total_features: int = 0
    total_training_rows: int = 0


# ---------------------------------------------------------------------------
# Basketball Analyst
# ---------------------------------------------------------------------------


class FeatureSuggestion(BaseModel):
    """A single feature idea from the Basketball Analyst."""

    name: str
    description: str
    data_source: str = Field(
        description="Which existing data source provides the raw data "
        "(e.g., torvik_ratings, team_stats, player_stats)"
    )
    implementation_hint: str = ""
    expected_impact: str = Field(
        default="medium", description="low, medium, or high expected predictive impact"
    )
    rationale: str = ""


class AnalystSuggestion(BaseModel):
    """Output of the Basketball Analyst agent."""

    iteration: int
    responding_to_gaps: list[str] = Field(default_factory=list)
    feature_suggestions: list[FeatureSuggestion] = Field(default_factory=list)
    domain_rationale: str = ""


# ---------------------------------------------------------------------------
# Feature Agent
# ---------------------------------------------------------------------------


class ChangeType(str, Enum):
    ADD = "add"
    MODIFY = "modify"
    REMOVE = "remove"


class FeatureChange(BaseModel):
    """A single code change proposed by the Feature Agent."""

    file_path: str
    change_type: ChangeType
    description: str
    code_snippet: str = ""


class FeatureProposal(BaseModel):
    """Output of the Feature Agent."""

    iteration: int
    changes: list[FeatureChange] = Field(default_factory=list)
    new_features: list[str] = Field(default_factory=list)
    modified_features: list[str] = Field(default_factory=list)
    removed_features: list[str] = Field(default_factory=list)
    code_diff_summary: str = ""


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


class NextAction(str, Enum):
    CONTINUE = "continue"
    STOP_TARGET_REACHED = "stop_target_reached"
    STOP_MAX_ITERATIONS = "stop_max_iterations"
    STOP_STALLED = "stop_stalled"
    ROLLBACK_AND_RETRY = "rollback_and_retry"


class SupervisorDecision(BaseModel):
    """Output of the Supervisor agent."""

    iteration: int
    accepted: bool
    reason: str
    metrics_before: ModelMetrics
    metrics_after: ModelMetrics
    delta: MetricsDelta
    next_action: NextAction = NextAction.CONTINUE
    focus_area: str = ""


# ---------------------------------------------------------------------------
# Collaboration State
# ---------------------------------------------------------------------------


class IterationRecord(BaseModel):
    """Record of a single iteration for the history log."""

    iteration: int
    accepted: bool
    metrics: ModelMetrics
    features_added: list[str] = Field(default_factory=list)
    features_removed: list[str] = Field(default_factory=list)
    reason: str = ""


class Status(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    STALLED = "stalled"
    FAILED = "failed"


class CollaborationState(BaseModel):
    """Persistent state across the collaboration loop."""

    current_iteration: int = 0
    baseline_metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    best_metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    history: list[IterationRecord] = Field(default_factory=list)
    stalled_count: int = 0
    status: Status = Status.NOT_STARTED

    # Targets
    target_accuracy: float = 0.72
    target_brier: float = 0.190
    max_iterations: int = 10
    max_stalls: int = 3
