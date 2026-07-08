"""Tests for deterministic retrieval query planning (Issue 4)."""

from law_agent.review.facts import extract_facts
from law_agent.review.query_planner import plan_high_confidence_queries, plan_queries
from law_agent.review.schemas import ReviewFacts


def _query_types(queries) -> list[str]:
    return [q.query_type for q in queries]


# ---------------------------------------------------------------------------
# Legal issue query
# ---------------------------------------------------------------------------

def test_legal_issue_query_always_present() -> None:
    facts = ReviewFacts()
    queries = plan_queries("是否需要数据出境安全评估？", facts)

    assert len(queries) >= 1
    assert queries[0].query_type == "legal_issue"
    assert queries[0].text == "是否需要数据出境安全评估？"


def test_empty_facts_produces_only_legal_issue_and_missing() -> None:
    facts = ReviewFacts()
    queries = plan_queries("问题", facts)

    types = _query_types(queries)
    assert "legal_issue" in types
    assert "material_fact" not in types
    assert "region_condition" not in types
    assert "industry_condition" not in types


# ---------------------------------------------------------------------------
# Material fact query
# ---------------------------------------------------------------------------

def test_material_fact_query_with_cross_border_facts() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["手机号", "定位信息"],
        overseas_recipient="新加坡",
    )
    queries = plan_queries("是否需要数据出境安全评估？", facts)

    material_queries = [q for q in queries if q.query_type == "material_fact"]
    assert len(material_queries) == 1
    text = material_queries[0].text
    assert "数据出境" in text
    assert "手机号" in text
    assert "定位信息" in text
    assert "新加坡" in text


def test_material_fact_query_with_sensitive_info() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["人脸信息"],
        sensitive_personal_info=True,
    )
    queries = plan_queries("问题", facts)

    material_queries = [q for q in queries if q.query_type == "material_fact"]
    assert len(material_queries) == 1
    assert "敏感个人信息" in material_queries[0].text


# ---------------------------------------------------------------------------
# Region condition query
# ---------------------------------------------------------------------------

def test_region_query_when_region_set() -> None:
    facts = ReviewFacts(region="上海", cross_border_transfer=True)
    queries = plan_queries("上海自贸区数据出境负面清单要求？", facts)

    region_queries = [q for q in queries if q.query_type == "region_condition"]
    assert len(region_queries) == 1
    assert "上海" in region_queries[0].text
    assert "负面清单" in region_queries[0].text


# ---------------------------------------------------------------------------
# Industry condition query
# ---------------------------------------------------------------------------

def test_industry_query_when_industry_set() -> None:
    facts = ReviewFacts(industry="智能网联汽车")
    queries = plan_queries("智能网联汽车数据处理者安全要求？", facts)

    industry_queries = [q for q in queries if q.query_type == "industry_condition"]
    assert len(industry_queries) == 1
    assert "智能网联汽车" in industry_queries[0].text
    assert "安全管理" in industry_queries[0].text


def test_region_query_requires_explicit_regional_intent() -> None:
    facts = ReviewFacts(region="上海", cross_border_transfer=True)
    queries = plan_queries("个人信息处理规则？", facts, "公司在上海开展业务。")

    assert "region_condition" not in _query_types(queries)


def test_region_query_does_not_trigger_for_plain_cross_border_region() -> None:
    facts = ReviewFacts(region="北京", cross_border_transfer=True)
    queries = plan_queries("数据出境需要注意什么？", facts, "公司在北京开展业务。")

    assert "region_condition" not in _query_types(queries)


def test_region_query_does_not_treat_cn_as_local_region() -> None:
    facts = ReviewFacts(region="CN", cross_border_transfer=True)
    queries = plan_queries("数据出境后续义务？", facts, "数据传输至日本分析中心。")

    assert "region_condition" not in _query_types(queries)


def test_industry_query_requires_explicit_industry_intent() -> None:
    facts = ReviewFacts(industry="汽车")
    queries = plan_queries("个人信息处理规则？", facts, "汽车制造商开展普通营销活动。")

    assert "industry_condition" not in _query_types(queries)


# ---------------------------------------------------------------------------
# Missing information queries
# ---------------------------------------------------------------------------

def test_missing_information_queries_for_each_missing_fact() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        missing_information=[
            "overseas_recipient",
            "legal_basis_or_consent",
            "data_volume_threshold",
        ],
    )
    queries = plan_queries("问题", facts)

    missing_queries = [q for q in queries if q.query_type == "missing_information"]
    assert len(missing_queries) == 3
    texts = [q.text for q in missing_queries]
    assert any("境外接收方" in t for t in texts)
    assert any("同意" in t for t in texts)
    assert any("阈值" in t for t in texts)


