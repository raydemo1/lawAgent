# LawAgent Phase 2 Issue Specs

This document is the draft `to-issues` breakdown for Phase 2. It is not yet published to an external issue tracker. Each issue is written as an independently grabbable implementation spec with concrete code notes, acceptance criteria, tests, and known non-goals.

The slices intentionally start with local CLI/file behavior before API and frontend wiring. That matches the current repository: the codebase is a Python package with JSONL helpers and argparse commands, and no frontend app is currently checked in.

## Proposed Breakdown

1. **Make Phase 2 planning assets trackable**
   - Blocked by: None
   - User stories covered: project maintainability, future agent handoff

2. **Create traceable review case skeleton**
   - Blocked by: Issue 1
   - User stories covered: enterprise data compliance reviewer can start a material review case and get a persisted trace
   - Detailed spec: [Issue 02 review case skeleton](./phase-2/issues/02-review-case-skeleton.md)

3. **Support pasted text and Docling-backed uploaded material input**
   - Blocked by: Issue 2
   - User stories covered: reviewer can use pasted text as the stable path and PDF/DOCX upload as beta input

4. **Extract review facts and plan retrieval queries**
   - Blocked by: Issue 2
   - User stories covered: reviewer sees the system's understanding of business facts before evidence retrieval

5. **Load the cleaned corpus and run keyword baseline retrieval**
   - Blocked by: Issue 2
   - User stories covered: reviewer can retrieve evidence from the 42-document cleaned corpus

6. **Add hybrid retrieval with vector mock, metadata boosts, RRF, and neighbor chunks**
   - Blocked by: Issues 4 and 5
   - User stories covered: reviewer gets a richer evidence set than keyword-only search

7. **Add evidence self-check and one controlled second retrieval**
   - Blocked by: Issue 6
   - User stories covered: reviewer sees when evidence is insufficient and whether the system performed a second retrieval

8. **Validate citations and generate structured review results**
   - Blocked by: Issues 4 and 7
   - User stories covered: reviewer gets risk, missing information, recommended actions, risk boundaries, and governed citations

9. **Build scenario golden set and retrieval/citation eval runner**
   - Blocked by: Issues 6 and 8
   - User stories covered: project owner can prove hybrid retrieval and citation governance with metrics and bad cases

10. **Expose a local review API**
    - Blocked by: Issue 8
    - User stories covered: frontend can call the real review flow instead of mock data

11. **Wire the single-user frontend workbench to the review API**
    - Blocked by: Issues 9 and 10
    - User stories covered: reviewer can run a real material review and see evidence, citations, and eval output in the UI

12. **Add pgvector and Elasticsearch adapters behind the local retriever interfaces**
    - Blocked by: Issues 6 and 9
    - User stories covered: project can compare local core behavior with service-backed retrieval

## Issue 1: Make Phase 2 Planning Assets Trackable

## What to build

Make Phase 2 planning documents, glossary, and ADRs visible to Git while keeping generated data, artifacts, and local scratch files ignored.

## Why this slice exists

The current `.gitignore` ignores all `docs/`, so the Phase 2 implementation plan, glossary changes, and ADRs are local-only. Before implementation starts, future agents need the product decisions in versioned project context.

## Implementation notes

- Update `.gitignore` to stop ignoring all `docs/`.
- Keep generated reports and local scratch docs ignored explicitly, for example `docs/data_governance_report.md` if it reappears.
- Do not unignore `artifacts/`, `.env`, or generated `/data/` results.
- Verify `docs/CONTEXT.md`, `docs/implementation-plan-phase-2.md`, and `docs/adr/*.md` show as trackable.

## Acceptance criteria

- [ ] `git status --short` shows Phase 2 docs as normal untracked/modified files, not ignored files.
- [ ] Generated `artifacts/`, `.env`, and local data outputs remain ignored.
- [ ] No data corpus artifacts are accidentally made trackable.

## Tests

- No unit tests required.
- Run `git check-ignore -v docs/implementation-plan-phase-2.md` and confirm it does not match.
- Run `git check-ignore -v artifacts/review/legal_docs_20260702/chunks.jsonl` and confirm it remains ignored.

## Non-goals

