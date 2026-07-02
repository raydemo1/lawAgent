"""Cleaning pipeline for normalized documents."""

from __future__ import annotations

from law_agent.data.cleaners.common import clean_text
from law_agent.data.schemas import CleanedDocument, Document, DocumentSection


def clean_document(document: Document) -> CleanedDocument:
    result = clean_text(document.text, title=document.title)
    data = document.model_dump()
    data["text"] = result.text
    data["structure"] = [
        DocumentSection(
            heading_path=section.heading_path,
            text=clean_text(section.text, title=document.title).text,
        ).model_dump()
        for section in document.structure
    ]
    data["cleaning_rule_hits"] = result.rule_hits
    return CleanedDocument.model_validate(data)
