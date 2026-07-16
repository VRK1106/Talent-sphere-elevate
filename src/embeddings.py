"""Embedding utilities built on ``BAAI/bge-large-en-v1.5``.

Design notes (these materially affect retrieval quality):

* The model is loaded once per session via ``@st.cache_resource``.
* Device auto-selects CUDA when available, else CPU.
* Embeddings are always L2-normalized (``normalize_embeddings=True``) to pair
  correctly with the cosine-distance Chroma collection.
* Queries — and only queries — get the BGE instruction prefix.
"""

from __future__ import annotations

import streamlit as st
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL, QUERY_INSTRUCTION

_BATCH_SIZE = 32


def _auto_device() -> str:
    """Return ``"cuda"`` when a GPU is available, otherwise ``"cpu"``."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001 - torch missing/broken -> safe CPU fallback
        return "cpu"


@st.cache_resource(show_spinner=False)
def get_model() -> SentenceTransformer:
    """Load and cache the sentence-transformer model (once per session).

    The first load downloads ~1.3GB, so we wrap it in a spinner that
    communicates progress to the user.
    """
    with st.spinner("Loading embedding model (first run downloads ~1.3GB)…"):
        return SentenceTransformer(EMBEDDING_MODEL, device=_auto_device())


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed document chunks (no query prefix).

    Args:
        texts: Raw chunk texts.

    Returns:
        A list of 1024-dim, L2-normalized embedding vectors.
    """
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=_BATCH_SIZE,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float]:
    """Embed a single search query with the required BGE instruction prefix.

    Args:
        text: The user's raw search query.

    Returns:
        A single 1024-dim, L2-normalized embedding vector.
    """
    model = get_model()
    vector = model.encode(
        QUERY_INSTRUCTION + text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector.tolist()