- Do not stage or commit files.
- Do not move existing docs.

## Issue 2: Create Traceable Review Case Skeleton

## What to build

Create the `law_agent.review` package with Pydantic models and JSONL persistence for a review case and retrieval trace. Add a CLI command that creates a review case from a question and pasted material, writes a trace, and emits a minimal structured response.

## Why this slice exists

Every later slice needs stable review IDs, trace IDs, model shapes, and JSONL round trips. This is the narrowest end-to-end skeleton: input material in, review case and trace out.

## Implementation notes

- Add `law_agent/review/`.
- Suggested files:
  - `law_agent/review/__init__.py`
  - `law_agent/review/schemas.py`
  - `law_agent/review/io.py`
  - `law_agent/review/cli.py`
  - `law_agent/review/__main__.py`
- Follow `law_agent.data.schemas.StrictModel`: `ConfigDict(extra="forbid")`.
- Prefer reusing `law_agent.data.io.write_jsonl/read_jsonl` when possible.
- Suggested models:
  - `ReviewFacts`
  - `ReviewCase`
  - `RetrievalQuery`
  - `RetrievalHit`
  - `RetrievalTrace`
  - `Citation`
  - `ReviewResult`
- Suggested command:

```powershell
python -m law_agent.review run `
  --question "这个场景是否需要数据出境安全评估？" `
  --material-file samples/review/app_cross_border.txt `
  --output-dir artifacts/review_runs
