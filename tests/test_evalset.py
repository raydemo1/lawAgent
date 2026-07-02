from law_agent.data.evalset.build_cases import build_retrieval_cases
from law_agent.data.schemas import Chunk


def test_retrieval_case_keeps_citation_context() -> None:
    chunk = Chunk(
        chunk_id="doc:0000",
        doc_id="doc",
        source_id="source",
        title="中华人民共和国个人信息保护法",
        text="第一条 为了保护个人信息权益。",
        chunk_index=0,
        heading_path=["中华人民共和国个人信息保护法", "第一章 总则", "第一条"],
        article_no="第一条",
        authority="national_law",
        law_status="effective",
        source_url="https://flk.npc.gov.cn/",
        topic_tags=["个人信息保护"],
        char_count=15,
        citation_label="中华人民共和国个人信息保护法 第一条",
    )

    case = build_retrieval_cases([chunk], limit=1)[0]

    assert case.expected_heading_path == ["中华人民共和国个人信息保护法", "第一章 总则", "第一条"]
    assert case.expected_citation_label == "中华人民共和国个人信息保护法 第一条"


def test_retrieval_case_uses_paragraph_citation_in_question() -> None:
    chunk = Chunk(
        chunk_id="doc:0001",
        doc_id="doc",
        source_id="source",
        title="中华人民共和国个人信息保护法",
        text="在中华人民共和国境外处理中华人民共和国境内自然人个人信息的活动，有下列情形之一的，也适用本法。",
        chunk_index=1,
        heading_path=["中华人民共和国个人信息保护法", "第三条", "第2款"],
        article_no="第三条",
        paragraph_no="第2款",
        authority="national_law",
        law_status="effective",
        source_url="https://flk.npc.gov.cn/",
        topic_tags=["个人信息保护"],
        char_count=47,
        citation_label="中华人民共和国个人信息保护法 第三条 第2款",
    )

    case = build_retrieval_cases([chunk], limit=1)[0]

    assert case.question == "中华人民共和国个人信息保护法 第三条 第2款规定了什么？"
