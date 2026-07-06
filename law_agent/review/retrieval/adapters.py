"""Service-backed retrieval adapter interfaces.

The concrete adapters are dependency-free wrappers around injectable clients.
This keeps tests and local development independent from running Elasticsearch
or PostgreSQL while preserving the production boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from law_agent.review.schemas import RetrievalHit, RetrievalQueryType


class KeywordSearchAdapter(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_type: RetrievalQueryType | None = None,
    ) -> list[RetrievalHit]:
        ...


class VectorSearchAdapter(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_type: RetrievalQueryType | None = None,
    ) -> list[RetrievalHit]:
        ...


class ElasticsearchKeywordAdapter:
    """Keyword search adapter over an injected Elasticsearch-compatible client."""

    def __init__(self, *, client: Any, index_name: str) -> None:
        self.client = client
        self.index_name = index_name

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_type: RetrievalQueryType | None = None,
    ) -> list[RetrievalHit]:
        body = {
            "size": top_k,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^2",
                        "citation_label^2",
                        "heading_path",
                        "text",
                        "topic_tags",
                        "applicable_subjects",
                    ],
                }
            },
        }
        response = self.client.search(index=self.index_name, body=body)
        raw_hits = response.get("hits", {}).get("hits", [])
        return [
            _hit_from_source(
                raw.get("_source", {}),
                raw.get("_score", 0.0),
                rank,
                "elasticsearch",
                query_type,
            )
            for rank, raw in enumerate(raw_hits[:top_k])
        ]


class PgVectorAdapter:
    """Vector search adapter over an injected pgvector-compatible search function."""

    def __init__(
        self,
        *,
        search_fn: Callable[[list[float], int], list[dict[str, Any]]],
        embed_query: Callable[[str], list[float]],
    ) -> None:
        self.search_fn = search_fn
        self.embed_query = embed_query

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        query_type: RetrievalQueryType | None = None,
    ) -> list[RetrievalHit]:
        vector = self.embed_query(query)
        rows = self.search_fn(vector, top_k)
        return [
            _hit_from_source(row, row.get("score", 0.0), rank, "pgvector", query_type)
            for rank, row in enumerate(rows[:top_k])
        ]


def require_service_adapters(
    *,
    keyword: KeywordSearchAdapter | None,
    vector: VectorSearchAdapter | None,
) -> tuple[KeywordSearchAdapter, VectorSearchAdapter]:
    """Return both service adapters or fail without falling back."""

    if keyword is None and vector is None:
        raise RuntimeError("service retrieval requires Elasticsearch and pgvector adapters")
    if keyword is None:
        raise RuntimeError("service retrieval requires Elasticsearch adapter")
    if vector is None:
        raise RuntimeError("service retrieval requires pgvector adapter")
    return keyword, vector


def _hit_from_source(
    source: dict[str, Any],
    score: float,
    rank: int,
    retriever: str,
    query_type: RetrievalQueryType | None,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=str(source["chunk_id"]),
        doc_id=str(source["doc_id"]),
        source_id=str(source["source_id"]),
        title=str(source["title"]),
        text=str(source["text"]),
        score=float(score),
        rank=rank,
        retriever=retriever,
        citation_role=source.get("citation_role", "interpretation_auxiliary"),
        can_cite_clause=bool(source.get("can_cite_clause", False)),
        source_url=str(source.get("source_url", "")),
        matched_query_type=query_type,
    )
