"""Dependency-free keyword retrieval scorer.

Issue 5: Implement a local keyword/BM25-style baseline retriever that returns
scored evidence hits for a review case. No third-party dependencies so the
loop runs locally without Elasticsearch or embedding services.

Scoring pipeline:
1. Normalize Chinese punctuation and lowercase ASCII.
2. Tokenize into Chinese character bigrams plus contiguous ASCII/number runs.
3. Score each chunk by query token overlap, with boosts for title,
   citation_label, and exact phrase matches.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from law_agent.data.schemas import Chunk
from law_agent.review.schemas import RetrievalHit, RetrievalQueryType

# ---------------------------------------------------------------------------
# Text normalization and tokenization
# ---------------------------------------------------------------------------

# Chinese full-width punctuation to replace with spaces
_PUNCT_RE = re.compile(
    r"[，。；：、（）《》""''【】「」　]"
)

# Strip remaining non-CJK, non-ASCII-alnum chars after punctuation normalization
_STRIP_RE = re.compile(r"[^\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9\s]")


def normalize_text(text: str) -> str:
    """Normalize Chinese punctuation and case for tokenization."""

    # NFC first so decomposed chars behave consistently
    text = unicodedata.normalize("NFC", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _STRIP_RE.sub(" ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


# CJK Unified Ideographs range
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
# Contiguous ASCII alnum run (words, numbers, version codes like GB/T 35273)
_ASCII_RUN_RE = re.compile(r"[a-z0-9]+(?:[/-][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Tokenize text into Chinese bigrams plus ASCII/number tokens.

    Chinese characters are tokenized as character bigrams: "数据出境" ->
    ["数据", "据出", "出境"]. Single CJK characters are kept as unigrams so
    short queries still match. Contiguous ASCII alphanumeric runs (optionally
    separated by ``/`` or ``-``) are kept as single tokens: "GB/T 35273" ->
    ["gb/t 35273"].
    """

    normalized = normalize_text(text)
    tokens: list[str] = []

    # Extract ASCII runs first, then remove them so CJK bigramming is clean
    ascii_runs = _ASCII_RUN_RE.findall(normalized)
    tokens.extend(run.replace(" ", "") for run in ascii_runs if run.strip())

    cjk_text = _ASCII_RUN_RE.sub(" ", normalized)
    cjk_chars = [c for c in cjk_text if _CJK_RE.match(c)]

    if len(cjk_chars) <= 1:
        tokens.extend(cjk_chars)
    else:
        for i in range(len(cjk_chars) - 1):
            tokens.append(cjk_chars[i] + cjk_chars[i + 1])
        # Keep last char as unigram so trailing single CJK is matchable
        tokens.append(cjk_chars[-1])

    return [t for t in tokens if t]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class _ChunkIndex:
    """Pre-tokenized chunk with token sets for fast overlap scoring."""

    chunk: Chunk
    body_tokens: set[str] = field(default_factory=set)
    title_tokens: set[str] = field(default_factory=set)
    label_tokens: set[str] = field(default_factory=set)
    heading_tokens: set[str] = field(default_factory=set)


def _build_index(chunks: list[Chunk]) -> list[_ChunkIndex]:
    index: list[_ChunkIndex] = []
    for chunk in chunks:
        body_tokens = set(tokenize(chunk.text))
        title_tokens = set(tokenize(chunk.title)) if chunk.title else set()
        label_tokens = (
            set(tokenize(chunk.citation_label)) if chunk.citation_label else set()
        )
        heading_tokens = set()
        for h in chunk.heading_path:
            heading_tokens.update(tokenize(h))
        index.append(
            _ChunkIndex(
                chunk=chunk,
                body_tokens=body_tokens,
                title_tokens=title_tokens,
                label_tokens=label_tokens,
                heading_tokens=heading_tokens,
            )
        )
    return index


# Weights for different match locations
_BODY_WEIGHT = 1.0
_TITLE_WEIGHT = 2.5
_LABEL_WEIGHT = 2.0
_HEADING_WEIGHT = 1.5
_PHRASE_WEIGHT = 3.0


def _score_chunk(
    query_tokens: list[str],
    query_token_set: set[str],
    indexed: _ChunkIndex,
    query_text_normalized: str,
    chunk_text_normalized: str,
) -> float:
    """Score a single chunk against a tokenized query."""

    if not query_token_set:
        return 0.0

    # Body overlap: fraction of query tokens present in body
    body_hits = query_token_set & indexed.body_tokens
    body_score = len(body_hits) / len(query_token_set) * _BODY_WEIGHT

    # Title overlap
    title_hits = query_token_set & indexed.title_tokens
    title_score = len(title_hits) / len(query_token_set) * _TITLE_WEIGHT

    # Citation label overlap
    label_hits = query_token_set & indexed.label_tokens
    label_score = len(label_hits) / len(query_token_set) * _LABEL_WEIGHT

    # Heading path overlap
    heading_hits = query_token_set & indexed.heading_tokens
    heading_score = len(heading_hits) / len(query_token_set) * _HEADING_WEIGHT

    # Exact phrase boost: query substring appears in chunk text
    phrase_score = 0.0
    if len(query_text_normalized) >= 4 and query_text_normalized in chunk_text_normalized:
        phrase_score = _PHRASE_WEIGHT

    return body_score + title_score + label_score + heading_score + phrase_score


# ---------------------------------------------------------------------------
# Public retriever
# ---------------------------------------------------------------------------

class KeywordRetriever:
    """Local keyword retriever over pre-loaded corpus chunks.

    Not mathematically full BM25; uses weighted token overlap with field
    boosts. Interface mirrors the future vector adapter so Issue 6 can fuse
    results via RRF without changing call sites.
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self._index = _build_index(chunks)
        # Cache normalized body text for phrase matching
        self._body_normalized = [normalize_text(c.text) for c in chunks]

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
        query_normalized = normalize_text(query)

        if not query_token_set:
            return []

        scored: list[tuple[float, int]] = []
        for idx, indexed in enumerate(self._index):
            score = _score_chunk(
                query_tokens,
                query_token_set,
                indexed,
                query_normalized,
                self._body_normalized[idx],
            )
            if score > 0.0:
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
                    retriever="keyword",
                    citation_role=chunk.citation_role,
                    can_cite_clause=chunk.can_cite_clause,
                    source_url=chunk.source_url,
                    matched_query_type=query_type,
                )
            )
        return hits

    def search_many(
        self,
        queries: Sequence[tuple[str, RetrievalQueryType | None]],
        *,
        top_k: int = 10,
    ) -> list[list[RetrievalHit]]:
        return [
            self.search(query, top_k=top_k, query_type=query_type)
            for query, query_type in queries
        ]


def merge_hits_by_chunk_id(
    hits_per_query: list[list[RetrievalHit]],
    *,
    top_k: int = 10,
) -> list[RetrievalHit]:
    """Merge hits from multiple queries, dedup by chunk_id, keep best score.

    When the same chunk is hit by multiple queries, keep the highest score
    and record the first matched query type. Re-rank the merged set and
    reassign ranks.
    """

    best: dict[str, RetrievalHit] = {}
    for hits in hits_per_query:
        for hit in hits:
            existing = best.get(hit.chunk_id)
            if existing is None or hit.score > existing.score:
                best[hit.chunk_id] = hit

    merged = sorted(best.values(), key=lambda h: (-h.score, h.chunk_id))
    reassigned: list[RetrievalHit] = []
    for rank, hit in enumerate(merged[:top_k]):
        reassigned.append(hit.model_copy(update={"rank": rank}))
    return reassigned
