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

from pydantic import Field

from law_agent.config import require_llm_config
from law_agent.data.schemas import Chunk
from law_agent.data.schemas import StrictModel
from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient
from law_agent.review.citations import group_citations
from law_agent.review.llm import ReviewWorkflowFailed, StructuredLLMNode
from law_agent.review.schemas import (
    Citation,
    CitationGroup,
    EvidenceSelfCheck,
    GroundedClaim,
    ReviewFacts,
    ReviewResult,
    RetrievalHit,
    RetrievalQuery,
    RiskLevel,
    SourceEvidencePacket,
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
    claims: list[GroundedClaim] = Field(min_length=1)
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
# Claim grounding
# ---------------------------------------------------------------------------

def _split_claim_sentences(text: str) -> list[str]:
    """Split a conclusion into displayable claim sentences."""

    sentences: list[str] = []
    current: list[str] = []
    for char in text.strip():
        current.append(char)
        if char in "。！？!?":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return sentences or ([text.strip()] if text.strip() else [])


def build_rule_grounded_claims(
    conclusion: str,
    evidence_hits: list[RetrievalHit],
) -> list[GroundedClaim]:
    """Ground rule-built conclusion sentences to the current evidence ids."""

    supporting_ids: list[str] = []
    seen: set[str] = set()
    for hit in evidence_hits:
        if hit.chunk_id in seen:
            continue
        supporting_ids.append(hit.chunk_id)
        seen.add(hit.chunk_id)
        if len(supporting_ids) >= 3:
            break

    return [
        GroundedClaim(text=sentence, supporting_chunk_ids=supporting_ids)
        for sentence in _split_claim_sentences(conclusion)
    ]


def validate_grounded_claims(
    claims: list[GroundedClaim],
    evidence_hits: list[RetrievalHit],
) -> list[GroundedClaim]:
    """Ensure every claim support id points at a current evidence chunk."""

    allowed_ids = {hit.chunk_id for hit in evidence_hits}
    invalid_ids = sorted(
        {
            chunk_id
            for claim in claims
            for chunk_id in claim.supporting_chunk_ids
            if chunk_id not in allowed_ids
        }
    )
    empty_claims = [claim.text for claim in claims if not claim.supporting_chunk_ids]
    if invalid_ids or empty_claims:
        details = {
            "invalid_supporting_chunk_ids": invalid_ids,
            "empty_claims": empty_claims,
            "allowed_chunk_ids": sorted(allowed_ids),
        }
        raise ValueError(f"claim grounding validation failed: {details}")
    return claims


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
    claims = build_rule_grounded_claims(conclusion, evidence_hits)

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
        claims=claims,
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
    source_evidence_packets: list[SourceEvidencePacket] | None = None,
) -> list[ChatMessage]:
    """Build a DeepSeek JSON prompt for structured review result generation."""

    json_example = {
        "risk_level": "medium",
        "conclusion": "该场景可能涉及个人信息跨境提供，但仍需补充数据规模和同意情况。",
        "claims": [
            {
                "text": "该场景可能涉及个人信息跨境提供。",
                "supporting_chunk_ids": ["chunk_id_from_evidence_packets"],
            },
            {
                "text": "仍需补充数据规模和同意情况。",
                "supporting_chunk_ids": ["another_chunk_id_from_evidence_packets"],
            },
        ],
        "trigger_reasons": ["cross_border_transfer", "missing_information"],
        "missing_information": ["legal_basis_or_consent", "data_volume_threshold"],
        "recommended_actions": ["确认是否取得单独同意", "确认出境数据规模"],
        "risk_boundaries": ["本结论基于当前材料和已召回证据，不构成正式法律意见"],
    }
    evidence_packets = [
        {
            "source_id": packet.source_id,
            "title": packet.title,
            "representative_chunk": _llm_evidence_hit(packet.representative_chunk),
            "supporting_chunks": [
                _llm_evidence_hit(hit) for hit in packet.supporting_chunks[:2]
            ],
            "neighbor_chunks": [
                _llm_evidence_hit(hit) for hit in packet.neighbor_chunks[:2]
            ],
        }
        for packet in (source_evidence_packets or [])
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
        "evidence_packets": evidence_packets,
        "corpus_scope": {
            "jurisdiction": "中国大陆数据合规和个人信息保护语料",
            "includes": [
                "个人信息保护法、数据安全法、网络安全法、网络数据安全管理条例",
                "数据出境安全评估、个人信息出境标准合同、个人信息保护认证",
                "国家网信部门政策问答、TC260 标准、自贸区地方数据出境清单、汽车/金融等行业材料",
            ],
            "excludes": [
                "EU AI Act",
                "CCPA/CPRA",
                "其他外国法或非数据合规领域问题",
            ],
        },
        "json_example": json_example,
        "instructions": [
            "基于审查事实和 evidence_packets 生成结构化审查结果。",
            "必须结合 question、material_excerpt、retrieval_queries 和 evidence_self_check 判断结论边界。",
            "只能基于 corpus_scope 内的中国数据合规语料和 evidence_packets 作答；如果 question 明确询问 corpus_scope.excludes 中的法域或制度，risk_level 必须为 insufficient_evidence。",
            "不要过度谨慎：如果材料已有可审查事实且 evidence 支持相关规则，即使缺少数据规模、同意状态、备案细节等信息，也要给出 high、medium 或 low 的有边界判断。",
            "缺失事实优先写入 missing_information、recommended_actions 和 risk_boundaries；不要仅因存在 missing_information 就输出 insufficient_evidence。",
            "如果材料没有说明关键事实（数据类型、处理目的、是否出境、接收方、地区/行业等），不要把 question 中的假设当作事实；只有在无法形成任何有用边界判断时才输出 insufficient_evidence。",
            "当 evidence_self_check.status 为 sufficient，且材料至少包含一个实质法律维度（如数据类型、处理目的、跨境安排、地区、行业、个人信息/敏感信息），通常不应输出 insufficient_evidence。",
            "必须输出合法 json object，字段必须与 json_example 完全一致。",
            "risk_level 只能是 high、medium、low、insufficient_evidence。",
            "claims 必须逐句覆盖 conclusion 中的关键判断；每个 claim.text 是一个可单独展示的结论句。",
            "每个 claims[].supporting_chunk_ids 必须只使用 evidence_packets 中真实存在的 chunk_id，且不能为空。",
            "evidence_self_check.status=sufficient 表示证据可用于当前语料范围内的判断；若事实有缺口但仍可形成边界判断，不要拒答。",
            "insufficient_evidence 只适用于：证据自检 insufficient、材料几乎没有可审查事实、问题超出 corpus_scope、或证据与问题/材料明显不匹配。",
            "不得编造未出现在证据中的法律来源。",
            "优先依据 representative_chunk；supporting_chunks 用于补充同一来源内更精确的条款；neighbor_chunks 只用于理解上下文。",
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


def _llm_evidence_hit(hit: RetrievalHit) -> dict[str, object]:
    return {
        "chunk_id": hit.chunk_id,
        "source_id": hit.source_id,
        "title": hit.title,
        "text": hit.text[:1200],
        "citation_role": hit.citation_role,
        "can_cite_clause": hit.can_cite_clause,
        "source_url": hit.source_url,
        "score": hit.score,
        "rank": hit.rank,
        "matched_query_type": hit.matched_query_type,
    }


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
    source_evidence_packets: list[SourceEvidencePacket] | None = None,
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
    try:
        draft = node.run(
            build_result_generation_messages(
                facts=facts,
                self_check=self_check,
                evidence_hits=evidence_hits,
                question=question,
                material_text=material_text,
                retrieval_queries=retrieval_queries,
                second_retrieval=second_retrieval,
                source_evidence_packets=source_evidence_packets,
            )
        )
        claims = validate_grounded_claims(draft.claims, evidence_hits)
    except ValueError as exc:
        raise ReviewWorkflowFailed(
            failed_node="result_generation",
            reason="claim_grounding_validation_failed",
            message=str(exc),
            attempts=1,
            trace_id=trace_id,
        ) from exc

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
        claims=claims,
        citations=all_citations,
        applicable_evidence=citation_groups,
    )
