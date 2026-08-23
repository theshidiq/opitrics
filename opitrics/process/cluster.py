"""Near-duplicate removal and bottom-up theme discovery.

Dedupe runs first so copypasta cannot fake a consensus — the Racco
corpus contains political slogans posted verbatim dozens of times, and
left in they would form a large, entirely artificial "cluster".

Clustering then finds themes without a predefined aspect list. What
comes out is whatever people actually argued about, which is the point:
a fixed list can only confirm what you already suspected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

NOISE = -1


@dataclass
class Cluster:
    """A discovered theme. Named later — at this stage it is just a set
    of comments that sit close together in embedding space."""

    id: int
    indices: list[int]
    centroid: np.ndarray

    @property
    def size(self) -> int:
        return len(self.indices)


def dedupe(
    vectors: np.ndarray, threshold: float = 0.93
) -> tuple[np.ndarray, list[int], dict[int, int]]:
    """Drop near-duplicates, keeping one representative of each group.

    Returns (kept_vectors, kept_indices, duplicate_counts) where the
    counts record how many copies each survivor stood for — that number
    is real signal (a slogan posted 40 times says something) but it is
    signal about repetition, not about 40 independent opinions.

    Uses a blocked matmul rather than a full N×N matrix: at 15k comments
    the full similarity matrix is ~1.8GB, which is a lot to ask of a
    16GB laptop that is also holding a transformer.
    """
    n = len(vectors)
    keep: list[int] = []
    dup_counts: dict[int, int] = {}
    absorbed = np.zeros(n, dtype=bool)

    block = 512
    for start in range(0, n, block):
        end = min(start + block, n)
        for i in range(start, end):
            if absorbed[i]:
                continue
            keep.append(i)
            dup_counts[i] = 1

            # Compare against everything after i only — earlier items
            # were already either kept or absorbed.
            if i + 1 >= n:
                continue
            sims = vectors[i + 1 :] @ vectors[i]
            close = np.where(sims >= threshold)[0] + i + 1
            for j in close:
                if not absorbed[j]:
                    absorbed[j] = True
                    dup_counts[i] += 1

    log.info(
        "dedupe: %d → %d (%d absorbed as near-duplicates)",
        n,
        len(keep),
        n - len(keep),
    )
    return vectors[keep], keep, dup_counts


def _reduce(vectors: np.ndarray, reduce_to: int | None) -> np.ndarray:
    """PCA down to a workable dimensionality, re-normalised so euclidean
    distance remains a proxy for cosine similarity."""
    if not reduce_to or vectors.shape[1] <= reduce_to:
        return vectors

    from sklearn.decomposition import PCA

    n_components = min(reduce_to, len(vectors) - 1, vectors.shape[1])
    log.info("reducing %d dims → %d via PCA", vectors.shape[1], n_components)
    working = PCA(n_components=n_components, random_state=42).fit_transform(vectors)
    norms = np.linalg.norm(working, axis=1, keepdims=True)
    return working / np.clip(norms, 1e-9, None)


def _build_clusters(labels: np.ndarray, vectors: np.ndarray) -> list[Cluster]:
    clusters: list[Cluster] = []
    for label in sorted(set(labels.tolist())):
        if label == NOISE:
            continue
        idx = np.where(labels == label)[0].tolist()
        centroid = vectors[idx].mean(axis=0)
        centroid /= np.clip(np.linalg.norm(centroid), 1e-9, None)
        clusters.append(Cluster(id=int(label), indices=idx, centroid=centroid))
    return clusters


def cluster_kmeans(
    vectors: np.ndarray, n_clusters: int = 40, reduce_to: int | None = 50
) -> tuple[np.ndarray, list[Cluster]]:
    """Partition comments into themes with k-means.

    This is the default because comment embeddings form one continuous
    cloud rather than dense islands separated by empty space. Measured
    on the Racco corpus, HDBSCAN either collapsed 8,000 comments into a
    single blob or discarded 90%+ as noise at every parameter setting
    tried — the density assumption simply does not hold here.

    k-means makes a different trade: every comment lands somewhere, so
    genuinely off-topic remarks get absorbed into whichever theme they
    sit nearest. That is acceptable because the aspect-mapping stage
    downstream can route a whole cluster to "unmapped", which recovers
    the signal HDBSCAN's noise label would have given us.
    """
    from sklearn.cluster import KMeans

    working = _reduce(vectors, reduce_to)
    k = min(n_clusters, len(working))
    log.info("k-means clustering %d comments into %d themes…", len(working), k)
    labels = KMeans(n_clusters=k, random_state=42, n_init=4).fit_predict(working)
    clusters = _build_clusters(labels, vectors)
    sizes = sorted((c.size for c in clusters), reverse=True)
    log.info(
        "%d clusters — largest %d, smallest %d", len(clusters), sizes[0], sizes[-1]
    )
    return labels, clusters


def cluster_hdbscan(
    vectors: np.ndarray,
    min_cluster_size: int = 15,
    min_samples: int | None = None,
    reduce_to: int | None = 50,
) -> tuple[np.ndarray, list[Cluster]]:
    """Density-based clustering, kept as an alternative.

    Can label a comment as noise, which is conceptually right for a
    one-off rant. In practice it needs corpora with genuinely separable
    topics — see `cluster_kmeans` for why it did not suit this data.
    """
    import hdbscan

    working = _reduce(vectors, reduce_to)

    log.info("clustering %d comments (min_cluster_size=%d)…", len(working), min_cluster_size)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples or max(3, min_cluster_size // 3),
        metric="euclidean",
        # "leaf" splits the dendrogram at its finest stable level. EOM
        # (excess of mass) prefers large stable clusters, which on this
        # corpus produced one 1,400-comment blob that merged distinct
        # arguments about China, EVs and Japanese manufacturing — the
        # exact distinctions the analysis needs to keep apart.
        cluster_selection_method="leaf",
        prediction_data=False,
    )
    labels = clusterer.fit_predict(working.astype(np.float64))

    clusters = _build_clusters(labels, vectors)
    noise_n = int((labels == NOISE).sum())
    log.info(
        "found %d clusters, %d noise (%.0f%%)",
        len(clusters),
        noise_n,
        100 * noise_n / max(len(labels), 1),
    )
    return labels, clusters


def representative_indices(
    cluster: Cluster, vectors: np.ndarray, k: int = 25, weights: np.ndarray | None = None
) -> list[int]:
    """Pick the comments that best represent a cluster.

    Sorted by closeness to the centroid, optionally nudged by engagement
    weight so a heavily-liked comment is more likely to be among the
    quotes you end up putting on screen.
    """
    idx = np.array(cluster.indices)
    sims = vectors[idx] @ cluster.centroid
    if weights is not None:
        sims = sims * (1.0 + 0.15 * np.log1p(weights[idx]))
    order = np.argsort(-sims)
    return idx[order][:k].tolist()
