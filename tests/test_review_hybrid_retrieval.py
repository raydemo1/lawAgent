"""Tests for hybrid retrieval: vector mock, boosts, RRF, neighbors (Issue 6)."""

from pathlib import Path

import pytest

from law_agent.data.io import write_jsonl
from law_agent.data.schemas import Chunk
from law_agent.review.retrieval.boosts import (
    INTERPRETATION_AUXILIARY_BOOST,
    MISSING_INFORMATION_QUERY_WEIGHT,
    PRIMARY_LEGAL_BASIS_BOOST,
    apply_boosts_to_hits,
    compute_boost_for_hit,
    compute_boosts_summary,
)
from law_agent.review.retrieval.fusion import rrf_fuse
from law_agent.review.retrieval.neighbors import expand_neighbors
from law_agent.review.retrieval.vector_mock import VectorMockRetriever
from law_agent.review.schemas import ReviewFacts, RetrievalHit

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS, _make_chunk


# ---------------------------------------------------------------------------
# Vector mock retriever tests
# ---------------------------------------------------------------------------

def test_vector_mock_returns_hits() -> None:
    retriever = VectorMockRetriever(FIXTURE_CHUNKS)
    hits = retriever.search("数据出境安全评估", top_k=3)

    assert len(hits) > 0
    assert all(h.retriever == "vector_mock" for h in hits)
    assert all(h.score > 0 for h in hits)


def test_vector_mock_uses_topic_tags_for_broader_coverage() -> None:
    """Vector mock should find chunks that keyword misses via topic_tags."""

    chunk_with_tags = _make_chunk(
        chunk_id="chunk_tagged",
        title="某标准",
        text="本标准规定了相关要求。",
        citation_role="implementation_reference",
        citation_label=None,
        can_cite_clause=False,
    )
    # Manually set topic_tags (the _make_chunk helper doesn't expose it)
    chunk_with_tags = chunk_with_tags.model_copy(
        update={"topic_tags": ["数据出境", "安全评估"]}
    )

    retriever = VectorMockRetriever([chunk_with_tags])
    hits = retriever.search("数据出境安全评估", top_k=1)

    assert len(hits) == 1
    assert hits[0].chunk_id == "chunk_tagged"


def test_vector_mock_empty_query_returns_empty() -> None:
    retriever = VectorMockRetriever(FIXTURE_CHUNKS)
    assert retriever.search("   ", top_k=3) == []


def test_vector_mock_records_query_type() -> None:
    retriever = VectorMockRetriever(FIXTURE_CHUNKS)
    hits = retriever.search("数据出境", top_k=1, query_type="legal_issue")
    assert all(h.matched_query_type == "legal_issue" for h in hits)


# ---------------------------------------------------------------------------
# Metadata boost tests
# ---------------------------------------------------------------------------

def test_primary_legal_basis_gets_boost() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=1.0, rank=0, retriever="keyword",
        citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
    )
    chunk = _make_chunk(chunk_id="c1")
    facts = ReviewFacts()

    boost = compute_boost_for_hit(hit, chunk, facts)
    assert boost == pytest.approx(PRIMARY_LEGAL_BASIS_BOOST)


def test_interpretation_auxiliary_gets_demoted() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=1.0, rank=0, retriever="keyword",
        citation_role="interpretation_auxiliary", can_cite_clause=False, source_url="u",
    )
    chunk = _make_chunk(chunk_id="c1", citation_role="interpretation_auxiliary")
    facts = ReviewFacts()

    boost = compute_boost_for_hit(hit, chunk, facts)
    assert boost == pytest.approx(INTERPRETATION_AUXILIARY_BOOST)


def test_conditional_local_basis_boosted_when_region_matches() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=1.0, rank=0, retriever="keyword",
        citation_role="conditional_local_basis", can_cite_clause=False, source_url="u",
    )
    chunk = _make_chunk(
        chunk_id="c1",
        citation_role="conditional_local_basis",
        applicable_region="CN-SH",
    )
    facts = ReviewFacts(region="上海")

    boost = compute_boost_for_hit(hit, chunk, facts)
    assert boost > 1.0


def test_conditional_local_basis_not_boosted_when_region_mismatch() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=1.0, rank=0, retriever="keyword",
        citation_role="conditional_local_basis", can_cite_clause=False, source_url="u",
    )
    chunk = _make_chunk(
        chunk_id="c1",
        citation_role="conditional_local_basis",
        applicable_region="CN-BJ",
    )
    facts = ReviewFacts(region="上海")

    boost = compute_boost_for_hit(hit, chunk, facts)
    assert boost == 1.0  # no boost when region doesn't match


