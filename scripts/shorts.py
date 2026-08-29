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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.render import remotion as rmt  # noqa: E402
from opitrics.render import sequence  # noqa: E402
from opitrics.render.angles import ANGLES, ShortAngle  # noqa: E402
from opitrics.render.audio import (  # noqa: E402
    AudioError,
    ElevenLabs,
    audio_duration,
    deepen,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

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

THE CARD SHOWS THE NUMBER. YOU ARE THE VOICE OVER IT.

Every line is spoken over a card that already displays the figure, the
quote, or the chart. Saying the number out loud as well is the single
thing that makes these sound like a data readout instead of somebody
talking.

  Card shows:  15,950 · comments read
  Weak:        "Fifteen thousand nine hundred fifty comments on this car."
  Strong:      "I did not expect this to turn into a fight about China."

  Card shows:  a Japanese comment, 311 likes
  Weak:        "This one's got 311 likes. He's not even a buyer."
  Strong:      "This guy does not even want one. He just wants them to
                stop being smug about it."

SAY QUANTITIES THE WAY A PERSON SAYS THEM. "A fifth of them." "Hundreds
of people." "More than any other complaint." Nobody watching a vertical
video divides 3,205 by 15,950. Keep an exact figure only where the
number itself is the surprise: "1.2 tonnes, in a kei car" lands because
it is absurd. AT MOST ONE line in the whole script may contain a figure
over one hundred.

DO NOT OPEN ON THE CORPUS TOTAL. Three of five scripts opened on
"fifteen thousand nine hundred fifty comments", which tells a scrolling
viewer nothing and is the same opening they have already scrolled past.
Open on the most contested thing in the data, or on what surprised you.

Rules:
- SPOKEN, not written. Contractions. Read each line aloud; if you
  stumble, rewrite it.
- VARY THE SENTENCE LENGTH. This is what makes narration sound like a
  person telling you something rather than a person reading. A line of
  even, equal-length sentences is delivered flat no matter how it is
  voiced, because there is nothing in it to rise or fall against.
  Put a two-word sentence next to a fifteen-word one. Use a question
  where a question is real. Break a sentence off where a speaker would.

    Flat:   "Nearly a quarter of these comments are not about the car.
             They are about the brand and where it comes from."
    Spoken: "A quarter of them aren't about the car at all. Not one
             word. They're arguing about China."

  Aim for a mix across the script: some lines 4 to 8 words, some 15 to
  20. Never write every line the same length.
- Vary length ACROSS lines, not by chopping one line into fragments.
  Every full stop becomes an audible pause when this is voiced, so a
  line built from four two-word sentences is four dead stops in six
  seconds, and the viewer scrolls during them. Within a single line,
  prefer a comma or a dash to a full stop, and use at most one full
  stop mid-line. Keep the fragments for where they land hardest — the
  opening line and the closing one.
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

NEVER INVENT A QUOTE. Do not write words inside quotation marks and
attribute them to a commenter unless those exact words appear in the
card you were given. Not a paraphrase, not a tightened version, not
something truer to what they meant. A short that puts invented words
in a real person's mouth is the one failure that cannot be corrected
after publishing.

If a quote card is in the sequence, the viewer is already reading the
comment on screen. Your line says what it MEANS, or why it matters, or
who is saying it — never the words themselves:

  Forbidden: One guy says "the real range is half what they claim."
  Correct:   This one did the maths himself. Thirty-six people agreed.

Every figure you use must come from the card descriptions or the
ground-truth facts. Do not attach a number from one theme to a
different theme, and do not name a theme the data did not give you.

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
    rejected: list[tuple[int, str]] | None = None,
) -> list[str]:
    """One spoken line per card, written against the actual sequence."""
    correction = ""
    if rejected:
        listed = "\n".join(f'  line {i}: "{claim}"' for i, claim in rejected)
        correction = (
            "\n\nYour previous attempt was REJECTED. These quoted phrases "
            "appear nowhere in the corpus — you invented them:\n"
            + listed
            + "\n\nRewrite every line. Do not put words in quotation marks "
            "and attribute them to a commenter. Describe what the comment "
            "means and how many people agreed instead.\n"
        )
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
        + correction
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


