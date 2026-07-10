"""Bounded multi-agent roles layered over the deterministic review workflow."""

from __future__ import annotations

import json

from law_agent.config import require_llm_config
from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient
from law_agent.review.llm import StructuredLLMNode
from law_agent.review.schemas import (
    CritiqueDecision,
    EvidenceDossier,
    EvidenceSelfCheck,
    IssuePlan,
    ReviewIssue,
    ReviewResult,
    RetrievalHit,
    RetrievalQuery,
    RetrievalQueryType,
)

_ISSUE_GROUPS: tuple[tuple[str, tuple[RetrievalQueryType, ...], str], ...] = (
    ("核心法律问题", ("legal_issue", "material_fact"), "high"),
    ("地区适用条件", ("region_condition",), "medium"),
    ("行业适用条件", ("industry_condition",), "medium"),
    ("关键缺失信息", ("missing_information",), "medium"),
)


def build_issue_plan(queries: list[RetrievalQuery]) -> IssuePlan:
    """Group existing typed queries into at most five review issues."""

    issues: list[ReviewIssue] = []
    for label, query_types, priority in _ISSUE_GROUPS:
        grouped = [query for query in queries if query.query_type in query_types]
        if not grouped:
            continue
        issue_number = len(issues) + 1
        issues.append(
            ReviewIssue(
                issue_id=f"issue_{issue_number}",
                question=f"{label}：" + "；".join(query.text for query in grouped),
                query_ids=[query.query_id for query in grouped],
                query_types=list(dict.fromkeys(query.query_type for query in grouped)),
                priority=priority,
            )
        )
        if len(issues) == 5:
            break
    return IssuePlan(issues=issues)


def build_evidence_dossiers(
    issue_plan: IssuePlan,
    evidence_hits: list[RetrievalHit],
) -> list[EvidenceDossier]:
    """Assign retrieved evidence to issues using recorded query types."""

    dossiers: list[EvidenceDossier] = []
    for issue in issue_plan.issues:
        matched = [
            hit
            for hit in evidence_hits
            if hit.matched_query_type in set(issue.query_types)
        ]
        chunk_ids = list(dict.fromkeys(hit.chunk_id for hit in matched))
        source_ids = list(dict.fromkeys(hit.source_id for hit in matched))
        dossiers.append(
            EvidenceDossier(
                issue_id=issue.issue_id,
                evidence_chunk_ids=chunk_ids,
                source_ids=source_ids,
                evidence_gap=not chunk_ids,
            )
        )
    return dossiers


def should_run_evidence_critic(
    result: ReviewResult,
    self_check: EvidenceSelfCheck,
    issue_plan: IssuePlan,
) -> bool:
    """Limit Critic cost to risky, retried, insufficient, or complex cases."""

    return (
        result.risk_level == "high"
        or self_check.second_retrieval_triggered
        or self_check.status == "insufficient"
        or len(issue_plan.issues) >= 4
    )


def build_critic_messages(
    *,
    result: ReviewResult,
    issue_plan: IssuePlan,
    dossiers: list[EvidenceDossier],
    evidence_hits: list[RetrievalHit],
) -> list[ChatMessage]:
    payload = {
        "issues": [issue.model_dump() for issue in issue_plan.issues],
        "dossiers": [dossier.model_dump() for dossier in dossiers],
        "result": {
            "risk_level": result.risk_level,
            "conclusion": result.conclusion,
            "claims": [claim.model_dump() for claim in result.claims],
            "missing_information": result.missing_information,
            "risk_boundaries": result.risk_boundaries,
        },
        "evidence": [
            {
                "chunk_id": hit.chunk_id,
                "title": hit.title,
                "text": hit.text,
                "can_cite_clause": hit.can_cite_clause,
                "citation_role": hit.citation_role,
            }
            for hit in evidence_hits
        ],
    }
    example = {
        "decision": "approve",
        "unsupported_claims": [],
        "missing_issue_ids": [],
        "revision_instructions": [],
        "reason": "所有高优先级问题均有证据支持",
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是企业数据合规审查的 Evidence Critic。只检查结论是否超出证据、"
                "高优先级 issue 是否遗漏、风险等级是否与证据冲突。不要重新检索，"
                "不要要求文风修改。只有实质性证据问题才输出 revise。"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "请输出严格 JSON。revision_instructions 必须具体且最多三条；"
                "approve 时该数组必须为空。"
                f"\njson_example={json.dumps(example, ensure_ascii=False)}"
                f"\npayload={json.dumps(payload, ensure_ascii=False)}"
            ),
        ),
    ]


def run_evidence_critic(
    *,
    result: ReviewResult,
    issue_plan: IssuePlan,
    dossiers: list[EvidenceDossier],
    evidence_hits: list[RetrievalHit],
    client: OpenAICompatibleClient | None = None,
    max_retries: int | None = None,
) -> CritiqueDecision:
    if client is None:
        client = OpenAICompatibleClient(require_llm_config())
    node = StructuredLLMNode(
        node_name="evidence_critic",
        output_model=CritiqueDecision,
        client=client,
        max_retries=max_retries,
        trace_id=result.trace_id,
    )
    return node.run(
        build_critic_messages(
            result=result,
            issue_plan=issue_plan,
            dossiers=dossiers,
            evidence_hits=evidence_hits,
        )
    )
