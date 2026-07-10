# LawAgent Full Evaluation Report

- Generated: `2026-07-10T21:46:31.693349+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `full`

## Run configuration

- Git commit: `a590967`
- Retrieval: `service` (Elasticsearch + pgvector, 1728 rows each)
- Review mode: `llm`
- LLM: `deepseek-v4-flash`
- Embedding: `BAAI/bge-m3`
- Rerank: `off`
- Workers: `8`
- Frozen inputs: `full_phase_comparison.jsonl` (82 cases)
- Top K: `10`

## retrieval=service,review=llm

| Metric | Value |
|---|---:|
| Total cases | 82 |
| Recall@3 | 0.7236 |
| Recall@5 | 0.8059 |
| MRR@10 | 0.8618 |
| Candidate Recall@50 | 0.9350 |
| Abstention accuracy | 0.9756 |
| Second retrieval trigger rate | 0.1220 |
| Citation violations | 0 |
| Bad cases | 7 |
| Mean total latency (ms) | 57000.12 |
| Mean retrieval latency (ms) | 33938.74 |
| Total LLM calls | 164 |
| Total retries | 4 |

### Bad-case taxonomy

- `retrieval_low_recall`: 5
- `workflow_error`: 2

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_cross_border_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | cac_cross_border_data_flow_rules_2024<br>cac_data_export_assessment_qna_2022 |
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_automotive_007 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
| eval_automotive_009 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_financial_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_processing_requirements_2025 |
| eval_qna_002 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_boundary_002 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