# Double quotes and matched single quotes only. A bare apostrophe is
# not a delimiter: the first version of this treated ' as one, sliced
# every contraction in half ("He's got" → "s got"), failed to find the
# fragment in the corpus, and rejected two perfectly honest scripts.
QUOTED = re.compile(
    r'"([^"]{18,})"'
    r"|“([^”]{18,})”"
    r"|(?<![A-Za-z])'([^']{18,})'(?![A-Za-z])"
    r"|(?<![A-Za-z])‘([^’]{18,})’(?![A-Za-z])"
)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def check_quotes(lines: list[str], analysis: dict) -> list[tuple[int, str]]:
    """Find narration that quotes words no commenter actually wrote.

    The prompt forbids inventing quotes, and the prompt was not enough:
    asking for livelier writing produced fluent, plausible, entirely
    fabricated comments — "I drove 200 km and the battery dropped 60%"
    from a corpus containing no such sentence. A rule the model can
    silently break needs a check that does not depend on the model.

    Anything the narration presents in quotation marks is matched
    against the stored corpus. Matching is on a run of consecutive
    words rather than the whole string, since narration legitimately
    trims a long comment; but the words it does use have to be the
    commenter's own.
    """
    corpus = " ".join(
        _normalise(q.get("text", "") + " " + q.get("english", ""))
        for cluster in analysis["clusters"]
        for q in cluster.get("quotes", [])
    )
    bad: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        for groups in QUOTED.findall(line or ""):
            claim = next((g for g in groups if g), "")
            words = _normalise(claim).split()
            if len(words) < 4:
                continue
            span = min(6, len(words))
            if not any(
                " ".join(words[j:j + span]) in corpus
                for j in range(len(words) - span + 1)
            ):
                bad.append((i, claim.strip()))
    return bad


def _rank_wide(paths: list[Path]) -> list[Path]:
    """Order photographs by how likely each is to show the whole car.

    The first version of this took whichever image the rotation had
    left over, and on this corpus that was a close crop of a door
    handle — held behind every card for twenty-five seconds,
    unrecognisable as a vehicle. A backdrop only works if the shape
    reads at a glance.

    Landscape framing is the signal available without recognising
    anything: a photographer shooting a whole car steps back and the
    frame goes wide, while detail shots trend square. Ties break
    towards the larger file, which is the more detailed original.

    Returns the full ranking rather than a winner so callers can take
    different slots — picking the single best gave every angle the
    same backdrop.
    """
    scored: list[tuple[float, int, Path]] = []
    for path in paths:
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0:s=x", str(path)],
                capture_output=True, text=True, check=False, timeout=20,
            )
            w, h = (int(v) for v in proc.stdout.strip().split("x")[:2])
        except (ValueError, OSError, subprocess.SubprocessError):
            continue
        if h:
            scored.append((w / h, path.stat().st_size, path))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [p for _, _, p in scored] or list(paths)


def _fit(
    holds: list[float],
    lowest: float,
    highest: float,
    crossfade: float,
) -> list[float]:
    """Trim card holds so the short does not overrun its window.

    This used to stretch short videos up to a floor as well, which was
    a mistake: padding to reach a target length means adding silence,
    and silence on a vertical short is where the viewer leaves. A
    35-second video that holds attention beats a 40-second one that
    earned five of those seconds by waiting.

    So the floor is advisory — reported, never padded to. If the
    narration only fills 31 seconds, the short is 31 seconds.

    Trimming is bounded: a hold may never fall below its own
    voiceover, since a card that cuts before its line finishes is a
    worse fault than a long video. If the narration alone overruns the
    ceiling, the ceiling loses.
    """
    if not holds:
        return holds

    # What render() actually produces: each crossfade overlaps two cards.
    overlap = crossfade * max(len(holds) - 1, 0)
    total = sum(holds) - overlap

    if total > highest:
        # Matches the 0.25s tail added above: anything more would trim
        # into the line itself.
        floors = [max(h - 0.25, 2.0) for h in holds]
        room = sum(holds) - sum(floors)
        excess = total - highest
        if room <= 0:
            return holds
        take = min(excess, room)
        return [h - (h - f) * (take / room) for h, f in zip(holds, floors)]

    if total < lowest:
        log.info("short runs %.1fs, under the %.0fs target — "
                 "not padding, silence costs more than length gains",
                 total, lowest)
    return holds


