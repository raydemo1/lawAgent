# 数据治理设计

## 目标

LawAgent 第一阶段优先建设数据治理底座，目标是把多来源、多格式、多噪声的法律法规、政策材料、隐私政策语料和问答数据加工成可检索、可评测、可追溯的知识库。

第一阶段不急于完成前端产品演示，而是先交付稳定的数据采集、清洗、语义增强、分块、入库准备和评测数据准备能力。

## 目录结构

```text
data/
  manifests/
    source_manifest.csv
    source_manifest.schema.json
  raw/
    flk_npc/
    cac/
    privacy_qa/
    opp_115/
    gdpr_dataset/
  normalized/
    documents.jsonl
  cleaned/
    documents.cleaned.jsonl
    cleaning_report.md
  enriched/
    documents.enriched.jsonl
  chunks/
    chunks.jsonl
  eval/
    retrieval_cases.jsonl
    generation_cases.jsonl
    agentic_cases.jsonl
  samples/
    before_after/
```

## 版本控制边界

真实数据文件默认不进 Git，避免仓库膨胀和许可证/隐私边界不清。

不进 Git：

1. `data/raw/`
2. `data/normalized/`
3. `data/cleaned/`
4. `data/enriched/`
5. `data/chunks/`
6. 大规模评测数据输出
7. 本地索引、缓存和下载文件

可以进 Git：

1. `data/manifests/*.schema.json`
2. 小规模示例 manifest
3. 小规模 before/after 清洗样例
4. `data/eval/*.schema.json`
5. 数据治理报告
6. 数据源说明文档

## 第一阶段产物

第一阶段数据治理完成时，应至少产出：

1. `source_manifest.csv`：候选数据源清单，经过人工确认后决定是否进入 MVP。
2. `documents.jsonl`：统一后的内部文档格式。
3. `documents.cleaned.jsonl`：清洗后的文档。
4. `cleaning_report.md`：清洗规则、命中统计和抽样前后对比。
5. `documents.enriched.jsonl`：摘要、关键词、可回答问题、权威级别和主题标签。
6. `chunks.jsonl`：可检索分块结果。
7. `retrieval_cases.jsonl`：检索评测候选集。
8. `generation_cases.jsonl`：生成评测候选集。
9. `agentic_cases.jsonl`：二次召回、拒答和证据不足专项样本。

## Source Manifest 字段

`source_manifest` 是入库前的人工确认清单，字段包括：

1. `source_id`
2. `title`
3. `source_url`
4. `download_url`
5. `source_site`
6. `doc_type`
7. `authority`
8. `law_status`
9. `publish_date`
10. `effective_date`
11. `issuing_body`
12. `applicable_region`
13. `legal_domain`
14. `applicable_subjects`
15. `case_no`
16. `court`
17. `trial_instance`
18. `contract_parties`
19. `clause_type`
20. `topic_tags`
21. `language`
22. `file_format`
23. `include_in_mvp`
24. `review_note`

## 统一 Document 格式

所有来源材料先解析为统一 `Document`，再进入清洗、语义增强、分块和入库。

```json
{
  "doc_id": "flk_npc_pipl_2021",
  "source_id": "flk_npc_001",
  "title": "中华人民共和国个人信息保护法",
  "source_url": "https://flk.npc.gov.cn/...",
  "download_url": "https://wb.flk.npc.gov.cn/...",
  "source_site": "flk.npc.gov.cn",
  "doc_type": "law",
  "authority": "national_law",
  "law_status": "effective",
  "publish_date": "2021-08-20",
  "effective_date": "2021-11-01",
  "issuing_body": "全国人民代表大会常务委员会",
  "language": "zh",
  "applicable_region": "CN",
  "legal_domain": ["数据合规", "个人信息保护"],
  "applicable_subjects": ["个人信息处理者", "境外接收方"],
  "case_no": null,
  "court": null,
  "trial_instance": null,
  "contract_parties": [],
  "clause_type": null,
  "topic_tags": ["个人信息保护", "数据合规"],
  "raw_format": "docx",
  "text": "...",
  "structure": [
    {
      "heading_path": ["第一章 总则", "第一条"],
      "text": "..."
    }
  ],
  "attachments": [],
  "ingest_meta": {
    "fetched_at": "...",
    "parser": "flk_docx_parser",
    "parser_version": "0.1.0"
  }
}
```

关键字段说明：

