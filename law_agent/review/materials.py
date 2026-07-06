"""Material input normalization for review cases."""

from __future__ import annotations

from pathlib import Path

from law_agent.data.normalize import ParserEngine, normalize_source
from law_agent.data.schemas import SourceRecord
from law_agent.review.schemas import MaterialRecord, UploadedFileMeta


def material_from_text(material_text: str) -> MaterialRecord:
    return MaterialRecord(material_text=material_text)


def material_from_file(path: Path, *, parser: ParserEngine = "auto") -> MaterialRecord:
    if not path.exists():
        raise FileNotFoundError(f"material file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"material path is not a file: {path}")

    resolved = path.resolve()
    raw_format = resolved.suffix.lower().lstrip(".") or "txt"
    record = SourceRecord(
        source_id=f"upload_{resolved.stem}",
        title=resolved.stem,
        source_url=resolved.as_uri(),
        source_site="user_upload",
        doc_type="internal_policy",
        file_format=raw_format,
        include_in_mvp=True,
    )
    document = normalize_source(record, resolved, parser=parser)
    return MaterialRecord(
        input_mode="uploaded_file",
        material_text=document.text,
        source_name=resolved.name,
        parser=document.ingest_meta.parser,
        parser_version=document.ingest_meta.parser_version,
        uploaded_file=UploadedFileMeta(
            filename=resolved.name,
            local_path=str(resolved),
            raw_format=document.raw_format,
        ),
    )
