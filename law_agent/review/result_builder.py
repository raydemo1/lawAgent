"""Rule-based structured review result builder.

Issue 8: Generate a governed ``ReviewResult`` from review facts and final
evidence. The rule builder determines risk level, conclusion, trigger
reasons, missing information, recommended actions, risk boundaries, and
citation groups — all without an LLM.

Risk level logic:
- ``insufficient_evidence``: evidence self-check is insufficient, or no
  primary legal basis and no fixable issues
- ``high``: sensitive personal info + cross-border + no consent, or
  cross-border + data volume threshold met
- ``medium``: cross-border transfer detected with some evidence
- ``low``: no cross-border, no sensitive data, evidence sufficient
"""

from __future__ import annotations

import json

from law_agent.config import require_llm_config
from law_agent.data.schemas import Chunk
from law_agent.data.schemas import StrictModel
from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient
from law_agent.review.citations import group_citations
from law_agent.review.llm import StructuredLLMNode
from law_agent.review.schemas import (
    Citation,
    CitationGroup,
    EvidenceSelfCheck,
    ReviewFacts,
    ReviewResult,
    RetrievalHit,
    RetrievalQuery,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# High-risk trigger detection
# ---------------------------------------------------------------------------

_HIGH_RISK_SENSITIVE_TERMS: tuple[str, ...] = (
    "人脸", "指纹", "生物识别", "身份证号", "医疗", "病历",
)


class LLMReviewResultDraft(StrictModel):
    """Required-field schema for LLM structured review generation."""

    risk_level: RiskLevel
    conclusion: str
    trigger_reasons: list[str]
    missing_information: list[str]
    recommended_actions: list[str]
    risk_boundaries: list[str]


def _has_high_risk_triggers(facts: ReviewFacts) -> bool:
    """Check if high-risk conditions are present.

    Note: ``legal_basis_or_consent`` being None means "not mentioned in
    material", not "definitely absent". We only treat it as high-risk when
    combined with sensitive info + cross-border, since that combination
    warrants caution regardless.
    """

    # Sensitive personal info + cross-border: high risk regardless of consent
    # (if consent is missing from material, it's a gap that needs attention)
    if facts.sensitive_personal_info and facts.cross_border_transfer:
        return True

    # Explicit high-risk data types + cross-border
    for data_type in facts.data_types:
        if any(term in data_type for term in _HIGH_RISK_SENSITIVE_TERMS):
            if facts.cross_border_transfer:
                return True

    return False


# ---------------------------------------------------------------------------
# Risk level determination
# ---------------------------------------------------------------------------

def _has_no_substantive_facts(facts: ReviewFacts) -> bool:
    """Check if facts have no substantive legal dimensions at all.

    When the material is extremely vague (e.g. "我们处理一些数据"), the
    system should abstain even if generic legal chunks are retrieved —
    there's no meaningful legal question to answer.

    Note: LLM fact extraction may return the string "null" instead of
    actual None for empty fields, so we filter those out too.
    """

    _NULLISH = ("", "null", "None", "无", "未知")

    def _is_truthy(val: str | None) -> bool:
        return bool(val) and val not in _NULLISH

    has_cross_border = bool(facts.cross_border_transfer)
    has_sensitive = _is_truthy(facts.sensitive_personal_info)
    has_industry = _is_truthy(facts.industry)
    has_region = _is_truthy(facts.region)
    # Filter out generic terms like "数据" that carry no legal specificity
    specific_data_types = [
        dt for dt in facts.data_types
        if dt not in ("数据", "信息", "个人信息", "") + _NULLISH
    ]
    has_specific_data = len(specific_data_types) > 0
    has_processing_purpose = _is_truthy(facts.processing_purpose)

    return not any([
        has_cross_border, has_sensitive, has_industry, has_region,
        has_specific_data, has_processing_purpose,
    ])


def determine_risk_level(
    facts: ReviewFacts,
    self_check: EvidenceSelfCheck,
    has_legal_basis_evidence: bool,
) -> str:
    """Determine risk level from facts, self-check status, and evidence."""

    # Insufficient evidence: abstain
    if self_check.status == "insufficient":
        return "insufficient_evidence"
    if not has_legal_basis_evidence and self_check.status != "sufficient":
        return "insufficient_evidence"

    # No substantive facts: abstain even if evidence is technically present.
    # Generic legal chunks don't help when there's no real legal question.
    if _has_no_substantive_facts(facts):
        return "insufficient_evidence"

    # High risk triggers
    if _has_high_risk_triggers(facts):
        return "high"

    # Cross-border transfer: medium risk
    if facts.cross_border_transfer:
        return "medium"

    # Sensitive personal info without cross-border: medium
    if facts.sensitive_personal_info:
        return "medium"

    # Default: low risk
    return "low"


# ---------------------------------------------------------------------------
# Conclusion generation
# ---------------------------------------------------------------------------

def build_conclusion(
    facts: ReviewFacts,
    risk_level: str,
    self_check: EvidenceSelfCheck,
) -> str:
    """Build a rule-based conclusion string."""

    if risk_level == "insufficient_evidence":
        return (
            "证据不足，无法做出明确判断。"
            "建议补充关键事实信息后重新审查。"
        )

    parts: list[str] = []

    if facts.cross_border_transfer:
        parts.append("该场景涉及数据出境")
        if facts.overseas_recipient:
            parts.append(f"（境外接收方：{facts.overseas_recipient}）")
        parts.append("，")
        if risk_level == "high":
            parts.append("存在高风险合规问题，需立即采取整改措施。")
        elif risk_level == "medium":
            parts.append("可能需要申报数据出境安全评估。")
        else:
            parts.append("但风险较低。")
    elif facts.sensitive_personal_info:
        parts.append("该场景涉及敏感个人信息处理，需遵守单独同意等特殊保护要求。")
    else:
        parts.append("该场景的合规风险较低。")

    # Missing information
    critical_missing = [
        f for f in facts.missing_information
        if f in ("legal_basis_or_consent", "overseas_recipient", "data_volume_threshold")
    ]
    if critical_missing:
        parts.append(f" 注意：关键信息缺失（{'、'.join(critical_missing)}），影响风险判断的准确性。")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Trigger reasons
# ---------------------------------------------------------------------------

def build_trigger_reasons(facts: ReviewFacts, risk_level: str) -> list[str]:
    """Build list of triggered risk reasons."""

    reasons: list[str] = []

    if facts.cross_border_transfer:
        reasons.append("cross_border_transfer")
    if facts.sensitive_personal_info:
        reasons.append("sensitive_personal_info")
    if facts.overseas_recipient:
        reasons.append("overseas_recipient_identified")
    if risk_level == "high":
        reasons.append("high_risk_triggers")
    if facts.missing_information:
        reasons.append("missing_information")

    return reasons


# ---------------------------------------------------------------------------
# Recommended actions
# ---------------------------------------------------------------------------

def build_recommended_actions(
    facts: ReviewFacts,
    risk_level: str,
    self_check: EvidenceSelfCheck,
) -> list[str]:
    """Build recommended actions based on facts and risk level."""

    actions: list[str] = []

    if risk_level == "insufficient_evidence":
        actions.append("补充关键事实信息后重新审查")
        for missing in facts.missing_information:
            if missing == "legal_basis_or_consent":
                actions.append("确认是否已获得用户单独同意")
            elif missing == "overseas_recipient":
                actions.append("明确境外接收方信息")
            elif missing == "data_volume_threshold":
                actions.append("确认处理个人信息的数据量规模")
        return actions

    if facts.cross_border_transfer:
        if risk_level in ("high", "medium"):
            actions.append("评估是否需要申报数据出境安全评估")
        if not facts.legal_basis_or_consent:
            actions.append("获取用户单独同意并留存告知记录")
        if facts.overseas_recipient:
            actions.append(f"与境外接收方（{facts.overseas_recipient}）签订数据处理协议")

    if facts.sensitive_personal_info:
        actions.append("对敏感个人信息实施单独同意和加密等保护措施")

    if self_check.second_retrieval_triggered:
        actions.append("已触发二次检索补充证据，请关注证据完整性")

    return actions


# ---------------------------------------------------------------------------
# Risk boundaries
# ---------------------------------------------------------------------------

def build_risk_boundaries(facts: ReviewFacts, risk_level: str) -> list[str]:
    """Build risk boundary statements."""

    boundaries: list[str] = []

    if facts.cross_border_transfer:
        boundaries.append("本结论基于当前提供的数据出境场景，如出境方式或接收方变更需重新评估")

    if facts.missing_information:
        boundaries.append(
            f"以下信息缺失可能影响判断准确性：{'、'.join(facts.missing_information)}"
        )

    if risk_level == "insufficient_evidence":
        boundaries.append("当前证据不足以做出确定性判断，结论仅供参考")
    else:
        boundaries.append("本结论基于当前检索到的法律法规和标准，不构成正式法律意见")

    return boundaries


# ---------------------------------------------------------------------------
# Full result builder
# ---------------------------------------------------------------------------

def build_review_result(
    *,
    review_result_id: str,
    review_case_id: str,
    trace_id: str,
    facts: ReviewFacts,
    self_check: EvidenceSelfCheck,
    evidence_hits: list[RetrievalHit],
    chunks_by_id: dict[str, Chunk] | None = None,
) -> ReviewResult:
    """Build a complete governed ReviewResult from facts and evidence.

    This is the rule-based builder. An optional LLM adapter can be added
    later with the same signature, but the rule builder remains the test
    fallback.
    """

    if chunks_by_id is None:
        chunks_by_id = {}

    # Group and validate citations
    citation_groups, violations = group_citations(evidence_hits, facts, chunks_by_id)

    # Check if we have legal basis evidence
    has_legal_basis = any(
        g.usage == "legal_basis" and len(g.citations) > 0 for g in citation_groups
    )

    # Determine risk level
    risk_level = determine_risk_level(facts, self_check, has_legal_basis)

    # Build all components
    conclusion = build_conclusion(facts, risk_level, self_check)
    trigger_reasons = build_trigger_reasons(facts, risk_level)
    recommended_actions = build_recommended_actions(facts, risk_level, self_check)
    risk_boundaries = build_risk_boundaries(facts, risk_level)

    # Flatten citations from groups
    all_citations: list[Citation] = []
    for group in citation_groups:
        all_citations.extend(group.citations)

    return ReviewResult(
        review_result_id=review_result_id,
        review_case_id=review_case_id,
        trace_id=trace_id,
        risk_level=risk_level,
        conclusion=conclusion,
        review_facts=facts,
        trigger_reasons=trigger_reasons,
        missing_information=facts.missing_information,
        recommended_actions=recommended_actions,
        risk_boundaries=risk_boundaries,
        citations=all_citations,
        applicable_evidence=citation_groups,
    )


# ---------------------------------------------------------------------------
# DeepSeek structured result generation
# ---------------------------------------------------------------------------

def build_result_generation_messages(
    *,
    facts: ReviewFacts,
    self_check: EvidenceSelfCheck,
    evidence_hits: list[RetrievalHit],
    question: str | None = None,
    material_text: str | None = None,
    retrieval_queries: list[RetrievalQuery] | None = None,
    second_retrieval: dict[str, object] | None = None,
) -> list[ChatMessage]:
    """Build a DeepSeek JSON prompt for structured review result generation."""

    json_example = {
        "risk_level": "medium",
        "conclusion": "该场景可能涉及个人信息跨境提供，但仍需补充数据规模和同意情况。",
        "trigger_reasons": ["cross_border_transfer", "missing_information"],
        "missing_information": ["legal_basis_or_consent", "data_volume_threshold"],
        "recommended_actions": ["确认是否取得单独同意", "确认出境数据规模"],
        "risk_boundaries": ["本结论基于当前材料和已召回证据，不构成正式法律意见"],
    }
    evidence = [
        {
            "chunk_id": hit.chunk_id,
            "source_id": hit.source_id,
            "title": hit.title,
            "text": hit.text[:1200],
            "citation_role": hit.citation_role,
            "can_cite_clause": hit.can_cite_clause,
            "source_url": hit.source_url,
        }
        for hit in evidence_hits[:12]
    ]
    payload = {
        "question": question,
        "material_excerpt": (material_text or "")[:3000],
        "review_facts": facts.model_dump(),
        "evidence_self_check": self_check.model_dump(),
        "retrieval_queries": [
            query.model_dump() for query in (retrieval_queries or [])
        ],
        "second_retrieval": second_retrieval or {},
        "evidence": evidence,
        "json_example": json_example,
        "instructions": [
            "基于审查事实和证据生成结构化审查结果。",
            "必须结合 question、material_excerpt、retrieval_queries 和 evidence_self_check 判断结论边界。",
            "必须输出合法 json object，字段必须与 json_example 完全一致。",
            "risk_level 只能是 high、medium、low、insufficient_evidence。",
            "当 evidence_self_check.status 为 sufficient 时，不应输出 insufficient_evidence，"
            "除非材料完全没有实质性法律维度（如仅含「我们处理一些数据」等模糊描述）。",
            "insufficient_evidence 仅适用于证据自检判定为 insufficient "
            "或材料无实质法律维度的情形，不应因 missing_information 中的输入质量缺陷而弃答。",
            "不得编造未出现在证据中的法律来源。",
            "引用分组由程序处理，本节点不要输出 citations。",
            "不要输出解释、markdown 或自然语言。",
        ],
    }
    return [
        ChatMessage(
            role="system",
            content=(
                "你是企业数据合规审查结果生成助手。"
                "只输出 json，不输出解释、markdown 或自然语言。"
            ),
        ),
        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]


def build_review_result_with_deepseek(
    *,
    review_result_id: str,
    review_case_id: str,
    trace_id: str,
    facts: ReviewFacts,
    self_check: EvidenceSelfCheck,
    evidence_hits: list[RetrievalHit],
    chunks_by_id: dict[str, Chunk] | None = None,
    question: str | None = None,
    material_text: str | None = None,
    retrieval_queries: list[RetrievalQuery] | None = None,
    second_retrieval: dict[str, object] | None = None,
    client: OpenAICompatibleClient | None = None,
    max_retries: int | None = None,
) -> ReviewResult:
    """Build a governed ReviewResult using DeepSeek for result content."""

    if chunks_by_id is None:
        chunks_by_id = {}
    if client is None:
        client = OpenAICompatibleClient(require_llm_config())

    node = StructuredLLMNode(
        node_name="result_generation",
        output_model=LLMReviewResultDraft,
        client=client,
        max_retries=max_retries,
        trace_id=trace_id,
    )
    draft = node.run(
        build_result_generation_messages(
            facts=facts,
            self_check=self_check,
            evidence_hits=evidence_hits,
            question=question,
            material_text=material_text,
            retrieval_queries=retrieval_queries,
            second_retrieval=second_retrieval,
        )
    )

    # Guardrail: LLM may still abstain even when evidence is sufficient.
    # If self-check is sufficient and facts have substantive legal dimensions,
    # override false abstention to the rule-based risk level.
    if (
        self_check.status == "sufficient"
        and not _has_no_substantive_facts(facts)
        and draft.risk_level == "insufficient_evidence"
    ):
        has_legal_basis = any(
            hit.citation_role == "primary_legal_basis" for hit in evidence_hits
        )
        rule_risk = determine_risk_level(facts, self_check, has_legal_basis)
        draft = draft.model_copy(update={
            "risk_level": rule_risk,
            "conclusion": build_conclusion(facts, rule_risk, self_check),
        })

    citation_groups, _violations = group_citations(evidence_hits, facts, chunks_by_id)
    all_citations: list[Citation] = []
    for group in citation_groups:
        all_citations.extend(group.citations)

    return ReviewResult(
        review_result_id=review_result_id,
        review_case_id=review_case_id,
        trace_id=trace_id,
        risk_level=draft.risk_level,
        conclusion=draft.conclusion,
        review_facts=facts,
        trigger_reasons=draft.trigger_reasons,
        missing_information=draft.missing_information,
        recommended_actions=draft.recommended_actions,
        risk_boundaries=draft.risk_boundaries,
        citations=all_citations,
        applicable_evidence=citation_groups,
    )
