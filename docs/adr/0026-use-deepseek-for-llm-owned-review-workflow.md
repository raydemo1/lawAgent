# Use DeepSeek for the LLM-Owned Review Workflow

LawAgent will introduce LLM behavior into the material-driven review workflow through DeepSeek first, without adding a provider capability abstraction or rule fallback path. DeepSeek prompts must include a target JSON example, model output is validated by strict Pydantic schemas at each LLM node, and node-level retry exhaustion returns a structured `review_failed` result with trace information.

Rules remain useful as baseline evaluation modes, but online LLM review does not silently fall back to rules because that would hide model, schema, retrieval, or citation failures behind a different decision system.
