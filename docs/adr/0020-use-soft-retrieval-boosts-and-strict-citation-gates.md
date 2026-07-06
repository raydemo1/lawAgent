# Use Soft Retrieval Boosts and Strict Citation Gates

LawAgent Phase 2 uses soft metadata boosts during retrieval and strict eligibility gates during citation. Primary legal basis, matching local rules, matching industry rules, implementation references, and interpretation materials can all be retrieved together with different weights, while final clause-level legal citations are limited to evidence marked `can_cite_clause=true`.

This avoids losing useful local, industry, standard, and policy-explanation materials during recall, while preventing non-authoritative or conditional evidence from being presented as nationwide legal basis.
