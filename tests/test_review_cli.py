"""CLI tests for the review run command (Issues 1-4)."""

from pathlib import Path

from law_agent.review.cli import main
from law_agent.review.io import read_review_cases, read_review_results, read_retrieval_traces
from law_agent.review.schemas import ReviewFacts
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


def test_create_review_case_populates_facts_from_material(tmp_path: Path) -> None:
    response = create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    facts = response.review_case.review_facts
    assert facts.cross_border_transfer is True
    assert facts.overseas_recipient == "新加坡"
    assert "手机号" in facts.data_types
    assert "定位信息" in facts.data_types
    assert facts.processing_purpose is not None
    assert "legal_basis_or_consent" in facts.missing_information

    assert response.result.review_facts == facts


def test_create_review_case_persists_queries_in_trace(tmp_path: Path) -> None:
    response = create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    queries = response.trace.queries
    assert len(queries) >= 3
    query_types = [q.query_type for q in queries]
    assert "legal_issue" in query_types
    assert "material_fact" in query_types
    assert "missing_information" in query_types

    assert all(q.query_id.startswith("q_") for q in queries)


def test_create_review_case_with_automotive_material_extracts_industry(tmp_path: Path) -> None:
    response = create_review_case(
        question="汽车数据出境合规要求？",
        material_text="智能网联汽车采集车辆位置和行驶轨迹数据，需进行数据出境安全评估。",
        output_dir=tmp_path,
    )

    assert response.review_case.review_facts.industry == "智能网联汽车"
    query_types = [q.query_type for q in response.trace.queries]
    assert "industry_condition" in query_types


def test_create_review_case_with_regional_material_extracts_region(tmp_path: Path) -> None:
    response = create_review_case(
        question="上海数据出境负面清单要求？",
        material_text="公司在上海自贸区开展业务，涉及数据出境。",
        output_dir=tmp_path,
    )

    assert response.review_case.review_facts.region == "上海"
    query_types = [q.query_type for q in response.trace.queries]
    assert "region_condition" in query_types


def test_create_review_case_supports_custom_facts_extractor(tmp_path: Path) -> None:
    custom_facts = ReviewFacts(
        business_activity="custom activity",
        data_types=["自定义数据"],
        cross_border_transfer=True,
    )

    def custom_extractor(material_text: str, question: str | None = None) -> ReviewFacts:
        return custom_facts

    response = create_review_case(
        question="问题",
        material_text="材料",
        output_dir=tmp_path,
        facts_extractor=custom_extractor,
    )

    assert response.review_case.review_facts == custom_facts
    assert response.result.review_facts == custom_facts


def test_review_cli_run_prints_facts_and_queries(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "run",
            "--question",
            "这个场景是否需要数据出境安全评估？",
            "--material-text",
            "我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Facts:" in captured.out
    assert "Queries:" in captured.out
    assert "legal_issue" in captured.out
    assert "material_fact" in captured.out
