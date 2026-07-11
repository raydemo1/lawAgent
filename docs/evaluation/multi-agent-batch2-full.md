# LawAgent Full Evaluation Report

- Generated: `2026-07-11T07:10:05.982638+00:00`
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
| Recall@5 | 0.8487 |
| MRR@10 | 0.8640 |
| Candidate Recall@50 | 0.9243 |
| Abstention accuracy | 0.9878 |
| Second retrieval trigger rate | 0.4024 |
| Bad cases | 2 |
| Mean total latency (ms) | 92483.21 |
| Mean retrieval latency (ms) | 20399.65 |
| Total LLM calls | 285 |
| Total retries | 38 |
| Workflow success rate | 1.0000 |
| Clean success rate | 0.7683 |
| Degraded success rate | 0.2317 |
| Hard failure rate | 0.0000 |
| Critic trigger rate | 0.5244 |
| Critic revision rate | 0.5122 |
| Targeted retrieval trigger rate | 0.4878 |

### Bad-case taxonomy

- `abstention_error`: 1
- `candidate_missing`: 1
- `retrieval_low_recall`: 1

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_certification_003 | retrieval_low_recall, candidate_missing | low_recall_at_5=0.3333<min=0.5000<br>candidate_missing=['tc260_cross_border_certification_spec_2022', 'cac_personal_info_export_certification_measures_2025'] | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_abstain_004 | abstention_error | abstention_incorrect | - |
