"""Evaluation runner for review modes (Issue 9).

Runs golden-set scenarios through explicit review modes, computes metrics,
and produces a comparison summary.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import tempfile
from pathlib import Path
from typing import Literal

from law_agent.config import RerankMode
from law_agent.review.evalset.cases import EvalSuite, get_scenarios
from law_agent.review.evalset.metrics import aggregate_metrics, evaluate_case
from law_agent.review.evalset.schemas import (
    CaseMetricResult,
    EvalScenario,
    EvalSummary,
    ModeMetrics,
)
from law_agent.review.facts import extract_facts
from law_agent.review.ids import utc_now_iso
from law_agent.review.io import (
    read_review_results,
)
from law_agent.review.query_planner import plan_queries
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH
from law_agent.review.service import create_review_case, run_hybrid_retrieval

RetrievalEvalMode = Literal["service", "local"]
ReviewEvalMode = Literal["llm", "local"]
DEFAULT_RETRIEVAL_MODE: RetrievalEvalMode = "service"
DEFAULT_REVIEW_MODE: ReviewEvalMode = "llm"
DEFAULT_RERANK_MODE: RerankMode = "off"
DEFAULT_EVAL_SUITE: EvalSuite = "full"
DEFAULT_MAX_WORKERS = 4


def run_evaluation(
    *,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    scenarios: list[EvalScenario] | None = None,
    suite: EvalSuite = DEFAULT_EVAL_SUITE,
    top_k: int = 10,
    retrieval_mode: RetrievalEvalMode = DEFAULT_RETRIEVAL_MODE,
    review_mode: ReviewEvalMode = DEFAULT_REVIEW_MODE,
    rerank_mode: RerankMode = DEFAULT_RERANK_MODE,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> EvalSummary:
    """Run full evaluation across selected modes.

    Returns an ``EvalSummary`` with per-mode aggregated metrics and bad cases.
    """

    cases_label = suite if scenarios is None else "custom"
    if scenarios is None:
        scenarios = get_scenarios(suite)

    generated_at = utc_now_iso()

    eval_key = _eval_key(retrieval_mode, review_mode, rerank_mode)
    max_workers = max(1, max_workers)

    # Serial service retrieval can reuse adapters. Parallel service retrieval
    # must not share the pgvector Postgres connection across threads, so each
    # case builds its own adapters from the same config.
    service_adapters = None
    service_config = None
    if retrieval_mode == "service":
        from law_agent.config import require_service_config
        from law_agent.review.retrieval.service_backends import build_service_adapters

        service_config = require_service_config()
        if max_workers == 1:
            service_adapters = build_service_adapters(service_config)
        if review_mode == "local" and service_adapters is not None:
            _prewarm_service_eval_queries(service_adapters, scenarios)

    try:
        results_by_mode: dict[str, list[CaseMetricResult]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            mode_results = list(
                executor.map(
                    lambda scenario: _run_single_case(
                        scenario,
                        chunks_path,
                        retrieval_mode=retrieval_mode,
                        review_mode=review_mode,
                        rerank_mode=rerank_mode,
                        top_k=top_k,
                        service_adapters=service_adapters,
                        service_config=service_config,
                    ),
                    scenarios,
                )
            )
        results_by_mode[eval_key] = mode_results
    finally:
        if service_adapters is not None:
            service_adapters.close()

    mode_metrics = {
        mode: aggregate_metrics(results, mode)
        for mode, results in results_by_mode.items()
    }

    all_results = [
        result
        for results in results_by_mode.values()
        for result in results
    ]
    all_bad = [r for r in all_results if r.is_bad_case]

    return EvalSummary(
        generated_at=generated_at,
        chunks_path=str(chunks_path),
        cases_path=cases_label,
        mode_metrics=mode_metrics,
        bad_cases=all_bad,
        all_case_results=results_by_mode,
    )


def _prewarm_service_eval_queries(service_adapters: object, scenarios: list[EvalScenario]) -> None:
    """Embed all deterministic service-eval queries once before case execution."""

    vector = getattr(service_adapters, "vector", None)
    prewarm = getattr(vector, "prewarm_queries", None)
    if prewarm is None:
        raise RuntimeError("service vector adapter must support prewarm_queries")

    queries: list[str] = []
    for scenario in scenarios:
        facts = extract_facts(scenario.material_text, scenario.question)
        queries.extend(
            query.text
            for query in plan_queries(scenario.question, facts, scenario.material_text)
        )
    prewarm(queries)


def _run_single_case(
    scenario: EvalScenario,
    chunks_path: Path | str,
    *,
    retrieval_mode: RetrievalEvalMode,
    review_mode: ReviewEvalMode,
    top_k: int,
    rerank_mode: RerankMode = DEFAULT_RERANK_MODE,
    service_adapters: object | None = None,
    service_config: object | None = None,
) -> CaseMetricResult:
    """Run a single scenario in one mode and return metrics."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        service_review_mode = "llm" if review_mode == "llm" else "rule_baseline"

        # Create review case
        response = create_review_case(
            question=scenario.question,
            material_text=scenario.material_text,
            output_dir=tmp_path,
            now=lambda: "2026-07-06T00:00:00+00:00",
            id_factory=lambda prefix: f"{prefix}_eval",
            review_mode=service_review_mode,
        )

        case_id = "review_eval"

        if retrieval_mode == "service":
            from law_agent.review.service import run_service_retrieval

            trace = run_service_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
                review_mode=service_review_mode,
                rerank_mode=rerank_mode,
                config=service_config,
                adapters=service_adapters,
            )
            hits = trace.final_evidence or trace.hybrid_results
            second_retrieval_triggered = trace.evidence_self_check.second_retrieval_triggered
        else:
            trace = run_hybrid_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
                review_mode=service_review_mode,
                rerank_mode=rerank_mode,
            )
            hits = trace.final_evidence or trace.hybrid_results
            second_retrieval_triggered = trace.evidence_self_check.second_retrieval_triggered

        # Get risk level and final citations from result.
        results_path = tmp_path / "review_results.jsonl"
        risk_level = ""
        citation_groups = None
        if results_path.exists():
            results = read_review_results(results_path)
            if results:
                result = results[0]
                risk_level = result.risk_level
                citation_groups = result.applicable_evidence

        return evaluate_case(
            scenario,
            hits,
            candidate_hits=[*trace.keyword_results, *trace.vector_results],
            risk_level=risk_level,
            second_retrieval_triggered=second_retrieval_triggered,
            citation_groups=citation_groups,
        )


