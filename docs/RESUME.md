# LawAgent Resume Notes

## Recommended project bullets

- 设计并实现面向企业数据合规审查的 Agentic RAG 系统，构建 Elasticsearch + pgvector 双路检索、RRF/source-aware fusion、元数据增强、证据自检、受控二次召回和 claim-level citation gate；后端累计 315 项测试通过。
- 设计确定性 Supervisor + Case Analyst + Evidence Researcher + Compliance Reviewer + 条件式 Evidence Critic，通过严格 schema、最多一次修订和 AgentStep trace 约束协作，避免自治 Agent 无限循环。
- 在相同 82-case service-mode 评测集、冻结 facts/query、DeepSeek Flash 和 8 workers 配置下，Multi-Agent 版本单次评测 Recall@5 从 80.59% 提升至 83.64%，abstention accuracy 从 97.56% 提升至 98.78%，引用违规保持 0；同时量化 30.5% LLM 调用增量和 15.6% 延迟增量。

## Interview caveat

The Recall improvement is an observed two-run comparison, not a statistical significance claim. The Evidence Critic runs after retrieval; its directly attributable value is finding unsupported legal inferences and forcing one bounded revision, while retrieval differences may also reflect stochastic evidence-check and supplemental-retrieval decisions.

## Suggested walkthrough

1. Start with the material-driven user flow rather than generic legal chat.
2. Explain why ES + pgvector and source-aware fusion are separate retrieval adapters.
3. Show the controlled second-retrieval state transition.
4. Use `eval_hainan_001` to demonstrate why the Critic earns its additional call.
5. Close with the measured quality/cost tradeoff and why the Critic remains conditional.
