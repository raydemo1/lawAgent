"""Schemas for the review evaluation suite (Issue 9)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from law_agent.review.schemas import StrictModel

# ---------------------------------------------------------------------------
# Golden set case schema
# ---------------------------------------------------------------------------

class EvalScenario(StrictModel):
    """A single golden-set scenario for evaluation."""

    case_id: str
    question: str
    material_text: str
    expected_sources: list[str] = Field(
        default_factory=list,
        description="source_id values that should appear in top results",
    )
    expected_citation_roles: list[str] = Field(
        default_factory=list,
        description="citation_role values expected in results",
    )
    should_trigger_second_retrieval: bool = False
    should_abstain: bool = False
    must_not_cite_as_clause: list[str] = Field(
        default_factory=list,
        description="chunk_id values that must NOT appear as can_cite_clause=True",
    )
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-case eval result
# ---------------------------------------------------------------------------

class CaseMetricResult(StrictModel):
    """Metrics for a single scenario case."""

    case_id: str
    recall_at_3: float
    recall_at_5: float
    mrr_at_10: float
    citation_violation_count: int
    abstention_correct: bool
    second_retrieval_correct: bool
    actual_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    is_bad_case: bool = False
    bad_reasons: list[str] = Field(default_factory=list)
    risk_level: str = ""


# ---------------------------------------------------------------------------
# Aggregated metrics
# ---------------------------------------------------------------------------

EvalMode = Literal["keyword", "hybrid"]


class ModeMetrics(StrictModel):
    """Aggregated metrics for one retrieval mode."""

    mode: EvalMode
    mean_recall_at_3: float
    mean_recall_at_5: float
    mean_mrr_at_10: float
    abstention_accuracy: float
    second_retrieval_accuracy: float
    total_citation_violations: int
    bad_case_count: int
    total_cases: int


class EvalSummary(StrictModel):
    """Full evaluation summary output."""

    generated_at: str
    chunks_path: str
    cases_path: str
    mode_metrics: dict[str, ModeMetrics] = Field(default_factory=dict)
    bad_cases: list[CaseMetricResult] = Field(default_factory=list)
    all_case_results: dict[str, list[CaseMetricResult]] = Field(default_factory=dict)
