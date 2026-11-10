"""Hybrid BM25 + embedding retrieval over the frozen corpus."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

import numpy as np

from .models import (
    Chunk,
    SearchHit,
    SourceDocument,
    TrustLevel,
)

_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[一-鿿]+")


class EmbeddingError(Exception):
    """Raised when a real embedding provider is unavailable."""


def tokenize(text: str) -> list[str]:
    """English words + Chinese unigrams and bigrams.

    Chinese bigrams improve BM25 over single characters without requiring a
    segmenter dependency. The result is deterministic and cheap.
    """

    lowered = text.lower()
    tokens = _ASCII_WORD.findall(lowered)
    for run in _CJK_RUN.findall(lowered):
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


class BM25Index:
    def __init__(self, chunks: Sequence[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.chunk_ids = [chunk.id for chunk in chunks]
        self.k1 = k1
        self.b = b
        self._tokens = [tokenize(chunk.text) for chunk in chunks]
        self._tf = [Counter(tokens) for tokens in self._tokens]
        self._doc_len = [len(tokens) for tokens in self._tokens]
        self._n = len(chunks)
        self._avgdl = (sum(self._doc_len) / self._n) if self._n else 1.0
        self._df: Counter[str] = Counter()
        for tokens in self._tokens:
            self._df.update(set(tokens))

    def search(self, query: str, k: int | None = None) -> list[tuple[str, float]]:
        query_tokens = tokenize(query)
        if not query_tokens or not self._n:
            return []
        scores: list[tuple[str, float]] = []
        for index, chunk_id in enumerate(self.chunk_ids):
            score = 0.0
            tf = self._tf[index]
            doc_len = self._doc_len[index] or 1
            for token in query_tokens:
                frequency = tf.get(token, 0)
                if not frequency:
                    continue
                df = self._df.get(token, 0)
                idf = math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * doc_len / (self._avgdl or 1.0)
                )
                score += idf * (frequency * (self.k1 + 1.0)) / denominator
            if score > 0:
                scores.append((chunk_id, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:k] if k is not None else scores


class EmbeddingProvider(Protocol):
    dim: int

    def embed(self, text: str) -> np.ndarray: ...

    def embed_many(self, texts: Sequence[str]) -> np.ndarray: ...


class HashEmbedding:
    """Deterministic, offline embeddings for tests and CI.

    Semantically weak by design; the real evaluation uses fastembed or another
    provider. The point is reproducibility without a network or GPU.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.embed(text) for text in texts])


class FastEmbedProvider:
    """Optional real embeddings via fastembed (ONNX, no torch)."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self.model_name = model_name
        self._model: Any = None
        self.dim = 0

    def _ensure(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingError(
                "fastembed is not installed; run `pip install -e '.[embed]'` "
                "or set SCOUT_EMBEDDING_PROVIDER=hash"
            ) from exc
        self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim or 1), dtype=np.float32)
        model = self._ensure()
        vectors = np.asarray(list(model.embed(list(texts))), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
        self.dim = int(vectors.shape[1])
        return vectors


def make_embedding_provider(
    provider: str,
    *,
    model_name: str = "BAAI/bge-small-zh-v1.5",
    dim: int = 384,
) -> EmbeddingProvider:
    if provider == "fastembed":
        return FastEmbedProvider(model_name=model_name)
    return HashEmbedding(dim=dim)


def _minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(values.min())
    high = float(values.max())
    if high - low < 1e-9:
        return np.zeros_like(values)
    return (values - low) / (high - low)


def _snippet(text: str, query: str, max_chars: int = 320) -> str:
    if len(text) <= max_chars:
        return text.strip()
    lowered = text.lower()
    position = -1
    for token in tokenize(query):
        if len(token) < 2:
            continue
        found = lowered.find(token)
        if found >= 0:
            position = found
            break
    if position < 0:
        return text[:max_chars].strip()
    start = max(0, position - 80)
    end = min(len(text), start + max_chars)
    return text[start:end].strip()


class HybridIndex:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        documents: Iterable[SourceDocument],
        *,
        embedding_provider: str = "hash",
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
        embedding_dim: int = 384,
    ) -> None:
        self.chunks = list(chunks)
        self.documents = {doc.id: doc for doc in documents}
        self.bm25 = BM25Index(self.chunks)
        self.embedder = make_embedding_provider(
            embedding_provider, model_name=embedding_model, dim=embedding_dim
        )
        self.embeddings = (
            self.embedder.embed_many([chunk.text for chunk in self.chunks])
            if self.chunks
            else np.zeros((0, embedding_dim), dtype=np.float32)
        )

    def search(
        self,
        query: str,
        *,
        k: int = 8,
        source_types: set[str] | None = None,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        if not self.chunks:
            return []

        bm25_scores = dict(self.bm25.search(query, len(self.chunks)))
        bm25_vector = np.asarray(
            [bm25_scores.get(chunk.id, 0.0) for chunk in self.chunks], dtype=np.float32
        )
        query_tokens = set(tokenize(query))
        query_vector = self.embedder.embed(query)
        if self.embeddings.size:
            cosine = self.embeddings @ query_vector
        else:
            cosine = np.zeros(len(self.chunks), dtype=np.float32)

        # BM25 is the candidate gate for the deterministic hash embedding:
        # hash vectors are semantically weak, so unrelated queries must not
        # produce hits just because cosine normalization has a maximum.
        # A real provider (fastembed) is allowed to expand the candidate set.
        lexical_indices = [index for index, value in enumerate(bm25_vector) if value > 0]
        if lexical_indices:
            candidate_indices = lexical_indices
        elif isinstance(self.embedder, FastEmbedProvider):
            candidate_indices = list(range(len(self.chunks)))
        else:
            return []

        bm25_norm = _minmax(bm25_vector)
        cosine_norm = _minmax((cosine + 1.0) / 2.0)
        combined = 0.6 * bm25_norm + 0.4 * cosine_norm

        ranked: list[tuple[int, float]] = []
        for index in candidate_indices:
            chunk = self.chunks[index]
            document = self.documents.get(chunk.doc_id)
            if document is None:
                continue
            if source_types and document.source_type.value not in source_types:
                continue
            boost = 0.03 if document.trust == TrustLevel.PRIMARY else 0.0
            if document.trust == TrustLevel.UNTRUSTED:
                boost = -0.05
            title_tokens = set(tokenize(document.title))
            title_hit = (
                len(query_tokens & title_tokens) / len(query_tokens) if query_tokens else 0.0
            )
            score = float(combined[index] + 0.08 * title_hit + boost)
            if score < min_score:
                continue
            ranked.append((index, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        hits: list[SearchHit] = []
        for index, score in ranked[:k]:
            chunk = self.chunks[index]
            document = self.documents[chunk.doc_id]
            hits.append(
                SearchHit(
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.id,
                    score=score,
                    snippet=_snippet(chunk.text, query),
                    title=document.title,
                    url=document.url,
                    trust=document.trust,
                    retrieval_method=document.retrieval_method,
                )
            )
        return hits


def build_index_from_store(
    store: Any,
    *,
    embedding_provider: str = "hash",
    embedding_model: str = "BAAI/bge-small-zh-v1.5",
    embedding_dim: int = 384,
) -> HybridIndex:
    return HybridIndex(
        store.list_chunks(),
        store.list_documents(),
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
    )
