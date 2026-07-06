# Use Structured Review Output Before Freeform Generation

LawAgent Phase 2 generates review results through a controlled structure before any freeform prose: risk level, trigger reasons, review facts, applicable evidence groups, missing information, recommended actions, risk boundaries, and citations. LLMs may help with fact extraction, query rewriting, and final wording, but program logic owns the answer schema, citation grouping, and citation eligibility checks.

This makes retrieval and citation failures debuggable and prevents the model from presenting non-authoritative or conditional materials as clause-level legal basis.
