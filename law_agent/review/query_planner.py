"""Retrieval query planning.

Issue 4: Generate typed ``RetrievalQuery`` objects from the user question plus
extracted ``ReviewFacts``. Phase 2 retrieval should not be a raw user-query
search; the review facts bridge concrete business material with
metadata-aware legal evidence retrieval.

The deterministic planner remains available as an explicit baseline. The
DeepSeek planner is the online LLM path and does not fall back to rules.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import Field, field_validator

from law_agent.config import require_llm_config
from law_agent.data.schemas import StrictModel
from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient
from law_agent.review.llm import StructuredLLMNode
from law_agent.review.schemas import ReviewFacts, RetrievalQuery, RetrievalQueryType

QueryPlanner = Callable[[str, ReviewFacts, str | None], list[RetrievalQuery]]

_REGION_INTENT_TERMS: tuple[str, ...] = (
    "自贸区",
    "自由贸易试验区",
    "负面清单",
    "管理清单",
    "地方政策",
    "区域政策",
    "数据出境",
    "跨境",
    "出境",
)

_INDUSTRY_INTENT_TERMS: tuple[str, ...] = (
    "行业",
    "安全要求",
    "安全管理",
    "合规要求",
    "特殊要求",
    "数据处理者",
    "数据处理",
    "数据安全",
    "数据出境",
    "测绘",
    "地理信息",
)

_NON_LOCAL_REGION_VALUES: frozenset[str] = frozenset(
    {"CN", "中国", "全国", "境内", "全国范围"}
)

_STANDARD_CONTRACT_TERMS: tuple[str, ...] = (
    "标准合同",
    "合同路径",
    "合同方式",
)

_STANDARD_CONTRACT_FILING_TERMS: tuple[str, ...] = (
    "备案",
    "备案材料",
    "备案包",
    "哪类文件",
    "准备哪些文件",
    "准备哪类文件",
)

_STANDARD_CONTRACT_IMPLICIT_CONTEXT_TERMS: tuple[str, ...] = (
    "员工",
    "HR",
    "人力资源",
    "通讯录",
)

_ASSESSMENT_INTENT_TERMS: tuple[str, ...] = (
    "安全评估",
    "申报",
    "网信办",
    "网信部门",
    "必须走",
    "一定要走",
    "什么情况下",
    "申报条件",
    "阈值",
    "规模",
    "万人",
    "百万",
)


class _QueryIdGenerator:
    """Deterministic counter-based query ID generator."""

    def __init__(self) -> None:
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"q_{self._counter}"


# ---------------------------------------------------------------------------
# Deterministic rules planner
# ---------------------------------------------------------------------------

def _build_legal_issue_query(
    question: str, ids: _QueryIdGenerator
) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="legal_issue",
        text=question,
    )


def _build_material_fact_query(
    facts: ReviewFacts, ids: _QueryIdGenerator
) -> RetrievalQuery | None:
    terms: list[str] = []
    if facts.cross_border_transfer:
        terms.append("数据出境")
    terms.extend(facts.data_types)
    if facts.overseas_recipient:
        terms.append(facts.overseas_recipient)
    if facts.sensitive_personal_info:
        terms.append("敏感个人信息")
    if not terms:
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="material_fact",
        text=" ".join(terms),
    )


def _build_region_query(
    facts: ReviewFacts,
    ids: _QueryIdGenerator,
    context_text: str,
) -> RetrievalQuery | None:
    if not facts.region or facts.region in _NON_LOCAL_REGION_VALUES:
        return None
    if not _contains_any(context_text, _REGION_INTENT_TERMS):
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="region_condition",
        text=f"{facts.region} 数据出境 负面清单 管理清单 自贸区",
    )


def _build_industry_query(
    facts: ReviewFacts,
    ids: _QueryIdGenerator,
    context_text: str,
) -> RetrievalQuery | None:
    if not facts.industry:
        return None
    if not _contains_any(context_text, _INDUSTRY_INTENT_TERMS):
        return None
    focus = "数据出境" if facts.cross_border_transfer else "数据安全"
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="industry_condition",
        text=f"{facts.industry} {focus} 安全管理 合规要求",
    )


def _build_standard_contract_query(
    question: str,
    facts: ReviewFacts,
    material_text: str | None,
    ids: _QueryIdGenerator,
) -> RetrievalQuery | None:
    combined = f"{question}\n{material_text or ''}"
    explicit_contract = _contains_any(combined, _STANDARD_CONTRACT_TERMS)
    filing_for_cross_border_personal_info = (
        bool(facts.cross_border_transfer)
        and _contains_any(combined, _STANDARD_CONTRACT_FILING_TERMS)
        and _contains_any(combined, _STANDARD_CONTRACT_IMPLICIT_CONTEXT_TERMS)
    )
    if not (explicit_contract or filing_for_cross_border_personal_info):
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="legal_issue",
        text="个人信息出境 标准合同 办法 备案指南 备案材料",
    )


def _build_assessment_query(
    facts: ReviewFacts,
    ids: _QueryIdGenerator,
    context_text: str,
) -> RetrievalQuery | None:
    if not facts.cross_border_transfer:
        return None
    if not _contains_any(context_text, _ASSESSMENT_INTENT_TERMS):
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="legal_issue",
        text="数据出境安全评估 申报条件 重要数据 个人信息 100万人 10万人",
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _context_text(question: str, material_text: str | None) -> str:
    return f"{question}\n{material_text or ''}"


_MISSING_QUERY_TEMPLATES: dict[str, str] = {
    "overseas_recipient": "数据出境 境外接收方 信息 保护要求",
    "legal_basis_or_consent": "个人信息处理 法律基础 同意 告知 单独同意",
    "data_volume_threshold": "数据出境安全评估 申报条件 阈值 数量标准",
    "processing_purpose": "个人信息处理 处理目的 合法正当必要",
    "data_types": "个人信息 数据分类 数据类型 识别",
}


def _build_missing_information_queries(
    facts: ReviewFacts, ids: _QueryIdGenerator
) -> list[RetrievalQuery]:
    queries: list[RetrievalQuery] = []
    for missing_key in facts.missing_information:
        template = _MISSING_QUERY_TEMPLATES.get(missing_key)
        if template is None:
            # Skip unknown keys — using a raw field name as a query text
            # (e.g. "cross_border_transfer") pollutes retrieval with noise.
            continue
        queries.append(
            RetrievalQuery(
                query_id=ids.next_id(),
                query_type="missing_information",
                text=template,
            )
        )
    return queries


def plan_queries(
    question: str,
    facts: ReviewFacts,
    material_text: str | None = None,
) -> list[RetrievalQuery]:
    """Plan typed retrieval queries from a question and extracted facts.

    The ``material_text`` parameter is accepted for interface compatibility with
    the LLM adapter but is not used by the rules planner.
    """

    ids = _QueryIdGenerator()
    queries: list[RetrievalQuery] = []
    context_text = _context_text(question, material_text)

    legal_query = _build_legal_issue_query(question, ids)
    queries.append(legal_query)

    material_query = _build_material_fact_query(facts, ids)
    if material_query is not None:
        queries.append(material_query)

    region_query = _build_region_query(facts, ids, context_text)
    if region_query is not None:
        queries.append(region_query)

    industry_query = _build_industry_query(facts, ids, context_text)
    if industry_query is not None:
        queries.append(industry_query)

    assessment_query = _build_assessment_query(facts, ids, context_text)
    if assessment_query is not None:
        queries.append(assessment_query)

    standard_contract_query = _build_standard_contract_query(
        question, facts, material_text, ids
    )
    if standard_contract_query is not None:
        queries.append(standard_contract_query)

    queries.extend(_build_missing_information_queries(facts, ids))

    return queries


def plan_high_confidence_queries(
    question: str,
    facts: ReviewFacts,
    material_text: str | None = None,
) -> list[RetrievalQuery]:
    """Plan only deterministic supplemental queries with explicit triggers.

    This is intentionally narrower than ``plan_queries`` and is safe to merge
    after LLM query planning. It avoids broad missing-information queries, which
    are useful in the rules baseline but too noisy as online LLM fallback.
    """

    ids = _QueryIdGenerator()
    context_text = _context_text(question, material_text)
    queries: list[RetrievalQuery] = []

    region_query = _build_region_query(facts, ids, context_text)
    if region_query is not None:
        queries.append(region_query)

    industry_query = _build_industry_query(facts, ids, context_text)
    if industry_query is not None:
        queries.append(industry_query)

    assessment_query = _build_assessment_query(facts, ids, context_text)
    if assessment_query is not None:
        queries.append(assessment_query)

    standard_contract_query = _build_standard_contract_query(
        question, facts, material_text, ids
    )
    if standard_contract_query is not None:
        queries.append(standard_contract_query)

    return queries


def merge_queries_with_rule_fallback(
    primary: list[RetrievalQuery],
    fallback: list[RetrievalQuery],
) -> list[RetrievalQuery]:
    """Append deterministic fallback queries that the primary planner missed."""

    ids = _QueryIdGenerator()
    merged: list[RetrievalQuery] = []
    seen: set[tuple[str, str]] = set()
    for query in [*primary, *fallback]:
        text = query.text.strip()
        if not text:
            continue
        key = (query.query_type, " ".join(text.split()))
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            RetrievalQuery(
                query_id=ids.next_id(),
                query_type=query.query_type,
                text=text,
            )
        )
    return merged


# ---------------------------------------------------------------------------
# DeepSeek LLM planner
# ---------------------------------------------------------------------------

_VALID_QUERY_TYPES: tuple[RetrievalQueryType, ...] = (
    "legal_issue",
    "material_fact",
    "region_condition",
    "industry_condition",
    "missing_information",
)


class LLMRetrievalQuery(StrictModel):
    query_type: RetrievalQueryType
    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class LLMQueryPlan(StrictModel):
    queries: list[LLMRetrievalQuery] = Field(min_length=1)


def build_query_planning_messages(
    question: str,
    facts: ReviewFacts,
    material_text: str | None = None,
) -> list[ChatMessage]:
    """Build a DeepSeek JSON prompt for query planning."""

    json_example = {
        "queries": [
            {
                "query_type": "legal_issue",
                "text": "数据出境安全评估 申报条件",
            },
            {
                "query_type": "material_fact",
                "text": "手机号 定位信息 新加坡 数据出境",
            },
            {
                "query_type": "missing_information",
                "text": "数据出境安全评估 数据规模 阈值 单独同意",
            },
        ]
    }

    user_payload = {
        "question": question,
        "review_facts": facts.model_dump(),
        "material_text": (material_text or "")[:6000],
        "allowed_query_types": list(_VALID_QUERY_TYPES),
        "json_example": json_example,
        "instructions": [
            "基于用户问题和审查事实生成多个类型化检索查询。",
            "必须输出合法 json object，字段必须与 json_example 完全一致。",
            "query_type 只能使用 allowed_query_types 中的值。",
            "不要输出 query_id，query_id 由程序生成。",
        ],
    }

    return [
        ChatMessage(
            role="system",
            content=(
                "你是法律合规检索 query planning 助手。"
                "只输出 json，不输出解释、markdown 或自然语言。"
            ),
        ),
        ChatMessage(role="user", content=json.dumps(user_payload, ensure_ascii=False)),
    ]


def plan_queries_with_deepseek(
    question: str,
    facts: ReviewFacts,
    material_text: str | None = None,
    *,
    client: OpenAICompatibleClient | None = None,
    max_retries: int | None = None,
    trace_id: str | None = None,
) -> list[RetrievalQuery]:
    """Plan retrieval queries using DeepSeek with strict validation.

    This is the online LLM path. It does not fill omitted query types from
    rules and does not parse natural-language responses.
    """

    if client is None:
        client = OpenAICompatibleClient(require_llm_config())
    node = StructuredLLMNode(
        node_name="query_planning",
        output_model=LLMQueryPlan,
        client=client,
        max_retries=max_retries,
        trace_id=trace_id,
    )
    plan = node.run(build_query_planning_messages(question, facts, material_text))

    ids = _QueryIdGenerator()
    queries: list[RetrievalQuery] = []
    for query in plan.queries:
        queries.append(
            RetrievalQuery(
                query_id=ids.next_id(),
                query_type=query.query_type,
                text=query.text.strip(),
            )
        )

    return queries


plan_queries_with_llm = plan_queries_with_deepseek
