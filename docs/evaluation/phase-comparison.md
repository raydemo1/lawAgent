# Single Workflow vs Multi-Agent Full Evaluation

Both full evaluations used the same 82 scenarios, corpus/index, frozen facts and initial queries, `service` retrieval, `deepseek-v4-flash`, BGE-M3 embeddings, `rerank=off`, `top_k=10`, and 8 workers.

| Metric | Phase 1: single workflow | Phase 2: Multi-Agent | Observed delta |
|---|---:|---:|---:|
| Recall@3 | 0.7236 | 0.7480 | +0.0244 |
| Recall@5 | 0.8059 | 0.8364 | +0.0305 |
| MRR@10 | 0.8618 | 0.8618 | 0.0000 |
| Candidate Recall@50 | 0.9350 | 0.9472 | +0.0122 |
| Abstention accuracy | 0.9756 | 0.9878 | +0.0122 |
| Workflow success rate | 0.9756 | 0.9878 | +0.0122 |
| Citation violations | 0 | 0 | 0 |
| Bad cases | 7 | 6 | -1 |
| Workflow errors | 2 | 1 | -1 |
| Mean total latency | 57.00 s | 65.89 s | +8.89 s (+15.6%) |
| Mean retrieval latency | 33.94 s | 32.95 s | -0.99 s |
| Total LLM calls | 164 | 214 | +50 (+30.5%) |
| Total retries | 4 | 2 | -2 |

## Multi-Agent behavior

- Evidence Critic triggered on 30/82 cases (36.59%).
- It requested one bounded revision on 20/82 cases (24.39%).
- No case could enter a second Critic/Reviewer loop.
- Citation violations remained zero after revisions.

## Interpretation

The Multi-Agent run observed a 3.05 percentage-point Recall@5 increase, stable MRR@10, one fewer workflow error, and better abstention accuracy. It paid for this with 50 additional Flash calls and 8.89 seconds more mean latency per case.

The Critic runs after retrieval, so the retrieval lift cannot be attributed directly to the Critic. Facts and initial queries were frozen, but evidence self-check and supplemental-retrieval decisions remained LLM-owned; the observed Recall difference can therefore include run-to-run variation in those nodes. The strongest direct evidence for the Multi-Agent design is the bounded Critic behavior shown in the real traces: it identified unsupported legal inferences and forced one correction without violating citation rules.

## Recommendation

Keep `llm` as the cost-sensitive mode and expose `multi_agent` for complex or high-risk reviews. The measured quality gain is useful for an interview project, but the 30.5% call increase does not justify forcing the Critic onto every case; the current conditional trigger is the intended production posture.

Raw tracked reports:

- [Phase 1 baseline](phase1-baseline-full.md)
- [Phase 2 Multi-Agent](phase2-multi-agent-full.md)
