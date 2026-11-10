from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scout.corpus import Manifest, ManifestEntry, save_manifest
from scout.models import (
    Chunk,
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
)
from scout.storage import SQLiteStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SQLiteStore]:
    instance = SQLiteStore(tmp_path / "scout.db")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def sample_documents() -> list[SourceDocument]:
    return [
        SourceDocument(
            id="arxiv:1",
            title="vLLM and PagedAttention",
            url="https://arxiv.org/abs/2309.06180",
            source_type=SourceType.PAPER,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            text="vLLM uses PagedAttention to manage the KV cache efficiently.",
        ),
        SourceDocument(
            id="docs:sglang:index",
            title="SGLang documentation",
            url="https://docs.sglang.ai/",
            source_type=SourceType.OFFICIAL_DOC,
            trust=TrustLevel.PRIMARY,
            retrieval_method=RetrievalMethod.API,
            text="SGLang uses RadixAttention for prefix sharing in LLM serving.",
        ),
        SourceDocument(
            id="blog:weather",
            title="Weather blog",
            url="https://example.com/weather",
            source_type=SourceType.BLOG,
            trust=TrustLevel.UNTRUSTED,
            retrieval_method=RetrievalMethod.GUI,
            text="The weather is sunny and warm today.",
        ),
    ]


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            id="arxiv:1:0",
            doc_id="arxiv:1",
            ordinal=0,
            text="vLLM uses PagedAttention to manage the KV cache efficiently.",
            token_count=10,
        ),
        Chunk(
            id="docs:sglang:index:0",
            doc_id="docs:sglang:index",
            ordinal=0,
            text="SGLang uses RadixAttention for prefix sharing in LLM serving.",
            token_count=10,
        ),
        Chunk(
            id="blog:weather:0",
            doc_id="blog:weather",
            ordinal=0,
            text="The weather is sunny and warm today.",
            token_count=8,
        ),
    ]


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    raw = root / "raw"
    raw.mkdir(parents=True)
    (raw / "doc1.md").write_text(
        "# PagedAttention\n\nvLLM manages the KV cache with PagedAttention.",
        encoding="utf-8",
    )
    (raw / "doc2.md").write_text(
        "# RadixAttention\n\nSGLang shares prefixes with RadixAttention.",
        encoding="utf-8",
    )
    save_manifest(
        root,
        Manifest(
            documents=[
                ManifestEntry(
                    id="arxiv:1",
                    title="PagedAttention",
                    url="https://arxiv.org/abs/1",
                    source_type=SourceType.PAPER,
                    trust=TrustLevel.PRIMARY,
                    path="raw/doc1.md",
                    content_hash="hash1",
                ),
                ManifestEntry(
                    id="docs:sglang",
                    title="RadixAttention",
                    url="https://docs.sglang.ai/",
                    source_type=SourceType.OFFICIAL_DOC,
                    trust=TrustLevel.PRIMARY,
                    path="raw/doc2.md",
                    content_hash="hash2",
                ),
            ]
        ),
    )
    return root
