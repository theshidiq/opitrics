"""Build a vertical short — cards, voiceover, and a narrated MP4.

    python scripts/short.py --subject byd-racco
    python scripts/short.py --subject byd-racco --music ~/Music/bed.mp3
    python scripts/short.py --subject byd-racco --no-audio

Cards are always written out alongside the video, so pacing can be
changed in an editor without re-running any of this.
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
from opitrics.render import vertical  # noqa: E402
from opitrics.render.audio import AudioError, ElevenLabs  # noqa: E402
from opitrics.render.short import write_short  # noqa: E402
from opitrics.render.story import verify_quotes  # noqa: E402
from opitrics.render.video import (  # noqa: E402
    VideoError,
    build_narrated_short,
    ffmpeg_available,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--name", help="display name, e.g. 'BYD Racco'")
    ap.add_argument("--beats", type=int, default=6)
    ap.add_argument("--scope", default="car", choices=["car", "meta", "all"],
                    help="which side of the corpus the short draws on")
    ap.add_argument("--music", type=Path, help="background track to mix under")
    ap.add_argument("--music-gain", type=float, default=-22.0)
    ap.add_argument("--no-audio", action="store_true",
                    help="cards and a silent cut only")
    ap.add_argument("--no-sfx", action="store_true")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    if not paths.analysis.exists():
        print(f"\n{paths.analysis} not found — run scripts/report.py first.\n")
        return 1

    analysis = json.loads(paths.analysis.read_text(encoding="utf-8"))
    display = args.name or paths.display_name
    db = Database(settings.database_path)
    meta = {
        "raw": len(db.comments_for_subject(args.subject)),
        "videos": len(db.videos_for_subject(args.subject)),
    }

    out_dir = paths.content_dir / "shorts" / args.scope
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── script ──────────────────────────────────────────────
    try:
        client = LLMClient(settings.require_llm())
    except Exception as exc:  # noqa: BLE001 - config errors explain themselves
        print(f"\n{exc}\n")
        return 1

    print(f"\n{BOLD}Writing script{RESET} {DIM}{display} · {args.beats} beats{RESET}")
    script = write_short(client, display, analysis, meta, args.beats, args.scope)
    if not script.beats:
        print(f"{RED}No beats returned.{RESET}\n")
        return 1

    # Quotes on cards must exist in the corpus, same rule as threads.
    class _Shim:
        posts = [
            type("P", (), {"index": b.index, "quote_original": b.quote_original})()
            for b in script.beats if b.quote_original
        ]
    problems = verify_quotes(_Shim(), analysis)
    if problems:
        print(f"  {RED}quote check failed{RESET}")
        for p in problems:
            print(f"    {RED}·{RESET} {p}")
    else:
        print(f"  {GREEN}✓{RESET} {DIM}quotes verified{RESET}")

    print(f"  {BOLD}{script.title}{RESET}")
    print(f"  {DIM}~{script.estimated_seconds:.0f}s spoken, "
          f"{script.spoken_words} words{RESET}\n")
    for b in script.beats:
        print(f"  {BOLD}{b.index}{RESET} {DIM}[{b.kind}]{RESET} {b.narration}")

    # ── cards ───────────────────────────────────────────────
    print(f"\n{BOLD}Rendering cards{RESET}")
    cards: list[Path] = []
    for b in script.beats:
        path = out_dir / f"{b.index:02d}.png"
        if b.kind == "hook":
            vertical.hook_card(
                figure=b.figure or f"{meta['raw']:,}",
                caption=b.caption or "comments read",
                subject=args.subject, out=path,
            )
        elif b.kind == "quote" and b.quote_original:
            vertical.quote_card(
                original=b.quote_original,
                english=b.quote_english,
                likes=b.quote_likes,
                subject=args.subject, out=path,
            )
        else:
            vertical.statement_card(
                text=b.text or b.caption or b.narration,
                subject=args.subject, out=path,
                eyebrow=display,
            )
        cards.append(path)
        print(f"  {DIM}{path.name} · {b.kind}{RESET}")

    # ── audio ───────────────────────────────────────────────
    narration: list[Path | None] = [None] * len(script.beats)
    effects: list[tuple[Path, int]] = []

    if not args.no_audio:
        try:
            eleven = ElevenLabs(cache_dir=settings.database_path.parent / "audio")
        except AudioError as exc:
            print(f"\n{YELLOW}{exc}{RESET}")
            print(f"{DIM}continuing without audio{RESET}")
            eleven = None

        if eleven:
            warning = eleven.warn_if_free()
            if warning:
                print(f"\n{YELLOW}{warning}{RESET}")

            print(f"\n{BOLD}Generating voiceover{RESET}")
            for i, b in enumerate(script.beats):
                vo = out_dir / f"vo-{b.index:02d}.mp3"
                try:
                    eleven.speak(b.narration, vo)
                    narration[i] = vo
                    print(f"  {DIM}{vo.name}{RESET}")
                except AudioError as exc:
                    print(f"  {YELLOW}beat {b.index}: {exc}{RESET}")

            if not args.no_sfx:
                wanted = [(i, b) for i, b in enumerate(script.beats) if b.sfx]
                # Two effects is the whole budget — one on the hook, one
                # on the payoff. More than that is exhausting at this pace.
                for i, b in wanted[:2]:
                    fx = out_dir / f"sfx-{b.index:02d}.mp3"
                    try:
                        eleven.sound_effect(b.sfx, fx, duration=1.5)
                        effects.append((fx, i))
                        print(f"  {DIM}{fx.name} · {b.sfx[:40]}{RESET}")
                    except AudioError as exc:
                        print(f"  {YELLOW}sfx {b.index}: {exc}{RESET}")

    # ── video ───────────────────────────────────────────────
    holds: list[float] = []
    video = out_dir / "short.mp4"
    if ffmpeg_available():
        print(f"\n{BOLD}Rendering video{RESET}")
        try:
            _, holds = build_narrated_short(
                cards, narration, video,
                music=args.music if args.music and args.music.exists() else None,
                effects=effects,
                music_gain=args.music_gain,
            )
            print(f"  {GREEN}{video.name}{RESET} "
                  f"{DIM}{sum(holds):.1f}s{RESET}")
            if args.music and not args.music.exists():
                print(f"  {YELLOW}music file not found: {args.music}{RESET}")
        except VideoError as exc:
            print(f"  {YELLOW}{exc}{RESET}")
    else:
        print(f"\n{YELLOW}ffmpeg not found — cards written, no video{RESET}")

    # ── script file ─────────────────────────────────────────
    lines = [f"{script.title}", "", f"~{sum(holds) or script.estimated_seconds:.0f}s", ""]
    for i, b in enumerate(script.beats):
        hold = f"{holds[i]:.1f}s" if i < len(holds) else "—"
        lines.append(f"[{b.index}] {hold}  ({b.kind})")
        lines.append(f"  VO: {b.narration}")
        if b.quote_original:
            lines.append(f"  ON SCREEN: {b.quote_original[:70]}")
        elif b.figure:
            lines.append(f"  ON SCREEN: {b.figure} — {b.caption}")
        elif b.text:
            lines.append(f"  ON SCREEN: {b.text}")
        lines.append("")
    if script.hashtags:
        lines.append("tags: " + " ".join(f"#{h}" for h in script.hashtags))

    (out_dir / "script.txt").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "script.json").write_text(
        json.dumps(
            {
                "subject": args.subject,
                "title": script.title,
                "scope": args.scope,
                "hashtags": script.hashtags,
                "quote_warnings": problems,
                "beats": [
                    {
                        "index": b.index, "kind": b.kind,
                        "narration": b.narration,
                        "hold": round(holds[i], 2) if i < len(holds) else None,
                        "figure": b.figure, "caption": b.caption, "text": b.text,
                        "quote_original": b.quote_original,
                        "quote_english": b.quote_english,
                        "quote_likes": b.quote_likes,
                        "sfx": b.sfx,
                    }
                    for i, b in enumerate(script.beats)
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{GREEN}{BOLD}Short ready{RESET}  {out_dir}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
