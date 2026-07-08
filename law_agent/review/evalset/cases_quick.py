"""Quick review evaluation suite.

The quick suite is a small, representative subset of the full golden set for
local smoke checks. It references case IDs from the full suite instead of
duplicating scenario definitions.
"""

from __future__ import annotations

QUICK_CASE_IDS: tuple[str, ...] = (
    "eval_cross_border_001",
    "eval_cross_border_006",
    "eval_standard_contract_003",
    "eval_certification_001",
    "eval_automotive_001",
    "eval_financial_002",
    "eval_shanghai_001",
    "eval_tianjin_001",
    "eval_guangdong_001",
    "eval_tc260_sensitive_001",
    "eval_qna_002",
    "eval_out_of_corpus_001",
)
