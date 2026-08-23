"""Sentiment scoring and aspect mapping, both running locally.

Sentiment uses a multilingual model so Japanese, Chinese and English
comments are scored natively rather than through a translation step
that would flatten tone.

Aspect mapping uses zero-shot NLI: each cluster's representative text
is tested against the taxonomy's hypothesis sentences. No training data
needed, and adding an aspect is a one-line change to the taxonomy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from opitrics.analyze.taxonomy import Aspect

log = logging.getLogger(__name__)

# Below this cosine similarity, a cluster is called unmapped rather
# than forced into the nearest aspect. Unmapped clusters are the
# interesting pile — they are where genuinely new topics surface.
# Calibrated against the Racco corpus: clear on-topic clusters land
# around 0.50-0.65, ambiguous ones around 0.42-0.47.
MAP_THRESHOLD = 0.46


@dataclass
class SentimentScore:
    positive: float
    neutral: float
    negative: float

    @property
    def polarity(self) -> float:
        """Single number in [-1, 1] for charting."""
        return self.positive - self.negative

    @property
    def intensity(self) -> float:
        """How strongly felt, regardless of direction. A cluster that is
        60/0/40 is far more contentious than one that is 30/40/30, and
        volume-ranked lists hide exactly that."""
        return self.positive + self.negative

    @property
    def label(self) -> str:
        if self.polarity > 0.15:
            return "positive"
        if self.polarity < -0.15:
            return "negative"
        return "mixed"


class SentimentScorer:
    """Multilingual 3-class sentiment."""

    def __init__(self, model_name: str, device: str = "mps", batch_size: int = 32) -> None:
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._pipe = None

    @property
    def pipe(self):
        if self._pipe is None:
            from transformers import pipeline

            log.info("loading sentiment model %s…", self.model_name)
            self._pipe = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=self.device,
                truncation=True,
                max_length=512,
                top_k=None,
            )
        return self._pipe

    def score(self, texts: list[str]) -> list[SentimentScore]:
        if not texts:
            return []
        log.info("scoring sentiment for %d texts…", len(texts))
        raw = self.pipe(texts, batch_size=self.batch_size)

        scores: list[SentimentScore] = []
        for entry in raw:
            buckets = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
            for item in entry:
                key = _normalise_label(item["label"])
                if key:
                    buckets[key] = float(item["score"])
            scores.append(SentimentScore(**buckets))
        return scores

    def score_weighted(
        self, texts: list[str], weights: np.ndarray | None = None
    ) -> SentimentScore:
        """Aggregate a group of texts into one score.

        Weighting by engagement matters: a comment with 400 likes is one
        opinion several hundred people endorsed, and treating it as
        equal to a zero-like reply understates it.
        """
        scores = self.score(texts)
        if not scores:
            return SentimentScore(0.0, 1.0, 0.0)

        w = np.ones(len(scores)) if weights is None else np.asarray(weights, dtype=float)
        w = w / max(w.sum(), 1e-9)
        return SentimentScore(
            positive=float(sum(s.positive * wi for s, wi in zip(scores, w))),
            neutral=float(sum(s.neutral * wi for s, wi in zip(scores, w))),
            negative=float(sum(s.negative * wi for s, wi in zip(scores, w))),
        )


def _normalise_label(label: str) -> str | None:
    """Different checkpoints spell the classes differently."""
    lowered = label.lower()
    if lowered in {"positive", "pos", "label_2"}:
        return "positive"
    if lowered in {"neutral", "neu", "label_1"}:
        return "neutral"
    if lowered in {"negative", "neg", "label_0"}:
        return "negative"
    return None


@dataclass
class AspectMatch:
    aspect: Aspect | None
    confidence: float
    runners_up: list[tuple[str, float]]
    # Gap to the runner-up. A cluster that matches its top two aspects
    # almost equally has not really been classified, and this is what
    # exposes that — the raw score alone looks confident either way.
    margin: float = 0.0

    @property
    def is_mapped(self) -> bool:
        return self.aspect is not None


class AspectMapper:
    """Map clusters onto the taxonomy by embedding similarity.

    This started out as zero-shot NLI, which is the textbook choice and
    was measurably bad here: on the Racco corpus mDeBERTa put a comment
    about rural charging infrastructure into "brand trust" at 0.96
    confidence, and put reply chatter into "cargo space" at 0.53. With
    ~50 candidate hypotheses the generic-sounding ones absorb
    everything, and nothing is left unmapped because every cluster
    clears the threshold on a wrong label.

    Embedding similarity against short bilingual aspect descriptions
    handled the same cases correctly. It reuses the model already loaded
    for clustering, so it is also faster and costs no extra download.
    """

    def __init__(self, model_name: str, device: str = "mps") -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        self._cache: dict[str, np.ndarray] = {}

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("loading embedding model %s for aspect mapping…", self.model_name)
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def _aspect_matrix(self, aspects: list[Aspect]) -> np.ndarray:
        key = "|".join(a.key for a in aspects)
        if key not in self._cache:
            self._cache[key] = self.model.encode(
                [a.description for a in aspects],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return self._cache[key]

    def map_cluster(
        self,
        texts: list[str],
        aspects: list[Aspect],
        threshold: float = MAP_THRESHOLD,
        sample: int = 12,
        min_margin: float = 0.015,
    ) -> AspectMatch:
        """Assign a cluster to one aspect, or leave it unmapped.

        Pools several representatives rather than trusting one comment —
        clusters are not pure, and one atypical member should not decide
        the label. A cluster is left unmapped when its best score is too
        low *or* when the top two aspects are too close to separate.
        """
        if not texts:
            return AspectMatch(None, 0.0, [])

        chosen = texts[:sample]
        vectors = self.model.encode(
            [t[:1000] for t in chosen],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        # Mean of per-comment similarities, not similarity-of-the-mean:
        # averaging vectors first would let one long comment dominate.
        sims = (vectors @ self._aspect_matrix(aspects).T).mean(axis=0)

        order = np.argsort(-sims)
        best, second = int(order[0]), int(order[1])
        best_score = float(sims[best])
        margin = best_score - float(sims[second])
        runners = [(aspects[int(i)].key, round(float(sims[i]), 3)) for i in order[1:4]]

        if best_score < threshold or margin < min_margin:
            return AspectMatch(None, best_score, runners, margin)
        return AspectMatch(aspects[best], best_score, runners, margin)
