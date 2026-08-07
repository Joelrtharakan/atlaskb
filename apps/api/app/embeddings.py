"""Pluggable embedding backends.

Embeddings are produced directly (local sentence-transformers or the OpenAI
embeddings API) — never through OpenRouter, which does not serve embeddings.

Backends:
  * ``local``  — sentence-transformers, in-process, no API key, good default.
  * ``openai`` — OpenAI embeddings API (requires ``OPENAI_API_KEY``).
  * ``fake``   — deterministic hash-based vectors; fast, offline, for tests.

All backends return unit-length vectors of ``settings.embedding_dim`` so cosine
similarity in pgvector behaves consistently regardless of backend.
"""

from __future__ import annotations

import hashlib
import math

from app.config import settings

_local_model = None


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic pseudo-embeddings from a hash of the text.

    Not semantically meaningful, but stable and cheap — sufficient to exercise
    the pgvector code path in tests without downloading a model.
    """
    dim = settings.embedding_dim
    out: list[list[float]] = []
    for text in texts:
        vec = [0.0] * dim
        for token in text.lower().split():
            h = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(dim):
                # Map each dimension to a byte of the (repeating) digest.
                vec[i] += (h[i % len(h)] - 127.5) / 127.5
        out.append(_normalize(vec))
    return out


def _local_embed(texts: list[str]) -> list[list[float]]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(
            settings.embedding_model, device=settings.embedding_device
        )
    vecs = _local_model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def _openai_embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [_normalize(d.embedding) for d in resp.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the configured backend."""
    if not texts:
        return []
    backend = settings.embedding_backend.lower()
    if backend == "fake":
        return _fake_embed(texts)
    if backend == "openai":
        return _openai_embed(texts)
    return _local_embed(texts)


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([text])[0]
