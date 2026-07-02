from law_agent.data.cleaners.common import clean_text
from law_agent.data.cleaners.pipeline import clean_document
from law_agent.data.schemas import Document, IngestMeta


def test_clean_text_removes_mechanical_noise_without_rewriting_articles() -> None:
    raw = (
        "中华人民共和国个人信息保护法\r\n"
        "中华人民共和国个人信息保护法\r\n"
        "\u0000第一条  为了保护个人信息权益，规范个人信息处理活动。\r\n"
        "\r\n"
        "\r\n"
        "第二条  自然人的个人信息受法律保护。   \r\n"
    )

    result = clean_text(raw, title="中华人民共和国个人信息保护法")

    assert result.text.count("中华人民共和国个人信息保护法") == 1
    assert "第一条  为了保护个人信息权益，规范个人信息处理活动。" in result.text
    assert "第二条  自然人的个人信息受法律保护。" in result.text
    assert result.rule_hits["duplicate_title"] == 1
    assert result.rule_hits["control_chars"] == 1


def test_clean_text_removes_repeated_contents_table() -> None:
    raw = (
        "中华人民共和国个人信息保护法\n"
        "目　　录\n"
        "第一章　总　　则\n"
        "第二章　个人信息处理规则\n"
        "第一章　总　　则\n"
        "第一条　为了保护个人信息权益，规范个人信息处理活动。\n"
    )

    result = clean_text(raw, title="中华人民共和国个人信息保护法")

    assert "目　　录" not in result.text
    assert result.text.count("第一章　总　　则") == 1
    assert "第一条　为了保护个人信息权益" in result.text
    assert result.rule_hits["contents_table_lines"] == 3


def test_clean_text_removes_web_boilerplate_from_cac_pages() -> None:
    raw = (
        "Title: 国家互联网信息办公室发布《数据出境安全评估申报指南（第三版）》\n"
        "URL Source: https://www.cac.gov.cn/example.htm\n"
        "Markdown Content:\n"
        "2026年07月02日 星期四\n"
        "[设为首页](#)[加入收藏](#)[手机版](#)[繁體](#)\n"
        "*   ![Image 1](logo.png)\n"
        "当前位置：[首页](https://www.cac.gov.cn/)>[正文](javascript:void(0);)\n"
        "# 国家互联网信息办公室发布《数据出境安全评估申报指南（第三版）》\n"
        "为了指导和帮助数据处理者规范有序申报数据出境安全评估。\n"
        "关闭\n"
        "Produced By CMS 网站群内容管理系统 publishdate:2025/06/27 17:01:53\n"
    )

    result = clean_text(raw, title="数据出境安全评估申报指南（第三版）")

    assert "Title:" not in result.text
    assert "设为首页" not in result.text
    assert "Produced By CMS" not in result.text
    assert "为了指导和帮助数据处理者" in result.text
    assert result.rule_hits["web_boilerplate_lines"] == 9


def test_clean_text_removes_dot_leader_toc_but_keeps_front_matter_body() -> None:
    raw = (
        "目次\n"
        "前言 ................................................................................ III\n"
        "引言 ................................................................................. IV\n"
        "1 范围 ................................................................................ 1\n"
        "前言\n"
        "本文件按照 GB/T 1.1 的规定起草。\n"
        "引言\n"
        "本文件用于指导数据分类分级工作。\n"
    )

    result = clean_text(raw)

    assert "................................................................" not in result.text
    assert "前言\n本文件按照 GB/T 1.1 的规定起草。" in result.text
    assert "引言\n本文件用于指导数据分类分级工作。" in result.text
    assert result.rule_hits["dot_leader_toc_lines"] == 3


def test_clean_document_cleans_structure_sections() -> None:
    document = Document(
        doc_id="doc-1",
        source_id="src-1",
        title="测试文档",
        source_url="https://example.com",
        source_site="example.com",
        doc_type="policy",
        text="测试文档\n正文\n",
        structure=[
            {
                "heading_path": ["测试文档"],
                "text": "Title: 测试文档\nMarkdown Content:\n正文\nProduced By CMS 网站群内容管理系统\n",
            }
        ],
        ingest_meta=IngestMeta(
            fetched_at="2026-07-02T00:00:00+00:00",
            parser="test_parser",
            parser_version="0.1.0",
        ),
    )

    cleaned = clean_document(document)

    assert "Title:" not in cleaned.structure[0].text
    assert "Produced By CMS" not in cleaned.structure[0].text
    assert "正文" in cleaned.structure[0].text
