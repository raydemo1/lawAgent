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
import re
from typing import Literal

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
    """Required-field schema for LLM structured review generation (plain path)."""

    risk_level: RiskLevel
    conclusion: str
    claims: list[GroundedClaim] = Field(min_length=1)
    trigger_reasons: list[str]
    missing_information: list[str]
    recommended_actions: list[str]
    risk_boundaries: list[str]


class MarkdownReviewDraft(StrictModel):
    """Simplified schema for markdown (frontend) path.

    Unlike ``LLMReviewResultDraft`` which splits the report into
    conclusion/recommended_actions/risk_boundaries/missing_information,
    this schema collapses everything into a single ``report`` field.
    The LLM writes one coherent markdown report with scene-adaptive
    sections, instead of filling separate fields that the backend then
    stitches back together. ``claims`` stays separate so evidence
    grounding is preserved for the right-panel citation cards.
    """

    risk_level: RiskLevel
    report: str
    claims: list[GroundedClaim] = Field(min_length=1)
    trigger_reasons: list[str]


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

#: Mandatory disclaimer appended to the end of every conclusion string.
CONCLUSION_DISCLAIMER = "\n\n本结论基于当前材料和已召回证据，**不构成正式法律意见**。"


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
        ) + CONCLUSION_DISCLAIMER

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

    return "".join(parts) + CONCLUSION_DISCLAIMER


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
    """Ensure every claim support id points at a citable evidence chunk.

    Two-level validation:

    1. The chunk_id must exist in the current evidence set (anti-hallucination).
    2. The referenced chunk must be ``can_cite_clause=True`` — i.e. a
       concrete legal article from a primary source. Guide/template/Q&A
       and other non-citable chunks are silently dropped from claim
       references; they remain in the evidence panel as auxiliary evidence
       but cannot be inlined as clause citations in the conclusion.

    Claims that only restate material facts may legitimately have no legal
    chunk support, so they are omitted from the grounded-claim rail. The
    result fails only when every emitted claim loses support; fabricating a
    legal citation is never an acceptable fallback.
    """

    allowed_ids = {hit.chunk_id for hit in evidence_hits}
    citable_ids = {hit.chunk_id for hit in evidence_hits if hit.can_cite_clause}
    if not citable_ids:
        return []
    cleaned: list[GroundedClaim] = []
    empty_claims: list[str] = []
    for claim in claims:
        valid_ids = [
            cid for cid in claim.supporting_chunk_ids
            if cid in allowed_ids and cid in citable_ids
        ]
        if not valid_ids:
            empty_claims.append(claim.text)
            continue
        cleaned.append(
            claim.model_copy(update={"supporting_chunk_ids": valid_ids})
        )
    if empty_claims and not cleaned:
        details = {
            "empty_claims": empty_claims,
            "allowed_chunk_ids": sorted(allowed_ids),
            "citable_chunk_ids": sorted(citable_ids),
        }
        raise ValueError(f"claim grounding validation failed: {details}")
    return cleaned


# ---------------------------------------------------------------------------
# Markdown sanitization for LLM-generated text fields
# ---------------------------------------------------------------------------

# Drop fenced code block fences (``` or ```lang) — LLM occasionally wraps examples.
_CODE_FENCE_RE = re.compile(r"```[^\n]*\n?")
# Downgrade level-1/2 headings to ### so they don't clash with the page's h1/h2.
_HEADING_DOWNGRADE_RE = re.compile(r"^(#{1,2})(?!#)\s", re.MULTILINE)
# Detect **bold** spans. Non-greedy, disallow nested * to keep it simple.
_BOLD_SPAN_RE = re.compile(r"\*\*([^\*\n]{1,120}?)\*\*")


