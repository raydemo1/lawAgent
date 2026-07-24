# CrossComply Resume Notes

## Recommended project bullets

- 设计并实现面向企业数据合规审查的 Agentic RAG 系统，构建 Elasticsearch + pgvector 双路检索、RRF/source-aware fusion、元数据增强、证据自检、受控二次召回和 claim-level citation gate；后端累计 315 项测试通过。
- 设计确定性 Supervisor + LLM Case Analyst + 按议题 Evidence Researchers + Compliance Reviewer + 条件式 Evidence Critic，通过严格 schema、每 issue 独立检索融合、最多一次定向补检索/修订和 AgentStep trace 避免自治 Agent 无限循环。
- 手工复核 82 个 service-mode 场景的核心/辅助法源标签，修正自动分母带来的指标虚高；将 Must-have Recall@5、Optional coverage@5 与整体 Recall@5 拆分为独立指标，引用与拒答校验均保持可追溯。
- 在同一手工标注口径下完成 LLM、LLM + embedding rerank 和有界 Multi-Agent 全量对比：rerank 将 Must-have Recall@5 从 87.06% 提升至 89.25%、MRR@10 从 85.53% 提升至 88.16%，仅用 84 次 LLM 调用；Multi-Agent 以 215 次调用和约 1.9 倍延迟换取 78.57% Optional coverage@5 及更少的阈值型 bad case。
- 通过逐案例归因证明 rerank 主要改变 top-50 候选内部排序：整体核心法源召回上升，但个别边界/冲突案例发生严重误排；据此将 rerank 设为可回退的质量增强层，Multi-Agent 仅用于高风险、多议题深度审查。

## Interview caveat

The latest numbers are one controlled 82-case run per configuration, not a statistical-significance claim. Bad-case count uses a hard `Recall@5 < 0.5` threshold, so it must not replace continuous recall and ranking metrics. The production posture is LLM as the resilient fallback, rerank as a health-gated quality layer, and bounded Multi-Agent only for complex reviews where broader supporting-source coverage justifies the extra calls and latency.

## Suggested walkthrough

1. Start with the material-driven user flow rather than generic legal chat.
2. Explain why ES + pgvector and source-aware fusion are separate retrieval adapters.
3. Show the controlled second-retrieval state transition.
4. Explain why manually separated must-have and optional labels prevent a misleading aggregate score.
5. Compare rerank's core-law gain with its case-level regressions, then close with the quality/cost/reliability routing decision.
