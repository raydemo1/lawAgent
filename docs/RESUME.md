# LawAgent Resume Notes

## Recommended project bullets

- 设计并实现面向企业数据合规审查的 Agentic RAG 系统，构建 Elasticsearch + pgvector 双路检索、RRF/source-aware fusion、元数据增强、证据自检、受控二次召回和 claim-level citation gate；后端累计 315 项测试通过。
- 设计确定性 Supervisor + LLM Case Analyst + 按议题 Evidence Researchers + Compliance Reviewer + 条件式 Evidence Critic，通过严格 schema、每 issue 独立检索融合、最多一次定向补检索/修订和 AgentStep trace 避免自治 Agent 无限循环。
- 在相同 82-case service-mode 评测集、冻结 facts/query、DeepSeek Flash 和 8 workers 配置下，完成单工作流、简版 Multi-Agent、深版 Multi-Agent 三阶段实验；失败修复口径下 Recall@5 从 80.59% 提升至 84.96%，Candidate Recall@50 从 93.50% 提升至 95.94%，引用违规保持 0，同时量化深版相对简版约 46% LLM 调用和 41% 延迟增量。
- 通过全量评测定位“下游生成失败被误记为检索全零”的指标归因缺陷，增加初次 Reviewer 的确定性 fallback 与修订失败保留原结果；5 个失败案例重放后 workflow success 5/5、Recall@5 100%。

## Interview caveat

The Recall improvement is an observed staged comparison, not a statistical significance claim. The deep result is a transparent reconstruction from 77 original successes plus five post-fix failure replays, not a second atomic full run. The recommended production posture is conditional deep orchestration for high-risk cases, not enabling every LLM role for all traffic.

## Suggested walkthrough

1. Start with the material-driven user flow rather than generic legal chat.
2. Explain why ES + pgvector and source-aware fusion are separate retrieval adapters.
3. Show the controlled second-retrieval state transition.
4. Use `eval_hainan_001` to demonstrate why the Critic earns its additional call.
5. Close with the measured quality/cost tradeoff and why the Critic remains conditional.
