"""Deterministic text cleaning helpers shared by data sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


CONTROL_CHARS_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")
BLANK_LINES_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class CleanResult:
    """Text after cleaning plus rule hit counters."""

    text: str
    rule_hits: dict[str, int] = field(default_factory=dict)


def _apply_counted_sub(pattern: re.Pattern[str], replacement: str, text: str) -> tuple[str, int]:
    return pattern.subn(replacement, text)


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

    text, count = _apply_counted_sub(BLANK_LINES_RE, "\n\n", text.strip())
    hits["blank_lines"] = count

    return CleanResult(text=text + "\n", rule_hits={key: value for key, value in hits.items() if value})

