# LawAgent 第二阶段实施计划

第二阶段目标是把第一阶段清洗后的企业数据合规法规/政策语料，接入一个可演示、可评估、可追溯的材料驱动合规审查流程。第二阶段不以“普通法规问答”作为主线，而是让企业数据合规审查人提交具体材料或业务场景，系统抽取审查事实、执行混合检索、进行证据自检，并输出结构化审查结果和引用依据。

## 产品目标

第二阶段要交付一条真实可跑通的审查链路：

1. 用户输入审查问题，并粘贴业务说明、隐私政策片段、SDK/字段说明等文本材料。
2. PDF/DOCX 上传作为 beta 入口，通过已有 Docling/解析器链路解析成文本后进入同一流程。
3. DeepSeek LLM 节点抽取固定审查事实，输出必须通过 Pydantic 严格校验。
4. DeepSeek LLM 节点基于审查事实和用户问题生成多路检索 query。
5. 系统从当前 `artifacts/review/legal_docs_20260702/chunks.jsonl` 加载 42 份清洗后的法规/政策 chunk。
6. 系统执行本地 hybrid retrieval core：BM25、vector mock、metadata boost、RRF 融合、父文档/邻近 chunk 补充。
7. DeepSeek LLM 证据自检节点判断是否需要一次受控二次召回。
8. DeepSeek LLM 节点输出结构化审查结果，程序严格执行引用规则。
9. 前端从 mock 升级为单用户审查工作台，调用真实 review API 展示结果。
10. 评估看板展示检索/引用最小闭环指标和 bad cases。

## 非目标

第二阶段不做以下内容：

1. 生产级多用户权限、团队协作和完整历史搜索。
2. 知识库管理后台、chunk 调试台、prompt 调试台。
3. 复杂扫描件、复杂表格和页码级引用质量的专项解析评估。
4. 完整 RAGAS/LLM-as-judge 回答质量平台。
5. 循环式 Agent 检索。
6. 多 provider LLM 能力抽象和线上规则 fallback。

PostgreSQL/pgvector 和 Elasticsearch 仍是目标服务后端。Issue 12 接入服务后端时，service 模式要求 Elasticsearch 和 pgvector 都可用并融合检索；单路服务检索只作为显式诊断/消融模式。

## 主用户和使用流程

主用户是企业数据合规审查人，即企业内部负责数据出境、个人信息处理、隐私政策、第三方共享和行业/地区适用性审查的法务或合规人员。

完整流程：

1. 用户新建审查案卷。
2. 用户输入审查问题，例如“这个场景是否需要数据出境安全评估？”
3. 用户粘贴业务说明或隐私政策片段；如上传 PDF/DOCX，则先通过 Docling beta 路径解析。
4. DeepSeek LLM 抽取审查事实，并在前端展示事实摘要和缺失信息。
5. DeepSeek LLM 生成多路检索 query。
6. 系统执行本地混合检索和 RRF 融合。
7. DeepSeek LLM 执行证据自检；证据不足时最多触发一次二次召回。
8. DeepSeek LLM 生成结构化审查结果。
9. 前端展示风险等级、触发原因、适用依据、缺失信息、建议动作、风险边界和引用来源。
10. 系统保存 review case 和 retrieval trace，供评估、依据过程展示和 bad case 复盘使用。

## 核心数据结构

### ReviewFacts

`ReviewFacts` 是从用户材料抽取出的固定字段事实，供检索、证据自检、结果生成和评估复用。

建议字段：

```json
{
  "business_activity": "移动 App 个性化推荐和数据分析",
  "data_types": ["手机号", "定位信息", "设备 ID", "行为日志"],
  "sensitive_personal_info": true,
  "cross_border_transfer": true,
  "overseas_recipient": "新加坡数据分析服务商",
  "processing_purpose": "推荐优化和行为分析",
  "legal_basis_or_consent": null,
  "industry": null,
  "region": "CN",
  "missing_information": ["是否取得单独同意", "出境数据规模", "保存期限", "境外接收方安全措施"]
}
```

