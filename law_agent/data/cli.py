"""Small argparse CLI for the data governance file pipeline."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

from law_agent.data.cleaners.common import clean_text
from law_agent.data.schemas import SourceRecord


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_manifest(path: Path) -> Iterable[SourceRecord]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield SourceRecord.model_validate(row)


def _cmd_manifest_schema(args: argparse.Namespace) -> int:
    _write_json(Path(args.output), SourceRecord.model_json_schema())
    print(f"Wrote schema to {args.output}")
    return 0


def _cmd_manifest_validate(args: argparse.Namespace) -> int:
    records = list(_read_manifest(Path(args.path)))
    included = sum(1 for record in records if record.include_in_mvp)
    print(f"Validated {len(records)} sources ({included} included in MVP)")
    return 0


def _cmd_clean_text(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    result = clean_text(input_path.read_text(encoding="utf-8"), title=args.title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.text, encoding="utf-8")
    print(json.dumps(result.rule_hits, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m law_agent.data")
    subparsers = parser.add_subparsers(dest="command")

    manifest = subparsers.add_parser("manifest", help="Work with source manifests")
    manifest_sub = manifest.add_subparsers(dest="manifest_command")

    manifest_schema = manifest_sub.add_parser("schema", help="Write source manifest schema")
    manifest_schema.add_argument(
        "--output",
        default="data/manifests/source_manifest.schema.json",
        help="Path to write JSON schema",
    )
    manifest_schema.set_defaults(func=_cmd_manifest_schema)

    manifest_validate = manifest_sub.add_parser("validate", help="Validate a manifest CSV")
    manifest_validate.add_argument("path", help="Manifest CSV path")
    manifest_validate.set_defaults(func=_cmd_manifest_validate)

    clean = subparsers.add_parser("clean", help="Run cleaning helpers")
    clean_sub = clean.add_subparsers(dest="clean_command")
    clean_text_cmd = clean_sub.add_parser("text", help="Clean a UTF-8 text file")
    clean_text_cmd.add_argument("--input", required=True)
    clean_text_cmd.add_argument("--output", required=True)
    clean_text_cmd.add_argument("--title", default=None)
    clean_text_cmd.set_defaults(func=_cmd_clean_text)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)