TRANSLATE_SYSTEM = """\
You translate YouTube comments into natural English for a subtitle on
a short video.

Faithful, not literal. Keep the register: a blunt comment stays blunt,
a sarcastic one stays sarcastic, a joke stays a joke. Do not soften an
insult, do not add politeness the original does not have, and do not
explain what the person meant.

Keep it under 120 characters where the original allows, because it is
rendered under the original on a phone screen. If the comment is long,
translate the part that carries the point rather than summarising the
whole thing.

Return JSON: {"translations":[{"index":<int>,"english":"..."}]}"""


def check_narration(lines: list[str], raw: int) -> list[str]:
    """Numbers recited aloud, and openings that waste the first line.

    The threads needed a gate for this because the prompt alone did not
    hold, and the shorts have exactly the same failure with less room
    to absorb it: a viewer leaves in two seconds, so a first line spent
    on the corpus total is the whole video.
    """
    import re

    problems: list[str] = []
    numeric = [
        i + 1 for i, line in enumerate(lines)
        if any(int(t.replace(",", "")) > 100
               for t in re.findall(r"\b\d[\d,]*\b", line))
    ]
    if len(numeric) > 1:
        problems.append(
            f"lines {', '.join(map(str, numeric))} recite a figure. At most "
            "one should — the card already shows it"
        )

    # Spelled-out totals: "fifteen thousand nine hundred fifty" passes
    # every digit check and is the same recitation.
    if lines and re.search(
        r"\b(thousand|hundred)\b.*\bcomments?\b", lines[0], re.I
    ):
        problems.append(
            "line 1 opens on the comment total. Open on the finding"
        )
    return problems