1. `doc_type` 区分 `law`、`regulation`、`policy`、`faq`、`guideline`、`privacy_policy`、`internal_policy`、`case`、`contract`。
2. `authority` 用于证据自检和引用排序，例如 `national_law` 高于 `public_interpretation` 和 `simulated_internal_policy`。
3. `law_status` 必须保留，用于避免引用已废止或失效法规。
4. `structure.heading_path` 用于后续分块、引用定位和父文档补充。
5. `ingest_meta` 记录获取时间、解析器和解析器版本，便于追溯数据处理过程。
6. `applicable_region` 表示适用地域，全国性法规为 `CN`，地方性规则后续使用 `CN-BJ`、`CN-SH` 等编码；第一阶段不再同时维护 `jurisdiction` 和 `region` 两套字段。
7. `issuing_body` 是可选精确字段，只在来源字段明确或人工 manifest 确认时填写；FLK 搜索结果读不到时不猜测。
8. `legal_domain`、`applicable_subjects`、`clause_type` 是后续 metadata filter 的核心字段。
9. `case_no`、`court`、`trial_instance`、`contract_parties` 先进入统一 schema，第一阶段法规数据可为空，第二阶段案例和合同数据接入时启用。

## 数据治理流程

1. 主题词检索和候选发现。
2. 下载或保存原始材料。
3. 生成 `source_manifest`。
4. 人工确认进入 MVP 的材料。
5. 解析为统一 `Document` 格式。
6. 执行清洗规则。
7. 生成清洗报告和抽样前后对比。
8. 调用模型或规则做语义增强。
9. 按文档类型执行分块。
10. 生成评测候选集。
11. 写入 PostgreSQL/pgvector 和 Elasticsearch。

## 来源纳入规则

第一阶段知识库默认只纳入可直接作为合规判断依据或操作指引的现行材料。采集阶段可以保留更多候选材料供审阅，但正式入库前必须执行以下取舍：

1. 修改决定、修正草案、征求意见稿、新闻稿式发布说明不直接进入正式检索知识库；除非需要做版本沿革说明，否则只作为来源 trace 或人工审阅材料保留。
2. 同一文件存在多个版本时，默认启用最新现行版本；旧版进入 `superseded` / `amended` 状态，不参与默认召回。
3. 如果一个发布页同时包含多个附件，必须拆成多个逻辑文档管理，不能把发布页标题当作唯一知识文档。
4. 对数据出境材料的当前口径：`数据出境安全评估申报指南（第三版）` 替代安全评估申报指南第二版；但 2024 年同页发布的 `个人信息出境标准合同备案指南（第二版）` 是另一类备案指南，没有被第三版安全评估指南替代，仍可作为标准合同备案流程材料保留。
5. 旧版法律、旧版指南、历史决定可以进入审计/版本对照数据集，但回答层默认过滤，只在用户明确问“历史版本/修订变化”时召回。
6. 具体条款引用只允许来自 `primary_legal_basis` 材料；地方性法规、标准指南、官方问答、报告和版本材料可以被检索或辅助解释，但不能作为“第 X 条/第 X 款”的最终引用来源。

### 引用角色

每个 chunk 进入检索前都要带上 `citation_role` 和 `can_cite_clause`：

1. `primary_legal_basis`：正式依据层，允许具体条款引用，`can_cite_clause=true`。
2. `conditional_local_basis`：地方性法规，只有问题显式命中地域时作为地域依据，不进入默认全国性条款引用。
3. `implementation_reference`：标准、实践指南、模板体系文件，用于落地说明，不输出为法律条款依据。
4. `interpretation_auxiliary`：答记者问、政策问答、报告，用于解释口径和查询增强，不替代正式依据。
5. `version_archive`：旧版、修改决定、历史沿革，只在版本比较问题中启用。

## 清洗规则设计

第一版清洗分为三层：通用规则、来源特定规则和人工抽样审核。

### 通用清洗规则

适用于所有文本：

1. 统一换行和空白。
2. 去掉重复空行。
3. 去掉不可见字符。
4. 去掉明显乱码。
5. 去掉重复标题。
6. 去掉空段落。
7. 规范 URL、脚注和引用格式。
8. 保留原始段落顺序。
9. 去掉网页导航、图片占位、打印/纠错/分享控件、页脚备案号和 CMS 发布信息。
10. 去掉 PDF/标准目录里的点线页码行，目录结构尽量转成 `structure.heading_path` 或 `toc` 元数据。
11. 来源文档自带摘要、前言、引言不一刀切删除：摘要可进入 `summary` / `abstract` 元数据；前言多用于版本说明，默认低权重；引言、范围、术语、定义、正文要求和附录按内容价值保留。

