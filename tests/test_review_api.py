"""Tests for the FastAPI review API (Issue 10)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from law_agent.data.io import write_jsonl
from law_agent.review.api import create_app

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixture_corpus(tmp_path: Path) -> Path:
    """Write fixture chunks to a temp file and return the path."""

    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(chunks_path, FIXTURE_CHUNKS)
    return chunks_path


@pytest.fixture
def client(fixture_corpus: Path) -> TestClient:
    """Create a TestClient with the fixture corpus."""

    app = create_app(chunks_path=fixture_corpus)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/review
# ---------------------------------------------------------------------------

def test_review_returns_structured_response(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        data={
            "question": "这个场景是否需要数据出境安全评估？",
            "material_text": "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "review_case_id" in data
    assert "trace_id" in data
    assert "review_facts" in data
    assert "review_result" in data
    assert "evidence_self_check" in data
    assert "citation_groups" in data
    assert "second_retrieval_triggered" in data

    # Review facts should be populated
    facts = data["review_facts"]
    assert facts["cross_border_transfer"] is True

    # Review result should have risk level and conclusion
    result = data["review_result"]
    assert result["risk_level"] in ("high", "medium", "low", "insufficient_evidence")
    assert result["conclusion"]
    assert len(result["conclusion"]) > 10  # not placeholder

    # Citation groups should be present
    assert isinstance(data["citation_groups"], list)


def test_review_includes_trace_id(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        data={
            "question": "数据出境安全评估",
            "material_text": "手机号发送给新加坡。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"]
    assert data["trace_id"].startswith("trace_")


def test_review_includes_citation_groups(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        data={
            "question": "数据出境安全评估",
            "material_text": "手机号发送给新加坡。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    groups = data["citation_groups"]
    assert len(groups) > 0

    # Each group should have usage and citations
    for group in groups:
        assert "usage" in group
        assert "citations" in group
        assert group["usage"] in (
            "legal_basis",
            "conditional_basis",
            "implementation_reference",
            "policy_explanation",
        )


def test_review_blank_question_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        data={
            "question": "   ",
            "material_text": "材料",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_review_missing_question_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        data={
            "material_text": "材料",
        },
    )

    assert response.status_code == 422


def test_review_missing_material_text_returns_400(client: TestClient) -> None:
    """When no material_text and no file are provided, returns 400."""
    response = client.post(
        "/api/review",
        data={
            "question": "问题",
        },
    )

    assert response.status_code == 400


def test_review_empty_body_returns_422(client: TestClient) -> None:
    """When question is missing entirely (required Form field), returns 422."""
    response = client.post("/api/review", data={})
    assert response.status_code == 422


def test_review_abstention_case(client: TestClient) -> None:
    """Vague material should produce insufficient_evidence risk level."""

    response = client.post(
        "/api/review",
        data={
            "question": "这个数据处理活动是否合规？",
            "material_text": "我们处理一些数据。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    result = data["review_result"]
    # Should either abstain or have low risk
    assert result["risk_level"] in ("insufficient_evidence", "low")


def test_review_with_file_upload(client: TestClient) -> None:
    """POST /api/review with a file upload should extract text and run review."""

    # Create a simple .txt file as test material
    file_content = "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。"

    response = client.post(
        "/api/review",
        data={
            "question": "这个场景是否需要数据出境安全评估？",
        },
        files={
            "file": ("test_material.txt", file_content.encode("utf-8"), "text/plain"),
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "review_case_id" in data
    assert "trace_id" in data
    assert data["review_facts"]["cross_border_transfer"] is True
    assert data["review_result"]["risk_level"] in ("high", "medium", "low", "insufficient_evidence")


# ---------------------------------------------------------------------------
# GET /api/eval/latest
# ---------------------------------------------------------------------------

def test_eval_latest_returns_404_when_not_run(client: TestClient) -> None:
    response = client.get("/api/eval/latest")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_eval_latest_returns_summary_after_run(client: TestClient) -> None:
    # First trigger an eval run
    run_response = client.post("/api/eval/run")
    assert run_response.status_code == 200

    # Then get latest
    response = client.get("/api/eval/latest")
    assert response.status_code == 200
    data = response.json()
    assert "mode_metrics" in data
    assert "keyword" in data["mode_metrics"]
    assert "hybrid" in data["mode_metrics"]


def test_eval_cache_isolated_between_apps(fixture_corpus: Path) -> None:
    """Two separate app instances must NOT share the eval cache.

    Bug: ``_eval_cache`` was a module-level global, so running eval on one
    app polluted every other app instance. After running eval on app1,
    app2's ``GET /api/eval/latest`` must still return 404 (its own cache is
    empty), not app1's cached result.
    """

    app1 = create_app(chunks_path=fixture_corpus)
    app2 = create_app(chunks_path=fixture_corpus)
    client1 = TestClient(app1)
    client2 = TestClient(app2)

    # Run eval on app1 — this caches the result in app1's state only.
    run_response = client1.post("/api/eval/run")
    assert run_response.status_code == 200

    # app1 should now return the cached summary.
    latest1 = client1.get("/api/eval/latest")
    assert latest1.status_code == 200

    # app2 has its own, isolated cache — it must NOT see app1's result.
    latest2 = client2.get("/api/eval/latest")
    assert latest2.status_code == 404
    assert "detail" in latest2.json()


# ---------------------------------------------------------------------------
# POST /api/eval/run
# ---------------------------------------------------------------------------

def test_eval_run_returns_summary(client: TestClient) -> None:
    response = client.post("/api/eval/run")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert "mode_metrics" in data
    assert data["mode_metrics"]["keyword"]["total_cases"] > 0
    assert data["mode_metrics"]["hybrid"]["total_cases"] > 0


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def test_cors_headers_present(client: TestClient) -> None:
    response = client.options(
        "/api/review",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    # CORS preflight should return 200
    assert response.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in response.headers.keys()}


# ---------------------------------------------------------------------------
# OpenAPI docs
# ---------------------------------------------------------------------------

def test_openapi_docs_available(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema_available(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "LawAgent Review API"
    assert "/api/review" in data["paths"]
    assert "/api/health" in data["paths"]
    assert "/api/eval/latest" in data["paths"]
    assert "/api/eval/run" in data["paths"]
