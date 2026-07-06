# Limit Second Retrieval to One Controlled Pass

LawAgent Phase 2 allows one controlled second-retrieval pass when evidence self-check detects missing primary legal basis, missing matching local or industry evidence, weak authority, mismatch with review facts, or insufficient support for the concrete material scenario. The second pass may rewrite queries, add fact keywords, boost region/industry metadata, expand topK, or fetch neighboring chunks, but it does not loop indefinitely.

If evidence remains insufficient after the second pass, the review result must ask for missing information or abstain instead of generating an unsupported legal conclusion.
