"""Per-review lightweight telemetry counters."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class WorkflowTelemetry:
    """Counters for one review workflow execution."""

    llm_call_count: int = 0
    retry_count: int = 0


_current: ContextVar[WorkflowTelemetry] = ContextVar(
    "lawagent_review_telemetry",
    default=WorkflowTelemetry(),
)


def reset_telemetry() -> WorkflowTelemetry:
    """Reset counters for the current execution context."""

    telemetry = WorkflowTelemetry()
    _current.set(telemetry)
    return telemetry


def current_telemetry() -> WorkflowTelemetry:
    """Return counters for the current execution context."""

    return _current.get()


def record_llm_call() -> None:
    """Record one attempted LLM call."""

    _current.get().llm_call_count += 1


def record_retry() -> None:
    """Record one retry after a failed call or validation."""

    _current.get().retry_count += 1
