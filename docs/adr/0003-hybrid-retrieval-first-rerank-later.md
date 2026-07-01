# Build Hybrid Retrieval First and Keep Rerank Optional

LawAgent 第一版的高精度检索先实现向量检索、关键词/BM25 检索、RRF 融合和父文档补充，以解决法规政策问题中的语义匹配、精确术语命中和上下文缺失问题。真实 reranker 暂不作为第一阶段硬依赖，但保留接口和评测位，后续通过 Recall、MRR、耗时对比决定是否接入。
