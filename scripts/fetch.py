"""Fetch comments for a subject into the local cache.

    # by search
    python scripts/fetch.py --subject byd-racco --query "BYD Racco" --limit 6

    # by explicit video ids or urls (no search quota spent)
    python scripts/fetch.py --subject byd-racco --video abc123 --video xyz789

    # see what is already cached
    python scripts/fetch.py --subject byd-racco --status
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.ingest.youtube import (  # noqa: E402
    DAILY_QUOTA,
    QuotaExceeded,
    YouTubeClient,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("fetch")

DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"

VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


def extract_video_id(raw: str) -> str:
    """Accept a bare id or any common YouTube URL shape."""
    raw = raw.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    match = VIDEO_ID_RE.search(raw)
    if match:
        return match.group(1)
    raise ValueError(f"Could not parse a video id from {raw!r}")


def show_status(db: Database, subject: str) -> None:
    videos = db.videos_for_subject(subject)
    if not videos:
        print(f"\nNothing cached for subject {subject!r}.\n")
        return

    print(f"\n{BOLD}{subject}{RESET} — {len(videos)} video(s) cached\n")
    total = 0
    for v in videos:
        n = db.comment_count(v["video_id"])
        total += n
        state = db.fetch_state(v["video_id"])
        if state and state["error"]:
            mark = f"{YELLOW}!{RESET}"
        elif state and state["complete"]:
            mark = f"{GREEN}✓{RESET}"
        else:
            mark = f"{YELLOW}·{RESET}"
        region = v["region"] or "—"
        title = v["title"][:58]
        print(f"  {mark} {n:>6,}  {DIM}{region:<4}{RESET} {title}")
        print(f"       {DIM}{v['channel_title']}{RESET}")
    print(f"\n  {BOLD}{total:,}{RESET} comments cached")
    print(f"  {DIM}quota used today: {db.quota_used_today()}/{DAILY_QUOTA}{RESET}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True, help="analysis subject, e.g. byd-racco")
    ap.add_argument("--query", help="search term; costs 100 quota units")
    ap.add_argument("--video", action="append", default=[], help="video id or URL")
    ap.add_argument("--region", help="attribute these videos to a region code, e.g. JP")
    ap.add_argument("--limit", type=int, default=6, help="max videos from a search")
    ap.add_argument("--max-comments", type=int, help="stop after N comments per video")
    ap.add_argument("--status", action="store_true", help="show cache state and exit")
    args = ap.parse_args()

    db = Database(settings.database_path)

    if args.status:
        show_status(db, args.subject)
        return 0

    if not args.query and not args.video:
        ap.error("give --query or at least one --video (or --status)")

    try:
        api_key = settings.require_youtube()
    except Exception as exc:  # noqa: BLE001 - config errors are self-explaining
        print(f"\n{exc}\n")
        return 1

    client = YouTubeClient(api_key, db)
    print(f"\n{DIM}quota remaining today: {client.quota_remaining()}/{DAILY_QUOTA}{RESET}")

    video_ids: list[str] = []
    for raw in args.video:
        try:
            video_ids.append(extract_video_id(raw))
        except ValueError as exc:
            print(f"{YELLOW}skipping:{RESET} {exc}")

    if args.query:
        print(f"{DIM}searching {args.query!r}…{RESET}")
        try:
            found = client.search_videos(
                args.query, max_results=args.limit, region_code=args.region
            )
        except QuotaExceeded as exc:
            print(f"\n{YELLOW}{exc}{RESET}\n")
            return 1
        print(f"{DIM}found {len(found)} video(s){RESET}")
        video_ids.extend(found)

    # De-duplicate, keeping order.
    video_ids = list(dict.fromkeys(video_ids))[: args.limit]
    if not video_ids:
        print("\nNo videos to fetch.\n")
        return 1

    videos = client.get_videos(video_ids)
    print(f"\n{BOLD}Fetching comments for {len(videos)} video(s){RESET}\n")

    grand_total = 0
    for video in videos:
        db.upsert_video(video.as_dict(), subject=args.subject, region=args.region)
        title = video.title[:60]
        print(f"  {title}")
        print(f"  {DIM}{video.channel_title} · {video.comment_count or 0:,} comments reported{RESET}")

        try:
            added = client.fetch_comments(
                video.video_id, max_comments=args.max_comments
            )
        except QuotaExceeded as exc:
            print(f"\n  {YELLOW}{exc}{RESET}")
            print(f"  {DIM}progress saved — re-run to resume{RESET}\n")
            break
        except Exception as exc:  # noqa: BLE001 - report and continue to next video
            print(f"  {YELLOW}failed: {exc}{RESET}\n")
            continue

        cached = db.comment_count(video.video_id)
        grand_total += added
        note = f"{GREEN}+{added:,} new{RESET}" if added else f"{DIM}nothing new{RESET}"
        print(f"  {note} {DIM}({cached:,} cached total){RESET}\n")

    print(f"{BOLD}{grand_total:,}{RESET} new comments this run")
    print(f"{DIM}quota used today: {db.quota_used_today()}/{DAILY_QUOTA}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