### 来源特定规则

`flk.npc.gov.cn`：

1. 保留法规标题、章、节、条。
2. 去掉页面导航、下载提示、无关按钮文本。
3. 保留公布日期、施行日期、法规状态。
4. 识别“第 X 条”为结构化标题路径。

网信办和其他主管部门网页：

1. 去掉导航、分享、责任编辑、来源网站页脚。
2. 保留发文机关、发布时间和正文。
3. 对政策问答保留问答结构。

OPP-115 和隐私政策：

1. 去掉 cookie banner、网页 footer、广告导航。
2. 保留 section heading。
3. 合并断裂段落。
4. 识别隐私实践相关段落。

PrivacyQA：

1. 问题、答案、证据段落分开保存。
2. 不把评测答案混进知识库正文。

### 人工抽样审核

每轮清洗后抽样检查：

1. 每个数据源抽 5 到 10 份。
2. 比较清洗前后。
3. 标注噪声是否还在。
4. 标注是否误删重要内容。
5. 把问题沉淀为下一轮清洗规则。

### LLM 使用边界

法律法规正文必须保真。LLM 可以用于发现噪声模式、生成摘要、关键词和可回答问题，但不能大规模改写法律法规正文。

## 语义增强字段

第一版语义增强生成以下字段：

```json
{
  "summary": "一句话到三句话摘要",
  "keywords": ["个人信息", "数据出境", "单独同意"],
  "questions": [
    "什么情况下需要申报数据出境安全评估？",
    "个人信息出境需要履行哪些义务？"
  ],
  "topic_tags": ["数据出境", "个人信息保护"],
  "applicable_subjects": ["个人信息处理者", "关键信息基础设施运营者"],
  "authority_level": "national_law",
  "risk_tags": ["高风险出境", "敏感个人信息"],
  "effective_status": "effective",
  "enrichment_meta": {
    "model": "...",
    "prompt_version": "0.1.0",
    "generated_at": "..."
  }
}
```

字段用途：

1. `summary` 帮助父文档整体理解。
2. `keywords` 参与 Elasticsearch 加权检索。
3. `questions` 增强用户问法和文档表达之间的匹配。
4. `topic_tags` 用于路由和过滤。
5. `applicable_subjects` 帮助回答适用对象。
6. `authority_level` 参与证据自检和引用排序。
7. `risk_tags` 帮助生成风险边界。
8. `effective_status` 避免引用失效法规。
9. `enrichment_meta` 记录模型、提示词版本和生成时间，便于追溯。

## 分块策略

第一版分块按文档类型执行，不使用单一固定长度策略。

## 成熟框架借鉴

RAGFlow 作为成熟 RAG 产品和设计参照，但第一阶段不作为主框架引入。项目优先保留自己的官方数据采集、数据治理 schema、清洗、语义增强、chunk、evalset 和后续混合检索链路。

重点借鉴以下设计：

1. 法律文档解析和 chunk 模板：参考 RAGFlow `laws` chunk 思路，保留章、节、条、标题树、表格和父级上下文，但实现上继续围绕 LawAgent 的 `Document`、`Chunk` schema 做可追溯字段。
2. 引用溯源和解析可视化：后续产品界面不展示清洗流程细节，但用户侧要能看到证据来源、命中条文、父文档、权威级别和生效状态；内部治理报告保留解析、清洗、chunk 统计。
3. KG / RAPTOR 等增强能力：不放入第一阶段 MVP，作为后续多跳合规问题和长文档父子召回的候选增强方案；只有当基础混合检索评测稳定后再引入。

第一阶段已落地的借鉴点：

