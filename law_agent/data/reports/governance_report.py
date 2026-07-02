"""Markdown reports for data governance outputs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from law_agent.data.io import ensure_parent
from law_agent.data.schemas import Chunk, CleanedDocument, Document, EnrichedDocument


def build_data_governance_report(
    documents: list[Document],
    cleaned: list[CleanedDocument],
    enriched: list[EnrichedDocument],
    chunks: list[Chunk],
    output: Path,
) -> None:
    doc_types = Counter(doc.doc_type for doc in documents)
    authorities = Counter(doc.authority for doc in documents)
    rule_hits: Counter[str] = Counter()
    for doc in cleaned:
        rule_hits.update(doc.cleaning_rule_hits)

    lines = [
        "# 数据治理报告",
        "",
        "## 总览",
        "",
        f"- 规范化文档数：{len(documents)}",
        f"- 清洗文档数：{len(cleaned)}",
        f"- 语义增强文档数：{len(enriched)}",
        f"- Chunk 数：{len(chunks)}",
        "",
        "## 文档类型",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(doc_types.items()))
    lines.extend(["", "## 权威级别", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(authorities.items()))
    lines.extend(["", "## 清洗规则命中", ""])
    if rule_hits:
        lines.extend(f"- {key}: {value}" for key, value in sorted(rule_hits.items()))
    else:
        lines.append("- 暂无命中")
    lines.extend(["", "## 说明", "", "本报告由文件流水线生成，不包含真实原始数据。"])

    ensure_parent(output)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
