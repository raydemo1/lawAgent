# LawAgent

LawAgent 是一个面向企业数据合规政策研究的 Agentic RAG 项目。

第一阶段优先建设数据治理底座：数据源 manifest、统一文档格式、规则清洗、语义增强、结构化分块和评测数据准备。

## 开发命令

```powershell
python -m law_agent.data --help
pytest
```

## 当前范围

第一阶段先实现 JSONL 文件流水线，不急于接入 PostgreSQL、Elasticsearch、LangGraph、FastAPI 或前端。

