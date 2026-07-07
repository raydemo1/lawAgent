"""FastAPI application for the local review API (Issue 10).

Exposes the review flow through a local JSON API so the frontend can call
real review behavior. All business logic stays in ``service.py`` — this
module is a thin transport layer.

Endpoints:
- ``POST /api/review`` — run a full review case
- ``GET /api/eval/latest`` — get the latest cached eval summary
- ``POST /api/eval/run`` — trigger evaluation and cache result
- ``GET /api/health`` — health check
- ``GET /docs`` — OpenAPI interactive docs (provided by FastAPI)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from law_agent.review.evalset.runner import run_evaluation
from law_agent.review.evalset.schemas import EvalMode, EvalSummary
from law_agent.review.io import read_review_results, read_retrieval_traces
from law_agent.review.llm import ReviewWorkflowFailed
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH
from law_agent.review.schemas import (
    CitationGroup,
    EvidenceSelfCheck,
    ReviewFailedResponse,
    ReviewFacts,
    ReviewResult,
)
from law_agent.review.service import (
    DEFAULT_REVIEW_RUNS_DIR,
    ReviewMode,
    create_review_case,
    run_hybrid_retrieval,
)

RetrievalBackend = Literal["local", "service"]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    """Request body for POST /api/review."""

    question: str = Field(..., min_length=1, description="The review question")
    material_text: str = Field(..., min_length=1, description="The material text to review")


class ReviewResponse(BaseModel):
    """Response body for POST /api/review."""

    review_case_id: str
    trace_id: str
    review_facts: ReviewFacts
    review_result: ReviewResult
    evidence_self_check: EvidenceSelfCheck
    citation_groups: list[CitationGroup] = Field(default_factory=list)
    second_retrieval_triggered: bool = False


class HealthResponse(BaseModel):
    """Response body for GET /api/health."""

    status: str = "ok"


class EvalRunRequest(BaseModel):
    """Request body for POST /api/eval/run (all fields optional)."""

    chunks_path: str | None = Field(default=None, description="Custom path to chunks.jsonl")
    modes: list[EvalMode] | None = Field(
        default=None,
        description="Eval modes to run, e.g. rule_baseline/local/service/llm",
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Retrieval top_k")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    chunks_path: Path | str = DEFAULT_CHUNKS_PATH,
    review_mode: ReviewMode = "rule_baseline",
    retrieval_backend: RetrievalBackend = "local",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        chunks_path: Path to the corpus chunks.jsonl file.
    """

    app = FastAPI(
        title="LawAgent Review API",
        description="Local JSON API for material-driven legal compliance review.",
        version="0.1.0",
    )

    # CORS: allow local frontend dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store config in app state
    app.state.chunks_path = Path(chunks_path)
    app.state.review_mode = review_mode
    app.state.retrieval_backend = retrieval_backend
    # Per-app eval cache so two app instances never share eval results.
    app.state.eval_cache: dict[str, EvalSummary | None] = {"latest": None}

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""

        return HealthResponse(status="ok")

    @app.post("/api/review", response_model=ReviewResponse)
    async def run_review(
        request: Request,
        question: str | None = Form(default=None),
        material_text: str = Form(default=""),
        file: UploadFile | None = File(default=None),
    ) -> ReviewResponse | JSONResponse:
        """Run a full review case: create case, hybrid retrieval, build result.

        Accepts either:
        - JSON body: ``{"question": "...", "material_text": "..."}``
        - form field: ``question`` + ``material_text``
        - ``file``: uploaded document file (.txt, .md, .pdf, .docx, .html, .json)

        When a file is provided, it is saved to the review run directory and
        text is extracted using the project's docling pipeline. The file
        becomes part of the review case history (MaterialRecord.uploaded_file).

        Returns structured review result with facts, evidence self-check,
        citation groups, and trace IDs.
        """

        if file is None and question is None and _is_json_request(request):
            try:
                payload = ReviewRequest.model_validate(await request.json())
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=exc.errors())
            question = payload.question
            material_text = payload.material_text

        if question is None:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "type": "missing",
                    "loc": ["body", "question"],
                    "msg": "Field required",
                    "input": None,
                }],
            )

        question = question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question must not be blank")

        # Use a temp directory for the review run
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            try:
                if file is not None and file.filename:
                    # --- File upload mode ---
                    raw = await file.read()
                    if not raw:
                        raise HTTPException(
                            status_code=400, detail="uploaded file is empty"
                        )

                    # Save the file to the review run directory
                    uploads_dir = tmp_path / "uploads"
                    uploads_dir.mkdir(exist_ok=True)
                    saved_path = uploads_dir / Path(file.filename).name
                    saved_path.write_bytes(raw)

                    # Convert file to MaterialRecord (docling extraction)
                    from law_agent.review.materials import material_from_file

                    material_record = material_from_file(saved_path)

                    # Create review case with the material record
                    response = create_review_case(
                        question=question,
                        material=material_record,
                        output_dir=tmp_path,
                        review_mode=app.state.review_mode,
                    )
                else:
                    # --- Pasted text mode ---
                    if not material_text.strip():
                        raise HTTPException(
                            status_code=400,
                            detail="material_text or file must be provided",
                        )
                    response = create_review_case(
                        question=question,
                        material_text=material_text,
                        output_dir=tmp_path,
                        review_mode=app.state.review_mode,
                    )

                case_id = response.review_case.review_case_id
                trace_id = response.trace.trace_id

                # Run retrieval. ``service`` is fail-fast and never falls back
                # to the local vector mock.
                if app.state.retrieval_backend == "service":
                    from law_agent.review.service import run_service_retrieval

                    trace = run_service_retrieval(
                        case_id=case_id,
                        chunks_path=app.state.chunks_path,
                        output_dir=tmp_path,
                        review_mode=app.state.review_mode,
                    )
                else:
                    trace = run_hybrid_retrieval(
                        case_id=case_id,
                        chunks_path=app.state.chunks_path,
                        output_dir=tmp_path,
                        review_mode=app.state.review_mode,
                    )

                # Read the structured result
                results = read_review_results(tmp_path / "review_results.jsonl")
                if not results:
                    raise HTTPException(
                        status_code=500,
                        detail="review result was not generated",
                    )
                review_result = results[0]

                return ReviewResponse(
                    review_case_id=case_id,
                    trace_id=trace_id,
                    review_facts=response.review_case.review_facts,
                    review_result=review_result,
                    evidence_self_check=trace.evidence_self_check,
                    citation_groups=review_result.applicable_evidence,
                    second_retrieval_triggered=trace.evidence_self_check.second_retrieval_triggered,
                )
            except HTTPException:
                raise
            except ReviewWorkflowFailed as exc:
                failed = ReviewFailedResponse.model_validate(exc.to_response())
                return JSONResponse(status_code=200, content=failed.model_dump())
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"unexpected error during review: {exc}",
                )

    @app.get("/api/eval/latest")
    async def get_latest_eval() -> JSONResponse:
        """Get the latest cached evaluation summary.

        Returns 404 if no evaluation has been run yet.
        """

        cached = app.state.eval_cache.get("latest")
        if cached is None:
            raise HTTPException(
                status_code=404,
                detail="no evaluation has been run yet. POST /api/eval/run to trigger one.",
            )
        return JSONResponse(content=cached.model_dump())

    @app.post("/api/eval/run")
    async def trigger_eval(request: EvalRunRequest | None = None) -> JSONResponse:
        """Trigger evaluation and cache the result.

        Returns the full evaluation summary.
        """

        chunks = (
            Path(request.chunks_path) if request and request.chunks_path else app.state.chunks_path
        )

        try:
            summary = run_evaluation(
                chunks_path=chunks,
                modes=request.modes if request else None,
                top_k=request.top_k if request else 10,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"unexpected error during evaluation: {exc}",
            )

        app.state.eval_cache["latest"] = summary
        return JSONResponse(content=summary.model_dump())

    return app


def _is_json_request(request: Request) -> bool:
    """Return True when the request body is JSON."""

    content_type = request.headers.get("content-type", "").lower()
    return "application/json" in content_type


# ---------------------------------------------------------------------------
# Default app instance (for uvicorn import)
# ---------------------------------------------------------------------------

app = create_app()
