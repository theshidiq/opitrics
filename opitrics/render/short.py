"""Write a short-form script from an analysis.

Thread copy and short-form copy are different crafts. A thread post is
read at the reader's pace and can carry a clause; a narration line is
heard once, at the narrator's pace, and has to land on first hearing.
Converting one into the other produces stilted video, so this is its
own pass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from opitrics.analyze.llm import LLMClient
from opitrics.render.story import _cluster_payload

log = logging.getLogger(__name__)

SHORT_SYSTEM = """\
You write 60-80 second vertical video scripts about cars, from YouTube \
comment analysis. The viewer is scrolling and will leave in two seconds \
if the first line does not land.

This is not the same audience as a reader on X. A reader on X already \
cared enough to click. This viewer arrived by accident and owes you \
nothing. The opening line is therefore not a summary — it is the most \
contested thing in the data, said plainly enough to stop a thumb.

  Weak:   "Nearly a quarter of the comments aren't about the car."
  Strong: "They're not arguing about the car. They're arguing about China."

Structure: a hook, then beats that build an argument, then a payoff. \
Each beat is one card on screen with one line of narration.

At this length the piece needs a shape, not just a list of findings. \
Set up a tension early — a claim, a contradiction, a number that does \
not fit — and let the middle beats complicate it before the payoff \
resolves or sharpens it. Alternate quote beats with statement beats so \
the rhythm changes; three quotes in a row is monotonous.

The hard limit: every line must survive a viewer opening the sources \
page and checking it. Provocative framing of a true finding is the \
job; a claim the data does not support is not, and earns a correction \
in your own comments. Do not turn a sentiment score into a verdict, do \
not present the loudest cluster as the majority unless it is, and \
never imply sales or ownership from comment sentiment.

Hard rules for the narration:
- Written to be SPOKEN. Short sentences. No subordinate clauses, no \
parentheses, no semicolons. Read each line aloud in your head; if you \
run out of breath it is too long.
- 12 to 20 words per line. The hook can be shorter.
- Numbers spoken as a person would say them: "sixteen thousand \
comments", not "15,950 comments". The card shows the exact figure.
- No "in this video", no "let's dive in", no "stay tuned". Start with \
the finding.
- The payoff must land something, not trail off. A question the viewer \
carries away is fine; a summary is not.

Each beat also carries what appears ON the card, which is different \
from what is said. The card is glanceable: a number, a short label, or \
a quote. Never put the narration line on the card as well — reading and \
listening to the same words at once is unpleasant.

Card types:
- "hook": a single large figure. `figure` is the number, `caption` is \
three or four words under it.
- "quote": a real comment. Use `quote_index` to pick from the supplied \
quotes. Include a natural English translation.
- "statement": a line of text on screen, at most twelve words.

Never invent a number or a quote. Use only what you are given.

Return JSON only."""


@dataclass
class Beat:
    index: int
    kind: str          # hook | quote | statement
    narration: str
    figure: str = ""
    caption: str = ""
    text: str = ""
    quote_original: str = ""
    quote_english: str = ""
    quote_likes: int = 0
    sfx: str = ""


@dataclass
class ShortScript:
    title: str
    beats: list[Beat]
    hashtags: list[str]

    @property
    def spoken_words(self) -> int:
        return sum(len(b.narration.split()) for b in self.beats)

    @property
    def estimated_seconds(self) -> float:
        # ~2.6 words a second is an unhurried documentary read, plus a
        # beat of air between cards.
        return self.spoken_words / 2.6 + len(self.beats) * 0.55


def write_short(
    client: LLMClient,
    display_name: str,
    analysis: dict,
    meta: dict,
    beats: int = 6,
    angle_scope: str = "car",
) -> ShortScript:
    totals = analysis["totals"]
    clusters = _cluster_payload(analysis["clusters"], limit=14, scope=angle_scope)

    # A flat list of quotes the model can point at by index, so it
    # cannot paraphrase one into existence.
    quotes: list[dict] = []
    for cluster in clusters:
        for quote in cluster.get("quotes", []):
            quotes.append(
                {
                    "index": len(quotes),
                    "text": quote["text"][:280],
                    "likes": quote["likes"],
                    "theme": cluster.get("label"),
                }
            )

    payload = {
        "car": display_name,
        "corpus": {
            "comments": meta["raw"],
            "videos": meta["videos"],
            "about_the_car_pct": round(
                100 * totals["car"] / max(totals["clustered"], 1)
            ),
        },
        "themes": [
            {
                "label": c["label"],
                "size": c["size"],
                "polarity": c["polarity"],
                "summary": c.get("summary", ""),
            }
            for c in clusters[:10]
        ],
        "quotes": quotes[:30],
    }

    instruction = (
        f"Write a {beats}-beat vertical short about the {display_name}.\n\n"
        "Return:\n"
        '{"title":"<for the upload>",'
        '"beats":[{"index":1,"kind":"hook|quote|statement",'
        '"narration":"<spoken>","figure":"","caption":"","text":"",'
        '"quote_index":<int or null>,"quote_english":"",'
        '"sfx":"<short description or empty>"}],'
        '"hashtags":["...","..."]}\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )

    log.info("writing short script for %s…", display_name)
    result = client._chat(SHORT_SYSTEM, instruction, max_tokens=4000)

    out: list[Beat] = []
    for item in result.get("beats", []):
        try:
            beat = Beat(
                index=int(item["index"]),
                kind=str(item.get("kind", "statement")),
                narration=str(item["narration"]).strip(),
                figure=str(item.get("figure", "")).strip(),
                caption=str(item.get("caption", "")).strip(),
                text=str(item.get("text", "")).strip(),
                quote_english=str(item.get("quote_english", "")).strip(),
                sfx=str(item.get("sfx", "")).strip(),
            )
        except (KeyError, ValueError, TypeError):
            continue

        qi = item.get("quote_index")
        if qi is not None:
            try:
                source = quotes[int(qi)]
                beat.quote_original = source["text"]
                beat.quote_likes = source["likes"]
            except (ValueError, TypeError, IndexError):
                # A quote that cannot be resolved becomes a statement
                # rather than a card with an invented comment on it.
                if beat.kind == "quote":
                    beat.kind = "statement"
                    beat.text = beat.text or beat.narration[:60]

        out.append(beat)

    out.sort(key=lambda b: b.index)
    return ShortScript(
        title=str(result.get("title", display_name)).strip(),
        beats=out,
        hashtags=[str(h).lstrip("#") for h in result.get("hashtags", [])],
    )
