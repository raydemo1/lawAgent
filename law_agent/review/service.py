"""Application services for material-driven review runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from law_agent.review.evidence import (
    evaluate_after_second_retrieval,
    run_self_check,
)
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
from law_agent.review.result_builder import build_review_result
from law_agent.review.retrieval.boosts import (
    apply_boosts_to_hits,
    compute_boosts_summary,
)
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH, CorpusError, load_corpus
from law_agent.review.retrieval.fusion import rrf_fuse
from law_agent.review.retrieval.keyword import KeywordRetriever, merge_hits_by_chunk_id
from law_agent.review.retrieval.neighbors import expand_neighbors
from law_agent.review.retrieval.vector_mock import VectorMockRetriever
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


# ---------------------------------------------------------------------------
# Issue 6: hybrid retrieval with vector mock, boosts, RRF, neighbors
# ---------------------------------------------------------------------------

DEFAULT_NEIGHBOR_COUNT = 10


def _load_case_and_trace(
    case_id: str,
    output_dir: Path,
) -> tuple[ReviewCase, RetrievalTrace, list[RetrievalTrace]]:
    """Load a review case and its trace from the output directory."""

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
        raise ValueError(f"review case {case_id} not found in {trace_path}")

    if not target_trace.queries:
        raise ValueError(
            f"review case {case_id} has no planned queries; "
            "ensure create_review_case ran fact extraction and query planning."
        )

    cases_path = review_cases_path(output_dir)
    from law_agent.review.io import read_review_cases

    cases = read_review_cases(cases_path)
    target_case: ReviewCase | None = None
    for case in cases:
        if case.review_case_id == case_id:
            target_case = case
            break

    if target_case is None:
        raise ValueError(f"review case {case_id} not found in {cases_path}")

    return target_case, target_trace, traces


def run_hybrid_retrieval(
    *,
    case_id: str,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    output_dir: Path = DEFAULT_REVIEW_RUNS_DIR,
    top_k: int = DEFAULT_TOP_K,
    max_neighbors: int = DEFAULT_NEIGHBOR_COUNT,
) -> RetrievalTrace:
    """Run hybrid retrieval for an existing review case.

    Combines keyword and vector_mock retrievers, applies metadata boosts
    based on ``ReviewFacts``, fuses with RRF, and expands neighbor chunks.
    Persists all component results and the fused result to the trace.
    """

    case, target_trace, traces = _load_case_and_trace(case_id, output_dir)
    facts = case.review_facts

    chunks = load_corpus(chunks_path)
    chunks_by_id: dict[str, object] = {c.chunk_id: c for c in chunks}

    keyword_retriever = KeywordRetriever(chunks)
    vector_retriever = VectorMockRetriever(chunks)

    # Run both retrievers per query and merge
    keyword_hits_per_query: list[list[RetrievalHit]] = []
    vector_hits_per_query: list[list[RetrievalHit]] = []
    query_types: list[str | None] = []

    for query in target_trace.queries:
        query_types.append(query.query_type)
        kw_hits = keyword_retriever.search(
            query.text, top_k=top_k, query_type=query.query_type
        )
        vec_hits = vector_retriever.search(
            query.text, top_k=top_k, query_type=query.query_type
        )
        keyword_hits_per_query.append(kw_hits)
        vector_hits_per_query.append(vec_hits)

    merged_keyword = merge_hits_by_chunk_id(keyword_hits_per_query, top_k=top_k)
    merged_vector = merge_hits_by_chunk_id(vector_hits_per_query, top_k=top_k)

    # Apply metadata boosts to both component results
    boosted_keyword = apply_boosts_to_hits(merged_keyword, chunks_by_id, facts)
    boosted_vector = apply_boosts_to_hits(merged_vector, chunks_by_id, facts)

    # RRF fusion
    hybrid_hits = rrf_fuse(boosted_keyword, boosted_vector, top_k=top_k)

    # Expand neighbors for top hits
    neighbor_hits = expand_neighbors(
        hybrid_hits[:5], chunks_by_id, max_neighbors=max_neighbors
    )

    # Build boost summary for trace
    boosts_summary = compute_boosts_summary(facts, query_types)

    # Issue 7: Evidence self-check
    self_check = run_self_check(hybrid_hits, facts, chunks_by_id)
    second_retrieval_info: dict[str, object] = {}
    final_evidence: list[RetrievalHit] = hybrid_hits

    if self_check.status == "needs_second_retrieval" and self_check.second_retrieval_plan:
        plan = self_check.second_retrieval_plan
        expanded_top_k = plan.increased_top_k

        # Run second retrieval with expanded queries
        all_queries = list(target_trace.queries) + plan.expanded_queries
        kw2_per_query: list[list[RetrievalHit]] = []
        vec2_per_query: list[list[RetrievalHit]] = []
        for q in all_queries:
            kw2_per_query.append(
                keyword_retriever.search(q.text, top_k=expanded_top_k, query_type=q.query_type)
            )
            vec2_per_query.append(
                vector_retriever.search(q.text, top_k=expanded_top_k, query_type=q.query_type)
            )

        merged_kw2 = merge_hits_by_chunk_id(kw2_per_query, top_k=expanded_top_k)
        merged_vec2 = merge_hits_by_chunk_id(vec2_per_query, top_k=expanded_top_k)

        # Apply stronger boosts on second retrieval
        boosted_kw2 = apply_boosts_to_hits(merged_kw2, chunks_by_id, facts)
        boosted_vec2 = apply_boosts_to_hits(merged_vec2, chunks_by_id, facts)

        hybrid2_hits = rrf_fuse(boosted_kw2, boosted_vec2, top_k=expanded_top_k)
        neighbor2_hits = expand_neighbors(
            hybrid2_hits[:5], chunks_by_id, max_neighbors=max_neighbors
        )

        # Re-evaluate after second retrieval (never triggers another)
        self_check = evaluate_after_second_retrieval(
            hybrid2_hits, facts, chunks_by_id, self_check.issues
        )

        # Use second retrieval results as final evidence
        final_evidence = hybrid2_hits
        second_retrieval_info = {
            "triggered": True,
            "expanded_queries": [q.model_dump() for q in plan.expanded_queries],
            "increased_top_k": expanded_top_k,
            "stronger_boost": plan.stronger_boost,
            "reason": plan.reason,
            "hybrid_results_count": len(hybrid2_hits),
            "neighbor_chunks_count": len(neighbor2_hits),
        }

        # Update trace with second retrieval results
        updated_trace = target_trace.model_copy(
            update={
                "keyword_results": boosted_kw2,
                "vector_results": boosted_vec2,
                "hybrid_results": hybrid2_hits,
                "neighbor_chunks": neighbor2_hits,
                "metadata_boosts": boosts_summary,
                "evidence_self_check": self_check,
                "second_retrieval": second_retrieval_info,
                "final_evidence": final_evidence,
            }
        )
    else:
        updated_trace = target_trace.model_copy(
            update={
                "keyword_results": boosted_keyword,
                "vector_results": boosted_vector,
                "hybrid_results": hybrid_hits,
                "neighbor_chunks": neighbor_hits,
                "metadata_boosts": boosts_summary,
                "evidence_self_check": self_check,
                "second_retrieval": second_retrieval_info,
                "final_evidence": final_evidence,
            }
        )

    # Rewrite traces file
    updated_traces = [
        updated_trace if t.trace_id == target_trace.trace_id else t
        for t in traces
    ]
    write_retrieval_traces(retrieval_traces_path(output_dir), updated_traces)

    # Issue 8: Build governed review result
    review_result = build_review_result(
        review_result_id=case.latest_result_id or make_id("result"),
        review_case_id=case_id,
        trace_id=target_trace.trace_id,
        facts=facts,
        self_check=self_check,
        evidence_hits=final_evidence,
        chunks_by_id=chunks_by_id,
    )

    # Persist updated result
    from law_agent.review.io import read_review_results

    results_path = review_results_path(output_dir)
    if results_path.exists():
        existing_results = read_review_results(results_path)
        updated_results = [
            review_result if r.review_case_id == case_id else r
            for r in existing_results
        ]
    else:
        updated_results = [review_result]
    write_review_results(results_path, updated_results)

    return updated_trace
