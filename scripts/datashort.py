"""A short built around the charts rather than the comments.

    python scripts/datashort.py --subject byd-racco
    python scripts/datashort.py --subject byd-racco --no-photos

The quote-led short shows what people said. This one shows what the
numbers say — the split between comments about the car and comments
about everything else, the ranked themes, the sentiment. Same corpus,
different claim, so it stands as separate content rather than a
re-edit.

Photographs come from Wikimedia Commons under CC0 or CC BY, and the
credit is drawn onto the card. Manufacturer press images are avoided:
their terms are usually editorial-only, which excludes monetised video.
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
from opitrics.ingest.imagery import download, search_images  # noqa: E402
from opitrics.render import layers, vcharts  # noqa: E402
from opitrics.render.audio import AudioError, ElevenLabs  # noqa: E402
from opitrics.render.motion import (  # noqa: E402
    LayeredShot,
    MotionError,
    build_layered_short,
)
from opitrics.render import remotion as rmt  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

NARRATION_SYSTEM = """\
You write narration for vertical shorts about what people actually say
online about a car. TikTok, Reels, YouTube Shorts.

This audience is different from a reader on X. A reader on X already
cared enough to click. A short-form viewer arrived by accident, is
holding their thumb over the screen, and leaves in two seconds. Nothing
is owed to you.

So the first line is not a summary. It is the most contested thing in
the data, said plainly enough to stop a thumb.

  Weak:   "Nearly a quarter of the chatter isn't about the car."
  Strong: "They're not arguing about the car. They're arguing about China."

  Weak:   "Sentiment on build quality is negative."
  Strong: "Mechanics looked underneath. They didn't like what they saw."

Rules:
- SPOKEN, not written. Short sentences, 8 to 16 words. Contractions.
  Read each line aloud; if you stumble, rewrite it.
- Lead with the conflict the data actually shows. Every car has a
  different one — a defect, a price, a rivalry, a nationality fight.
  Find this car's and open on it.
- Never describe the screen. The viewer can see the chart. Say what it
  means or why it is surprising.
- Numbers as a person says them: "sixteen thousand comments".
- Build tension across the middle. A short is an argument, not a list.
- End on something the viewer carries away. A question is fine. A
  summary is not.
- No "as you can see", no "this chart shows", no "let's take a look",
  no "stay tuned", no "the results might surprise you".

The hard limit: every line must survive a viewer opening the sources
page and checking. Provocative framing of a true finding is the job.
A claim the data does not support is not — it earns a correction in
your own comments, which costs more than the view was worth.

Specifically:
- Do not call a sentiment score a verdict. "Most of the comments were
  negative" is true; "the internet hated it" is not.
- Do not present the loudest cluster as the majority unless it is.
- Where a cluster is flagged for sarcasm, do not state its polarity as
  fact.
- Commenters are not buyers. Never imply sales, demand or ownership
  from comment sentiment.

