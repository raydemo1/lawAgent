# LawAgent Full Evaluation Report

- Generated: `2026-07-11T16:34:01.896378+00:00`
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
| Recall@3 | 0.7281 |
| Recall@5 | 0.8311 |
| MRR@10 | 0.8706 |
| Candidate Recall@50 | 0.9594 |
| Abstention accuracy | 1.0000 |
| Second retrieval trigger rate | 0.4268 |
| Bad cases | 2 |
| Mean total latency (ms) | 86052.68 |
| Mean retrieval latency (ms) | 21141.26 |
| Total LLM calls | 230 |
| Total retries | 20 |
| Workflow success rate | 1.0000 |
| Clean success rate | 0.9512 |
| Degraded success rate | 0.0488 |
| Hard failure rate | 0.0000 |
| Critic trigger rate | 0.5488 |
| Critic revision rate | 0.5244 |
| Targeted retrieval trigger rate | 0.4512 |

### Bad-case taxonomy

- `retrieval_low_recall`: 2

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_boundary_002 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | flk_npc_ff8081817b6472a3017b656cc2040044<br>tc260_sensitive_pip_identification_guide_2024 |
