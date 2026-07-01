# Use PostgreSQL/pgvector with Elasticsearch for First-Version Retrieval

LawAgent 第一版采用 PostgreSQL/pgvector + Elasticsearch 的双检索存储方案。PostgreSQL 作为主数据源保存文档、chunk、元数据、会话、trace、评测和向量索引，Elasticsearch 承担关键词/BM25 检索、中文术语匹配和后续搜索调优；RRF 在应用层融合两路召回。第一版不引入 Milvus，因为当前规模更需要可解释的混合检索、事务一致性和低运维复杂度；当 chunk 数量、并发或向量召回延迟证明 pgvector 成为瓶颈时，再以评测数据驱动迁移到 Milvus。