def test_no_missing_queries_when_nothing_missing() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["手机号"],
        overseas_recipient="新加坡",
        processing_purpose="推荐",
        legal_basis_or_consent="用户同意",
        missing_information=[],
    )
    queries = plan_queries("问题", facts)

    assert "missing_information" not in _query_types(queries)


# ---------------------------------------------------------------------------
# Integration with extract_facts
# ---------------------------------------------------------------------------

def test_cross_border_sample_produces_multiple_query_types() -> None:
    material = "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。"
    question = "这个场景是否需要数据出境安全评估？"
    facts = extract_facts(material)
    queries = plan_queries(question, facts, material)

    types = _query_types(queries)
    assert "legal_issue" in types
    assert "material_fact" in types
    assert "missing_information" in types
    assert len(queries) >= 3


def test_automotive_sample_produces_industry_query() -> None:
    material = "智能网联汽车采集车辆位置和行驶轨迹数据，需进行数据出境安全评估。"
    facts = extract_facts(material)
    queries = plan_queries("汽车数据出境合规要求？", facts, material)

    types = _query_types(queries)
    assert "industry_condition" in types
    assert "material_fact" in types


def test_regional_sample_produces_region_query() -> None:
    material = "公司在上海自贸区开展业务，涉及数据出境。"
    facts = extract_facts(material)
    queries = plan_queries("上海数据出境负面清单要求？", facts, material)

    types = _query_types(queries)
    assert "region_condition" in types


def test_standard_contract_question_adds_targeted_query() -> None:
    material = "拟通过签订标准合同方式向德国分公司传输员工数据。"
    facts = extract_facts(material)
    queries = plan_queries("这个场景是否可以采用标准合同方式出境？", facts, material)

    assert any("标准合同" in query.text and "备案指南" in query.text for query in queries)


def test_cross_border_personal_info_filing_does_not_infer_standard_contract_query() -> None:
    material = (
        "集团要把境内员工姓名、手机号、邮箱同步到德国 HR 系统，"
        "全年涉及员工约3000人，已在员工告知书里说明用途。"
    )
    facts = extract_facts(material)
    queries = plan_queries("海外 HR 系统同步员工通讯录，应该准备哪类文件和备案？", facts, material)

    assert not any("标准合同" in query.text and "备案指南" in query.text for query in queries)


def test_standard_contract_filing_query_requires_cross_border_context() -> None:
    facts = ReviewFacts(data_types=["手机号"])
    queries = plan_queries("普通个人信息处理要准备哪类文件和备案？", facts, "App 收集手机号。")

    assert not any("标准合同" in query.text and "备案指南" in query.text for query in queries)


def test_standard_contract_filing_query_does_not_hijack_assessment_question() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["个人信息"],
        overseas_recipient="美国",
    )
    queries = plan_queries(
        "什么情况下必须走网信办申报，而不是只做普通备案？",
        facts,
        "大型平台计划将部分用户数据传输至美国云服务商。",
    )

    texts = [query.text for query in queries]
    assert not any("标准合同" in text and "备案指南" in text for text in texts)


def test_cross_border_assessment_intent_adds_threshold_query() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["个人信息"],
        overseas_recipient="美国",
    )
    queries = plan_queries(
        "海外 BI 团队要看国内用户画像，是不是一定要走安全评估？",
        facts,
        "平台累计注册用户约120万人，近期一年预计涉及约12万人个人信息。",
    )

    assert any("数据出境安全评估" in query.text and "申报条件" in query.text for query in queries)


def test_cross_border_assessment_template_requires_anchor_for_weak_terms() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["个人信息"],
        overseas_recipient="美国",
    )
    queries = plan_queries(
        "跨境业务备案材料怎么准备？",
        facts,
        "公司计划向美国合作方提供少量客户信息。",
    )

    assert not any("数据出境安全评估" in query.text for query in queries)


def test_high_confidence_queries_exclude_missing_information_noise() -> None:
    facts = ReviewFacts(
        region="天津",
        industry="汽车",
        cross_border_transfer=True,
        missing_information=["legal_basis_or_consent", "data_volume_threshold"],
    )

    queries = plan_high_confidence_queries(
        "天津自贸区汽车数据出境负面清单有什么特殊要求？",
        facts,
        "公司在天津自贸区开展汽车数据出境业务。",
    )

    types = _query_types(queries)
    assert "region_condition" in types
    assert "industry_condition" in types
    assert "missing_information" not in types


# ---------------------------------------------------------------------------
# Query ID determinism
# ---------------------------------------------------------------------------

def test_query_ids_are_unique_and_sequential() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        data_types=["手机号"],
        overseas_recipient="新加坡",
        region="上海",
        industry="汽车",
        missing_information=["legal_basis_or_consent"],
    )
    queries = plan_queries("问题", facts)

    ids = [q.query_id for q in queries]
    assert len(ids) == len(set(ids))
    assert ids[0] == "q_1"
