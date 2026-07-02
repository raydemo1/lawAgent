"""Runtime configuration for LawAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
