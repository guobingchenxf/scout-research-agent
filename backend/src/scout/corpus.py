"""Frozen corpus manifest, document loading and chunking."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    Chunk,
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
    utc_now,
)


class CorpusError(Exception):
    """Raised when the corpus manifest or a document path is invalid."""


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    url: str
    source_type: SourceType = SourceType.WEB
    trust: TrustLevel = TrustLevel.SECONDARY
    retrieval_method: RetrievalMethod = RetrievalMethod.LOCAL
    license: str | None = None
    published_at: str | None = None
    fetched_at: str = Field(default_factory=utc_now)
    content_hash: str = ""
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    generated_at: str | None = None
    documents: list[ManifestEntry] = Field(default_factory=list)


def manifest_path(corpus_dir: str | Path) -> Path:
    return Path(corpus_dir) / "manifest.json"


def load_manifest(corpus_dir: str | Path) -> Manifest:
    path = manifest_path(corpus_dir)
    if not path.exists():
        return Manifest()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"invalid manifest JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CorpusError(f"manifest must be a JSON object: {path}")
    if int(payload.get("version", 1)) != 1:
        raise CorpusError(f"unsupported manifest version: {payload.get('version')}")
    return Manifest.model_validate(payload)


def save_manifest(corpus_dir: str | Path, manifest: Manifest) -> Path:
    path = manifest_path(corpus_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def _resolve_inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise CorpusError(f"path escapes corpus directory: {relative}")
    return target


def read_entry_text(corpus_dir: str | Path, entry: ManifestEntry) -> str:
    path = _resolve_inside(Path(corpus_dir), entry.path)
    if not path.exists():
        raise CorpusError(f"missing corpus file: {entry.path}")
    return path.read_text(encoding="utf-8")


def estimate_tokens(text: str) -> int:
    ascii_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    cjk_chars = len(re.findall(r"[一-鿿]", text))
    return max(1, ascii_words + cjk_chars)


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks, preferring sentence boundaries."""

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap, max_chars // 2))

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    while start < length:
        end = min(length, start + max_chars)
        if end < length:
            window = normalized[start:end]
            candidates = [
                window.rfind("。"),
                window.rfind("！"),
                window.rfind("？"),
                window.rfind(". "),
                window.rfind("\n"),
            ]
            cut = max(candidates)
            if cut > int(max_chars * 0.5):
                end = start + cut + 1
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(
    entry: ManifestEntry,
    text: str,
    *,
    max_chars: int = 1200,
    overlap: int = 150,
) -> list[Chunk]:
    return [
        Chunk(
            id=f"{entry.id}:{ordinal}",
            doc_id=entry.id,
            ordinal=ordinal,
            text=piece,
            token_count=estimate_tokens(piece),
        )
        for ordinal, piece in enumerate(chunk_text(text, max_chars=max_chars, overlap=overlap))
    ]


def iter_entries(corpus_dir: str | Path) -> Iterable[ManifestEntry]:
    yield from load_manifest(corpus_dir).documents


def load_corpus(corpus_dir: str | Path) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for entry in iter_entries(corpus_dir):
        try:
            text = read_entry_text(corpus_dir, entry)
        except CorpusError:
            continue
        if not text.strip():
            continue
        documents.append(
            SourceDocument(
                id=entry.id,
                title=entry.title,
                url=entry.url,
                source_type=entry.source_type,
                trust=entry.trust,
                retrieval_method=entry.retrieval_method,
                license=entry.license,
                published_at=entry.published_at,
                fetched_at=entry.fetched_at,
                content_hash=entry.content_hash,
                text=text,
                metadata=entry.metadata,
            )
        )
    return documents


def ingest_corpus(store: Any, corpus_dir: str | Path) -> tuple[int, int]:
    """Load every manifest entry into the store. Returns (documents, chunks)."""

    doc_count = 0
    chunk_count = 0
    for entry in iter_entries(corpus_dir):
        try:
            text = read_entry_text(corpus_dir, entry)
        except CorpusError:
            continue
        if not text.strip():
            continue
        doc = SourceDocument(
            id=entry.id,
            title=entry.title,
            url=entry.url,
            source_type=entry.source_type,
            trust=entry.trust,
            retrieval_method=entry.retrieval_method,
            license=entry.license,
            published_at=entry.published_at,
            fetched_at=entry.fetched_at,
            content_hash=entry.content_hash,
            text=text,
            metadata=entry.metadata,
        )
        chunks = build_chunks(entry, text)
        store.ingest_document(doc, chunks)
        doc_count += 1
        chunk_count += len(chunks)
    return doc_count, chunk_count
