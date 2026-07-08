"""Argparse CLI for LegalBench-RAG-mini retrieval-only evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_agent.external.legalbench_rag.data import (
    DEFAULT_CHUNK_META_PATH,
    DEFAULT_CHUNKS_PATH,
    DEFAULT_DATA_DIR,
)
from law_agent.external.legalbench_rag.service import (
    DEFAULT_ES_INDEX,
    DEFAULT_PG_TABLE,
    evaluate_legalbench,
    index_legalbench,
    prepare_chunks,
)


def _cmd_prepare(args: argparse.Namespace) -> int:
    try:
        summary = prepare_chunks(
            data_dir=Path(args.data_dir),
            chunks_path=Path(args.chunks),
            chunk_meta_path=Path(args.chunk_meta),
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


def _cmd_index(args: argparse.Namespace) -> int:
    try:
        summary = index_legalbench(
            data_dir=Path(args.data_dir),
            chunks_path=Path(args.chunks),
            chunk_meta_path=Path(args.chunk_meta),
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            es_index=args.es_index,
            pg_table=args.pg_table,
            reset=args.reset,
            embedding_batch_size=args.embedding_batch_size,
            embedding_sleep_seconds=args.embedding_sleep_seconds,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("Indexed LegalBench-RAG-mini into service hybrid backends:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    try:
        summary = evaluate_legalbench(
            data_dir=Path(args.data_dir),
            chunks_path=Path(args.chunks),
            chunk_meta_path=Path(args.chunk_meta),
            output_path=Path(args.output),
            report_path=Path(args.report) if args.report else None,
            es_index=args.es_index,
            pg_table=args.pg_table,
            top_k=args.top_k,
            candidate_top_k=args.candidate_top_k,
            query_embedding_batch_size=args.query_embedding_batch_size,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("LegalBench-RAG-mini retrieval summary:")
    print(f"  cases: {summary.total_cases}")
    print(f"  doc_recall@5: {summary.doc_recall_at_5:.4f}")
    print(f"  doc_recall@10: {summary.doc_recall_at_10:.4f}")
    print(f"  span_recall@5: {summary.span_recall_at_5:.4f}")
    print(f"  span_recall@10: {summary.span_recall_at_10:.4f}")
    print(f"  mrr@10: {summary.mrr_at_10:.4f}")
    print(f"  avg_latency_ms: {summary.avg_latency_ms:.1f}")
    print(f"  bad_cases: {summary.bad_case_count}")
    print(f"  wrote: {args.output}")
    if args.report:
        print(f"  report: {args.report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m law_agent.external.legalbench_rag")
    subparsers = parser.add_subparsers(dest="command")

    def add_common_io(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
        subparser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH))
        subparser.add_argument("--chunk-meta", default=str(DEFAULT_CHUNK_META_PATH))

    prepare = subparsers.add_parser("prepare", help="Build LegalBench chunks only")
    add_common_io(prepare)
    prepare.add_argument("--chunk-size", type=int, default=1000)
    prepare.add_argument("--overlap", type=int, default=200)
    prepare.set_defaults(func=_cmd_prepare)

    index = subparsers.add_parser("index", help="Index LegalBench chunks into service backends")
    add_common_io(index)
    index.add_argument("--chunk-size", type=int, default=1000)
    index.add_argument("--overlap", type=int, default=200)
    index.add_argument("--es-index", default=DEFAULT_ES_INDEX)
    index.add_argument("--pg-table", default=DEFAULT_PG_TABLE)
    index.add_argument("--reset", action="store_true")
    index.add_argument(
        "--embedding-batch-size",
        type=int,
        default=64,
        help="Embedding batch size for LegalBench indexing. Defaults to 64.",
    )
    index.add_argument(
        "--embedding-sleep-seconds",
        type=float,
        default=0.0,
        help="Optional pause between embedding batches. Defaults to 0.",
    )
    index.set_defaults(func=_cmd_index)

    eval_parser = subparsers.add_parser("eval", help="Run retrieval-only hybrid eval")
    add_common_io(eval_parser)
    eval_parser.add_argument("--es-index", default=DEFAULT_ES_INDEX)
    eval_parser.add_argument("--pg-table", default=DEFAULT_PG_TABLE)
    eval_parser.add_argument("--top-k", type=int, default=10)
    eval_parser.add_argument("--candidate-top-k", type=int, default=50)
    eval_parser.add_argument(
        "--query-embedding-batch-size",
        type=int,
        default=64,
        help="Batch size for prewarming query embeddings. Defaults to 64.",
    )
    eval_parser.add_argument(
        "--output",
        default="artifacts/external/legalbenchrag/results_hybrid.json",
    )
    eval_parser.add_argument(
        "--report",
        default="artifacts/external/legalbenchrag/report_hybrid.md",
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
