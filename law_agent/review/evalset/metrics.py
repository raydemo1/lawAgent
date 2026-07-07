"""Evaluation metrics for review retrieval (Issue 9).

Metrics:
- Recall@K: fraction of expected sources found in top-K results
- MRR@K: mean reciprocal rank of first expected source
- Abstention accuracy: did the system correctly abstain when it should?
- Second retrieval accuracy: did second retrieval trigger when expected?
- Citation violation count: must_not_cite_as_clause chunks cited as legal basis
"""

from __future__ import annotations

from law_agent.review.evalset.schemas import CaseMetricResult, EvalScenario
from law_agent.review.schemas import Citation, CitationGroup, RetrievalHit


def compute_recall_at_k(
    hits: list[RetrievalHit],
    expected_sources: list[str],
    k: int,
) -> tuple[float, list[str]]:
    """Compute Recall@K. Returns (score, missing_sources)."""

    if not expected_sources:
        return 1.0, []

    top_k_sources = {h.source_id for h in hits[:k]}
    found = top_k_sources & set(expected_sources)
    missing = [s for s in expected_sources if s not in top_k_sources]
    return len(found) / len(expected_sources), missing


def compute_mrr_at_k(
    hits: list[RetrievalHit],
    expected_sources: list[str],
    k: int,
) -> float:
    """Compute MRR@K: reciprocal rank of first expected source in top-K."""

    if not expected_sources:
        return 1.0

    expected_set = set(expected_sources)
    for i, hit in enumerate(hits[:k]):
        if hit.source_id in expected_set:
            return 1.0 / (i + 1)
    return 0.0


def compute_source_pool_recall(
    hits: list[RetrievalHit],
    expected_sources: list[str],
) -> tuple[float, list[str]]:
    """Compute source recall over an unordered candidate pool."""

    if not expected_sources:
        return 1.0, []

    pool_sources = {h.source_id for h in hits}
    found = pool_sources & set(expected_sources)
    missing = [s for s in expected_sources if s not in pool_sources]
    return len(found) / len(expected_sources), missing


def distinct_source_hits_at_k(
    hits: list[RetrievalHit],
    k: int,
) -> list[RetrievalHit]:
    """Return the first K hits after collapsing duplicate source IDs."""

    seen: set[str] = set()
    distinct: list[RetrievalHit] = []
    for hit in hits:
        if hit.source_id in seen:
            continue
        seen.add(hit.source_id)
        distinct.append(hit)
        if len(distinct) >= k:
            break
    return distinct


def count_duplicate_sources_at_k(hits: list[RetrievalHit], k: int) -> int:
    """Count how many top-K positions are occupied by duplicate sources."""

    top = hits[:k]
    return len(top) - len({hit.source_id for hit in top})


def ordered_unique_sources(hits: list[RetrievalHit]) -> list[str]:
    """Return source IDs in result order, collapsing duplicates."""

    seen: set[str] = set()
    sources: list[str] = []
    for hit in hits:
        if hit.source_id in seen:
            continue
        seen.add(hit.source_id)
        sources.append(hit.source_id)
    return sources


def count_citation_violations(
    hits: list[RetrievalHit] | None = None,
    must_not_cite_as_clause: list[str] | None = None,
    *,
    citations: list[Citation] | None = None,
) -> int:
    """Count chunks that must NOT be cited as a clause but are.

    When ``citations`` is provided, violations are counted against the final
    citations: chunks listed in ``must_not_cite_as_clause`` that appear in a
    citation whose ``usage`` is ``"legal_basis"`` or ``"conditional_basis"``
    (i.e. used as a clause-level citation).

    When ``citations`` is not provided, falls back to the legacy hit-based
    behavior for backward compatibility: chunks in
    ``must_not_cite_as_clause`` that appear in retrieval ``hits`` with
    ``can_cite_clause=True``.
    """

    forbidden = set(must_not_cite_as_clause or [])
    if not forbidden:
        return 0

    if citations is not None:
        violations = 0
        for citation in citations:
            if (
                citation.chunk_id in forbidden
                and citation.usage in ("legal_basis", "conditional_basis")
            ):
                violations += 1
        return violations

    # Legacy hit-based behavior (backward compatibility).
    violations = 0
    for hit in hits or []:
        if hit.chunk_id in forbidden and hit.can_cite_clause:
            violations += 1
    return violations