Return JSON only."""


def write_narration(
    client: LLMClient,
    cards: list[dict],
    display: str,
    facts: dict | None = None,
) -> list[str]:
    """One spoken line per card, written against the actual sequence.

    `facts` states the handful of figures a provocative opening is most
    likely to overstate. Asking for sharper framing produced "most of
    them aren't about the car" on a corpus that is 78% about the car —
    the instruction not to overclaim was not enough on its own, so the
    numbers travel with the request.
    """
    instruction = (
        f"Write narration for this {len(cards)}-card sequence about the "
        f"{display}.\n\n"
        "These figures are the ground truth. Do not contradict them. "
        "This is a constraint on accuracy, NOT an instruction to hedge — "
        "write with the same force you would without it, and keep every "
        "line to the 8-16 word range with real rhythm. A cautious, "
        "clipped script fails as badly as an inaccurate one:\n"
        + json.dumps(facts or {}, ensure_ascii=False, indent=2)
        + "\n\n"
        'Return {"lines":[{"index":<int>,"narration":"..."}]}\n\n'
        + json.dumps({"cards": cards}, ensure_ascii=False)
    )
    result = client._chat(NARRATION_SYSTEM, instruction, max_tokens=2500)

    lines = [""] * len(cards)
    for item in result.get("lines", []):
        try:
            i = int(item["index"]) - 1
            if 0 <= i < len(lines):
                lines[i] = str(item["narration"]).strip()
        except (KeyError, ValueError, TypeError):
            continue
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--name", help="display name, e.g. 'BYD Racco'")
    ap.add_argument("--no-photos", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--music", type=Path)
    ap.add_argument("--music-gain", type=float, default=-22.0)
    ap.add_argument("--crossfade", type=float, default=0.18)
    ap.add_argument("--legacy", action="store_true",
                    help="use the matplotlib/movis renderer instead of Remotion")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    if not paths.analysis.exists():
        print(f"\n{paths.analysis} not found — run scripts/report.py first.\n")
        return 1

    analysis = json.loads(paths.analysis.read_text(encoding="utf-8"))
    display = args.name or paths.display_name
    db = Database(settings.database_path)
    raw = len(db.comments_for_subject(args.subject))
    videos = len(db.videos_for_subject(args.subject))
    totals = analysis["totals"]
    clusters = analysis["clusters"]

    out_dir = paths.content_dir / "shorts" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── photographs ─────────────────────────────────────────
    photos: list = []
    if not args.no_photos:
        cache = settings.database_path.parent / "imagery" / args.subject
        manifest = cache / "credits.json"
        if manifest.exists():
            records = json.loads(manifest.read_text(encoding="utf-8"))
            photos = [(cache / r["file"], r["credit"]) for r in records
                      if (cache / r["file"]).exists()]
            # Deterministic shuffle keyed on the subject: the same car
            # always gets the same order, different cars get different
            # ones, and re-running does not reshuffle mid-series.
            import random as _random
            _random.Random(args.subject).shuffle(photos)
            print(f"\n{DIM}{len(photos)} cached image(s){RESET}")
        else:
            print(f"\n{BOLD}Fetching imagery{RESET} {DIM}Wikimedia Commons{RESET}")
            found = search_images(display, limit=4, min_width=1400)
            kept = download(found, cache)
            photos = [(k.local, k.credit) for k in kept]
            for k in kept:
                print(f"  {DIM}{k.local.name} · {k.credit[:52]}{RESET}")
            if not kept:
                print(f"  {YELLOW}no freely-licensed images found{RESET}")

    # ── build the sequence ──────────────────────────────────
    # Cards are described, not drawn. Remotion renders each frame in a
    # browser, so a bar's width comes from the frame number rather than
    # from one of a handful of pre-drawn images.
    print(f"\n{BOLD}Building sequence{RESET}")
    cards: list[dict] = []
    described: list[dict] = []
    car_pct = round(100 * totals["car"] / max(totals["clustered"], 1))
    eyebrow = display.lower()

    def add(card: dict, shows: str) -> None:
        cards.append(card)
        described.append({
            "index": len(described) + 1, "kind": card["kind"], "shows": shows,
        })
        print(f"  {DIM}{len(cards):02d} · {card['kind']}{RESET}")

    if photos:
        photo, credit = photos[0]
        add(
            {"kind": "photo", "src": str(photo),
             "caption": f"{raw:,} comments", "credit": credit},
            f"the car, with the headline figure {raw:,} comments",
        )
    else:
        add(
            {"kind": "hook", "figure": f"{raw:,}", "caption": "comments read",
             "detail": f"across {videos} videos", "eyebrow": eyebrow},
            f"{raw:,} comments across {videos} videos",
        )

    add(
        {"kind": "composition", "title": "what the comments are about",
         "eyebrow": eyebrow,
         "segments": [
             s for s in [
                 {"value": totals["car"], "label": "about the car",
                  "colour": "#065FD4"},
                 {"value": totals["meta"], "label": "about the video, or arguing",
                  "colour": "#B8860B"},
                 {"value": totals["unmapped"], "label": "unmapped",
                  "colour": "#8A8A8A"},
             ] if s["value"] > 0
         ]},
        f"only {car_pct}% of comments are about the car itself; "
        f"the rest argue about the brand, the reviewer, or each other",
    )

    car_clusters = [c for c in clusters
                    if c.get("aspect") and not c.get("is_meta")]
    rows = sorted(car_clusters, key=lambda c: -c["size"])[:6]
    if rows:
        add(
            {"kind": "bars", "title": "what they argue about",
             "eyebrow": eyebrow,
             "rows": [
                 {"label": _short(r.get("llm_label") or r["aspect_label"], 34),
                  "size": r["size"],
                  "polarity": r["sentiment"]["polarity"]}
                 for r in rows
             ]},
            "the six biggest themes, ranked by how many comments, "
            "coloured by sentiment — most are negative",
        )

    if car_clusters:
        worst = min(car_clusters, key=lambda c: c["sentiment"]["polarity"])
        add(
            {"kind": "hook", "figure": f"{worst['size']:,}",
             "caption": _short(worst.get("llm_label", ""), 30),
             "detail": f"sentiment {worst['sentiment']['polarity']:+.2f}",
             "eyebrow": eyebrow},
            f"the most negative theme: {worst.get('llm_label')} — "
            f"{worst['size']:,} comments at {worst['sentiment']['polarity']:+.2f}",
        )

    if len(photos) > 1:
        photo, credit = photos[1]
        add(
            {"kind": "photo", "src": str(photo),
             "caption": "so is it any good?", "credit": credit},
            "the car again, posing the question of whether the criticism is fair",
        )

    if len(photos) > 2:
        photo, credit = photos[2]
        add(
            {"kind": "photo", "src": str(photo),
             "caption": "the people who drove it disagreed",
             "credit": credit},
            "the car once more, turning from the criticism to the praise",
        )

    best = (max(car_clusters, key=lambda c: c["sentiment"]["polarity"])
            if car_clusters else None)
    if best and best["sentiment"]["polarity"] > 0:
        add(
            {"kind": "statement",
             "text": _short(best.get("llm_label", ""), 46),
             "eyebrow": eyebrow},
            f"the one clearly positive theme: {best.get('llm_label')} "
            f"at {best['sentiment']['polarity']:+.2f}",
        )

    add(
        {"kind": "statement",
         "text": "every quote links to the original comment",
         "eyebrow": "check the work"},
        "the sources are published; the viewer can check every number",
    )

    # ── narration ───────────────────────────────────────────
    narration: list[Path | None] = [None] * len(cards)
    lines: list[str] = [""] * len(cards)

    try:
        client = LLMClient(settings.require_llm())
        print(f"\n{BOLD}Writing narration{RESET}")
        facts = {
            "comments_total": raw,
            "share_about_the_car_pct": car_pct,
            "share_not_about_the_car_pct": 100 - car_pct,
            "note": (
                f"{car_pct}% of clustered comments ARE about the car. "
                "A majority is therefore about the car — saying otherwise "
                "is false. The interesting figure is that "
                f"{100 - car_pct}% is not."
            ),
        }
        lines = write_narration(client, described, display, facts)
        for i, line in enumerate(lines, 1):
            print(f"  {BOLD}{i}{RESET} {line}")
    except Exception as exc:  # noqa: BLE001 - the video still renders silent
        print(f"{YELLOW}narration failed: {exc}{RESET}")

    if not args.no_audio and any(lines):
        try:
            eleven = ElevenLabs(cache_dir=settings.database_path.parent / "audio")
            warning = eleven.warn_if_free()
            if warning:
                print(f"\n{YELLOW}{warning}{RESET}")
            print(f"\n{BOLD}Generating voiceover{RESET}")
            for i, line in enumerate(lines):
                if not line:
                    continue
                vo = out_dir / f"vo-{i + 1:02d}.mp3"
                try:
                    eleven.speak(line, vo)
                    narration[i] = vo
                except AudioError as exc:
                    print(f"  {YELLOW}line {i + 1}: {exc}{RESET}")
        except AudioError as exc:
            print(f"\n{YELLOW}{exc}{RESET}")
            print(f"{DIM}rendering silent{RESET}")

    # ── render ──────────────────────────────────────────────
    from opitrics.render.audio import audio_duration

    holds = [
        max(audio_duration(vo) + 0.6, 3.0) if vo else 4.0
        for vo in narration
    ]
    # Charts need longer than a statement: the bars grow, the counts
    # arrive, then the viewer needs a moment to read them.
    for i, card in enumerate(described):
        if card["kind"] in {"bars", "composition"}:
            holds[i] = max(holds[i], 5.5)

    video = out_dir / "short.mp4"
    music = args.music if args.music and args.music.exists() else None
    print(f"\n{BOLD}Rendering{RESET} {DIM}Remotion{RESET}")
    try:
        spec = rmt.ShortSpec(
            shots=[
                rmt.Shot(card=c, hold=h, audio=vo)
                for c, h, vo in zip(cards, holds, narration)
            ],
            music=music,
            music_gain_db=args.music_gain,
            crossfade=args.crossfade,
        )
        _, total = rmt.render(spec, video)
        print(f"  {GREEN}{video.name}{RESET} {DIM}{total:.1f}s{RESET}")
    except rmt.RemotionError as exc:
        print(f"  {RED}{exc}{RESET}\n")
        return 1

    script_lines = [f"{display} — data short", ""]
    for i, (line, card, hold) in enumerate(zip(lines, described, holds), 1):
        script_lines.append(f"[{i}] {hold:.1f}s  ({card['kind']})")
        script_lines.append(f"  VO: {line}")
        script_lines.append(f"  ON SCREEN: {card['shows']}")
        script_lines.append("")
    if photos:
        script_lines.append("Image credits:")
        for _, credit in photos[:2]:
            script_lines.append(f"  {credit}")
    (out_dir / "script.txt").write_text("\n".join(script_lines), encoding="utf-8")

    print(f"\n{GREEN}{BOLD}Data short ready{RESET}  {out_dir}\n")
    return 0


def _short(label: str, limit: int = 22) -> str:
    label = (label or "").strip()
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
