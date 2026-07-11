# Optimized Multi-Agent vs Current LLM

## Decision

Keep both lanes behind the same `ReviewCase -> ReviewResult` interface. Use the
current LLM workflow as the default fast lane and route compound cross-border,
sensitive-data, regional/industry, or explicit path-conflict cases to the
bounded Multi-Agent workflow. The optimized Multi-Agent workflow improves
reliability and selected difficult cases, but the full-suite Recall lift is not
large or stable enough to justify making it the unconditional default.

## Controlled configuration

- 82 full scenarios; 76 have expected retrieval sources
- frozen facts and initial queries from
  `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`
- service retrieval: Elasticsearch + pgvector, 1,728 rows each
- rerank off; 8 workers
- corrected retrieval denominator and unique fused chunk Candidate Recall@50
- generated on 2026-07-12 Asia/Hong_Kong (run timestamps are stored in UTC)

## Result

| Metric | Current LLM | Optimized Multi-Agent | Delta |
|---|---:|---:|---:|
| Source-bearing Recall@5 | 0.8103 | 0.8311 | +0.0208 |
| MRR@10 | 0.8509 | 0.8706 | +0.0197 |
| Candidate Recall@50 | 0.8980 | 0.9594 | +0.0614 |
| Abstention accuracy | 0.9878 | 1.0000 | +0.0122 |
| Clean success | 0.9878 | 0.9512 | -0.0366 |
| Degraded success | 0.0000 | 0.0488 | +0.0488 |
| Hard failure | 0.0122 | 0.0000 | -0.0122 |
| LLM calls | 88 | 230 | +142 |
| Retries | 5 | 20 | +15 |
| Mean latency | 42.32 s | 86.05 s | +43.73 s |
| p95 latency | 61.37 s | 153.43 s | +92.06 s |
| Bad cases | 6 | 2 | -4 |

## Paired uncertainty

Across the 76 source-bearing cases, Multi-Agent improves Recall@5 on 9 cases,
regresses on 6, and ties on 61. The paired mean delta is `+0.0208`; a seeded
10,000-sample case bootstrap gives a 95% interval of
`[-0.0241, +0.0691]`. One run therefore does not establish a stable aggregate
retrieval advantage.

## What the optimization established

- Conditional Analyst routing ran on 42/82 cases instead of every case.
- Multi-Agent calls fell from the Phase 4 value of 341 to 230.
- Candidate pool semantics now include global, issue-specific, second-pass,
  and targeted candidates; Final Recall no longer exceeds Candidate Recall.
- Revision patch-shape errors are normalized deterministically, and patch
  application failures degrade by retaining the original valid result instead
  of terminating the suite.
- A 23-case ranking-focused diagnostic slice improved mean Recall@5 from
  0.5942 to 0.7536 (9 improved, 0 regressed), but the full-suite result remains
  affected by stochastic Analyst, self-check, Critic, and retrieval behavior.

## Production recommendation

Use the fast LLM lane for ordinary single-path cases. Use bounded Multi-Agent
for compound cases where the extra issue decomposition, targeted retrieval,
and failure resilience justify roughly double mean latency. Do not continue
tuning source weights or case-specific queries against the repeatedly inspected
82-case development suite.

Raw and detailed reports:

- `artifacts/review_runs/eval_optimized_final_full.json`
- `docs/evaluation/optimized-final-full.md`
- `artifacts/review_runs/eval_llm_current_full.json`
- `docs/evaluation/llm-current-full.md`
