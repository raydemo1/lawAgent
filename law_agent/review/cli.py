"""Argparse CLI for material-driven review runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_agent.review.materials import material_from_file, material_from_text
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH
from law_agent.review.service import (
    DEFAULT_REVIEW_RUNS_DIR,
    create_review_case,
    run_hybrid_retrieval,
    run_keyword_retrieval,
)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        material = (
            material_from_text(args.material_text)
            if args.material_text is not None
            else material_from_file(Path(args.material_file), parser=args.parser)
        )
        response = create_review_case(
            question=args.question,
            material=material,
            output_dir=Path(args.output_dir),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Created review case {response.review_case.review_case_id}")
    print(f"Trace {response.trace.trace_id}")
    print(f"Result {response.result.review_result_id}")

    facts = response.review_case.review_facts
    print(f"Facts: cross_border={facts.cross_border_transfer}, data_types={facts.data_types}")
    if facts.industry:
        print(f"  industry={facts.industry}")
    if facts.region:
        print(f"  region={facts.region}")
    if facts.missing_information:
        print(f"  missing={facts.missing_information}")
    print(f"Queries: {len(response.trace.queries)} planned")
    for query in response.trace.queries:
        print(f"  [{query.query_type}] {query.text}")

    print(f"Wrote {response.case_path}")
    print(f"Wrote {response.trace_path}")
    print(f"Wrote {response.result_path}")
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    try:
        if args.hybrid:
            trace = run_hybrid_retrieval(
                case_id=args.case_id,
                chunks_path=Path(args.chunks),
                output_dir=Path(args.output_dir),
                top_k=args.top_k,
            )
        else:
            trace = run_keyword_retrieval(
                case_id=args.case_id,
                chunks_path=Path(args.chunks),
                output_dir=Path(args.output_dir),
                top_k=args.top_k,
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Retrieved evidence for case {trace.review_case_id}")
    print(f"Trace {trace.trace_id}")
    print(f"Keyword hits: {len(trace.keyword_results)}")
    if args.hybrid:
        print(f"Vector mock hits: {len(trace.vector_results)}")
        print(f"Hybrid (RRF) hits: {len(trace.hybrid_results)}")
        print(f"Neighbor chunks: {len(trace.neighbor_chunks)}")
        if trace.metadata_boosts:
            print(f"Metadata boosts: {trace.metadata_boosts}")

        # Evidence self-check status
        check = trace.evidence_self_check
        print(f"Evidence self-check: {check.status}")
        if check.triggered_reasons:
            print(f"  Triggered reasons: {check.triggered_reasons}")
        for issue in check.issues:
            print(f"  [{issue.issue_type}] {issue.description}")
        if check.second_retrieval_triggered:
            print(f"  Second retrieval: triggered")
            if trace.second_retrieval:
                print(f"  Expanded queries: {len(trace.second_retrieval.get('expanded_queries', []))}")
        elif check.second_retrieval_plan:
            print(f"  Second retrieval: planned but not executed")

        if trace.final_evidence:
            print(f"Final evidence: {len(trace.final_evidence)} hits")
        hits = trace.final_evidence or trace.hybrid_results
    else:
        hits = trace.keyword_results

    for hit in hits:
        print(
            f"  [{hit.rank + 1}] score={hit.score:.4f} role={hit.citation_role} "
            f"can_cite={hit.can_cite_clause} type={hit.matched_query_type}"
        )
        print(f"      {hit.title[:60]}")

    # Issue 8: Display structured review result
    if args.hybrid:
        from law_agent.review.io import read_review_results

        results_path = Path(args.output_dir) / "review_results.jsonl"
        if results_path.exists():
            results = read_review_results(results_path)
            result = next(
                (r for r in results if r.review_case_id == args.case_id), None
            )
            if result is not None:
                print(f"\nReview Result: {result.review_result_id}")
                print(f"  Risk level: {result.risk_level}")
                print(f"  Conclusion: {result.conclusion[:120]}")
                if result.trigger_reasons:
                    print(f"  Trigger reasons: {result.trigger_reasons}")
                if result.missing_information:
                    print(f"  Missing information: {result.missing_information}")
                if result.recommended_actions:
                    print(f"  Recommended actions:")
                    for action in result.recommended_actions:
                        print(f"    - {action}")
                if result.risk_boundaries:
                    print(f"  Risk boundaries:")
                    for boundary in result.risk_boundaries:
                        print(f"    - {boundary}")
                if result.applicable_evidence:
                    print(f"  Applicable evidence:")
                    for group in result.applicable_evidence:
                        print(f"    [{group.usage}] ({len(group.citations)} citations)")
                        if group.scope_note:
                            print(f"      scope: {group.scope_note}")
                        for cite in group.citations[:3]:
                            label = f" - {cite.citation_label}" if cite.citation_label else ""
                            print(f"      {cite.title[:50]}{label}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from law_agent.review.evalset.runner import format_summary_text, run_evaluation

    try:
        summary = run_evaluation(
            chunks_path=Path(args.chunks),
            top_k=args.top_k,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_summary_text(summary))

    # Save summary JSON if output specified
    if args.output:
        import json

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            summary.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"\nSaved JSON summary to {output_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m law_agent.review")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Create a material review case skeleton")
    run.add_argument("--question", required=True)
    material = run.add_mutually_exclusive_group(required=True)
    material.add_argument("--material-text")
    material.add_argument("--material-file")
    run.add_argument(
        "--parser",
        choices=["auto", "plain", "docx", "docling", "mineru"],
        default="auto",
        help="Parser used for --material-file. Pasted text ignores this option.",
    )
    run.add_argument("--output-dir", default=str(DEFAULT_REVIEW_RUNS_DIR))
    run.set_defaults(func=_cmd_run)

    retrieve = subparsers.add_parser(
        "retrieve", help="Run retrieval for an existing review case"
    )
    retrieve.add_argument("--case-id", required=True)
    retrieve.add_argument(
        "--chunks",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Path to chunks.jsonl corpus file",
    )
    retrieve.add_argument("--output-dir", default=str(DEFAULT_REVIEW_RUNS_DIR))
    retrieve.add_argument("--top-k", type=int, default=10)
    retrieve.add_argument(
        "--hybrid",
        action="store_true",
        help="Run hybrid retrieval (keyword + vector_mock + RRF + neighbors)",
    )
    retrieve.set_defaults(func=_cmd_retrieve)

    eval_parser = subparsers.add_parser(
        "eval", help="Run evaluation suite on golden-set scenarios"
    )
    eval_parser.add_argument(
        "--chunks",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Path to chunks.jsonl corpus file",
    )
    eval_parser.add_argument("--top-k", type=int, default=10)
    eval_parser.add_argument(
        "--output",
        default=None,
        help="Save JSON summary to this file path",
    )
    eval_parser.set_defaults(func=_cmd_eval)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)
