"""Normalize raw source files into Document records."""

from __future__ import annotations

import re
import json
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

from law_agent.data.schemas import Document, DocumentSection, IngestMeta, SourceRecord


HTML_TAG_RE = re.compile(r"<[^>]+>")
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ParserEngine = Literal["auto", "plain", "docx", "docling", "mineru"]
DOC_PARSER_FORMATS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_DOCLING_ARTIFACTS_PATH = Path("artifacts/models/docling")


@dataclass(frozen=True)
class ParsedText:
    text: str
    parser: str
    parser_version: str


def _package_version(*distribution_names: str) -> str:
    for distribution_name in distribution_names:
        try:
            return version(distribution_name)
        except PackageNotFoundError:
            continue
    return "unknown"


def _read_text(
    path: Path,
    parser: ParserEngine = "auto",
    parser_output_dir: Path | None = None,
) -> ParsedText:
    suffix = path.suffix.lower()
    if parser == "docling":
        return _docling_to_text(path)
    if parser == "mineru":
        return _mineru_to_text(path, parser_output_dir=parser_output_dir)
    if parser == "docx":
        if suffix != ".docx":
            raise RuntimeError(f"docx parser cannot parse {suffix or 'extensionless'} files")
        return ParsedText(_docx_to_text(path.read_bytes()), "docx_parser", "0.1.0")
    if parser == "plain":
        return ParsedText(path.read_text(encoding="utf-8", errors="replace"), "plain_text_parser", "0.1.0")
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return ParsedText(_json_to_text(data), "json_parser", "0.1.0")
    if suffix == ".docx":
        return ParsedText(_docx_to_text(path.read_bytes()), "docx_parser", "0.1.0")
    if suffix in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return ParsedText(HTML_TAG_RE.sub("", raw), "html_text_parser", "0.1.0")
    if suffix in DOC_PARSER_FORMATS:
        return _docling_to_text(path)
    return ParsedText(path.read_text(encoding="utf-8", errors="replace"), "plain_text_parser", "0.1.0")


def _docling_to_text(path: Path) -> ParsedText:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "Docling parser requires optional dependency: "
            'install with `pip install -e ".[docling]"` or `uv pip install -U docling`.'
        ) from exc
    artifacts_path = _docling_artifacts_path()
    pipeline_options = PdfPipelineOptions(
        artifacts_path=artifacts_path,
        do_ocr=True,
        ocr_options=RapidOcrOptions(lang=["chinese", "english"], backend="onnxruntime"),
        do_table_structure=_docling_tableformer_available(artifacts_path),
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(path))
    return ParsedText(
        text=result.document.export_to_markdown(),
        parser="docling_parser",
        parser_version=_package_version("docling"),
    )


def _docling_artifacts_path() -> Path | None:
    configured = os.environ.get("LAWAGENT_DOCLING_ARTIFACTS_PATH")
    path = Path(configured) if configured else DEFAULT_DOCLING_ARTIFACTS_PATH
    return path if path.exists() else None


def _docling_tableformer_available(artifacts_path: Path | None) -> bool:
    if artifacts_path is None:
        return False
    tableformer_root = artifacts_path / "docling-project--docling-models" / "model_artifacts" / "tableformer"
    required = [
        tableformer_root / "fast" / "tm_config.json",
        tableformer_root / "fast" / "tableformer_fast.safetensors",
    ]
    return all(path.exists() for path in required)


def _mineru_to_text(path: Path, parser_output_dir: Path | None = None) -> ParsedText:
    executable = shutil.which("mineru")
    if executable is None:
        raise RuntimeError(
            "MinerU parser requires the `mineru` CLI. "
            'Install with `pip install -e ".[mineru]"` or `uv pip install -U "mineru[all]"`.'
        )
    output_dir = parser_output_dir or path.parent / ".parser_artifacts" / "mineru" / path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [executable, "-p", str(path), "-o", str(output_dir), "-b", "pipeline"]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "MinerU parser failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    markdown_path = _find_mineru_markdown(output_dir, path.stem)
    if markdown_path is None:
        raise RuntimeError(f"MinerU parser did not produce a markdown file under {output_dir}")
    return ParsedText(
        text=markdown_path.read_text(encoding="utf-8", errors="replace"),
        parser="mineru_parser",
        parser_version=_package_version("mineru", "magic-pdf"),
    )


def _find_mineru_markdown(output_dir: Path, source_stem: str) -> Path | None:
    markdown_files = [path for path in output_dir.rglob("*.md") if path.is_file()]
    if not markdown_files:
        return None
    matching = [path for path in markdown_files if source_stem.lower() in path.stem.lower()]
    candidates = matching or markdown_files
    return max(candidates, key=lambda path: (path.stat().st_size, path.stat().st_mtime))


def _docx_to_text(content: bytes) -> str:
    if content[:4] != b"PK\x03\x04":
        raise RuntimeError("DOCX parser received a non-zip document")
    with zipfile.ZipFile(BytesIO(content), "r") as archive:
        with archive.open("word/document.xml") as document_xml:
            tree = ET.parse(document_xml)
    body = tree.find(f"{WORD_NS}body")
    if body is None:
        return ""
    blocks: list[str] = []
    for block in body:
        if block.tag == f"{WORD_NS}p":
            text = _paragraph_text(block)
            if text:
                blocks.append(text)
        elif block.tag == f"{WORD_NS}tbl":
            table = _table_to_html(block)
            if table:
                blocks.append(table)
    return "\n".join(blocks)


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t")).strip()


def _table_to_html(table: ET.Element) -> str:
    rows: list[str] = []
    for row in table.findall(f"{WORD_NS}tr"):
        cells: list[str] = []
        for cell in row.findall(f"{WORD_NS}tc"):
            cell_text = "\n".join(
                text for paragraph in cell.findall(f"{WORD_NS}p")
                if (text := _paragraph_text(paragraph))
            )
            cells.append(f"<td>{escape(cell_text)}</td>")
        if cells:
            rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table>{''.join(rows)}</table>" if rows else ""


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


def normalize_source(
    record: SourceRecord,
    raw_path: Path,
    parser: ParserEngine = "auto",
    parser_output_dir: Path | None = None,
) -> Document:
    parsed = _read_text(raw_path, parser=parser, parser_output_dir=parser_output_dir)
    text = parsed.text
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
        issuing_body=record.issuing_body,
        language=record.language,
        applicable_region=record.applicable_region,
        legal_domain=record.legal_domain,
        applicable_subjects=record.applicable_subjects,
        case_no=record.case_no,
        court=record.court,
        trial_instance=record.trial_instance,
        contract_parties=record.contract_parties,
        clause_type=record.clause_type,
        topic_tags=record.topic_tags,
        raw_format=raw_path.suffix.lstrip(".") or record.file_format,
        text=text,
        structure=structure,
        ingest_meta=IngestMeta(
            fetched_at=datetime.now(timezone.utc).isoformat(),
            parser=parsed.parser,
            parser_version=parsed.parser_version,
        ),
    )