1. DOCX 解析不只抽段落，而是按 Word body 顺序处理段落和表格，表格以 HTML 片段进入正文，避免法规附件或条款表格在解析阶段丢失。
2. 清洗阶段增加保守的目录块移除规则：只有检测到目录标题和正文标题重复时才删除目录块，避免误删真实法规正文。
3. 法律法规 chunk 不只保存条号，还保存 `heading_path`，路径包含法规标题、编、篇、章、节、条；只有超长条文才拆到款，项保留在所属条/款正文里，具体引用哪一项交给后续召回和回答层定位。
4. `Chunk` 增加 `citation_label`，评测样本同步保留 `expected_heading_path` 和 `expected_citation_label`，让检索评测从“命中 chunk”升级为“命中可引用证据”。
5. `Chunk` 继承 `doc_type`、`authority`、`law_status`、`publish_date`、`effective_date`、`applicable_region`、`legal_domain`、`applicable_subjects` 等过滤字段，先形成后续混合检索的 metadata filter 契约。
6. 治理报告增加解析器、原始格式、时效状态、法律元数据、条文 chunk、款级 chunk、项级独立 chunk、表格 chunk 和 heading 深度统计，为后续前端解析可视化提供数据基础。
7. Normalize 阶段已经接入 parser router：默认轻量解析 FLK DOCX / HTML / JSON / TXT，PDF 和图片类文档走 Docling，复杂扫描件可以显式选择 MinerU 并收集 Markdown 解析产物。

依赖取舍：

1. 不引入 RAGFlow 的整套服务依赖，例如 DeepDoc、知识图谱服务和 Agent 编排层，避免第一阶段重心变成平台部署。
2. 暂不新增 `python-docx`，因为当前 DOCX 段落和表格保留可以用标准库 `zipfile` 和 XML parser 完成；如果后续需要读取 Word 样式层级、复杂合并单元格或页码，再单独引入。
3. 后续检索服务阶段可以借鉴 RAGFlow 的多路召回、融合排序和 reranker 窗口设计，但实现仍以 LawAgent 的 PostgreSQL/pgvector + Elasticsearch 混合检索为主。
4. 用户上传文档解析已经接入可选 parser router，但不把重型 OCR 平台作为基础安装依赖；默认选择 Docling 作为 PDF、图片型文档和复杂 Office 文档的结构化解析器。
5. MinerU 已作为显式增强 parser 接入，用于复杂扫描件、表格密集 PDF、版面识别效果不佳的材料；Tika 只作为超广格式覆盖或解析失败兜底候选，不作为法律结构化 chunk 的核心 parser。
6. 回答层 guardrail 放入第二阶段，包括只基于召回条款回答、强制引用条款、区分“明确规定/可能适用/材料不足”、材料不足拒答。

### 上传文档解析策略

用户上传文档和官方法规采集走同一个治理契约：先解析成统一 `Document`，记录解析器、版本、页码、表格、标题路径和置信度，再进入清洗、事实抽取、分块和检索。

第一版 parser routing：

1. Markdown / TXT / HTML：优先使用轻量 parser，保留标题层级、链接和表格。
2. FLK DOCX：继续使用当前标准库 DOCX parser，确保法规正文和表格按 Word body 顺序进入正文。
3. PDF / 图片型文件：`auto` 默认使用 Docling，输出 Markdown，再映射为 LawAgent `Document`。
4. 扫描版 PDF / 表格密集 PDF / Docling 效果不足的材料：显式使用 `--parser mineru`，让 MinerU pipeline 产出 Markdown 后再进入清洗、分块和检索。
5. 罕见 Office / 多媒体 / 邮件等格式：暂不承诺第一版支持；确有需要时再评估 Tika 作为兜底解析服务。

选择 Docling 作为默认上传文档解析器的原因：

1. 它是 Python 原生接入方式，和当前 `law_agent` 数据治理包更容易集成，不需要先引入完整 RAGFlow 服务。
2. 它面向 GenAI/RAG 输出结构化文档，支持 Markdown、HTML、JSON 等下游友好格式，适合映射到 `Document`、`Chunk` 和引用路径。
3. 它覆盖 PDF、DOCX、PPTX、XLSX、HTML、图片等常见上传材料，能支撑隐私政策、合同、数据处理协议、字段表等产品场景。
4. 它支持本地运行，适合用户上传合规材料这种敏感数据场景。

暂不默认选择其他方案：

1. DeepDoc：能力强，但更像 RAGFlow 内部深度解析组件；如果只为 LawAgent 接入上传解析，直接引入会把系统复杂度推向 RAGFlow 平台级部署。
2. MinerU：复杂 PDF、表格、公式、扫描件价值高，但部署和模型依赖更重；因此已接入为显式增强 parser，不放进默认轻量流水线。
3. Tika：格式覆盖极广，但主要价值是通用文本和元数据抽取，对法律标题树、表格语义和引用路径帮助有限；更适合兜底。

当前使用方式：

