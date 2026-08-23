"""Turn an analysis into publishable claims.

The report answers "what does the data say". This answers "what is worth
saying" — a different question with a different output shape. A briefing
hedges and enumerates; a thread makes a claim and backs it.

Written for a car audience: findings lead with the car, and the method
is evidence rather than the subject.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from opitrics.analyze.llm import LLMClient

log = logging.getLogger(__name__)

STORY_SYSTEM = """\
You turn comment analysis into content for an automotive audience on X \
(Twitter). Your reader is a car enthusiast, not a data analyst.

You receive named comment clusters with sizes, sentiment and real quotes \
(often Japanese). Produce a thread.

Hard rules:
- Lead with the single most surprising finding. Not a summary, not \
methodology, not "I analysed X comments" — the finding itself.
- Every post must carry a concrete number or a real quote. No filler \
posts, no "let's dive in", no "a thread 🧵" cliché.
- Never invent a number or a quote. Use only what you are given.
- Where sentiment is flagged sarcasm_risk, do not state its polarity as \
fact.
- Each post must stand alone if screenshotted.
- HARD LIMIT: 240 characters per post. Count them. This is the single \
most common failure — a post over the limit cannot be published at all.
- When a quote is long, do NOT paste both the original and a full \
translation into the post. The card carries both. Put the English \
meaning in the post and leave the original to the image.
- No hashtags. No emoji except where genuinely useful (rare).
- The FINAL post must point readers at the sources: state that every
quote links to the original comment on YouTube and that the full video
list is published. Say it plainly and without defensiveness — it is an
invitation to check, not a plea to be believed. Include the literal
token {SOURCES_URL} where the link belongs. Set that post's `kind` to
"sources".

For quotes, give the original text verbatim and a natural English \
translation — not a literal gloss.

