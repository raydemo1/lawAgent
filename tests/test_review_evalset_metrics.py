"""Tests for citation-violation counting based on final citations (Bug 2).

Bug: ``count_citation_violations()`` checked retrieval ``hits`` with
``can_cite_clause=True``. That produced false positives (a forbidden chunk
retrieved but NOT used as a final clause-level citation) and false negatives
(a demoted citation with ``can_cite_clause=False`` but ``usage="legal_basis"``).

The fix counts violations against the final ``CitationGroup`` /
``ReviewResult.citations`` where ``usage in ("legal_basis", "conditional_basis")``.
"""

from law_agent.review.evalset.metrics import evaluate_case
from law_agent.review.evalset.schemas import EvalScenario
from law_agent.review.schemas import Citation, CitationGroup, RetrievalHit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hit(
    source_id: str = "s1",
    chunk_id: str = "c1",
    citation_role: str = "primary_legal_basis",
    can_cite: bool = True,
    rank: int = 0,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id, doc_id="d1", source_id=source_id, title="t", text="x",
        score=1.0, rank=rank, retriever="hybrid",
        citation_role=citation_role, can_cite_clause=can_cite, source_url="u",
    )


def _citation(
    source_id: str = "s1",
    chunk_id: str = "c1",
    citation_role: str = "primary_legal_basis",
    can_cite_clause: bool = True,
    usage: str = "legal_basis",
) -> Citation:
    return Citation(
        source_id=source_id,
        chunk_id=chunk_id,
        title="t",
        source_url="u",
        citation_role=citation_role,
        can_cite_clause=can_cite_clause,
        usage=usage,
    )


def _scenario(must_not_cite_as_clause: list[str]) -> EvalScenario:
    return EvalScenario(
        case_id="test_citation",
        question="问题",
        material_text="材料",
        expected_sources=["s1"],
        must_not_cite_as_clause=must_not_cite_as_clause,
    )


# ---------------------------------------------------------------------------
# Bug 2: citation violations must use final citations, not raw retrieval hits
# ---------------------------------------------------------------------------

def test_citation_violation_uses_final_citations_not_hits() -> None:
    """A forbidden chunk retrieved but NOT used as a final clause-level
    citation must NOT be counted as a violation.

    Under the old hit-based logic, the forbidden chunk appearing in
    ``hits`` with ``can_cite_clause=True`` would be a violation. But here it
    is demoted to ``implementation_reference`` in the final citation groups,
    so it is not cited as ``legal_basis`` / ``conditional_basis`` and the
    violation count must be 0.
    """

    scenario = _scenario(must_not_cite_as_clause=["chunk_forbidden"])

    # Retrieval hits include the forbidden chunk with can_cite_clause=True.
    hits = [
        _hit(source_id="s1", chunk_id="chunk_ok", can_cite=True, rank=0),
        _hit(source_id="s2", chunk_id="chunk_forbidden", can_cite=True, rank=1),
    ]

    # Final citations: chunk_forbidden is demoted to implementation_reference,
    # NOT a clause-level (legal_basis / conditional_basis) citation.
    citation_groups = [
        CitationGroup(
            usage="legal_basis",
            citations=[
                _citation(
                    source_id="s1", chunk_id="chunk_ok",
                    citation_role="primary_legal_basis",
                    can_cite_clause=True, usage="legal_basis",
                ),
            ],
        ),
        CitationGroup(
            usage="implementation_reference",
            citations=[
                _citation(
                    source_id="s2", chunk_id="chunk_forbidden",
                    citation_role="implementation_reference",
                    can_cite_clause=False, usage="implementation_reference",
                ),
            ],
        ),
    ]

    result = evaluate_case(scenario, hits, citation_groups=citation_groups)

    assert result.citation_violation_count == 0
    assert not any("citation_violations" in r for r in result.bad_reasons)


def test_citation_violation_detected_in_final_legal_basis() -> None:
    """A forbidden chunk used as a ``legal_basis`` final citation IS a
    violation, even if the demotion bug set ``can_cite_clause=False``.
    """

    scenario = _scenario(must_not_cite_as_clause=["chunk_forbidden"])

    hits = [
        _hit(source_id="s1", chunk_id="chunk_ok", can_cite=True, rank=0),
        _hit(source_id="s2", chunk_id="chunk_forbidden", can_cite=True, rank=1),
    ]

    # chunk_forbidden appears in a legal_basis citation group -> violation.
    # Note can_cite_clause=False mimics the demotion bug; the final usage is
    # what matters now.
    citation_groups = [
        CitationGroup(
            usage="legal_basis",
            citations=[
                _citation(
                    source_id="s1", chunk_id="chunk_ok",
                    citation_role="primary_legal_basis",
                    can_cite_clause=True, usage="legal_basis",
                ),
                _citation(
                    source_id="s2", chunk_id="chunk_forbidden",
                    citation_role="primary_legal_basis",
                    can_cite_clause=False, usage="legal_basis",
                ),
            ],
        ),
    ]

    result = evaluate_case(scenario, hits, citation_groups=citation_groups)

    assert result.citation_violation_count == 1
    assert result.is_bad_case is True
    assert any("citation_violations" in r for r in result.bad_reasons)
