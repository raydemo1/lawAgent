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
        json={
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
        json={
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
        json={
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
        json={
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
        json={
            "material_text": "材料",
        },
    )

    assert response.status_code == 422


def test_review_missing_material_text_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/review",
        json={
            "question": "问题",
        },
    )

    assert response.status_code == 422


def test_review_empty_body_returns_422(client: TestClient) -> None:
    response = client.post("/api/review", json={})
    assert response.status_code == 422


def test_review_abstention_case(client: TestClient) -> None:
    """Vague material should produce insufficient_evidence risk level."""

    response = client.post(
        "/api/review",
        json={
            "question": "这个数据处理活动是否合规？",
            "material_text": "我们处理一些数据。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    result = data["review_result"]
    # Should either abstain or have low risk
    assert result["risk_level"] in ("insufficient_evidence", "low")


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
