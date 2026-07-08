"""Schemas for the review evaluation suite (Issue 9)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from law_agent.review.schemas import StrictModel

BadCaseCategory = Literal[
    "retrieval_zero_recall",
    "retrieval_low_recall",
    "candidate_missing",
    "abstention_error",
    "citation_gate_error",
]

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
    should_abstain: bool = False
    min_recall_at_5: float = Field(
        default=0.5,
        description="Minimum Recall@5 before a non-abstention case is considered bad.",
    )
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
    candidate_recall_at_50: float = 0.0
    distinct_source_recall_at_5: float = 0.0
    duplicate_source_count_at_10: int = 0
    citation_violation_count: int
    abstention_correct: bool
    # Fact only: did the pipeline trigger second retrieval? No expectation
    # comparison, no bad-case weight — purely diagnostic.
    second_retrieval_triggered: bool = False
    actual_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    is_bad_case: bool = False
    bad_reasons: list[str] = Field(default_factory=list)
    bad_case_categories: list[BadCaseCategory] = Field(default_factory=list)
    risk_level: str = ""


# ---------------------------------------------------------------------------
# Aggregated metrics
# ---------------------------------------------------------------------------

class ModeMetrics(StrictModel):
    """Aggregated metrics for one retrieval mode."""

    mode: str
    mean_recall_at_3: float
    mean_recall_at_5: float
    mean_mrr_at_10: float
    mean_candidate_recall_at_50: float = 0.0
    mean_distinct_source_recall_at_5: float = 0.0
    mean_duplicate_source_count_at_10: float = 0.0
    abstention_accuracy: float
    # Diagnostic only: fraction of cases where second retrieval fired.
    second_retrieval_trigger_rate: float = 0.0
    total_citation_violations: int
    bad_case_count: int
    bad_case_taxonomy: dict[str, int] = Field(default_factory=dict)
    total_cases: int


class EvalSummary(StrictModel):
    """Full evaluation summary output."""

    generated_at: str
    chunks_path: str
    cases_path: str
    mode_metrics: dict[str, ModeMetrics] = Field(default_factory=dict)
    bad_cases: list[CaseMetricResult] = Field(default_factory=list)
    all_case_results: dict[str, list[CaseMetricResult]] = Field(default_factory=dict)
