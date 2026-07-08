"""Load and chunk LegalBench-RAG data without importing the upstream package."""

from __future__ import annotations

import json
import random
from pathlib import Path

from law_agent.data.io import write_jsonl
from law_agent.data.schemas import Chunk
from law_agent.external.legalbench_rag.schemas import (
    LegalBenchChunkMeta,
    LegalBenchDocument,
    LegalBenchQuery,
    LegalBenchSnippet,
)

DEFAULT_DATA_DIR = Path("artifacts/external/legalbenchrag/data")
DEFAULT_OUTPUT_DIR = Path("artifacts/external/legalbenchrag")
DEFAULT_CHUNKS_PATH = DEFAULT_OUTPUT_DIR / "chunks_fixed_1000_200.jsonl"
DEFAULT_CHUNK_META_PATH = DEFAULT_OUTPUT_DIR / "chunks_fixed_1000_200.meta.jsonl"
BENCHMARK_WEIGHTS: dict[str, float] = {
    "privacy_qa": 0.25,
    "contractnli": 0.25,
    "maud": 0.25,
    "cuad": 0.25,
}


def load_mini_queries(
    data_dir: Path,
    *,
    max_tests_per_benchmark: int = 194,
    sort_by_document: bool = True,
) -> list[LegalBenchQuery]:
    """Load the upstream mini selection: 194 tests per benchmark."""

    queries: list[LegalBenchQuery] = []
    benchmarks_dir = data_dir / "benchmarks"
    for benchmark_name in BENCHMARK_WEIGHTS:
        path = benchmarks_dir / f"{benchmark_name}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        tests = payload.get("tests", [])
        if len(tests) > max_tests_per_benchmark:
            if sort_by_document:
                tests = sorted(
                    tests,
                    key=lambda test: (
                        random.seed(test["snippets"][0]["file_path"]),
                        random.random(),
                    )[1],
                )
            else:
                random.seed(benchmark_name)
                tests = list(tests)
                random.shuffle(tests)
            tests = tests[:max_tests_per_benchmark]

        for index, test in enumerate(tests):
            snippets = [
                LegalBenchSnippet(
                    file_path=str(snippet["file_path"]),
                    span=tuple(snippet["span"]),
                )
                for snippet in test.get("snippets", [])
            ]
            queries.append(
                LegalBenchQuery(
                    query_id=f"{benchmark_name}_{index:04d}",
                    query=str(test["query"]),
                    snippets=snippets,
                    tags=[benchmark_name],
                )
            )
    return queries


def load_documents_for_queries(
    data_dir: Path,
    queries: list[LegalBenchQuery],
) -> list[LegalBenchDocument]:
    """Load only corpus files referenced by the selected mini queries."""

    corpus_dir = data_dir / "corpus"
    file_paths = sorted({snippet.file_path for query in queries for snippet in query.snippets})
    documents: list[LegalBenchDocument] = []
    for file_path in file_paths:
        path = corpus_dir / file_path
        documents.append(
            LegalBenchDocument(
                file_path=file_path,
                text=path.read_text(encoding="utf-8", errors="replace"),
            )
        )
    return documents


def build_chunks(
    documents: list[LegalBenchDocument],
    *,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> tuple[list[Chunk], list[LegalBenchChunkMeta]]:
    """Build fixed-size chunks that preserve original character spans."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    chunks: list[Chunk] = []
    metas: list[LegalBenchChunkMeta] = []
    step = chunk_size - overlap
    for document in documents:
        safe_id = _safe_id(document.file_path)
        title = Path(document.file_path).name
        text = document.text
        starts = list(range(0, len(text), step)) or [0]
        previous_chunk_id: str | None = None
        for chunk_index, start in enumerate(starts):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if not chunk_text:
                continue
            chunk_id = f"{safe_id}:{chunk_index:04d}"
            chunk = Chunk(
                chunk_id=chunk_id,
                doc_id=safe_id,
                source_id=document.file_path,
                title=title,
                text=chunk_text,
                chunk_index=chunk_index,
                doc_type="contract",
                citation_label=f"{document.file_path}:{start}-{end}",
                citation_role="primary_legal_basis",
                can_cite_clause=True,
                prev_chunk_id=previous_chunk_id,
                source_url=f"legalbenchrag://{document.file_path}",
                applicable_region="US",
                legal_domain=["legalbench_rag"],
                applicable_subjects=["contract"],
                topic_tags=["external_benchmark"],
                char_count=len(chunk_text),
            )
            if previous_chunk_id is not None:
                chunks[-1] = chunks[-1].model_copy(update={"next_chunk_id": chunk_id})
            chunks.append(chunk)
            metas.append(
                LegalBenchChunkMeta(
                    chunk_id=chunk_id,
                    file_path=document.file_path,
                    char_start=start,
                    char_end=end,
                )
            )
            previous_chunk_id = chunk_id
            if end >= len(text):
                break
    return chunks, metas


def write_chunks_and_meta(
    chunks: list[Chunk],
    metas: list[LegalBenchChunkMeta],
    *,
    chunks_path: Path,
    chunk_meta_path: Path,
) -> None:
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(chunks_path, chunks)
    write_jsonl(chunk_meta_path, metas)


def _safe_id(file_path: str) -> str:
    value = file_path.replace("\\", "/")
    for char in "/:. ":
        value = value.replace(char, "_")
    return value
