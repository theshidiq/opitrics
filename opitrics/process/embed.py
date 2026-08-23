"""Multilingual embeddings, cached to disk.

Embedding is the slowest local step, so vectors are cached keyed by
(model, comment_id). Re-running clustering with different parameters
then costs nothing — which is the whole point, because cluster tuning
is iterative.
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class Embedder:
    def __init__(
        self,
        model_name: str,
        device: str = "mps",
        batch_size: int = 32,
        cache_dir: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None

    @property
    def model(self):
        """Loaded lazily — importing torch and pulling weights is slow,
        and a cache hit means we never need either."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("loading %s on %s…", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        slug = self.model_name.replace("/", "_")
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{slug}__{digest}.pkl"

    def encode(self, texts: list[str], cache_key: str | None = None) -> np.ndarray:
        """Embed texts, reusing a cached matrix when the inputs match."""
        path = self._cache_path(cache_key) if cache_key else None

        if path and path.exists():
            with path.open("rb") as fh:
                cached = pickle.load(fh)
            if cached["count"] == len(texts) and cached["checksum"] == _checksum(texts):
                log.info("embeddings loaded from cache (%d vectors)", len(texts))
                return cached["vectors"]
            log.info("cache stale — re-embedding")

        log.info("embedding %d comments on %s…", len(texts), self.device)
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        if path:
            with path.open("wb") as fh:
                pickle.dump(
                    {
                        "vectors": vectors,
                        "count": len(texts),
                        "checksum": _checksum(texts),
                    },
                    fh,
                )
        return vectors


def _checksum(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8", errors="ignore"))
        h.update(b"\x00")
    return h.hexdigest()
