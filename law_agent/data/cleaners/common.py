"""Deterministic text cleaning helpers shared by data sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


CONTROL_CHARS_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")
BLANK_LINES_RE = re.compile(r"\n{3,}")
CONTENTS_TITLE_RE = re.compile(r"^(contents|目录|目次|tableofcontents)$", re.IGNORECASE)
STRUCTURAL_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百千万零〇\d]+[章节编]")
DOT_LEADER_TOC_RE = re.compile(r"^\s*.+?[\.·…．]{4,}\s*[IVXLCDM\d]+\s*$", re.IGNORECASE)
WEB_BOILERPLATE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"^Title:\s+",
        r"^URL Source:\s+",
        r"^Markdown Content:\s*$",
        r"^\d{4}年\d{2}月\d{2}日 星期[一二三四五六日天]$",
        r"^\[设为首页\].*\[加入收藏\].*",
        r"^\[搜索\]\(",
        r"^\*?\s*!\[Image\b",
        r"^\[!\[Image\b",
        r"^!\[Image\b",
        r"^\*?\s*### \[?(首 页|首页|时政要闻|网信政务|互动服务|热点专题)",
        r"^\*?\s*\[(首页|时政要闻|网信政务|互动服务|热点专题)\]",
        r"^当前位置：",
        r"^\[\]\(",
        r"^\[【打印】\]",
        r"^关闭$",
        r"^中央网络安全和信息化委员会办公室",
        r"^中华人民共和国国家互联网信息办公室 © 版权所有",
        r"^承办：",
        r"^技术支持",
        r"^京ICP备",
        r"^\[京公网安备",
        r"^Produced By CMS",
        r"^分享到微信",
        r"^打开微信",
        r"^使用“扫一扫”",
        r"^\*\s+######\s*(学习强国|微信|返回顶部)",
        r"^_◆_◆",
    ]
]


@dataclass(frozen=True)
class CleanResult:
    """Text after cleaning plus rule hit counters."""

    text: str
    rule_hits: dict[str, int] = field(default_factory=dict)


def _apply_counted_sub(pattern: re.Pattern[str], replacement: str, text: str) -> tuple[str, int]:
    return pattern.subn(replacement, text)


def _compact_heading(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", value.strip())


def _remove_contents_table(lines: list[str]) -> tuple[list[str], int]:
    """Remove repeated table-of-contents blocks while leaving the body heading."""

    cleaned: list[str] = []
    removed = 0
    index = 0
    while index < len(lines):
        compact = _compact_heading(lines[index])
        if not CONTENTS_TITLE_RE.match(compact):
            cleaned.append(lines[index])
            index += 1
            continue

        cursor = index + 1
        catalog_headings: list[str] = []
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                cursor += 1
                continue
            if catalog_headings and candidate == catalog_headings[0]:
                break
            if STRUCTURAL_HEADING_RE.match(candidate) and "条" not in candidate:
                catalog_headings.append(candidate)
                cursor += 1
                continue
            break

        if catalog_headings and cursor < len(lines) and lines[cursor].strip() == catalog_headings[0]:
            removed += cursor - index
            index = cursor
            continue

        cleaned.append(lines[index])
        index += 1

    return cleaned, removed


def _remove_mechanical_lines(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    cleaned: list[str] = []
    hits = {"dot_leader_toc_lines": 0, "web_boilerplate_lines": 0}

    for line in lines:
        stripped = line.strip()
        if DOT_LEADER_TOC_RE.match(stripped):
            hits["dot_leader_toc_lines"] += 1
            continue
        if any(pattern.search(stripped) for pattern in WEB_BOILERPLATE_PATTERNS):
            hits["web_boilerplate_lines"] += 1
            continue
        cleaned.append(line)

    return cleaned, {key: value for key, value in hits.items() if value}


def clean_text(text: str, *, title: str | None = None) -> CleanResult:
    """Clean mechanical noise without rewriting legal text."""

    hits: dict[str, int] = {}
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text, count = _apply_counted_sub(CONTROL_CHARS_RE, "", text)
    hits["control_chars"] = count

    text, count = _apply_counted_sub(TRAILING_SPACE_RE, "\n", text)
    hits["trailing_space"] = count

    if title:
        lines = text.split("\n")
        cleaned_lines: list[str] = []
        seen_title = False
        duplicate_title_count = 0
        for line in lines:
            if line.strip() == title.strip():
                if seen_title:
                    duplicate_title_count += 1
                    continue
                seen_title = True
            cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)
        hits["duplicate_title"] = duplicate_title_count

    lines, count = _remove_contents_table(text.split("\n"))
    lines, line_hits = _remove_mechanical_lines(lines)
    hits.update(line_hits)
    text = "\n".join(lines)
    hits["contents_table_lines"] = count

    text, count = _apply_counted_sub(BLANK_LINES_RE, "\n\n", text.strip())
    hits["blank_lines"] = count

    return CleanResult(text=text + "\n", rule_hits={key: value for key, value in hits.items() if value})
