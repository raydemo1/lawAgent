# Three-Phase Full Evaluation Comparison

All phases use the same 82 scenarios, corpus/index, frozen facts and initial queries, `service` retrieval, `deepseek-v4-flash`, BGE-M3 embeddings, `rerank=off`, `top_k=10`, and 8 workers.

Phase 3 has two deliberately separate views. **Raw full** is the untouched 82-case run. It exposed a workflow bug: five result-generation failures were converted to all-zero retrieval metrics. **Failure-repaired** replaces only those five failed records with a bounded replay after adding deterministic Reviewer fallback and “keep original result” Revision fallback. It is a diagnostic reconstruction, not a second atomic 82-case run.

| Metric | Phase 1: single workflow | Phase 2: bounded Multi-Agent | Phase 3: deep raw full | Phase 3: failure-repaired |
|---|---:|---:|---:|---:|
| Recall@3 | 0.7236 | 0.7480 | 0.6870 | 0.7480 |
| Recall@5 | 0.8059 | 0.8364 | 0.7886 | 0.8496 |
| MRR@10 | 0.8618 | 0.8618 | 0.8191 | 0.8679 |
| Candidate Recall@50 | 0.9350 | 0.9472 | 0.8984 | 0.9594 |
| Abstention accuracy | 0.9756 | 0.9878 | 0.9390 | 1.0000 |
| Workflow success rate | 0.9756 | 0.9878 | 0.9390 | 1.0000 |
| Citation violations | 0 | 0 | 0 | 0 |
| Bad cases | 7 | 6 | 6 | 1 |
| Workflow errors | 2 | 1 | 5 | 0 |
| Mean total latency | 57.00 s | 65.89 s | 89.56 s | 92.96 s |
| Mean retrieval latency | 33.94 s | 32.95 s | 31.45 s | 31.27 s |
| Total LLM calls | 164 | 214 | 282* | 313 |
| Total retries | 4 | 2 | 7* | 17 |

`*` The raw failure records lose their telemetry when the safe runner creates a workflow-error result, so raw Phase 3 calls and retries are under-counted.

## What changed in Phase 3

- Case Analyst became a real Flash LLM node and generates up to four issue plans plus issue-specific research queries.
- Evidence Researchers fuse candidates per issue. Final evidence keeps three baseline-query anchors, reserves at most one source per issue, then fills remaining slots globally.
- Evidence Critic may request one batched targeted retrieval pass before one Reviewer revision. Neither step can loop.
- Critic is triggered only by high risk, evidence insufficiency, or a previous evidence retry; merely having four issues no longer triggers it.
- A failed initial Reviewer falls back to the deterministic governed result. A failed Critic revision keeps the already validated original result.

## Phase 3 behavior

On the failure-repaired 82-case view:

- Critic triggered on 26/82 cases (31.71%).
- It requested one revision on 24/82 cases (29.27%).
- Targeted evidence retrieval ran on 22/82 cases (26.83%).
- No case entered a second Critic or a second revision loop.
- The five-case replay achieved 5/5 workflow success and Recall@5 1.0. Two revisions still failed claim-grounding validation, but the original valid Reviewer results were retained.

## Interpretation

Compared with Phase 2, the failure-repaired deep workflow improves Recall@5 by 0.0132, MRR@10 by 0.0061, and Candidate Recall@50 by 0.0122. The gain is real but small: LLM calls rise by about 46% and mean latency by about 41%.

The raw Phase 3 result is intentionally retained because it found two engineering defects. First, a downstream generation failure could discard an otherwise successful review. Second, the evaluation safe runner conflated generation failure with retrieval failure by assigning zero Recall/MRR/Candidate Recall. The production fallback is fixed; evaluation reports now disclose the raw and repaired views instead of silently rewriting the full run.

After this evaluation, revision was further hardened from full-result regeneration to typed, patch-based revision with an evidence-feasibility gate. Out-of-corpus abstentions now use a deterministic no-LLM revision path. These post-evaluation changes are covered by tests but are not claimed in the numbers above; no additional full evaluation was run.

## Recommendation

Keep Phase 2 `multi_agent` behavior as the cost-sensitive default. Use the deep Analyst + issue research + targeted Critic path for high-risk or complex cases where a 1–2 point retrieval improvement is worth roughly 40–46% more latency/calls. For an interview project, Phase 3 is most valuable as an evidence-backed architecture experiment and failure-analysis story, not as a claim that more agents always win.

Tracked reports:

- [Phase 1 baseline](phase1-baseline-full.md)
- [Phase 2 bounded Multi-Agent](phase2-multi-agent-full.md)
- [Phase 3 raw full](phase3-deep-multi-agent-full.md)
- [Phase 3 five-case failure replay](phase3-failed-case-replay.md)
