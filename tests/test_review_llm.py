"""Tests for DeepSeek-owned review LLM nodes."""

from __future__ import annotations

import pytest

from law_agent.llm.openai_compatible import ChatMessage
from law_agent.review.facts import (
    build_fact_extraction_messages,
    extract_facts_with_deepseek,
)
from law_agent.review.evidence import (
    build_evidence_check_messages,
    run_self_check_with_deepseek,
)
from law_agent.review.llm import ReviewWorkflowFailed, StructuredLLMNode
from law_agent.review.query_planner import (
    build_query_planning_messages,
    plan_queries_with_deepseek,
)
from law_agent.review.result_builder import (
    build_result_generation_messages,
    build_review_result_with_deepseek,
)
from law_agent.review.schemas import ReviewFacts
from law_agent.review.schemas import EvidenceSelfCheck

from tests.test_review_result_builder import _hit


class FakeClient:
    def __init__(self, outputs: list[dict] | None = None, errors: list[Exception] | None = None):
        self.outputs = list(outputs or [])
        self.errors = list(errors or [])
        self.calls: list[list[ChatMessage]] = []

    def chat_json(self, messages: list[ChatMessage]) -> dict:
        self.calls.append(messages)
        if self.errors:
            raise self.errors.pop(0)
        return self.outputs.pop(0)


def _valid_facts_payload() -> dict:
    return {
        "business_activity": "移动 App 个性化推荐",
        "data_types": ["手机号", "定位信息"],
        "sensitive_personal_info": True,
        "cross_border_transfer": True,
        "overseas_recipient": "新加坡",
        "processing_purpose": "推荐优化",
        "legal_basis_or_consent": None,
        "industry": None,
        "region": "CN",
        "missing_information": ["legal_basis_or_consent"],
    }


def test_fact_prompt_contains_json_example() -> None:
    messages = build_fact_extraction_messages("材料", "问题")
    combined = "\n".join(message.content for message in messages)

    assert "json" in combined.lower()
    assert "json_example" in combined
    assert '"business_activity"' in combined


def test_query_prompt_contains_json_example() -> None:
    messages = build_query_planning_messages("问题", ReviewFacts(), "材料")
    combined = "\n".join(message.content for message in messages)

    assert "json" in combined.lower()
    assert "json_example" in combined
    assert '"queries"' in combined


def test_evidence_prompt_contains_json_example() -> None:
    messages = build_evidence_check_messages([_hit()], ReviewFacts(cross_border_transfer=True))
    combined = "\n".join(message.content for message in messages)

    assert "json" in combined.lower()
    assert "json_example" in combined
    assert '"second_retrieval_plan"' in combined


def test_result_prompt_contains_json_example() -> None:
    messages = build_result_generation_messages(
        facts=ReviewFacts(cross_border_transfer=True),
        self_check=EvidenceSelfCheck(status="sufficient"),
        evidence_hits=[_hit()],
    )
    combined = "\n".join(message.content for message in messages)

    assert "json" in combined.lower()
    assert "json_example" in combined
    assert '"risk_level"' in combined


def test_structured_node_retries_validation_failure() -> None:
    client = FakeClient(outputs=[{"extra": "bad"}, _valid_facts_payload()])
    node = StructuredLLMNode(
        node_name="fact_extraction",
        output_model=ReviewFacts,
        client=client,  # type: ignore[arg-type]
        max_retries=1,
        trace_id="trace_1",
    )

    facts = node.run([ChatMessage(role="user", content="json")])

    assert facts.cross_border_transfer is True
    assert len(client.calls) == 2


def test_structured_node_exhaustion_returns_review_failed() -> None:
    client = FakeClient(outputs=[{"extra": "bad"}, {"still": "bad"}])
    node = StructuredLLMNode(
        node_name="fact_extraction",
        output_model=ReviewFacts,
        client=client,  # type: ignore[arg-type]
        max_retries=1,
        trace_id="trace_1",
    )

    with pytest.raises(ReviewWorkflowFailed) as exc_info:
        node.run([ChatMessage(role="user", content="json")])

    failure = exc_info.value
    assert failure.failed_node == "fact_extraction"
    assert failure.reason == "pydantic_validation_failed"
    assert failure.attempts == 2
    assert failure.to_response()["status"] == "review_failed"
    assert failure.to_response()["trace_id"] == "trace_1"