Return JSON only."""


@dataclass(frozen=True)
class Angle:
    """One way of telling the story of a corpus.

    Threads built from the same analysis must differ in *what they claim*,
    not just in wording — an audience spots a rephrased repost instantly.
    Each angle therefore gets its own slice of the clusters and its own
    brief, so two threads about one car genuinely disagree about what the
    interesting part was.
    """

    key: str
    title: str
    brief: str
    # Which clusters this angle is allowed to see.
    scope: str  # car | meta | all | quotes
    posts: int = 8


ANGLES: dict[str, Angle] = {
    "car": Angle(
        key="car",
        title="The car itself",
        scope="car",
        posts=8,
        brief=(
            "Write only about the vehicle: engineering, build, price, "
            "practicality, how it compares to rivals. Ignore arguments about "
            "the brand's country of origin entirely — another thread covers "
            "that. Lead with the most specific technical complaint or praise, "
            "the kind a car enthusiast would argue about."
        ),
    ),
    "fight": Angle(
        key="fight",
        title="The argument in the comments",
        scope="meta",
        posts=7,
        brief=(
            "The story here is that a large share of the comment section is "
            "not about the car at all — it is people arguing with each other, "
            "accusing each other of being paid, or fighting about nationality. "
            "Lead with the proportion. Be even-handed: quote both sides. Do "
            "not editorialise about who is right."
        ),
    ),
    "defenders": Angle(
        key="defenders",
        title="Who defends it, and why",
        scope="all",
        posts=7,
        brief=(
            "Focus on the counter-intuitive supporters — people defending the "
            "car against the prevailing sentiment in their own market, and "
            "what arguments they use. Quote them at length. This is the angle "
            "nobody else covers, so make the surprise explicit."
        ),
    ),
    "quotes": Angle(
        key="quotes",
        title="Just the comments",
        scope="quotes",
        posts=10,
        brief=(
            "Minimal commentary. Each post is one real comment with its like "
            "count and a short line of context — no more than a sentence. "
            "Pick the ten most striking, and vary the tone between them: "
            "furious, funny, technical, resigned. Let the comments carry it."
        ),
    ),
    "method": Angle(
        key="method",
        title="How this was built",
        scope="all",
        posts=7,
        brief=(
            "Here the audience is technical, so the pipeline IS the subject. "
            "Explain how 16,000 comments become a finding: clustering, "
            "multilingual embeddings, why sarcasm breaks sentiment scoring. "
            "Be honest about what the method gets wrong. Use the car only as "
            "the worked example."
        ),
    ),
}


@dataclass
class ThreadPost:
    index: int
    text: str
    kind: str  # hook | finding | quote | method | closer | sources
    chart: str | None = None
    quote_original: str | None = None
    quote_english: str | None = None
    quote_likes: int | None = None


@dataclass
class Story:
    headline: str
    posts: list[ThreadPost]
    alt_hooks: list[str]
    angle: str = "car"

    @property
    def char_counts(self) -> list[int]:
        return [len(p.text) for p in self.posts]


def _in_scope(cluster: dict, scope: str) -> bool:
    """Whether an angle is allowed to see this cluster.

    Scoping at the data level rather than by instruction is what keeps
    two threads genuinely different: the "car" thread cannot mention the
    nationality argument because it never sees it.
    """
    is_meta = cluster.get("is_meta", False)
    unmapped = not cluster.get("aspect")

    if scope == "car":
        return not is_meta and not unmapped
    if scope == "meta":
        return is_meta or unmapped
    return True


def _cluster_payload(
    clusters: list[dict], limit: int = 22, scope: str = "all"
) -> list[dict]:
    """Compact clusters for the prompt.

    Quotes are the expensive part of the payload and the valuable part
    of the output, so they are trimmed rather than dropped.
    """
    pool = [c for c in clusters if _in_scope(c, scope)]

    # The quotes angle wants the most-liked comments regardless of which
    # cluster they came from, so rank by engagement rather than size.
    key = (lambda c: -c["total_likes"]) if scope == "quotes" else (lambda c: -c["size"])
    ranked = sorted(pool, key=key)[:limit]
    return [
        {
            "label": c.get("llm_label") or c.get("aspect_label"),
            "summary": c.get("llm_summary", ""),
            "aspect": c.get("aspect_label"),
            "size": c["size"],
            "likes": c["total_likes"],
            "polarity": c["sentiment"]["polarity"],
            "intensity": c["sentiment"]["intensity"],
            "is_meta": c.get("is_meta", False),
            "unmapped": not c.get("aspect"),
            "sarcasm_risk": c.get("sarcasm_risk", False),
            "quotes": [
                {"text": q["text"][:300], "likes": q["like_count"]}
                for q in c["quotes"][:3]
            ],
        }
        for c in ranked
    ]


def extract_story(
    client: LLMClient,
    subject: str,
    display_name: str,
    analysis: dict,
    meta: dict,
    posts: int | None = None,
    angle: Angle | None = None,
) -> Story:
    angle = angle or ANGLES["car"]
    posts = posts or angle.posts
    totals = analysis["totals"]

    scoped = _cluster_payload(analysis["clusters"], scope=angle.scope)
    if not scoped:
        return Story(headline="", posts=[], alt_hooks=[], angle=angle.key)

    payload = {
        "car": display_name,
        "corpus": {
            "comments_fetched": meta["raw"],
            "videos": meta["videos"],
            "clustered": totals["clustered"],
            "about_the_car": totals["car"],
            "about_video_or_arguing": totals["meta"],
            "unmapped": totals["unmapped"],
        },
        "clusters": scoped,
    }

    instruction = (
        f"Build a {posts}-post X thread about the {display_name}.\n\n"
        f"ANGLE — {angle.title}:\n{angle.brief}\n\n"
        "The headline must be specific to THIS angle. A generic summary of "
        "overall sentiment is wrong here — several other threads are built "
        "from the same data, and they must not converge on the same claim.\n\n"
        "Return:\n"
        '{"headline":"<the core claim, one line>",'
        '"posts":[{"index":1,"kind":"hook|finding|quote|method|closer",'
        '"text":"<=260 chars",'
        '"chart":"aspects|volume-intensity|composition|null",'
        '"quote_original":"<verbatim or null>",'
        '"quote_english":"<translation or null>",'
        '"quote_likes":<int or null>}],'
        '"alt_hooks":["<2 alternative opening posts>"]}\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )

    log.info("extracting story for %s (angle: %s)…", subject, angle.key)
    result = client._chat(STORY_SYSTEM, instruction, max_tokens=6000)

    out: list[ThreadPost] = []
    for item in result.get("posts", []):
        try:
            chart = item.get("chart")
            out.append(
                ThreadPost(
                    index=int(item["index"]),
                    text=str(item["text"]).strip(),
                    kind=str(item.get("kind", "finding")),
                    chart=chart if chart not in (None, "null", "") else None,
                    quote_original=item.get("quote_original") or None,
                    quote_english=item.get("quote_english") or None,
                    quote_likes=item.get("quote_likes"),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    out.sort(key=lambda p: p.index)
    story = Story(
        headline=str(result.get("headline", "")).strip(),
        posts=out,
        alt_hooks=[str(h) for h in result.get("alt_hooks", [])],
        angle=angle.key,
    )

    # Shortening can itself come back over the limit, so retry — but
    # bounded, and with a hard truncation as the last resort. A post
    # over the limit simply cannot be published, so ending up with one
    # is worse than ending up with a slightly clipped sentence.
    for attempt in range(3):
        over = [p for p in story.posts if len(p.text) > HARD_LIMIT]
        if not over:
            break
        log.info("%d post(s) over %d chars — rewrite %d",
                 len(over), HARD_LIMIT, attempt + 1)
        _shorten(client, story, over)
    else:
        for post in story.posts:
            if len(post.text) > HARD_LIMIT:
                log.warning("post %d truncated at %d chars", post.index, HARD_LIMIT)
                post.text = post.text[: HARD_LIMIT - 1].rstrip(" ,;:—-") + "…"

    return story


HARD_LIMIT = 280


def _shorten(client: LLMClient, story: Story, over: list[ThreadPost]) -> None:
    """Rewrite over-length posts in place.

    Cheaper and more reliable than truncating: a post cut mid-sentence
    reads as broken, and one over the limit cannot be published at all.
    """
    payload = [
        {"index": p.index, "chars": len(p.text), "text": p.text} for p in over
    ]
    instruction = (
        "These posts exceed the character limit. Rewrite each to fit "
        f"{HARD_LIMIT - 40} characters or fewer, keeping the number or "
        "quote that makes the point. Where a post contains both an "
        "original-language quote and its translation, keep only the "
        "translation — the attached image carries the original.\n\n"
        'Return {"posts":[{"index":<int>,"text":"..."}]}\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        result = client._chat(STORY_SYSTEM, instruction, max_tokens=2500)
    except Exception as exc:  # noqa: BLE001 - keep the long version rather than lose it
        log.warning("shortening failed: %s", exc)
        return

    by_index = {p.index: p for p in story.posts}
    for item in result.get("posts", []):
        try:
            post = by_index.get(int(item["index"]))
            text = str(item["text"]).strip()
        except (KeyError, ValueError, TypeError):
            continue
        if post and 0 < len(text) <= HARD_LIMIT:
            post.text = text


def verify_quotes(story: Story, analysis: dict) -> list[str]:
    """Check every quoted line actually appears in the corpus.

    An LLM paraphrasing a comment into something punchier is the single
    most damaging failure mode here — you would be putting words in a
    real person's mouth on a public timeline. Cheap to check, so check.
    """
    known: set[str] = set()
    for cluster in analysis["clusters"]:
        for quote in cluster["quotes"]:
            known.add(quote["text"].strip())

    problems: list[str] = []
    for post in story.posts:
        if not post.quote_original:
            continue
        needle = post.quote_original.strip()
        if any(needle in text or text.startswith(needle) for text in known):
            continue
        problems.append(f"post {post.index}: quote not found verbatim — {needle[:60]}")
    return problems
