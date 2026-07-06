import pytest
from pydantic import ValidationError

from law_agent.review.schemas import (
    EvidenceSelfCheck,
    MaterialRecord,
    ReviewCase,
    ReviewFacts,
    ReviewResult,
    RetrievalTrace,
)


def test_review_facts_accepts_empty_placeholder_state() -> None:
    facts = ReviewFacts()

    assert facts.business_activity is None
    assert facts.data_types == []
    assert facts.cross_border_transfer is None
    assert facts.missing_information == []


def test_review_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReviewFacts(extra_field="not allowed")


def test_review_case_points_to_latest_result() -> None:
    facts = ReviewFacts()
    case = ReviewCase(
        review_case_id="review_test",
        created_at="2026-07-06T00:00:00+00:00",
        question="这个场景是否需要数据出境安全评估？",
        material=MaterialRecord(material_text="手机号发送给新加坡服务商。"),
        review_facts=facts,
        trace_id="trace_test",
        latest_result_id="result_test",
    )

    assert case.latest_result_id == "result_test"
    assert case.material.parser == "pasted_text"


def test_review_result_is_separate_from_case() -> None:
    result = ReviewResult(
        review_result_id="result_test",
        review_case_id="review_test",
        trace_id="trace_test",
        risk_level="insufficient_evidence",
        conclusion="Review case created. Evidence retrieval has not run yet.",
        review_facts=ReviewFacts(),
    )

    assert result.review_result_id == "result_test"
    assert result.citations == []


def test_retrieval_trace_starts_not_checked() -> None:
    trace = RetrievalTrace(
        trace_id="trace_test",
        review_case_id="review_test",
        created_at="2026-07-06T00:00:00+00:00",
        evidence_self_check=EvidenceSelfCheck(status="not_checked"),
    )

    assert trace.evidence_self_check.status == "not_checked"
    assert trace.keyword_results == []
