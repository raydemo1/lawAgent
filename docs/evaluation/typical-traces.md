# Three Real Multi-Agent Traces

These examples come from the tracked 82-case Phase 2 full evaluation. They are not synthetic walkthroughs.

## 1. Direct success without Critic cost

**Case:** `eval_standard_contract_002`  
**Question:** 签完那份个人信息出境合同后，备案包里通常要放哪些材料？

| Step | Decision | Latency | LLM calls |
|---|---|---:|---:|
| Case Analyst | Planned 2 issues | 0 ms | 0 |
| Evidence Researcher | Built 2 dossiers | 33.34 s | 1 |
| Compliance Reviewer | Generated review | 16.20 s | 1 |
| Evidence Critic | Skipped: simple low-risk case | 0 ms | 0 |

Outcome: `risk=low`, Recall@5 `1.0`, MRR@10 `1.0`, no second retrieval, no missing expected source, no citation violation. This trace demonstrates that the Multi-Agent mode does not pay Critic cost for every review.

## 2. Controlled second retrieval, Critic approve

**Case:** `eval_automotive_004`  
**Question:** 重庆自贸区里的车联网平台出境，除了全国规则还要看本地清单吗？

| Step | Decision | Latency | LLM calls |
|---|---|---:|---:|
| Case Analyst | Planned 4 issues | 0 ms | 0 |
| Evidence Researcher | Built 4 dossiers after one supplemental retrieval | 53.73 s | 1 |
| Compliance Reviewer | Generated review | 30.16 s | 1 |
| Evidence Critic | Approve | 11.60 s | 1 |

The Critic found all high-priority issues supported, accepted a medium risk level, and preserved the evidence gap for missing facts. Outcome: Recall@5 `1.0`, MRR@10 `1.0`, no citation violation. The workflow terminated after one supplemental retrieval.

## 3. Critic catches overreach and forces one revision

**Case:** `eval_hainan_001`  
**Question:** 海南旅游平台把游客数据给境外关联公司，要注意自贸港哪些本地规则？

| Step | Decision | Latency | LLM calls |
|---|---|---:|---:|
| Case Analyst | Planned 2 issues | 0 ms | 0 |
| Evidence Researcher | Built 2 dossiers after one supplemental retrieval | 38.25 s | 1 |
| Compliance Reviewer | Generated first review | 22.12 s | 1 |
| Evidence Critic | Revise | 14.56 s | 1 |
| Compliance Revision | Revised once | 26.17 s | 1 |

The Critic identified three concrete problems:

1. A Personal Information Protection Law claim had no matching article in the retrieved evidence.
2. The threshold statement omitted the Hainan negative-list scenario restriction for tourism services.
3. The draft inferred that falling below the threshold automatically allowed the standard-contract path, which the retrieved local list did not establish.

The Reviewer received those instructions once and produced the final result. Outcome: `risk=medium`, Recall@5 `1.0`, MRR@10 `0.5`, no missing expected source, no citation violation, and no further loop.
