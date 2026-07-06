"""Default golden-set scenarios for review evaluation (Issue 9).

12 scenario cases covering:
- Cross-border data export assessment (3 cases)
- Standard contract for personal info export (2 cases)
- Smart connected vehicle / automotive (2 cases)
- Regional negative list (Shanghai, Tianjin, Hainan) (3 cases)
- Sensitive personal information (1 case)
- Abstention case (insufficient info) (1 case)
"""

from __future__ import annotations

from law_agent.review.evalset.schemas import EvalScenario

DEFAULT_SCENARIOS: list[EvalScenario] = [
    # ------------------------------------------------------------------
    # Cross-border data export assessment
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_cross_border_001",
        question="这个场景是否需要数据出境安全评估？",
        material_text=(
            "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。"
            "目前日均处理约50万用户的数据。"
        ),
        expected_sources=[
            "cac_data_export_security_assessment_measures_2022",
            "cac_data_export_assessment_qna_2022",
            "missing_20260702_009",
        ],
        expected_citation_roles=["primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        must_not_cite_as_clause=[],
        tags=["cross_border", "assessment", "personal_info"],
    ),
    EvalScenario(
        case_id="eval_cross_border_002",
        question="数据出境安全评估的申报条件是什么？",
        material_text=(
            "公司是大型互联网平台，处理超过1000万用户个人信息，"
            "计划将部分用户数据传输至美国云服务商。"
        ),
        expected_sources=[
            "cac_data_export_security_assessment_measures_2022",
            "missing_20260702_009",
        ],
        expected_citation_roles=["primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["cross_border", "assessment", "large_scale"],
    ),
    EvalScenario(
        case_id="eval_cross_border_003",
        question="数据出境后还需要做什么合规工作？",
        material_text=(
            "我们已通过数据出境安全评估，将用户行为数据传输至日本分析中心。"
            "想知道后续还需要履行哪些义务。"
        ),
        expected_sources=[
            "cac_data_export_security_assessment_measures_2022",
            "cac_cross_border_data_flow_rules_2024",
        ],
        expected_citation_roles=["primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["cross_border", "post_assessment"],
    ),

    # ------------------------------------------------------------------
    # Standard contract for personal info export
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_standard_contract_001",
        question="这个场景是否可以采用标准合同方式出境？",
        material_text=(
            "公司规模较小，处理约5万人个人信息，"
            "拟通过签订标准合同方式向德国分公司传输员工数据。已取得员工同意。"
        ),
        expected_sources=[
            "cac_personal_info_export_standard_contract_measures_2023",
            "cac_personal_info_export_standard_contract_filing_guide_v2_2024",
        ],
        expected_citation_roles=["primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["standard_contract", "small_scale"],
    ),
    EvalScenario(
        case_id="eval_standard_contract_002",
        question="标准合同备案需要准备哪些材料？",
        material_text=(
            "我们准备用标准合同方式将客户信息传输至境外合作方，"
            "需要了解备案流程和所需材料。"
        ),
        expected_sources=[
            "cac_personal_info_export_standard_contract_filing_guide_v2_2024",
            "cac_personal_info_export_standard_contract_template_2023",
        ],
        expected_citation_roles=["primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["standard_contract", "filing"],
    ),

    # ------------------------------------------------------------------
    # Smart connected vehicle / automotive
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_automotive_001",
        question="智能网联汽车数据出境有什么特殊要求？",
        material_text=(
            "智能网联汽车采集车辆位置和行驶轨迹数据，"
            "需将数据传输至海外研发中心进行分析。"
        ),
        expected_sources=[
            "missing_20260702_001",
            "missing_20260702_002",
            "cac_data_export_security_assessment_measures_2022",
        ],
        expected_citation_roles=[
            "conditional_industry_basis",
            "primary_legal_basis",
        ],
        should_trigger_second_retrieval=True,
        should_abstain=False,
        tags=["automotive", "cross_border", "industry"],
    ),
    EvalScenario(
        case_id="eval_automotive_002",
        question="汽车数据处理者需要遵守哪些安全要求？",
        material_text=(
            "汽车制造商在车辆生产和运营中处理车主个人信息和车辆运行数据，"
            "需要了解行业安全要求。"
        ),
        expected_sources=[
            "missing_20260702_001",
            "missing_20260702_004",
        ],
        expected_citation_roles=["conditional_industry_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["automotive", "industry", "security"],
    ),

    # ------------------------------------------------------------------
    # Regional negative list
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_shanghai_001",
        question="上海自贸区数据出境负面清单有什么要求？",
        material_text=(
            "公司在上海自贸区开展业务，涉及用户数据出境，"
            "需要了解负面清单管理要求。"
        ),
        expected_sources=[
            "missing_20260702_013",
            "missing_20260702_006",
        ],
        expected_citation_roles=["conditional_local_basis"],
        should_trigger_second_retrieval=True,
        should_abstain=False,
        tags=["regional", "shanghai", "negative_list"],
    ),
    EvalScenario(
        case_id="eval_tianjin_001",
        question="天津自贸区负面清单如何适用？",
        material_text=(
            "企业在天津自贸区注册，处理个人信息拟出境，"
            "想了解天津版负面清单的规定。"
        ),
        expected_sources=[
            "missing_20260702_005",
        ],
        expected_citation_roles=["conditional_local_basis"],
        should_trigger_second_retrieval=True,
        should_abstain=False,
        tags=["regional", "tianjin", "negative_list"],
    ),
    EvalScenario(
        case_id="eval_hainan_001",
        question="海南自贸港数据出境有什么特殊政策？",
        material_text=(
            "公司在海南自贸港运营旅游平台，需要将游客数据传输至境外关联公司。"
        ),
        expected_sources=[
            "missing_20260702_007",
        ],
        expected_citation_roles=["conditional_local_basis"],
        should_trigger_second_retrieval=True,
        should_abstain=False,
        tags=["regional", "hainan", "negative_list"],
    ),

    # ------------------------------------------------------------------
    # Sensitive personal information
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_sensitive_001",
        question="处理人脸信息需要遵守什么规定？",
        material_text=(
            "公司计划在商场部署人脸识别系统进行客流分析，"
            "收集顾客人脸信息用于商业分析。"
        ),
        expected_sources=[
            "tc260_sensitive_pip_identification_guide_2024",
            "tc260_sensitive_pip_processing_requirements_2025",
            "flk_npc_ff8081817b6472a3017b656cc2040044",
        ],
        expected_citation_roles=["implementation_reference", "primary_legal_basis"],
        should_trigger_second_retrieval=False,
        should_abstain=False,
        tags=["sensitive", "facial_recognition"],
    ),

    # ------------------------------------------------------------------
    # Abstention case (insufficient info)
    # ------------------------------------------------------------------
    EvalScenario(
        case_id="eval_abstain_001",
        question="这个数据处理活动是否合规？",
        material_text="我们处理一些数据。",
        expected_sources=[],
        expected_citation_roles=[],
        should_trigger_second_retrieval=False,
        should_abstain=True,
        must_not_cite_as_clause=[],
        tags=["abstention", "insufficient_info"],
    ),
]


def get_default_scenarios() -> list[EvalScenario]:
    """Return the default golden-set scenarios."""

    return list(DEFAULT_SCENARIOS)
