"""Embedding generation behind a swappable interface (DOC_03 §4.3).

Default is Voyage AI ``voyage-3`` (1024-dim). A deterministic offline ``hash``
embedder keeps dev and the test suite fully offline; a ``local``
sentence-transformers option is available via the ``local-embed`` extra.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Protocol, runtime_checkable

import structlog
from app.config import Settings

log = structlog.get_logger("embed")

BATCH_SIZE = 16  # DOC_03 §4.3


class EmbeddingError(Exception):
    """Raised when embedding generation fails after retries (DOC_03 §6)."""


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class HashEmbedder:
    """Deterministic, network-free embedder for offline dev and tests."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec: list[float] = []
        counter = 0
        while len(vec) < self.dim:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            for b in digest:
                vec.append((b / 255.0) * 2.0 - 1.0)
                if len(vec) == self.dim:
                    break
            counter += 1
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class VoyageEmbedder:
    """voyage-3 embeddings with exponential-backoff retry (DOC_03 §4.3, §6)."""

    def __init__(self, api_key: str, model: str = "voyage-3", dim: int = 1024) -> None:
        import voyageai

        self._client = voyageai.Client(api_key=api_key)  # type: ignore[attr-defined]
        self._model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for batch in _batched(texts, BATCH_SIZE):
            out.extend(self._embed_batch(batch))
        return out

    def _embed_batch(self, batch: list[str], retries: int = 4) -> list[list[float]]:
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                result = self._client.embed(batch, model=self._model, input_type="document")
                return [list(e) for e in result.embeddings]
            except Exception as exc:  # noqa: BLE001 — retry any API failure
                last_exc = exc
                log.warning("voyage_embed_retry", attempt=attempt, error=str(exc))
                time.sleep(delay)
                delay *= 2
        raise EmbeddingError(str(last_exc))


class LocalEmbedder:
    """sentence-transformers fallback (requires the `local-embed` extra)."""

    def __init__(self, model_name: str = "sentence-transformers/all-mpnet-base-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


def make_embedder(settings: Settings) -> Embedder:
    """Select an embedder from settings, falling back to hash when offline."""
    provider = settings.embedding_provider.lower()
    if provider == "voyage" and settings.voyage_api_key:
        return VoyageEmbedder(
            api_key=settings.voyage_api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    if provider == "local":
        return LocalEmbedder()
    if provider == "voyage":
        log.warning("voyage_key_missing_fallback_hash")
    return HashEmbedder(dim=settings.embedding_dim)
