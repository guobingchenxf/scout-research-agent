from __future__ import annotations

import pytest

from scout.corpus import (
    CorpusError,
    ManifestEntry,
    chunk_text,
    ingest_corpus,
    load_manifest,
    read_entry_text,
)
from scout.models import SourceType


def test_chunk_text_respects_size_and_overlap() -> None:
    text = "One sentence. " * 40
    chunks = chunk_text(text, max_chars=100, overlap=10)
    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_chunk_text_empty() -> None:
    assert chunk_text("   \n\n  ") == []


def test_manifest_roundtrip(corpus_dir) -> None:
    manifest = load_manifest(corpus_dir)
    assert len(manifest.documents) == 2
    assert manifest.documents[0].source_type == SourceType.PAPER
    assert manifest.documents[0].content_hash == "hash1"


def test_path_traversal_is_rejected(corpus_dir) -> None:
    entry = ManifestEntry(
        id="evil",
        title="evil",
        url="https://example.com",
        path="../secret.md",
    )
    with pytest.raises(CorpusError):
        read_entry_text(corpus_dir, entry)


def test_ingest_corpus(store, corpus_dir) -> None:
    documents, chunks = ingest_corpus(store, corpus_dir)
    assert documents == 2
    assert chunks >= 2
    assert store.count_documents() == 2
    assert store.count_chunks() == chunks
