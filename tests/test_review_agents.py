from __future__ import annotations

from law_agent.llm.openai_compatible import ChatMessage
from law_agent.review.agents import (
    build_evidence_dossiers,
    build_issue_plan,
    run_evidence_critic,
    should_run_evidence_critic,
)
from law_agent.review.schemas import (
    CritiqueDecision,
    EvidenceSelfCheck,
    ReviewFacts,
    ReviewResult,
    RetrievalQuery,
)

from tests.test_review_result_builder import _hit


class FakeClient:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.calls: list[list[ChatMessage]] = []

    def chat_json(self, messages: list[ChatMessage], **kwargs) -> dict:
        self.calls.append(messages)
        return self.output


def test_issue_plan_groups_queries_into_bounded_review_issues() -> None:
    queries = [
        RetrievalQuery(query_id="q_1", query_type="legal_issue", text="出境评估条件"),
        RetrievalQuery(query_id="q_2", query_type="legal_issue", text="标准合同条件"),
        RetrievalQuery(query_id="q_3", query_type="region_condition", text="上海负面清单"),
    ]

    plan = build_issue_plan(queries)

    assert [issue.issue_id for issue in plan.issues] == ["issue_1", "issue_2"]
    assert plan.issues[0].query_ids == ["q_1", "q_2"]
    assert plan.issues[1].query_ids == ["q_3"]


def test_evidence_dossiers_map_hits_to_issue_query_types() -> None:
    queries = [
        RetrievalQuery(query_id="q_1", query_type="legal_issue", text="出境评估条件"),
        RetrievalQuery(query_id="q_2", query_type="region_condition", text="上海负面清单"),
    ]
    plan = build_issue_plan(queries)
    hits = [
        _hit().model_copy(update={"chunk_id": "legal", "matched_query_type": "legal_issue"}),
        _hit().model_copy(update={"chunk_id": "region", "matched_query_type": "region_condition"}),
    ]

    dossiers = build_evidence_dossiers(plan, hits)

    assert dossiers[0].evidence_chunk_ids == ["legal"]
    assert dossiers[1].evidence_chunk_ids == ["region"]
    assert all(not dossier.evidence_gap for dossier in dossiers)


def test_critic_only_runs_for_complex_or_risky_reviews() -> None:
    plan = build_issue_plan(
        [RetrievalQuery(query_id="q_1", query_type="legal_issue", text="一般问题")]
    )
    low_result = ReviewResult(
        review_result_id="r",
        review_case_id="c",
        trace_id="t",
        risk_level="low",
        conclusion="低风险",
        review_facts=ReviewFacts(),
    )

    assert not should_run_evidence_critic(
        low_result,
        EvidenceSelfCheck(status="sufficient"),
        plan,
    )
    assert should_run_evidence_critic(
        low_result.model_copy(update={"risk_level": "high"}),
        EvidenceSelfCheck(status="sufficient"),
        plan,
    )


def test_evidence_critic_returns_strict_revision_decision() -> None:
    client = FakeClient(
        {
            "decision": "revise",
            "unsupported_claims": ["缺少依据的结论"],
            "missing_issue_ids": ["issue_1"],
            "revision_instructions": ["删除无依据结论并覆盖 issue_1"],
            "reason": "关键问题未覆盖",
        }
    )
    plan = build_issue_plan(
        [RetrievalQuery(query_id="q_1", query_type="legal_issue", text="出境评估条件")]
    )
    result = ReviewResult(
        review_result_id="r",
        review_case_id="c",
        trace_id="t",
        risk_level="high",
        conclusion="需要申报。",
        review_facts=ReviewFacts(cross_border_transfer=True),
    )

    decision = run_evidence_critic(
        result=result,
        issue_plan=plan,
        dossiers=build_evidence_dossiers(plan, [_hit()]),
        evidence_hits=[_hit()],
        client=client,  # type: ignore[arg-type]
        max_retries=0,
    )

    assert decision == CritiqueDecision(
        decision="revise",
        unsupported_claims=["缺少依据的结论"],
        missing_issue_ids=["issue_1"],
        revision_instructions=["删除无依据结论并覆盖 issue_1"],
        reason="关键问题未覆盖",
    )
    assert "issue_1" in client.calls[0][-1].content
