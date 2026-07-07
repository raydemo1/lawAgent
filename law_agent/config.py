"""Runtime configuration for LawAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


def load_env_file(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE lines into the process environment."""

    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI-compatible chat completion configuration."""

    base_url: str
    api_key: str | None
    model: str
    timeout_seconds: int

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def load_llm_config() -> LLMConfig:
    """Load LLM settings from environment variables."""

    load_env_file()
    timeout = os.getenv("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "60")
    return LLMConfig(
        base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        api_key=os.getenv("OPENAI_COMPATIBLE_API_KEY") or None,
        model=os.getenv("OPENAI_COMPATIBLE_MODEL", "deepseek-v4-flash"),
        timeout_seconds=int(timeout),
    )


def require_llm_config() -> LLMConfig:
    """Load LLM settings and fail if mandatory values are missing."""

    config = load_llm_config()
    if not config.base_url:
        raise RuntimeError("OPENAI_COMPATIBLE_BASE_URL is required")
    if not config.api_key or config.api_key == "sk-your-deepseek-api-key":
        raise RuntimeError("OPENAI_COMPATIBLE_API_KEY is required")
    if not config.model:
        raise RuntimeError("OPENAI_COMPATIBLE_MODEL is required")
    return config


# ---------------------------------------------------------------------------
# Service retrieval configuration (Elasticsearch + pgvector + embeddings)
# ---------------------------------------------------------------------------

EmbeddingProvider = Literal["openai_compatible", "sentence_transformers", "mock"]


@dataclass(frozen=True)
class EmbeddingConfig:
    """Configuration for the embedding provider used by pgvector indexing.

    Kept separate from ``LLMConfig`` because the chat provider (DeepSeek) does
    not expose an embeddings endpoint; embeddings may come from a different
    OpenAI-compatible host, a local sentence-transformers model, or a
    deterministic mock for tests.
    """

    provider: EmbeddingProvider
    base_url: str
    api_key: str | None
    model: str
    dimension: int
    timeout_seconds: int


@dataclass(frozen=True)
class ElasticsearchConfig:
    url: str
    index_name: str
    api_key: str | None
    verify_certs: bool


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str
    table_name: str


@dataclass(frozen=True)
class ServiceConfig:
    """Full service retrieval configuration (ES + pgvector + embeddings)."""

    elasticsearch: ElasticsearchConfig
    postgres: PostgresConfig
    embedding: EmbeddingConfig

    @property
    def enabled(self) -> bool:
        return bool(self.elasticsearch.url and self.postgres.dsn)


def _load_embedding_config() -> EmbeddingConfig:
    load_env_file()
    provider = os.getenv("EMBEDDING_PROVIDER", "openai_compatible")
    if provider not in ("openai_compatible", "sentence_transformers", "mock"):
        raise RuntimeError(
            f"EMBEDDING_PROVIDER={provider!r} is not supported; "
            "use openai_compatible, sentence_transformers, or mock"
        )
    return EmbeddingConfig(
        provider=provider,
        base_url=os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        api_key=os.getenv("EMBEDDING_API_KEY") or None,
        model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        dimension=int(os.getenv("EMBEDDING_DIM", "1536")),
        timeout_seconds=int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
    )


def load_service_config() -> ServiceConfig:
    """Load service retrieval settings from environment variables."""

    load_env_file()
    es = ElasticsearchConfig(
        url=os.getenv("ES_URL", "http://localhost:9200").rstrip("/"),
        index_name=os.getenv("ES_INDEX", os.getenv("ES_INDEX_NAME", "lawagent_chunks")),
        api_key=os.getenv("ES_API_KEY") or None,
        verify_certs=os.getenv("ES_VERIFY_CERTS", "true").lower() == "true",
    )
    pg = PostgresConfig(
        dsn=os.getenv(
            "PG_DSN", "postgresql://lawagent:lawagent@localhost:5432/lawagent"
        ),
        table_name=os.getenv("PG_TABLE", "lawagent_chunks"),
    )
    return ServiceConfig(
        elasticsearch=es,
        postgres=pg,
        embedding=_load_embedding_config(),
    )


def require_service_config() -> ServiceConfig:
    """Load service settings and fail if mandatory values are missing.

    Mirrors the fail-fast semantics of ``require_service_adapters``: service
    retrieval must not silently fall back to local retrieval.
    """

    config = load_service_config()
    if not config.elasticsearch.url:
        raise RuntimeError("ES_URL is required for service retrieval")
    if not config.postgres.dsn:
        raise RuntimeError("PG_DSN is required for service retrieval")
    if config.embedding.provider == "openai_compatible" and not config.embedding.api_key:
        raise RuntimeError(
            "EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=openai_compatible"
        )
    if config.embedding.provider == "sentence_transformers" and not config.embedding.model:
        raise RuntimeError("EMBEDDING_MODEL is required for sentence_transformers provider")
    return config
