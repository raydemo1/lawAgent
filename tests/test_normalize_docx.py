import zipfile
from io import BytesIO

from law_agent.data.normalize import _docx_to_text


def _make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_docx_to_text_extracts_paragraphs() -> None:
    content = _make_docx(["中华人民共和国个人信息保护法", "第一条 为了保护个人信息权益。"])

    text = _docx_to_text(content)

    assert text == "中华人民共和国个人信息保护法\n第一条 为了保护个人信息权益。"
