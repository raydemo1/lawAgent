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
11. `topic_tags`
12. `language`
13. `file_format`
14. `include_in_mvp`
15. `review_note`

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
  "language": "zh",
  "jurisdiction": "CN",
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

1. `doc_type` 区分 `law`、`regulation`、`policy`、`faq`、`guideline`、`privacy_policy`、`internal_policy`。
2. `authority` 用于证据自检和引用排序，例如 `national_law` 高于 `public_interpretation` 和 `simulated_internal_policy`。
3. `law_status` 必须保留，用于避免引用已废止或失效法规。
4. `structure.heading_path` 用于后续分块、引用定位和父文档补充。
5. `ingest_meta` 记录获取时间、解析器和解析器版本，便于追溯数据处理过程。

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

### 法律法规类

以“章 / 节 / 条”为结构边界：

1. 每个“第 X 条”优先作为一个 chunk。
2. 如果条文太短，可以合并相邻条。
3. 如果条文太长，按款、项拆分。
4. chunk 必须保留法规标题、章节路径、条号、父文档 ID、生效状态和权威级别。

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

1. 中文法规 chunk：300 到 1200 中文字符。
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
