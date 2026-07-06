"""Evaluation runner for review retrieval modes (Issue 9).

Runs each golden-set scenario through both keyword and hybrid retrieval
modes, computes metrics, and produces a comparison summary.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from law_agent.review.evalset.cases import get_default_scenarios
from law_agent.review.evalset.metrics import aggregate_metrics, evaluate_case
from law_agent.review.evalset.schemas import (
    CaseMetricResult,
    EvalScenario,
    EvalSummary,
    ModeMetrics,
)
from law_agent.review.evidence import run_self_check
from law_agent.review.ids import make_id, utc_now_iso
from law_agent.review.io import (
    read_review_cases,
    read_review_results,
    review_cases_path,
    review_results_path,
    write_review_results,
)
from law_agent.review.result_builder import build_review_result
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH, load_corpus
from law_agent.review.service import create_review_case, run_hybrid_retrieval, run_keyword_retrieval


def run_evaluation(
    *,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    scenarios: list[EvalScenario] | None = None,
    top_k: int = 10,
) -> EvalSummary:
    """Run full evaluation across both modes.

    Returns an ``EvalSummary`` with per-mode aggregated metrics and bad cases.
    """

    if scenarios is None:
        scenarios = get_default_scenarios()

    generated_at = utc_now_iso()

    # Run each scenario in both modes
    keyword_results: list[CaseMetricResult] = []
    hybrid_results: list[CaseMetricResult] = []

    for scenario in scenarios:
        kw_result = _run_single_case(scenario, chunks_path, mode="keyword", top_k=top_k)
        hy_result = _run_single_case(scenario, chunks_path, mode="hybrid", top_k=top_k)
        keyword_results.append(kw_result)
        hybrid_results.append(hy_result)

    # Aggregate
    kw_metrics = aggregate_metrics(keyword_results, "keyword")
    hy_metrics = aggregate_metrics(hybrid_results, "hybrid")

    # Collect bad cases from both modes
    all_bad = [r for r in keyword_results + hybrid_results if r.is_bad_case]

    return EvalSummary(
        generated_at=generated_at,
        chunks_path=str(chunks_path),
        cases_path="default",
        mode_metrics={
            "keyword": kw_metrics,
            "hybrid": hy_metrics,
        },
        bad_cases=all_bad,
        all_case_results={
            "keyword": keyword_results,
            "hybrid": hybrid_results,
        },
    )


def _run_single_case(
    scenario: EvalScenario,
    chunks_path: Path | str,
    *,
    mode: str,
    top_k: int,
) -> CaseMetricResult:
    """Run a single scenario in one mode and return metrics."""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create review case
        response = create_review_case(
            question=scenario.question,
            material_text=scenario.material_text,
            output_dir=tmp_path,
            now=lambda: "2026-07-06T00:00:00+00:00",
            id_factory=lambda prefix: f"{prefix}_eval",
        )

        case_id = "review_eval"

        if mode == "hybrid":
            trace = run_hybrid_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
            )
            hits = trace.final_evidence or trace.hybrid_results
            second_retrieval_triggered = trace.evidence_self_check.second_retrieval_triggered
        else:
            trace = run_keyword_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
            )
            hits = trace.keyword_results

            # Bug 1 fix: run_keyword_retrieval (unlike run_hybrid_retrieval)
            # does not run the evidence self-check or build a governed
            # ReviewResult. Without this, review_results.jsonl keeps the
            # placeholder "insufficient_evidence" risk level written by
            # create_review_case(), so every non-abstain scenario is judged as
            # an abstention failure. Mirror run_hybrid_retrieval: run the
            # self-check and result builder to produce a real risk level.
            cases = read_review_cases(review_cases_path(tmp_path))
            target_case = next(c for c in cases if c.review_case_id == case_id)
            chunks = load_corpus(chunks_path)
            chunks_by_id = {c.chunk_id: c for c in chunks}
            self_check = run_self_check(hits, target_case.review_facts, chunks_by_id)
            review_result = build_review_result(
                review_result_id=target_case.latest_result_id or make_id("result"),
                review_case_id=case_id,
                trace_id=trace.trace_id,
                facts=target_case.review_facts,
                self_check=self_check,
                evidence_hits=hits,
                chunks_by_id=chunks_by_id,
            )
            results_path = review_results_path(tmp_path)
            existing_results = read_review_results(results_path)
            updated_results = [
                review_result if r.review_case_id == case_id else r
                for r in existing_results
            ]
            write_review_results(results_path, updated_results)
            second_retrieval_triggered = self_check.second_retrieval_triggered

        # Get risk level from result
        results_path = tmp_path / "review_results.jsonl"
        risk_level = ""
        if results_path.exists():
            results = read_review_results(results_path)
            if results:
                risk_level = results[0].risk_level

        return evaluate_case(
            scenario,
            hits,
            risk_level=risk_level,
            second_retrieval_triggered=second_retrieval_triggered,
        )


def format_summary_text(summary: EvalSummary) -> str:
    """Format evaluation summary as readable text for CLI output."""

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"Evaluation Summary (generated: {summary.generated_at})")
    lines.append(f"Corpus: {summary.chunks_path}")
    lines.append(f"Cases: {summary.cases_path}")
    lines.append("=" * 70)

    for mode_name in ("keyword", "hybrid"):
        metrics = summary.mode_metrics.get(mode_name)
        if metrics is None:
            continue

        lines.append(f"\n--- {mode_name.upper()} mode ---")
        lines.append(f"  Total cases:        {metrics.total_cases}")
        lines.append(f"  Mean Recall@3:      {metrics.mean_recall_at_3:.4f}")
        lines.append(f"  Mean Recall@5:      {metrics.mean_recall_at_5:.4f}")
        lines.append(f"  Mean MRR@10:        {metrics.mean_mrr_at_10:.4f}")
        lines.append(f"  Abstention accuracy: {metrics.abstention_accuracy:.4f}")
        lines.append(f"  Second retrieval:   {metrics.second_retrieval_accuracy:.4f}")
        lines.append(f"  Citation violations: {metrics.total_citation_violations}")
        lines.append(f"  Bad cases:          {metrics.bad_case_count}")

    if summary.bad_cases:
        lines.append(f"\n--- Bad cases ({len(summary.bad_cases)}) ---")
        seen: set[str] = set()
        for case in summary.bad_cases:
            key = f"{case.case_id}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  {case.case_id}: {case.bad_reasons}")
            if case.missing_sources:
                lines.append(f"    missing: {case.missing_sources}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
