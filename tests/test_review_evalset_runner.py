"""Tests for the evalset runner (Bug 1: keyword-mode placeholder risk level).

Bug 1 (P2): In keyword mode the runner only called ``run_keyword_retrieval()``
and never rebuilt the ``ReviewResult``. It therefore read back the placeholder
``insufficient_evidence`` risk level written by ``create_review_case()``, so
every non-abstain scenario was systematically judged as an abstention failure.
"""

from __future__ import annotations

from pathlib import Path

from law_agent.data.io import write_jsonl
from law_agent.review.evalset.cases import get_default_scenarios
from law_agent.review.evalset.metrics import evaluate_case
from law_agent.review.evalset.runner import _run_single_case, run_evaluation
import law_agent.review.evalset.runner as runner_module

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS


def _write_fixture_corpus(tmp_path: Path) -> Path:
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(chunks_path, FIXTURE_CHUNKS)
    return chunks_path


def test_keyword_mode_produces_real_risk_level(tmp_path: Path) -> None:
    """Keyword mode must build a real risk level, not the placeholder.

    Picks a non-abstain scenario (``should_abstain=False``) whose question
    matches the fixture corpus (``chunk_assessment`` is a
    ``primary_legal_basis`` chunk about 数据出境安全评估), runs it through the
    runner in keyword mode, and asserts:

    * the case's ``risk_level`` is NOT ``insufficient_evidence`` (it should be
      one of high/medium/low), and
    * ``abstention_correct`` is ``True`` for the non-abstain scenario (this was
      ``False`` before the fix because the placeholder was read back).
    """

    chunks_path = _write_fixture_corpus(tmp_path)

    scenarios = get_default_scenarios()
    non_abstain = [s for s in scenarios if not s.should_abstain]
    assert non_abstain, "expected at least one non-abstain scenario"
    # eval_cross_border_001: question mentions 数据出境安全评估, material
    # mentions cross-border transfer to a Singapore provider — its keyword
    # queries hit chunk_assessment (primary_legal_basis) in the fixture corpus.
    scenario = non_abstain[0]

    result = _run_single_case(
        scenario,
        chunks_path,
        retrieval_mode="local",
        review_mode="local",
        top_k=5,
    )

    # The risk level must be a real judgment, not the placeholder written by
    # create_review_case().
    assert result.risk_level != "insufficient_evidence"
    assert result.risk_level in ("high", "medium", "low")

    # For non-abstain scenarios abstention must be correct. Before the fix this
    # was False because risk_level was stuck on the placeholder.
    assert result.abstention_correct is True
    assert "abstention_incorrect" not in result.bad_reasons


def test_runner_passes_final_citation_groups_to_metrics(tmp_path: Path, monkeypatch) -> None:
    """Eval runner must count citation violations from final citations."""

    chunks_path = _write_fixture_corpus(tmp_path)
    scenario = [s for s in get_default_scenarios() if not s.should_abstain][0]
    captured = []

    def spy_evaluate_case(*args, **kwargs):
        captured.append(kwargs.get("citation_groups"))
        return evaluate_case(*args, **kwargs)

    monkeypatch.setattr(runner_module, "evaluate_case", spy_evaluate_case)

    _run_single_case(
        scenario,
        chunks_path,
        retrieval_mode="local",
        review_mode="local",
        top_k=5,
    )

    assert captured
    assert captured[0] is not None


def test_run_evaluation_uses_named_suite_when_scenarios_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Runner should select the requested suite before executing cases."""

    chunks_path = _write_fixture_corpus(tmp_path)
    captured = []

    def fake_run_single_case(
        scenario,
        chunks_path,
        *,
        retrieval_mode,
        review_mode,
        top_k,
        rerank_mode="off",
        service_adapters=None,
        service_config=None,
    ):
        captured.append(scenario.case_id)
        from law_agent.review.evalset.schemas import CaseMetricResult

        return CaseMetricResult(
            case_id=scenario.case_id,
            recall_at_3=1.0,
            recall_at_5=1.0,
            mrr_at_10=1.0,
            citation_violation_count=0,
            abstention_correct=True,
            second_retrieval_triggered=False,
        )

    monkeypatch.setattr(runner_module, "_run_single_case", fake_run_single_case)

    summary = run_evaluation(
        chunks_path=chunks_path,
        suite="quick",
        retrieval_mode="local",
        review_mode="local",
    )

    assert summary.cases_path == "quick"
    assert len(captured) == 12
    assert summary.mode_metrics["retrieval=local,review=local"].total_cases == 12


def test_service_eval_mode_fails_fast_without_service_backend(tmp_path: Path) -> None:
    """service mode must not silently fall back to local retrieval.

    In an environment without the ``[service]`` extra installed, building the
    service adapters fails fast with a dependency error. With the extra
    installed, the gated integration test in ``test_service_integration.py``
    covers the real backend path. Either way, service mode never returns a
    local-style summary by silently substituting local retrievers.
    """

    chunks_path = _write_fixture_corpus(tmp_path)

    import pytest

    try:
        import elasticsearch  # noqa: F401
    except ImportError:
        # Default (no-service-extra) environment: must fail fast on the
        # missing Elasticsearch dependency rather than falling back.
        with pytest.raises(RuntimeError, match="elasticsearch"):
            run_evaluation(
                chunks_path=chunks_path,
                scenarios=[get_default_scenarios()[0]],
                retrieval_mode="service",
                review_mode="local",
            )
        return

    # If the service extra is installed, defer to the gated integration test.
    pytest.skip("service extra installed; see test_service_integration.py")
