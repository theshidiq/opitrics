"""Find which cars are having a moment right now.

    python scripts/discover.py
    python scripts/discover.py --regions JP US --top 12
    python scripts/discover.py --fetch 1        # analyse the hottest one

Trending sweeps cost 1 quota unit per region. Channel velocity costs
100 per channel, so it is opt-in via --channels.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.ingest.discover import (  # noqa: E402
    DEFAULT_REGIONS,
    Discovery,
    slugify,
)
from opitrics.ingest.youtube import DAILY_QUOTA, QuotaExceeded, YouTubeClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regions", nargs="*", default=DEFAULT_REGIONS)
    ap.add_argument("--channels", nargs="*", default=[],
                    help="channel IDs to check for fast risers (100 units each)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-channels", type=int, default=2,
                    help="how many channels must cover a model to count")
    ap.add_argument("--no-reviews", action="store_true",
                    help="skip the review search (saves 400 quota units)")
    ap.add_argument("--queries", nargs="*", default=None,
                    help="override the review search terms")
    ap.add_argument("--fetch", type=int, metavar="N",
                    help="after listing, fetch comments for result N")
    args = ap.parse_args()

    db = Database(settings.database_path)
    try:
        client = YouTubeClient(settings.require_youtube(), db)
    except Exception as exc:  # noqa: BLE001 - config errors explain themselves
        print(f"\n{exc}\n")
        return 1

    print(f"\n{DIM}quota remaining: {client.quota_remaining()}/{DAILY_QUOTA}{RESET}")
    print(f"{BOLD}Sweeping{RESET} {DIM}{' '.join(args.regions)}"
          f"{f' + {len(args.channels)} channels' if args.channels else ''}{RESET}\n")

    discovery = Discovery(client)
    try:
        models = discovery.sweep(
            regions=args.regions,
            channels=args.channels or None,
            min_channels=args.min_channels,
            reviews=not args.no_reviews,
            queries=args.queries,
        )
    except QuotaExceeded as exc:
        print(f"\n{YELLOW}{exc}{RESET}\n")
        return 1

    if not models:
        print(f"{YELLOW}Nothing converging right now.{RESET}")
        print(f"{DIM}Try --min-channels 1, more regions, or come back after a launch.{RESET}\n")
        return 0

    top = models[: args.top]
    print(f"{BOLD}What's hot{RESET}\n")
    for i, model in enumerate(top, 1):
        heat = "█" * min(int(model.score), 14)
        print(f"  {BOLD}{i:>2}.{RESET} {CYAN}{model.name}{RESET}")
        print(f"      {GREEN}{heat}{RESET} {DIM}{model.score:.1f} · {model.why}{RESET}")
        for video in sorted(model.videos, key=lambda v: -(v.video.view_count or 0))[:2]:
            views = video.video.view_count or 0
            print(f"      {DIM}· {video.video.title[:62]}{RESET}")
            print(f"        {DIM}{video.video.channel_title[:34]} · {views:,} views{RESET}")
        print()

    out = settings.workspace.discovery
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            [
                {
                    "rank": i,
                    "name": m.name,
                    "subject": slugify(m.name),
                    "score": round(m.score, 2),
                    "channels": m.convergence,
                    "views": m.total_views,
                    "comments": m.total_comments,
                    "argument_rate": round(m.argument_rate, 2),
                    "videos": [
                        {
                            "video_id": v.video.video_id,
                            "title": v.video.title,
                            "channel": v.video.channel_title,
                            "views": v.video.view_count,
                            "comments": v.video.comment_count,
                            "region": v.region,
                        }
                        for v in m.videos
                    ],
                }
                for i, m in enumerate(top, 1)
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{DIM}written: {out}{RESET}")
    print(f"{DIM}quota used today: {db.quota_used_today()}/{DAILY_QUOTA}{RESET}\n")

    # ── optional: fetch one straight away ───────────────────
    if args.fetch:
        if not 1 <= args.fetch <= len(top):
            print(f"{YELLOW}--fetch must be between 1 and {len(top)}{RESET}\n")
            return 1

        model = top[args.fetch - 1]
        subject = slugify(model.name)
        print(f"{BOLD}Fetching comments for {model.name}{RESET} "
              f"{DIM}(subject: {subject}){RESET}\n")

        for heat in model.videos:
            db.upsert_video(heat.video.as_dict(), subject=subject, region=heat.region)
            print(f"  {heat.video.title[:60]}")
            try:
                added = client.fetch_comments(heat.video.video_id)
            except QuotaExceeded as exc:
                print(f"\n  {YELLOW}{exc}{RESET}\n")
                break
            except Exception as exc:  # noqa: BLE001 - continue to the next video
                print(f"  {YELLOW}failed: {exc}{RESET}\n")
                continue
            print(f"  {GREEN}+{added:,}{RESET} "
                  f"{DIM}({db.comment_count(heat.video.video_id):,} cached){RESET}\n")

        print(f"{DIM}next: python scripts/cluster.py --subject {subject}{RESET}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
