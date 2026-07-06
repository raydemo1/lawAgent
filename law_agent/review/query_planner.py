"""Deterministic and LLM-assisted retrieval query planning.

Issue 4: Generate typed ``RetrievalQuery`` objects from the user question plus
extracted ``ReviewFacts``. Phase 2 retrieval should not be a raw user-query
search; the review facts bridge concrete business material with
metadata-aware legal evidence retrieval.

The default planner is rule-based and dependency-free so tests never need an
LLM. An LLM adapter function with the same callable signature is provided for
optional production use.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from law_agent.review.schemas import ReviewFacts, RetrievalQuery, RetrievalQueryType

QueryPlanner = Callable[[str, ReviewFacts, str | None], list[RetrievalQuery]]


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
    facts: ReviewFacts, ids: _QueryIdGenerator
) -> RetrievalQuery | None:
    if not facts.region:
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="region_condition",
        text=f"{facts.region} 数据出境 负面清单 管理清单 自贸区",
    )


def _build_industry_query(
    facts: ReviewFacts, ids: _QueryIdGenerator
) -> RetrievalQuery | None:
    if not facts.industry:
        return None
    return RetrievalQuery(
        query_id=ids.next_id(),
        query_type="industry_condition",
        text=f"{facts.industry} 数据出境 安全管理 合规要求",
    )


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
            template = missing_key
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

    legal_query = _build_legal_issue_query(question, ids)
    queries.append(legal_query)

    material_query = _build_material_fact_query(facts, ids)
    if material_query is not None:
        queries.append(material_query)

    region_query = _build_region_query(facts, ids)
    if region_query is not None:
        queries.append(region_query)

    industry_query = _build_industry_query(facts, ids)
    if industry_query is not None:
        queries.append(industry_query)

    queries.extend(_build_missing_information_queries(facts, ids))

    return queries


# ---------------------------------------------------------------------------
# Optional LLM-based planner (same callable signature)
# ---------------------------------------------------------------------------

_VALID_QUERY_TYPES: tuple[RetrievalQueryType, ...] = (
    "legal_issue",
    "material_fact",
    "region_condition",
    "industry_condition",
    "missing_information",
)


def plan_queries_with_llm(
    question: str,
    facts: ReviewFacts,
    material_text: str | None = None,
) -> list[RetrievalQuery]:
    """Plan retrieval queries using an OpenAI-compatible LLM.

    Requires ``OPENAI_COMPATIBLE_API_KEY`` to be configured. Falls back to
    rule-based queries for any query type the LLM omits.
    """

    from law_agent.config import require_llm_config
    from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient

    config = require_llm_config()
    client = OpenAICompatibleClient(config)

    prompt = {
        "question": question,
        "review_facts": facts.model_dump(),
        "material_text": (material_text or "")[:6000],
        "query_types": list(_VALID_QUERY_TYPES),
        "instructions": (
            "基于用户问题和审查事实，生成多个类型化检索查询。"
            "每个查询包含 query_type 和 text。只输出 JSON object，"
            "格式为 {\"queries\": [{\"query_type\": \"...\", \"text\": \"...\"}]}。"
        ),
    }

    data = client.chat_json(
        [
            ChatMessage(
                role="system",
                content=(
                    "你是法律合规检索查询规划助手。"
                    "生成覆盖法律问题、材料事实、地区条件、行业条件和缺失信息的检索查询。"
                    "必须输出 JSON object。"
                ),
            ),
            ChatMessage(role="user", content=json.dumps(prompt, ensure_ascii=False)),
        ]
    )

    raw_queries = data.get("queries", [])
    if not isinstance(raw_queries, list):
        raw_queries = []

    ids = _QueryIdGenerator()
    llm_queries: list[RetrievalQuery] = []
    seen_types: set[str] = set()

    for raw in raw_queries:
        if not isinstance(raw, dict):
            continue
        query_type = raw.get("query_type")
        text = raw.get("text")
        if not isinstance(query_type, str) or query_type not in _VALID_QUERY_TYPES:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        if query_type in seen_types:
            continue
        seen_types.add(query_type)
        llm_queries.append(
            RetrievalQuery(
                query_id=ids.next_id(),
                query_type=query_type,
                text=text.strip(),
            )
        )

    if not llm_queries:
        return plan_queries(question, facts, material_text)

    return llm_queries
