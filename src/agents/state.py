"""Collaboration state management — load, save, initialize.

State is persisted as JSON in data/agents/state.json and updated after each
iteration. Each iteration's artifacts are stored in data/agents/iteration_NNN/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.agents.schemas import CollaborationState, ModelMetrics, Status

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "data" / "agents"
STATE_PATH = AGENTS_DIR / "state.json"


def init_state(
    baseline_metrics: ModelMetrics | None = None,
    max_iterations: int = 10,
    target_accuracy: float = 0.72,
    target_brier: float = 0.190,
) -> CollaborationState:
    """Create a fresh collaboration state."""
    metrics = baseline_metrics or ModelMetrics()
    return CollaborationState(
        current_iteration=0,
        baseline_metrics=metrics,
        best_metrics=metrics,
        status=Status.NOT_STARTED,
        max_iterations=max_iterations,
        target_accuracy=target_accuracy,
        target_brier=target_brier,
    )


def save_state(state: CollaborationState) -> Path:
    """Persist state to disk."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(state.model_dump_json(indent=2))
    logger.info("State saved to %s (iteration %d)", STATE_PATH, state.current_iteration)
    return STATE_PATH


def load_state() -> CollaborationState | None:
    """Load state from disk, or return None if no state file exists."""
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text())
        return CollaborationState.model_validate(data)
    except Exception:
        logger.exception("Failed to load state from %s", STATE_PATH)
        return None


def iteration_dir(iteration: int) -> Path:
    """Return the artifact directory for a given iteration, creating it if needed."""
    d = AGENTS_DIR / f"iteration_{iteration:03d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_artifact(iteration: int, filename: str, data: str) -> Path:
    """Write a JSON artifact to the iteration directory."""
    d = iteration_dir(iteration)
    path = d / filename
    path.write_text(data)
    logger.info("Artifact saved: %s", path)
    return path


def load_artifact(iteration: int, filename: str) -> str | None:
    """Read a JSON artifact from the iteration directory."""
    path = iteration_dir(iteration) / filename
    if path.exists():
        return path.read_text()
    return None
