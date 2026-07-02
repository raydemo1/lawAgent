"""Chunking pipeline dispatcher."""

from __future__ import annotations

from law_agent.data.chunking.law import chunk_law_document
from law_agent.data.schemas import Chunk, Document


def chunk_document(document: Document) -> list[Chunk]:
    if document.doc_type in {"law", "regulation"}:
        return chunk_law_document(document)
    return chunk_law_document(document)
