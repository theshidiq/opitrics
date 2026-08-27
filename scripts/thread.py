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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.render import cards as cards_mod  # noqa: E402
from opitrics.render.story import (  # noqa: E402
    ANGLES,
    check_dashes,
    check_number_density,
    check_quote_echo,
    check_repetition,
    check_rounding,
    check_sources_post,
    check_superlatives,
    check_theme_count,
    extract_story,
    strip_dashes,
    verify_quotes,
)

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
    # Charts are shared across a subject's threads, not per thread. Three
    # angles independently picking "aspects" put one identical chart in
    # front of the same follower three times, and each thread was
    # individually correct, so only a set that outlives the loop can see
    # it. Later angles fall back to stat cards, which differ per post.
    charts_taken: set[str] = set()
    quotes_taken: set[str] = set()
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
            charts_taken=charts_taken,
            quotes_taken=quotes_taken,
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
    charts_taken: set[str] | None = None,
    quotes_taken: set[str] | None = None,
) -> bool:
    tp = paths.thread(angle.key).ensure()

    print(f"\n{BOLD}── {angle.title}{RESET} {DIM}[{angle.key}]{RESET}")
    story = extract_story(
        client, subject, display, analysis, meta, posts,
        angle=angle, charts_taken=charts_taken, quotes_taken=quotes_taken,
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
        # The model sometimes writes a perfectly good sources post and
        # simply omits the token, leaving a closing post that promises a
        # published analysis and gives no way to reach it. Regenerating
        # for this is wasteful — where the URL goes is mechanical, so
        # append it rather than asking again.
        if post.kind == "sources" and "{SOURCES_URL}" not in post.text:
            post.text = post.text.rstrip() + " {SOURCES_URL}"
        if "{SOURCES_URL}" not in post.text:
            continue
        # Nothing may follow the URL on the same run of characters. The
        # model writes "published at {SOURCES_URL}: every theme, its
        # sentiment..." because the colon introduces the list, which is
        # correct prose and wrong on X: the punctuation reads as part of
        # the address, and some clients pull it into the link. A full
        # stop and a space put the list in its own sentence.
        post.text = re.sub(
            r"\{SOURCES_URL\}\s*([:;,])\s*", "{SOURCES_URL}. ", post.text
        )
        # And a colon introducing the link reads like a label. This is
        # the one sentence every follower sees in every thread, so it
        # gets a full stop.
        post.text = re.sub(r"\s*:\s*\{SOURCES_URL\}", ". {SOURCES_URL}",
                           post.text)
        post.text = post.text.replace("{SOURCES_URL}", placeholder)
        if len(post.text) > LIMIT:
            # Drop whole sentences, not characters. Trimming by length
            # cut a closing post to "...links to the original co
            # https://..." — a word sliced in half in the one post every
            # follower sees in every thread.
            head, _, tail = post.text.partition(placeholder)
            sentences = re.split(r"(?<=[.!?])\s+", head.strip())
            while len(sentences) > 1 and (
                len(" ".join(sentences)) + len(placeholder) + len(tail) + 1
                > LIMIT
            ):
                sentences.pop()
            head = " ".join(sentences).rstrip(" ,;:")
            post.text = f"{head} {placeholder}{tail}".strip()
            if len(post.text) > LIMIT:
                # A single sentence that still will not fit. Cut it at a
                # word boundary rather than mid-word.
                room = LIMIT - len(placeholder) - len(tail) - 2
                head = head[:max(0, room)].rsplit(" ", 1)[0].rstrip(" ,;:")
                post.text = f"{head} {placeholder}{tail}".strip()

    # Punctuation is mechanical, so fix it rather than regenerate for
    # it. The gate below still runs and reports anything left.
    removed = strip_dashes(story)
    if removed:
        print(f"  {DIM}em dashes rewritten in {removed} post(s){RESET}")

    # ── verify before anything gets published ───────────────
    problems = verify_quotes(story, analysis)
    problems += check_rounding(story, analysis, meta)
    problems += check_sources_post(story)
    problems += check_repetition(story)
    problems += check_quote_echo(story)
    problems += check_number_density(story)
    problems += check_dashes(story)
    problems += check_superlatives(story)
    problems += check_theme_count(story, analysis)
    if problems:
        print(f"  {RED}checks failed{RESET} "
              f"{DIM}(quote, count, or missing sources post):{RESET}")
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

        figure, caption = _pick_stat(post, analysis, meta, angle.key)
        # No detail line. It used to be `post.text[:150]`, which printed
        # the post's own words underneath its own figure — so a reader
        # got the same sentence twice, once as prose and once as an
        # image of that prose. No amount of rewriting the post could fix
        # that, because the card copied whatever the rewrite produced.
        cards_mod.stat_card(figure, caption, "", subject, path)
        print(f"    {DIM}{path.name} · stat{RESET}")

    print(f"  {GREEN}ready{RESET} {DIM}{out_dir}{RESET}")
    return True


def _pick_stat(post, analysis: dict, meta: dict, angle_key: str = "") -> tuple[str, str]:
    """Choose a headline figure for a post that has no chart or quote.

    Keyed by angle, not only by post kind. The first version returned
    the corpus total for every hook and the same 78% for every finding,
    so five threads built from one corpus opened on the same card — and
    an account whose claim is that these are five different findings
    cannot afford its five openings to be one picture.

    The shorts hit this first and solved it the same way (`_opening()`
    in `opitrics/render/sequence.py`).
    """
    totals = analysis["totals"]
    clustered = max(totals["clustered"], 1)
    clusters = analysis.get("clusters", [])
    share = round(100 * totals["car"] / clustered)

    if post.kind == "closer":
        return f"{meta['videos']}", "videos analysed"

    if post.kind == "hook":
        if angle_key == "fight":
            return f"{100 - share}%", "not about the car at all"
        if angle_key == "defenders" and clusters:
            best = max(clusters, key=lambda c: c["sentiment"]["polarity"])
            return f"{best['size']:,}", "came to defend it"
        if angle_key == "quotes":
            quoted = sum(len(c.get("quotes", [])) for c in clusters)
            if quoted:
                return f"{quoted:,}", "comments quoted verbatim"
        if angle_key == "method":
            return f"{len(clusters)}", "themes, named by hand"
        return f"{meta['raw']:,}", "comments read"

    # Findings: the same reasoning one level down. "78% about the car"
    # on every non-hook card is the same collision, just less visible.
    if angle_key == "fight":
        return f"{totals['meta']:,}", "arguing, not reviewing"
    if angle_key == "method" and clusters:
        return f"{len(clusters)}", "themes found"
    return f"{share}%", "actually about the car"


if __name__ == "__main__":
    raise SystemExit(main())