def evaluate_case(
    scenario: EvalScenario,
    hits: list[RetrievalHit],
    *,
    candidate_hits: list[RetrievalHit] | None = None,
    risk_level: str = "",
    second_retrieval_triggered: bool = False,
    citation_groups: list[CitationGroup] | None = None,
) -> CaseMetricResult:
    """Evaluate a single scenario case against retrieval results.

    Args:
        scenario: The golden-set scenario.
        hits: Retrieved evidence hits (hybrid_results or keyword_results).
        risk_level: The review result risk level (for abstention check).
        second_retrieval_triggered: Whether second retrieval was triggered.
        citation_groups: Optional final ``CitationGroup`` list from the
            review result. When provided, citation violations are counted
            against these final citations (chunks in
            ``must_not_cite_as_clause`` used with ``usage`` of
            ``"legal_basis"`` / ``"conditional_basis"``). When ``None``,
            falls back to the legacy hit-based behavior.
    """

    recall_3, missing_3 = compute_recall_at_k(hits, scenario.expected_sources, 3)
    recall_5, missing_5 = compute_recall_at_k(hits, scenario.expected_sources, 5)
    mrr = compute_mrr_at_k(hits, scenario.expected_sources, 10)
    candidate_recall_50, _candidate_missing = compute_source_pool_recall(
        candidate_hits if candidate_hits is not None else hits,
        scenario.expected_sources,
    )
    distinct_recall_5, _distinct_missing = compute_recall_at_k(
        distinct_source_hits_at_k(hits, 5),
        scenario.expected_sources,
        5,
    )
    duplicate_sources_10 = count_duplicate_sources_at_k(hits, 10)

    if citation_groups is not None:
        final_citations = [c for group in citation_groups for c in group.citations]
        citation_violations = count_citation_violations(
            must_not_cite_as_clause=scenario.must_not_cite_as_clause,
            citations=final_citations,
        )
    else:
        citation_violations = count_citation_violations(
            hits, scenario.must_not_cite_as_clause
        )

    # Abstention check
    abstention_correct = True
    if scenario.should_abstain:
        abstention_correct = risk_level == "insufficient_evidence"
    else:
        # Should NOT abstain — if risk_level is insufficient, that's wrong
        if risk_level == "insufficient_evidence":
            abstention_correct = False

    # Second retrieval check
    second_retrieval_correct = (
        second_retrieval_triggered == scenario.should_trigger_second_retrieval
    )

    # Determine bad case
    bad_reasons: list[str] = []
    if scenario.expected_sources and recall_5 == 0.0 and not scenario.should_abstain:
        bad_reasons.append("zero_recall_at_5")
    if not abstention_correct:
        bad_reasons.append("abstention_incorrect")
    if citation_violations > 0:
        bad_reasons.append(f"citation_violations={citation_violations}")

    return CaseMetricResult(
        case_id=scenario.case_id,
        recall_at_3=round(recall_3, 4),
        recall_at_5=round(recall_5, 4),
        mrr_at_10=round(mrr, 4),
        candidate_recall_at_50=round(candidate_recall_50, 4),
        distinct_source_recall_at_5=round(distinct_recall_5, 4),
        duplicate_source_count_at_10=duplicate_sources_10,
        citation_violation_count=citation_violations,
        abstention_correct=abstention_correct,
        second_retrieval_correct=second_retrieval_correct,
        actual_sources=ordered_unique_sources(hits),
        missing_sources=missing_5,
        is_bad_case=len(bad_reasons) > 0,
        bad_reasons=bad_reasons,
        risk_level=risk_level,
    )


def aggregate_metrics(
    case_results: list[CaseMetricResult],
    mode: str,
) -> object:
    """Aggregate per-case metrics into mode-level summary."""

    from law_agent.review.evalset.schemas import ModeMetrics

    total = len(case_results)
    if total == 0:
        return ModeMetrics(
            mode=mode,
            mean_recall_at_3=0.0,
            mean_recall_at_5=0.0,
            mean_mrr_at_10=0.0,
            mean_candidate_recall_at_50=0.0,
            mean_distinct_source_recall_at_5=0.0,
            mean_duplicate_source_count_at_10=0.0,
            abstention_accuracy=0.0,
            second_retrieval_accuracy=0.0,
            total_citation_violations=0,
            bad_case_count=0,
            total_cases=0,
        )

    mean_recall_3 = sum(c.recall_at_3 for c in case_results) / total
    mean_recall_5 = sum(c.recall_at_5 for c in case_results) / total
    mean_mrr = sum(c.mrr_at_10 for c in case_results) / total
    mean_candidate_recall_50 = (
        sum(c.candidate_recall_at_50 for c in case_results) / total
    )
    mean_distinct_recall_5 = (
        sum(c.distinct_source_recall_at_5 for c in case_results) / total
    )
    mean_duplicate_sources_10 = (
        sum(c.duplicate_source_count_at_10 for c in case_results) / total
    )

    abstention_correct = sum(1 for c in case_results if c.abstention_correct)
    second_retrieval_correct = sum(1 for c in case_results if c.second_retrieval_correct)

    total_violations = sum(c.citation_violation_count for c in case_results)
    bad_count = sum(1 for c in case_results if c.is_bad_case)

    return ModeMetrics(
        mode=mode,
        mean_recall_at_3=round(mean_recall_3, 4),
        mean_recall_at_5=round(mean_recall_5, 4),
        mean_mrr_at_10=round(mean_mrr, 4),
        mean_candidate_recall_at_50=round(mean_candidate_recall_50, 4),
        mean_distinct_source_recall_at_5=round(mean_distinct_recall_5, 4),
        mean_duplicate_source_count_at_10=round(mean_duplicate_sources_10, 4),
        abstention_accuracy=round(abstention_correct / total, 4),
        second_retrieval_accuracy=round(second_retrieval_correct / total, 4),
        total_citation_violations=total_violations,
        bad_case_count=bad_count,
        total_cases=total,
    )