def test_conditional_industry_basis_boosted_when_industry_matches() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=1.0, rank=0, retriever="keyword",
        citation_role="conditional_industry_basis", can_cite_clause=True, source_url="u",
    )
    chunk = _make_chunk(
        chunk_id="c1",
        citation_role="conditional_industry_basis",
    ).model_copy(update={"applicable_subjects": ["汽车数据处理者"], "topic_tags": ["汽车行业"]})
    facts = ReviewFacts(industry="汽车")

    boost = compute_boost_for_hit(hit, chunk, facts)
    assert boost > 1.0


def test_boosts_summary_records_active_rules() -> None:
    facts = ReviewFacts(region="上海", industry="汽车")
    summary = compute_boosts_summary(facts, ["legal_issue", "missing_information"])

    assert "primary_legal_basis" in summary
    assert "interpretation_auxiliary" in summary
    assert "conditional_local_basis:CN-SH" in summary
    assert "conditional_industry_basis:汽车" in summary
    assert "implementation_reference:missing_information" in summary


def test_apply_boosts_to_hits_multiplies_scores() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=2.0, rank=0, retriever="keyword",
        citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
    )
    chunk = _make_chunk(chunk_id="c1")
    facts = ReviewFacts()

    boosted = apply_boosts_to_hits([hit], {"c1": chunk}, facts)
    assert boosted[0].score == pytest.approx(2.0 * PRIMARY_LEGAL_BASIS_BOOST, rel=1e-4)


def test_missing_information_query_hits_are_downweighted() -> None:
    hit = RetrievalHit(
        chunk_id="c1", doc_id="d1", source_id="s1", title="t", text="x",
        score=2.0, rank=0, retriever="keyword",
        citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        matched_query_type="missing_information",
    )
    chunk = _make_chunk(chunk_id="c1")
    facts = ReviewFacts()

    boosted = apply_boosts_to_hits([hit], {"c1": chunk}, facts)

    assert boosted[0].score == pytest.approx(
        2.0 * PRIMARY_LEGAL_BASIS_BOOST * MISSING_INFORMATION_QUERY_WEIGHT,
        rel=1e-4,
    )


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------

def _make_hit(
    chunk_id: str, rank: int, score: float = 1.0, retriever: str = "keyword"
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id, doc_id="d", source_id="s", title="t", text="x",
        score=score, rank=rank, retriever=retriever,
        citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
    )


def test_rrf_fuse_combines_keyword_and_vector_ranks() -> None:
    keyword_hits = [_make_hit("a", rank=0), _make_hit("b", rank=1)]
    vector_hits = [_make_hit("a", rank=0), _make_hit("c", rank=1)]

    fused = rrf_fuse(keyword_hits, vector_hits, top_k=10)

    assert len(fused) == 3
    # Chunk "a" appears in both, should rank first
    assert fused[0].chunk_id == "a"
    assert fused[0].retriever == "hybrid"
    assert fused[0].rank == 0


def test_rrf_fuse_score_formula() -> None:
    """Verify RRF score = sum(1 / (k + rank)) for a chunk in both lists.

    Ranks are derived from each list's score ordering (see the fusion fix),
    so to place ``a`` at vector rank 1 we put a higher-scored hit ``b``
    ahead of it in the vector list. ``a`` then contributes keyword rank 0
    plus vector rank 1.
    """

    keyword_hits = [_make_hit("a", rank=0, score=1.0)]  # a at keyword rank 0
    vector_hits = [
        _make_hit("b", rank=0, score=1.0),  # higher score -> vector rank 0
        _make_hit("a", rank=1, score=0.5),  # lower score  -> vector rank 1
    ]

    fused = rrf_fuse(keyword_hits, vector_hits, top_k=2, k=60)

    a_hit = next(h for h in fused if h.chunk_id == "a")
    expected = 1.0 / (60 + 0) + 1.0 / (60 + 1)
    assert a_hit.score == pytest.approx(expected, rel=1e-5)


def test_rrf_fuse_respects_top_k() -> None:
    keyword_hits = [_make_hit(f"k{i}", rank=i) for i in range(5)]
    vector_hits = [_make_hit(f"v{i}", rank=i) for i in range(5)]

    fused = rrf_fuse(keyword_hits, vector_hits, top_k=3)

    assert len(fused) == 3


