# Evaluate Against Retrieval Baselines

LawAgent 第一版评测必须包含 baseline 对比，而不是只报告最终效果。检索层至少比较 pgvector 向量检索、Elasticsearch BM25、混合检索和 Agentic RAG 四组结果，用 Recall@3、Recall@5、MRR@10、二次召回命中提升和拒答准确率说明混合检索、父文档补充和二次召回带来的真实增益。
