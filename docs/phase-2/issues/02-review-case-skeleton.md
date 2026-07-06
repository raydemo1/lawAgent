# Issue 02: Traceable Review Case Skeleton

## Status

Draft for review. Do not implement until this spec is accepted.

## Purpose

Create the minimum review-domain foundation that every later Phase 2 slice can plug into. This issue should let LawAgent create a material review case, persist the case, persist an empty retrieval trace, persist a placeholder review result, and return a structured response without doing fact extraction, retrieval, citation validation, API work, or frontend work.

This is the foundation for the product loop:

```text
question + material -> ReviewCase -> RetrievalTrace -> ReviewResult
```

## Existing Code To Reuse

Use existing project patterns instead of inventing a second style:

1. Pydantic models should follow `law_agent.data.schemas.StrictModel` behavior: `extra="forbid"`.
2. JSONL persistence should reuse or mirror `law_agent.data.io.write_jsonl` and `read_jsonl`.
3. CLI style should mirror `law_agent.data.cli`: small argparse commands and explicit path arguments.
4. Tests should mirror current unit-test style under `tests/`, with direct function calls where possible.

## Proposed Package Boundary

Add a new top-level package:

```text
law_agent/
  review/
    __init__.py
    __main__.py
    cli.py
    ids.py
    io.py
    schemas.py
    service.py
```

### Module Responsibilities

**`schemas.py`**
Owns review-domain Pydantic models only. It should not read files, generate IDs, call LLMs, retrieve chunks, or run CLI code.

**`ids.py`**
Small helpers for ID and timestamp generation. This makes tests deterministic by allowing dependency injection in `service.py`.

**`io.py`**
Owns review JSONL persistence. It can reuse `law_agent.data.io.write_jsonl/read_jsonl`, but should expose review-named functions so later code does not import data-pipeline internals everywhere.

**`service.py`**
Owns the first application service:

```text
create_review_case(question, material_text, output_dir, clock/id providers)
```

It assembles `ReviewCase`, placeholder `RetrievalTrace`, placeholder `ReviewResult`, writes JSONL records, and returns a response object for CLI/API reuse.

**`cli.py` / `__main__.py`**
Thin argparse wrapper. It should call `service.py`, print stable output, and avoid business logic.

## Data Model Draft

The exact field names are part of this issue's API. Keep them stable unless a later issue has a concrete reason to change them.

### ReviewInputMode

Literal:

```python
"pasted_text" | "uploaded_file"
```

Issue 02 only supports `pasted_text`. `uploaded_file` exists in the schema so Issue 03 can add it without changing `ReviewCase`.

### RiskLevel

Literal:

```python
"high" | "medium" | "low" | "insufficient_evidence"
```

Issue 02 always returns `insufficient_evidence`.

### ReviewFacts

Placeholder-ready model. Issue 04 will populate it.

Fields:

```python
business_activity: str | None = None
data_types: list[str] = []
sensitive_personal_info: bool | None = None
cross_border_transfer: bool | None = None
overseas_recipient: str | None = None
processing_purpose: str | None = None
legal_basis_or_consent: str | None = None
industry: str | None = None
region: str | None = None
missing_information: list[str] = []
```

Design note: use `None` when the system has not determined a fact, not `False`. This matters later because “not detected yet” and “known false” are different in compliance review.

### MaterialRecord

Fields:

```python
input_mode: ReviewInputMode
material_text: str
source_name: str | None = None
parser: str = "pasted_text"
parser_version: str = "0.1.0"
```

Issue 03 can add uploaded-file metadata, but Issue 02 should keep this narrow.

### RetrievalQuery

Fields:

```python
query_id: str
query_type: Literal[
  "legal_issue",
  "material_fact",
  "region_condition",
  "industry_condition",
  "missing_information"
]
text: str
```

Issue 02 writes an empty list. Issue 04 owns query planning.

### RetrievalHit

Fields:

```python
chunk_id: str
doc_id: str
source_id: str
title: str
text: str
score: float
rank: int
retriever: Literal["keyword", "vector_mock", "hybrid"]
citation_role: ClauseCitationRole
can_cite_clause: bool
source_url: str
```

Issue 02 writes empty lists. Issue 05 and Issue 06 populate hits.

### EvidenceSelfCheck

Fields:

```python
status: Literal["not_checked", "sufficient", "needs_second_retrieval", "insufficient"]
issues: list[str] = []
second_retrieval_triggered: bool = False
```

Issue 02 uses `not_checked`.

### Citation

Fields:

```python
source_id: str
chunk_id: str
title: str
citation_label: str | None = None
source_url: str
citation_role: ClauseCitationRole
can_cite_clause: bool
usage: Literal[
  "legal_basis",
  "conditional_basis",
  "implementation_reference",
  "policy_explanation"
]
```

Issue 02 writes an empty list.

### ReviewResult

Fields:

```python
review_result_id: str
review_case_id: str
trace_id: str
risk_level: RiskLevel
conclusion: str
trigger_reasons: list[str] = []
review_facts: ReviewFacts
missing_information: list[str] = []
recommended_actions: list[str] = []
risk_boundaries: list[str] = []
citations: list[Citation] = []
```

Issue 02 placeholder result:

```text
risk_level = insufficient_evidence
conclusion = "Review case created. Evidence retrieval has not run yet."
```

