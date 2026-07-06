"""Argparse CLI for material-driven review runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_agent.review.materials import material_from_file, material_from_text
from law_agent.review.retrieval.corpus import DEFAULT_CHUNKS_PATH
from law_agent.review.service import DEFAULT_REVIEW_RUNS_DIR, create_review_case, run_keyword_retrieval


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
    for hit in trace.keyword_results:
        print(
            f"  [{hit.rank + 1}] score={hit.score:.4f} role={hit.citation_role} "
            f"can_cite={hit.can_cite_clause} type={hit.matched_query_type}"
        )
        print(f"      {hit.title[:60]}")
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
        "retrieve", help="Run keyword baseline retrieval for an existing review case"
    )
    retrieve.add_argument("--case-id", required=True)
    retrieve.add_argument(
        "--chunks",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Path to chunks.jsonl corpus file",
    )
    retrieve.add_argument("--output-dir", default=str(DEFAULT_REVIEW_RUNS_DIR))
    retrieve.add_argument("--top-k", type=int, default=10)
    retrieve.set_defaults(func=_cmd_retrieve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)
