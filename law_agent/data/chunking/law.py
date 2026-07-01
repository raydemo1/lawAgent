"""Structure-aware chunking for Chinese laws and regulations."""

from __future__ import annotations

import re

from law_agent.data.schemas import Chunk, Document

ARTICLE_RE = re.compile(r"(第[一二三四五六七八九十百千万零〇]+条)")


def split_law_articles(text: str) -> list[tuple[str, str]]:
    """Split Chinese legal text by article markers while preserving article numbers."""

    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        return [("", stripped)] if stripped else []

    articles: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        article_no = match.group(1)
        article_text = text[start:end].strip()
        if article_text:
            articles.append((article_no, article_text))
    return articles


def chunk_law_document(document: Document) -> list[Chunk]:
    """Create retrieval chunks for a law-like document."""

    articles = split_law_articles(document.text)
    chunks: list[Chunk] = []
    for index, (article_no, article_text) in enumerate(articles):
        chunk_id = f"{document.doc_id}:{index:04d}"
        heading_path = [document.title]
        if article_no:
            heading_path.append(article_no)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                source_id=document.source_id,
                title=document.title,
                text=article_text,
                chunk_index=index,
                heading_path=heading_path,
                article_no=article_no or None,
                prev_chunk_id=f"{document.doc_id}:{index - 1:04d}" if index > 0 else None,
                next_chunk_id=(
                    f"{document.doc_id}:{index + 1:04d}" if index + 1 < len(articles) else None
                ),
                authority=document.authority,
                law_status=document.law_status,
                source_url=document.source_url,
                topic_tags=document.topic_tags,
                char_count=len(article_text),
            )
        )
    return chunks

