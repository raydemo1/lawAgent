"""Tests for citation validation and structured result building (Issue 8)."""

from pathlib import Path

import pytest

from law_agent.data.io import write_jsonl
from law_agent.data.schemas import Chunk
from law_agent.review.citations import (
    group_citations,
    validate_citation,
    count_citations_by_usage,
)
from law_agent.review.result_builder import (
    build_conclusion,
    build_recommended_actions,
    build_review_result,
    build_risk_boundaries,
    build_trigger_reasons,
    determine_risk_level,
)
from law_agent.review.schemas import (
    EvidenceSelfCheck,
    ReviewFacts,
    RetrievalHit,
)

from tests.test_review_retrieval_keyword import FIXTURE_CHUNKS, _make_chunk


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _hit(
    chunk_id: str = "c1",
    citation_role: str = "primary_legal_basis",
    can_cite: bool = True,
    title: str = "数据出境安全评估办法",
    text: str = "第四条　数据处理者向境外提供数据，应当申报数据出境安全评估。",
    source_url: str = "https://example.gov.cn/doc/001",
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id, doc_id="d1", source_id="s1", title=title, text=text,
        score=1.0, rank=0, retriever="hybrid",
        citation_role=citation_role, can_cite_clause=can_cite, source_url=source_url,
    )


def _sufficient_check() -> EvidenceSelfCheck:
    return EvidenceSelfCheck(status="sufficient")


# ---------------------------------------------------------------------------
# Citation validation tests
# ---------------------------------------------------------------------------

def test_validate_legal_basis_requires_can_cite_clause() -> None:
    hit = _hit(citation_role="primary_legal_basis", can_cite=False)
    violations = validate_citation(hit, "legal_basis")

    assert len(violations) == 1
    assert "can_cite_clause=True" in violations[0]


def test_validate_legal_basis_passes_with_can_cite() -> None:
    hit = _hit(citation_role="primary_legal_basis", can_cite=True)
    violations = validate_citation(hit, "legal_basis")

    assert violations == []


def test_validate_conditional_basis_requires_can_cite() -> None:
    hit = _hit(citation_role="conditional_local_basis", can_cite=False)
    violations = validate_citation(hit, "conditional_basis")

    assert len(violations) == 1


def test_validate_implementation_reference_allows_non_citable() -> None:
    hit = _hit(citation_role="implementation_reference", can_cite=False)
    violations = validate_citation(hit, "implementation_reference")

    assert violations == []


def test_validate_policy_explanation_allows_non_citable() -> None:
    hit = _hit(citation_role="interpretation_auxiliary", can_cite=False)
    violations = validate_citation(hit, "policy_explanation")

    assert violations == []


# ---------------------------------------------------------------------------
# Citation grouping tests
# ---------------------------------------------------------------------------

def test_group_citations_separates_by_usage() -> None:
    hits = [
        _hit(chunk_id="c1", citation_role="primary_legal_basis", can_cite=True),
        _hit(chunk_id="c2", citation_role="conditional_local_basis", can_cite=True),
        _hit(chunk_id="c3", citation_role="implementation_reference", can_cite=False),
        _hit(chunk_id="c4", citation_role="interpretation_auxiliary", can_cite=False),
    ]
    facts = ReviewFacts()

    groups, violations = group_citations(hits, facts)

    assert len(groups) == 4
    usages = [g.usage for g in groups]
    assert "legal_basis" in usages
    assert "conditional_basis" in usages
    assert "implementation_reference" in usages
    assert "policy_explanation" in usages
    assert violations == []


def test_group_citations_demotes_non_citable_legal_basis() -> None:
    """Non-citable primary_legal_basis is demoted to implementation_reference."""

    hit = _hit(chunk_id="c1", citation_role="primary_legal_basis", can_cite=False)
    facts = ReviewFacts()

    groups, _ = group_citations([hit], facts)

    # Should NOT have legal_basis group (demoted)
    legal_groups = [g for g in groups if g.usage == "legal_basis"]
    assert len(legal_groups) == 0
    # Should have implementation_reference group
    impl_groups = [g for g in groups if g.usage == "implementation_reference"]
    assert len(impl_groups) == 1


def test_group_citations_adds_scope_note_for_conditional() -> None:
    hit = _hit(chunk_id="c1", citation_role="conditional_local_basis", can_cite=True)
    chunk = _make_chunk(chunk_id="c1", applicable_region="CN-SH")
    facts = ReviewFacts(region="上海")

    groups, _ = group_citations([hit], facts, {"c1": chunk})

    cond_groups = [g for g in groups if g.usage == "conditional_basis"]
    assert len(cond_groups) == 1
    assert cond_groups[0].scope_note is not None
    assert "CN-SH" in cond_groups[0].scope_note


def test_group_citations_scope_note_for_implementation_reference() -> None:
    hit = _hit(chunk_id="c1", citation_role="implementation_reference", can_cite=False)
    facts = ReviewFacts()

    groups, _ = group_citations([hit], facts)

    impl_groups = [g for g in groups if g.usage == "implementation_reference"]
    assert len(impl_groups) == 1
    assert "不作为条款级法律依据" in impl_groups[0].scope_note


