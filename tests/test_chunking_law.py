from law_agent.data.chunking.law import chunk_law_document, split_law_articles
from law_agent.data.schemas import Document, IngestMeta


def test_split_law_articles_preserves_article_markers() -> None:
    text = "第一条  保护个人信息。\n第二条  规范处理活动。"

    articles = split_law_articles(text)

    assert articles == [
        ("第一条", "第一条  保护个人信息。"),
        ("第二条", "第二条  规范处理活动。"),
    ]


def test_chunk_law_document_keeps_parent_traceability() -> None:
    document = Document(
        doc_id="flk_npc_pipl_2021",
        source_id="flk_npc_pipl_2021",
        title="中华人民共和国个人信息保护法",
        source_url="https://flk.npc.gov.cn/",
        source_site="flk.npc.gov.cn",
        doc_type="law",
        authority="national_law",
        law_status="effective",
        topic_tags=["个人信息保护"],
        text="第一条  保护个人信息。\n第二条  规范处理活动。",
        ingest_meta=IngestMeta(
            fetched_at="2026-07-01T00:00:00Z",
            parser="test_parser",
            parser_version="0.1.0",
        ),
    )

    chunks = chunk_law_document(document)

    assert [chunk.article_no for chunk in chunks] == ["第一条", "第二条"]
    assert chunks[0].next_chunk_id == "flk_npc_pipl_2021:0001"
    assert chunks[1].prev_chunk_id == "flk_npc_pipl_2021:0000"
    assert chunks[0].heading_path == ["中华人民共和国个人信息保护法", "第一条"]
    assert chunks[0].authority == "national_law"

