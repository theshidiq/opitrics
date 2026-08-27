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
import re
from dataclasses import dataclass

from opitrics.analyze.llm import LLMClient

log = logging.getLogger(__name__)

STORY_SYSTEM = """\
You turn comment analysis into content for an automotive audience on X \
(Twitter). Your reader is a car enthusiast, not a data analyst.

You receive named comment clusters with sizes, sentiment and real quotes \
(often Japanese). Produce a thread.

WHAT THE THREAD IS FOR. It has to be read, argued with and replied to. \
Accuracy is the constraint, not the goal — a thread nobody finishes is \
worth nothing however defensible each line is. The best posts here give \
a reader something to react to: a number that sounds wrong until you \
see it, a fight they did not know was happening, a comment that says \
what people are thinking. Write for the reply, not the citation.

That does NOT mean inventing stakes. The material is genuinely \
argumentative — people fighting about nationality under a car review, \
sarcasm dense enough that sentiment scoring gives up, a car both mocked \
and defended by the same market. Those are real and they are \
interesting. Your job is to stop flattening them into "cluster N, \
polarity −0.5", not to add drama that is not in the data.

Hard rules:
- Lead with the single most surprising finding. Not a summary, not \
methodology, not "I analysed X comments" — the finding itself.
- Every post must carry a concrete number or a real quote. No filler \
posts, no "let's dive in", no "a thread 🧵" cliché.
- Never invent a number or a quote. Use only what you are given.
- Where sentiment is flagged sarcasm_risk, do not state its polarity as \
fact.
- Each post must stand alone if screenshotted.
- SAY A FIGURE ONCE. If post 2 says a cluster runs to 509 comments, no \
later post repeats 509. Referring back is fine — "that same cluster", \
"the one I couldn't score" — but restating the number is padding, and a \
reader who has just read it feels talked down to. A thread of seven \
posts should carry seven different facts, not four facts and three \
restatements.
- CHARTS: **at most ONE post may carry each chart** — never name the \
same chart twice in a thread. Six posts naming "aspects" renders the \
same picture six times, and a reader scrolling sees a broken feed \
rather than evidence.
  But do use one or two. This is a data account; a thread of nothing \
but quote cards throws away the thing that makes it different from \
somebody reading comments aloud. Aim for one or two charted posts in \
a thread of seven, on the posts whose claim IS that chart. A post that \
carries a quote never needs one — the quote is already the image.
- HARD LIMIT: 240 characters per post. Count them. This is the single \
most common failure — a post over the limit cannot be published at all.
- When a quote is long, do NOT paste both the original and a full \
translation into the post. The card carries both. Put the English \
meaning in the post and leave the original to the image.
- No hashtags. No emoji except where genuinely useful (rare).
- The FINAL post must point readers at the sources: state that every
quote links to the original comment on YouTube, and that the full
analysis is published. Say it plainly and without defensiveness — it is
an invitation to check, not a plea to be believed. Include the literal
token {SOURCES_URL} where the link belongs. Set that post's `kind` to
"sources" — that exact string, not "closer" or anything else. A thread
whose last post is not kind "sources" ships with no link to the
evidence, which defeats the one thing this account is for.
  Describe what is actually at that URL: the analysis, with every theme,
  its sentiment, and a sourced comment behind each one. Do NOT promise
  a "full video list" or a list of quotes. Those live one click further
  on, at `sources.html`, and a closing post that names a thing the
  landing page does not show fails the exact check it is inviting.
  Write this post with no dashes at all. It is the same sentence in
  every thread, so a dash here is a dash a follower sees five times.

Voice:

You are one person who did this work, not a publication and not a \
narrator. That person is not showing off, and is not explaining the \
material to someone slower than them.

THE CLAIM TEST. Every CLAIM about the data must carry a figure from \
the payload — a count, a rank, a percentage, a polarity. A claim with \
no figure behind it is your opinion wearing a finding's clothes.

  Fails:  "The origin issue is the single biggest barrier, louder than
           any spec complaint."
  Passes: "That cluster runs to 456 comments. The largest complaint
           about the car itself runs to 269."

  Fails:  "But it's drowned out by the nationalist chorus."
  Passes: nothing. Cut it. You have no measurement of relative volume
           between one comment and a theme, so you cannot say one
           drowns out the other in any words at all.

  Also fails: "The fear is real, even among patriots." "The car is a
  proxy for something bigger." "Sentiment scores lie without context."
  "a sign of deep distrust", "it's physics".

This governs CLAIMS, not every sentence. An earlier version demanded a \
figure in any sentence that interpreted anything, and the threads came \
back reading like a board pack: seven posts of "N comments, polarity \
-0.5" with nothing a person would actually read. That is a failure \
too. A thread nobody finishes proves nothing, however defensible each \
line is.

So: write like someone who found something and wants to tell you, not \
like someone presenting quarterly results. Short sentences. A question \
where a question is real. Let the surprising number land on its own \
line instead of burying it mid-clause. You may set a scene, name the \
tension, or hand the reader a reaction — provided you are not smuggling \
an unmeasured claim in while doing it.

  Fine:   "Nobody agrees on this car. Not even about what it is."
          (frames; the next post carries the figures)
  Fine:   "Then it gets stranger."
  Fine:   "I couldn't score this one at all. Here's why."
  Still fails: "The badge matters more than the spec."
          (a claim about relative weight, no measurement)

The distinction is whether a reader could open the sources page and \
disagree with you. Framing they cannot check because it asserts \
nothing is fine. A claim they cannot check is not.

NEVER ROUND A COUNT. A corpus of 15,950 is not "16,000" and not \
"nearly 16,000"; write whatever figure the payload gives you, exactly. \
The entire claim of this account is that its numbers survive being \
checked, and a rounded figure in an opening line is the first thing a \
hostile reader tests. Write every count exactly as given.

NEVER CHARACTERISE A COMMENTER. You know what someone wrote and how \
many people liked it. You do not know who they are. Not "from a \
fanboy", not "not even a buyer", not "a patriot", not "an owner" unless \
the comment itself says so. Describe the comment, never the person \
behind it.

NO SUPERLATIVES ACROSS THE CORPUS. You are given a slice of the \
clusters, not all of them, so you cannot know what the most-liked \
comment in the corpus is, or the highest anything. Two threads built \
from two slices once claimed different corpus maxima — 310 and 381 — \
which is the one kind of error this account cannot absorb, because both \
were published and both were checkable. Rank claims are allowed ONLY \
within a named set you were given: "the most-liked comment in this \
cluster", "the largest of the six themes below". Never "in the entire \
corpus", "in all N comments", "of any comment here".

THE NOT-BUT TAIL. Having been told interpretation needs a number, you \
will be tempted to keep the rhetorical clause and put the number \
elsewhere in the post. That is not compliance. The construction \
"X isn't A — it's B" is the tail wearing a different coat: it asserts \
what a thing is really about, which is a claim you cannot measure. \
Three posts in one thread used it. At most one post may, and only when \
both halves carry their own figure.

  Fails:  "The weight criticism cluster (340 comments) isn't about ride
           quality — it's about the 1.2t battery."
  Passes: "The weight criticism cluster runs to 340 comments. Ride
           quality is a separate cluster of 336."

SECOND TEST: could the reader have got there themselves? If the quote \
already shows it, saying it insults them. "A backhanded compliment" \
after a comment calling the car a knockoff is explaining a joke the \
reader already got. Interpretation earns its place only when it adds \
what the reader could NOT see — nearly always a number, a rank, or a \
comparison to another cluster.

NO AWARDS CEREMONY. Never introduce a comment with a phrase that \
evaluates it. Not "A voice of reason:", not "The funniest jab:", not \
"Skeptics smell astroturfing:", not "The mockery is sharp:", not \
"Price is the counterweight:". You are not curating a gallery. \
Introduce a comment with a fact about it — its like count, its cluster, \
its size — or with nothing at all. The quote can open the post.

FIRST PERSON, SPARINGLY. Two or three posts in a thread may use "I", \
and only to report a DECISION about the analysis: what you grouped, \
what you refused to score, which reading you did not trust. "I grouped \
these 509 into mockery and then couldn't score them." "I'm giving you \
the count, not a verdict." Never claim the machine's labour — not "I \
read every comment"; a machine embedded and clustered them. True \
verbs: sorted, pulled, grouped, counted, went through. Not "read". \
Every other post has no narrator at all: the number and the quote.

DASHES. You have been ending roughly one sentence per post with a dash \
and an explanatory clause. At most ONE post in the whole thread may use \
a dash in its own prose — count them before you return, and if two \
posts have one, rewrite the weaker. A dash inside a commenter's \
verbatim words does not count and must not be altered. This is not a punctuation preference: the clause \
after the dash is almost always the unnumbered interpretation the tests \
above already forbid, so when you reach for a dash, check the clause \
against the interpretation test and you will usually find you should \
cut it rather than repunctuate it. Do NOT substitute a colon, a \
semicolon or a new sentence to keep the same clause — that is not \
compliance. This limit does not apply to the dash separating an \
original-language quote from its English translation; that is a \
formatting convention and it stays.

For quotes, give the original text verbatim and a natural English \
translation — not a literal gloss.

The translation is published beside the original with a link to it, so \
a reader can check your work. Three failures show up repeatedly and all \
of them are avoidable:
- Dropping a closing question or hedge (かなあ, けど, でしょう) and \
turning a doubtful remark into a flat assertion.
- Omitting the specific comparison the commenter was making, which is \
usually the substance of what they said.
- Rendering sarcasm as sincerity when the irony sits in politeness or \
an emoji rather than in the words.

If the comment is too long to translate fully, translate one complete \
thought rather than compressing the whole thing into something the \
commenter did not quite say.

POST SHAPES. Ten posts of identical construction read as machine \
output however well each one is written, and the repeating shape here \
has been `[label]: [quote]. [likes]. [interpretation]`. Build each post \
from one of the shapes below. Use no shape more than twice in a thread, \
and never twice in a row.

  bare      the quote alone, with its like count. Nothing else.
  lead      the like count first, then the quote. Nothing else.
  pair      two quotes from opposing clusters, both with counts, and no
            comment from you on which is right.
  scale     a count or a rank, then the quote that sits inside it.
  refusal   something you could not measure, and why — a sarcasm-flagged
            cluster, thin data, a polarity you do not trust.
  frame     one sentence of context that is a FACT about the corpus,
            then the quote.

Two of these shapes contain no sentence of yours at all. Use them. And \
use `refusal` at least once where the data supports it: a thread that \
admits one thing it could not measure is doing what no generated thread \
does.

You may be told which quotes other threads about this car already used. \
The card is rendered from the quote text, so reusing one puts a \
byte-identical image in front of the same follower twice. Prefer a \
different quote from the same cluster; the cluster is the finding, and \
any of its quotes evidences it.

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
            # Was "how 16,000 comments become a finding". The corpus is
            # 15,950, and the model copied the round number straight out
            # of this brief for six regenerations while a rule against
            # rounding sat in the system prompt. Never put an
            # illustrative figure in a brief; the payload has the real
            # ones.
            "Explain how a corpus of comments becomes a finding: clustering, "
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
    charts_taken: set[str] | None = None,
    quotes_taken: set[str] | None = None,
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
    if quotes_taken:
        payload["quotes_already_used_in_other_threads"] = sorted(quotes_taken)

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
    # Each chart may be used once per thread. The prompt says so, and the
    # prompt was not enough: one angle asked for the "aspects" chart on
    # six of eight posts, which renders the same picture six times in a
    # row. A reader scrolling that sees a broken feed, not evidence.
    #
    # Dropping the repeat rather than the post is deliberate — the text
    # is fine, and a post with no chart falls back to a stat card, which
    # is a different image. Silently keeping the duplicate is the only
    # outcome that would be wrong.
    #
    # `charts_taken` carries the same rule ACROSS angles, which is where
    # it was still failing: three of five threads independently reached
    # for "aspects", so a follower saw one identical twelve-bar chart
    # three times. Per-thread dedup could not see that, because each
    # thread was individually correct. Charts are a shared resource
    # across a subject's threads, not a per-thread one.
    # Mutated in place, deliberately: the caller's set has to learn what
    # this angle consumed, or every angle starts from the same empty
    # slate and the cross-angle rule does nothing.
    used_charts: set[str] = charts_taken if charts_taken is not None else set()
    for item in result.get("posts", []):
        try:
            chart = item.get("chart")
            if chart in (None, "null", ""):
                chart = None
            elif chart in used_charts:
                log.info("  post %s: dropped repeat of the %s chart",
                         item.get("index"), chart)
                chart = None
            else:
                used_charts.add(chart)
            out.append(
                ThreadPost(
                    index=int(item["index"]),
                    text=str(item["text"]).strip(),
                    kind=str(item.get("kind", "finding")),
                    chart=chart,
                    quote_original=item.get("quote_original") or None,
                    quote_english=item.get("quote_english") or None,
                    quote_likes=item.get("quote_likes"),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    # Tell the caller which quotes this angle consumed, so later angles
    # can be given the list. Not enforced the way charts are: two threads
    # sharing a quote is repetition, not a correctness failure, and
    # dropping the quote would leave a post with nothing to show.
    if quotes_taken is not None:
        for post in out:
            if post.quote_original:
                quotes_taken.add(post.quote_original.strip())

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


def check_repetition(story: Story) -> list[str]:
    """Catch the same figure quoted in more than one post.

    Four of five threads did this. The `method` thread used 509 three
    times, twice for the same cluster in consecutive posts — the reader
    gets told the same fact again in different words, which reads as
    padding in a form where every post has to earn its place.

    Figures inside a quote or its translation do not count: a commenter
    writing "1200kg" and the analysis reporting 1,200 are not the same
    author repeating themselves. Only the model's own prose is checked.

    A closing post naturally restates the headline figure sometimes, so
    the last post is exempt — it is the one place a callback is a
    device rather than an accident.
    """
    import re
    from collections import defaultdict

    seen: dict[str, list[int]] = defaultdict(list)
    body = story.posts[:-1] if len(story.posts) > 1 else story.posts
    for post in body:
        text = post.text
        for quoted in (post.quote_original, post.quote_english):
            if quoted:
                text = text.replace(quoted, " ")
        # Four digits or more, or any comma-grouped number. Below that,
        # like counts and small ranks collide constantly by chance.
        for figure in set(re.findall(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{3,}\b",
                                     text)):
            seen[figure].append(post.index)

    problems: list[str] = []
    for figure, posts in sorted(seen.items()):
        if len(posts) > 1:
            problems.append(
                f"posts {', '.join(map(str, posts))} all cite {figure} — "
                "say a figure once, or say what changed about it"
            )
    return problems


def check_sources_post(story: Story) -> list[str]:
    """Every thread must end on a post carrying the sources link.

    One angle returned its last post as kind "closer" and shipped with
    no link to the evidence at all. That is the worst thing a thread
    here can do quietly: the claim is that every number is checkable,
    and the post whose whole job is providing the destination was
    simply absent.
    """
    if not story.posts:
        return []
    last = story.posts[-1]
    problems: list[str] = []
    if last.kind != "sources":
        problems.append(
            f"post {last.index}: last post is kind '{last.kind}', not 'sources'"
        )
    if "http" not in last.text and "{SOURCES_URL}" not in last.text:
        problems.append(f"post {last.index}: final post carries no sources link")
    return problems


def check_rounding(
    story: Story, analysis: dict, counts: dict | None = None
) -> list[str]:
    """Catch a corpus total written as a round number.

    The prompt forbids this and the model does it anyway — "16,000
    comments" for a corpus of 15,950 survived three regenerations with
    an explicit rule against it. A rounded count in an opening line is
    the first thing a hostile reader checks, and this account's whole
    claim is that its numbers hold up, so the check cannot depend on the
    model choosing to comply.

    Only the corpus totals are checked. A cluster size the model rounds
    would be caught by the same logic, but those are quoted exactly far
    more reliably and the false-positive cost is higher: "300 comments"
    is wrong for a cluster of 301, yet "about a third" is fine prose
    about the same number.
    """
    totals = analysis.get("totals", {})
    exact = {v for v in totals.values() if isinstance(v, int) and v > 999}
    exact.add(sum(c["size"] for c in analysis["clusters"]))

    # The figure the hooks actually reach for is the raw fetched count,
    # and it is NOT in analysis.json — that carries only the clustered
    # subset. Without `counts` the check silently passes the one number
    # most likely to be rounded, which is how it failed the first time.
    for value in (counts or {}).values():
        if isinstance(value, int) and value > 999:
            exact.add(value)

    # The round neighbours of each real total, at 100 and 1000.
    forbidden: dict[int, int] = {}
    for n in exact:
        for step in (100, 1000):
            for near in (n // step * step, (n // step + 1) * step):
                if near != n and abs(near - n) <= step:
                    forbidden[near] = n

    problems: list[str] = []
    for post in story.posts:
        for token in re.findall(r"\b\d[\d,]{3,}\b", post.text):
            value = int(token.replace(",", ""))
            if value in forbidden:
                problems.append(
                    f"post {post.index}: {token} is rounded — "
                    f"the real figure is {forbidden[value]:,}"
                )
    return problems
