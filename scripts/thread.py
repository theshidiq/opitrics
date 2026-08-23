"""Build an X thread from a finished analysis.

    python scripts/thread.py --subject byd-racco --name "BYD Racco"

    python scripts/thread.py --subject byd-racco --angle fight
    python scripts/thread.py --subject byd-racco --all

One corpus supports several genuinely different threads. Each angle sees
a different slice of the clusters, so the "car" thread cannot drift into
the nationality argument and vice versa.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.render import cards as cards_mod  # noqa: E402
from opitrics.render.story import ANGLES, extract_story, verify_quotes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

LIMIT = 280


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--name", help="display name, e.g. 'BYD Racco'")
    ap.add_argument("--angle", default="car", choices=sorted(ANGLES),
                    help="which story to tell from this corpus")
    ap.add_argument("--all", action="store_true",
                    help="build every angle in one run")
    ap.add_argument("--posts", type=int, default=None,
                    help="override the angle's default post count")
    ap.add_argument("--no-cards", action="store_true", help="copy only")
    ap.add_argument("--sources-url", default="",
                    help="public URL of the sources page, substituted into the closing post")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    src = paths.analysis
    if not src.exists():
        print(f"\n{src} not found — run scripts/report.py first.\n")
        return 1

    analysis = json.loads(src.read_text(encoding="utf-8"))
    display = args.name or args.subject.replace("-", " ").title()

    db = Database(settings.database_path)
    meta = {
        "raw": len(db.comments_for_subject(args.subject)),
        "videos": len(db.videos_for_subject(args.subject)),
    }

    try:
        client = LLMClient(settings.require_llm())
    except Exception as exc:  # noqa: BLE001 - config errors explain themselves
        print(f"\n{exc}\n")
        return 1

    wanted = sorted(ANGLES) if args.all else [args.angle]
    failures = 0
    for key in wanted:
        ok = build_angle(
            client=client,
            paths=paths,
            angle=ANGLES[key],
            subject=args.subject,
            display=display,
            analysis=analysis,
            meta=meta,
            posts=args.posts,
            cards=not args.no_cards,
            sources_url=args.sources_url,
        )
        failures += 0 if ok else 1

    if len(wanted) > 1:
        made = len(wanted) - failures
        print(f"{BOLD}{made}/{len(wanted)} threads built{RESET}  "
              f"{DIM}{paths.threads_dir}{RESET}\n")
    return 1 if failures == len(wanted) else 0


def build_angle(
    *,
    client,
    paths,
    angle,
    subject: str,
    display: str,
    analysis: dict,
    meta: dict,
    posts: int | None,
    cards: bool,
    sources_url: str = "",
) -> bool:
    tp = paths.thread(angle.key).ensure()

    print(f"\n{BOLD}── {angle.title}{RESET} {DIM}[{angle.key}]{RESET}")
    story = extract_story(
        client, subject, display, analysis, meta, posts, angle=angle
    )
    if not story.posts:
        print(f"  {YELLOW}nothing to say from this angle — skipped{RESET}")
        return False

    # The model is told to leave a token where the link goes, so the URL
    # can change without regenerating the thread. Substituting a long
    # URL can push a post over the limit after the length check has
    # already run, so anything that overflows is trimmed here.
    placeholder = sources_url or "[sources page — publish and paste URL]"
    for post in story.posts:
        if "{SOURCES_URL}" not in post.text:
            continue
        post.text = post.text.replace("{SOURCES_URL}", placeholder)
        if len(post.text) > LIMIT:
            excess = len(post.text) - LIMIT + 1
            head, _, tail = post.text.partition(placeholder)
            head = head[: max(0, len(head) - excess)].rstrip(" ,;:—-")
            post.text = f"{head} {placeholder}{tail}".strip()

    # ── verify before anything gets published ───────────────
    problems = verify_quotes(story, analysis)
    if problems:
        print(f"  {RED}quote check failed{RESET} "
              f"{DIM}— not found verbatim in the corpus:{RESET}")
        for p in problems:
            print(f"    {RED}·{RESET} {p}")
    else:
        print(f"  {GREEN}✓{RESET} {DIM}quotes verified{RESET}")

    out_dir = tp.root

    # ── copy ────────────────────────────────────────────────
    print(f"  {BOLD}{story.headline}{RESET}\n")
    lines: list[str] = []
    for post in story.posts:
        n = len(post.text)
        flag = f"{RED}{n}{RESET}" if n > LIMIT else f"{DIM}{n}{RESET}"
        print(f"{BOLD}{post.index}/{len(story.posts)}{RESET} "
              f"{DIM}[{post.kind}]{RESET} {flag}")
        print(f"  {post.text}")
        if post.quote_original:
            print(f"  {DIM}└ quote: {post.quote_original[:56]}"
                  f"{f' ({post.quote_likes:,}♥)' if post.quote_likes else ''}{RESET}")
        print()
        lines.append(f"{post.index}/{len(story.posts)}\n{post.text}\n")

    if story.alt_hooks:
        print(f"{DIM}alt hooks:{RESET}")
        for hook in story.alt_hooks:
            print(f"  {DIM}· {hook}{RESET}")
        print()

    tp.copy.write_text("\n".join(lines), encoding="utf-8")
    tp.json.write_text(
        json.dumps(
            {
                "subject": subject,
                "angle": angle.key,
                "angle_title": angle.title,
                "display_name": display,
                "headline": story.headline,
                "alt_hooks": story.alt_hooks,
                "quote_warnings": problems,
                "posts": [
                    {
                        "index": p.index,
                        "kind": p.kind,
                        "text": p.text,
                        "chars": len(p.text),
                        "chart": p.chart,
                        "quote_original": p.quote_original,
                        "quote_english": p.quote_english,
                        "quote_likes": p.quote_likes,
                    }
                    for p in story.posts
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ── cards ───────────────────────────────────────────────
    if not cards:
        print(f"  {DIM}written: {out_dir}{RESET}")
        return True

    print(f"  {DIM}rendering cards…{RESET}")
    # Only render a quote card when that specific quote passed the
    # verbatim check — a paraphrased quote on a card is a fabricated
    # statement attributed to a real person.
    unverified = {
        int(problem.split()[1].rstrip(":"))
        for problem in problems
        if problem.startswith("post ")
    }

    for post in story.posts:
        path = tp.card(post.index)

        if post.quote_original and post.index not in unverified:
            cards_mod.quote_card(
                original=post.quote_original,
                english=post.quote_english or "",
                likes=post.quote_likes or 0,
                subject=subject,
                context=display,
                out=path,
            )
            print(f"    {DIM}{path.name} · quote{RESET}")
            continue

        if post.chart:
            # Prefer the light chart — cards are on cream stock.
            for candidate in (
                paths.chart(post.chart, "light"),
                paths.chart(post.chart),
            ):
                if candidate.exists():
                    cards_mod.chart_card(candidate, post.kind, subject, path)
                    print(f"    {DIM}{path.name} · chart ({post.chart}){RESET}")
                    break
            else:
                print(f"    {YELLOW}{path.name} · chart {post.chart} missing{RESET}")
            continue

        figure, caption = _pick_stat(post, analysis, meta)
        cards_mod.stat_card(figure, caption, post.text[:150], subject, path)
        print(f"    {DIM}{path.name} · stat{RESET}")

    print(f"  {GREEN}ready{RESET} {DIM}{out_dir}{RESET}")
    return True


def _pick_stat(post, analysis: dict, meta: dict) -> tuple[str, str]:
    """Choose a headline figure for a post that has no chart or quote."""
    totals = analysis["totals"]
    clustered = max(totals["clustered"], 1)

    if post.kind == "hook":
        return f"{meta['raw']:,}", "comments read"
    if post.kind == "closer":
        return f"{meta['videos']}", "videos analysed"

    share = round(100 * totals["car"] / clustered)
    return f"{share}%", "actually about the car"


if __name__ == "__main__":
    raise SystemExit(main())
