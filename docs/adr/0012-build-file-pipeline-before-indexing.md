# Build the File Pipeline Before Database Indexing

LawAgent 第一阶段前半段先用 JSONL 文件流水线贯穿 manifest、normalized、cleaned、enriched、chunks 和 eval 产物，等采集、清洗、语义增强和分块逻辑稳定后，再实现 PostgreSQL/pgvector 与 Elasticsearch 的索引导入。这个顺序减少早期基础设施阻塞，也让数据治理逻辑更容易测试和复盘。
