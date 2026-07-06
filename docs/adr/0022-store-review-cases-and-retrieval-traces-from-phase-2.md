# Store Review Cases and Retrieval Traces from Phase 2

LawAgent Phase 2 stores review cases and retrieval traces as first-class artifacts from the beginning. The initial implementation may use local JSONL files while the local retrieval core is being built, but each run should preserve the user question, material text or parsed text, extracted review facts, generated queries, BM25/vector/hybrid results, metadata boosts, second-retrieval triggers, evidence self-check outcome, final citations, abstention or missing-information reasons, and user feedback.

These traces support the user-visible evidence process, retrieval evaluation, and bad-case review, and can later be moved into PostgreSQL without changing the product loop.
