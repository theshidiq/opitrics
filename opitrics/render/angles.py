"""What each short is about, and what it is made of.

The thread angles proved that scoping at the data layer is what keeps
five pieces from one corpus genuinely different — the "car" thread
cannot drift into the nationality argument because it never sees those
clusters. The same rule applies here.

But a video is not a thread. A thread angle only needed a slice of the
data and a brief; a short also needs a *shape* — which cards, in which
order. A quote-led short and a chart-led short are structurally
different films, not the same film with different words over it.

So each angle carries both: the slice it may see, and the sequence of
card kinds it is built from.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShortAngle:
    key: str
    title: str
    # Which clusters this angle may draw on: car | meta | all | quotes.
    scope: str
    # The claim, in the narration writer's terms.
    brief: str
    # Card kinds in order. The builder fills each from the data.
    #   photo | hook | composition | bars | quote | statement | sources
    shape: tuple[str, ...]
    # Roughly how long, for the narration writer.
    target_seconds: int = 45


ANGLES: dict[str, ShortAngle] = {
    "numbers": ShortAngle(
        key="numbers",
        title="What the data says",
        scope="car",
        shape=("photo", "composition", "bars", "hook", "photo",
               "statement", "sources"),
        brief=(
            "The analysis itself is the story. Open on the split between "
            "comments about the car and comments about everything else, "
            "then the ranked themes, then the single most negative one as "
            "a figure. Close by pointing at the sources. This is the angle "
            "where charts do the talking, so the narration should say what "
            "the numbers mean rather than reading them out."
        ),
    ),
    "fight": ShortAngle(
        key="fight",
        title="The argument in the comments",
        scope="meta",
        shape=("hook", "statement", "quote", "quote", "composition",
               "quote", "statement", "sources"),
        brief=(
            "A large share of this comment section is not about the car at "
            "all — people arguing with each other, accusing each other of "
            "being paid, fighting about nationality. Lead with the "
            "proportion. Quote both sides. Do not editorialise about who is "
            "right; the point is that the argument exists, not who wins it."
        ),
        target_seconds=50,
    ),
    "defect": ShortAngle(
        key="defect",
        title="The specific complaint",
        scope="car",
        shape=("photo", "hook", "quote", "bars", "quote",
               "statement", "sources"),
        brief=(
            "One concrete technical complaint, followed all the way down. "
            "Pick the most specific negative theme — a measurement, a "
            "component, a number people keep citing — and let the quotes "
            "show how seriously they take it. Avoid the brand-origin "
            "argument entirely; this angle is about the object."
        ),
    ),
    "defenders": ShortAngle(
        key="defenders",
        title="Who defends it, and why",
        scope="all",
        shape=("hook", "quote", "quote", "photo", "quote",
               "statement", "sources"),
        brief=(
            "The counter-intuitive supporters: people defending the car "
            "against the prevailing sentiment in their own market, and the "
            "arguments they use. Quote them at length. Make the surprise "
            "explicit — this is the angle nobody else covers."
        ),
        target_seconds=50,
    ),
    "quotes": ShortAngle(
        key="quotes",
        title="Just the comments",
        scope="quotes",
        shape=("hook", "quote", "quote", "quote", "quote", "quote",
               "quote", "sources"),
        brief=(
            "Minimal commentary. Each line of narration is at most one "
            "sentence of context around a real comment. Pick the most "
            "striking, and vary the tone between them — furious, funny, "
            "technical, resigned. Let the comments carry it."
        ),
        target_seconds=55,
    ),
}


def get(key: str) -> ShortAngle:
    if key not in ANGLES:
        raise KeyError(
            f"unknown angle {key!r} — choose from {', '.join(sorted(ANGLES))}"
        )
    return ANGLES[key]
