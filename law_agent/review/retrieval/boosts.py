"""Metadata boost rules for hybrid retrieval.

Issue 6: Apply soft metadata boosts based on ``ReviewFacts`` and query type.
Boosts are multipliers on the RRF score — they elevate matching evidence
without hard-filtering other roles, per the implementation plan: "检索阶段
默认软加权，引用阶段严格治理".

Boost rules:
- ``primary_legal_basis``: always slightly boosted (national law priority)
- ``conditional_local_basis``: boosted when ``ReviewFacts.region`` matches
  the chunk's ``applicable_region``
- ``conditional_industry_basis``: boosted when ``ReviewFacts.industry``
  matches the chunk's ``applicable_subjects`` or ``topic_tags``
- ``implementation_reference``: boosted for missing_information queries
- ``interpretation_auxiliary``: always slightly demoted (keep retrievable
  but lower authority)
"""

from __future__ import annotations

from law_agent.data.schemas import Chunk
from law_agent.review.schemas import ReviewFacts, RetrievalHit, RetrievalQueryType

# ---------------------------------------------------------------------------
# Region mapping: Chinese name -> ISO 3166-2 subdivision code
# ---------------------------------------------------------------------------

_REGION_CODE_MAP: dict[str, str] = {
    "上海": "CN-SH",
    "广东": "CN-GD",
    "深圳": "CN-GD-SZ",
    "天津": "CN-TJ",
    "福建": "CN-FJ",
    "广西": "CN-GX",
    "重庆": "CN-CQ",
    "浙江": "CN-ZJ",
    "海南": "CN-HI",
    "北京": "CN-BJ",
    "江苏": "CN-JS",
}

# ---------------------------------------------------------------------------
# Industry matching: fact industry -> keywords to match in applicable_subjects
# and topic_tags
# ---------------------------------------------------------------------------

_INDUSTRY_KEYWORD_MAP: dict[str, list[str]] = {
    "智能网联汽车": ["汽车", "智能网联"],
    "汽车": ["汽车"],
    "金融": ["金融"],
    "金融信息服务": ["金融"],
    "医疗": ["医疗", "健康"],
    "教育": ["教育"],
}


# ---------------------------------------------------------------------------
# Boost factor constants
# ---------------------------------------------------------------------------

PRIMARY_LEGAL_BASIS_BOOST = 1.2
CONDITIONAL_LOCAL_BASIS_BOOST = 1.5
CONDITIONAL_INDUSTRY_BASIS_BOOST = 1.4
IMPLEMENTATION_REFERENCE_BOOST = 1.15
INTERPRETATION_AUXILIARY_BOOST = 0.85


def compute_boost_for_hit(
    hit: RetrievalHit,
    chunk: Chunk,
    facts: ReviewFacts,
    query_type: RetrievalQueryType | None = None,
) -> float:
    """Compute a multiplicative boost factor for a single hit.

    Returns 1.0 when no boost applies. Multiple matching conditions
    stack multiplicatively, but the total is capped to avoid runaway
    inflation.
    """

    boost = 1.0
    role = hit.citation_role

    # Primary legal basis: always slightly elevated
    if role == "primary_legal_basis":
        boost *= PRIMARY_LEGAL_BASIS_BOOST

    # Conditional local basis: boost when region matches
    if role == "conditional_local_basis" and facts.region:
        region_code = _REGION_CODE_MAP.get(facts.region, facts.region)
        if chunk.applicable_region == region_code or chunk.applicable_region == facts.region:
            boost *= CONDITIONAL_LOCAL_BASIS_BOOST

    # Conditional industry basis: boost when industry matches
    if role == "conditional_industry_basis" and facts.industry:
        keywords = _INDUSTRY_KEYWORD_MAP.get(facts.industry, [facts.industry])
        subject_text = " ".join(chunk.applicable_subjects)
        tag_text = " ".join(chunk.topic_tags)
        combined = subject_text + " " + tag_text
        if any(kw in combined for kw in keywords):
            boost *= CONDITIONAL_INDUSTRY_BASIS_BOOST

    # Implementation reference: boost for missing_information queries
    if role == "implementation_reference" and query_type == "missing_information":
        boost *= IMPLEMENTATION_REFERENCE_BOOST

    # Interpretation auxiliary: always slightly demoted
    if role == "interpretation_auxiliary":
        boost *= INTERPRETATION_AUXILIARY_BOOST

    return boost


def compute_boosts_summary(
    facts: ReviewFacts,
    query_types: list[RetrievalQueryType | None],
) -> dict[str, float]:
    """Build a human-readable summary of active boost rules for the trace.

    This is stored in ``RetrievalTrace.metadata_boosts`` so the trace
    records which boost rules were active, even if individual hits don't
    all trigger them.
    """

    summary: dict[str, float] = {
        "primary_legal_basis": PRIMARY_LEGAL_BASIS_BOOST,
        "interpretation_auxiliary": INTERPRETATION_AUXILIARY_BOOST,
    }

    if facts.region:
        region_code = _REGION_CODE_MAP.get(facts.region, facts.region)
        summary[f"conditional_local_basis:{region_code}"] = CONDITIONAL_LOCAL_BASIS_BOOST

    if facts.industry:
        summary[f"conditional_industry_basis:{facts.industry}"] = CONDITIONAL_INDUSTRY_BASIS_BOOST

    if "missing_information" in query_types:
        summary["implementation_reference:missing_information"] = IMPLEMENTATION_REFERENCE_BOOST

    return summary


def apply_boosts_to_hits(
    hits: list[RetrievalHit],
    chunks_by_id: dict[str, Chunk],
    facts: ReviewFacts,
    query_type: RetrievalQueryType | None = None,
) -> list[RetrievalHit]:
    """Apply metadata boosts to a list of hits, returning updated copies.

    The ``score`` field is multiplied by the boost factor. Original scores
    are not preserved separately — the trace's ``metadata_boosts`` dict
    records the active rules.
    """

    boosted: list[RetrievalHit] = []
    for hit in hits:
        chunk = chunks_by_id.get(hit.chunk_id)
        if chunk is None:
            boosted.append(hit)
            continue
        factor = compute_boost_for_hit(hit, chunk, facts, query_type)
        boosted.append(
            hit.model_copy(update={"score": round(hit.score * factor, 6)})
        )
    return boosted
