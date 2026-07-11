# Phase 4 Full Evaluation and Evaluation-System Audit

## Executive conclusion

The current result is **not an upper bound**. The new 82-case full run reached Recall@5 `0.8526`, but the source-bearing subset is `0.8410`; six abstention cases with no expected sources are currently counted as perfect retrieval and inflate the aggregate. Among the 76 source-bearing cases, mean Recall@10 is `0.9441`, and 20 cases already contain more expected sources in Top-10 than Top-5. Most remaining headroom is ranking and evaluation design, not corpus absence.

The deep Multi-Agent workflow is also not yet a clear default winner. Against Phase 2 it gains `+0.0163` Recall@5, while LLM calls rise from 214 to 341 and mean latency from 65.89 s to 96.75 s. A paired case bootstrap gives a 95% interval of `[-0.0285, +0.0610]` for the Recall@5 delta, so the observed lift is not statistically convincing from one run.

## Run configuration

- 82 full scenarios
- frozen initial facts and queries: `artifacts/review_runs/eval_inputs/full_phase_comparison.jsonl`
- retrieval: real `service` mode, Elasticsearch + pgvector, 1,728 rows each
- review: deep `multi_agent`
- models: DeepSeek Flash node overrides and BGE-M3 embeddings
- rerank: off
- top_k: 10
- workers: 8
- implementation commit: `65714a1`
- report: [phase4-patch-revision-full.md](phase4-patch-revision-full.md)

## Result

| Metric | Phase 1 | Phase 2 | Phase 4 current |
|---|---:|---:|---:|
| Recall@3 | 0.7236 | 0.7480 | 0.7541 |
| Recall@5 | 0.8059 | 0.8364 | 0.8526 |
| MRR@10 | 0.8618 | 0.8618 | 0.8679 |
| Reported Candidate Recall@50 | 0.9350 | 0.9472 | 0.9573 |
| Abstention accuracy | 0.9756 | 0.9878 | 0.9390 |
| Workflow success | 0.9756 | 0.9878 | 1.0000 |
| Bad cases | 7 | 6 | 6 |
| Mean total latency | 57.00 s | 65.89 s | 96.75 s |
| Mean retrieval latency | 33.94 s | 32.95 s | 32.57 s |
| LLM calls | 164 | 214 | 341 |
| Retries | 4 | 2 | 45 |

Phase 4 generated 13.71 total queries per case on average, versus 6.54 frozen initial queries. The extra total latency is primarily LLM orchestration: mean retrieval latency stayed close to Phase 2, while total latency increased by about 47%.

## Why Recall@5 stops near 0.85 today

### 1. Top-5 ranking is the main measured bottleneck

- All 39 unique expected source IDs exist in the 42-source corpus.
- 53/82 cases already have Recall@5 1.0.
- 29/76 source-bearing cases are not perfect at Top-5.
- 20 of those cases recover additional expected sources by Top-10.
- Source-bearing Recall@5 is `0.8410`; source-bearing Recall@10 is `0.9441`.

The current selection policy preserves three global anchors, reserves one source per issue, then fills globally. This is stable and diverse, but not calibrated for the final legal-source ordering. Generic cross-border sources frequently outrank narrower Q&A, certification, boundary, and TC260 sources.

### 2. Cross-query score fusion is not well calibrated

`merge_hits_by_chunk_id` compares raw scores from different queries and keeps the highest score before RRF. BM25 scores from different query texts are not inherently calibrated. Adding Analyst queries can therefore introduce high-scoring generic chunks and evict narrower candidates before source fusion. Per-query rank fusion or per-query normalization should happen before cross-query truncation.

### 3. The remaining hard cases are concentrated, not universal

The weakest repeated expected sources include:

- `cac_data_export_assessment_qna_2022`: Top-5 hit in 1/4 annotated cases
- `cac_data_export_security_assessment_measures_2022`: 11/19
- `cac_personal_info_export_certification_measures_2025`: 6/9
- `tc260_sensitive_pip_identification_guide_2024`: 3/5

