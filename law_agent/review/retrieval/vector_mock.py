"""Vector mock retriever for local hybrid retrieval.

Issue 6: Simulate semantic retrieval without a real embedding API. The mock
scores token overlap against a richer field set than the keyword retriever:
``text + title + topic_tags + legal_domain + applicable_subjects``. This
mirrors how a real vector adapter would leverage metadata-enriched fields.

Interface matches the future vector adapter:
``search(queries, top_k) -> list[RetrievalHit]`` with ``retriever="vector_mock"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from law_agent.data.schemas import Chunk
from law_agent.review.retrieval.keyword import normalize_text, tokenize
from law_agent.review.schemas import RetrievalHit, RetrievalQueryType


@dataclass
class _VectorIndexEntry:
    """Pre-tokenized chunk with expanded metadata token set."""

    chunk: Chunk
    # Union of tokens from text, title, topic_tags, legal_domain,
    # applicable_subjects, and heading_path. This simulates the richer
    # semantic field a real embedding model would encode.
    semantic_tokens: set[str] = field(default_factory=set)


def _build_semantic_tokens(chunk: Chunk) -> set[str]:
    """Build a token set from all metadata-enriched fields."""

    parts: list[str] = [chunk.text, chunk.title]
    parts.extend(chunk.topic_tags)
    parts.extend(chunk.legal_domain)
    parts.extend(chunk.applicable_subjects)
    parts.extend(chunk.heading_path)
    if chunk.citation_label:
        parts.append(chunk.citation_label)
    if chunk.article_no:
        parts.append(chunk.article_no)

    tokens: set[str] = set()
    for part in parts:
        tokens.update(tokenize(part))
    return tokens


class VectorMockRetriever:
    """Local vector mock retriever using expanded metadata token overlap.

    Not a real embedding model. Scores query token overlap against the
    union of text, title, topic_tags, legal_domain, applicable_subjects,
    and heading_path. This gives broader semantic coverage than the
    keyword retriever (which focuses on body/title/label).
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self._index: list[_VectorIndexEntry] = [
            _VectorIndexEntry(chunk=chunk, semantic_tokens=_build_semantic_tokens(chunk))
            for chunk in chunks
        ]

    @property
    def chunk_count(self) -> int:
        return len(self._index)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_type: RetrievalQueryType | None = None,
    ) -> list[RetrievalHit]:
        """Return scored hits for a single query string."""

        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)

        if not query_token_set:
            return []

        scored: list[tuple[float, int]] = []
        for idx, entry in enumerate(self._index):
            hits = query_token_set & entry.semantic_tokens
            if not hits:
                continue
            # Jaccard-like overlap score
            score = len(hits) / len(query_token_set)
            # Boost for title and topic_tag matches (simulating embedding
            # attention to semantic fields)
            title_tokens = set(tokenize(entry.chunk.title))
            title_hits = query_token_set & title_tokens
            if title_hits:
                score += len(title_hits) / len(query_token_set) * 0.5

            tag_tokens: set[str] = set()
            for tag in entry.chunk.topic_tags:
                tag_tokens.update(tokenize(tag))
            tag_hits = query_token_set & tag_tokens
            if tag_hits:
                score += len(tag_hits) / len(query_token_set) * 0.3

            scored.append((score, idx))

        scored.sort(key=lambda pair: (-pair[0], pair[1]))

        hits: list[RetrievalHit] = []
        for rank, (score, idx) in enumerate(scored[:top_k]):
            chunk = self._index[idx].chunk
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    source_id=chunk.source_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=round(score, 6),
                    rank=rank,
                    retriever="vector_mock",
                    citation_role=chunk.citation_role,
                    can_cite_clause=chunk.can_cite_clause,
                    source_url=chunk.source_url,
                    matched_query_type=query_type,
                )
            )
        return hits
