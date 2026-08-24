"""Build vertical shorts — one per angle, or all of them.

    python scripts/shorts.py --subject byd-racco --angle numbers
    python scripts/shorts.py --subject byd-racco --all
    python scripts/shorts.py --subject byd-racco --all --no-audio

Five angles from one corpus, each making a different claim. Scoping
happens at the data layer, so the "defect" short cannot drift into the
nationality argument — it never sees those clusters.

Replaces scripts/datashort.py, which built only the numbers angle.
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
from opitrics.render import remotion as rmt  # noqa: E402
from opitrics.render import sequence  # noqa: E402
from opitrics.render.angles import ANGLES, ShortAngle  # noqa: E402
from opitrics.render.audio import AudioError, ElevenLabs, audio_duration  # noqa: E402

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

This audience is not a reader on X. A reader on X clicked. This viewer
arrived by accident, is holding a thumb over the screen, and leaves in
two seconds. Nothing is owed to you.

So the first line is not a summary. It is the most contested thing in
the data, said plainly enough to stop a thumb.

  Weak:   "Nearly a quarter of the chatter isn't about the car."
  Strong: "They're not arguing about the car. They're arguing about China."

Rules:
- SPOKEN, not written. Short sentences, 8 to 16 words. Contractions.
  Read each line aloud; if you stumble, rewrite it.
- Never describe the screen. The viewer can see the chart or the quote.
  Say what it means, or why it is surprising.
- Numbers as a person says them: "sixteen thousand comments".
- Build tension across the middle. A short is an argument, not a list.
- End on something the viewer carries away. A question is fine.
- No "as you can see", no "this chart shows", no "let's take a look",
  no "stay tuned", no "the results might surprise you".
- Each line belongs to its own card. Do not quote a comment over a
  photograph or a chart — the viewer is reading one thing and hearing
  another, and it lands as a mistake. Quote only on cards whose `kind`
  is "quote", and say what the quote MEANS rather than reading it
  aloud, since the card already shows the words.

The hard limit: every line must survive a viewer opening the sources
page and checking it. Provocative framing of a true finding is the job.
A claim the data does not support is not — it earns a correction in
your own comments, which costs more than the view was worth.

Do not turn a sentiment score into a verdict. Do not present the
loudest cluster as the majority unless it is. Where a cluster is
flagged for sarcasm, do not state its polarity as fact. Commenters are
not buyers: never imply sales or ownership from comment sentiment.

Return JSON only."""


