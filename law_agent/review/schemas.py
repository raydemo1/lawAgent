"""Schemas for material-driven compliance review runs."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from law_agent.data.schemas import ClauseCitationRole, StrictModel

ReviewInputMode = Literal["pasted_text", "uploaded_file"]
RiskLevel = Literal["high", "medium", "low", "insufficient_evidence"]
RetrievalQueryType = Literal[
    "legal_issue",
    "material_fact",
    "region_condition",
    "industry_condition",
    "missing_information",
]
RetrieverName = Literal["keyword", "vector_mock", "hybrid"]
EvidenceStatus = Literal["not_checked", "sufficient", "needs_second_retrieval", "insufficient"]
CitationUsage = Literal[
    "legal_basis",
    "conditional_basis",
    "implementation_reference",
    "policy_explanation",
]


class ReviewFacts(StrictModel):
    """Structured facts extracted from user material."""

    business_activity: str | None = None
    data_types: list[str] = Field(default_factory=list)
    sensitive_personal_info: bool | None = None
    cross_border_transfer: bool | None = None
    overseas_recipient: str | None = None
    processing_purpose: str | None = None
    legal_basis_or_consent: str | None = None
    industry: str | None = None
    region: str | None = None
    missing_information: list[str] = Field(default_factory=list)


class UploadedFileMeta(StrictModel):
    """Metadata for a local file used as review material."""

    filename: str
    local_path: str
    raw_format: str


class MaterialRecord(StrictModel):
    """Normalized review material input."""

    input_mode: ReviewInputMode = "pasted_text"
    material_text: str
    source_name: str | None = None
    parser: str = "pasted_text"
    parser_version: str = "0.1.0"
    uploaded_file: UploadedFileMeta | None = None

    @field_validator("material_text")
    @classmethod
    def material_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("material_text must not be blank")
        return value


class RetrievalQuery(StrictModel):
    """A typed query generated for retrieval."""

    query_id: str
    query_type: RetrievalQueryType
    text: str


class RetrievalHit(StrictModel):
    """A scored evidence hit returned by a retriever."""

    chunk_id: str
    doc_id: str
    source_id: str
    title: str
    text: str
    score: float
    rank: int
    retriever: RetrieverName
    citation_role: ClauseCitationRole
    can_cite_clause: bool
    source_url: str
    matched_query_type: RetrievalQueryType | None = None


class EvidenceSelfCheck(StrictModel):
    """Evidence sufficiency state for a review trace."""

    status: EvidenceStatus
    issues: list[str] = Field(default_factory=list)
    second_retrieval_triggered: bool = False


class Citation(StrictModel):
    """A governed citation selected for a review result."""

    source_id: str
    chunk_id: str
    title: str
    source_url: str
    citation_role: ClauseCitationRole
    can_cite_clause: bool
    usage: CitationUsage
    citation_label: str | None = None


class ReviewResult(StrictModel):
    """Structured review result produced from facts and evidence."""

    review_result_id: str
    review_case_id: str
    trace_id: str
    risk_level: RiskLevel
    conclusion: str
    review_facts: ReviewFacts
    trigger_reasons: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    risk_boundaries: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class ReviewCase(StrictModel):
    """A material-driven compliance review case."""

    review_case_id: str
    created_at: str
    question: str
    material: MaterialRecord
    review_facts: ReviewFacts
    trace_id: str
    latest_result_id: str | None = None
    user_feedback: dict[str, str] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class RetrievalTrace(StrictModel):
    """Verbose retrieval and evidence trace for review debugging and eval."""

    trace_id: str
    review_case_id: str
    created_at: str
    evidence_self_check: EvidenceSelfCheck
    queries: list[RetrievalQuery] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)
    metadata_boosts: dict[str, float] = Field(default_factory=dict)
    keyword_results: list[RetrievalHit] = Field(default_factory=list)
    vector_results: list[RetrievalHit] = Field(default_factory=list)
    hybrid_results: list[RetrievalHit] = Field(default_factory=list)
    neighbor_chunks: list[RetrievalHit] = Field(default_factory=list)
    second_retrieval: dict[str, object] = Field(default_factory=dict)
    final_evidence: list[RetrievalHit] = Field(default_factory=list)
    citation_validation: dict[str, object] = Field(default_factory=dict)
    latency_ms: int | None = None


class ReviewRunResponse(StrictModel):
    """Response returned after creating a review skeleton."""

    review_case: ReviewCase
    trace: RetrievalTrace
    result: ReviewResult
    case_path: Path
    trace_path: Path
    result_path: Path
