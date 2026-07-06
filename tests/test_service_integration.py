"""Integration tests for the Elasticsearch + pgvector service retrieval path.

Two layers of tests live here:

* Always-on unit tests for the embedding providers and ``ServiceConfig`` that
  do not require any running service or optional dependency.
* A gated end-to-end test that indexes a fixture corpus into real Elasticsearch
  + pgvector and runs ``run_service_retrieval``. It is skipped unless
  ``LAWAGENT_SERVICE_INTEGRATION=1`` is set AND both services are reachable, so
  the normal test suite never depends on ``elasticsearch``/``psycopg`` being
  installed.
"""

from __future__ import annotations

import dataclasses
import os
import uuid
from pathlib import Path

import pytest

from law_agent.config import load_service_config
from law_agent.llm.embeddings import MockEmbeddings, build_embeddings_provider
from law_agent.review.retrieval.service_backends import (
    healthcheck,
    index_corpus_to_services,
)

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS


# ---------------------------------------------------------------------------
# Always-on: embedding providers and service config (no services required)
# ---------------------------------------------------------------------------

def test_mock_embeddings_are_deterministic_and_dimensioned() -> None:
    embeddings = MockEmbeddings(dimension=8)
    a = embeddings.embed_query("数据出境")
    b = embeddings.embed_query("数据出境")
    c = embeddings.embed_query("different text")

    assert len(a) == 8
    assert a == b  # deterministic for identical input
    assert a != c  # different text -> different vector
    # Mock vectors are L2-normalized.
    norm = sum(v * v for v in a) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_mock_embeddings_batch() -> None:
    embeddings = MockEmbeddings(dimension=4)
    vectors = embeddings.embed_texts(["one", "two", "three"])
    assert len(vectors) == 3
    assert all(len(v) == 4 for v in vectors)


def test_build_embeddings_provider_mock_from_config() -> None:
    config = load_service_config()
    # Default .env ships EMBEDDING_PROVIDER=mock; if a developer overrode it,
    # only assert the mock path here.
    if config.embedding.provider != "mock":
        pytest.skip("EMBEDDING_PROVIDER is not 'mock' in this environment")
    provider = build_embeddings_provider(config.embedding)
    assert isinstance(provider, MockEmbeddings)
    vec = provider.embed_query("query")
    assert len(vec) == config.embedding.dimension


def test_service_config_has_es_pg_and_embedding_sections() -> None:
    config = load_service_config()
    assert config.elasticsearch.url
    assert config.elasticsearch.index_name
    assert config.postgres.dsn
    assert config.postgres.table_name
    assert config.embedding.dimension > 0
    assert config.embedding.provider in ("openai_compatible", "sentence_transformers", "mock")


# ---------------------------------------------------------------------------
# Gated end-to-end: real Elasticsearch + pgvector
# ---------------------------------------------------------------------------

IntegrationMark = pytest.mark.skipif(
    os.getenv("LAWAGENT_SERVICE_INTEGRATION") != "1",
    reason="set LAWAGENT_SERVICE_INTEGRATION=1 to run service integration tests",
)


def _optional_deps_available() -> bool:
    try:
        import elasticsearch  # noqa: F401
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return True


def _test_config(suffix: str):
    """Build a ServiceConfig with isolated index/table names for one test run."""

    cfg = load_service_config()
    return dataclasses.replace(
        cfg,
        elasticsearch=dataclasses.replace(
            cfg.elasticsearch, index_name=f"lawagent_test_{suffix}"
        ),
        postgres=dataclasses.replace(
            cfg.postgres, table_name=f"lawagent_test_{suffix}"
        ),
    )


@IntegrationMark
def test_healthcheck_reaches_both_services() -> None:
    if not _optional_deps_available():
        pytest.skip("elasticsearch/psycopg not installed")
    config = _test_config(uuid.uuid4().hex[:8])
    result = healthcheck(config)
    assert result["elasticsearch"], result
    assert result["postgres"], result


@IntegrationMark
def test_index_corpus_and_run_service_retrieval(tmp_path: Path) -> None:
    if not _optional_deps_available():
        pytest.skip("elasticsearch/psycopg not installed")

    suffix = uuid.uuid4().hex[:8]
    config = _test_config(suffix)

    # Both services must be reachable before we index.
    probe = healthcheck(config)
    assert probe["elasticsearch"], probe
    assert probe["postgres"], probe

    try:
        # 1. Index the fixture corpus into ES + pgvector.
        summary = index_corpus_to_services(config, FIXTURE_CHUNKS[:3])
        assert summary["elasticsearch_docs"] == 3
        assert summary["pgvector_rows"] == 3

        # 2. Create a review case and run service retrieval against the services.
        from law_agent.review.service import create_review_case, run_service_retrieval

        chunks_path = tmp_path / "chunks.jsonl"
        from law_agent.data.io import write_jsonl

        write_jsonl(chunks_path, FIXTURE_CHUNKS[:3])

        create_review_case(
            question="这个场景是否需要数据出境安全评估？",
            material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
            output_dir=tmp_path,
            now=lambda: "2026-07-07T00:00:00+00:00",
            id_factory=lambda prefix: f"{prefix}_svc",
        )

        trace = run_service_retrieval(
            case_id="review_svc",
            chunks_path=chunks_path,
            output_dir=tmp_path,
            top_k=5,
            config=config,
        )

        # Both retrieval routes were served by the real backends.
        retrievers = {hit.retriever for hit in trace.keyword_results + trace.vector_results}
        assert "elasticsearch" in retrievers
        assert "pgvector" in retrievers
        assert len(trace.hybrid_results) > 0
    finally:
        _teardown(config)


def _teardown(config) -> None:
    """Delete the test ES index and drop the test pgvector table."""

    try:
        from law_agent.review.retrieval.service_backends import (
            create_elasticsearch_client,
            create_postgres_connection,
        )

        es = create_elasticsearch_client(config)
        if es.indices.exists(index=config.elasticsearch.index_name):
            es.indices.delete(index=config.elasticsearch.index_name)
        es.close()
    except Exception:  # noqa: BLE001 - teardown is best-effort
        pass
    try:
        from law_agent.review.retrieval.service_backends import (
            create_postgres_connection,
        )

        conn = create_postgres_connection(config)
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {config.postgres.table_name}")
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        pass
