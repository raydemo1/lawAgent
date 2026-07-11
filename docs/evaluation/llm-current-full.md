# LawAgent Full Evaluation Report

- Generated: `2026-07-11T17:20:38.015922+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `full`

## Run configuration

- retrieval_mode: `service`
- review_mode: `llm`
- rerank_mode: `off`
- max_workers: `8`
- top_k: `10`
- eval_inputs: `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`

## retrieval=service,review=llm

| Metric | Value |
|---|---:|
| Total cases | 82 |
| Source-bearing cases | 76 |
| Recall@3 | 0.7105 |
| Recall@5 | 0.8103 |
| MRR@10 | 0.8509 |
| Candidate Recall@50 | 0.8980 |
| Abstention accuracy | 0.9878 |
| Second retrieval trigger rate | 0.4390 |
| Bad cases | 6 |
| Mean total latency (ms) | 42320.10 |
| Mean retrieval latency (ms) | 20576.44 |
| Total LLM calls | 88 |
| Total retries | 5 |
| Workflow success rate | 0.9878 |
| Clean success rate | 0.9878 |
| Degraded success rate | 0.0000 |
| Hard failure rate | 0.0122 |
| Critic trigger rate | 0.0000 |
| Critic revision rate | 0.0000 |
| Targeted retrieval trigger rate | 0.0000 |

### Bad-case taxonomy

- `candidate_missing`: 1
- `retrieval_low_recall`: 5
- `workflow_error`: 1

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_cross_border_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | cac_cross_border_data_flow_rules_2024<br>cac_data_export_assessment_qna_2022 |
| eval_certification_003 | retrieval_low_recall, candidate_missing | low_recall_at_5=0.3333<min=0.5000<br>candidate_missing=['tc260_cross_border_certification_spec_2022', 'cac_personal_info_export_certification_measures_2025'] | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_automotive_007 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
| eval_automotive_009 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_financial_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_processing_requirements_2025 |
| eval_boundary_002 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
