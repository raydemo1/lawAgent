"""Client for the National Laws and Regulations Database."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from law_agent.data.schemas import Authority, DocType, LawStatus, SourceRecord

BASE_URL = "https://flk.npc.gov.cn"
SEARCH_URL = f"{BASE_URL}/law-search/search/list"
DETAIL_URL = f"{BASE_URL}/law-search/search/flfgDetails"
DOWNLOAD_URL = f"{BASE_URL}/law-search/download/pc"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LawAgent/0.1",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE_URL}/",
}

DATA_COMPLIANCE_TERMS = [
    "个人信息保护",
    "数据安全",
    "网络安全",
    "数据出境",
    "重要数据",
    "关键信息基础设施",
    "网络数据",
]

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    return TAG_RE.sub("", value).strip()


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, params: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_binary(url: str, timeout_seconds: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read()
    if "text/html" in content_type.lower() and len(data) < 5000:
        raise RuntimeError("FLK download returned HTML instead of a document")
    return data


def _map_doc_type(flxz: str | None) -> DocType:
    value = flxz or ""
    if "法律" in value:
        return "law"
    if "法规" in value or "条例" in value:
        return "regulation"
    if "解释" in value:
        return "guideline"
    return "policy"


def _map_authority(flxz: str | None) -> Authority:
    value = flxz or ""
    if "法律" in value:
        return "national_law"
    if "行政法规" in value:
        return "administrative_regulation"
    if "司法解释" in value:
        return "judicial_interpretation"
    if "地方" in value:
        return "local_regulation"
    return "unknown"


def _map_status(sxx: Any) -> LawStatus:
    return {3: "effective", 2: "amended", 1: "repealed"}.get(sxx, "unknown")


def bbbs_from_source_id(source_id: str) -> str:
    prefix = "flk_npc_"
    if not source_id.startswith(prefix):
        raise ValueError(f"Not an FLK source_id: {source_id}")
    return source_id[len(prefix) :]


def get_download_url(bbbs: str, fmt: str = "docx", *, timeout_seconds: int = 30) -> str:
    """Resolve an FLK document to its public signed file URL."""

    response = _get_json(
        DOWNLOAD_URL,
        {"format": fmt, "bbbs": bbbs},
        timeout_seconds,
    )
    if response.get("code") != 200:
        raise RuntimeError(f"FLK download API failed: {response.get('msg') or response}")
    url = (response.get("data") or {}).get("url")
    if not url:
        raise RuntimeError(f"FLK download API returned no URL for format={fmt}, bbbs={bbbs}")
    return str(url)


def download_document(bbbs: str, fmt: str = "docx", *, timeout_seconds: int = 30) -> bytes:
    """Download the official FLK file through the documented download endpoint."""

    url = get_download_url(bbbs, fmt, timeout_seconds=timeout_seconds)
    return _download_binary(url, timeout_seconds)


def search_sources(
    terms: list[str] | None = None,
    *,
    page_size: int = 10,
    timeout_seconds: int = 30,
) -> list[SourceRecord]:
    """Search FLK for candidate data-compliance sources."""

    records: dict[str, SourceRecord] = {}
    for term in terms or DATA_COMPLIANCE_TERMS:
        payload = {
            "searchContent": term,
            "searchType": 2,
            "searchRange": 1,
            "pageNum": 1,
            "pageSize": page_size,
        }
        response = _post_json(SEARCH_URL, payload, timeout_seconds)
        if response.get("code") != 200:
            raise RuntimeError(f"FLK search failed for {term}: {response}")
        for row in response.get("rows", []):
            bbbs = row.get("bbbs")
            title = strip_html(str(row.get("title", "")))
            if not bbbs or not title:
                continue
            if term not in title and term not in str(row.get("xgzlHighLight") or ""):
                continue
            records[bbbs] = SourceRecord(
                source_id=f"flk_npc_{bbbs}",
                title=title,
                source_url=f"{DETAIL_URL}?bbbs={bbbs}",
                download_url=f"{DOWNLOAD_URL}?format=docx&bbbs={bbbs}",
                source_site="flk.npc.gov.cn",
                doc_type=_map_doc_type(row.get("flxz")),
                authority=_map_authority(row.get("flxz")),
                law_status=_map_status(row.get("sxx")),
                publish_date=row.get("gbrq"),
                effective_date=row.get("sxrq"),
                topic_tags=[term, "数据合规"],
                language="zh",
                file_format="docx",
                include_in_mvp=True,
                review_note="FLK official download candidate; requires human confirmation",
            )
    return list(records.values())
