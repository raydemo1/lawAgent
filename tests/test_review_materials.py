from pathlib import Path

from law_agent.data.schemas import Document, IngestMeta, SourceRecord
from law_agent.review import materials as materials_module
from law_agent.review.materials import material_from_file, material_from_text


def test_material_from_text_marks_pasted_text() -> None:
    material = material_from_text("手机号发送给新加坡服务商。")

    assert material.input_mode == "pasted_text"
    assert material.material_text == "手机号发送给新加坡服务商。"
    assert material.parser == "pasted_text"
    assert material.uploaded_file is None


def test_material_from_file_reads_utf8_text(tmp_path: Path) -> None:
    path = tmp_path / "scenario.txt"
    path.write_text("手机号发送给新加坡服务商。", encoding="utf-8")

    material = material_from_file(path)

    assert material.input_mode == "uploaded_file"
    assert material.material_text == "手机号发送给新加坡服务商。"
    assert material.source_name == "scenario.txt"
    assert material.parser == "plain_text_parser"
    assert material.uploaded_file is not None
    assert material.uploaded_file.filename == "scenario.txt"


def test_material_from_file_routes_pdf_through_normalize(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "upload.pdf"
    path.write_bytes(b"%PDF-1.4")

    def fake_normalize_source(
        record: SourceRecord,
        raw_path: Path,
        *,
        parser="auto",
        parser_output_dir=None,
    ) -> Document:
        assert raw_path == path
        assert parser == "auto"
        assert record.source_site == "user_upload"
        return Document(
            doc_id=record.source_id,
            source_id=record.source_id,
            title=record.title,
            source_url=record.source_url,
            source_site=record.source_site,
            doc_type=record.doc_type,
            raw_format="pdf",
            text="解析后的 PDF 正文",
            ingest_meta=IngestMeta(
                fetched_at="2026-07-06T00:00:00+00:00",
                parser="docling_parser",
                parser_version="test",
            ),
        )

    monkeypatch.setattr(materials_module, "normalize_source", fake_normalize_source)

    material = material_from_file(path)

    assert material.material_text == "解析后的 PDF 正文"
    assert material.parser == "docling_parser"
    assert material.parser_version == "test"
    assert material.uploaded_file is not None
    assert material.uploaded_file.raw_format == "pdf"