def test_count_citations_by_usage() -> None:
    hits = [
        _hit(chunk_id="c1", citation_role="primary_legal_basis", can_cite=True),
        _hit(chunk_id="c2", citation_role="primary_legal_basis", can_cite=True),
        _hit(chunk_id="c3", citation_role="interpretation_auxiliary", can_cite=False),
    ]
    facts = ReviewFacts()

    groups, _ = group_citations(hits, facts)
    counts = count_citations_by_usage(groups)

    assert counts["legal_basis"] == 2
    assert counts["policy_explanation"] == 1


# ---------------------------------------------------------------------------
# Risk level determination tests
# ---------------------------------------------------------------------------

def test_risk_level_insufficient_when_self_check_insufficient() -> None:
    facts = ReviewFacts(cross_border_transfer=True)
    check = EvidenceSelfCheck(status="insufficient")

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "insufficient_evidence"


def test_risk_level_high_for_sensitive_cross_border_no_consent() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        sensitive_personal_info=True,
        legal_basis_or_consent=None,
        data_types=["人脸信息"],
    )
    check = _sufficient_check()

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "high"


def test_risk_level_medium_for_cross_border() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        overseas_recipient="新加坡",
        legal_basis_or_consent="用户同意",
    )
    check = _sufficient_check()

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "medium"


def test_risk_level_medium_for_sensitive_without_cross_border() -> None:
    facts = ReviewFacts(sensitive_personal_info=True)
    check = _sufficient_check()

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "medium"


def test_risk_level_low_for_no_risk_factors() -> None:
    """When facts have substance but no risk triggers, risk is low."""

    facts = ReviewFacts(
        data_types=["订单信息"],
        processing_purpose="订单履约",
    )
    check = _sufficient_check()

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "low"


def test_risk_level_insufficient_for_no_substantive_facts() -> None:
    """When facts are completely empty/vague, abstain even with evidence."""

    facts = ReviewFacts()  # no substantive dimensions
    check = _sufficient_check()

    assert determine_risk_level(facts, check, has_legal_basis_evidence=True) == "insufficient_evidence"


def test_risk_level_insufficient_when_no_legal_basis_and_not_sufficient() -> None:
    facts = ReviewFacts(cross_border_transfer=True)
    check = EvidenceSelfCheck(status="needs_second_retrieval")

    assert determine_risk_level(facts, check, has_legal_basis_evidence=False) == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Conclusion building tests
# ---------------------------------------------------------------------------

def test_conclusion_cross_border_medium() -> None:
    facts = ReviewFacts(cross_border_transfer=True, overseas_recipient="新加坡")
    check = _sufficient_check()

    conclusion = build_conclusion(facts, "medium", check)

    assert "数据出境" in conclusion
    assert "新加坡" in conclusion
    assert "安全评估" in conclusion


def test_conclusion_insufficient_evidence() -> None:
    facts = ReviewFacts(missing_information=["legal_basis_or_consent"])
    check = EvidenceSelfCheck(status="insufficient")

    conclusion = build_conclusion(facts, "insufficient_evidence", check)

    assert "证据不足" in conclusion


def test_conclusion_includes_missing_info_warning() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        missing_information=["legal_basis_or_consent", "data_volume_threshold"],
    )
    check = _sufficient_check()

    conclusion = build_conclusion(facts, "medium", check)

    assert "关键信息缺失" in conclusion


# ---------------------------------------------------------------------------
# Recommended actions tests
# ---------------------------------------------------------------------------

def test_actions_for_cross_border_without_consent() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        overseas_recipient="新加坡",
        legal_basis_or_consent=None,
    )
    check = _sufficient_check()

    actions = build_recommended_actions(facts, "medium", check)

    assert any("安全评估" in a for a in actions)
    assert any("单独同意" in a for a in actions)
    assert any("新加坡" in a for a in actions)


def test_actions_for_insufficient_evidence() -> None:
    facts = ReviewFacts(
        missing_information=["legal_basis_or_consent", "overseas_recipient"],
    )
    check = EvidenceSelfCheck(status="insufficient")

    actions = build_recommended_actions(facts, "insufficient_evidence", check)

    assert any("重新审查" in a for a in actions)
    assert any("单独同意" in a for a in actions)
    assert any("接收方" in a for a in actions)


# ---------------------------------------------------------------------------
# Full result builder tests
# ---------------------------------------------------------------------------

def test_build_review_result_cross_border_sample() -> None:
    facts = ReviewFacts(
        cross_border_transfer=True,
        overseas_recipient="新加坡",
        data_types=["手机号", "定位信息"],
        sensitive_personal_info=True,
        processing_purpose="推荐",
        missing_information=["legal_basis_or_consent"],
    )
    check = _sufficient_check()
    hits = [
        _hit(chunk_id="chunk_assessment", citation_role="primary_legal_basis", can_cite=True),
        _hit(chunk_id="chunk_faq", citation_role="interpretation_auxiliary", can_cite=False),
    ]

    result = build_review_result(
        review_result_id="result_test",
        review_case_id="review_test",
        trace_id="trace_test",
        facts=facts,
        self_check=check,
        evidence_hits=hits,
    )

    assert result.risk_level == "high"  # sensitive + cross_border + no consent
    assert "数据出境" in result.conclusion
    assert "cross_border_transfer" in result.trigger_reasons
    assert "sensitive_personal_info" in result.trigger_reasons
    assert "legal_basis_or_consent" in result.missing_information
    assert len(result.recommended_actions) > 0
    assert len(result.risk_boundaries) > 0
    assert len(result.citations) == 2
    assert len(result.applicable_evidence) >= 1


