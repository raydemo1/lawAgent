"""CLI tests for the review run command (Issues 1-3)."""

from pathlib import Path

from law_agent.review.cli import main
from law_agent.review.io import read_review_cases, read_review_results, read_retrieval_traces
from law_agent.review.service import create_review_case


def test_create_review_case_writes_case_trace_and_result(tmp_path: Path) -> None:
    response = create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="手机号发送给新加坡服务商。",
        output_dir=tmp_path,
        now=lambda: "2026-07-01T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    assert response.review_case.review_case_id == "review_test"
    assert response.trace.trace_id == "trace_test"
    assert response.result.review_result_id == "result_test"

    cases = read_review_cases(tmp_path / "review_cases.jsonl")
    results = read_review_results(tmp_path / "review_results.jsonl")
    traces = read_retrieval_traces(tmp_path / "retrieval_traces.jsonl")

    assert len(cases) == 1
    assert len(results) == 1
    assert len(traces) == 1
    assert cases[0].review_case_id == "review_test"
    assert traces[0].trace_id == "trace_test"
    assert results[0].review_result_id == "result_test"


def test_review_cli_help_exits_successfully() -> None:
    exit_code = main(["--help"])
    assert exit_code == 0


def test_review_cli_run_material_text(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run",
            "--question",
            "这个场景是否需要数据出境安全评估？",
            "--material-text",
            "手机号发送给新加坡服务商。",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "review_cases.jsonl").exists()
    assert (tmp_path / "retrieval_traces.jsonl").exists()
    assert (tmp_path / "review_results.jsonl").exists()


def test_review_cli_rejects_blank_question(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run",
            "--question",
            "   ",
            "--material-text",
            "material",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 2


def test_review_cli_requires_material_text(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run",
            "--question",
            "question",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 2


def test_review_cli_run_material_file(tmp_path: Path, capsys) -> None:
    material_path = tmp_path / "scenario.txt"
    material_path.write_text("手机号发送给新加坡服务商。", encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--question",
            "这个场景是否需要数据出境安全评估？",
            "--material-file",
            str(material_path),
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Created review case review_" in captured.out
    assert (tmp_path / "runs" / "review_cases.jsonl").exists()