The only current retrieval bad case under the existing threshold is `eval_certification_003`, where the GBA-specific source is found but two general certification sources remain outside Top-5. This needs source-pathway ranking work, not more autonomous Agent loops.

### 4. Patch revision introduced over-abstention

Phase 4 correctly abstains on all 6 abstention cases, but incorrectly changes 5 answerable cases to `insufficient_evidence`:

- `eval_automotive_001`
- `eval_automotive_005`
- `eval_financial_002`
- `eval_shenzhen_001`
- `eval_conflict_002`

Abstention recall is 1.0, but abstention precision is only `0.5455`. A `mark_evidence_gap` or `narrow_claim` patch is currently allowed to change risk to `insufficient_evidence`; that transition should require an explicit `abstain` action plus an out-of-scope or insufficient-evidence signal.

### 5. Strict patch validation is costly and opaque

- 8/25 patch revisions exhausted validation retries and retained the original result.
- 2/82 initial Reviewers used deterministic fallback.
- Reported workflow success is 1.0, but only 72/82 cases completed without any failed AgentStep (`0.8780` clean-workflow rate).
- The evaluation reports only `revision_patch_validation_failed`, then deletes the temporary trace, so the exact failed constraint cannot be audited after a full run.

## Evaluation-system findings

### P0 — Citation evaluation is currently vacuous

All 82 scenarios have an empty `must_not_cite_as_clause` list. Therefore citation violations must be zero regardless of result quality. Meanwhile `expected_citation_roles` is populated for 76 cases but is never consumed by `evaluate_case`.

Consequences:

- “zero citation violations” should not be used as a resume-quality claim yet;
- the suite does not measure citation completeness, expected role coverage, or whether a claim is entailed by its cited chunk;
- returning no citations can also score zero violations.

### P0 — Candidate Recall@50 is not Candidate Recall@50

The runner passes `keyword_results + vector_results` as the candidate pool. This can contain up to 100 entries with duplicates, is not the fused Top-50 pool, and excludes Critic-targeted candidates. `eval_classification_001` demonstrates the inconsistency: final Recall@5 is 1.0 while reported Candidate Recall is 0.6667.

This metric must be rebuilt from a persisted, unique, fused pre-selection candidate pool before it is used to distinguish recall from ranking failures.

### P1 — Empty-ground-truth cases inflate retrieval metrics

Recall and MRR return 1.0 when `expected_sources` is empty. The six abstention cases therefore count as perfect retrieval. Phase 4's reported Recall@5 is 0.8526, while the 76 source-bearing cases score 0.8410. Retrieval and abstention metrics should be aggregated over separate denominators.

### P1 — “Workflow success” hides degraded execution

Workflow success only checks `workflow_failed`. Deterministic Reviewer fallback and failed Revision fallback still count as success. Phase 4 reports 100%, although 10 cases contain a failed AgentStep. Add clean success, degraded success, and hard failure as separate outcomes.

### P1 — Bad-case thresholds are too lenient and uneven

78/82 scenarios use `min_recall_at_5=0.5`. With two expected sources, one hit passes; with three, one hit fails and two pass. Only one retrieval case is marked bad, while 29/76 source-bearing cases miss at least one required source. Report completeness bands or must-have source misses instead of a single 0.5 threshold.

### P1 — Golden labels lack alternatives and priority

Every expected source is treated as equally required by exact `source_id`. The schema cannot express:

- must-have primary basis versus useful supporting material;
- acceptable alternative or superseding sources;
- source groups where any one is sufficient;
- temporal validity and annotation rationale.

This is especially important for Q&A, implementation guides, certification pathways, and newer rules that overlap older documents.

### P1 — The comparison is not a controlled ablation

Facts and initial queries are frozen, but Analyst output, evidence self-check, supplemental retrieval, Critic decisions, and model retries remain stochastic. Across the four stored runs, 31 cases changed Recall@5 and 20 changed by at least 0.5. The suite has no repeated-run variance estimate, fixed model snapshot, or seed.