Design note: `ReviewResult` is persisted separately from `ReviewCase`. This keeps review inputs, traces, and generated results independently addressable. Later issues can rerun retrieval or result generation and write a new result without rewriting the original case.

### ReviewCase

Fields:

```python
review_case_id: str
created_at: str
question: str
material: MaterialRecord
review_facts: ReviewFacts
trace_id: str
latest_result_id: str | None = None
user_feedback: dict[str, str] = {}
```

`created_at` should be ISO 8601 UTC.

### RetrievalTrace

Fields:

```python
trace_id: str
review_case_id: str
created_at: str
queries: list[RetrievalQuery] = []
filters: dict[str, object] = {}
metadata_boosts: dict[str, float] = {}
keyword_results: list[RetrievalHit] = []
vector_results: list[RetrievalHit] = []
hybrid_results: list[RetrievalHit] = []
neighbor_chunks: list[RetrievalHit] = []
evidence_self_check: EvidenceSelfCheck
second_retrieval: dict[str, object] = {}
final_evidence: list[RetrievalHit] = []
citation_validation: dict[str, object] = {}
latency_ms: int | None = None
```

Design note: keep trace verbose and append-only. It is an evaluation and debugging artifact, not a user-facing response model.

### ReviewRunResponse

Returned by service and CLI as a convenience wrapper:

```python
review_case: ReviewCase
trace: RetrievalTrace
result: ReviewResult
case_path: str
trace_path: str
result_path: str
```

## Storage Layout

Default output directory:

```text
artifacts/review_runs/
  review_cases.jsonl
  retrieval_traces.jsonl
  review_results.jsonl
```

Rationale:

1. `artifacts/` is already ignored.
2. Review runs are generated local artifacts.
3. Cases, traces, and results are separate because they change at different rates.
4. Later API and eval code can read the same files during local development.

Allow `--output-dir` override for tests and reproducibility.

## CLI Draft

Command:

```powershell
python -m law_agent.review run `
  --question "这个场景是否需要数据出境安全评估？" `
  --material-text "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。" `
  --output-dir artifacts/review_runs
```

Issue 02 only supports `--material-text`. File input is deliberately left to Issue 03 so all file handling, including UTF-8 text files, PDF/DOCX beta parsing, parser metadata, and parser failure states, is designed in one material-input layer.

Expected stdout should be short and parseable by a human:

```text
Created review case review_...
Trace trace_...
Result result_...
Wrote artifacts/review_runs/review_cases.jsonl
Wrote artifacts/review_runs/retrieval_traces.jsonl
Wrote artifacts/review_runs/review_results.jsonl
```

## Service Flow

Pseudo-flow:

```text
validate question and material are non-empty
generate review_case_id
generate trace_id
generate review_result_id
create empty ReviewFacts
create placeholder ReviewResult
create ReviewCase with latest_result_id
create RetrievalTrace with evidence_self_check.status = not_checked
append ReviewCase to review_cases.jsonl
append RetrievalTrace to retrieval_traces.jsonl
append ReviewResult to review_results.jsonl
return ReviewRunResponse
```

## Validation Rules

1. `question` must not be blank.
2. `material_text` must not be blank.
3. `review_case_id` should start with `review_`.
4. `trace_id` should start with `trace_`.
5. `review_result_id` should start with `result_`.
6. All models reject unknown fields.
7. JSONL writes should create parent directories.

## Tests

Add:

```text
tests/test_review_schemas.py
tests/test_review_io.py
tests/test_review_cli.py
```

Required cases:

1. `ReviewFacts` accepts empty placeholder state.
2. Unknown fields are rejected.
3. `ReviewCase`, `RetrievalTrace`, and `ReviewResult` JSONL roundtrip.
4. `create_review_case` writes all three JSONL files.
5. CLI `run --material-text` succeeds and prints IDs.
6. CLI rejects blank question.
7. CLI rejects missing material text.

Use `tmp_path` for all file writes.

## Acceptance Criteria

1. `python -m law_agent.review --help` exits successfully.
2. `python -m law_agent.review run --question ... --material-text ...` writes review, trace, and result JSONL.
3. The written `ReviewCase` contains placeholder facts and points to `latest_result_id`.
4. The written `ReviewResult` has `risk_level == "insufficient_evidence"`.
5. The written `RetrievalTrace` has `evidence_self_check.status == "not_checked"`.
6. Tests for schema, IO, service, and CLI pass.

## Non-Goals

1. No fact extraction.
2. No LLM calls.
3. No retrieval.
4. No citation validation.
5. No HTTP API.
6. No frontend.
7. No file input of any kind.
8. No Docling upload parsing.

## Implementation Risk

Low. This issue introduces stable domain objects, so the main risk is over-designing. Keep the first version narrow and let later issues populate fields instead of expanding this issue into a whole review engine.

## Open Questions

1. Should review run JSONL live under `artifacts/review_runs/` or `artifacts/review/legal_docs_20260702/runs/`?
   - Recommendation: `artifacts/review_runs/`, because review runs are not part of the synchronized corpus bundle.
2. Should `ReviewResult` live inside `ReviewCase`, or should it be a separate JSONL artifact?
   - Decision: separate JSONL artifact. `ReviewCase.latest_result_id` points to the latest result.
3. Should Issue 02 include `--material-file` for UTF-8 text?
   - Decision: no. Issue 02 only accepts `--material-text`; all file input belongs to Issue 03.
