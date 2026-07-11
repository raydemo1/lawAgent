# LawAgent Full Evaluation Report

- Generated: `2026-07-11T05:47:09.751364+00:00`
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
| Recall@3 | 0.7541 |
| Recall@5 | 0.8526 |
| MRR@10 | 0.8679 |
| Candidate Recall@50 | 0.9573 |
| Abstention accuracy | 0.9390 |
| Second retrieval trigger rate | 0.0854 |
| Citation violations | 0 |
| Bad cases | 6 |
| Mean total latency (ms) | 96754.99 |
| Mean retrieval latency (ms) | 32573.18 |
| Total LLM calls | 341 |
| Total retries | 45 |
| Workflow success rate | 1.0000 |
| Critic trigger rate | 0.3171 |
| Critic revision rate | 0.3049 |
| Targeted retrieval trigger rate | 0.2927 |

### Bad-case taxonomy

- `abstention_error`: 5
- `retrieval_low_recall`: 1

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_automotive_001 | abstention_error | abstention_incorrect | cac_data_export_security_assessment_measures_2022 |
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_automotive_005 | abstention_error | abstention_incorrect | - |
| eval_financial_002 | abstention_error | abstention_incorrect | - |
| eval_shenzhen_001 | abstention_error | abstention_incorrect | flk_npc_ff80818179f5e0800179f885c7e70392 |
| eval_conflict_002 | abstention_error | abstention_incorrect | cac_cross_border_flow_rules_qna_2024 |