def write_narration(
    client: LLMClient,
    angle: ShortAngle,
    cards: list[dict],
    display: str,
    facts: dict,
) -> list[str]:
    """One spoken line per card, written against the actual sequence."""
    instruction = (
        f"Write narration for this {len(cards)}-card short about the "
        f"{display}.\n\n"
        f"ANGLE — {angle.title}:\n{angle.brief}\n\n"
        f"Target length: about {angle.target_seconds} seconds.\n\n"
        "These figures are the ground truth. Do not contradict them. This "
        "is a constraint on accuracy, NOT an instruction to hedge — write "
        "with the same force you would without it. A cautious, clipped "
        "script fails as badly as an inaccurate one:\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
        + "\n\n"
        '{"lines":[{"index":<int>,"narration":"..."}]}\n\n'
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


def load_photos(subject: str) -> list[tuple[Path, str]]:
    cache = settings.database_path.parent / "imagery" / subject
    manifest = cache / "credits.json"
    if not manifest.exists():
        return []
    records = json.loads(manifest.read_text(encoding="utf-8"))
    return [(cache / r["file"], r["credit"]) for r in records
            if (cache / r["file"]).exists()]


def build_angle(
    *,
    client: LLMClient | None,
    eleven: ElevenLabs | None,
    angle: ShortAngle,
    paths,
    analysis: dict,
    photos: list[tuple[Path, str]],
    display: str,
    subject: str,
    raw: int,
    videos: int,
    args,
) -> bool:
    out_dir = paths.content_dir / "shorts" / angle.key
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{BOLD}── {angle.title}{RESET} {DIM}[{angle.key}]{RESET}")

    # Rotate the photographs per angle so five shorts of one car do not
    # all open on the same frame.
    import random

    ordered = list(photos)
    random.Random(f"{subject}:{angle.key}").shuffle(ordered)

    built = sequence.build(
        angle, analysis, ordered, display, subject, raw, videos,
        args.sources_url,
    )
    if not built.cards:
        print(f"  {YELLOW}nothing to build from this angle — skipped{RESET}")
        return False
    print(f"  {DIM}{len(built.cards)} cards: "
          f"{', '.join(c['kind'] for c in built.cards)}{RESET}")

    totals = analysis["totals"]
    car_pct = round(100 * totals["car"] / max(totals["clustered"], 1))
    facts = {
        "comments_total": raw,
        "videos": videos,
        "share_about_the_car_pct": car_pct,
        "share_not_about_the_car_pct": 100 - car_pct,
        "note": (
            f"{car_pct}% of clustered comments ARE about the car, so a "
            f"majority is — saying otherwise is false. The interesting "
            f"figure is that {100 - car_pct}% is not."
        ),
    }

    lines = [""] * len(built.cards)
    if client:
        try:
            lines = write_narration(client, angle, built.described, display, facts)
            for i, line in enumerate(lines, 1):
                print(f"  {BOLD}{i}{RESET} {line}")
        except Exception as exc:  # noqa: BLE001 - render silent rather than fail
            print(f"  {YELLOW}narration failed: {exc}{RESET}")

    narration: list[Path | None] = [None] * len(built.cards)
    if eleven and any(lines):
        for i, line in enumerate(lines):
            if not line:
                continue
            vo = out_dir / f"vo-{i + 1:02d}.mp3"
            try:
                eleven.speak(line, vo)
                narration[i] = vo
            except AudioError as exc:
                print(f"  {YELLOW}line {i + 1}: {exc}{RESET}")

    holds = [
        max(audio_duration(vo) + 0.6, 3.0) if vo else 3.6
        for vo in narration
    ]
    # Charts need longer: the bars grow, the counts arrive, then the
    # viewer needs a moment to read them.
    for i, card in enumerate(built.described):
        if card["kind"] in {"bars", "composition"}:
            holds[i] = max(holds[i], 5.5)

    video = out_dir / "short.mp4"
    music = args.music if args.music and args.music.exists() else None
    try:
        spec = rmt.ShortSpec(
            shots=[
                rmt.Shot(card=c, hold=h, audio=vo)
                for c, h, vo in zip(built.cards, holds, narration)
            ],
            music=music,
            music_gain_db=args.music_gain,
            crossfade=args.crossfade,
        )
        _, total = rmt.render(spec, video)
        print(f"  {GREEN}{video.name}{RESET} {DIM}{total:.1f}s{RESET}")
    except rmt.RemotionError as exc:
        print(f"  {RED}{exc}{RESET}")
        return False

    script = [f"{display} — {angle.title}", "", f"~{total:.0f}s", ""]
    for i, (line, card, hold) in enumerate(zip(lines, built.described, holds), 1):
        script.append(f"[{i}] {hold:.1f}s  ({card['kind']})")
        script.append(f"  VO: {line}")
        script.append(f"  ON SCREEN: {card['shows']}")
        script.append("")
    if photos:
        script.append("Image credits:")
        seen: set[str] = set()
        for _, credit in ordered[:4]:
            if credit not in seen:
                seen.add(credit)
                script.append(f"  {credit}")
    (out_dir / "script.txt").write_text("\n".join(script), encoding="utf-8")
    (out_dir / "script.json").write_text(
        json.dumps(
            {
                "subject": subject, "angle": angle.key,
                "angle_title": angle.title, "duration": round(total, 2),
                "beats": [
                    {"index": i + 1, "kind": c["kind"], "narration": lines[i],
                     "hold": round(holds[i], 2), "shows": c["shows"]}
                    for i, c in enumerate(built.described)
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--name")
    ap.add_argument("--angle", default="numbers", choices=sorted(ANGLES))
    ap.add_argument("--all", action="store_true", help="build every angle")
    ap.add_argument("--music", type=Path)
    ap.add_argument("--music-gain", type=float, default=-22.0)
    ap.add_argument("--crossfade", type=float, default=0.18)
    ap.add_argument("--sources-url", default="")
    ap.add_argument("--no-audio", action="store_true")
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
    photos = load_photos(args.subject)

    print(f"\n{BOLD}{display}{RESET} {DIM}{raw:,} comments · "
          f"{len(photos)} image(s){RESET}")

    client = None
    try:
        client = LLMClient(settings.require_llm())
    except Exception as exc:  # noqa: BLE001 - silent shorts are still useful
        print(f"{YELLOW}no LLM: {exc}{RESET}")

    eleven = None
    if not args.no_audio:
        try:
            eleven = ElevenLabs(cache_dir=settings.database_path.parent / "audio")
            warning = eleven.warn_if_free()
            if warning:
                print(f"{YELLOW}{warning}{RESET}")
        except AudioError as exc:
            print(f"{DIM}no voiceover: {str(exc).splitlines()[0]}{RESET}")

    wanted = sorted(ANGLES) if args.all else [args.angle]
    made = 0
    for key in wanted:
        if build_angle(
            client=client, eleven=eleven, angle=ANGLES[key], paths=paths,
            analysis=analysis, photos=photos, display=display,
            subject=args.subject, raw=raw, videos=videos, args=args,
        ):
            made += 1

    print(f"\n{GREEN}{BOLD}{made}/{len(wanted)} short(s) built{RESET}  "
          f"{DIM}{paths.content_dir / 'shorts'}{RESET}\n")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
