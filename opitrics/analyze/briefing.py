"""What a comment section tells a product team, and what it cannot.

Commenters are not buyers. Nothing here says whether a car will sell,
how demand is moving, or what the market will do — those claims need a
survey of buyers, and this is a survey of nobody. `CLAUDE.md` forbids
implying them and `STATUS.md` records why: a client who acts on comment
sentiment as demand and is wrong is a refund plus a reputation.

What a comment section does tell you is **which attributes generate
friction in public discussion, at what volume and intensity**. When 340
people independently raise kerb weight, that is a real signal about
where the conversation catches — regardless of whether any of them buys
anything. It is actionable for a product or communications team, and it
is a finding rather than a forecast.

The distinction this module encodes:

    supported      "476 comments question charging practicality,
                    61% of them negative"
    NOT supported  "charging anxiety will cost sales"

So every figure here is a share or a count of comments, and the
language is about the discourse. The one judgement made is
ADDRESSABILITY — whether a theme describes something a team could
change — and that is derived from the aspect taxonomy rather than from
reading sentiment, because it is a property of the subject matter, not
of the mood.
"""

from __future__ import annotations

from dataclasses import dataclass

# Which aspect groups describe something a team could act on, and which
# describe a condition it can only respond to.
#
# `Brand & origin` is the important case. A car's country of manufacture
# is not a product decision, and no amount of engineering changes it —
# so themes about it are communications material at best, and treating
# them as a product backlog would be a category error. The BYD Racco is
# 35% brand-and-origin discourse; reading that as a defect list would
# produce exactly the wrong brief.
PRODUCT = {
    "Build & quality",
    "Design",
    "Driving",
    "Practicality",
    "Tech & features",
    "Utility",
    "EV",
}
COMMS = {
    "Brand & origin",
    "Commercial",
    "Ownership & cost",
    "Kei",
}


@dataclass(frozen=True)
class Theme:
    """One cluster, with the figures a briefing needs."""

    cluster_id: int
    label: str
    summary: str
    group: str
    aspect_label: str
    size: int
    likes: int
    channels: int
    negative: float
    positive: float
    sarcasm: bool

    @property
    def friction(self) -> float:
        """Comments that read negative. Volume times negative share.

        Not a severity score and not weighted by likes: both would be
        inventions on top of a measurement, and `CLAUDE.md` is explicit
        that every derived number is another number that can be wrong on
        screen. This one is just "how many comments in this theme read
        negative", which is checkable by opening the theme.
        """
        return self.size * self.negative

    @property
    def addressable(self) -> str:
        if self.group in PRODUCT:
            return "product"
        if self.group in COMMS:
            return "comms"
        return "other"

    @property
    def reach_per_comment(self) -> float:
        """Likes per comment — how far a theme travels, not how big it is.

        A small theme with heavy likes reached more people than its size
        suggests. Kept separate from volume rather than folded into one
        score, because they answer different questions.
        """
        return self.likes / max(self.size, 1)


def themes(analysis: dict) -> list[Theme]:
    """Every car theme, largest first. Meta clusters are excluded."""
    out = []
    for c in analysis.get("clusters", []):
        if c.get("is_meta"):
            continue
        s = c.get("sentiment", {})
        out.append(
            Theme(
                cluster_id=c.get("cluster_id", 0),
                label=c.get("llm_label") or c.get("aspect_label", "theme"),
                summary=c.get("llm_summary", ""),
                group=c.get("aspect_group", "Other"),
                aspect_label=c.get("aspect_label", ""),
                size=c.get("size", 0),
                likes=c.get("total_likes", 0),
                channels=c.get("channel_spread", 0),
                negative=s.get("negative", 0.0),
                positive=s.get("positive", 0.0),
                sarcasm=bool(c.get("sarcasm_risk")),
            )
        )
    return sorted(out, key=lambda t: -t.size)


def shape(ts: list[Theme]) -> list[tuple[str, int, float]]:
    """(group, comments, share) largest first — what the corpus is about.

    This is the figure `report.py` already prints as corpus shape, and
    it is the first thing a briefing should say: the four cars here
    differ enormously (35% brand for one, 40% design for another), so
    the same analysis produces a different brief for each.
    """
    total = sum(t.size for t in ts) or 1
    agg: dict[str, int] = {}
    for t in ts:
        agg[t.group] = agg.get(t.group, 0) + t.size
    return sorted(
        ((g, n, 100 * n / total) for g, n in agg.items()),
        key=lambda r: -r[1],
    )


def friction_points(ts: list[Theme], kind: str = "", limit: int = 6) -> list[Theme]:
    """Themes where the discussion runs most negative, biggest first.

    `kind` filters to "product" or "comms". Sarcasm-flagged themes are
    kept but carry their flag: the method note promises they are
    surfaced rather than quietly scored, and a briefing that dropped
    them would be hiding its own uncertainty.
    """
    pool = [t for t in ts if not kind or t.addressable == kind]
    return sorted(pool, key=lambda t: -t.friction)[:limit]


def strengths(ts: list[Theme], limit: int = 4) -> list[Theme]:
    """Themes reading positive, by volume of positive comments.

    A briefing that only lists complaints misrepresents a corpus where
    a third of the discussion is approving, and gives a team no idea
    what not to break.
    """
    pool = [t for t in ts if t.positive > t.negative and not t.sarcasm]
    return sorted(pool, key=lambda t: -(t.size * t.positive))[:limit]


def travels_furthest(ts: list[Theme], limit: int = 3) -> list[Theme]:
    """Themes with the highest likes per comment, among substantial ones.

    A 40-comment theme with 20 likes each is a different thing from a
    400-comment theme with two. The floor keeps a single viral comment
    from topping the list.
    """
    pool = [t for t in ts if t.size >= 50]
    return sorted(pool, key=lambda t: -t.reach_per_comment)[:limit]


def headline(ts: list[Theme], display_name: str) -> tuple[str, str]:
    """The one sentence a briefing opens with, and its qualifier.

    Derived rather than written, so it cannot drift from the figures
    beneath it — and phrased as a fact about the discussion, never as a
    market claim.
    """
    if not ts:
        return ("No themes found.", "")

    sh = shape(ts)
    top_group, top_n, top_pct = sh[0]
    total = sum(t.size for t in ts)
    prod = sum(t.size for t in ts if t.addressable == "product")

    lead = (
        f"{top_pct:.0f}% of {display_name} discussion is about "
        f"{top_group.lower()} — {top_n:,} of {total:,} comments."
    )
    qual = (
        f"{100 * prod / max(total, 1):.0f}% concerns attributes a product "
        f"team could change; the rest is brand, price and context."
    )
    return lead, qual
