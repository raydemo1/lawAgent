# LawAgent

LawAgent 是一个面向企业数据合规政策研究的 Agentic RAG 项目。

第一阶段优先建设数据治理底座：数据源 manifest、统一文档格式、规则清洗、语义增强、结构化分块和评测数据准备。

## 开发命令

```powershell
python -m law_agent.data --help
pytest
```

## 模型配置

语义增强阶段强制使用 OpenAI-compatible API，不提供 rule-based fallback。

复制 `.env.example` 为 `.env`，填入 DeepSeek 或其他 OpenAI-compatible provider：

```powershell
Copy-Item .env.example .env
```

`.env.example` 已预填 DeepSeek 官方 OpenAI-compatible 配置：

```text
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_API_KEY=sk-your-deepseek-api-key
OPENAI_COMPATIBLE_MODEL=deepseek-v4-flash
```

配置后验证：

```powershell
python -m law_agent.data config check
```

## 文件流水线

```powershell
python -m law_agent.data manifest build --topic data_compliance --from-flk --limit 5
python -m law_agent.data manifest validate data/manifests/source_manifest.csv
python -m law_agent.data fetch
python -m law_agent.data normalize
python -m law_agent.data clean run
python -m law_agent.data enrich
python -m law_agent.data chunk
python -m law_agent.data evalset build
python -m law_agent.data report governance
```

或在配置好 manifest 和模型后运行：

```powershell
python -m law_agent.data pipeline run
```

FLK 采集链路使用国家法律法规数据库官方接口：

- `POST /law-search/search/list`：按主题生成 source manifest。
- `GET /law-search/download/pc?format=docx&bbbs=...`：解析公开签名下载 URL。
- DOCX 正文解析使用 Python 标准库 `zipfile` 和 XML parser，不引入额外依赖。

## 文档解析器

默认 `auto` 解析策略保持第一阶段轻量：FLK 法规 DOCX 继续使用标准库解析，HTML/JSON/文本走内置规则；PDF 和图片类文档会转给 Docling。用户上传扫描版 PDF、复杂版式 PDF 时，可以显式切到 MinerU。

```powershell
python -m law_agent.data normalize --parser auto
python -m law_agent.data normalize --parser docling
python -m law_agent.data normalize --parser mineru --parser-output-dir artifacts/parser/mineru
```

Docling 和 MinerU 是可选重依赖，按需要安装：

```powershell
pip install -e ".[docling]"
pip install -e ".[mineru]"
# 或一次安装两者
pip install -e ".[parsers]"
```

取舍原则：

1. 纯文本法规、FLK DOCX：使用内置轻量 parser，速度快、依赖少。
2. 普通 PDF、Word、表格和版面结构：优先 Docling，便于导出 Markdown 并保留结构。
3. 扫描版/复杂 PDF：使用 MinerU pipeline，产出 Markdown 后再进入清洗、分块和检索链路。

实现参考了 `ZongziForu/cn-law-hub` 对 FLK API 的公开整理，但当前仓库保留自己的数据治理 schema、清洗、语义增强、chunk 和 evalset 流水线。

## 当前范围

第一阶段先实现 JSONL 文件流水线，不急于接入 PostgreSQL、Elasticsearch、LangGraph、FastAPI 或前端。
