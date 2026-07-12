# Current manually labeled evaluation comparison

## Decision

Use the LLM workflow as the resilient fallback, enable embedding rerank as a
health-gated quality layer, and reserve bounded Multi-Agent for high-risk or
multi-issue reviews where supporting-source breadth justifies materially higher
latency and LLM usage. The latest results do not support calling Multi-Agent the
unconditional best mode: it has the broadest optional coverage and fewest
threshold-defined bad cases, while rerank has the best core-law recall, ranking
quality, latency/cost balance, and source diversity.

## Controlled configuration

- 82 full scenarios; 76 contain manually labeled must-have sources
- 28 scenarios contain genuinely optional supporting sources such as guidance,
  templates, Q&A, and national standards
- real service retrieval through Elasticsearch + pgvector
- DeepSeek Flash review; 8 workers
- the LLM and Multi-Agent arms use rerank off; the rerank arm uses embedding
  rerank over the same 50-candidate window
- generated on 2026-07-12 Asia/Hong_Kong

Manual labels replace the previous `can_cite_clause` partition. This makes
Must-have Recall@5, Optional coverage@5, and overall Recall@5 independent and
semantically useful instead of allowing industry or regional sources to inflate
the optional denominator.

## Result

| Metric | LLM | LLM + rerank | Bounded Multi-Agent |
|---|---:|---:|---:|
| Recall@5 | 0.8432 | 0.8586 | **0.8607** |
| Must-have Recall@5 | 0.8706 | **0.8925** | 0.8794 |
| Optional coverage@5 | 0.6964 | 0.6607 | **0.7857** |
| MRR@10 | 0.8553 | **0.8816** | 0.8575 |
| Candidate Recall@50 | 0.9200 | 0.9200 | **0.9507** |
| Bad cases (`Recall@5 < 0.5`) | 4 | 6 | **2** |
| Abstention accuracy | 1.0000 | 1.0000 | 1.0000 |
| Mean duplicate sources@10 | **0.0000** | **0.0000** | 0.2073 |
| Mean total latency | **10.37 s** | 10.40 s | 19.46 s |
| Mean retrieval latency | **1.55 s** | 2.11 s | 1.69 s |
| Total LLM calls | **84** | **84** | 215 |
| Total retries | **0** | **0** | 6 |

## How to read the trade-off

Embedding rerank improves Must-have Recall@5 by 0.0219, overall Recall@5 by
0.0154, and MRR@10 by 0.0263 over the LLM baseline. Candidate Recall@50 remains
0.9200, confirming that the gain comes from reordering the existing candidate
pool rather than broader first-stage retrieval.

The improvement is uneven. Rerank improves core-law placement in cases such as
`eval_automotive_007`, `eval_cross_border_002`, and `eval_fujian_001`, but
regresses `eval_boundary_002`, `eval_conflict_001`, and the optional source in
`eval_cross_border_003`. Optional coverage falls by exactly 1/28, so this run
does not support the broader claim that rerank systematically removes many
supporting sources.

Bad-case count is a threshold metric, not an aggregate quality score. A case
crossing from 0.6667 to 0.3333 immediately becomes bad, while a case improving
from 0.5 to 1.0 was never counted as bad. This explains why rerank can improve
all three continuous ranking metrics while bad cases increase from four to six.

Multi-Agent improves Optional coverage@5 by 0.0893 over the LLM baseline and
reduces bad cases to two. In exchange, it uses 2.56x as many LLM calls, takes
about 1.88x the mean latency, has lower Must-have Recall@5 and MRR@10 than
rerank, and introduces duplicate sources. Its value is deeper issue coverage
and targeted recovery, not a free aggregate retrieval win.

## Production and interview positioning

- **LLM:** resilient fast fallback with no rerank-service dependency.
- **LLM + rerank:** preferred quality/cost mode when the embedding/rerank
  service is healthy; timeouts must fall back to the original fused order.
- **Bounded Multi-Agent:** deep-review mode for compound, high-risk, or
  multi-jurisdiction cases where optional supporting coverage matters.

For interviews, lead with `Must-have Recall@5 = 0.8925` and `MRR@10 = 0.8816`
for the rerank arm, then explain the case-level regressions and operational
timeout risk. Present Multi-Agent as an evidence-backed quality/cost trade-off,
not as proof that adding more agents always wins.

## Artifacts

- `data/review_runs/eval_manual_labels_llm_rerank_off_full.json`
- `data/review_runs/eval_manual_labels_llm_rerank_on_full.json`
- `data/review_runs/eval_manual_labels_multi_agent_full.json`

Earlier phase reports remain historical records of workflow evolution and use
their original metric definitions. They must not be compared directly with the
manually labeled table above.
