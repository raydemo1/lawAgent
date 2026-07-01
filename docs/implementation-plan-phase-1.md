# 第一阶段实现计划：数据治理底座

## 目标

第一阶段先交付 LawAgent 的数据治理底座，不急于做产品演示。目标是把企业数据合规相关的法规、政策、隐私政策和问答数据加工成可清洗、可增强、可分块、可评测、可追溯的 JSONL 文件流水线。

## 范围内

1. 初始化 Python 数据治理包 `law_agent`。
2. 定义核心数据结构：`SourceRecord`、`Document`、`CleanedDocument`、`EnrichedDocument`、`Chunk`、评测样本。
3. 定义 `source_manifest` schema 和示例。
4. 实现数据治理 CLI 基础框架。
5. 实现第一批文件流水线命令骨架：manifest、normalize、clean、chunk、report。
6. 实现通用清洗规则和法规结构化分块的最小版本。
7. 加入聚焦测试，覆盖 schema 校验、清洗规则和法律条文分块。

## 暂不做

1. 不接 PostgreSQL/pgvector。
2. 不接 Elasticsearch。
3. 不接 LangGraph。
4. 不做 FastAPI 后端。
5. 不做前端实现。
6. 不全量下载国家法律法规数据库。
7. 不用 LLM 改写法律法规正文。

## 实现切片

### Slice 1：项目骨架

产物：

1. `pyproject.toml`
2. `law_agent/`
3. `tests/`
4. 基础 README 或开发命令说明

验收：

1. 可以运行 `python -m law_agent.data --help`。
2. 可以运行 `pytest`。

### Slice 2：Schema 与 manifest

产物：

1. `law_agent/data/schemas.py`
2. `data/manifests/source_manifest.schema.json`
3. `data/manifests/source_manifest.example.csv`

验收：

1. `SourceRecord` 可以表达国家法律法规数据库、网信办政策、PrivacyQA 等来源。
2. Manifest 示例不包含真实大数据，只作为字段样例。

### Slice 3：Normalize / Clean 文件流水线

产物：

1. `law_agent/data/normalizers/`
2. `law_agent/data/cleaners/common.py`
3. `law_agent/data/cleaners/flk_npc.py`

验收：

1. 可以把小样例输入转成统一 `Document`。
2. 通用清洗能去除重复空行、不可见字符、重复标题等噪声。
3. 法规正文清洗不改变条文核心文本。

### Slice 4：Chunking

产物：

1. `law_agent/data/chunking/law.py`
2. `law_agent/data/chunking/policy.py`

验收：

1. 法律法规按“第 X 条”优先分块。
2. chunk 保留父文档、标题路径、条号、权威级别和法规状态。
3. 文档摘要不会拼进 chunk 正文。

### Slice 5：报告与测试

产物：

1. `law_agent/data/reports/cleaning_report.py`
2. `tests/`

验收：

1. 清洗报告能输出文档数量、规则命中统计和样例摘要。
2. 测试覆盖 schema、cleaner、chunker。

## 第一轮实现优先级

本轮先完成 Slice 1、Slice 2 和 Slice 4 的可测试骨架，再补 Slice 3 的通用清洗最小版本。这样先把数据结构和分块主线立起来，后续再接具体采集器。

## 验证命令

```powershell
python -m law_agent.data --help
pytest
```

如果本机 Python 或依赖环境不可用，记录失败原因，不伪装测试已通过。
