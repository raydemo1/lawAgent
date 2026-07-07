"""Tests for the FastAPI review API (Issue 10)."""

from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from law_agent.data.io import write_jsonl
from law_agent.review.llm import ReviewWorkflowFailed
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


def test_review_accepts_json_body_for_backward_compatibility(client: TestClient) -> None:
    """POST /api/review still accepts the original JSON API contract."""

    response = client.post(
        "/api/review",
        json={
            "question": "这个场景是否需要数据出境安全评估？",
            "material_text": "我们会将手机号发送给新加坡服务商。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["review_facts"]["cross_border_transfer"] is True
    assert data["review_result"]["conclusion"]


def test_review_workflow_failure_returns_structured_review_failed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workflow failures keep trace context instead of becoming HTTP 500."""

    def fail_review_case(*args, **kwargs):
        raise ReviewWorkflowFailed(
            failed_node="fact_extraction",
            reason="pydantic_validation_failed",
            message="事实抽取结果未通过结构化校验",
            attempts=3,
            trace_id="trace_failure",
        )

    monkeypatch.setattr("law_agent.review.api.create_review_case", fail_review_case)

    response = client.post(
        "/api/review",
        json={
            "question": "这个场景是否需要数据出境安全评估？",
            "material_text": "我们会将手机号发送给新加坡服务商。",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "review_failed",
        "failed_node": "fact_extraction",
        "reason": "pydantic_validation_failed",
        "message": "事实抽取结果未通过结构化校验",
        "attempts": 3,
        "trace_id": "trace_failure",
    }


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
    run_response = client.post(
        "/api/eval/run",
        json={"retrieval_mode": "local", "review_mode": "local"},
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] in ("running", "succeeded")
    _wait_for_eval_job(client)

    # Then get latest
    response = client.get("/api/eval/latest")
    assert response.status_code == 200
    data = response.json()
    assert "mode_metrics" in data
    assert "retrieval=local,review=local" in data["mode_metrics"]


def test_eval_run_accepts_retrieval_and_review_modes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/eval/run forwards explicit retrieval/review modes and top_k."""

    captured = {}

    def fake_run_evaluation(
        *,
        chunks_path,
        retrieval_mode="service",
        review_mode="llm",
        top_k=10,
        **kwargs,
    ):
        captured["chunks_path"] = chunks_path
        captured["retrieval_mode"] = retrieval_mode
        captured["review_mode"] = review_mode
        captured["top_k"] = top_k
        from law_agent.review.evalset.schemas import EvalSummary, ModeMetrics

        metrics = ModeMetrics(
            mode="retrieval=service,review=llm",
            mean_recall_at_3=0.5,
            mean_recall_at_5=0.5,
            mean_mrr_at_10=0.5,
            abstention_accuracy=1.0,
            second_retrieval_accuracy=1.0,
            total_citation_violations=0,
            bad_case_count=0,
            total_cases=1,
        )
        return EvalSummary(
            generated_at="2026-07-07T00:00:00+00:00",
            chunks_path=str(chunks_path),
            cases_path="default",
            mode_metrics={"retrieval=service,review=llm": metrics},
            bad_cases=[],
            all_case_results={"retrieval=service,review=llm": []},
        )

    monkeypatch.setattr("law_agent.review.api.run_evaluation", fake_run_evaluation)

    response = client.post(
        "/api/eval/run",
        json={"retrieval_mode": "service", "review_mode": "llm", "top_k": 7},
    )

    assert response.status_code == 200
    _wait_for_eval_job(client)
    assert captured["retrieval_mode"] == "service"
    assert captured["review_mode"] == "llm"
    assert captured["top_k"] == 7
    latest = client.get("/api/eval/latest")
    assert latest.status_code == 200
    assert "retrieval=service,review=llm" in latest.json()["mode_metrics"]


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
    run_response = client1.post(
        "/api/eval/run",
        json={"retrieval_mode": "local", "review_mode": "local"},
    )
    assert run_response.status_code == 200
    _wait_for_eval_job(client1)

    # app1 should now return the cached summary.
    latest1 = client1.get("/api/eval/latest")
    assert latest1.status_code == 200

    # app2 has its own, isolated cache — it must NOT see app1's result.
    latest2 = client2.get("/api/eval/latest")
    assert latest2.status_code == 404
    assert "detail" in latest2.json()


def _wait_for_eval_job(client: TestClient) -> dict:
    deadline = time.monotonic() + 10
    latest = {}
    while time.monotonic() < deadline:
        response = client.get("/api/eval/status")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert latest["status"] == "succeeded", latest
    return latest


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
