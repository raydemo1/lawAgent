# Build Local Retrieval Core Before Service Backends

LawAgent Phase 2 first builds a local hybrid retrieval core over the existing `chunks.jsonl` artifact, including metadata filters, scoring/boosting, RRF fusion, citation policy, trace output, and evaluation metrics. PostgreSQL/pgvector and Elasticsearch remain the target service backends, but they should replace the storage/search adapters after the product and evaluation loop is running.

This reduces infrastructure risk and lets the team validate review facts, retrieval strategy, citation behavior, and eval cases before committing debugging time to database and search service integration.
