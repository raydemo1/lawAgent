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
from typing import NamedTuple

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
    "地方清单",
    "地方规则",
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

_ASSESSMENT_STRONG_INTENT_TERMS: tuple[str, ...] = (
    "安全评估",
    "数据出境安全评估",
    "申报数据出境安全评估",
    "网信部门申报",
    "网信办申报",
)

_ASSESSMENT_WEAK_INTENT_TERMS: tuple[str, ...] = (
    "申报",
    "必须走",
    "一定要走",
    "什么情况下",
    "申报条件",
    "阈值",
    "规模",
    "万人",
    "百万",
)

_ASSESSMENT_ANCHOR_TERMS: tuple[str, ...] = (
    "评估",
    "网信办",
    "网信部门",
    "重要数据",
    "100万人",
    "10万人",
)


class _LegalQueryTemplate(NamedTuple):
    """Controlled legal terminology expansion template."""

    intent_terms: tuple[str, ...]
    query_text: str
    requires_cross_border: bool = False
    anchor_terms: tuple[str, ...] = ()


_LEGAL_QUERY_TEMPLATES: tuple[_LegalQueryTemplate, ...] = (
    _LegalQueryTemplate(
        intent_terms=_ASSESSMENT_STRONG_INTENT_TERMS,
        query_text="数据出境安全评估 申报条件 重要数据 个人信息 100万人 10万人",
        requires_cross_border=True,
    ),
    _LegalQueryTemplate(
        intent_terms=_ASSESSMENT_WEAK_INTENT_TERMS,
        query_text="数据出境安全评估 申报条件 重要数据 个人信息 100万人 10万人",
        requires_cross_border=True,
        anchor_terms=_ASSESSMENT_ANCHOR_TERMS,
    ),
    _LegalQueryTemplate(
        intent_terms=_STANDARD_CONTRACT_TERMS,
        query_text="个人信息出境 标准合同 办法 备案指南 备案材料",
        requires_cross_border=False,
    ),
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


def _build_template_queries(
    facts: ReviewFacts,
    ids: _QueryIdGenerator,
    context_text: str,
) -> list[RetrievalQuery]:
    queries: list[RetrievalQuery] = []
    seen_texts: set[str] = set()
    for template in _LEGAL_QUERY_TEMPLATES:
        if template.requires_cross_border and not facts.cross_border_transfer:
            continue
        if not _contains_any(context_text, template.intent_terms):
            continue
        if template.anchor_terms and not _contains_any(context_text, template.anchor_terms):
            continue
        if template.query_text in seen_texts:
            continue
        seen_texts.add(template.query_text)
        queries.append(
            RetrievalQuery(
                query_id=ids.next_id(),
                query_type="legal_issue",
                text=template.query_text,
            )
        )
    return queries


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

    queries.extend(_build_template_queries(facts, ids, context_text))

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

    queries.extend(_build_template_queries(facts, ids, context_text))

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

_CONTROLLED_LEGAL_PATHWAY_ANCHORS: list[dict[str, object]] = [
    {
        "pathway": "cross_border_foundation",
        "when_to_use": "用户询问数据出境基础规则、总体合规路径、豁免边界、不同路径关系，或地方/行业规则与全国规则的关系。",
        "query_type": "legal_issue",
        "query_terms": [
            "促进和规范数据跨境流动规定",
            "数据出境",
            "基础规则",
            "豁免情形",
            "适用范围",
        ],
    },
    {
        "pathway": "security_assessment",
        "when_to_use": "问题或事实涉及申报、网信部门、安全评估、重要数据、数量阈值或大规模个人信息。",
        "query_type": "legal_issue",
        "query_terms": [
            "数据出境安全评估办法",
            "数据出境安全评估申报指南",
            "申报条件",
            "重要数据",
            "个人信息数量阈值",
        ],
    },
    {
        "pathway": "post_assessment_obligations",
        "when_to_use": "问题或事实涉及已通过安全评估后的持续义务、重新申报、变更、监督检查或评估有效期。",
        "query_type": "legal_issue",
        "query_terms": [
            "数据出境安全评估办法",
            "数据出境安全评估",
            "重新申报",
            "变更",
            "后续义务",
            "监督管理",
        ],
    },
    {
        "pathway": "standard_contract",
        "when_to_use": "问题或事实涉及标准合同、备案、合同文本或境外接收方义务。",
        "query_type": "legal_issue",
        "query_terms": [
            "个人信息出境标准合同办法",
            "个人信息出境标准合同范本",
            "备案指南",
            "境外接收方义务",
        ],
    },
    {
        "pathway": "certification",
        "when_to_use": "问题或事实涉及个人信息保护认证、集团内部跨境共享、认证路径、粤港澳/大湾区跨境个人信息或认证路径下的责任。",
        "query_type": "legal_issue",
        "query_terms": [
            "个人信息出境个人信息保护认证办法",
            "个人信息保护认证实施规则",
            "个人信息跨境处理活动安全认证规范",
            "认证路径",
            "境外接收方责任",
        ],
    },
    {
        "pathway": "sensitive_personal_info",
        "when_to_use": "问题或事实涉及敏感个人信息、人脸识别、生物识别、儿童个人信息、精确定位、行踪轨迹或敏感个人信息处理要求。",
        "query_type": "legal_issue",
        "query_terms": [
            "个人信息保护法",
            "敏感个人信息",
            "生物识别",
            "儿童个人信息",
            "精确定位",
            "敏感个人信息处理安全要求",
            "敏感个人信息识别指南",
        ],
    },
    {
        "pathway": "remote_access_boundary",
        "when_to_use": "问题或事实涉及境外远程访问境内数据、VPN 查看境内数据库、没有批量下载但境外可访问，或询问是否属于数据出境边界。",
        "query_type": "legal_issue",
        "query_terms": [
            "数据出境安全评估办法",
            "数据出境安全评估办法答记者问",
            "促进和规范数据跨境流动规定",
            "远程访问",
            "境外访问",
            "数据出境",
        ],
    },
    {
        "pathway": "pathway_conflict",
        "when_to_use": "问题或事实同时涉及标准合同、安全评估门槛、认证或多条个人信息出境路径，询问哪条路径优先或如何选择。",
        "query_type": "legal_issue",
        "query_terms": [
            "数据出境安全评估办法",
            "个人信息出境标准合同办法",
            "促进和规范数据跨境流动规定答记者问",
            "安全评估",
            "标准合同",
            "适用条件",
            "路径优先",
        ],
    },
]

_CONTROLLED_REGION_FACETS: list[dict[str, object]] = [
    {
        "label": "上海自贸区/临港新片区",
        "region_code": "CN-SH",
        "aliases": ["上海", "上海自贸区", "临港新片区"],
        "query_terms": ["上海自贸区", "临港新片区", "数据出境", "负面清单"],
    },
    {
        "label": "天津自贸区",
        "region_code": "CN-TJ",
        "aliases": ["天津", "天津自贸区"],
        "query_terms": ["天津自贸区", "数据出境", "负面清单", "管理清单"],
    },
    {
        "label": "重庆自贸区",
        "region_code": "CN-CQ",
        "aliases": ["重庆", "重庆自贸区"],
        "query_terms": ["重庆自贸区", "数据出境", "负面清单", "车联网"],
    },
    {
        "label": "浙江自贸区",
        "region_code": "CN-ZJ",
        "aliases": ["浙江", "浙江自贸区"],
        "query_terms": ["浙江自贸区", "数据出境", "负面清单", "跨境电商"],
    },
    {
        "label": "海南自由贸易港",
        "region_code": "CN-HI",
        "aliases": ["海南", "海南自由贸易港"],
        "query_terms": ["海南自由贸易港", "数据出境", "负面清单"],
    },
    {
        "label": "北京自贸区/服务业扩大开放示范区",
        "region_code": "CN-BJ",
        "aliases": ["北京", "北京自贸区"],
        "query_terms": ["北京自贸区", "服务业扩大开放", "数据出境", "负面清单"],
    },
    {
        "label": "广东自贸区",
        "region_code": "CN-GD",
        "aliases": ["广东", "广东自贸区"],
        "query_terms": ["广东自贸区", "数据出境", "负面清单"],
    },
    {
        "label": "深圳",
        "region_code": "CN-GD-SZ",
        "aliases": ["深圳"],
        "query_terms": ["深圳", "数据条例", "数据出境"],
    },
    {
        "label": "福建自贸区",
        "region_code": "CN-FJ",
        "aliases": ["福建", "福建自贸区"],
        "query_terms": ["福建自贸区", "数据出境", "负面清单"],
    },
    {
        "label": "广西自贸区",
        "region_code": "CN-GX",
        "aliases": ["广西", "广西自贸区"],
        "query_terms": ["广西自贸区", "数据出境", "负面清单"],
    },
    {
        "label": "江苏自贸区",
        "region_code": "CN-JS",
        "aliases": ["江苏", "江苏自贸区"],
        "query_terms": ["江苏自贸区", "数据出境", "负面清单"],
    },
]

_CONTROLLED_INDUSTRY_FACETS: list[dict[str, object]] = [
    {
        "label": "智能网联汽车/车联网",
        "aliases": ["汽车", "智能网联汽车", "车联网", "车辆位置", "行驶轨迹", "道路环境"],
        "query_terms": [
            "汽车数据安全管理若干规定",
            "汽车数据出境安全指引",
            "智能网联汽车",
            "测绘地理信息",
            "数据出境",
        ],
    },
    {
        "label": "跨境电商",
        "aliases": ["跨境电商", "电子商务", "电商", "订单数据", "物流数据"],
        "query_terms": ["跨境电商", "订单数据", "物流数据", "数据出境"],
    },
    {
        "label": "金融信息服务",
        "aliases": ["金融", "金融信息服务"],
        "query_terms": ["金融信息服务", "数据分类分级", "重要数据"],
    },
]


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
        "allowed_query_types": list(_VALID_QUERY_TYPES),
        "controlled_legal_pathways": _CONTROLLED_LEGAL_PATHWAY_ANCHORS,
        "controlled_region_facets": _CONTROLLED_REGION_FACETS,
        "controlled_industry_facets": _CONTROLLED_INDUSTRY_FACETS,
        "json_example": json_example,
        "instructions": [
            "基于用户问题和审查事实生成多个类型化检索查询。",
            "所有查询都必须面向 corpus_scope 内的中国数据合规语料；不要把库外外国法问题改写成看似相关的中国法问题。",
            "如果问题明显超出 corpus_scope，仍输出最小查询用于验证语料缺口，但不要编造国内法替代查询。",
            "如果材料事实不足，生成 missing_information 查询以帮助确认缺口，而不是假设事实成立。",
            "legal_issue 查询优先从 controlled_legal_pathways 中选择相关 pathway，并用其 query_terms 作为文件名/制度锚点；可以加入用户问题或材料里的具体事实词，但不要发明该列表以外的外国法、非数据合规制度或文件名。",
            "不要因为 review_facts.cross_border_transfer 为 true 就机械选择 cross_border_foundation；如果问题已经明确落入 security_assessment、standard_contract 或 post_assessment_obligations，应优先生成具体 pathway 查询，让具体依据排在泛化基础规则之前。",
            "只有当用户询问出境基础规则、总体合规路径、豁免边界、路径关系，或地方/行业规则与全国规则关系时，才选择 cross_border_foundation pathway。",
            "如果 review_facts.cross_border_transfer 为 false，或材料明确“暂不出境/境内处理/不向境外提供”，不要因为问题里出现“是否触发安全评估”就选择 cross_border_foundation、security_assessment、standard_contract 或 certification；应优先选择 sensitive_personal_info 等境内处理相关 pathway，并保留否定边界。",
            "当问题或事实涉及申报、网信部门、安全评估、阈值、重要数据或大规模个人信息时，必须选择 security_assessment pathway。",
            "当问题或事实涉及已通过安全评估后的持续义务、重新申报、接收方/目的/范围变更、监督检查时，必须选择 post_assessment_obligations pathway。",
            "当问题或事实涉及标准合同文本、备案、境外接收方义务时，必须选择 standard_contract pathway。",
            "当问题或事实涉及认证、集团内部跨境共享、大湾区/香港个人信息跨境或认证路径责任时，必须选择 certification pathway。",
            "当问题或事实涉及人脸识别、生物识别、儿童个人信息、精确定位、行踪轨迹或敏感个人信息处理时，必须选择 sensitive_personal_info pathway。",
            "当问题或事实涉及境外远程访问境内数据库、VPN 查看或是否构成数据出境边界时，必须选择 remote_access_boundary pathway。",
            "当问题或事实同时涉及标准合同和安全评估门槛，并询问优先级/冲突时，必须选择 pathway_conflict pathway，同时选择 security_assessment 和 standard_contract。",
            "region_condition 只能从 controlled_region_facets 中选择一个和材料事实明确匹配的中国境内地区/自贸区 facet，并用其 query_terms 组合；没有明确命中时不要输出 region_condition。",
            "不要把境外接收方所在地（如新加坡、日本、美国、德国）写成 region_condition；它们只能出现在 material_fact 查询中。",
            "industry_condition 只能从 controlled_industry_facets 中选择一个和材料事实明确匹配的行业 facet，并用其 query_terms 组合；没有明确命中时不要输出 industry_condition。",
            "如果问题涉及自贸区、负面清单、地方口径或行业专项要求，同时保留全国基础规则查询，并追加匹配到的 region_condition 或 industry_condition。",
            "对否定式或边界问题要保留否定边界，例如“暂不出境”“境内处理”“是否一定触发”。",
            "优先输出 5 到 8 条互补查询；每条查询应短而具体，尽量包含可命中文件标题的中文关键词。",
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
