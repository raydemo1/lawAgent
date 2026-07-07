"""Integration tests for keyword retrieval service (Issue 5)."""

from pathlib import Path

from law_agent.data.io import write_jsonl
from law_agent.data.schemas import Chunk
from law_agent.review.io import (
    read_retrieval_traces,
    read_review_cases,
    review_cases_path,
    write_review_cases,
)
from law_agent.review.service import (
    create_review_case,
    run_hybrid_retrieval,
    run_keyword_retrieval,
)
from law_agent.review.schemas import ReviewFacts, RetrievalQuery

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS


def _write_fixture_corpus(tmp_path: Path) -> Path:
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(chunks_path, FIXTURE_CHUNKS)
    return chunks_path


def test_run_keyword_retrieval_writes_hits_to_trace(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    response = create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_keyword_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
    )

    assert len(trace.keyword_results) > 0
    assert all(h.retriever == "keyword" for h in trace.keyword_results)
    assert all(h.score > 0 for h in trace.keyword_results)
    assert [h.rank for h in trace.keyword_results] == list(range(len(trace.keyword_results)))


def test_run_keyword_retrieval_persists_to_jsonl(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="数据出境安全评估申报条件",
        material_text="手机号发送给新加坡服务商。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    run_keyword_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    traces = read_retrieval_traces(tmp_path / "retrieval_traces.jsonl")
    assert len(traces) == 1
    assert len(traces[0].keyword_results) > 0
    assert traces[0].queries  # original queries preserved


def test_run_keyword_retrieval_preserves_queries_and_evidence_check(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    response = create_review_case(
        question="数据出境安全评估",
        material_text="手机号发送给新加坡服务商。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )
    original_queries = response.trace.queries

    trace = run_keyword_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    assert trace.queries == original_queries
    assert trace.evidence_self_check.status == "not_checked"
    assert trace.vector_results == []
    assert trace.hybrid_results == []


def test_create_review_case_llm_mode_adds_high_confidence_query_supplements(
    tmp_path: Path,
) -> None:
    def llm_missed_facts(_material_text: str, _question: str | None = None) -> ReviewFacts:
        return ReviewFacts()

    def llm_missed_queries(
        question: str,
        _facts: ReviewFacts,
        _material_text: str | None = None,
    ) -> list[RetrievalQuery]:
        return [
            RetrievalQuery(query_id="q_1", query_type="legal_issue", text=question)
        ]

    response = create_review_case(
        question="天津自贸区数据出境是否适用负面清单？",
        material_text="公司在天津自贸区开展智能网联汽车业务，涉及数据出境。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
        review_mode="llm",
        facts_extractor=llm_missed_facts,
        query_planner=llm_missed_queries,
    )

    assert response.review_case.review_facts.region == "天津"
    assert response.review_case.review_facts.industry == "智能网联汽车"
    query_types = [query.query_type for query in response.trace.queries]
    assert "region_condition" in query_types
    assert "industry_condition" in query_types
    assert "missing_information" not in query_types


def test_run_keyword_retrieval_data_export_query_finds_assessment_chunk(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    trace = run_keyword_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
    )

    chunk_ids = [h.chunk_id for h in trace.keyword_results]
    assert "chunk_assessment" in chunk_ids


def test_run_keyword_retrieval_unknown_case_raises(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="问题",
        material_text="材料",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    import pytest

    with pytest.raises(ValueError, match="not found"):
        run_keyword_retrieval(
            case_id="review_unknown",
            chunks_path=chunks_path,
            output_dir=tmp_path,
        )


def test_run_keyword_retrieval_no_traces_file_raises(tmp_path: Path) -> None:
    chunks_path = _write_fixture_corpus(tmp_path)

    import pytest

    with pytest.raises(ValueError, match="does not exist"):
        run_keyword_retrieval(
            case_id="review_test",
            chunks_path=chunks_path,
            output_dir=tmp_path,
        )


def test_run_hybrid_retrieval_with_none_latest_result_id(tmp_path: Path) -> None:
    """run_hybrid_retrieval must not raise NameError when latest_result_id is None.

    Bug 2 (P3): service.py used ``case.latest_result_id or id_factory("result")``
    in run_hybrid_retrieval(), but ``id_factory`` is not defined in that scope
    (it is neither a parameter nor imported). Normal new cases have
    ``latest_result_id`` set, so the ``or`` short-circuits and the bug stays
    hidden. But old or hand-written cases with ``latest_result_id=None`` raise
    ``NameError: name 'id_factory' is not defined``.
    """

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    # Simulate an old / hand-written case that has no latest_result_id.
    cases_path = review_cases_path(tmp_path)
    cases = read_review_cases(cases_path)
    assert cases, "expected the review case created above to be persisted"
    cases[0] = cases[0].model_copy(update={"latest_result_id": None})
    write_review_cases(cases_path, cases)

    # Before the fix this raised NameError: name 'id_factory' is not defined.
    trace = run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
        top_k=5,
    )

    assert trace is not None
    assert len(trace.hybrid_results) > 0
