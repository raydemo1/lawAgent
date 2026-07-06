"""DeepSeek-backed structured LLM nodes for review workflows."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from law_agent.llm.openai_compatible import ChatMessage, OpenAICompatibleClient

ModelT = TypeVar("ModelT", bound=BaseModel)


class ReviewWorkflowFailed(RuntimeError):
    """Raised when a review workflow node exhausts retries."""

    def __init__(
        self,
        *,
        failed_node: str,
        reason: str,
        message: str,
        attempts: int,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_node = failed_node
        self.reason = reason
        self.message = message
        self.attempts = attempts
        self.trace_id = trace_id

    def to_response(self) -> dict[str, object]:
        return {
            "status": "review_failed",
            "failed_node": self.failed_node,
            "reason": self.reason,
            "message": self.message,
            "attempts": self.attempts,
            "trace_id": self.trace_id,
        }


def max_retries_for_node(node_name: str, default: int = 2) -> int:
    """Return configured retry count for a workflow node."""

    env_by_node = {
        "fact_extraction": "LAWAGENT_LLM_FACT_RETRIES",
        "query_planning": "LAWAGENT_LLM_QUERY_RETRIES",
        "evidence_check": "LAWAGENT_LLM_EVIDENCE_CHECK_RETRIES",
        "result_generation": "LAWAGENT_LLM_RESULT_RETRIES",
    }
    raw = os.getenv(env_by_node.get(node_name, ""), os.getenv("LAWAGENT_LLM_MAX_RETRIES"))
    if raw is None:
        return default
    try:
        retries = int(raw)
    except ValueError:
        return default
    return max(retries, 0)


class StructuredLLMNode(Generic[ModelT]):
    """Run one DeepSeek JSON node with strict Pydantic validation and retry."""

    def __init__(
        self,
        *,
        node_name: str,
        output_model: type[ModelT],
        client: OpenAICompatibleClient,
        max_retries: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.node_name = node_name
        self.output_model = output_model
        self.client = client
        self.max_retries = (
            max_retries if max_retries is not None else max_retries_for_node(node_name)
        )
        self.trace_id = trace_id

    def run(self, messages: Sequence[ChatMessage]) -> ModelT:
        attempts_allowed = self.max_retries + 1
        last_reason = "llm_api_error"
        last_message = f"{self.node_name} failed"

        for attempt in range(1, attempts_allowed + 1):
            try:
                raw = self.client.chat_json(list(messages))
                return self.output_model.model_validate(raw, strict=True)
            except ValidationError as exc:
                last_reason = "pydantic_validation_failed"
                last_message = (
                    f"{self.node_name} output did not match the required JSON schema"
                )
                if attempt == attempts_allowed:
                    raise ReviewWorkflowFailed(
                        failed_node=self.node_name,
                        reason=last_reason,
                        message=last_message,
                        attempts=attempt,
                        trace_id=self.trace_id,
                    ) from exc
            except Exception as exc:
                last_reason = "llm_api_error"
                last_message = f"{self.node_name} LLM call failed"
                if attempt == attempts_allowed:
                    raise ReviewWorkflowFailed(
                        failed_node=self.node_name,
                        reason=last_reason,
                        message=last_message,
                        attempts=attempt,
                        trace_id=self.trace_id,
                    ) from exc

        raise ReviewWorkflowFailed(
            failed_node=self.node_name,
            reason=last_reason,
            message=last_message,
            attempts=attempts_allowed,
            trace_id=self.trace_id,
        )
