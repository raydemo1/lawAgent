"""Generic source fetching helpers."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from law_agent.data.io import ensure_parent
from law_agent.data.schemas import SourceRecord


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    path: Path
    ok: bool
    sha256: str | None = None
    error: str | None = None


def _safe_suffix(record: SourceRecord) -> str:
    if record.file_format:
        normalized = record.file_format.lower().lstrip(".")
        if normalized in {"html", "htm", "txt", "json", "docx", "pdf"}:
            return f".{normalized}"
    suffix = Path(record.download_url or record.source_url).suffix.lower()
    if suffix in {".html", ".htm", ".txt", ".json", ".docx", ".pdf"}:
        return suffix
    return ".txt"


def _download(url: str, timeout_seconds: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "LawAgent/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _download_record(record: SourceRecord, timeout_seconds: int) -> bytes:
    if record.source_site == "flk.npc.gov.cn" and record.file_format.lower() in {"docx", "pdf"}:
        from law_agent.data.fetchers.flk_npc import bbbs_from_source_id, download_document

        return download_document(
            bbbs_from_source_id(record.source_id),
            record.file_format.lower(),
            timeout_seconds=timeout_seconds,
        )
    return _download(record.download_url or record.source_url, timeout_seconds)


def fetch_source(
    record: SourceRecord,
    output_dir: Path,
    *,
    timeout_seconds: int = 30,
    allow_network: bool = True,
) -> FetchResult:
    """Fetch one source. Failure is explicit; there is no sample fallback."""

    suffix = _safe_suffix(record)
    path = output_dir / record.source_site.replace(".", "_") / f"{record.source_id}{suffix}"
    ensure_parent(path)
    data: bytes | None = None
    error: str | None = None

    if allow_network:
        try:
            data = _download_record(record, timeout_seconds)
        except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
            error = str(exc)

    if data is None:
        return FetchResult(source_id=record.source_id, path=path, ok=False, error=error)

    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "source_id": record.source_id,
                "source_url": record.source_url,
                "download_url": record.download_url,
                "sha256": digest,
                "bytes": len(data),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return FetchResult(source_id=record.source_id, path=path, ok=True, sha256=digest)