def test_rrf_fuse_preserves_metadata_from_base_hit() -> None:
    keyword_hits = [
        RetrievalHit(
            chunk_id="a", doc_id="d1", source_id="s1", title="法规标题",
            text="法规正文", score=1.0, rank=0, retriever="keyword",
            citation_role="primary_legal_basis", can_cite_clause=True,
            source_url="http://example.com", matched_query_type="legal_issue",
        )
    ]
    vector_hits: list[RetrievalHit] = []

    fused = rrf_fuse(keyword_hits, vector_hits, top_k=1)

    assert fused[0].title == "法规标题"
    assert fused[0].citation_role == "primary_legal_basis"
    assert fused[0].can_cite_clause is True
    assert fused[0].source_url == "http://example.com"
    assert fused[0].matched_query_type == "legal_issue"


# ---------------------------------------------------------------------------
# Neighbor expansion tests
# ---------------------------------------------------------------------------

def test_expand_neighbors_pulls_prev_and_next() -> None:
    chunk_a = _make_chunk(chunk_id="a", chunk_index=0, next_chunk_id="b")
    chunk_b = _make_chunk(chunk_id="b", chunk_index=1, prev_chunk_id="a", next_chunk_id="c")
    chunk_c = _make_chunk(chunk_id="c", chunk_index=2, prev_chunk_id="b")

    chunks_by_id = {"a": chunk_a, "b": chunk_b, "c": chunk_c}

    top_hits = [
        RetrievalHit(
            chunk_id="b", doc_id="d", source_id="s", title="t", text="x",
            score=1.0, rank=0, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        )
    ]

    neighbors = expand_neighbors(top_hits, chunks_by_id)

    neighbor_ids = [n.chunk_id for n in neighbors]
    assert "a" in neighbor_ids  # prev of b
    assert "c" in neighbor_ids  # next of b


def test_expand_neighbors_skips_chunks_already_in_top_hits() -> None:
    chunk_a = _make_chunk(chunk_id="a", chunk_index=0, next_chunk_id="b")
    chunk_b = _make_chunk(chunk_id="b", chunk_index=1, prev_chunk_id="a")

    chunks_by_id = {"a": chunk_a, "b": chunk_b}

    # Both a and b are in top hits, so no neighbors should be added
    top_hits = [
        RetrievalHit(
            chunk_id="a", doc_id="d", source_id="s", title="t", text="x",
            score=1.0, rank=0, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        ),
        RetrievalHit(
            chunk_id="b", doc_id="d", source_id="s", title="t", text="x",
            score=0.8, rank=1, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        ),
    ]

    neighbors = expand_neighbors(top_hits, chunks_by_id)
    assert len(neighbors) == 0


def test_expand_neighbors_deduplicates() -> None:
    """If two top hits share the same neighbor, it should only appear once."""

    chunk_a = _make_chunk(chunk_id="a", chunk_index=0, next_chunk_id="b")
    chunk_b = _make_chunk(chunk_id="b", chunk_index=1, prev_chunk_id="a", next_chunk_id="c")
    chunk_c = _make_chunk(chunk_id="c", chunk_index=2, prev_chunk_id="b", next_chunk_id="d")
    chunk_d = _make_chunk(chunk_id="d", chunk_index=3, prev_chunk_id="c")

    chunks_by_id = {"a": chunk_a, "b": chunk_b, "c": chunk_c, "d": chunk_d}

    # b and c are top hits; b's next is c (already in top), c's prev is b (already in top)
    # b's prev is a, c's next is d -> should get a and d
    top_hits = [
        RetrievalHit(
            chunk_id="b", doc_id="d", source_id="s", title="t", text="x",
            score=1.0, rank=0, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        ),
        RetrievalHit(
            chunk_id="c", doc_id="d", source_id="s", title="t", text="x",
            score=0.8, rank=1, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        ),
    ]

    neighbors = expand_neighbors(top_hits, chunks_by_id)
    neighbor_ids = [n.chunk_id for n in neighbors]
    assert "a" in neighbor_ids
    assert "d" in neighbor_ids
    # No duplicates
    assert len(neighbor_ids) == len(set(neighbor_ids))


def test_neighbor_rank_convention() -> None:
    chunk_a = _make_chunk(chunk_id="a", chunk_index=0, next_chunk_id="b")
    chunk_b = _make_chunk(chunk_id="b", chunk_index=1, prev_chunk_id="a")

    chunks_by_id = {"a": chunk_a, "b": chunk_b}

    top_hits = [
        RetrievalHit(
            chunk_id="b", doc_id="d", source_id="s", title="t", text="x",
            score=1.0, rank=0, retriever="hybrid",
            citation_role="primary_legal_basis", can_cite_clause=True, source_url="u",
        )
    ]

    neighbors = expand_neighbors(top_hits, chunks_by_id)
    # "a" is prev of "b", should have rank -1
    assert neighbors[0].rank == -1


# ---------------------------------------------------------------------------
# Integration: run_hybrid_retrieval service
# ---------------------------------------------------------------------------

