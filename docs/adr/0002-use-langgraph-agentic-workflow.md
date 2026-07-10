# Use a Deterministic Agentic Workflow Instead of Autonomous Multi-Agent Chat

LawAgent 第一版采用项目内的确定性 Supervisor 实现 Agentic Workflow，而不是 CrewAI 或 AutoGen 式多个自治 Agent 互相对话。这个选择让意图识别、查询改写、混合检索、证据自检、二次召回、引用校验和拒答都成为可观察、可测试、可评测的显式节点；Supervisor、Researcher、Reviewer、Critic 等角色通过严格 schema 交换状态，并由程序限制分支和最大回路次数。

当前实现不依赖 LangGraph。只有在 checkpoint、人工中断后恢复、长任务持久化或复杂并行子图成为真实需求时，才重新评估迁移到 LangGraph；框架迁移本身不作为产品目标。
