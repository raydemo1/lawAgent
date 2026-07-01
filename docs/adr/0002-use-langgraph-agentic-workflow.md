# Use LangGraph Agentic Workflow Instead of Autonomous Multi-Agent Chat

LawAgent 第一版采用 LangGraph 实现 Agentic Workflow，而不是 CrewAI 或 AutoGen 式多个自治 Agent 互相对话。这个选择让意图识别、查询改写、混合检索、证据自检、二次召回、引用校验和拒答都成为可观察、可测试、可评测的显式节点；Supervisor、RAG Agent、Data Agent 等名称保留为角色化模块或子流程，不在第一版实现为独立自治 Agent。
