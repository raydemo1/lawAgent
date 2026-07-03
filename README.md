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

默认 `auto` 解析策略保持第一阶段轻量：FLK 法规 DOCX 继续使用标准库解析，HTML/JSON/文本走内置规则；PDF 和图片类文档会转给 Docling。Docling 默认在 OCR 阶段使用本地 RapidOCR + ONNXRuntime；如果需要把 OCR 放到远程 PaddleOCR 服务，可接 KServe v2-compatible OCR API。用户上传扫描版 PDF、复杂版式 PDF 时，也可以显式切到 MinerU。

```powershell
python -m law_agent.data normalize --parser auto
python -m law_agent.data normalize --parser docling
python -m law_agent.data normalize --parser mineru --parser-output-dir artifacts/parser/mineru
```

Docling 和 MinerU 是可选重依赖，按需要安装：

```powershell
pip install -e ".[docling]"
pip install -e ".[mineru]"
# 或一次安装全部解析器
pip install -e ".[parsers]"
```

如果本地 `artifacts/models/docling` 目录缺 RapidOCR 模型，流水线会让 Docling 回到默认模型缓存，避免卡在残缺目录上。要强制使用某个完整模型目录，可以设置：

```powershell
$env:LAWAGENT_DOCLING_ARTIFACTS_PATH="artifacts/models/docling"
```

远程 OCR API 需要兼容 Docling 的 KServe v2 OCR 输入输出：输入包含 `image` 和 `lang_type`，输出包含 `boxes`、`txts`、`scores`。配置示例：

```powershell
$env:LAWAGENT_DOCLING_OCR_ENGINE="kserve_v2_ocr"
$env:LAWAGENT_DOCLING_OCR_API_URL="http://127.0.0.1:8000"
$env:LAWAGENT_DOCLING_OCR_MODEL_NAME="ocr"
$env:LAWAGENT_DOCLING_OCR_TRANSPORT="http"
python -m law_agent.data normalize --parser docling
```

取舍原则：

1. 纯文本法规、FLK DOCX：使用内置轻量 parser，速度快、依赖少。
2. 普通 PDF、Word、表格和版面结构：优先 Docling，便于导出 Markdown 并保留结构。
3. 扫描版/复杂 PDF：优先试 Docling；若版式结构仍不理想，再使用 MinerU pipeline，产出 Markdown 后进入清洗、分块和检索链路。
4. 不在当前项目内直接加载 PaddleOCR 本地模型；如果要用 PaddleOCR，优先把它封装成远程 KServe v2-compatible OCR 服务，让 Docling 在 OCR 阶段调用。

实现参考了 `ZongziForu/cn-law-hub` 对 FLK API 的公开整理，但当前仓库保留自己的数据治理 schema、清洗、语义增强、chunk 和 evalset 流水线。

## 当前范围

第一阶段先实现 JSONL 文件流水线，不急于接入 PostgreSQL、Elasticsearch、LangGraph、FastAPI 或前端。
