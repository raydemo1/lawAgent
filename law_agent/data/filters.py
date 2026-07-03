"""Metadata filters for retrieval-ready chunks."""

from __future__ import annotations

from collections.abc import Iterable

from law_agent.data.schemas import Authority, Chunk, ClauseCitationRole, DocType, LawStatus


def _matches_scalar(value: str | None, expected: str | None) -> bool:
    return expected is None or value == expected


def _matches_list(values: list[str], expected: str | Iterable[str] | None) -> bool:
    if expected is None:
        return True
    expected_values = {expected} if isinstance(expected, str) else set(expected)
    return bool(set(values) & expected_values)


def filter_chunks(
    chunks: Iterable[Chunk],
    *,
    doc_type: DocType | None = None,
    authority: Authority | None = None,
    law_status: LawStatus | None = None,
    applicable_region: str | None = None,
    issuing_body: str | None = None,
    legal_domain: str | Iterable[str] | None = None,
    applicable_subjects: str | Iterable[str] | None = None,
    clause_type: str | None = None,
    court: str | None = None,
    trial_instance: str | None = None,
    citation_role: ClauseCitationRole | None = None,
    can_cite_clause: bool | None = None,
) -> list[Chunk]:
    """Filter chunks with the same metadata dimensions used by retrieval services."""

    matched: list[Chunk] = []
    for chunk in chunks:
        if not _matches_scalar(chunk.doc_type, doc_type):
            continue
        if not _matches_scalar(chunk.authority, authority):
            continue
        if not _matches_scalar(chunk.law_status, law_status):
            continue
        if not _matches_scalar(chunk.applicable_region, applicable_region):
            continue
        if not _matches_scalar(chunk.issuing_body, issuing_body):
            continue
        if not _matches_scalar(chunk.clause_type, clause_type):
            continue
        if not _matches_scalar(chunk.court, court):
            continue
        if not _matches_scalar(chunk.trial_instance, trial_instance):
            continue
        if not _matches_scalar(chunk.citation_role, citation_role):
            continue
        if can_cite_clause is not None and chunk.can_cite_clause is not can_cite_clause:
            continue
        if not _matches_list(chunk.legal_domain, legal_domain):
            continue
        if not _matches_list(chunk.applicable_subjects, applicable_subjects):
            continue
        matched.append(chunk)
    return matched


def filter_clause_citable_chunks(chunks: Iterable[Chunk]) -> list[Chunk]:
    """Return evidence chunks allowed to appear as concrete clause citations."""

    return filter_chunks(
        chunks,
        law_status="effective",
        citation_role="primary_legal_basis",
        can_cite_clause=True,
    )