def test_build_review_result_insufficient_evidence() -> None:
    facts = ReviewFacts(missing_information=["legal_basis_or_consent"])
    check = EvidenceSelfCheck(status="insufficient")
    hits: list[RetrievalHit] = []

    result = build_review_result(
        review_result_id="result_test",
        review_case_id="review_test",
        trace_id="trace_test",
        facts=facts,
        self_check=check,
        evidence_hits=hits,
    )

    assert result.risk_level == "insufficient_evidence"
    assert "证据不足" in result.conclusion
    # Insufficient evidence should NOT cite weak evidence as legal basis
    legal_groups = [g for g in result.applicable_evidence if g.usage == "legal_basis"]
    assert len(legal_groups) == 0


def test_build_review_result_groups_citations_correctly() -> None:
    facts = ReviewFacts(cross_border_transfer=True)
    check = _sufficient_check()
    hits = [
        _hit(chunk_id="c1", citation_role="primary_legal_basis", can_cite=True),
        _hit(chunk_id="c2", citation_role="conditional_local_basis", can_cite=True),
        _hit(chunk_id="c3", citation_role="implementation_reference", can_cite=False),
        _hit(chunk_id="c4", citation_role="interpretation_auxiliary", can_cite=False),
    ]

    result = build_review_result(
        review_result_id="result_test",
        review_case_id="review_test",
        trace_id="trace_test",
        facts=facts,
        self_check=check,
        evidence_hits=hits,
    )

    usages = [g.usage for g in result.applicable_evidence]
    assert "legal_basis" in usages
    assert "conditional_basis" in usages
    assert "implementation_reference" in usages
    assert "policy_explanation" in usages


# ---------------------------------------------------------------------------
# Integration: run_hybrid_retrieval produces review result
# ---------------------------------------------------------------------------

def _write_fixture_corpus(tmp_path: Path) -> Path:
    chunks_path = tmp_path / "chunks.jsonl"
    linked_chunks = []
    for i, chunk in enumerate(FIXTURE_CHUNKS):
        linked = chunk.model_copy(
            update={
                "prev_chunk_id": FIXTURE_CHUNKS[i - 1].chunk_id if i > 0 else None,
                "next_chunk_id": FIXTURE_CHUNKS[i + 1].chunk_id if i < len(FIXTURE_CHUNKS) - 1 else None,
            }
        )
        linked_chunks.append(linked)
    write_jsonl(chunks_path, linked_chunks)
    return chunks_path


def test_hybrid_retrieval_persists_structured_result(tmp_path: Path) -> None:
    from law_agent.review.io import read_review_results
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    results = read_review_results(tmp_path / "review_results.jsonl")
    assert len(results) == 1
    result = results[0]

    assert result.risk_level != "insufficient_evidence" or "证据不足" in result.conclusion
    assert result.conclusion != "Review case created. Evidence retrieval has not run yet."
    assert len(result.applicable_evidence) > 0
    assert result.review_facts.cross_border_transfer is True


def test_hybrid_retrieval_result_has_citation_groups(tmp_path: Path) -> None:
    from law_agent.review.io import read_review_results
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="数据出境安全评估",
        material_text="手机号发送给新加坡。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    results = read_review_results(tmp_path / "review_results.jsonl")
    result = results[0]

    # Should have at least one citation group
    assert len(result.applicable_evidence) > 0

    # Check that legal_basis citations only use can_cite_clause=True
    for group in result.applicable_evidence:
        if group.usage == "legal_basis":
            for cite in group.citations:
                assert cite.can_cite_clause is True


def test_cross_border_sample_produces_missing_information_actions(tmp_path: Path) -> None:
    from law_agent.review.io import read_review_results
    from law_agent.review.service import create_review_case, run_hybrid_retrieval

    chunks_path = _write_fixture_corpus(tmp_path)

    create_review_case(
        question="这个场景是否需要数据出境安全评估？",
        material_text="我们会将手机号和定位信息发送给新加坡服务商用于推荐优化。",
        output_dir=tmp_path,
        now=lambda: "2026-07-06T00:00:00+00:00",
        id_factory=lambda prefix: f"{prefix}_test",
    )

    run_hybrid_retrieval(
        case_id="review_test",
        chunks_path=chunks_path,
        output_dir=tmp_path,
    )

    results = read_review_results(tmp_path / "review_results.jsonl")
    result = results[0]

    # Cross-border sample should have missing information
    assert "legal_basis_or_consent" in result.missing_information
    # Should have recommended actions
    assert len(result.recommended_actions) > 0