```

- The first implementation can write empty `review_facts`, no retrieval hits, and a result with `risk_level="insufficient_evidence"`.
- Generate IDs deterministically enough for tests by allowing injectable clock/id factory or by testing shape instead of exact ID.

## Acceptance criteria

- [ ] A user can run a review CLI command with a question and material text.
- [ ] A `ReviewCase` JSONL record is written.
- [ ] A `RetrievalTrace` JSONL record is written.
- [ ] The command prints the review case ID and output file paths.
- [ ] Models reject unknown fields.

## Tests

- Add `tests/test_review_schemas.py`.
- Add `tests/test_review_io.py`.
- Add `tests/test_review_cli.py`.
- Cover required fields, `extra="forbid"`, JSONL roundtrip, and CLI success path.

## Non-goals

- No LLM calls.
- No retrieval.
- No frontend.

## Issue 3: Support Pasted Text and Docling-Backed Uploaded Material Input

## What to build

Add a material input layer that accepts either pasted text or an uploaded local PDF/DOCX path, normalizes it into review material text, and records parser metadata in the review case.

## Why this slice exists

Pasted text is the stable Phase 2 path, while PDF/DOCX upload is a beta path. Both must feed the same review flow without turning Phase 2 into a parser-quality project.

## Implementation notes

- Add `law_agent/review/materials.py`.
- Suggested model:
  - `MaterialInput`
  - `ParsedMaterial`
  - `UploadedFileMeta`
- For pasted text, return text directly with parser `"pasted_text"`.
- For file input:
  - Construct a temporary `SourceRecord` with `source_site="user_upload"`.
  - Reuse `normalize_source()` from `law_agent.data.normalize`.
  - For `.docx`, current auto parser uses the standard library docx parser.
  - For `.pdf` and images, current auto parser routes to Docling.
- Do not run full enrich/chunk on user material in this issue.
- Add review CLI flags:
  - `--material-text`
  - `--material-file`
  - exactly one required
- Preserve parser and parser version in `ReviewCase`.

## Acceptance criteria

- [ ] Pasted text review creates material text without parser dependencies.
- [ ] DOCX/PDF file input goes through the existing normalize route.
- [ ] Parser metadata is persisted.
- [ ] Parser failures are recorded as review errors instead of crashing with an unclear stack trace.

## Tests

- Test pasted text path.
- Test `.pdf` path by monkeypatching `_docling_to_text`, mirroring `tests/test_normalize_docx.py`.
- Test invalid extension or parser failure produces a structured error.

## Non-goals

- No parser quality scoring.
- No complex scanned PDF support guarantee.
- No file upload HTTP endpoint yet.

## Issue 4: Extract Review Facts and Plan Retrieval Queries

## What to build

Extract fixed `ReviewFacts` from review material and generate typed retrieval queries from the user question plus extracted facts.

## Why this slice exists

Phase 2 retrieval should not be a raw user-query search. The review facts are the bridge between concrete business material and metadata-aware legal evidence retrieval.

## Implementation notes

- Add `law_agent/review/facts.py`.
- Add `law_agent/review/query_planner.py`.
- Start with a deterministic rules extractor so tests do not depend on LLM:
  - detect cross-border terms: `境外`, `出境`, country/region names such as `新加坡`, `香港`
  - detect common data types: `手机号`, `定位`, `设备ID`, `行为日志`, `身份证`, `人脸`
  - detect sensitive personal information hints: `定位`, `人脸`, `身份证`, `医疗`, `金融账户`
  - detect industry hints: `汽车`, `智能网联`, `金融信息服务`
  - detect region hints: `上海`, `广东`, `天津`, `福建`, `广西`, `重庆`, `浙江`, `海南`, `北京`, `深圳`
- Keep an LLM adapter interface but do not require it for tests.
- Suggested query types:
  - `legal_issue`
  - `material_fact`
  - `region_condition`
  - `industry_condition`
  - `missing_information`
- Persist query plan into `RetrievalTrace`.

## Acceptance criteria

- [ ] A pasted material case produces populated `ReviewFacts`.
- [ ] Missing required facts are listed in `missing_information`.
- [ ] Query planner produces multiple typed queries.
- [ ] Query plan is persisted in trace.

## Tests

- Cross-border app sample extracts data types, cross-border flag, overseas recipient, and missing consent/threshold facts.
- Automotive sample extracts industry condition.
- Regional negative-list sample extracts region.
- Query planner emits expected query types.

## Non-goals

- No final legal judgment.
- No production-grade NER.
- No mandatory LLM dependency.

## Issue 5: Load the Cleaned Corpus and Run Keyword Baseline Retrieval

## What to build

Load the cleaned Phase 1 corpus chunks and implement a local keyword/BM25-style baseline retriever that returns scored evidence hits for a review case.

## Why this slice exists

This is the first slice that proves review cases can retrieve from the real 42-document cleaned corpus. It also gives the eval runner a baseline.

## Implementation notes

- Add `law_agent/review/corpus.py`.
- Add `law_agent/review/retrieval/keyword.py`.
- Use `law_agent.data.io.read_jsonl(Path, Chunk)` to load chunks.
- Default chunks path should point to `artifacts/review/legal_docs_20260702/chunks.jsonl`, but allow `--chunks` override.
- Implement a simple dependency-free scorer:
  - normalize Chinese punctuation and lowercase ASCII
  - tokenize into Chinese character bigrams plus contiguous ASCII/number tokens
  - score by query token overlap, title/citation label boosts, and exact phrase boosts
  - call it `KeywordRetriever` if it is not mathematically full BM25 yet
- Record top hits in `RetrievalTrace.keyword_results`.
- Add CLI:

```powershell
python -m law_agent.review retrieve --case-id ... --chunks artifacts/review/legal_docs_20260702/chunks.jsonl
```

## Acceptance criteria

- [ ] Loads current `chunks.jsonl` without schema errors.
- [ ] Query for data export safety assessment returns relevant data export sources near top.
- [ ] Retrieval hit includes chunk ID, source ID, title, score, matched query type, citation role, and `can_cite_clause`.
- [ ] Results are written to trace.

## Tests

- Tiny in-memory chunk fixture proves keyword ranking.
- Corpus loader handles missing file with clear error.
- Retrieval trace serializes keyword hits.

## Non-goals

- No Elasticsearch.
- No vector retrieval.
- No answer generation.

## Issue 6: Add Hybrid Retrieval with Vector Mock, Metadata Boosts, RRF, and Neighbor Chunks

## What to build

Add the local hybrid retrieval core: keyword results, vector-mock results, metadata boosts, RRF fusion, and neighbor chunk expansion.

## Why this slice exists

This is the core Phase 2 retrieval claim. It should be verifiable locally before pgvector and Elasticsearch adapters exist.

## Implementation notes

- Add `law_agent/review/retrieval/vector_mock.py`.
- Add `law_agent/review/retrieval/fusion.py`.
- Add `law_agent/review/retrieval/boosts.py`.
- Add `law_agent/review/retrieval/neighbors.py`.
- Vector mock options:
  - score overlap against `text + title + topic_tags + legal_domain + applicable_subjects`
  - keep interface shaped like future vector adapter: `search(queries, top_k) -> list[RetrievalHit]`
- Metadata boost rules:
  - boost `primary_legal_basis` for national/default legal issue queries
  - boost matching `conditional_local_basis` when `ReviewFacts.region` is set
  - boost matching `conditional_industry_basis` when `ReviewFacts.industry` is set
  - boost `implementation_reference` for standard/operation queries
  - keep `interpretation_auxiliary` retrievable but lower authority
- RRF:
  - implement deterministic `rrf_score = sum(1 / (k + rank))`
  - apply metadata boost after or as a multiplier recorded separately
- Neighbor chunks:
  - use `prev_chunk_id` and `next_chunk_id` if present
  - add neighbors as supplemental evidence, not primary ranked hits

## Acceptance criteria

- [ ] Hybrid retrieval returns fused hits with component ranks and scores.
- [ ] Metadata boosts are visible in trace.
- [ ] Region and industry review facts affect ranking but do not hard-filter all other roles.
- [ ] Neighbor chunks are attached for top evidence.

## Tests

- RRF ordering with fixed ranks.
- Metadata boost elevates matching local/industry evidence.
- Non-matching evidence remains present.
- Neighbor expansion uses prev/next chunk IDs.

## Non-goals

- No real embedding API.
- No pgvector.
- No Elasticsearch.
- No reranker.

## Issue 7: Add Evidence Self-Check and One Controlled Second Retrieval

## What to build

Evaluate retrieved evidence for sufficiency and run at most one controlled second retrieval when evidence is weak or mismatched.

## Why this slice exists

The project needs Agentic RAG behavior without uncontrolled agent loops. Evidence self-check determines whether to answer, retrieve once more, or abstain/request missing facts.

## Implementation notes

- Add `law_agent/review/evidence.py`.
- Suggested models:
  - `EvidenceStatus`: `sufficient | needs_second_retrieval | insufficient`
  - `EvidenceIssue`
  - `SecondRetrievalPlan`
- Triggers:
  - no `primary_legal_basis`
  - region facts but no matching local evidence
  - industry facts but no matching industry evidence
  - only implementation/interpretation evidence
  - evidence does not match cross-border facts
  - critical facts are missing
- Second retrieval:
  - add legal terminology query expansions
  - add fact keywords
  - increase topK
  - apply stronger region/industry boost
  - fetch neighbors
- Persist `evidence_self_check` and `second_retrieval` in trace.

## Acceptance criteria

- [ ] Weak evidence triggers one second retrieval.
- [ ] Strong evidence does not trigger second retrieval.
- [ ] Second retrieval never loops more than once.
- [ ] Remaining insufficiency becomes a structured missing-information/abstention state.

## Tests

- No primary legal basis triggers second retrieval.
- Region fact without local evidence triggers second retrieval.
- Missing threshold facts can produce insufficient evidence.
- Guard that second retrieval count is max one.

## Non-goals

- No autonomous multi-agent loop.
- No LLM-as-judge.

## Issue 8: Validate Citations and Generate Structured Review Results

## What to build

Generate a governed `ReviewResult` from review facts and final evidence, with citation validation that prevents non-citable evidence from being presented as clause-level legal basis.

## Why this slice exists

This is where LawAgent stops being raw retrieval and becomes a legal compliance review assistant: it must separate legal basis, conditional basis, implementation references, and policy explanations.

## Implementation notes

- Add `law_agent/review/citations.py`.
- Add `law_agent/review/result_builder.py`.
- Use existing chunk fields:
  - `citation_role`
  - `can_cite_clause`
  - `citation_label`
  - `source_url`
  - `applicable_region`
  - `applicable_subjects`
- Citation groups:
  - `legal_basis`
  - `conditional_basis`
  - `implementation_reference`
  - `policy_explanation`
- Risk levels:
  - `high`
  - `medium`
  - `low`
  - `insufficient_evidence`
- Start with rule-based result building:
  - cross-border facts + relevant evidence -> medium unless specific high-risk triggers are present
  - missing threshold/consent/recipient facts -> missing info and risk boundary
  - insufficient evidence -> abstain
- Add an optional LLM structured-output adapter later, but keep the rule builder as test fallback.

## Acceptance criteria

- [ ] Review result contains risk level, conclusion, trigger reasons, missing information, actions, boundaries, and citations.
- [ ] Clause-level citations only use `can_cite_clause=True`.
- [ ] TC260/GB/T style evidence is grouped as implementation reference.
- [ ] Official Q&A evidence is grouped as policy explanation.
- [ ] Local/industry evidence includes scope wording.

## Tests

- Citation validator rejects non-citable clause citation.
- Grouping by citation role.
- Insufficient evidence result does not cite weak evidence as legal basis.
- Cross-border sample produces missing-information actions.

## Non-goals

- No polished final prose requirement.
- No freeform LLM answer as the source of truth.

## Issue 9: Build Scenario Golden Set and Retrieval/Citation Eval Runner

## What to build

Create a scenario-based golden set and an eval runner that compares keyword, vector mock, hybrid RRF, and hybrid plus second retrieval on retrieval and citation behavior.

## Why this slice exists

Phase 2 must prove the retrieval and citation loop, not just demo one hand-picked answer.

## Implementation notes

- Add `law_agent/review/evalset/`.
- Suggested files:
  - `schemas.py`
  - `cases.py`
  - `metrics.py`
  - `runner.py`
- Store sample cases under `data/eval/review_scenarios.example.jsonl` if tracked, or under `docs/examples/` if `/data/` ignore rules make that awkward.
- Case schema fields:
  - `case_id`
  - `question`
  - `material_text`
  - `expected_facts`
  - `expected_sources`
  - `expected_citation_roles`
  - `should_trigger_second_retrieval`
  - `should_abstain`
  - `must_not_cite_as_clause`
  - `tags`
- Metrics:
  - Recall@3
  - Recall@5
  - MRR@10
  - abstention accuracy
  - second-retrieval lift
  - citation rule violation count
- CLI:

```powershell
python -m law_agent.review eval `
  --cases docs/examples/review_scenarios.jsonl `
  --chunks artifacts/review/legal_docs_20260702/chunks.jsonl `
  --output artifacts/eval/review_eval_latest.json
```

