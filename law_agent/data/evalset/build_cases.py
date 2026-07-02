"""Build small candidate evaluation sets from chunks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from law_agent.data.schemas import Chunk


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    question: str
    expected_doc_id: str
    expected_chunk_id: str
    tags: list[str]


def build_retrieval_cases(chunks: list[Chunk], limit: int = 60) -> list[RetrievalCase]:
    cases: list[RetrievalCase] = []
    for chunk in chunks:
        if chunk.article_no:
            question = f"{chunk.title}{chunk.article_no}规定了什么？"
        else:
            question = f"{chunk.title}的核心内容是什么？"
        cases.append(
            RetrievalCase(
                case_id=f"retrieval_{len(cases):04d}",
                question=question,
                expected_doc_id=chunk.doc_id,
                expected_chunk_id=chunk.chunk_id,
                tags=chunk.topic_tags,
            )
        )
        if len(cases) >= limit:
            break
    return cases
