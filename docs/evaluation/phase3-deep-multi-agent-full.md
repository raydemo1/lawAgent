# LawAgent Full Evaluation Report

- Generated: `2026-07-11T04:58:59.565958+00:00`
- Corpus: `data\corpus\legal_docs_20260702\chunks.jsonl`
- Cases: `full`

## Run configuration

- retrieval_mode: `service`
- review_mode: `multi_agent`
- rerank_mode: `off`
- max_workers: `8`
- top_k: `10`
- eval_inputs: `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`

> This is the untouched raw full run. Five downstream result-generation failures were recorded as all-zero retrieval metrics by the safe runner. See the [five-case post-fix replay](phase3-failed-case-replay.md) and [three-phase comparison](phase-comparison.md) for the diagnosed and failure-repaired view; this file is intentionally not rewritten.

## retrieval=service,review=multi_agent

| Metric | Value |
|---|---:|
| Total cases | 82 |
| Recall@3 | 0.6870 |
| Recall@5 | 0.7886 |
| MRR@10 | 0.8191 |
| Candidate Recall@50 | 0.8984 |
| Abstention accuracy | 0.9390 |
| Second retrieval trigger rate | 0.0488 |
| Citation violations | 0 |
| Bad cases | 6 |
| Mean total latency (ms) | 89564.73 |
| Mean retrieval latency (ms) | 31451.39 |
| Total LLM calls | 282 |
| Total retries | 7 |
| Workflow success rate | 0.9390 |
| Critic trigger rate | 0.2805 |
| Critic revision rate | 0.2561 |
| Targeted retrieval trigger rate | 0.2317 |

### Bad-case taxonomy

- `retrieval_low_recall`: 1
- `workflow_error`: 5

## Bad cases

| Case | Categories | Reasons | Missing sources |
|---|---|---|---|
| eval_automotive_003 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_certification_003 | retrieval_low_recall | low_recall_at_5=0.3333<min=0.5000 | tc260_cross_border_certification_spec_2022<br>cac_personal_info_export_certification_measures_2025 |
| eval_automotive_005 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_automotive_009 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_qna_002 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
| eval_out_of_corpus_001 | workflow_error | workflow_failed:result_generation:claim_grounding_validation_failed | - |
