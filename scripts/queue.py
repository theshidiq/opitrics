"""Approve a short now, let it post later.

    python scripts/queue.py add --subject byd-racco --angle numbers \\
        --platform tiktok --at 2026-09-18T09:00

    python scripts/queue.py list
    python scripts/queue.py drop <id>
    python scripts/queue.py run            # post anything now due
    python scripts/queue.py run --dry-run

The approval and the posting are deliberately separate. `add` shows you
the video, its caption and its checks, and writes an entry only if you
say yes. `run` posts entries whose time has come and **never chooses
anything itself** — it cannot queue, re-queue, or substitute content.
If the queue is empty, `run` does nothing.

That split is the whole point. `CLAUDE.md` and `brand/PROFILE.md` both
require a human yes for each specific item; a scheduler that picked its
own content would be exactly the thing those rules exist to stop. This
one only carries out a decision already made, and the entry records who
approved what and when.

Intended use is a daily `run` from cron. A day with nothing approved is
a day nothing posts, which is the correct behaviour rather than a
failure — there is no "find something to fill the slot" path.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

PLATFORMS = ("tiktok", "instagram")


def queue_path() -> Path:
    return Path(settings.output_dir) / "queue.json"


@dataclass
class Entry:
    id: str
    subject: str
    angle: str
    platform: str
    at: str           # ISO 8601, local time
    caption: str
    video: str
    privacy: str
    approved_at: str
    posted_at: str | None = None
    result: str | None = None
    error: str | None = None

    @property
    def due(self) -> bool:
        return (
            self.posted_at is None
            and datetime.fromisoformat(self.at) <= datetime.now()
        )


def load() -> list[Entry]:
    path = queue_path()
    if not path.exists():
        return []
    return [Entry(**row) for row in json.loads(path.read_text())]


def save(entries: list[Entry]) -> None:
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def short_path(subject: str, angle: str) -> Path:
    return (
        Path(settings.output_dir) / "subjects" / subject
        / "content" / "shorts" / angle / "short.mp4"
    )


def cmd_add(args: argparse.Namespace) -> int:
    """Show the item, then write it only on an explicit yes."""
    video = short_path(args.subject, args.angle)
    if not video.exists():
        print(f"\n{RED}no rendered short at {video}{RESET}\n")
        return 1

    try:
        when = datetime.fromisoformat(args.at)
    except ValueError:
        print(f"\n{RED}--at must be ISO 8601, e.g. 2026-09-18T09:00{RESET}\n")
        return 1
    if when <= datetime.now():
        print(f"\n{RED}--at is in the past{RESET}\n")
        return 1

    size_mb = video.stat().st_size / 1_000_000
    print(f"\n{BOLD}Approve for posting{RESET}")
    print(f"  subject   {args.subject}")
    print(f"  angle     {args.angle}")
    print(f"  platform  {args.platform}")
    print(f"  when      {when:%Y-%m-%d %H:%M}")
    print(f"  video     {video.name}  {DIM}{size_mb:.1f} MB{RESET}")
    print(f"  privacy   {args.privacy}")
    print(f"\n  {BOLD}caption{RESET}\n  {args.caption}\n")
    print(f"{DIM}Nothing is queued until you type y. Once queued, "
          f"`run` will post it at that time without asking again.{RESET}")

    if input("Queue it? [y/N] ").strip().lower() != "y":
        print(f"\n{YELLOW}not queued{RESET}\n")
        return 0

    entries = load()
    entry = Entry(
        id=f"{args.subject}-{args.angle}-{args.platform}-{when:%Y%m%d%H%M}",
        subject=args.subject,
        angle=args.angle,
        platform=args.platform,
        at=when.isoformat(timespec="minutes"),
        caption=args.caption,
        video=str(video),
        privacy=args.privacy,
        approved_at=datetime.now().isoformat(timespec="seconds"),
    )
    if any(e.id == entry.id for e in entries):
        print(f"\n{YELLOW}already queued{RESET}\n")
        return 0
    entries.append(entry)
    save(entries)
    print(f"\n{GREEN}queued{RESET} {DIM}{entry.id}{RESET}\n")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    entries = load()
    if not entries:
        print(f"\n{DIM}queue is empty{RESET}\n")
        return 0
    print(f"\n{BOLD}Queue{RESET}")
    for e in sorted(entries, key=lambda x: x.at):
        if e.posted_at:
            state = f"{GREEN}posted{RESET}" if not e.error else f"{RED}failed{RESET}"
        elif e.due:
            state = f"{YELLOW}due{RESET}"
        else:
            state = f"{DIM}waiting{RESET}"
        print(f"  {state:<20} {e.at}  {e.platform:<10} "
              f"{e.subject}/{e.angle}")
        if e.error:
            print(f"    {RED}{e.error[:96]}{RESET}")
    print()
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    entries = load()
    kept = [e for e in entries if e.id != args.id]
    if len(kept) == len(entries):
        print(f"\n{YELLOW}no entry {args.id}{RESET}\n")
        return 1
    save(kept)
    print(f"\n{GREEN}dropped{RESET} {DIM}{args.id}{RESET}\n")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Post everything due. Never selects, never substitutes.

    An empty or not-yet-due queue is a no-op and exits 0 — this is meant
    to run from cron every day, and most days there will be nothing to
    do. Silence is the expected state, not an error.
    """
    entries = load()
    due = [e for e in entries if e.due]
    if not due:
        print(f"{DIM}nothing due{RESET}")
        return 0

    for entry in due:
        print(f"\n{BOLD}── {entry.platform}{RESET} {DIM}{entry.id}{RESET}")
        video = Path(entry.video)
        if not video.exists():
            entry.error = f"video missing: {video}"
            entry.posted_at = datetime.now().isoformat(timespec="seconds")
            print(f"  {RED}{entry.error}{RESET}")
            continue

        if args.dry_run:
            print(f"  {YELLOW}dry run{RESET} {DIM}would post {video.name}{RESET}")
            continue

        try:
            entry.result = _post(entry)
            entry.posted_at = datetime.now().isoformat(timespec="seconds")
            print(f"  {GREEN}posted{RESET} {DIM}{entry.result}{RESET}")
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            entry.error = str(exc)[:300]
            entry.posted_at = datetime.now().isoformat(timespec="seconds")
            print(f"  {RED}failed{RESET} {DIM}{entry.error}{RESET}")

    if not args.dry_run:
        save(entries)
    print()
    return 0