## Acceptance criteria

- [ ] At least 10 scenario cases exist.
- [ ] Eval runner emits JSON summary and bad cases.
- [ ] Metrics compare at least keyword-only and hybrid modes.
- [ ] Citation violations are counted.

## Tests

- Metrics unit tests with small fake ranked lists.
- Bad case output includes expected and actual sources.
- Eval runner works with a tiny fixture corpus.

## Non-goals

- No RAGAS.
- No LLM-as-judge.
- No answer fluency scoring.

## Issue 10: Expose a Local Review API

## What to build

Expose the review flow through a local JSON API so the frontend can call real review behavior instead of static mock data.

## Why this slice exists

The frontend should connect to the actual review loop, but the current repo has no web framework dependency. The first API should be minimal and local-first.

## Implementation notes

- Prefer no new dependency for the first pass.
- Add `law_agent/review/server.py` using Python standard library `http.server` or `wsgiref.simple_server`.
- Endpoint:
  - `POST /review`
  - input: `question`, `material_text`, optional `material_file_path` for local beta testing
  - output: `ReviewResult`, `ReviewFacts`, evidence summary, trace ID
- Endpoint:
  - `GET /eval/latest`
  - output latest eval JSON if present
- Add CORS headers for local frontend dev.
- Keep server thin: call the same service function used by CLI.
- If standard library server becomes too painful, create a short ADR before adding FastAPI or another dependency.

