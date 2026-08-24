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

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

NARRATION_SYSTEM = """\
You write narration for a 60-second vertical video that presents data \
about how people talk about a car online.

You are given the exact sequence of cards, in order, and what each one \
shows. Write one spoken line per card.

Rules:
- Written to be SPOKEN. Short sentences, 10 to 18 words. Read it aloud \
in your head.
- Never describe what is on screen. The viewer can see the chart. Say \
what it MEANS, or what is surprising about it.
- Numbers spoken as a person would say them.
- The first line has two seconds to stop a scroll. Lead with the finding.
- The last line must land something, not summarise.
- No "as you can see", no "this chart shows", no "let's take a look".

Return JSON only."""


def write_narration(client: LLMClient, cards: list[dict], display: str) -> list[str]:
    """One spoken line per card, written against the actual sequence."""
    instruction = (
        f"Write narration for this {len(cards)}-card sequence about the "
        f"{display}.\n\n"
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
    ap.add_argument("--crossfade", type=float, default=0.16)
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
    print(f"\n{BOLD}Building cards{RESET}")
    built: list = []
    described: list[dict] = []
    car_pct = round(100 * totals["car"] / max(totals["clustered"], 1))

    def add(card, kind: str, shows: str) -> None:
        built.append(card)
        described.append({"index": len(described) + 1, "kind": kind, "shows": shows})
        print(f"  {DIM}{len(built):02d} · {kind}{RESET}")

    # Open on the car if there is a photograph; the number lands harder
    # over something concrete than over an empty frame.
    if photos:
        photo, credit = photos[0]
        add(
            vcharts.photo_layers(photo, f"{raw:,} comments", credit,
                                 args.subject, out_dir / "l01"),
            "photo",
            f"the car, with the headline figure {raw:,} comments",
        )
    else:
        add(
            layers.hook_layers(f"{raw:,}", "comments read", args.subject,
                               out_dir / "l01", f"across {videos} videos"),
            "hook",
            f"{raw:,} comments across {videos} videos",
        )

    add(
        vcharts.composition_layers(totals, args.subject, out_dir / "l02"),
        "composition",
        f"only {car_pct}% of comments are about the car itself; "
        f"the rest argue about the brand, the reviewer, or each other",
    )

    add(
        vcharts.sentiment_bars_layers(clusters, args.subject, out_dir / "l03",
                                      title="what they argue about"),
        "bars",
        "the six biggest themes, ranked by how many comments, "
        "coloured by sentiment — most are negative",
    )

    # The strongest single finding, as a figure.
    car_clusters = [c for c in clusters
                    if c.get("aspect") and not c.get("is_meta")]
    if car_clusters:
        worst = min(car_clusters, key=lambda c: c["sentiment"]["polarity"])
        add(
            layers.hook_layers(
                f"{worst['size']:,}", _short(worst.get("llm_label", "")),
                args.subject, out_dir / "l04",
                f"sentiment {worst['sentiment']['polarity']:+.2f}",
            ),
            "figure",
            f"the most negative theme: {worst.get('llm_label')} — "
            f"{worst['size']:,} comments at {worst['sentiment']['polarity']:+.2f}",
        )

    if len(photos) > 1:
        photo, credit = photos[1]
        add(
            vcharts.photo_layers(photo, "so is it any good?", credit,
                                 args.subject, out_dir / "l05"),
            "photo",
            "the car again, posing the question of whether the criticism is fair",
        )

    best = max(car_clusters, key=lambda c: c["sentiment"]["polarity"]) if car_clusters else None
    if best and best["sentiment"]["polarity"] > 0:
        add(
            layers.statement_layers(
                _short(best.get("llm_label", ""), 40),
                args.subject, out_dir / "l06", eyebrow=display,
            ),
            "statement",
            f"the one clearly positive theme: {best.get('llm_label')} "
            f"at {best['sentiment']['polarity']:+.2f}",
        )

    add(
        layers.statement_layers(
            "every quote links to the original comment",
            args.subject, out_dir / "l07", eyebrow="check the work",
        ),
        "closer",
        "the sources are published; the viewer can check every number",
    )

    # ── narration ───────────────────────────────────────────
    narration: list[Path | None] = [None] * len(built)
    lines: list[str] = [""] * len(built)

    try:
        client = LLMClient(settings.require_llm())
        print(f"\n{BOLD}Writing narration{RESET}")
        lines = write_narration(client, described, display)
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
    # Charts need longer than a quote card: bars grow, then the numbers
    # arrive, then the viewer needs a moment to read them.
    for i, card in enumerate(described):
        if card["kind"] in {"bars", "composition"}:
            holds[i] = max(holds[i], 5.0)

    shots = [
        LayeredShot(card=c, hold=h, kind=d["kind"], audio=vo)
        for c, h, d, vo in zip(built, holds, described, narration)
    ]

    video = out_dir / "short.mp4"
    music = args.music if args.music and args.music.exists() else None
    print(f"\n{BOLD}Rendering{RESET}")
    try:
        _, total = build_layered_short(
            shots, video, music=music,
            music_gain_db=args.music_gain, crossfade=args.crossfade,
        )
        print(f"  {GREEN}{video.name}{RESET} {DIM}{total:.1f}s{RESET}")
    except MotionError as exc:
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
