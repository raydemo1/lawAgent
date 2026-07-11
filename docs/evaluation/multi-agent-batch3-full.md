# LawAgent Full Evaluation Report

- Generated: `2026-07-11T15:53:26.582808+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `full`

## Run configuration

- retrieval_mode: `service`
- review_mode: `multi_agent`
- rerank_mode: `off`
- max_workers: `8`
- top_k: `10`
- eval_inputs: `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`

## retrieval=service,review=multi_agent

| Metric | Value |
|---|---:|
| Total cases | 82 |
| Source-bearing cases | 76 |
| Recall@3 | 0.7347 |
| Recall@5 | 0.8366 |
| MRR@10 | 0.8575 |
| Candidate Recall@50 | 0.9890 |
| Abstention accuracy | 0.9878 |
| Second retrieval trigger rate | 0.3902 |
| Bad cases | 3 |
| Mean total latency (ms) | 92094.61 |
| Mean retrieval latency (ms) | 20409.59 |
| Total LLM calls | 273 |
| Total retries | 21 |
| Workflow success rate | 1.0000 |
| Clean success rate | 0.9512 |
| Degraded success rate | 0.0488 |
| Hard failure rate | 0.0000 |
| Critic trigger rate | 0.5610 |
| Critic revision rate | 0.5244 |
| Targeted retrieval trigger rate | 0.5000 |

### Bad-case taxonomy

- `abstention_error`: 1
- `retrieval_low_recall`: 2

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_tianjin_001 | abstention_error | abstention_incorrect | - |
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_conflict_001 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | missing_20260702_014<br>cac_data_export_security_assessment_measures_2022 |