## Acceptance criteria

- [ ] Local server starts with a documented command.
- [ ] `POST /review` returns structured JSON for pasted material.
- [ ] API response includes trace ID and citation groups.
- [ ] API errors are structured JSON.

## Tests

- Unit test the request handler service function directly.
- Optional integration test using `urllib.request` against a background server if reliable.

## Non-goals

- No authentication.
- No production deployment.
- No async job queue.

## Issue 11: Wire the Single-User Frontend Workbench to the Review API

## What to build

Connect the current Superhost/frontend mock or a minimal checked-in frontend shell to the local review API, showing real review facts, structured result, evidence status, citations, missing information, and eval output.

## Why this slice exists

Phase 2 should be demoable by a user, not just through CLI output.

## Implementation notes

- First inspect whether the Superhost mock exists outside the repo and decide whether to import it.
- If no frontend code exists, create a minimal frontend app only after confirming the stack. Options:
  - static HTML/JS for local demo with no build dependency
  - Vite/React if the project accepts adding Node tooling
- The existing repo currently has no `package.json`, so do not assume React/Next is available.
- Required UI sections:
  - question input
  - pasted material input
  - optional file path/upload beta control
  - extracted facts panel
  - structured review result
  - evidence status and second retrieval badge
  - grouped citations
  - missing information and recommended actions
  - latest eval metrics and bad cases
