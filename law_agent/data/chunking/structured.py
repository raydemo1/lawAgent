"""Structure-aware chunking for non-article legal materials."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from law_agent.data.citation_policy import can_cite_clause, citation_role_for_source
from law_agent.data.schemas import Chunk, Document

GENERIC_HARD_LIMIT_CHARS = 1200
GENERIC_SOFT_LIMIT_CHARS = 900
MIN_GENERIC_CHUNK_CHARS = 120

MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMERIC_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,4})[\.、]?\s+(.{1,80})$")
QUESTION_HEADING_RE = re.compile(r"^(?:问|Q|问题)\s*[:：].+")
TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
ROW_RE = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
DECORATIVE_TABLE_LINE_RE = re.compile(r"^\|[-:\s]+\|?$")


@dataclass(frozen=True)
class StructuredUnit:
    text: str
    heading_path: list[str]
    citation_label: str | None = None


def chunk_structured_document(document: Document) -> list[Chunk]:
    """Create retrieval chunks for guides, Q&A, standards, and table-heavy lists."""

    if document.doc_type == "faq":
        units = split_faq_units(document.text)
    elif _looks_table_heavy(document.text):
        units = split_table_aware_units(document.text)
    else:
        units = split_heading_units(document.text)

    if not units:
        units = split_plain_units(document.text, [])

    return _chunks_from_units(document, units)


def split_faq_units(text: str) -> list[StructuredUnit]:
    units: list[StructuredUnit] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_lines
        if current_lines:
            heading = current_heading or "问答"
            units.extend(_split_long_text("\n".join(current_lines), [heading], heading))
        current_heading = None
        current_lines = []

    for raw_line in _meaningful_lines(text):
        line = _clean_inline_markup(_strip_markdown_heading(raw_line))
        if QUESTION_HEADING_RE.match(line):
            flush()
            current_heading = line[:120]
            current_lines = [line]
            continue
        if current_lines:
            current_lines.append(line)

    flush()
    if units:
        return units
    return split_heading_units(text)


def split_table_aware_units(text: str) -> list[StructuredUnit]:
    units: list[StructuredUnit] = []
    cursor = 0
    table_index = 0
    heading_path: list[str] = []

    for match in TABLE_RE.finditer(text):
        before = text[cursor:match.start()]
        before_units = split_heading_units(before)
        if before_units:
            units.extend(before_units)
            heading_path = before_units[-1].heading_path
        else:
            heading_path = _last_context_heading(before, heading_path)

        table_index += 1
        table_heading = [*heading_path, f"表格{table_index}"]
        units.extend(split_table_units(match.group(0), table_heading))
        cursor = match.end()

    tail_units = split_heading_units(text[cursor:])
    units.extend(tail_units)
    return _merge_tiny_units(units)


def split_table_units(table_html: str, heading_path: list[str]) -> list[StructuredUnit]:
    rows = [_table_row_text(row.group(0)) for row in ROW_RE.finditer(table_html)]
    rows = [row for row in rows if row]
    if not rows:
        return split_plain_units(_strip_tags(table_html), heading_path)

    units: list[StructuredUnit] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            units.append(
                StructuredUnit(
                    text="\n".join(current),
                    heading_path=heading_path,
                    citation_label=" ".join(heading_path),
                )
            )
            current = []

    for row in rows:
        if current and len("\n".join([*current, row])) > GENERIC_HARD_LIMIT_CHARS:
            flush()
        if len(row) > GENERIC_HARD_LIMIT_CHARS:
            flush()
            units.extend(_split_long_text(row, heading_path, " ".join(heading_path)))
            continue
        current.append(row)
    flush()
    return units


def split_heading_units(text: str) -> list[StructuredUnit]:
    units: list[StructuredUnit] = []
    heading_stack: list[str] = []
    current_heading: str | None = None
    current_path: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_heading, current_path, current_lines
        if current_lines:
            if not (len(current_lines) == 1 and current_heading and current_lines[0].strip() == current_heading):
                citation = " ".join(current_path) if current_path else None
                units.extend(_split_long_text("\n".join(current_lines), current_path, citation))
        current_heading = None
        current_path = []
        current_lines = []

    for raw_line in _meaningful_lines(text):
        if DECORATIVE_TABLE_LINE_RE.match(raw_line.strip()):
            continue
        heading = _heading_from_line(raw_line)
        if heading is not None:
            flush()
            level, value = heading
            if level <= len(heading_stack):
                heading_stack = heading_stack[: level - 1]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(value)
            current_heading = value
            current_path = [item for item in heading_stack if item]
            current_lines = [value]
            continue
        if current_heading is None:
            current_path = []
        current_lines.append(_strip_markdown_heading(raw_line))

    flush()
    return _merge_tiny_units(units)


def split_plain_units(text: str, heading_path: list[str]) -> list[StructuredUnit]:
    return _split_long_text("\n".join(_meaningful_lines(_strip_tags(text))), heading_path, None)


def _chunks_from_units(document: Document, units: list[StructuredUnit]) -> list[Chunk]:
    chunks: list[Chunk] = []
    citation_role = citation_role_for_source(document.source_id)
    clause_citable = can_cite_clause(document.source_id)

    for index, unit in enumerate(unit for unit in units if unit.text.strip()):
        heading_path = [document.title, *unit.heading_path]
        citation_label = unit.citation_label
        if citation_label:
            citation_label = f"{document.title} {citation_label}"
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}:{index:04d}",
                doc_id=document.doc_id,
                source_id=document.source_id,
                title=document.title,
                text=unit.text.strip(),
                chunk_index=index,
                doc_type=document.doc_type,
                heading_path=heading_path,
                citation_label=citation_label,
                citation_role=citation_role,
                can_cite_clause=clause_citable,
                prev_chunk_id=f"{document.doc_id}:{index - 1:04d}" if index > 0 else None,
                next_chunk_id=f"{document.doc_id}:{index + 1:04d}" if index + 1 < len(units) else None,
                authority=document.authority,
                law_status=document.law_status,
                publish_date=document.publish_date,
                effective_date=document.effective_date,
                source_url=document.source_url,
                applicable_region=document.applicable_region,
                issuing_body=document.issuing_body,
                legal_domain=document.legal_domain,
                applicable_subjects=document.applicable_subjects,
                case_no=document.case_no,
                court=document.court,
                trial_instance=document.trial_instance,
                contract_parties=document.contract_parties,
                clause_type=document.clause_type,
                topic_tags=document.topic_tags,
                char_count=len(unit.text.strip()),
            )
        )
    for index, chunk in enumerate(chunks):
        chunks[index] = chunk.model_copy(
            update={
                "prev_chunk_id": chunks[index - 1].chunk_id if index > 0 else None,
                "next_chunk_id": chunks[index + 1].chunk_id if index + 1 < len(chunks) else None,
            }
        )
    return chunks


def _meaningful_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in {"<!-- image -->", "<!--image-->"}:
            continue
        lines.append(stripped)
    return lines


def _looks_table_heavy(text: str) -> bool:
    return "<table" in text.lower() or text.count("<tr") >= 3


def _heading_from_line(line: str) -> tuple[int, str] | None:
    stripped = line.strip()
    markdown = MARKDOWN_HEADING_RE.match(stripped)
    if markdown:
        return min(len(markdown.group(1)), 6), markdown.group(2).strip()
    numeric = NUMERIC_HEADING_RE.match(stripped)
    if numeric and "。" not in numeric.group(2):
        level = numeric.group(1).count(".") + 1
        return min(level, 6), f"{numeric.group(1)} {numeric.group(2).strip()}"
    if re.match(r"^[一二三四五六七八九十]+、.{1,80}$", stripped):
        return 1, stripped
    if re.match(r"^（[一二三四五六七八九十]+）.{1,80}$", stripped):
        return 2, stripped
    if stripped.startswith("行业领域") and len(stripped) <= 80:
        return 1, stripped
    return None


def _strip_markdown_heading(line: str) -> str:
    markdown = MARKDOWN_HEADING_RE.match(line.strip())
    return markdown.group(2).strip() if markdown else line.strip()


def _clean_inline_markup(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\*{1,3}(.+?)\*{1,3}$", r"\1", line)
    line = re.sub(r"\*\*(问|答|Q|A|问题)\s*[:：]\*\*", r"\1：", line)
    return line.strip()


def _last_context_heading(text: str, fallback: list[str]) -> list[str]:
    path = fallback
    for line in _meaningful_lines(text):
        heading = _heading_from_line(line)
        if heading:
            path = [heading[1]]
    return path


def _table_row_text(row_html: str) -> str:
    cells = [_strip_tags(cell.group(1)) for cell in CELL_RE.finditer(row_html)]
    cells = [cell for cell in cells if cell]
    return " | ".join(cells)


def _strip_tags(value: str) -> str:
    text = TAG_RE.sub(" ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _split_long_text(text: str, heading_path: list[str], citation_label: str | None) -> list[StructuredUnit]:
    lines = _meaningful_lines(text)
    if not lines:
        return []

    units: list[StructuredUnit] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            units.append(
                StructuredUnit(
                    text="\n".join(current),
                    heading_path=heading_path,
                    citation_label=citation_label,
                )
            )
            current = []

    for line in lines:
        if current and len("\n".join([*current, line])) > GENERIC_HARD_LIMIT_CHARS:
            flush()
        if len(line) > GENERIC_HARD_LIMIT_CHARS:
            for start in range(0, len(line), GENERIC_SOFT_LIMIT_CHARS):
                units.append(
                    StructuredUnit(
                        text=line[start : start + GENERIC_SOFT_LIMIT_CHARS],
                        heading_path=heading_path,
                        citation_label=citation_label,
                    )
                )
            continue
        current.append(line)
    flush()
    return units


def _merge_tiny_units(units: list[StructuredUnit]) -> list[StructuredUnit]:
    merged: list[StructuredUnit] = []
    for unit in units:
        if (
            merged
            and len(unit.text) < MIN_GENERIC_CHUNK_CHARS
            and merged[-1].heading_path == unit.heading_path
            and len(merged[-1].text) + len(unit.text) <= GENERIC_HARD_LIMIT_CHARS
        ):
            previous = merged[-1]
            merged[-1] = StructuredUnit(
                text=f"{previous.text}\n{unit.text}",
                heading_path=previous.heading_path,
                citation_label=previous.citation_label,
            )
        else:
            merged.append(unit)
    return merged