第一版用 DeepSeek LLM 抽取，prompt 必须包含目标 JSON 示例，输出必须经过 Pydantic schema 严格校验。模型输出不合格时只做节点级 retry；重试耗尽返回结构化 `review_failed`。业务材料本身缺少关键字段时，进入 `missing_information` 并影响最终结论。

### ReviewCase

`ReviewCase` 表示一次用户审查案卷。

建议字段：

1. `review_case_id`
2. `created_at`
3. `question`
4. `input_mode`: `pasted_text | uploaded_file`
5. `material_text`
6. `uploaded_file_meta`
7. `parsed_text`
8. `review_facts`
9. `review_result`
10. `trace_id`
11. `user_feedback`

第二阶段先保存为 JSONL；后续迁移到 PostgreSQL。

### RetrievalTrace

`RetrievalTrace` 用于复盘检索和评估。

建议字段：

1. `trace_id`
2. `review_case_id`
3. `queries`
4. `filters`
5. `metadata_boosts`
6. `bm25_results`
7. `vector_results`
8. `rrf_results`
9. `neighbor_chunks`
10. `evidence_self_check`
11. `second_retrieval`
12. `final_evidence`
13. `citation_validation`
14. `latency_ms`

## 检索流程

### 1. Query 生成

系统不只生成一个 query，而是生成多路 query：

1. 法规主问题 query：例如“数据出境安全评估触发条件”。
2. 材料事实 query：例如“手机号 定位 行为日志 新加坡 接收方 数据出境”。
3. 条件 query：例如“汽车数据出境”或“上海 数据出境 负面清单”。
4. 缺失信息 query：例如“数据出境安全评估 数量门槛”。

Query planning 由 DeepSeek LLM 节点负责，prompt 必须包含目标 JSON 示例，最终 query 列表和 query 类型要进入 trace。模型输出不合格时只做节点级 retry；重试耗尽返回结构化 `review_failed`。

### 2. Metadata boost/filter

检索阶段默认软加权，引用阶段严格治理。

建议 boost：

1. 全国性问题 boost `primary_legal_basis`。
2. 命中地区时 boost 对应 `conditional_local_basis`。
3. 命中行业时 boost 对应 `conditional_industry_basis`。
4. 操作/标准类问题 boost `implementation_reference`。
5. 官方问答 `interpretation_auxiliary` 可召回，但默认低于主依据。

只在用户明确问特定地区/行业规则时做强过滤或强加权。不要过早硬过滤掉实施参考或官方问答，否则会损失可解释材料。

### 3. 双路召回

第二阶段先实现本地检索核心：

1. BM25/关键词路：基于 chunk 文本、标题、citation label、topic tags、applicable region、applicable subjects 做关键词评分。
2. Vector mock 路：先用可替换接口模拟语义召回，可以从 enrichment questions、keywords、topic tags、文本 token overlap 或 deterministic fake embedding 起步。

实现重点是接口稳定、trace 完整、评估可跑。真实 embedding、pgvector 和 Elasticsearch 在本地闭环稳定后替换 adapter。

### 4. RRF 融合

RRF 在应用层融合两路召回结果。融合结果必须保留：

1. chunk id
2. source id
3. vector rank/score
4. BM25 rank/score
5. metadata boost
6. final RRF score
7. matched query type
8. citation role
9. can cite clause

### 5. 父文档和邻近 chunk 补充

对 top results 拉取前后 chunk、同条/同章相关 chunk 或父文档标题路径，避免只拿到半句法条或表格孤岛。

第一版先实现邻近 chunk 补充；复杂父子召回、RAPTOR、KG 放到后续。

### 6. 证据自检和二次召回

触发二次召回的条件：

1. 首次结果没有任何 `primary_legal_basis`。
2. 地区问题没有命中对应 `conditional_local_basis`。
3. 行业问题没有命中对应 `conditional_industry_basis`。
4. 只有 TC260/GB/T 或官方问答，没有主依据。
5. 召回结果和 `ReviewFacts` 关键事实不匹配。
6. 证据能回答概念，但不能支持当前材料场景判断。
7. 关键事实缺失，无法判断具体义务。