def _sanitize_markdown_text(text: str) -> str:
    """Gently clean LLM-generated markdown so the frontend renders safely.

    - Downgrade ``#`` / ``##`` headings to ``###`` (page owns h1/h2).
    - Strip fenced code block fences.
    - Repair unpaired ``**`` by dropping the last occurrence.
    - Un-bold spans longer than 50 chars (LLM sometimes bolds a whole
      sentence against the prompt; the frontend bold style is intended
      for short legal-term emphasis only).

    Plain text (rule builder output) passes through unchanged because it
    contains no markdown markers.
    """
    if not text:
        return text

    text = _CODE_FENCE_RE.sub("", text)
    text = _HEADING_DOWNGRADE_RE.sub(r"### ", text)

    # Repair unpaired ** : if count is odd, remove the last **.
    bold_count = text.count("**")
    if bold_count % 2 == 1:
        idx = text.rfind("**")
        text = text[:idx] + text[idx + 2:]

    # Un-bold overly long spans (whole-sentence bolding).
    def _unbold_long(match: re.Match[str]) -> str:
        inner = match.group(1)
        if len(inner) > 50:
            return inner
        return match.group(0)

    text = _BOLD_SPAN_RE.sub(_unbold_long, text)
    return text


# ---------------------------------------------------------------------------
# Inline citation markers: inject ①②③ into the report text so the
# frontend can render clickable superscripts that link each claim to its
# supporting legal article shown in the citation cards below.
# ---------------------------------------------------------------------------

_CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# Match legal article references like "《个人信息保护法》第三十九条" or
# standalone "第三十九条" / "第七条" in the report text.
_ARTICLE_REF_RE = re.compile(
    r"(?:《[^》]+》)?\s*第[一二三四五六七八九十百零〇\d]+条"
)


def _extract_cite_phrase(claim_text: str) -> str | None:
    """Extract the most specific legal-article phrase from a claim.

    Preference order:
    1. Full ``《法律名》第X条`` form (most precise).
    2. Bare ``第X条`` form.
    3. ``None`` if no article reference found (caller will fall back to
       appending the marker at the end of the nearest sentence).
    """

    if not claim_text:
        return None
    full_match = re.search(r"《[^》]+》\s*第[一二三四五六七八九十百零〇\d]+条", claim_text)
    if full_match:
        return full_match.group(0)
    bare_match = re.search(r"第[一二三四五六七八九十百零〇\d]+条", claim_text)
    if bare_match:
        return bare_match.group(0)
    return None


