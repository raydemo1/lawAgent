"""Application services for material-driven review runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from law_agent.review.facts import FactsExtractor, extract_facts
from law_agent.review.ids import make_id, utc_now_iso
from law_agent.review.io import (
    read_retrieval_traces,
    review_cases_path,
    review_results_path,
    retrieval_traces_path,
    write_review_cases,
    write_review_results,
    write_retrieval_traces,
)
from law_agent.review.materials import material_from_text
from law_agent.review.query_planner import QueryPlanner, plan_queries
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH, CorpusError, load_corpus
from law_agent.review.retrieval.keyword import KeywordRetriever, merge_hits_by_chunk_id
from law_agent.review.schemas import (
    EvidenceSelfCheck,
    MaterialRecord,
    ReviewCase,
    ReviewFacts,
    ReviewResult,
    ReviewRunResponse,
    RetrievalHit,
    RetrievalQuery,
    RetrievalTrace,
)

DEFAULT_REVIEW_RUNS_DIR = Path("artifacts/review_runs")
PLACEHOLDER_CONCLUSION = "Review case created. Evidence retrieval has not run yet."
DEFAULT_TOP_K = 10


def _validate_non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def create_review_case(
    *,
    question: str,
    material_text: str | None = None,
    material: MaterialRecord | None = None,
    output_dir: Path = DEFAULT_REVIEW_RUNS_DIR,
    now: Callable[[], str] = utc_now_iso,
    id_factory: Callable[[str], str] = make_id,
    facts_extractor: FactsExtractor = extract_facts,
    query_planner: QueryPlanner = plan_queries,
) -> ReviewRunResponse:
    """Create and persist a review case with extracted facts and planned queries.

    Issue 4 integration: facts are extracted from the material text and typed
    retrieval queries are planned from the question plus facts. Both are
    persisted into the review case and retrieval trace. Evidence retrieval,
    self-check, and result generation remain placeholder states for later
    issues.
    """

    question = _validate_non_blank(question, "question")
    if material is None:
        if material_text is None:
            raise ValueError("material_text is required")
        material = material_from_text(_validate_non_blank(material_text, "material_text"))
    elif material_text is not None:
        raise ValueError("provide either material or material_text, not both")

    created_at = now()
    review_case_id = id_factory("review")
    trace_id = id_factory("trace")
    review_result_id = id_factory("result")

    facts = facts_extractor(material.material_text, question)
    queries: list[RetrievalQuery] = query_planner(question, facts, material.material_text)

    result = ReviewResult(
        review_result_id=review_result_id,
        review_case_id=review_case_id,
        trace_id=trace_id,
        risk_level="insufficient_evidence",
        conclusion=PLACEHOLDER_CONCLUSION,
        review_facts=facts,
    )
    case = ReviewCase(
        review_case_id=review_case_id,
        created_at=created_at,
        question=question,
        material=material,
        review_facts=facts,
        trace_id=trace_id,
        latest_result_id=review_result_id,
    )
    trace = RetrievalTrace(
        trace_id=trace_id,
        review_case_id=review_case_id,
        created_at=created_at,
        evidence_self_check=EvidenceSelfCheck(status="not_checked"),
        queries=queries,
    )

    case_path = review_cases_path(output_dir)
    trace_path = retrieval_traces_path(output_dir)
    result_path = review_results_path(output_dir)
    write_review_cases(case_path, [case])
    write_retrieval_traces(trace_path, [trace])
    write_review_results(result_path, [result])

    return ReviewRunResponse(
        review_case=case,
        trace=trace,
        result=result,
        case_path=case_path,
        trace_path=trace_path,
        result_path=result_path,
    )


# ---------------------------------------------------------------------------
# Issue 5: keyword baseline retrieval
# ---------------------------------------------------------------------------

def run_keyword_retrieval(
    *,
    case_id: str,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    output_dir: Path = DEFAULT_REVIEW_RUNS_DIR,
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalTrace:
    """Run keyword retrieval for an existing review case.

    Loads the persisted ``RetrievalTrace`` for ``case_id``, runs the planned
    queries against the corpus, merges hits, and writes the updated trace
    back to JSONL. Returns the updated trace.

    Raises ``ValueError`` when the case or trace cannot be found.
    """

    trace_path = retrieval_traces_path(output_dir)
    if not trace_path.exists():
        raise ValueError(
            f"retrieval traces file does not exist: {trace_path}. "
            "Create a review case first with create_review_case."
        )

    traces = read_retrieval_traces(trace_path)
    target_trace: RetrievalTrace | None = None
    for trace in traces:
        if trace.review_case_id == case_id:
            target_trace = trace
            break

    if target_trace is None:
        raise ValueError(
            f"review case {case_id} not found in {trace_path}"
        )

    if not target_trace.queries:
        raise ValueError(
            f"review case {case_id} has no planned queries; "
            "ensure create_review_case ran fact extraction and query planning."
        )

    chunks = load_corpus(chunks_path)
    retriever = KeywordRetriever(chunks)

    hits_per_query: list[list[RetrievalHit]] = []
    for query in target_trace.queries:
        hits = retriever.search(
            query.text,
            top_k=top_k,
            query_type=query.query_type,
        )
        hits_per_query.append(hits)

    merged_hits = merge_hits_by_chunk_id(hits_per_query, top_k=top_k)

    updated_trace = target_trace.model_copy(
        update={"keyword_results": merged_hits}
    )

    # Rewrite the traces file with the updated trace
    updated_traces = [
        updated_trace if t.trace_id == target_trace.trace_id else t
        for t in traces
    ]
    write_retrieval_traces(trace_path, updated_traces)

    return updated_trace
