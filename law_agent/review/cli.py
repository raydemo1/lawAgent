"""Command-line interface for material-driven review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_agent.review.materials import material_from_file, material_from_text
from law_agent.review.service import DEFAULT_REVIEW_RUNS_DIR, create_review_case


def _cmd_run(args: argparse.Namespace) -> int:
    if args.material_text is not None:
        material = material_from_text(args.material_text)
    else:
        material = material_from_file(Path(args.material_file), parser=args.parser)

    try:
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
    print(f"Wrote {response.case_path}")
    print(f"Wrote {response.trace_path}")
    print(f"Wrote {response.result_path}")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)
