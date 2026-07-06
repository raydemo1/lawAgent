"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Issue 6: Fuse keyword and vector_mock results using deterministic RRF scoring.
RRF formula: ``rrf_score = sum(1 / (k + rank))`` over all retrievers where
the chunk appears. Metadata boosts are applied as a post-RRF multiplier.

The fused results are stored in ``RetrievalTrace.hybrid_results`` with
component scores preserved for traceability.
"""

from __future__ import annotations

from law_agent.review.schemas import RetrievalHit

DEFAULT_RRF_K = 60


def rrf_fuse(
    keyword_hits: list[RetrievalHit],
    vector_hits: list[RetrievalHit],
    *,
    top_k: int = 10,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievalHit]:
    """Fuse keyword and vector_mock results using RRF.

    Each retriever contributes ``1 / (k + rank)`` per hit. A chunk
    appearing in both retrievers gets the sum. Results are sorted by
    fused score and re-ranked. The ``retriever`` field is set to
    ``"hybrid"`` and the ``score`` field holds the RRF score.

    When the same chunk appears in both lists, the hit with more
    metadata (first encountered) is used as the base, and the score
    reflects both contributions.
    """

    # Build rank maps per retriever
    keyword_ranks: dict[str, int] = {}
    for hit in keyword_hits:
        keyword_ranks[hit.chunk_id] = hit.rank

    vector_ranks: dict[str, int] = {}
    for hit in vector_hits:
        vector_ranks[hit.chunk_id] = hit.rank

    # All chunk IDs that appear in either list
    all_chunk_ids = set(keyword_ranks) | set(vector_ranks)

    # Build a lookup for the "best" hit per chunk_id (prefer keyword as base
    # since it has more field-level detail)
    hit_by_chunk: dict[str, RetrievalHit] = {}
    for hit in keyword_hits:
        hit_by_chunk[hit.chunk_id] = hit
    for hit in vector_hits:
        if hit.chunk_id not in hit_by_chunk:
            hit_by_chunk[hit.chunk_id] = hit

    # Compute RRF scores
    scored: list[tuple[float, str]] = []
    for chunk_id in all_chunk_ids:
        rrf_score = 0.0
        if chunk_id in keyword_ranks:
            rrf_score += 1.0 / (k + keyword_ranks[chunk_id])
        if chunk_id in vector_ranks:
            rrf_score += 1.0 / (k + vector_ranks[chunk_id])
        scored.append((rrf_score, chunk_id))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))

    fused: list[RetrievalHit] = []
    for rank, (rrf_score, chunk_id) in enumerate(scored[:top_k]):
        base = hit_by_chunk[chunk_id]
        fused.append(
            base.model_copy(
                update={
                    "score": round(rrf_score, 6),
                    "rank": rank,
                    "retriever": "hybrid",
                }
            )
        )
    return fused
