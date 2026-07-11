from __future__ import annotations

from law_agent.llm.openai_compatible import ChatMessage
from law_agent.review.agents import (
    build_evidence_dossiers,
    build_issue_plan,
    run_case_analyst,
    run_evidence_critic,
    select_issue_aware_hits,
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


def test_case_analyst_adds_issue_specific_queries_without_replacing_frozen_inputs() -> None:
    initial = [
        RetrievalQuery(query_id="q_1", query_type="legal_issue", text="数据出境条件")
    ]
    client = FakeClient(
        {
            "issues": [
                {
                    "issue_id": "draft",
                    "question": "是否达到安全评估申报门槛？",
                    "query_ids": [],
                    "query_types": ["legal_issue"],
                    "research_queries": ["数据出境安全评估 申报门槛 条件"],
                    "required_evidence_roles": ["primary_legal_basis"],
                    "priority": "high",
                }
            ]
        }
    )

    analysis = run_case_analyst(
        question="是否需要申报？",
        material_text="向境外提供个人信息。",
        facts=ReviewFacts(cross_border_transfer=True),
        initial_queries=initial,
        client=client,  # type: ignore[arg-type]
        max_retries=0,
    )

    assert analysis.queries[0] == initial[0]
    assert analysis.queries[1].query_id == "q_2"
    assert analysis.issue_plan.issues[0].query_ids == ["q_2"]
    assert analysis.issue_plan.issues[0].research_queries == [
        "数据出境安全评估 申报门槛 条件"
    ]


def test_issue_aware_selection_reserves_evidence_for_each_issue() -> None:
    plan = build_issue_plan(
        [
            RetrievalQuery(query_id="q_1", query_type="legal_issue", text="核心条件"),
            RetrievalQuery(query_id="q_2", query_type="region_condition", text="地区条件"),
        ]
    )
    legal = _hit().model_copy(
        update={"chunk_id": "legal", "source_id": "law", "score": 0.8}
    )
    region = _hit().model_copy(
        update={"chunk_id": "region", "source_id": "region", "score": 0.7}
    )
    global_best = _hit().model_copy(
        update={"chunk_id": "global", "source_id": "guide", "score": 0.9}
    )

    selected = select_issue_aware_hits(
        plan,
        {"issue_1": [legal], "issue_2": [region]},
        [global_best],
        top_k=3,
    )

    assert {hit.chunk_id for hit in selected} == {"legal", "region", "global"}
    assert [hit.rank for hit in selected] == [1, 2, 3]


def test_dossiers_can_use_issue_specific_candidate_pools() -> None:
    plan = build_issue_plan(
        [RetrievalQuery(query_id="q_1", query_type="legal_issue", text="核心条件")]
    )
    precise = _hit().model_copy(update={"chunk_id": "precise", "source_id": "law"})

    dossiers = build_evidence_dossiers(
        plan,
        [],
        issue_hits_by_issue={"issue_1": [precise]},
    )

    assert dossiers[0].evidence_chunk_ids == ["precise"]


def test_critic_only_runs_for_risk_or_evidence_signals() -> None:
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

    four_issue_plan = build_issue_plan(
        [
            RetrievalQuery(query_id="q_1", query_type="legal_issue", text="核心"),
            RetrievalQuery(query_id="q_2", query_type="region_condition", text="地区"),
            RetrievalQuery(query_id="q_3", query_type="industry_condition", text="行业"),
            RetrievalQuery(query_id="q_4", query_type="missing_information", text="缺失"),
        ]
    )
    assert not should_run_evidence_critic(
        low_result,
        EvidenceSelfCheck(status="sufficient"),
        four_issue_plan,
    )


def test_evidence_critic_returns_strict_revision_decision() -> None:
    client = FakeClient(
        {
            "decision": "revise",
            "unsupported_claims": ["缺少依据的结论"],
            "missing_issue_ids": ["issue_1"],
            "revision_instructions": ["删除无依据结论并覆盖 issue_1"],
            "targeted_retrieval_requests": [
                {
                    "issue_id": "issue_1",
                    "query": "数据出境安全评估 申报门槛 条文",
                    "query_type": "legal_issue",
                    "reason": "缺少直接法条",
                }
            ],
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
        targeted_retrieval_requests=[
            {
                "issue_id": "issue_1",
                "query": "数据出境安全评估 申报门槛 条文",
                "query_type": "legal_issue",
                "reason": "缺少直接法条",
            }
        ],
        reason="关键问题未覆盖",
    )
    assert "issue_1" in client.calls[0][-1].content
