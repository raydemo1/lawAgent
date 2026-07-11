# LawAgent Custom Evaluation Report

- Generated: `2026-07-11T05:19:21.488956+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `custom`

## Run configuration

- retrieval_mode: `service`
- review_mode: `multi_agent`
- rerank_mode: `off`
- max_workers: `5`
- top_k: `10`
- eval_inputs: `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`
- scope: `five original workflow failures after fallback patch`

## retrieval=service,review=multi_agent

| Metric | Value |
|---|---:|
| Total cases | 5 |
| Recall@3 | 1.0000 |
| Recall@5 | 1.0000 |
| MRR@10 | 0.8000 |
| Candidate Recall@50 | 1.0000 |
| Abstention accuracy | 1.0000 |
| Second retrieval trigger rate | 0.4000 |
| Citation violations | 0 |
| Bad cases | 0 |
| Mean total latency (ms) | 145308.00 |
| Mean retrieval latency (ms) | 28442.20 |
| Total LLM calls | 31 |
| Total retries | 10 |
| Workflow success rate | 1.0000 |
| Critic trigger rate | 0.6000 |
| Critic revision rate | 0.6000 |
| Targeted retrieval trigger rate | 0.6000 |

## Bad cases

No bad cases.