The Phase 2 to Phase 4 Recall@5 lift is `+0.0163`; paired bootstrap 95% CI is `[-0.0285, +0.0610]`. One run cannot attribute this lift to the deep Multi-Agent design.

### P1 — No holdout split

The same 82 cases were repeatedly inspected while query planning, source fusion, rerank, and Multi-Agent behavior were changed. Even without explicit case-specific rules, this creates evaluation-set overfitting. Keep the current set as development diagnostics and create a separately annotated holdout set that is not used during optimization.

### P1 — Reproducibility assets are ignored

The canonical corpus, frozen eval inputs, and raw JSON summaries are under ignored `data/` and `artifacts/` paths. A clean clone has tracked Markdown summaries but not the exact inputs or corpus used to produce them. At minimum track a manifest with corpus hash, source inventory, frozen-input hash, model IDs, prompt/commit ID, index counts, and run command. Ideally publish a small redistributable evaluation snapshot.

### P2 — Several intended capabilities are not actually measured

- `expected_citation_roles` is unused.
- Second retrieval records only trigger rate, not before/after lift.
- Critic records trigger/revision rate, not whether the patch improved or harmed the result.
- No claim-level entailment, unsupported-claim precision, action correctness, or report-quality assessment exists.
- Calls and retries are counted, but tokens and monetary cost are not.
- Mean latency is reported without p50/p90/p95. Phase 4 total latency p50 is 77.6 s, p95 172.4 s, max 195.6 s.

### P2 — Documentation and behavior disagree

`docs/CONTEXT.md` says exhausted LLM nodes must fail explicitly and must not use rule fallback. Current Multi-Agent service intentionally uses deterministic fallback. The product contract must decide whether this is a successful degraded result or a hard workflow failure, and the evaluation must follow the same definition.

## Is 0.85 the ceiling?

No.

Evidence against a ceiling:

1. All expected sources exist in the corpus.
2. Top-10 source-bearing recall is `0.9441`, about 10 points above Top-5.
3. Twenty cases already recover missing Top-5 sources by Top-10.
4. A historical rerank-on run on the same suite reached Recall@5 `0.8852`, although it used an older workflow and is not a clean current comparison.
5. The current metric itself has denominator and candidate-pool defects, so `0.8526` is not a sufficiently reliable ceiling estimate.

The realistic near-term target is not “push Multi-Agent harder.” It is to establish a trustworthy metric, fix over-abstention, and improve candidate-to-Top-5 ordering. Only after that should another full run be used as the final resume number.

## Recommended order of work

1. **Repair the evaluation contract first**: true fused Candidate@50, separate retrieval/abstention denominators, citation-role coverage, non-empty negative citation cases, clean/degraded/failure workflow outcomes.
2. **Fix over-abstention**: only explicit `abstain` may transition to `insufficient_evidence`; evidence gaps should normally narrow claims while preserving a bounded risk decision.
3. **Make failures auditable**: persist node failure reason and validation category in the case result before temporary traces are removed.
4. **Fix cross-query fusion**: fuse per-query ranks or normalize scores before truncation; then re-evaluate source-aware Top-5 allocation.
5. **Cap Analyst query budget**: current mean is 13.71 total queries per case; target a controlled 8–10 total and measure quality/cost.
6. **Add a small holdout**: 20–30 independently reviewed cases with must-have/alternative sources and claim/citation expectations.
7. **Run one final controlled evaluation**: one ablation table plus paired uncertainty, rather than more sequential “full” runs with several changing nodes.

## Diagnostic feedback loop

The primary differential loop for this audit loads the stored Phase 2 and Phase 4 per-case JSON results, compares Recall/Candidate/abstention/AgentStep status case by case, and slices candidate-missing versus Top-5-ranking failures. It reproduced the exact symptoms: small aggregate lift, five false abstentions, ten degraded workflows, and an impossible Candidate-vs-final ordering.
