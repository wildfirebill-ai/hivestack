"""Embeddings — CPU-only, offline. Uses fastembed (ONNX MiniLM, 384-dim) when
available; returns None otherwise and search degrades to keyword-only."""

from __future__ import annotations

import os
import threading

import numpy as np

from ..config import settings

_lock = threading.Lock()
_singleton = None


def _cache_dir() -> str:
    return os.getenv("HIVESTACK_EMBED_CACHE") or str(settings.models_dir / "embed")


def available() -> bool:
    return _get_encoder() is not None


def _get_encoder():
    global _singleton
    with _lock:
        if _singleton is None:
            try:
                from fastembed import TextEmbedding

                _singleton = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2", cache_dir=_cache_dir())
                _singleton._mode = "fastembed"
            except Exception:  # noqa: BLE001
                _singleton = None
    return _singleton


def encode(texts: list[str]) -> np.ndarray | None:
    enc = _get_encoder()
    if enc is None:
        return None
    clean = [t or " " for t in texts]
    try:
        return np.asarray(list(enc.embed(clean, batch_size=16)), dtype=np.float32)
    except Exception:  # noqa: BLE001  (download failure when offline + uncached)
        return None


def embed_one(text: str) -> list[float] | None:
    vec = encode([text])
    if vec is None:
        return None
    return vec[0].tolist()


def cos(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    import numpy as _np

    a = _np.asarray(a, dtype=_np.float32)
    b = _np.asarray(b, dtype=_np.float32)
    na = _np.linalg.norm(a)
    nb = _np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(_np.dot(a, b) / (na * nb))