"""Clean, embed, dedupe and cluster a subject's cached comments.

    python scripts/cluster.py --subject byd-racco
    python scripts/cluster.py --subject byd-racco --min-cluster-size 25

Embeddings are cached, so re-running with different clustering
parameters is fast. Nothing here touches the network or spends quota.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.process.clean import clean_comments  # noqa: E402
from opitrics.process.cluster import (  # noqa: E402
    cluster_hdbscan,
    cluster_kmeans,
    dedupe,
    representative_indices,
)
from opitrics.process.embed import Embedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument(
        "--method",
        choices=["kmeans", "hdbscan"],
        default="kmeans",
        help="kmeans partitions everything; hdbscan finds dense regions and marks the rest noise",
    )
    ap.add_argument("--clusters", type=int, default=40, help="k, for --method kmeans")
    ap.add_argument("--min-cluster-size", type=int, default=settings.min_cluster_size)
    ap.add_argument("--min-samples", type=int, help="HDBSCAN min_samples; lower = fewer noise points")
    ap.add_argument("--dedupe-threshold", type=float, default=0.93)
    ap.add_argument("--pca-dims", type=int, default=50, help="0 disables PCA")
    ap.add_argument("--preview", type=int, default=4, help="comments shown per cluster")
    ap.add_argument("--top", type=int, default=20, help="clusters to print")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached embeddings")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    db = Database(settings.database_path)
    rows = db.comments_for_subject(args.subject)
    if not rows:
        print(f"\nNothing cached for {args.subject!r} — run scripts/fetch.py first.\n")
        return 1

    # ── clean ───────────────────────────────────────────────
    print(f"\n{BOLD}Cleaning{RESET}")
    comments, stats = clean_comments(rows, min_length=settings.min_comment_words)
    print(stats.report())

    texts = [c.text for c in comments]

    # ── embed ───────────────────────────────────────────────
    print(f"\n{BOLD}Embedding{RESET}")
    cache_dir = None if args.no_cache else settings.database_path.parent / "embeddings"
    embedder = Embedder(
        settings.embedding_model,
        device=settings.torch_device,
        batch_size=settings.embed_batch_size,
        cache_dir=cache_dir,
    )
    vectors = embedder.encode(texts, cache_key=f"{args.subject}:{len(texts)}")

    # ── dedupe ──────────────────────────────────────────────
    print(f"\n{BOLD}Deduplicating{RESET}")
    kept_vectors, kept_idx, dup_counts = dedupe(vectors, threshold=args.dedupe_threshold)
    kept_comments = [comments[i] for i in kept_idx]
    print(f"  {len(comments):,} → {len(kept_comments):,}")

    repeated = sorted(dup_counts.items(), key=lambda kv: -kv[1])[:5]
    if repeated and repeated[0][1] > 3:
        print(f"\n  {DIM}most-repeated comments (copypasta){RESET}")
        for idx, count in repeated:
            if count < 3:
                continue
            print(f"    {count:>3}×  {comments[idx].text[:62]}")

    # ── cluster ─────────────────────────────────────────────
    print(f"\n{BOLD}Clustering{RESET}")
    if args.method == "kmeans":
        labels, clusters = cluster_kmeans(
            kept_vectors,
            n_clusters=args.clusters,
            reduce_to=args.pca_dims or None,
        )
    else:
        labels, clusters = cluster_hdbscan(
            kept_vectors,
            min_cluster_size=args.min_cluster_size,
            min_samples=args.min_samples,
            reduce_to=args.pca_dims or None,
        )

    if not clusters:
        print(f"\n{YELLOW}No clusters found — try a smaller --min-cluster-size{RESET}\n")
        return 1

    weights = np.array([c.weight for c in kept_comments])
    clusters.sort(key=lambda c: -c.size)

    clustered = sum(c.size for c in clusters)
    print(f"\n{BOLD}{len(clusters)} clusters{RESET} covering {clustered:,} comments "
          f"{DIM}({clustered / len(kept_comments):.0%} of deduped){RESET}\n")

    export = []
    for rank, cl in enumerate(clusters, 1):
        reps = representative_indices(cl, kept_vectors, k=25, weights=weights)
        rep_comments = [kept_comments[i] for i in reps]
        total_likes = sum(kept_comments[i].like_count for i in cl.indices)
        channels = {}
        for i in cl.indices:
            ch = kept_comments[i].channel_title
            channels[ch] = channels.get(ch, 0) + 1
        top_channel = max(channels.items(), key=lambda kv: kv[1])

        if rank <= args.top:
            print(f"{BOLD}#{rank}{RESET} {GREEN}{cl.size:>4} comments{RESET} "
                  f"{DIM}· {total_likes:,} likes · {len(channels)} channels · "
                  f"top: {top_channel[0][:26]} ({top_channel[1]}){RESET}")
            for c in rep_comments[: args.preview]:
                print(f"     {DIM}[{c.like_count:>3}♥]{RESET} {c.text[:88]}")
            print()

        export.append(
            {
                "cluster_id": cl.id,
                "rank": rank,
                "size": cl.size,
                "total_likes": total_likes,
                "channel_spread": len(channels),
                "top_channel": top_channel[0],
                "representatives": [
                    {
                        "comment_id": c.comment_id,
                        "text": c.text,
                        "like_count": c.like_count,
                        "channel": c.channel_title,
                        "is_reply": c.is_reply,
                    }
                    for c in rep_comments
                ],
            }
        )

    # Freeze the previous analysis before overwriting, so a re-run with
    # different parameters stays comparable against the old one.
    snapshot = paths.snapshot()
    if snapshot:
        print(f"{DIM}previous run archived → runs/{snapshot.name}{RESET}")

    out = paths.clusters
    out.write_text(
        json.dumps(
            {
                "subject": args.subject,
                "raw_comments": len(rows),
                "cleaned": len(comments),
                "deduped": len(kept_comments),
                "clustered": clustered,
                "min_cluster_size": args.min_cluster_size,
                "clusters": export,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{DIM}written: {out}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
