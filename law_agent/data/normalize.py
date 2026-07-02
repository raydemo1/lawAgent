"""Normalize raw source files into Document records."""

from __future__ import annotations

import re
import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from law_agent.data.schemas import Document, DocumentSection, IngestMeta, SourceRecord


HTML_TAG_RE = re.compile(r"<[^>]+>")


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return _json_to_text(data)
    if path.suffix.lower() == ".docx":
        return _docx_to_text(path.read_bytes())
    if path.suffix.lower() in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return HTML_TAG_RE.sub("", raw)
    return path.read_text(encoding="utf-8", errors="replace")


def _docx_to_text(content: bytes) -> str:
    if content[:4] != b"PK\x03\x04":
        raise RuntimeError("DOCX parser received a non-zip document")
    with zipfile.ZipFile(BytesIO(content), "r") as archive:
        with archive.open("word/document.xml") as document_xml:
            tree = ET.parse(document_xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in tree.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _walk_content(node: object, path: list[str] | None = None) -> list[str]:
    path = path or []
    if not isinstance(node, dict):
        return []
    title = str(node.get("title") or "").strip()
    next_path = path + ([title] if title else [])
    lines: list[str] = []
    children = node.get("children")
    if title:
        lines.append(" / ".join(next_path))
    if isinstance(children, list):
        for child in children:
            lines.extend(_walk_content(child, next_path))
    elif isinstance(children, str) and children.strip():
        lines.append(children.strip())
    return lines


def _json_to_text(data: object) -> str:
    if not isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return json.dumps(data, ensure_ascii=False)
    lines = [
        str(payload.get("title") or "").strip(),
        f"制定机关：{payload.get('zdjgName') or ''}".strip(),
        f"公布日期：{payload.get('gbrq') or ''}".strip(),
        f"施行日期：{payload.get('sxrq') or ''}".strip(),
        f"法规类型：{payload.get('flxz') or ''}".strip(),
    ]
    lines.extend(_walk_content(payload.get("content")))
    return "\n".join(line for line in lines if line.strip())


def normalize_source(record: SourceRecord, raw_path: Path) -> Document:
    text = _read_text(raw_path)
    structure = [DocumentSection(heading_path=[record.title], text=text.strip())]
    return Document(
        doc_id=record.source_id,
        source_id=record.source_id,
        title=record.title,
        source_url=record.source_url,
        download_url=record.download_url,
        source_site=record.source_site,
        doc_type=record.doc_type,
        authority=record.authority,
        law_status=record.law_status,
        publish_date=record.publish_date,
        effective_date=record.effective_date,
        language=record.language,
        jurisdiction="CN" if record.language == "zh" else "unknown",
        topic_tags=record.topic_tags,
        raw_format=raw_path.suffix.lstrip(".") or record.file_format,
        text=text,
        structure=structure,
        ingest_meta=IngestMeta(
            fetched_at=datetime.now(timezone.utc).isoformat(),
            parser="docx_parser" if raw_path.suffix.lower() == ".docx" else "plain_text_parser",
            parser_version="0.1.0",
        ),
    )