def _write_fixture_corpus(tmp_path: Path) -> Path:
    chunks_path = tmp_path / "chunks.jsonl"
    # Add prev/next links to fixture chunks for neighbor testing
    linked_chunks = []
    for i, chunk in enumerate(FIXTURE_CHUNKS):
        linked = chunk.model_copy(
            update={
                "prev_chunk_id": FIXTURE_CHUNKS[i - 1].chunk_id if i > 0 else None,
                "next_chunk_id": FIXTURE_CHUNKS[i + 1].chunk_id if i < len(FIXTURE_CHUNKS) - 1 else None,
            }
        )
        linked_chunks.append(linked)
    write_jsonl(chunks_path, linked_chunks)
    return chunks_path


class _RecordingSearchManyRetriever:
    def __init__(self, chunks: list[Chunk], retriever: str) -> None:
        self.chunks = chunks
        self.retriever = retriever
        self.requested_top_ks: list[int] = []

    def search_many(self, queries, *, top_k: int = 10):
        self.requested_top_ks.append(top_k)
        hits = [
            RetrievalHit(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                source_id=chunk.source_id,
                title=chunk.title,
                text=chunk.text,
                score=float(len(self.chunks) - index),
                rank=index,
                retriever=self.retriever,
                citation_role=chunk.citation_role,
                can_cite_clause=chunk.can_cite_clause,
                source_url=chunk.source_url,
            )
            for index, chunk in enumerate(self.chunks[:top_k])
        ]
        return [hits for _query in queries]


def test_run_hybrid_retrieval_returns_all_components(tmp_path: Path) -> None:
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
    )

    assert len(trace.keyword_results) > 0
    assert len(trace.vector_results) > 0
    assert len(trace.hybrid_results) > 0
    assert all(h.retriever == "hybrid" for h in trace.hybrid_results)
    assert trace.metadata_boosts  # boost summary recorded


def test_run_hybrid_retrieval_uses_wide_candidate_pool_before_final_top_k(
    tmp_path: Path,
) -> None:
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks = [
        _make_chunk(
            chunk_id=f"wide_{index}",
            doc_id=f"doc_{index}",
            source_id=f"src_{index}",
            text=f"第{index}条 数据出境安全评估 申报条件。",
        )
        for index in range(120)
    ]
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(chunks_path, chunks)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )
    keyword = _RecordingSearchManyRetriever(chunks, "keyword")
    vector = _RecordingSearchManyRetriever(chunks, "vector_mock")

    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
        keyword_retriever=keyword,
        vector_retriever=vector,
    )

    assert keyword.requested_top_ks == [50]
    assert vector.requested_top_ks == [50]
    assert len(trace.keyword_results) == 50
    assert len(trace.vector_results) == 50
    assert len(trace.hybrid_results) == 5


def test_run_hybrid_retrieval_persists_to_trace(tmp_path: Path) -> None:
    from law_agent.review.io import read_retrieval_traces
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="数据出境安全评估",
        material_text="手机号发送给新加坡。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    traces = read_retrieval_traces(tmp_path / "retrieval_traces.jsonl")
    assert len(traces) == 1
    assert len(traces[0].hybrid_results) > 0
    assert len(traces[0].vector_results) > 0
    assert traces[0].metadata_boosts


def test_run_hybrid_retrieval_with_region_facts_boosts_local_evidence(tmp_path: Path) -> None:
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="上海数据出境负面清单要求？",
        material_text="公司在上海自贸区开展业务，涉及数据出境。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=10,
    )

    # The Shanghai chunk should appear in results (region boost applied)
    chunk_ids = [h.chunk_id for h in trace.hybrid_results]
    assert "chunk_shanghai" in chunk_ids

    # Boost summary should record the local basis boost
    assert any("CN-SH" in key for key in trace.metadata_boosts)


def test_run_hybrid_retrieval_non_matching_evidence_remains_present(tmp_path: Path) -> None:
    """Boosts should elevate matching evidence, not filter out others."""

    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=10,
    )

    # Multiple citation roles should be present (no hard filtering)
    roles = {h.citation_role for h in trace.hybrid_results}
    assert len(roles) > 1  # not just one role filtered in


def test_run_hybrid_retrieval_expands_neighbors(tmp_path: Path) -> None:
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="数据出境安全评估",
        material_text="手机号发送给新加坡。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
    )

    # Neighbors should be present (linked chunks have prev/next IDs)
    assert len(trace.neighbor_chunks) > 0
    # Neighbor ranks should be negative (convention)
    assert all(n.rank < 0 for n in trace.neighbor_chunks)
