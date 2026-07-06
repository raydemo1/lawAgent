# Scope Phase 2 Evaluation to Retrieval and Citations

LawAgent Phase 2 includes an evaluation loop, but scopes it to retrieval and citation behavior: golden retrieval cases, BM25/vector/hybrid/second-retrieval baselines, Recall@3, Recall@5, MRR@10, abstention accuracy, second-retrieval lift, bad-case output, and citation-rule checks. Full answer-quality evaluation with LLM judges, RAGAS-style scoring, long-term human feedback loops, and broad generation-quality dashboards belongs after the retrieval loop is proven.

This keeps evaluation close to the highest-risk Phase 2 claims: hybrid retrieval improves evidence recall, and citation governance prevents non-authoritative materials from being presented as clause-level legal basis.
