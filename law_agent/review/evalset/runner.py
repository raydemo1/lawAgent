"""Evaluation runner for review modes (Issue 9).

Runs golden-set scenarios through explicit review modes, computes metrics,
and produces a comparison summary.
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

DEFAULT_EVAL_MODES: tuple[str, ...] = ("rule_baseline", "local")
_MODE_ALIASES: dict[str, str] = {
    "keyword": "rule_baseline",
    "hybrid": "local",
}


def run_evaluation(
    *,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    scenarios: list[EvalScenario] | None = None,
    top_k: int = 10,
    modes: list[str] | tuple[str, ...] | None = None,
) -> EvalSummary:
    """Run full evaluation across selected modes.

    Returns an ``EvalSummary`` with per-mode aggregated metrics and bad cases.
    """

    if scenarios is None:
        scenarios = get_default_scenarios()

    generated_at = utc_now_iso()

    selected_modes = tuple(modes or DEFAULT_EVAL_MODES)
    canonical_modes = tuple(_MODE_ALIASES.get(mode, mode) for mode in selected_modes)

    # Service mode needs ES + pgvector adapters; build once and reuse across
    # all scenarios to avoid opening/closing connections per case.
    service_adapters = None
    if "service" in canonical_modes:
        from law_agent.config import require_service_config
        from law_agent.review.retrieval.service_backends import build_service_adapters

        service_adapters = build_service_adapters(require_service_config())

    try:
        results_by_mode: dict[str, list[CaseMetricResult]] = {}
        for mode in canonical_modes:
            mode_results: list[CaseMetricResult] = []
            for scenario in scenarios:
                mode_results.append(
                    _run_single_case(
                        scenario, chunks_path, mode=mode, top_k=top_k,
                        service_adapters=service_adapters,
                    )
                )
            results_by_mode[mode] = mode_results
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
        cases_path="default",
        mode_metrics=mode_metrics,
        bad_cases=all_bad,
        all_case_results=results_by_mode,
    )


def _run_single_case(
    scenario: EvalScenario,
    chunks_path: Path | str,
    *,
    mode: str,
    top_k: int,
    service_adapters: object | None = None,
) -> CaseMetricResult:
    """Run a single scenario in one mode and return metrics."""

    mode = _MODE_ALIASES.get(mode, mode)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        review_mode = "llm" if mode == "llm" else "rule_baseline"

        # Create review case
        response = create_review_case(
            question=scenario.question,
            material_text=scenario.material_text,
            output_dir=tmp_path,
            now=lambda: "2026-07-06T00:00:00+00:00",
            id_factory=lambda prefix: f"{prefix}_eval",
            review_mode=review_mode,
        )

        case_id = "review_eval"

        if mode == "service":
            from law_agent.review.service import run_service_retrieval

            trace = run_service_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
                review_mode=review_mode,
                adapters=service_adapters,
            )
            hits = trace.final_evidence or trace.hybrid_results
            second_retrieval_triggered = trace.evidence_self_check.second_retrieval_triggered
        elif mode in {"local", "llm"}:
            trace = run_hybrid_retrieval(
                case_id=case_id,
                chunks_path=chunks_path,
                output_dir=tmp_path,
                top_k=top_k,
                review_mode=review_mode,
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
            risk_level=risk_level,
            second_retrieval_triggered=second_retrieval_triggered,
            citation_groups=citation_groups,
        )


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
