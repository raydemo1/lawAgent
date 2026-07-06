# Use RAGFlow as Reference, Not Core Framework

LawAgent 不在第一阶段引入 RAGFlow 作为主框架。RAGFlow 的法律文档 chunk、引用溯源、解析可视化、KG/RAPTOR 等能力作为成熟设计参考，但核心实现仍保留在本项目自己的数据治理和检索链路中。

原因是本项目的面试亮点不是“部署一个成熟 RAG 平台”，而是展示从官方法律数据源到可评测、可追溯法律合规知识库的端到端治理能力。RAGFlow 可作为后续 baseline 或设计对标对象，用同一批 FLK 数据比较 chunk、召回和引用效果。
