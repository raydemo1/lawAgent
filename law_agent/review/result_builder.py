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

from law_agent.data.schemas import Chunk
from law_agent.review.citations import group_citations
from law_agent.review.schemas import (
    Citation,
    CitationGroup,
    EvidenceSelfCheck,
    ReviewFacts,
    ReviewResult,
    RetrievalHit,
)

# ---------------------------------------------------------------------------
# High-risk trigger detection
# ---------------------------------------------------------------------------

_HIGH_RISK_SENSITIVE_TERMS: tuple[str, ...] = (
    "人脸", "指纹", "生物识别", "身份证号", "医疗", "病历",
)


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
    """

    has_cross_border = bool(facts.cross_border_transfer)
    has_sensitive = bool(facts.sensitive_personal_info)
    has_industry = bool(facts.industry)
    has_region = bool(facts.region)
    # Filter out generic terms like "数据" that carry no legal specificity
    specific_data_types = [
        dt for dt in facts.data_types
        if dt not in ("数据", "信息", "个人信息", "")
    ]
    has_specific_data = len(specific_data_types) > 0
    has_processing_purpose = bool(facts.processing_purpose)

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