def _post(entry: Entry) -> str:
    """Hand the file to the platform module. One place, so a new
    platform is a branch here and nothing else."""
    if entry.platform == "tiktok":
        import os

        from opitrics.publish import tiktok

        token = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TIKTOK_ACCESS_TOKEN is not set")

        # Privacy is asked for explicitly rather than defaulted. The
        # module's docstring says unaudited clients are forced to
        # SELF_ONLY while the live API reports PUBLIC_TO_EVERYONE as
        # available; those disagree, so `post()` validates the request
        # against what creator_info actually returned and raises rather
        # than silently posting privately.
        meta = tiktok.PostMeta(
            video=Path(entry.video),
            title=entry.caption,
            privacy=entry.privacy,
        )
        return str(tiktok.post(meta, token))

    if entry.platform == "instagram":
        from opitrics.publish import meta

        # Meta fetches the file from a public URL rather than accepting
        # an upload, and nothing serves the shorts yet. Fail loudly
        # here rather than half-posting.
        raise RuntimeError(
            "instagram needs a public URL for the MP4; see STATUS.md"
        )

    raise RuntimeError(f"unknown platform {entry.platform}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="approve one item into the queue")
    a.add_argument("--subject", required=True)
    a.add_argument("--angle", required=True)
    a.add_argument("--platform", required=True, choices=PLATFORMS)
    a.add_argument("--at", required=True, help="ISO 8601, e.g. 2026-09-18T09:00")
    a.add_argument("--caption", required=True)
    a.add_argument("--privacy", default="private",
                   choices=("private", "public"),
                   help="defaults to private; pass --privacy public "
                        "deliberately, having watched it back")
    a.set_defaults(func=cmd_add)

    sub.add_parser("list", help="show the queue").set_defaults(func=cmd_list)

    d = sub.add_parser("drop", help="remove an entry")
    d.add_argument("id")
    d.set_defaults(func=cmd_drop)

    r = sub.add_parser("run", help="post anything now due")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_run)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
