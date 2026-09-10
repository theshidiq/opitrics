"""Name clusters with the LLM, render charts, and build the report.

    python scripts/report.py --subject byd-racco

This is the only stage that contacts an external service, and it sends
cluster summaries rather than raw comments.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.analyze.taxonomy import BY_KEY, aspects_for  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.render import charts as charts_mod  # noqa: E402
from opitrics.render.report import build_report  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--no-llm", action="store_true",
                    help="skip naming and narrative; use aspect labels only")
    ap.add_argument("--max-clusters", type=int, default=None,
                    help="only name the N largest clusters")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    src = paths.analysis
    if not src.exists():
        print(f"\n{src} not found — run scripts/analyze.py first.\n")
        return 1

    analysis = json.loads(src.read_text(encoding="utf-8"))
    clusters = analysis["clusters"]

    # ── name clusters ───────────────────────────────────────
    narrative: dict = {}
    if not args.no_llm:
        try:
            client = LLMClient(settings.require_llm())
        except Exception as exc:  # noqa: BLE001 - config errors explain themselves
            print(f"\n{exc}\n")
            return 1

        ordered = sorted(clusters, key=lambda c: -c["size"])
        to_name = ordered[: args.max_clusters] if args.max_clusters else ordered

        print(f"\n{BOLD}Naming {len(to_name)} clusters{RESET} "
              f"{DIM}via {settings.llm.provider}/{settings.llm.model}{RESET}")
        # Hand over the whole vocabulary for this vehicle, so an
        # adjudication is not limited to the embedding model's shortlist.
        vocabulary = [a.key for a in aspects_for(analysis.get("vehicle_types", []))]
        named = client.name_clusters(to_name, taxonomy=vocabulary)

        adjudicated = 0
        for c in clusters:
            hit = named.get(c["cluster_id"])
            if not hit:
                continue

            c["llm_label"] = hit.label
            c["llm_summary"] = hit.summary
            c["sarcasm_risk"] = hit.sarcasm_risk

            # The LLM reads the actual comments, so it overrules the
            # embedding mapper on whether a cluster is about the car.
            if not hit.is_about_car and not c.get("is_meta"):
                c["is_meta"] = True
                c["meta_source"] = "llm"

            # It also breaks ties the cosine scores could not — either
            # filling a gap, or overruling a mapping the embeddings made
            # by a margin too thin to mean anything.
            weak = c.get("margin", 1.0) < 0.02
            if hit.aspect and (not c.get("aspect") or weak):
                aspect = BY_KEY.get(hit.aspect)
                if aspect:
                    c["aspect"] = aspect.key
                    c["aspect_label"] = aspect.label
                    c["aspect_group"] = aspect.group
                    c["is_meta"] = aspect.is_meta or c.get("is_meta", False)
                    c["aspect_source"] = "llm"
                    adjudicated += 1

        print(f"  {GREEN}{len(named)}{RESET} named"
              + (f", {GREEN}{adjudicated}{RESET} ambiguous aspects resolved"
                 if adjudicated else ""))

        # ── re-score where sarcasm makes the statistics unreliable ──
        # Discard every earlier correction first, not only on clusters
        # flagged this run. Re-scoring an already-corrected number
        # compounds the adjustment, and a cluster that stops being
        # flagged should revert rather than keep a stale override.
        for c in clusters:
            if c.get("sentiment_statistical"):
                c["sentiment"] = c.pop("sentiment_statistical")

        flagged = [c for c in clusters if c.get("sarcasm_risk")]
        if flagged:
            print(f"{BOLD}Re-scoring {len(flagged)} sarcasm-flagged cluster(s){RESET}")
            rescored = client.rescore_sentiment(flagged)
            flipped = 0

            for c in flagged:
                hit = rescored.get(c["cluster_id"])
                if not hit:
                    continue

                stat = c["sentiment"]
                before = stat["polarity"]

                # A low-confidence re-score is blended with the original
                # rather than replacing it. The model itself says the
                # cluster is mixed in those cases, and letting it swing
                # the number freely produces the opposite error to the
                # one being fixed — measured, a doubtful cluster was
                # pushed from +0.25 to +0.60 on a low-confidence call.
                weight = 1.0 if hit.confidence == "high" else 0.5
                pos = hit.positive * weight + stat["positive"] * (1 - weight)
                neu = hit.neutral * weight + stat["neutral"] * (1 - weight)
                neg = hit.negative * weight + stat["negative"] * (1 - weight)

                # The original is kept rather than overwritten: a
                # published number that was corrected should be traceable
                # to what it was corrected from.
                c["sentiment_statistical"] = dict(stat)
                c["sentiment"] = {
                    "positive": round(pos, 3),
                    "neutral": round(neu, 3),
                    "negative": round(neg, 3),
                    "polarity": round(pos - neg, 3),
                    "intensity": round(pos + neg, 3),
                    "label": (
                        "positive" if pos - neg > 0.15
                        else "negative" if pos - neg < -0.15
                        else "mixed"
                    ),
                    "source": "llm" if weight == 1.0 else "blended",
                    "confidence": hit.confidence,
                    "reasoning": hit.reasoning,
                }
                after = c["sentiment"]["polarity"]
                if (before >= 0) != (after >= 0):
                    flipped += 1
                    print(f"  {YELLOW}↺{RESET} {c.get('llm_label', '')[:38]} "
                          f"{DIM}{before:+.2f} → {after:+.2f}{RESET}")
                    print(f"    {DIM}{hit.reasoning[:96]}{RESET}")

            print(f"  {GREEN}{len(rescored)}{RESET} re-scored"
                  + (f", {YELLOW}{flipped}{RESET} changed direction" if flipped else ""))

        # Recompute totals — the LLM may have reclassified clusters.
        analysis["totals"] = {
            "clustered": sum(c["size"] for c in clusters),
            "car": sum(c["size"] for c in clusters
                       if c.get("aspect") and not c.get("is_meta")),
            "meta": sum(c["size"] for c in clusters if c.get("is_meta")),
            "unmapped": sum(c["size"] for c in clusters
                            if not c.get("aspect") and not c.get("is_meta")),
        }

        summary = {
            "totals": analysis["totals"],
            "clusters": [
                {
                    "label": c.get("llm_label") or c.get("aspect_label"),
                    "summary": c.get("llm_summary"),
                    "aspect": c.get("aspect_label"),
                    "size": c["size"],
                    "likes": c["total_likes"],
                    "sentiment": c["sentiment"]["label"],
                    "polarity": c["sentiment"]["polarity"],
                    "intensity": c["sentiment"]["intensity"],
                    "is_meta": c.get("is_meta", False),
                    "sarcasm_risk": c.get("sarcasm_risk", False),
                    "top_quote": c["quotes"][0]["text"][:200] if c["quotes"] else "",
                }
                for c in sorted(clusters, key=lambda c: -c["size"])[:30]
            ],
        }
        print(f"{BOLD}Writing narrative{RESET}")
        try:
            narrative = client.write_narrative(args.subject, summary)
            # Persisted so charts can be re-rendered and the report
            # rebuilt without paying for the narrative again.
            paths.narrative.write_text(
                json.dumps(narrative, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001 - report still builds without it
            print(f"  {YELLOW}narrative failed: {exc}{RESET}")
    else:
        cached = paths.narrative
        if cached.exists():
            narrative = json.loads(cached.read_text(encoding="utf-8"))
            print(f"{DIM}reusing cached narrative{RESET}")

    # ── charts ──────────────────────────────────────────────
    print(f"\n{BOLD}Rendering charts{RESET}")
    charts = charts_mod.render_all(analysis, paths.charts_dir)
    for p in charts:
        print(f"  {DIM}{p.name}{RESET}")

    # ── report ──────────────────────────────────────────────
    db = Database(settings.database_path)
    videos = db.videos_for_subject(args.subject)
    raw = len(db.comments_for_subject(args.subject))
    scored = sum(len(c["quotes"]) for c in clusters)

    html = build_report(
        analysis,
        narrative,
        charts,
        args.subject,
        meta={
            "raw": raw,
            "videos": len(videos),
            "scored": sum(min(25, c["size"]) for c in clusters),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    )
    out = paths.report
    out.write_text(html, encoding="utf-8")

    # Persist enriched analysis so the report can be rebuilt without
    # spending another LLM call.
    src.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{GREEN}{BOLD}Report ready{RESET}  {out}")
    if narrative.get("headline"):
        print(f'{DIM}"{narrative["headline"]}"{RESET}')
    print()
    print_shape(analysis)
    return 0


# Which angles a corpus can actually support, keyed by the aspect group
# that dominates it. Not new analysis — `aspect_group` is already on
# every cluster and already drives the charts. This only puts the
# number where a decision gets made.
SHAPE_ADVICE = {
    "Brand & origin": (
        "the argument, not the car",
        "fight, defenders — an audience arrives for the car and finds "
        "geopolitics, so say so in the hook rather than burying it",
    ),
    "Meta": (
        "the comment section itself",
        "method, fight — the corpus is about the video and the people "
        "watching it more than the vehicle",
    ),
    "Build & quality": ("the product", "defect, numbers"),
    "Driving": ("the product", "defect, numbers"),
    "Practicality": ("the product", "defect, numbers"),
    "EV": ("the technology", "numbers, defect"),
    "Commercial": ("price and rivals", "numbers, car"),
}


def print_shape(analysis: dict) -> None:
    """Say what this corpus is about, before anyone picks an angle.

    Every failure in the first subject's shorts traces back to an angle
    asking for material the corpus did not have. `defect` narrated a
    cluster ranked 39th of 40 as dominant, because the angle wants a
    product complaint and BYD Racco is 33% brand-and-origin argument
    against 3% build quality. That was knowable here, before rendering.

    Deliberately not a new metric. A derived number that nobody fully
    trusts is a liability on an account whose product is that its
    figures survive checking — so this prints what is already computed
    rather than inventing a second vocabulary for it.
    """
    groups: dict[str, int] = {}
    for cluster in analysis["clusters"]:
        group = cluster.get("aspect_group") or "unmapped"
        groups[group] = groups.get(group, 0) + cluster["size"]
    total = sum(groups.values())
    if not total:
        return

    ranked = sorted(groups.items(), key=lambda kv: -kv[1])
    print(f"{BOLD}What this corpus is about{RESET}")
    for name, size in ranked[:5]:
        share = 100 * size / total
        bar = "█" * max(1, round(share / 3))
        print(f"  {name[:20]:<20} {share:>4.0f}%  {DIM}{bar}{RESET}")

    top, top_size = ranked[0]
    subject, angles = SHAPE_ADVICE.get(
        top, ("this corpus", "read the clusters before choosing")
    )
    print(f"\n  The story here is {BOLD}{subject}{RESET}. Lead with: {angles}.")

    # The warning that matters: an angle wanting product complaints has
    # nothing to work with when the product groups are thin, and will
    # reach for the largest cluster it can see instead.
    product = sum(
        size for name, size in groups.items()
        if name in ("Build & quality", "Driving", "Practicality")
    )
    product_share = 100 * product / total
    if product_share < 20:
        print(
            f"  {YELLOW}Only {product_share:.0f}% is about the product itself"
            f"{RESET} {DIM}— `defect` has little to work with here and will "
            f"reach for whatever it can see. Check its cluster before "
            f"shipping it.{RESET}"
        )
    print()


if __name__ == "__main__":
    raise SystemExit(main())
