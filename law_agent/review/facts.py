"""Deterministic and LLM-assisted review fact extraction.

Issue 4: Extract fixed ``ReviewFacts`` from review material so that later
retrieval slices can bridge concrete business material with metadata-aware
legal evidence retrieval.

The default extractor is rule-based and dependency-free so tests never need
an LLM. An LLM adapter function with the same callable signature is provided
for optional production use.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from law_agent.review.schemas import ReviewFacts

FactsExtractor = Callable[[str, str | None], ReviewFacts]

# ---------------------------------------------------------------------------
# Term dictionaries
# ---------------------------------------------------------------------------

_CROSS_BORDER_TERMS: tuple[str, ...] = (
    "境外", "出境", "跨境", "海外", "国外", "传输至", "传输到",
    "发送给", "发送至", "传至", "提供给", "共享给",
)

_OVERSEAS_RECIPIENTS: dict[str, str] = {
    "新加坡": "新加坡",
    "香港": "香港",
    "美国": "美国",
    "日本": "日本",
    "韩国": "韩国",
    "欧盟": "欧盟",
    "德国": "德国",
    "英国": "英国",
    "法国": "法国",
    "加拿大": "加拿大",
    "澳大利亚": "澳大利亚",
    "俄罗斯": "俄罗斯",
    "印度": "印度",
    "越南": "越南",
    "马来西亚": "马来西亚",
    "泰国": "泰国",
    "台湾": "台湾",
    "澳门": "澳门",
    "印尼": "印尼",
    "菲律宾": "菲律宾",
}

_DATA_TYPE_TERMS: dict[str, str] = {
    "手机号": "手机号",
    "电话号码": "手机号",
    "手机号码": "手机号",
    "定位": "定位信息",
    "位置信息": "定位信息",
    "车辆位置": "定位信息",
    "位置": "定位信息",
    "设备ID": "设备标识",
    "设备标识": "设备标识",
    "设备唯一标识": "设备标识",
    "IMEI": "设备标识",
    "行为日志": "行为日志",
    "行驶轨迹": "行驶轨迹",
    "轨迹": "行驶轨迹",
    "身份证": "身份证号",
    "身份证号": "身份证号",
    "人脸": "人脸信息",
    "人脸数据": "人脸信息",
    "面部": "人脸信息",
    "地址": "住址",
    "住址": "住址",
    "邮箱": "电子邮箱",
    "电子邮件": "电子邮箱",
    "银行卡": "银行账户",
    "银行账户": "银行账户",
    "交易记录": "交易记录",
    "通讯录": "通讯录",
    "照片": "照片",
    "指纹": "指纹",
    "健康": "健康信息",
    "医疗": "医疗信息",
    "病历": "医疗信息",
    "生物识别": "生物识别信息",
}

_SENSITIVE_HINTS: tuple[str, ...] = (
    "定位", "人脸", "面部", "身份证", "医疗", "病历", "金融账户",
    "银行账户", "生物识别", "指纹", "健康", "财产", "宗教",
    "14岁以下", "未成年人", "儿童",
)

# Ordered from most specific to least specific so "智能网联汽车" wins over "汽车".
_INDUSTRY_TERMS: tuple[tuple[str, str], ...] = (
    ("智能网联汽车", "智能网联汽车"),
    ("智能网联", "智能网联汽车"),
    ("金融信息服务", "金融信息服务"),
    ("汽车", "汽车"),
    ("金融", "金融"),
    ("医疗", "医疗"),
    ("教育", "教育"),
)

_REGION_TERMS: dict[str, str] = {
    "上海": "上海",
    "广东": "广东",
    "天津": "天津",
    "福建": "福建",
    "广西": "广西",
    "重庆": "重庆",
    "浙江": "浙江",
    "海南": "海南",
    "北京": "北京",
    "深圳": "深圳",
    "江苏": "江苏",
}

_CONSENT_TERMS: dict[str, str] = {
    "同意": "用户同意",
    "授权": "用户授权",
    "告知": "已告知",
    "许可": "已许可",
    "签署": "已签署协议",
    "签订协议": "已签署协议",
    "知情": "知情同意",
}

_PURPOSE_KEYWORDS: tuple[str, ...] = (
    "推荐", "营销", "广告", "统计分析", "分析", "统计",
    "安全", "风控", "运营", "研发", "测试", "客服",
    "售后服务", "产品改进", "优化", "画像",
)

_THRESHOLD_TERMS: tuple[str, ...] = (
    "阈值", "数量", "万人", "百万", "条", "用户数", "处理量",
    "人数", "规模",
)


# ---------------------------------------------------------------------------
# Deterministic rules extractor
# ---------------------------------------------------------------------------

def _detect_data_types(text: str) -> list[str]:
    detected: list[str] = []
    for term, label in _DATA_TYPE_TERMS.items():
        if term in text and label not in detected:
            detected.append(label)
    return detected


def _detect_overseas_recipient(text: str) -> str | None:
    for term, label in _OVERSEAS_RECIPIENTS.items():
        if term in text:
            return label
    return None


def _detect_industry(text: str) -> str | None:
    for term, label in _INDUSTRY_TERMS:
        if term in text:
            return label
    return None


def _detect_region(text: str) -> str | None:
    for term, label in _REGION_TERMS.items():
        if term in text:
            return label
    return None


def _detect_purpose(text: str) -> str | None:
    match = re.search(r"用于([^\s，。；,;：:]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"目的[是为：:]\s*([^\s，。；,;]+)", text)
    if match:
        return match.group(1)
    for keyword in _PURPOSE_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def _detect_consent(text: str) -> str | None:
    for term, label in _CONSENT_TERMS.items():
        if term in text:
            return label
    return None


def _has_data_volume_indicator(text: str) -> bool:
    if any(term in text for term in _THRESHOLD_TERMS):
        return True
    return bool(re.search(r"\d+\s*[万亿千百十]", text))


def _detect_missing_information(
    text: str,
    *,
    cross_border: bool | None,
    overseas_recipient: str | None,
    data_types: list[str],
    processing_purpose: str | None,
    legal_basis_or_consent: str | None,
) -> list[str]:
    missing: list[str] = []
    if cross_border:
        if not overseas_recipient:
            missing.append("overseas_recipient")
        if not legal_basis_or_consent:
            missing.append("legal_basis_or_consent")
        if not _has_data_volume_indicator(text):
            missing.append("data_volume_threshold")
    else:
        if not legal_basis_or_consent:
            missing.append("legal_basis_or_consent")
    if not processing_purpose:
        missing.append("processing_purpose")
    if not data_types:
        missing.append("data_types")
    return missing


def extract_facts(material_text: str, question: str | None = None) -> ReviewFacts:
    """Extract ``ReviewFacts`` from review material using deterministic rules.

    The ``question`` parameter is accepted for interface compatibility with the
    LLM adapter but is not used by the rules extractor. Facts come from the
    material text only.
    """

    text = material_text

    data_types = _detect_data_types(text)
    cross_border = any(term in text for term in _CROSS_BORDER_TERMS)
    overseas_recipient = _detect_overseas_recipient(text)
    sensitive = any(hint in text for hint in _SENSITIVE_HINTS)
    industry = _detect_industry(text)
    region = _detect_region(text)
    purpose = _detect_purpose(text)
    consent = _detect_consent(text)

    missing = _detect_missing_information(
        text,
        cross_border=cross_border if cross_border else None,
        overseas_recipient=overseas_recipient,
        data_types=data_types,
        processing_purpose=purpose,
        legal_basis_or_consent=consent,
    )

    return ReviewFacts(
        data_types=data_types,
        sensitive_personal_info=True if sensitive else None,
        cross_border_transfer=True if cross_border else None,
        overseas_recipient=overseas_recipient,
        processing_purpose=purpose,
        legal_basis_or_consent=consent,
        industry=industry,
        region=region,
        missing_information=missing,
    )


# ---------------------------------------------------------------------------
# Optional LLM-based extractor (same callable signature)
# ---------------------------------------------------------------------------

_LLM_PROMPT_VERSION = "0.1.0"


def extract_facts_with_llm(material_text: str, question: str | None = None) -> ReviewFacts:
    """Extract ``ReviewFacts`` using an OpenAI-compatible LLM.

    Requires ``OPENAI_COMPATIBLE_API_KEY`` to be configured. Falls back to
    rule-based extraction for any field the LLM omits.
    """

    from law_agent.config import require_llm_config
    from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient

    config = require_llm_config()
    client = OpenAICompatibleClient(config)

    prompt = {
        "question": question,
        "material_text": material_text[:6000],
        "required_schema": {
            "business_activity": "string or null",
            "data_types": ["string"],
            "sensitive_personal_info": "boolean or null",
            "cross_border_transfer": "boolean or null",
            "overseas_recipient": "string or null",
            "processing_purpose": "string or null",
            "legal_basis_or_consent": "string or null",
            "industry": "string or null",
            "region": "string or null",
            "missing_information": ["string"],
        },
        "instructions": (
            "从用户材料中抽取合规审查事实。只输出 JSON object。"
            "未检测到的事实用 null。missing_information 列出缺失的必要事实。"
        ),
    }

    data = client.chat_json(
        [
            ChatMessage(
                role="system",
                content=(
                    "你是法律合规审查事实抽取助手。"
                    "只基于用户材料抽取事实，不推测。必须输出 JSON object。"
                ),
            ),
            ChatMessage(role="user", content=json.dumps(prompt, ensure_ascii=False)),
        ]
    )

    rules_facts = extract_facts(material_text, question)

    def _coerce_str(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _coerce_bool(value: object) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "是"}
        return bool(value)

    def _coerce_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    return ReviewFacts(
        business_activity=_coerce_str(data.get("business_activity")),
        data_types=_coerce_list(data.get("data_types")) or rules_facts.data_types,
        sensitive_personal_info=_coerce_bool(data.get("sensitive_personal_info")),
        cross_border_transfer=_coerce_bool(data.get("cross_border_transfer")),
        overseas_recipient=_coerce_str(data.get("overseas_recipient")),
        processing_purpose=_coerce_str(data.get("processing_purpose")),
        legal_basis_or_consent=_coerce_str(data.get("legal_basis_or_consent")),
        industry=_coerce_str(data.get("industry")),
        region=_coerce_str(data.get("region")),
        missing_information=(
            _coerce_list(data.get("missing_information"))
            or rules_facts.missing_information
        ),
    )
