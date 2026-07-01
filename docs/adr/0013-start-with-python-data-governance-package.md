# Start with a Python Data Governance Package

LawAgent 第一阶段先搭建纯 Python 数据治理包，使用 `pyproject.toml` 和 `law_agent` 包结构实现 manifest、fetch、normalize、clean、enrich、chunk、evalset 和 report 流程。暂不引入 LangGraph、FastAPI、PostgreSQL client、Elasticsearch client 或前端框架，等 JSONL 文件流水线稳定后再接入在线问答和检索服务。