def translate_cards(client: LLMClient, cards: list[dict]) -> int:
    """Fill in the English line under each non-English quote card.

    The card component has always rendered a translation and the
    pipeline has always passed the field, but `analysis.json` carries
    no translations at all: 0 of 200 quotes had one, so every Japanese
    comment in every short shipped untranslated. On an English-language
    channel that is most of the evidence being unreadable.

    Threads never hit this because the story LLM writes `quote_english`
    as it goes. Shorts read the corpus directly, so the translation has
    to happen here.
    """
    import re

    latin_only = re.compile(r"^[\x00-\x7F\s]*$")
    wanted = [
        (i, card) for i, card in enumerate(cards)
        if card.get("kind") == "quote"
        and card.get("original")
        and not card.get("english")
        and not latin_only.match(card["original"])
    ]
    if not wanted:
        return 0

    payload = [{"index": i, "text": card["original"]} for i, card in wanted]
    try:
        result = client._chat(
            TRANSLATE_SYSTEM,
            "Translate these comments.\n\n"
            + json.dumps(payload, ensure_ascii=False),
            max_tokens=1200,
        )
    except Exception as exc:  # noqa: BLE001 - a missing subtitle is not fatal
        print(f"  {YELLOW}translation failed: {exc}{RESET}")
        return 0

    by_index = {c[0]: c[1] for c in wanted}
    filled = 0
    for item in result.get("translations", []):
        try:
            card = by_index[int(item["index"])]
        except (KeyError, ValueError, TypeError):
            continue
        english = str(item.get("english", "")).strip()
        if english:
            card["english"] = english
            filled += 1
    if filled:
        print(f"  {DIM}{filled} quote(s) translated{RESET}")
    return filled


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

    if client:
        translate_cards(client, built.cards)
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
            invented = check_quotes(lines, analysis)
            if invented:
                # One retry with the failure quoted back. If the model
                # invents again the short does not get made: a fake
                # quote is worse than a missing video.
                print(f"  {YELLOW}invented quote(s) — rewriting:{RESET}")
                for i, claim in invented:
                    print(f"    {RED}line {i}: {claim[:70]}{RESET}")
                lines = write_narration(
                    client, angle, built.described, display, facts,
                    rejected=invented,
                )
                invented = check_quotes(lines, analysis)
                if invented:
                    print(f"  {RED}still inventing quotes — skipped{RESET}")
                    for i, claim in invented:
                        print(f"    line {i}: {claim[:70]}")
                    return False
            # Reported, not fatal. A recited number makes a duller video;
            # an invented quote makes a false one, and only the second
            # is worth refusing to render over.
            for problem in check_narration(lines, raw):
                print(f"  {YELLOW}· {problem}{RESET}")
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
                # Each line is generated on its own, so without the
                # neighbours the voice restarts its prosody at every
                # cut and the short sounds recited. These are context
                # only — not spoken, not billed.
                eleven.speak(
                    line, vo,
                    previous_text=lines[i - 1] if i else None,
                    next_text=lines[i + 1] if i + 1 < len(lines) else None,
                )
                # Applied to the copy, never the cache, so a rebuild
                # shelves raw audio once rather than compounding.
                deepen(vo, gain_db=args.bass, max_pause=args.max_pause)
                narration[i] = vo
            except AudioError as exc:
                print(f"  {YELLOW}line {i + 1}: {exc}{RESET}")

    # The tail here is small on purpose. A card that lingers after its
    # line has finished is dead air, and dead air is where a scrolling
    # viewer leaves. 0.25s reads as a beat; 0.6s read as a stall.
    holds = [
        # 0.55s after the line ends, not 0.25s. Measured at the old
        # value the shorts ran 169 to 192 words per minute against 140
        # to 160 for conversational speech, and the shortest card held
        # 2.2s, which is not long enough to read a Japanese comment and
        # its translation. A card the viewer cannot finish reading is
        # the same as no evidence at all.
        max(audio_duration(vo) + 0.55, 2.8) if vo else 3.0
        for vo in narration
    ]
    # Charts still need longer: the bars grow, the counts arrive, then
    # the viewer needs a moment to read them. But only enough to
    # animate — the narration usually covers it by itself.
    for i, card in enumerate(built.described):
        if card["kind"] in {"bars", "composition"}:
            holds[i] = max(holds[i], 4.2)
        # A quote card now carries the original AND its translation, so
        # it is two blocks of text to read while the narration talks
        # over it. The floor is higher than for a card showing one
        # number.
        if card["kind"] == "quote":
            holds[i] = max(holds[i], 4.6)

    holds = _fit(holds, args.min_seconds, args.max_seconds, args.crossfade)

    video = out_dir / "short.mp4"
    music = args.music if args.music and args.music.exists() else None
    try:
        # Prefer an image this short does not already use full-bleed:
        # holding the same photograph behind the card that shows it
        # makes the cut look like a rendering fault. The rotation is
        # already per-angle, so the choice differs between shorts.
        shown = {c.get("src") for c in built.cards if c.get("src")}
        unused = [p for p, _ in ordered if str(p) not in shown]
        # Widest-first, but then take this angle's slot in that order.
        # Picking the single widest gave all five shorts the same
        # backdrop, which undoes the per-angle rotation entirely — five
        # videos of one car should not open on one identical frame.
        ranked = _rank_wide(unused or [p for p, _ in ordered])
        # Rotate only over the wider half. The full ranking runs down
        # into detail crops, and a backdrop is cropped again by the
        # frame — rotating across all eight handed the last angle an
        # interior shot that read as an anonymous white panel. Better
        # to repeat a good wide shot than to use a bad close one.
        pool_size = max(1, (len(ranked) + 1) // 2)
        backdrop = (
            ranked[sorted(ANGLES).index(angle.key) % pool_size]
            if ranked else None
        )

        spec = rmt.ShortSpec(
            shots=[
                rmt.Shot(card=c, hold=h, audio=vo)
                for c, h, vo in zip(built.cards, holds, narration)
            ],
            music=music,
            music_gain_db=args.music_gain,
            crossfade=args.crossfade,
            backdrop=backdrop,
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
    ap.add_argument("--crossfade", type=float, default=0.12)
    ap.add_argument("--max-pause", type=float, default=0.30,
                    help="cap on silence inside a spoken line, seconds")
    ap.add_argument("--min-seconds", type=float, default=35.0,
                    help="stretch card holds to reach at least this")
    ap.add_argument("--max-seconds", type=float, default=40.0,
                    help="trim towards this, but never below the voiceover")
    ap.add_argument("--bass", type=float, default=4.0,
                    help="low-shelf gain in dB on the voice (0 disables)")
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