```powershell
python -m law_agent.data normalize --parser auto
python -m law_agent.data normalize --parser docling
python -m law_agent.data normalize --parser mineru --parser-output-dir artifacts/parser/mineru
```

可选依赖安装：

```powershell
pip install -e ".[docling]"
pip install -e ".[mineru]"
pip install -e ".[parsers]"
```

### 法律法规类

以“编 / 篇 / 章 / 节 / 条”为主要结构边界，超长条文才下钻到“款”：

1. 默认以“第 X 条”作为一个 chunk，因为“条”通常是法律规范的最小完整语义单元。
2. 一条不超过 900 字：整条作为一个 chunk。
3. 一条 900 到 1200 字：原则上仍保留整条，除非后续评测发现召回质量下降。
4. 一条超过 1200 字且存在多个自然段：按款拆分。
5. 拆款后单个款级 chunk 少于 120 字时，优先并入相邻款，避免产生语义过弱的小 chunk。
6. “（一）（二）（三）”等项不作为独立 chunk，只保留在所属条或款正文中；具体引用哪一项由后续召回后的证据定位和回答层完成。
7. chunk 必须保留法规标题、编、篇、章、节、条、父文档 ID、生效状态、权威级别和 metadata filter 字段；款级 chunk 额外保留款号。

### 政策解读 / 问答类

以问答或小标题为边界：

1. 每个问题和回答优先作为一个 chunk。
2. 长回答按段落切分。
3. chunk 保留问题标题和政策来源。

### 隐私政策类

以 section heading 为边界：

1. 按隐私政策中的 section heading 切分。
2. 过长 section 再按段落切。
3. 保留 privacy practice 标签。

### 模拟内部制度

以制度章节和流程步骤切：

1. 按章节、流程节点、责任角色切分。
2. 保留适用部门和流程阶段。

### 长度目标

1. 中文法规 chunk：条优先，通常 100 到 900 中文字符；硬上限 1200 中文字符，超过后才按款拆。
2. 政策问答 chunk：500 到 1500 中文字符。
3. 英文隐私政策 chunk：800 到 1800 tokens 或按 section。
4. 法规类尽量不用 overlap。
5. 隐私政策和长政策解读可以使用少量 overlap。

### 摘要处理

每个文档的摘要作为独立字段参与检索和展示，不直接拼进 chunk 正文，避免摘要语义过强导致真正包含答案的正文 chunk 排名下降。

## 第一阶段规模

目标规模：

1. 中文法规、政策、问答和示范文本：100 到 200 份候选材料。
2. 英文隐私政策或问答语料：抽样 200 到 500 份或片段。
3. 检索评测候选问题：60 条左右。
4. 生成评测候选问题：30 条左右。
5. Agentic 专项问题：20 条左右。

## 验收标准

1. 能从国家法律法规数据库和相关主管部门官网生成数据合规主题的候选 manifest。
2. 人工确认后能将材料解析为统一文档格式。
3. 清洗报告能说明主要噪声类型、规则命中情况和抽样对比。
4. 每份文档能生成摘要、关键词、可回答问题、权威级别和主题标签。
5. 每个 chunk 保留父文档、来源 URL、标题路径和相邻关系。
6. 至少形成中等规模评测候选集。
7. 所有真实数据默认不提交到 Git，只提交 schema、样例和报告。

## 第一阶段模块拆分

```text
law_agent/
  data/
    manifest.py
    fetchers/
      flk_npc.py
      web_policy.py
      privacyqa.py
      opp115.py
    parsers/
      docx_parser.py
      pdf_parser.py
      html_parser.py
      json_parser.py
    cleaners/
      common.py
      flk_npc.py
      web_policy.py
      privacy_policy.py
    enrichment/
      schema.py
      prompts.py
      generator.py
    chunking/
      law.py
      policy.py
      privacy_policy.py
      internal_policy.py
    evalset/
      build_cases.py
    reports/
      cleaning_report.py
```

建议 CLI：

```bash
python -m law_agent.data manifest build --topic data_compliance
python -m law_agent.data fetch --manifest data/manifests/source_manifest.csv
python -m law_agent.data normalize --manifest data/manifests/source_manifest.csv
python -m law_agent.data clean
python -m law_agent.data enrich
python -m law_agent.data chunk
python -m law_agent.data evalset build
python -m law_agent.data report cleaning
```

第一阶段模块边界要清晰，但 CLI 可以保持简单。避免把所有数据治理步骤塞进一个不可测试的 `pipeline.py`。