def inject_citation_markers(
    report: str,
    claims: list[GroundedClaim],
    evidence_hits: list[RetrievalHit] | None = None,
) -> str:
    """Inject ①②③ markers into the report text for each claim.

    For each claim (in order), find the first occurrence of its cite phrase
    in the report and insert a ``<sup>`` marker right after it.

    The cite phrase is resolved with this priority:
    1. The ``citation_label`` of the claim's first supporting chunk (most
       precise — e.g. "《个人信息保护法》第三十九条").
    2. The ``article_no`` of the supporting chunk (e.g. "第三十九条").
    3. A ``《法律名》第X条`` phrase extracted from the claim text itself.

    If no phrase can be matched in the report, the marker is collected and
    appended in a trailing "引用说明" section so every claim still has a
    visible number that maps to a citation card.
    """

    if not report or not claims:
        return report

    # Build chunk_id -> RetrievalHit lookup for citation_label/article_no.
    chunks_by_id: dict[str, RetrievalHit] = {}
    if evidence_hits:
        for hit in evidence_hits:
            chunks_by_id[hit.chunk_id] = hit

    # Track which report positions have already been marked to avoid
    # stacking multiple markers on the same phrase.
    marked_positions: set[int] = set()
    pending_markers: list[str] = []

    text = report
    for index, claim in enumerate(claims[:len(_CIRCLED_NUMBERS)]):
        marker = _CIRCLED_NUMBERS[index]
        # Resolve the cite phrase: prefer chunk citation_label, then
        # article_no, then fall back to extracting from claim text.
        phrase: str | None = None
        if claim.supporting_chunk_ids and chunks_by_id:
            primary_chunk = chunks_by_id.get(claim.supporting_chunk_ids[0])
            if primary_chunk:
                if primary_chunk.citation_label:
                    phrase = primary_chunk.citation_label
                elif primary_chunk.article_no:
                    phrase = primary_chunk.article_no
        if not phrase:
            phrase = _extract_cite_phrase(claim.text)

        inserted = False
        if phrase:
            # citation_label is stored as "法律名 第X条" (no 《》, space
            # separated), but the report typically writes "《法律名》**第X条**"
            # with book-title marks and bold. Build a tolerant regex:
            #   - law name may be wrapped in 《》
            #   - ** may appear anywhere around the article number
            #   - whitespace allowed between name and number
            # Split the phrase into (law_name, article_no) if possible.
            article_match = re.search(r"第[一二三四五六七八九十百零〇\d]+条", phrase)
            if article_match:
                article_part = article_match.group(0)
                law_name = phrase[: article_match.start()].strip().rstrip("》").lstrip("《").strip()
                if law_name:
                    # Match optional 《》, law name, optional 》, optional **,
                    # then article number, then optional **.
                    pattern = re.compile(
                        re.escape(article_part)
                    )
                    # First try the full precise form with law name.
                    full_pattern = re.compile(
                        r"《?" + re.escape(law_name) + r"》?\s*\**\s*" + re.escape(article_part) + r"\**"
                    )
                    patterns_to_try = [full_pattern, pattern]
                else:
                    patterns_to_try = [re.compile(re.escape(article_part) + r"\**")]
            else:
                patterns_to_try = [re.compile(re.escape(phrase))]

            search_start = 0
            for pat in patterns_to_try:
                if inserted:
                    break
                while True:
                    match = pat.search(text, search_start)
                    if match is None:
                        break
                    insert_at = match.end()
                    # Skip any trailing ** so the marker lands after the bold close.
                    while insert_at < len(text) and text[insert_at] == "*":
                        insert_at += 1
                    if insert_at not in marked_positions:
                        sup = f'<sup class="cite-marker" id="cite-marker-{index}" data-claim-index="{index}">{marker}</sup>'
                        text = text[:insert_at] + sup + text[insert_at:]
                        marked_positions.add(insert_at)
                        inserted = True
                        break
                    search_start = match.end() + 1
        if not inserted:
            pending_markers.append(marker)

    if pending_markers:
        # Append unplaced markers in a trailing references section so every
        # claim still has a visible number that maps to a citation card.
        labels = " ".join(pending_markers)
        text = text.rstrip() + f"\n\n引用说明：{labels}\n"

    return text