二次召回最多一次。二次召回仍不足时，输出 `insufficient_evidence` 或要求补充信息，不进入无限循环。

## 结构化审查输出

第二阶段正式引入 DeepSeek LLM，但不让模型自由决定最终结构和引用边界。

LLM 负责：

1. 审查事实抽取。
2. query planning。
3. 证据自检和一次补充检索计划。
4. 结构化审查结果生成和用户可读解释。

程序负责：

1. 输出 schema 校验。
2. 引用来源校验。
3. citation role 分组。
4. `can_cite_clause` 条款引用门禁。
5. 节点级 retry 编排和 `review_failed` 错误上抛。

线上 LLM 模式不使用规则 fallback。规则路径只作为 baseline evaluation 对比；模型 API 失败、schema 校验失败、引用校验 retry 耗尽等系统故障必须显式返回 `review_failed`。

建议输出结构：

```json
{
  "risk_level": "medium",
  "conclusion": "该场景可能涉及个人信息跨境提供，但是否触发安全评估仍需补充数据规模等信息。",
  "trigger_reasons": [],
  "review_facts_summary": {},
  "applicable_evidence": {
    "legal_basis": [],
    "conditional_basis": [],
    "implementation_reference": [],
    "policy_explanation": []
  },
  "missing_information": [],
  "recommended_actions": [],
  "risk_boundaries": [],
  "citations": []
}
```

引用规则：

1. `can_cite_clause=True` 才能作为条款级法律依据。
2. TC260/GB/T 写成实施参考或参考标准。
3. 官方问答写成政策口径补充。
4. 地方/行业材料必须说明适用范围。
5. 不得编造未召回来源。

## 前端接线范围

第二阶段前端从 mock 变成单用户真实审查工作台：

1. 支持输入问题。
2. 支持粘贴材料。
3. 支持 PDF/DOCX beta 上传。
4. 调用真实 review API。
5. 展示 `ReviewFacts`。
6. 展示 LLM query plan。
7. 展示证据状态和二次召回状态。
8. 展示结构化审查结果。
9. 展示引用来源分组。
10. 展示缺失信息、建议动作和风险边界。
11. 展示 `review_failed` 的失败节点、说明、尝试次数和 trace id。
12. 评测看板展示最新 eval run 指标和 bad cases。

不默认展示 raw prompt、raw model output、validation errors、token usage、清洗前后文本、chunk 列表、embedding 向量、索引构建细节。

## 评估设计

第二阶段评估聚焦检索和引用，不做完整回答质量平台。

指标：

1. Recall@3
2. Recall@5
3. MRR@10
4. 拒答准确率
5. 二次召回命中提升
6. citation rule violation count

评估模式：

1. `rule_baseline`: deterministic rules only, used for comparison.
2. `local`: local hybrid retrieval core.
3. `service`: Elasticsearch + pgvector fused retrieval; either service missing is a failure.
4. `llm`: DeepSeek-owned fact extraction, query planning, evidence check, and result generation.

黄金集以场景审查题为主，条款定位题只作为 sanity check。

每个场景 case 建议包含：

1. `case_id`
2. `question`
3. `material_text`
4. `expected_facts`
5. `expected_sources`
6. `expected_citation_roles`
7. `should_trigger_second_retrieval`
8. `should_abstain`
9. `must_not_cite_as_clause`
10. `tags`

场景覆盖：

1. 数据出境安全评估触发条件。
2. 标准合同备案。
3. 个人信息保护认证。
4. 汽车数据出境。
5. 金融信息服务数据分类分级。
6. 上海、广东、天津、福建、广西、重庆、浙江等地区负面清单。
7. TC260/GB/T 标准类落地问题。
8. 官方问答口径补充问题。
9. 证据不足或知识库外拒答。

## 工程任务顺序

### Step 1: Schema 和本地 artifact 读写

1. 新增 `law_agent.review` 包。
2. 定义 `ReviewFacts`、`ReviewCase`、`RetrievalQuery`、`RetrievalTrace`、`ReviewResult`。
3. 实现从 `chunks.jsonl` 加载 chunk。
4. 实现 review case 和 trace 的 JSONL 保存。

