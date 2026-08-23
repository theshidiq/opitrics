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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
