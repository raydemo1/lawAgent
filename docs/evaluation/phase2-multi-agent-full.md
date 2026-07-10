# LawAgent Full Evaluation Report

- Generated: `2026-07-10T22:09:05.791648+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `full`

## Run configuration

- Git commit: `bbbbecc`
- LLM: `deepseek-v4-flash` for Reviewer and Evidence Critic
- Embedding: `BAAI/bge-m3`
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
| Recall@3 | 0.7480 |
| Recall@5 | 0.8364 |
| MRR@10 | 0.8618 |
| Candidate Recall@50 | 0.9472 |
| Abstention accuracy | 0.9878 |
| Second retrieval trigger rate | 0.1463 |
| Citation violations | 0 |
| Bad cases | 6 |
| Mean total latency (ms) | 65892.10 |
| Mean retrieval latency (ms) | 32952.88 |
| Total LLM calls | 214 |
| Total retries | 2 |
| Workflow success rate | 0.9878 |
| Critic trigger rate | 0.3659 |
| Critic revision rate | 0.2439 |

### Bad-case taxonomy

- `retrieval_low_recall`: 5
- `workflow_error`: 1

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_cross_border_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | cac_cross_border_data_flow_rules_2024<br>cac_data_export_assessment_qna_2022 |
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_automotive_007 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
| eval_financial_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_processing_requirements_2025 |
| eval_tc260_gba_001 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_boundary_002 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
