"""Score clusters for sentiment and map them onto the aspect taxonomy.

    python scripts/analyze.py --subject byd-racco --types kei ev

Reads the cluster JSON written by scripts/cluster.py, so it costs no
quota and no network. Both models run locally.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.sentiment import (  # noqa: E402
    AspectMapper,
    SentimentScorer,
)
from opitrics.analyze.taxonomy import aspects_for  # noqa: E402
from opitrics.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def bar(polarity: float, width: int = 18) -> str:
    """A centred bar: negative extends left, positive right."""
    half = width // 2
    filled = int(abs(polarity) * half)
    if polarity >= 0:
        return f"{' ' * half}{GREEN}{'█' * filled}{RESET}{' ' * (half - filled)}"
    return f"{' ' * (half - filled)}{RED}{'█' * filled}{RESET}{' ' * half}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument(
        "--types",
        nargs="*",
        default=[],
        help="vehicle types for add-on aspects: kei ev truck",
    )
    ap.add_argument("--name", help="display name, e.g. 'BYD Racco'")
    ap.add_argument("--threshold", type=float, default=0.46)
    ap.add_argument("--min-margin", type=float, default=0.015,
                    help="minimum gap to the runner-up aspect")
    ap.add_argument("--sample", type=int, default=10,
                    help="representatives classified per cluster")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    paths.write_meta(args.name or "", args.types)
    src = paths.clusters
    if not src.exists():
        print(f"\n{src} not found — run scripts/cluster.py first.\n")
        return 1

    data = json.loads(src.read_text(encoding="utf-8"))
    clusters = data["clusters"]
    aspects = aspects_for(args.types)
    print(f"\n{BOLD}{len(clusters)} clusters{RESET} · {len(aspects)} candidate aspects "
          f"{DIM}(types: {', '.join(args.types) or 'none'}){RESET}\n")

    scorer = SentimentScorer(
        settings.sentiment_model,
        device=settings.torch_device,
        batch_size=settings.embed_batch_size,
    )
    # Aspect mapping reuses the embedding model, not the zero-shot one:
    # cross-lingual NLI misclassified badly on this corpus (see
    # AspectMapper's docstring), and embeddings are already loaded.
    mapper = AspectMapper(settings.embedding_model, device=settings.torch_device)

    results = []
    for i, cl in enumerate(clusters, 1):
        reps = cl["representatives"]
        texts = [r["text"] for r in reps]
        weights = np.array([1.0 + np.log1p(r["like_count"]) for r in reps])

        sentiment = scorer.score_weighted(texts, weights)
        match = mapper.map_cluster(
            texts,
            aspects,
            threshold=args.threshold,
            sample=args.sample,
            min_margin=args.min_margin,
        )

        results.append(
            {
                "cluster_id": cl["cluster_id"],
                "size": cl["size"],
                "total_likes": cl["total_likes"],
                "channel_spread": cl["channel_spread"],
                "aspect": match.aspect.key if match.aspect else None,
                "aspect_label": match.aspect.label if match.aspect else None,
                "aspect_group": match.aspect.group if match.aspect else None,
                "is_meta": match.aspect.is_meta if match.aspect else False,
                "confidence": round(match.confidence, 3),
                "margin": round(match.margin, 3),
                "runners_up": match.runners_up,
                "sentiment": {
                    "positive": round(sentiment.positive, 3),
                    "neutral": round(sentiment.neutral, 3),
                    "negative": round(sentiment.negative, 3),
                    "polarity": round(sentiment.polarity, 3),
                    "intensity": round(sentiment.intensity, 3),
                    "label": sentiment.label,
                },
                "quotes": [
                    {"text": r["text"], "like_count": r["like_count"]}
                    for r in reps[:5]
                ],
            }
        )
        print(f"  {DIM}{i}/{len(clusters)}{RESET}", end="\r", flush=True)

    # ── report ──────────────────────────────────────────────
    car = [r for r in results if r["aspect"] and not r["is_meta"]]
    meta = [r for r in results if r["is_meta"]]
    unmapped = [r for r in results if not r["aspect"]]

    total = sum(r["size"] for r in results)
    car_n = sum(r["size"] for r in car)
    meta_n = sum(r["size"] for r in meta)
    un_n = sum(r["size"] for r in unmapped)

    print(f"\n{BOLD}Mapping{RESET}")
    print(f"  {GREEN}{car_n:>6,}{RESET} about the car   {DIM}({car_n/total:.0%}, {len(car)} clusters){RESET}")
    print(f"  {YELLOW}{meta_n:>6,}{RESET} meta / off-car  {DIM}({meta_n/total:.0%}, {len(meta)} clusters){RESET}")
    print(f"  {CYAN}{un_n:>6,}{RESET} unmapped        {DIM}({un_n/total:.0%}, {len(unmapped)} clusters){RESET}")

    if car:
        print(f"\n{BOLD}Car aspects — by volume{RESET}")
        print(f"  {DIM}{'aspect':<26}{'n':>6}  {'sentiment':^18}  polarity{RESET}")
        for r in sorted(car, key=lambda r: -r["size"]):
            s = r["sentiment"]
            print(f"  {r['aspect_label'][:25]:<26}{r['size']:>6}  {bar(s['polarity'])}  {s['polarity']:+.2f}")

        print(f"\n{BOLD}Strongest feeling{RESET} {DIM}(intensity × size — what people actually care about){RESET}")
        ranked = sorted(car, key=lambda r: -(r["sentiment"]["intensity"] * r["size"]))
        for r in ranked[:8]:
            s = r["sentiment"]
            tone = GREEN if s["polarity"] > 0 else RED
            print(f"  {tone}{s['label']:<9}{RESET} {r['aspect_label'][:24]:<26}"
                  f"{DIM}n={r['size']:<5} conf={r['confidence']:.2f}{RESET}")
            print(f"     {DIM}{r['quotes'][0]['text'][:84]}{RESET}")

    if unmapped:
        print(f"\n{BOLD}{CYAN}Unmapped{RESET} {DIM}— themes with no home in the taxonomy{RESET}")
        for r in sorted(unmapped, key=lambda r: -r["size"])[:6]:
            s = r["sentiment"]
            print(f"  {r['size']:>5} comments  {s['label']:<9} {DIM}best guess: "
                  f"{r['runners_up'][0][0] if r['runners_up'] else '—'} "
                  f"({r['confidence']:.2f}){RESET}")
            print(f"     {DIM}{r['quotes'][0]['text'][:84]}{RESET}")

    out = paths.analysis
    out.write_text(
        json.dumps(
            {
                "subject": args.subject,
                "vehicle_types": args.types,
                "totals": {
                    "clustered": total,
                    "car": car_n,
                    "meta": meta_n,
                    "unmapped": un_n,
                },
                "clusters": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{DIM}written: {out}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
