"""Schemas for the LegalBench-RAG retrieval-only benchmark."""

from __future__ import annotations

from pydantic import Field

from law_agent.data.schemas import StrictModel


class LegalBenchSnippet(StrictModel):
    file_path: str
    span: tuple[int, int]


class LegalBenchQuery(StrictModel):
    query_id: str
    query: str
    snippets: list[LegalBenchSnippet]
    tags: list[str] = Field(default_factory=list)


class LegalBenchDocument(StrictModel):
    file_path: str
    text: str


class LegalBenchChunkMeta(StrictModel):
    chunk_id: str
    file_path: str
    char_start: int
    char_end: int


class LegalBenchCaseResult(StrictModel):
    query_id: str
    query: str
    tags: list[str] = Field(default_factory=list)
    doc_hit_rank: int | None = None
    span_hit_rank: int | None = None
    doc_recall_at_5: bool
    doc_recall_at_10: bool
    span_recall_at_5: bool
    span_recall_at_10: bool
    best_span_overlap: float
    precision_at_10: float
    latency_ms: int
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)


class LegalBenchEvalSummary(StrictModel):
    generated_at: str
    data_dir: str
    chunks_path: str
    chunk_meta_path: str
    top_k: int
    candidate_top_k: int
    total_cases: int
    doc_recall_at_5: float
    doc_recall_at_10: float
    span_recall_at_5: float
    span_recall_at_10: float
    mrr_at_10: float
    mean_best_span_overlap: float
    mean_precision_at_10: float
    avg_latency_ms: float
    bad_case_count: int
    bad_cases: list[LegalBenchCaseResult] = Field(default_factory=list)
    all_case_results: list[LegalBenchCaseResult] = Field(default_factory=list)