- Do not expose chunk debug, embedding vectors, or cleaning pipeline internals.

## Acceptance criteria

- [ ] User can submit pasted material and question from the UI.
- [ ] UI calls real `POST /review`.
- [ ] UI displays `ReviewFacts` and structured result.
- [ ] UI displays grouped citations and evidence status.
- [ ] UI can show latest eval metrics.

## Tests

- If static frontend: use Playwright or browser verification to submit one scenario and inspect rendered sections.
- If React/Vite: add component-level or e2e smoke tests according to chosen stack.

## Non-goals

- No auth.
- No team history.
- No knowledge-base admin.
- No parser-quality correction UI.

## Issue 12: Add pgvector and Elasticsearch Adapters Behind the Local Retriever Interfaces

## What to build

Implement service-backed retrieval adapters for PostgreSQL/pgvector and Elasticsearch behind the same retriever interfaces used by the local hybrid core, then compare eval results against the local core.

## Why this slice exists

The target architecture is dual retrieval storage, but service integration should not disrupt the already-proven product loop.

## Implementation notes

- Keep local retriever as baseline.
- Add adapter interfaces before concrete clients if they are not already extracted:
  - `KeywordSearchAdapter`
  - `VectorSearchAdapter`
  - `HybridRetriever`
- Add dependencies only after confirming required client libraries and service availability.
- Store DB/ES connection config in `.env`, never hard-code.
- Add import/index scripts:
  - read `chunks.jsonl`
  - upsert chunk metadata and text
  - upsert embeddings for vector search when embedding provider is configured
  - index text and metadata into Elasticsearch
- Reuse the same eval runner to compare local and service modes.

## Acceptance criteria

- [ ] Local mode still passes eval.
- [ ] pgvector adapter can return vector hits for a tiny test index or mocked client.
- [ ] Elasticsearch adapter can return keyword hits for a tiny test index or mocked client.
- [ ] Eval runner supports backend selection.
- [ ] Documentation explains required services and env vars.

## Tests

- Mock adapter tests without running external services.
- Optional integration tests gated behind env vars.
- Eval runner backend selection tests.

## Non-goals

- No Milvus.
- No reranker unless eval data justifies it.
- No production ops/deployment work.

## Recommended Implementation Order

Start with Issues 1 and 2. They are boring in the best possible way: once schemas, trace persistence, and a CLI skeleton exist, every later issue has a stable place to plug into.

Then implement Issues 4 and 5 in parallel if desired: fact/query planning and keyword retrieval are independent after the skeleton.

Issue 6 is the core retrieval milestone. Issue 7 and Issue 8 turn retrieval into governed review. Issue 9 proves behavior with eval. Issue 10 and Issue 11 make it demoable. Issue 12 is the service-backend enhancement after the local loop is already useful.

## Open Questions Before Publishing

1. Should Issue 1 be done immediately, even though it changes `.gitignore` and makes docs trackable?
2. Should Issue 11 use the existing Superhost mock if it lives outside the repo, or should we create a minimal checked-in frontend shell?
3. For Issue 10, do we accept a dependency-free standard-library local server first, or do we want to approve FastAPI explicitly?
4. Should service-backed pgvector/Elasticsearch remain in Phase 2 issue list, or be moved to Phase 3 after local eval stabilizes?