def _sanitize_draft_markdown(draft: LLMReviewResultDraft) -> LLMReviewResultDraft:
    """Apply markdown sanitization to all text fields of an LLM result draft.

    Kept for potential future use on the plain path; the markdown path now
    uses ``MarkdownReviewDraft`` and sanitizes only the ``report`` field
    inline (see ``build_review_result_with_deepseek``).
    """

    return draft.model_copy(
        update={
            "conclusion": _sanitize_markdown_text(draft.conclusion),
            "claims": [
                claim.model_copy(
                    update={"text": _sanitize_markdown_text(claim.text)}
                )
                for claim in draft.claims
            ],
            "recommended_actions": [
                _sanitize_markdown_text(a) for a in draft.recommended_actions
            ],
            "risk_boundaries": [
                _sanitize_markdown_text(b) for b in draft.risk_boundaries
            ],
            "missing_information": [
                _sanitize_markdown_text(m) for m in draft.missing_information
            ],
        }
    )


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
    output_format: Literal["plain", "markdown"] = "plain",
) -> list[ChatMessage]:
    """Build a DeepSeek JSON prompt for structured review result generation.

    ``output_format="plain"`` (default, used by eval) emits plain-text
    conclusion/claims — keeps eval metrics stable and lets strict_tool mode
    validate the schema cleanly. ``output_format="markdown"`` (used by the
    frontend API) emits markdown-formatted conclusion (### headings, **bold**
    legal terms, lists) and inline-bold claims for richer display. Both
    formats share the same evidence/facts/corpus_scope payload and the same
    risk_level / abstention logic, so retrieval and risk judgements stay
    consistent across the two paths.
    """

    if output_format == "markdown":
        # markdown path uses MarkdownReviewDraft schema: a single `report`
        # field carries the whole review as natural-language markdown,
        # instead of splitting into conclusion/actions/boundaries/missing.
        # The LLM writes one coherent report whose sections adapt to the
        # scene (cross-border / sensitive info / insufficient evidence…).
        json_example = {
            "risk_level": "medium",
            "report": (
                "### 风险定性\n"
                "该场景涉及**个人信息跨境提供**，存在**中等合规风险**。\n\n"
                "### 关键法律依据\n"
                "依据《个人信息保护法》**第三十八条**，个人信息出境需通过安全评估、"
                "标准合同或认证等法定路径；《数据出境安全评估办法》规定，处理100万人"
                "以上个人信息的数据处理者应当申报安全评估。材料显示拟向境外接收方传输"
                "员工个人信息，但未说明已采取的出境路径。\n\n"
                "### 合规义务与缺口\n"
                "- 需确认是否取得用户**单独同意**；\n"
                "- 需确认出境数据规模是否触发**数据出境安全评估**申报门槛；\n"
                "- 材料未提供境外接收方信息，影响风险完整性判断。\n\n"
                "### 建议措施\n"
                "1. 取得用户**单独同意**并留存告知记录；\n"
                "2. 与境外接收方签订**数据处理协议**；\n"
                "3. 评估是否需要申报**数据出境安全评估**。\n\n"
                "### 风险边界\n"
                "本结论基于当前材料和已召回证据，**不构成正式法律意见**；"
                "如出境方式或接收方变更需重新评估。"
            ),
            "claims": [
                {
                    "text": "该场景涉及**个人信息跨境提供**，存在中等合规风险。",
                    "supporting_chunk_ids": ["chunk_id_from_evidence_packets"],
                },
                {
                    "text": "依据《个人信息保护法》**第三十八条**，出境需通过法定路径。",
                    "supporting_chunk_ids": ["another_chunk_id_from_evidence_packets"],
                },
                {
                    "text": "需确认是否取得**单独同意**及数据出境规模。",
                    "supporting_chunk_ids": ["chunk_id_from_evidence_packets"],
                },
            ],
            "trigger_reasons": ["cross_border_transfer", "missing_information"],
        }
        # markdown path: 3 replaced instructions adapt the shared list to
        # the report-based schema. Extra instructions teach report format
        # and chunk diversification. Plain path stays byte-identical to HEAD.
        format_instruction_replacements = [
            "必须输出合法 json object，字段必须与 json_example 完全一致；report 字段内使用 markdown 符号（**、###、-、数字列表）。",
            "claims 必须逐句覆盖 report 中的关键判断；每个 claim.text 是一个可单独展示的结论句，关键法律术语可用 **加粗**（只加粗短语，不加粗整句）。",
            "只输出 json object，不要输出 json 以外的任何解释文字；report 内可自由使用 markdown 让内容更易读。",
        ]
        extra_markdown_instructions = [
            "report 用 markdown 输出完整审查报告，根据场景自适应选择小节，通常包含「风险定性」「关键法律依据」「合规义务与缺口」「建议措施」「风险边界」等 ### 小节；段落间空行分隔，关键法律依据短语用 **加粗**，合规义务用 - 列表，建议措施用数字列表；不要用 # 或 ## 标题，不要用 ``` 代码块，长度建议 250-500 字。",
            "语言表达要自然清晰，让业务人员能快速看懂合规风险、义务缺口和下一步动作；不要堆砌法条，要把规则落到当前材料的实际场景上。",
            "claims 的 supporting_chunk_ids 只能从 payload.citable_chunk_ids 中选取（这些是 can_cite_clause=true 的法条 chunk）；不要使用 citable_chunk_ids 以外的任何 chunk_id，evidence_packets 中 can_cite_clause=false 的指南/范本/Q&A/地方清单只能作为背景理解，不能出现在 supporting_chunk_ids 里。",
            "claims 优先从 evidence_packets[].supporting_chunks 中选取条款最精确的 chunk，不要反复引用同一个 representative_chunk；不同 claim 尽量引用不同 chunk 以分散证据来源。",
            "每个 claim.text 应明确包含所依据的法律条款编号（如「《个人信息保护法》第三十九条」「数据出境安全评估办法 第七条」），便于生成内联引用标记。",
        ]
        system_content = (
            "你是企业数据合规审查结果生成助手。"
            "只输出一个合法 json object，不要输出 json 以外的任何解释文字；"
            "report 字段用 markdown 输出清晰易懂的审查报告。"
        )
        # markdown path has no missing_information/actions/boundaries fields
        # (they live inside report), so instruction 5 must be adapted.
        missing_facts_instruction = (
            "缺失的事实和合规缺口直接写进 report 的「合规义务与缺口」「建议措施」"
            "等小节；不要因为存在信息缺口就输出 insufficient_evidence。"
        )
    else:
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
        # plain path: keep HEAD instructions exactly as-is (eval stability).
        format_instruction_replacements = [
            "必须输出合法 json object，字段必须与 json_example 完全一致。",
            "claims 必须逐句覆盖 conclusion 中的关键判断；每个 claim.text 是一个可单独展示的结论句。",
            "不要输出解释、markdown 或自然语言。",
        ]
        extra_markdown_instructions = []
        system_content = (
            "你是企业数据合规审查结果生成助手。"
            "只输出 json，不输出解释、markdown 或自然语言。"
        )
        # plain path keeps the HEAD instruction 5 verbatim.
        missing_facts_instruction = (
            "缺失事实优先写入 missing_information、recommended_actions 和 risk_boundaries；"
            "不要仅因存在 missing_information 就输出 insufficient_evidence。"
        )
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
    # Flat whitelist of every chunk_id the LLM is allowed to cite. LLM
    # occasionally hallucinates ids that follow the source_id:N pattern
    # (e.g. ``:0004`` when only 0000/0003/0005 exist) by pattern-completion
    # on the nested evidence_packets structure. Surfacing the full list at
    # the top of the payload gives the model a single source of truth to
    # copy from. This field is purely additive context — no instruction
    # text is changed, so eval metrics stay stable.
    allowed_chunk_ids = sorted({hit.chunk_id for hit in evidence_hits})
    # Citable-only whitelist: claims[].supporting_chunk_ids must come from
    # this list. Pre-filtering here means the LLM does not have to inspect
    # each chunk's can_cite_clause flag — it just copies ids from this list.
    # Non-citable chunks (guides/templates/Q&A/local lists) remain in
    # evidence_packets as background context but cannot be cited.
    citable_chunk_ids = sorted(
        {hit.chunk_id for hit in evidence_hits if hit.can_cite_clause}
    )
    payload = {
        "question": question,
        "material_excerpt": (material_text or "")[:3000],
        "allowed_chunk_ids": allowed_chunk_ids,
        "citable_chunk_ids": citable_chunk_ids,
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
            missing_facts_instruction,
            "如果材料没有说明关键事实（数据类型、处理目的、是否出境、接收方、地区/行业等），不要把 question 中的假设当作事实；只有在无法形成任何有用边界判断时才输出 insufficient_evidence。",
            "当 evidence_self_check.status 为 sufficient，且材料至少包含一个实质法律维度（如数据类型、处理目的、跨境安排、地区、行业、个人信息/敏感信息），通常不应输出 insufficient_evidence。",
            format_instruction_replacements[0],
            "risk_level 只能是 high、medium、low、insufficient_evidence。",
            format_instruction_replacements[1],
            *extra_markdown_instructions,
            "每个 claims[].supporting_chunk_ids 必须只使用 evidence_packets 中真实存在的 chunk_id，且不能为空。",
            "evidence_self_check.status=sufficient 表示证据可用于当前语料范围内的判断；若事实有缺口但仍可形成边界判断，不要拒答。",
            "insufficient_evidence 只适用于：证据自检 insufficient、材料几乎没有可审查事实、问题超出 corpus_scope、或证据与问题/材料明显不匹配。",
            "不得编造未出现在证据中的法律来源。",
            "优先依据 representative_chunk；supporting_chunks 用于补充同一来源内更精确的条款；neighbor_chunks 只用于理解上下文。",
            "引用分组由程序处理，本节点不要输出 citations。",
            format_instruction_replacements[2],
        ],
    }
    return [
        ChatMessage(
            role="system",
            content=system_content,
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
        "article_no": hit.article_no,
        "citation_label": hit.citation_label,
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
    output_format: Literal["plain", "markdown"] = "plain",
) -> ReviewResult:
    """Build a governed ReviewResult using DeepSeek for result content.

    ``output_format="plain"`` (default, eval path) emits plain-text fields
    and runs under the client's default structured_output_mode (usually
    strict_tool) for tight schema validation. ``output_format="markdown"``
    (frontend path) emits markdown-formatted conclusion/claims and forces
    json_object mode, since strict_tool schema constraints clash with
    free-form markdown; normalization is still guaranteed by Pydantic
    strict validation + retry. Both paths share the same evidence/facts
    payload and risk logic, so retrieval and risk judgements stay
    consistent — only the textual rendering differs.
    """

    if chunks_by_id is None:
        chunks_by_id = {}
    if client is None:
        client = OpenAICompatibleClient(require_llm_config())

    # markdown format forces json_object: strict_tool schema validation
    # rejects free-form markdown inside string fields. plain format falls
    # back to the client's configured mode (usually strict_tool) so eval
    # gets the tightest schema guarantee.
    node_mode = "json_object" if output_format == "markdown" else None
    # markdown path uses a simplified schema (MarkdownReviewDraft) with a
    # single `report` field; plain path uses the split-field schema.
    output_model = MarkdownReviewDraft if output_format == "markdown" else LLMReviewResultDraft

    node = StructuredLLMNode(
        node_name="result_generation",
        output_model=output_model,
        client=client,
        max_retries=max_retries,
        trace_id=trace_id,
        structured_output_mode=node_mode,
    )
    try:
        def validate_draft_grounding(draft_to_validate):
            validated_claims = validate_grounded_claims(
                draft_to_validate.claims,
                evidence_hits,
            )
            return draft_to_validate.model_copy(update={"claims": validated_claims})

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
                output_format=output_format,
            ),
            post_validate=validate_draft_grounding,
            post_validation_reason="claim_grounding_validation_failed",
        )
        # markdown path: sanitize the report text and use it as conclusion;
        # actions/boundaries/missing_info are empty (content lives inside report).
        # plain path: pass through unchanged so eval sees exactly what the
        # LLM emitted.
        if output_format == "markdown":
            md_draft: MarkdownReviewDraft = draft  # type: ignore[assignment]
            md_draft = md_draft.model_copy(
                update={"report": _sanitize_markdown_text(md_draft.report)}
            )
            claims = validate_grounded_claims(md_draft.claims, evidence_hits)
            # Inject ①②③ inline citation markers into the report text so
            # the frontend can render clickable superscripts that link to
            # the citation cards below. Done after validation so markers
            # only cover citable legal articles. Uses chunk citation_label
            # for matching so the marker lands on the exact legal article
            # reference in the report text.
            conclusion = inject_citation_markers(
                md_draft.report, claims, evidence_hits
            )
            trigger_reasons = md_draft.trigger_reasons
            risk_level = md_draft.risk_level
            missing_information: list[str] = []
            recommended_actions: list[str] = []
            risk_boundaries: list[str] = []
        else:
            plain_draft: LLMReviewResultDraft = draft  # type: ignore[assignment]
            conclusion = plain_draft.conclusion
            claims = validate_grounded_claims(plain_draft.claims, evidence_hits)
            trigger_reasons = plain_draft.trigger_reasons
            risk_level = plain_draft.risk_level
            missing_information = plain_draft.missing_information
            recommended_actions = plain_draft.recommended_actions
            risk_boundaries = plain_draft.risk_boundaries
    except ValueError as exc:
        raise ReviewWorkflowFailed(
            failed_node="result_generation",
            reason="claim_grounding_validation_failed",
            message=str(exc),
            attempts=1,
            trace_id=trace_id,
        ) from exc

    # Append mandatory disclaimer to every LLM-generated conclusion
    conclusion = conclusion.rstrip() + CONCLUSION_DISCLAIMER

    citation_groups, _violations = group_citations(evidence_hits, facts, chunks_by_id)
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
        missing_information=missing_information,
        recommended_actions=recommended_actions,
        risk_boundaries=risk_boundaries,
        claims=claims,
        citations=all_citations,
        applicable_evidence=citation_groups,
    )
