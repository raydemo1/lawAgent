"""Application services for material-driven review runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from law_agent.config import RerankMode, load_rerank_config
from law_agent.review.evidence import (
    evaluate_after_second_retrieval,
    run_self_check,
    run_self_check_with_deepseek,
    validate_llm_self_check,
)
from law_agent.review.facts import (
    FactsExtractor,
    extract_facts,
    extract_facts_with_deepseek,
    merge_facts_with_rule_fallback,
)
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
from law_agent.review.query_planner import (
    QueryPlanner,
    merge_queries_with_rule_fallback,
    plan_high_confidence_queries,
    plan_queries,
    plan_queries_with_deepseek,
)
from law_agent.review.result_builder import build_review_result, build_review_result_with_deepseek
from law_agent.review.retrieval.boosts import (
    apply_boosts_to_hits,
    compute_boosts_summary,
)
from law_agent.review.retrieval.adapters import (
    KeywordSearchAdapter,
    VectorSearchAdapter,
)
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH, CorpusError, load_corpus
from law_agent.review.retrieval.fusion import rrf_fuse, source_aware_fuse
from law_agent.review.retrieval.keyword import KeywordRetriever, merge_hits_by_chunk_id
from law_agent.review.retrieval.neighbors import expand_neighbors
from law_agent.review.retrieval.rerank import rerank_hits
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
DEFAULT_CANDIDATE_TOP_K = 50
ReviewMode = Literal["rule_baseline", "llm"]


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
    review_mode: ReviewMode = "rule_baseline",
    facts_extractor: FactsExtractor | None = None,
    query_planner: QueryPlanner | None = None,
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

    if facts_extractor is None:
        facts_extractor = (
            extract_facts_with_deepseek if review_mode == "llm" else extract_facts
        )
    if query_planner is None:
        query_planner = (
            plan_queries_with_deepseek if review_mode == "llm" else plan_queries
        )

    facts = facts_extractor(material.material_text, question)
    queries: list[RetrievalQuery] = query_planner(question, facts, material.material_text)
    if review_mode == "llm":
        rule_facts = extract_facts(material.material_text, question)
        facts = merge_facts_with_rule_fallback(facts, rule_facts)
        supplemental_queries = plan_high_confidence_queries(
            question, facts, material.material_text
        )
        queries = merge_queries_with_rule_fallback(queries, supplemental_queries)

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
    review_mode: ReviewMode = "rule_baseline",
    rerank_mode: RerankMode = "off",
    keyword_retriever: KeywordSearchAdapter | None = None,
    vector_retriever: VectorSearchAdapter | None = None,
) -> RetrievalTrace:
    """Run hybrid retrieval for an existing review case.

    Combines keyword and vector_mock retrievers, applies metadata boosts
    based on ``ReviewFacts``, fuses with RRF, and expands neighbor chunks.
    Persists all component results and the fused result to the trace.

    ``keyword_retriever`` / ``vector_retriever`` may be injected to back the
    two retrieval routes with service adapters (Elasticsearch / pgvector)
    instead of the local in-memory retrievers. When omitted, the local
    ``KeywordRetriever`` and ``VectorMockRetriever`` are used.
    """

    case, target_trace, traces = _load_case_and_trace(case_id, output_dir)
    facts = case.review_facts

    chunks = load_corpus(chunks_path)
    chunks_by_id: dict[str, object] = {c.chunk_id: c for c in chunks}
    candidate_top_k = max(top_k, DEFAULT_CANDIDATE_TOP_K)
    rerank_config = load_rerank_config(mode=rerank_mode)
    source_fusion_top_k = (
        max(top_k, rerank_config.window) if rerank_mode != "off" else top_k
    )

    if keyword_retriever is None:
        keyword_retriever = KeywordRetriever(chunks)
    if vector_retriever is None:
        vector_retriever = VectorMockRetriever(chunks)

    # Run both retrievers per query and merge
    keyword_hits_per_query: list[list[RetrievalHit]] = []
    vector_hits_per_query: list[list[RetrievalHit]] = []
    query_types: list[str | None] = []

    retrieval_queries = [
        (query.text, query.query_type)
        for query in target_trace.queries
    ]
    query_types.extend(query_type for _text, query_type in retrieval_queries)
    keyword_hits_per_query = keyword_retriever.search_many(
        retrieval_queries, top_k=candidate_top_k
    )
    vector_hits_per_query = vector_retriever.search_many(
        retrieval_queries, top_k=candidate_top_k
    )

    merged_keyword = merge_hits_by_chunk_id(keyword_hits_per_query, top_k=candidate_top_k)
    merged_vector = merge_hits_by_chunk_id(vector_hits_per_query, top_k=candidate_top_k)

    # Apply metadata boosts to both component results
    boosted_keyword = apply_boosts_to_hits(merged_keyword, chunks_by_id, facts)
    boosted_vector = apply_boosts_to_hits(merged_vector, chunks_by_id, facts)

    # RRF produces a broad chunk-level candidate list; source-aware fusion
    # then collapses repeated chunks from the same legal source into a
    # source-diverse final evidence list.
    hybrid_candidates = rrf_fuse(
        boosted_keyword, boosted_vector, top_k=candidate_top_k
    )
    hybrid_hits = source_aware_fuse(
        hybrid_candidates,
        top_k=source_fusion_top_k,
        chunks_by_id=chunks_by_id,
    )
    rerank_outcome = rerank_hits(
        hybrid_hits,
        question=case.question,
        material_text=case.material.material_text,
        facts=facts,
        queries=target_trace.queries,
        top_k=top_k,
        mode=rerank_mode,
        config=rerank_config,
    )
    hybrid_hits = rerank_outcome.hits
    rerank_info: dict[str, object] = {"initial": rerank_outcome.info}

    # Expand neighbors for top hits
    neighbor_hits = expand_neighbors(
        hybrid_hits[:5], chunks_by_id, max_neighbors=max_neighbors
    )

    # Build boost summary for trace
    boosts_summary = compute_boosts_summary(facts, query_types)

    # Issue 7: Evidence self-check
    if review_mode == "llm":
        self_check = run_self_check_with_deepseek(hybrid_hits, facts, chunks_by_id)
        self_check = validate_llm_self_check(
            self_check, hybrid_hits, facts, chunks_by_id
        )
    else:
        self_check = run_self_check(hybrid_hits, facts, chunks_by_id)
    second_retrieval_info: dict[str, object] = {}
    final_evidence: list[RetrievalHit] = hybrid_hits

    if self_check.status == "needs_second_retrieval" and self_check.second_retrieval_plan:
        plan = self_check.second_retrieval_plan
        expanded_top_k = max(top_k, plan.increased_top_k)
        expanded_candidate_top_k = max(candidate_top_k, expanded_top_k)
        expanded_source_fusion_top_k = (
            max(expanded_top_k, rerank_config.window)
            if rerank_mode != "off"
            else expanded_top_k
        )

        # Run second retrieval with expanded queries
        all_queries = [
            (query.text, query.query_type)
            for query in list(target_trace.queries) + plan.expanded_queries
        ]
        kw2_per_query = keyword_retriever.search_many(
            all_queries, top_k=expanded_candidate_top_k
        )
        vec2_per_query = vector_retriever.search_many(
            all_queries, top_k=expanded_candidate_top_k
        )

        merged_kw2 = merge_hits_by_chunk_id(kw2_per_query, top_k=expanded_candidate_top_k)
        merged_vec2 = merge_hits_by_chunk_id(vec2_per_query, top_k=expanded_candidate_top_k)

        # Apply stronger boosts on second retrieval
        boosted_kw2 = apply_boosts_to_hits(merged_kw2, chunks_by_id, facts)
        boosted_vec2 = apply_boosts_to_hits(merged_vec2, chunks_by_id, facts)

        hybrid2_candidates = rrf_fuse(
            boosted_kw2,
            boosted_vec2,
            top_k=expanded_candidate_top_k,
        )
        hybrid2_hits = source_aware_fuse(
            hybrid2_candidates,
            top_k=expanded_source_fusion_top_k,
            chunks_by_id=chunks_by_id,
        )
        rerank2_outcome = rerank_hits(
            hybrid2_hits,
            question=case.question,
            material_text=case.material.material_text,
            facts=facts,
            queries=list(target_trace.queries) + plan.expanded_queries,
            top_k=expanded_top_k,
            mode=rerank_mode,
            config=rerank_config,
        )
        hybrid2_hits = rerank2_outcome.hits
        rerank_info["second_retrieval"] = rerank2_outcome.info
        neighbor2_hits = expand_neighbors(
            hybrid2_hits[:5], chunks_by_id, max_neighbors=max_neighbors
        )

        # Re-evaluate after second retrieval (never triggers another).
        # Always use the rule-based evaluator to guarantee termination:
        # critical_facts_missing are treated as soft warnings and the status
        # is forced to sufficient or insufficient, never needs_second_retrieval.
        self_check = evaluate_after_second_retrieval(
            hybrid2_hits, facts, chunks_by_id, self_check.issues
        )
        self_check = self_check.model_copy(update={"second_retrieval_triggered": True})

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
                "rerank": rerank_info,
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
                "rerank": rerank_info,
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
    if review_mode == "llm":
        review_result = build_review_result_with_deepseek(
            review_result_id=case.latest_result_id or make_id("result"),
            review_case_id=case_id,
            trace_id=target_trace.trace_id,
            facts=facts,
            self_check=self_check,
            evidence_hits=final_evidence,
            chunks_by_id=chunks_by_id,
            question=case.question,
            material_text=case.material.material_text,
            retrieval_queries=updated_trace.queries,
            second_retrieval=updated_trace.second_retrieval,
        )
    else:
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


# ---------------------------------------------------------------------------
# Service mode: real Elasticsearch + pgvector hybrid retrieval
# ---------------------------------------------------------------------------

def run_service_retrieval(
    *,
    case_id: str,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    output_dir: Path = DEFAULT_REVIEW_RUNS_DIR,
    top_k: int = DEFAULT_TOP_K,
    max_neighbors: int = DEFAULT_NEIGHBOR_COUNT,
    review_mode: ReviewMode = "rule_baseline",
    rerank_mode: RerankMode = "off",
    config: "object | None" = None,
    adapters: "object | None" = None,
) -> RetrievalTrace:
    """Run hybrid retrieval backed by real Elasticsearch + pgvector.

    Builds the service adapters from ``ServiceConfig`` (or accepts pre-built
    ``adapters``), then delegates to ``run_hybrid_retrieval`` with both routes
    injected. The corpus is still loaded locally for metadata boosts, neighbor
    expansion, and the governed result builder — only the two retrieval routes
    are served by ES and pgvector.

    Fail-fast: ``require_service_adapters`` inside ``build_service_adapters``
    ensures both routes exist; there is no fallback to local retrieval.
    """

    from law_agent.config import require_service_config
    from law_agent.review.retrieval.service_backends import (
        ServiceAdapters,
        build_service_adapters,
    )

    own_adapters = False
    if adapters is None:
        service_config = config or require_service_config()
        adapters = build_service_adapters(service_config)
        own_adapters = True

    assert isinstance(adapters, ServiceAdapters)
    try:
        return run_hybrid_retrieval(
            case_id=case_id,
            chunks_path=chunks_path,
            output_dir=output_dir,
            top_k=top_k,
            max_neighbors=max_neighbors,
            review_mode=review_mode,
            rerank_mode=rerank_mode,
            keyword_retriever=adapters.keyword,
            vector_retriever=adapters.vector,
        )
    finally:
        if own_adapters:
            adapters.close()