def _eval_key(
    retrieval_mode: RetrievalEvalMode,
    review_mode: ReviewEvalMode,
    rerank_mode: RerankMode = DEFAULT_RERANK_MODE,
) -> str:
    base = f"retrieval={retrieval_mode},review={review_mode}"
    if rerank_mode == "off":
        return base
    return f"{base},rerank={rerank_mode}"


def format_summary_text(summary: EvalSummary) -> str:
    """Format evaluation summary as readable text for CLI output."""

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"Evaluation Summary (generated: {summary.generated_at})")
    lines.append(f"Corpus: {summary.chunks_path}")
    lines.append(f"Cases: {summary.cases_path}")
    lines.append("=" * 70)

    for mode_name in summary.mode_metrics:
        metrics = summary.mode_metrics.get(mode_name)
        if metrics is None:
            continue

        lines.append(f"\n--- {mode_name.upper()} mode ---")
        lines.append(f"  Total cases:        {metrics.total_cases}")
        lines.append(f"  Mean Recall@3:      {metrics.mean_recall_at_3:.4f}")
        lines.append(f"  Mean Recall@5:      {metrics.mean_recall_at_5:.4f}")
        lines.append(f"  Mean MRR@10:        {metrics.mean_mrr_at_10:.4f}")
        lines.append(f"  Candidate Recall@50: {metrics.mean_candidate_recall_at_50:.4f}")
        lines.append(f"  Distinct Recall@5:  {metrics.mean_distinct_source_recall_at_5:.4f}")
        lines.append(f"  Duplicate src@10:   {metrics.mean_duplicate_source_count_at_10:.4f}")
        lines.append(f"  Abstention accuracy: {metrics.abstention_accuracy:.4f}")
        lines.append(f"  Second retrieval:   {metrics.second_retrieval_accuracy:.4f}")
        lines.append(f"  Citation violations: {metrics.total_citation_violations}")
        lines.append(f"  Bad cases:          {metrics.bad_case_count}")
        if metrics.bad_case_taxonomy:
            taxonomy = ", ".join(
                f"{category}={count}"
                for category, count in metrics.bad_case_taxonomy.items()
            )
            lines.append(f"  Bad taxonomy:       {taxonomy}")

    if summary.bad_cases:
        lines.append(f"\n--- Bad cases ({len(summary.bad_cases)}) ---")
        seen: set[str] = set()
        for case in summary.bad_cases:
            key = f"{case.case_id}"
            if key in seen:
                continue
            seen.add(key)
            categories = (
                f" categories={case.bad_case_categories}"
                if case.bad_case_categories
                else ""
            )
            lines.append(f"  {case.case_id}: {case.bad_reasons}{categories}")
            if case.missing_sources:
                lines.append(f"    missing: {case.missing_sources}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
