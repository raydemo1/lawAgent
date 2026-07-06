"""Tests for deterministic review fact extraction (Issue 4)."""

from law_agent.review.facts import extract_facts


# ---------------------------------------------------------------------------
# Cross-border app sample
# ---------------------------------------------------------------------------

CROSS_BORDER_MATERIAL = (
    "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。"
    "目前日均处理约50万用户的数据。"
)


def test_cross_border_sample_extracts_data_types() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert "手机号" in facts.data_types
    assert "定位信息" in facts.data_types


def test_cross_border_sample_extracts_cross_border_flag() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert facts.cross_border_transfer is True


def test_cross_border_sample_extracts_overseas_recipient() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert facts.overseas_recipient == "新加坡"


def test_cross_border_sample_extracts_sensitive_personal_info() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert facts.sensitive_personal_info is True


def test_cross_border_sample_extracts_processing_purpose() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert facts.processing_purpose is not None
    assert "推荐" in facts.processing_purpose


def test_cross_border_sample_lists_missing_consent_and_threshold() -> None:
    facts = extract_facts(CROSS_BORDER_MATERIAL)

    assert "legal_basis_or_consent" in facts.missing_information


def test_cross_border_sample_with_threshold_does_not_miss_threshold() -> None:
    material = (
        "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。"
        "目前日均处理约50万用户的数据。已获得用户同意。"
    )
    facts = extract_facts(material)

    assert "legal_basis_or_consent" not in facts.missing_information
    assert facts.legal_basis_or_consent is not None
    assert "data_volume_threshold" not in facts.missing_information


# ---------------------------------------------------------------------------
# Automotive sample
# ---------------------------------------------------------------------------

AUTOMOTIVE_MATERIAL = (
    "智能网联汽车采集车辆位置和行驶轨迹数据，"
    "需进行数据出境安全评估。"
)


def test_automotive_sample_extracts_industry() -> None:
    facts = extract_facts(AUTOMOTIVE_MATERIAL)

    assert facts.industry == "智能网联汽车"


def test_automotive_sample_extracts_cross_border() -> None:
    facts = extract_facts(AUTOMOTIVE_MATERIAL)

    assert facts.cross_border_transfer is True


def test_automotive_sample_extracts_location_data_type() -> None:
    facts = extract_facts(AUTOMOTIVE_MATERIAL)

    assert "定位信息" in facts.data_types
    assert "行驶轨迹" in facts.data_types


# ---------------------------------------------------------------------------
# Regional negative-list sample
# ---------------------------------------------------------------------------

REGIONAL_MATERIAL = (
    "公司在上海自贸区开展业务，涉及数据出境，"
    "需要了解负面清单管理要求。"
)


def test_regional_sample_extracts_region() -> None:
    facts = extract_facts(REGIONAL_MATERIAL)

    assert facts.region == "上海"


def test_regional_sample_extracts_cross_border() -> None:
    facts = extract_facts(REGIONAL_MATERIAL)

    assert facts.cross_border_transfer is True


# ---------------------------------------------------------------------------
# Missing information detection
# ---------------------------------------------------------------------------

def test_missing_overseas_recipient_when_cross_border_without_recipient() -> None:
    facts = extract_facts("我们将数据传输至境外用于分析。")

    assert facts.cross_border_transfer is True
    assert facts.overseas_recipient is None
    assert "overseas_recipient" in facts.missing_information


def test_no_cross_border_does_not_require_overseas_recipient() -> None:
    facts = extract_facts("我们收集手机号用于客服，已获得用户同意。")

    assert facts.cross_border_transfer is None
    assert "overseas_recipient" not in facts.missing_information


def test_empty_material_produces_missing_information() -> None:
    facts = extract_facts("我们处理一些数据。")

    assert "legal_basis_or_consent" in facts.missing_information
    assert "processing_purpose" in facts.missing_information
    assert "data_types" in facts.missing_information


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_industry_specificity_prefers_smart_connected_vehicle() -> None:
    facts = extract_facts("智能网联汽车数据出境。")

    assert facts.industry == "智能网联汽车"


def test_industry_falls_back_to_automotive() -> None:
    facts = extract_facts("汽车制造商采集车辆数据。")

    assert facts.industry == "汽车"


def test_question_parameter_does_not_affect_rules_extraction() -> None:
    material = "我们收集手机号用于客服。"
    facts_no_question = extract_facts(material)
    facts_with_question = extract_facts(material, "是否需要数据出境安全评估？")

    assert facts_no_question == facts_with_question


def test_multiple_data_types_deduplicated() -> None:
    facts = extract_facts("收集手机号、电话号码和设备ID。")

    assert facts.data_types.count("手机号") == 1
    assert "设备标识" in facts.data_types


def test_consent_detection() -> None:
    facts = extract_facts("已获得用户单独同意，将手机号传输至新加坡。")

    assert facts.legal_basis_or_consent is not None
    assert "legal_basis_or_consent" not in facts.missing_information


# ---------------------------------------------------------------------------
# Negated consent detection (P1 bug)
# ---------------------------------------------------------------------------

def test_negated_consent_not_detected() -> None:
    # "未取得用户同意" means "did NOT obtain user consent" -> must NOT be
    # treated as affirmative consent.
    facts = extract_facts("未取得用户同意")

    assert facts.legal_basis_or_consent is None
    assert "legal_basis_or_consent" in facts.missing_information


def test_affirmative_consent_still_works() -> None:
    # Affirmative phrasings must continue to be detected (no false negatives).
    affirmative_samples = [
        "已取得用户同意",
        "用户已授权",
    ]
    for sample in affirmative_samples:
        facts = extract_facts(sample)

        assert facts.legal_basis_or_consent is not None, (
            f"affirmative consent term should be detected: {sample!r}"
        )
        assert "legal_basis_or_consent" not in facts.missing_information


def test_consent_in_longer_negated_context() -> None:
    # A negated consent embedded in a longer sentence must still be ignored.
    facts = extract_facts("公司未取得用户同意就将数据传输至境外")

    assert facts.legal_basis_or_consent is None
    assert "legal_basis_or_consent" in facts.missing_information