### Step 2: Fact extraction 和 query planning

1. 实现最小 DeepSeek client wrapper。
2. 实现 DeepSeek fact extraction 节点。
3. 实现 DeepSeek query planning 节点。
4. 为两个节点增加 JSON 示例 prompt、Pydantic 严格校验和节点级 retry。
5. 测试缺失信息、地区/行业字段抽取、query 类型和 retry 耗尽后的 `review_failed`。

### Step 3: Local hybrid retrieval core

1. 实现 BM25/关键词 scorer。
2. 实现 vector mock retriever adapter。
3. 实现 metadata boost。
4. 实现 RRF。
5. 实现邻近 chunk 补充。
6. 输出完整 trace。

### Step 4: Evidence self-check 和 citation validator

1. 实现 DeepSeek evidence check 节点。
2. 实现一次二次召回。
3. 实现 citation role 分组。
4. 实现 `can_cite_clause` 校验。
5. 实现证据不足审查结果和 `review_failed` 的区分。

### Step 5: Structured review generation

1. 实现结构化审查结果 schema。
2. 接入 DeepSeek 生成结构化审查结果。
3. 为 result generation 增加 JSON 示例 prompt、Pydantic 严格校验和节点级 retry。
4. 程序化校验引用和风险边界。
5. 引用校验失败后重试 result generation；重试耗尽返回 `review_failed`。

### Step 6: Evaluation

1. 新建 scenario golden set。
2. 实现 Recall@3、Recall@5、MRR@10。
3. 实现拒答准确率、二次召回提升、citation violation 和 `review_failed` 统计。
4. 支持 `rule_baseline`、`local`、`service`、`llm` 模式对比。
5. 输出 bad cases JSON/Markdown/前端可读数据。

### Step 7: Review API 和前端接线

1. 新增本地 review API。
2. 前端提交问题和材料。
3. API 支持成功响应和结构化 `review_failed` 响应。
4. 前端展示 facts、query plan、证据、二次召回、结果、引用、trace 摘要。
5. 前端评测看板读取 eval run 输出。

### Step 8: 服务后端增强

1. 接 PostgreSQL/pgvector adapter。
2. 接 Elasticsearch adapter。
3. 增加 corpus index 脚本。
4. `service` 模式要求 ES + pgvector 都可用并融合检索。
5. 使用同一 golden set 对比 `local`、`service`、`llm` 和 `rule_baseline`。
6. 评估稳定后再决定是否引入 reranker。

## 验收清单

第二阶段必达：

1. 能加载当前 42 份清洗后的法规/政策 chunk。
2. 能创建审查案卷并处理粘贴材料。
3. PDF/DOCX 上传 beta 能通过 Docling 或现有 parser 进入同一流程。
4. 能用 DeepSeek 抽取固定 `ReviewFacts`。
5. 能执行本地 BM25/vector mock/RRF/metadata boost。
6. 能用 DeepSeek 证据自检最多触发一次受控二次召回。
7. 能用 DeepSeek 输出结构化审查结果。
8. 能强制 citation policy。
9. 能保存 `ReviewCase` 和 `RetrievalTrace` JSONL。
10. 前端能调用真实 review API。
11. 前端能展示 LLM trace 摘要和结构化 `review_failed`。
12. 评估能跑 scenario golden set。
13. 能输出 Recall@3、Recall@5、MRR@10、拒答准确率、二次召回提升、`review_failed` 率和 bad cases。
14. 至少跑通 3 个端到端 demo 场景：数据出境/标准合同、行业条件、地区负面清单。
15. 测试覆盖 schema、retriever、RRF、citation validator、eval metrics、LLM 节点 retry 和至少一条端到端审查流程。

第二阶段增强：

1. PostgreSQL/pgvector adapter。
2. Elasticsearch adapter。
3. corpus index 脚本。
4. 真实 embedding。
5. reranker 评估。
6. 解析质量专项评估。
7. 完整回答质量评估平台。