def test_fact_extraction_requires_all_llm_fields() -> None:
    payload = _valid_facts_payload()
    payload.pop("missing_information")
    client = FakeClient(outputs=[payload])

    with pytest.raises(ReviewWorkflowFailed) as exc_info:
        extract_facts_with_deepseek(
            "手机号发送给新加坡",
            "是否需要数据出境安全评估？",
            client=client,  # type: ignore[arg-type]
            max_retries=0,
        )

    assert exc_info.value.reason == "pydantic_validation_failed"


def test_query_planning_does_not_fill_empty_queries() -> None:
    client = FakeClient(outputs=[{"queries": []}])

    with pytest.raises(ReviewWorkflowFailed) as exc_info:
        plan_queries_with_deepseek(
            "是否需要数据出境安全评估？",
            ReviewFacts(cross_border_transfer=True),
            "材料",
            client=client,  # type: ignore[arg-type]
            max_retries=0,
        )

    assert exc_info.value.failed_node == "query_planning"


def test_query_planning_assigns_internal_query_ids_after_validation() -> None:
    client = FakeClient(
        outputs=[
            {
                "queries": [
                    {
                        "query_type": "legal_issue",
                        "text": "数据出境安全评估 申报条件",
                    },
                    {
                        "query_type": "material_fact",
                        "text": "手机号 新加坡 数据出境",
                    },
                ]
            }
        ]
    )

    queries = plan_queries_with_deepseek(
        "是否需要数据出境安全评估？",
        ReviewFacts(cross_border_transfer=True),
        "材料",
        client=client,  # type: ignore[arg-type]
        max_retries=0,
    )

    assert [query.query_id for query in queries] == ["q_1", "q_2"]
    assert [query.query_type for query in queries] == ["legal_issue", "material_fact"]


def test_evidence_check_with_deepseek_returns_second_retrieval_plan() -> None:
    client = FakeClient(
        outputs=[
            {
                "status": "needs_second_retrieval",
                "issues": [
                    {
                        "issue_type": "no_primary_legal_basis",
                        "description": "缺少主要法律依据",
                    }
                ],
                "triggered_reasons": ["no_primary_legal_basis"],
                "second_retrieval_triggered": False,
                "second_retrieval_plan": {
                    "expanded_queries": [
                        {
                            "query_type": "legal_issue",
                            "text": "数据出境安全评估 申报条件",
                        }
                    ],
                    "increased_top_k": 20,
                    "stronger_boost": True,
                    "reason": "补充主要法律依据",
                },
            }
        ]
    )

    check = run_self_check_with_deepseek(
        [_hit()],
        ReviewFacts(cross_border_transfer=True),
        {},
        client=client,  # type: ignore[arg-type]
        max_retries=0,
    )

    assert check.status == "needs_second_retrieval"
    assert check.second_retrieval_plan is not None
    assert check.second_retrieval_plan.expanded_queries[0].query_id == "q_1"


def test_result_generation_with_deepseek_uses_program_citation_groups() -> None:
    client = FakeClient(
        outputs=[
            {
                "risk_level": "medium",
                "conclusion": "该场景涉及数据出境，需要进一步确认申报条件。",
                "trigger_reasons": ["cross_border_transfer"],
                "missing_information": ["data_volume_threshold"],
                "recommended_actions": ["确认出境数据规模"],
                "risk_boundaries": ["本结论基于当前证据。"],
            }
        ]
    )

    result = build_review_result_with_deepseek(
        review_result_id="result_1",
        review_case_id="review_1",
        trace_id="trace_1",
        facts=ReviewFacts(cross_border_transfer=True),
        self_check=EvidenceSelfCheck(status="sufficient"),
        evidence_hits=[_hit()],
        client=client,  # type: ignore[arg-type]
        max_retries=0,
    )

    assert result.risk_level == "medium"
    assert result.conclusion.startswith("该场景涉及数据出境")
    assert result.applicable_evidence
    assert result.citations[0].chunk_id == "c1"
