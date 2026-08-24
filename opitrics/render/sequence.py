"""Turn an angle's shape into the cards it describes.

The angle says "photo, composition, bars, hook, photo, statement,
sources". This fills each slot from the analysis, keeping to the
angle's scope, and never reusing a quote or a photograph within one
short — repetition inside a thirty-second video is far more obvious
than it is in a thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from opitrics.render.angles import ShortAngle

log = logging.getLogger(__name__)


@dataclass
class Built:
    """Cards ready for Remotion, plus what each one shows."""

    cards: list[dict] = field(default_factory=list)
    described: list[dict] = field(default_factory=list)

    def add(self, card: dict, shows: str) -> None:
        self.cards.append(card)
        self.described.append(
            {"index": len(self.described) + 1, "kind": card["kind"], "shows": shows}
        )


def _in_scope(cluster: dict, scope: str) -> bool:
    is_meta = cluster.get("is_meta", False)
    unmapped = not cluster.get("aspect")
    if scope == "car":
        return not is_meta and not unmapped
    if scope == "meta":
        return is_meta or unmapped
    return True


def _specificity(cluster: dict) -> int:
    """How concrete a theme is.

    A complaint that cites a measurement is better video than a general
    sentiment, so the "defect" angle needs a way to prefer one. Counting
    digits in the quotes is crude and works: people arguing about ground
    clearance quote "130mm", people arguing about trust do not.
    """
    text = " ".join(q["text"] for q in cluster.get("quotes", [])[:5])
    return sum(ch.isdigit() for ch in text)


def build(
    angle: ShortAngle,
    analysis: dict,
    photos: list[tuple[Path, str]],
    display: str,
    subject: str,
    raw_comments: int,
    videos: int,
    sources_url: str = "",
) -> Built:
    totals = analysis["totals"]
    clusters = analysis["clusters"]
    eyebrow = display.lower()
    car_pct = round(100 * totals["car"] / max(totals["clustered"], 1))

    pool = [c for c in clusters if _in_scope(c, angle.scope)]
    if not pool:
        pool = clusters

    # Quote pool, most-liked first, drawn down as the short uses them.
    quotes: list[tuple[dict, dict]] = []
    for cluster in sorted(pool, key=lambda c: -c["total_likes"]):
        for quote in cluster.get("quotes", []):
            if quote.get("text"):
                quotes.append((quote, cluster))
    quotes.sort(key=lambda pair: -pair[0].get("like_count", 0))

    by_size = sorted(pool, key=lambda c: -c["size"])
    positive = sorted(pool, key=lambda c: -c["sentiment"]["polarity"])

    # "defect" wants the most concrete complaint, not merely the most
    # negative one — a theme where people cite measurements makes far
    # better video than a general expression of distrust.
    if angle.key == "defenders":
        # "Who defends it" must draw on the clusters that actually do.
        # Left to the general pool it picked the loudest quotes, which
        # on this corpus are the attackers — the short then argued the
        # opposite of its own premise.
        supportive = [c for c in pool if c["sentiment"]["polarity"] > 0.1]
        if supportive:
            keep = {id(c) for c in supportive}
            quotes = [(q, c) for q, c in quotes if id(c) in keep]
            pool = supportive
            by_size = sorted(pool, key=lambda c: -c["size"])
            positive = sorted(pool, key=lambda c: -c["sentiment"]["polarity"])

    if angle.key == "defect":
        negative = sorted(
            pool,
            key=lambda c: (-_specificity(c), c["sentiment"]["polarity"]),
        )
        # And its quotes should come from that theme, not the corpus at
        # large, or the short drifts off its own subject.
        if negative:
            focus = negative[0]
            focused = [(q, focus) for q in focus.get("quotes", []) if q.get("text")]
            others = [(q, c) for q, c in quotes if c is not focus]
            quotes = focused + others
    else:
        negative = sorted(pool, key=lambda c: c["sentiment"]["polarity"])

    out = Built()
    used_quotes: set[str] = set()
    photo_i = 0
    hook_used = False

    def next_quote() -> tuple[dict, dict] | None:
        for quote, cluster in quotes:
            key = quote["text"][:80]
            if key not in used_quotes:
                used_quotes.add(key)
                return quote, cluster
        return None

    for slot in angle.shape:
        if slot == "photo":
            if photo_i >= len(photos):
                continue
            path, credit = photos[photo_i]
            photo_i += 1
            caption = (
                f"{raw_comments:,} comments"
                if photo_i == 1
                else "so is it any good?"
            )
            out.add(
                {"kind": "photo", "src": str(path), "caption": caption,
                 "credit": credit},
                f"the car, captioned {caption!r}",
            )

        elif slot == "hook":
            if not hook_used:
                hook_used = True
                # Each angle opens on its own number. Three of five
                # shorts opening on the same corpus total reads as the
                # same video, whatever the narration says afterwards.
                figure, caption, detail, shows = _opening(
                    angle, pool, totals, raw_comments, videos, car_pct,
                )
                out.add(
                    {"kind": "hook", "figure": figure, "caption": caption,
                     "detail": detail, "eyebrow": eyebrow},
                    shows,
                )
            elif negative:
                worst = negative[0]
                out.add(
                    {"kind": "hook", "figure": f"{worst['size']:,}",
                     "caption": _trim(worst.get("llm_label", ""), 30),
                     "detail": f"sentiment {worst['sentiment']['polarity']:+.2f}",
                     "eyebrow": eyebrow},
                    f"the most negative theme, {worst.get('llm_label')}, "
                    f"at {worst['sentiment']['polarity']:+.2f}",
                )

        elif slot == "composition":
            # Dark enough to carry the white percentage printed inside
            # each segment. The first set was chosen to look right on a
            # white page and put white type on 3.25:1 gold, which is
            # illegible on a phone.
            segments = [
                s for s in (
                    {"value": totals["car"], "label": "about the car",
                     "colour": "#0546A8"},          # 8.6:1 against white text
                    {"value": totals["meta"],
                     "label": "about the video, or arguing",
                     "colour": "#8A6508"},          # 6.2:1
                    {"value": totals["unmapped"], "label": "unmapped",
                     "colour": "#5A5A5A"},          # 7.0:1
                ) if s["value"] > 0
            ]
            out.add(
                {"kind": "composition", "title": "what the comments are about",
                 "segments": segments, "eyebrow": eyebrow},
                f"{car_pct}% of comments are about the car; "
                f"{100 - car_pct}% are not",
            )

        elif slot == "bars":
            rows = by_size[:6]
            if not rows:
                continue
            out.add(
                {"kind": "bars", "title": "what they argue about",
                 "eyebrow": eyebrow,
                 "rows": [
                     {"label": _trim(r.get("llm_label") or r["aspect_label"], 34),
                      "size": r["size"],
                      "polarity": r["sentiment"]["polarity"]}
                     for r in rows
                 ]},
                "the biggest themes, ranked by comment count and "
                "coloured by sentiment",
            )

        elif slot == "quote":
            picked = next_quote()
            if not picked:
                continue
            quote, cluster = picked
            out.add(
                {"kind": "quote", "original": quote["text"],
                 "english": quote.get("english", ""),
                 "likes": quote.get("like_count", 0),
                 "avatarColour": _avatar(quote["text"])},
                f"a real comment with {quote.get('like_count', 0):,} likes, "
                f"from the {cluster.get('llm_label', 'unnamed')} theme",
            )

        elif slot == "statement":
            best = next((c for c in positive
                         if c["sentiment"]["polarity"] > 0.15), None)
            text = (
                _trim(best.get("llm_label", ""), 46) if best
                else "the argument is louder than the car"
            )
            out.add(
                {"kind": "statement", "text": text, "eyebrow": eyebrow},
                f"the clearest positive theme: {text}" if best
                else "a closing line about the argument",
            )

        elif slot == "sources":
            out.add(
                {"kind": "statement",
                 "text": "every quote links to the original comment",
                 "eyebrow": "check the work"},
                "the sources are published; the viewer can check every number"
                + (f" at {sources_url}" if sources_url else ""),
            )

    return out


def _opening(
    angle, pool: list[dict], totals: dict, raw: int, videos: int, car_pct: int,
) -> tuple[str, str, str, str]:
    """The figure each angle leads on."""
    if angle.key == "fight":
        share = 100 - car_pct
        return (
            f"{share}%", "not about the car",
            f"of {totals['clustered']:,} comments analysed",
            f"{share}% of comments are not about the car at all",
        )
    if angle.key == "defenders" and pool:
        biggest = max(pool, key=lambda c: c["size"])
        return (
            f"{biggest['size']:,}", "came to defend it",
            _trim(biggest.get("llm_label", ""), 40),
            f"the largest supportive theme, {biggest.get('llm_label')}, "
            f"at {biggest['size']:,} comments",
        )
    if angle.key == "defect" and pool:
        worst = min(pool, key=lambda c: c["sentiment"]["polarity"])
        return (
            f"{worst['size']:,}", _trim(worst.get("llm_label", ""), 28),
            f"sentiment {worst['sentiment']['polarity']:+.2f}",
            f"the complaint theme {worst.get('llm_label')} with "
            f"{worst['size']:,} comments",
        )
    return (
        f"{raw:,}", "comments read", f"across {videos} videos",
        f"{raw:,} comments across {videos} videos",
    )


def _trim(label: str, limit: int) -> str:
    label = (label or "").strip()
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def _avatar(seed: str) -> str:
    import hashlib

    palette = [
        "#C0392B", "#1B5E9E", "#1E7D45", "#8A6A0B",
        "#6C3483", "#0E6655", "#96430F", "#4A5A69",
    ]
    return palette[hashlib.sha256(seed.encode()).digest()[0] % len(palette)]
