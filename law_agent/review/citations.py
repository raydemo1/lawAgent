"""Citation validation and grouping for governed review results.

Issue 8: Validate that clause-level citations only use ``can_cite_clause=True``
evidence, and group citations by usage category:
- ``legal_basis``: primary_legal_basis with can_cite_clause
- ``conditional_basis``: conditional_local_basis / conditional_industry_basis
- ``implementation_reference``: implementation_reference (TC260/GB/T etc.)
- ``policy_explanation``: interpretation_auxiliary (official Q&A etc.)

Local and industry evidence includes scope wording to make applicability
explicit.
"""

from __future__ import annotations

from law_agent.data.schemas import Chunk
from law_agent.review.schemas import (
    Citation,
    CitationGroup,
    CitationUsage,
    ReviewFacts,
    RetrievalHit,
)


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------

class CitationValidationError(Exception):
    """Raised when a citation violates governance rules."""


def validate_citation(hit: RetrievalHit, usage: CitationUsage) -> list[str]:
    """Validate a single hit for a given usage. Returns violation messages.

    Rules:
    - ``legal_basis`` usage requires ``can_cite_clause=True``
    - ``conditional_basis`` usage requires ``can_cite_clause=True``
    - ``implementation_reference`` and ``policy_explanation`` allow
      ``can_cite_clause=False``
    """

    violations: list[str] = []

    if usage in ("legal_basis", "conditional_basis"):
        if not hit.can_cite_clause:
            violations.append(
                f"citation_role={hit.citation_role} usage={usage} requires "
                f"can_cite_clause=True, but chunk {hit.chunk_id} has can_cite_clause=False"
            )

    return violations


def validate_citations(hits_with_usage: list[tuple[RetrievalHit, CitationUsage]]) -> list[str]:
    """Validate all citations. Returns list of violation messages (empty if valid)."""

    violations: list[str] = []
    for hit, usage in hits_with_usage:
        violations.extend(validate_citation(hit, usage))
    return violations


# ---------------------------------------------------------------------------
# Citation grouping
# ---------------------------------------------------------------------------

def _determine_usage(hit: RetrievalHit) -> CitationUsage:
    """Determine the citation usage category from the hit's citation_role."""

    if hit.citation_role == "primary_legal_basis":
        return "legal_basis"
    if hit.citation_role in ("conditional_local_basis", "conditional_industry_basis"):
        return "conditional_basis"
    if hit.citation_role == "implementation_reference":
        return "implementation_reference"
    if hit.citation_role == "interpretation_auxiliary":
        return "policy_explanation"
    # Fallback: treat unknown roles as implementation_reference
    return "implementation_reference"


def _build_citation(hit: RetrievalHit, chunk: Chunk | None = None) -> Citation:
    """Build a Citation from a RetrievalHit, optionally enriched with chunk data."""

    citation_label = None
    if chunk is not None:
        citation_label = chunk.citation_label

    return Citation(
        source_id=hit.source_id,
        chunk_id=hit.chunk_id,
        title=hit.title,
        source_url=hit.source_url,
        citation_role=hit.citation_role,
        can_cite_clause=hit.can_cite_clause,
        usage=_determine_usage(hit),
        citation_label=citation_label,
    )


def _build_scope_note(usage: CitationUsage, facts: ReviewFacts, chunk: Chunk | None) -> str | None:
    """Build scope wording for conditional basis citations."""

    if usage == "conditional_basis" and chunk is not None:
        if chunk.applicable_region and chunk.applicable_region != "CN":
            return f"仅适用于地区：{chunk.applicable_region}"
        if chunk.applicable_subjects:
            return f"仅适用于：{', '.join(chunk.applicable_subjects[:3])}"
    if usage == "implementation_reference":
        return "参考标准/实施指南，不作为条款级法律依据"
    if usage == "policy_explanation":
        return "政策口径补充，不作为条款级法律依据"
    return None


def group_citations(
    hits: list[RetrievalHit],
    facts: ReviewFacts,
    chunks_by_id: dict[str, Chunk] | None = None,
) -> tuple[list[CitationGroup], list[str]]:
    """Group hits into citation groups by usage category.

    Returns:
        - List of CitationGroup (non-empty groups only)
        - List of validation violation messages (empty if all valid)

    Clause-level citations (legal_basis, conditional_basis) that fail
    validation (can_cite_clause=False) are demoted to implementation_reference
    rather than discarded, so the evidence is still visible but not
    presented as clause-level legal basis.
    """

    if chunks_by_id is None:
        chunks_by_id = {}

    # First pass: determine usage and validate
    hits_with_usage: list[tuple[RetrievalHit, CitationUsage]] = []
    demoted_hits: list[RetrievalHit] = []

    for hit in hits:
        usage = _determine_usage(hit)
        violations = validate_citation(hit, usage)
        if violations:
            # Demote to implementation_reference
            demoted_hits.append(hit)
            hits_with_usage.append((hit, "implementation_reference"))
        else:
            hits_with_usage.append((hit, usage))

    all_violations = validate_citations(hits_with_usage)

    # Second pass: build citations and group
    groups: dict[CitationUsage, list[Citation]] = {
        "legal_basis": [],
        "conditional_basis": [],
        "implementation_reference": [],
        "policy_explanation": [],
    }

    for hit, usage in hits_with_usage:
        chunk = chunks_by_id.get(hit.chunk_id)
        citation = _build_citation(hit, chunk)
        groups[usage].append(citation)

    # Build CitationGroup list with scope notes
    result_groups: list[CitationGroup] = []
    for usage in ("legal_basis", "conditional_basis", "implementation_reference", "policy_explanation"):
        citations = groups[usage]
        if not citations:
            continue

        # Build scope note from first citation's chunk
        scope_note = None
        if citations:
            first_hit = next((h for h, u in hits_with_usage if u == usage), None)
            if first_hit:
                chunk = chunks_by_id.get(first_hit.chunk_id)
                scope_note = _build_scope_note(usage, facts, chunk)

        result_groups.append(
            CitationGroup(
                usage=usage,
                citations=citations,
                scope_note=scope_note,
            )
        )

    return result_groups, all_violations


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def count_citations_by_usage(groups: list[CitationGroup]) -> dict[str, int]:
    """Count citations per usage category."""

    counts: dict[str, int] = {}
    for group in groups:
        counts[group.usage] = len(group.citations)
    return counts
