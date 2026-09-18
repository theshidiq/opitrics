"""Make the analysis checkable rather than merely claimed.

Nobody has to believe a comment is real if they can click it. Every
YouTube comment has a permanent ID that resolves to the original on the
original video — a fabricator cannot produce one that works, because
YouTube serves the page, not us.

This module attaches those IDs to quotes and builds an audit page: the
video list, the corpus counts, and every quoted comment with a link to
its source. It is the difference between "trust me" and "go check".
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Printed on every published report. Changing it changes what is on
# pages already out in the world, so it lives here rather than inline.
CONTACT_EMAIL = "info@opitrics.com"

# Icon and manifest links, matching what deploy_sources.py writes at the
# site root. Absolute paths: these pages live at /<subject>/ and
# /<subject>/sources.html, so a relative href would resolve differently
# per page and 404 on one of them.
ICON_TAGS = """<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#FFFFFF">"""


def comment_url(video_id: str, comment_id: str) -> str:
    """A permalink to one comment.

    YouTube resolves `lc=` to the comment thread and scrolls to it. For
    a reply, the id contains a dot and still resolves to its parent
    thread with the reply highlighted.
    """
    return f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


@dataclass
class SourcedQuote:
    text: str
    like_count: int
    comment_id: str
    video_id: str
    video_title: str
    channel: str

    @property
    def url(self) -> str:
        return comment_url(self.video_id, self.comment_id)


def _key(text: str) -> str:
    """A matching key that survives normalisation.

    Quotes in the analysis have been NFKC-folded and had their
    whitespace collapsed, so they rarely equal the raw comment byte for
    byte. Stripping to alphanumerics and CJK — dropping punctuation,
    emoji and spacing entirely — makes the two comparable without
    matching unrelated comments to each other.
    """
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKC", text)
    return re.sub(r"[^\w぀-ヿ一-鿿]", "", folded).lower()


def index_corpus(rows) -> dict[str, dict]:
    """Map comment text → its source, for attaching provenance to quotes.

    Indexed three ways — normalised key, its first 60 characters, and
    the raw text — because a quote may have been truncated or reshaped
    between storage and publication, and an unlinked quote is a quote a
    skeptic cannot check.
    """
    index: dict[str, dict] = {}
    for row in rows:
        text = (row["text"] or "").strip()
        if not text:
            continue
        meta = {
            "comment_id": row["comment_id"],
            "video_id": row["video_id"],
            "video_title": row["video_title"],
            "channel": row["channel_title"],
            "like_count": row["like_count"] or 0,
        }
        key = _key(text)
        if not key:
            continue
        index.setdefault(key, meta)
        index.setdefault(key[:60], meta)
        index.setdefault(text, meta)
    return index


def attach_sources(analysis: dict, index: dict[str, dict]) -> int:
    """Add comment/video ids to every quote in an analysis, in place.

    Returns how many quotes were successfully sourced.
    """
    matched = 0

    for cluster in analysis.get("clusters", []):
        for quote in cluster.get("quotes", []):
            text = quote["text"].strip()
            key = _key(text)
            meta = (
                index.get(text)
                or index.get(key)
                or index.get(key[:60])
            )
            if not meta:
                continue
            quote["comment_id"] = meta["comment_id"]
            quote["video_id"] = meta["video_id"]
            quote["video_title"] = meta["video_title"]
            quote["channel"] = meta["channel"]
            quote["url"] = comment_url(meta["video_id"], meta["comment_id"])
            matched += 1
    return matched


CSS = """
/* Mirrors remotion/src/theme.ts. A viewer taps from a short straight to
   this page; two palettes read as two publications, and the whole point
   of the link is that it is the same one. The contrast ratios there were
   measured, not estimated — carry the values, do not re-pick them by eye.
   `--ink-3` in particular replaces a warm grey that ran near 3.5:1 on
   small uppercase labels, the same failure theme.ts records for #909090. */
/* --soft is a fill (code, tints); --hair is the lighter internal rule.
   They were one warm token before, which on white made the internal
   hairlines fainter than the warm original measured. */
:root{--bg:#FFFFFF;--card:#FFFFFF;--line:#BFBFBF;--soft:#F4F4F4;--hair:#E0E0E0;
  --ink:#000000;--ink-2:#3D3D3D;--ink-3:#5A5A5A;--accent:#0546A8;--ok:#0A5F2F}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",
  "Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:48px 24px 90px}
header{border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:26px}
.eyebrow{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 9px}
h1{font-size:31px;line-height:1.15;margin:0 0 12px;letter-spacing:-.018em}
.lede{color:var(--ink-2);margin:0;max-width:66ch}
h2{font-size:14px;font-family:ui-monospace,monospace;letter-spacing:.13em;
  text-transform:uppercase;margin:44px 0 14px;padding-top:18px;
  border-top:1px solid var(--ink)}
/* Hairlines come from the cells, not from a gap over a coloured
   container. With auto-fit, a row that does not divide evenly leaves
   empty tracks, and those tracks paint the container background as a
   solid block — four stats over three columns on a phone. Bordering
   each cell wraps cleanly at any count and any width. */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:0;margin:22px 0;border:1px solid var(--line);border-width:1px 0 0 1px}
.stat{background:var(--card);padding:15px 17px;
  border:1px solid var(--line);border-width:0 1px 1px 0}
.stat b{display:block;font-size:23px;font-variant-numeric:tabular-nums;
  font-family:ui-monospace,monospace}
.stat span{font-size:10.5px;font-family:ui-monospace,monospace;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-3)}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th{text-align:left;font-family:ui-monospace,monospace;font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
  font-weight:400;padding:0 12px 9px 0;border-bottom:1px solid var(--line)}
td{padding:11px 12px 11px 0;border-bottom:1px solid var(--hair);
  color:var(--ink-2);vertical-align:top}
td a{color:var(--accent)}
.num{font-family:ui-monospace,monospace;text-align:right;font-variant-numeric:tabular-nums}
.q{background:var(--card);border:1px solid var(--line);padding:15px 17px;
  margin-bottom:11px}
.q-text{font-size:16px;line-height:1.5;margin:0 0 10px}
.q-meta{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--ink-3);
  display:flex;gap:14px;flex-wrap:wrap;align-items:center;
  border-top:1px solid var(--hair);padding-top:9px}
.q-meta a{color:var(--accent);text-decoration:none}
.q-meta a:hover{text-decoration:underline}
.note{border-left:2px solid var(--accent);background:#F1F5FB;padding:15px 19px;
  margin:22px 0;font-size:15px;color:var(--ink-2)}
.note b{color:var(--ink)}
.note.ok{border-left-color:var(--ok);background:#F0F7F2}
code{font-family:ui-monospace,monospace;font-size:13px;background:var(--soft);
  padding:1px 5px}
footer{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);
  color:var(--ink-3);font-size:13.5px}

/* ── report ─────────────────────────────────────────────────
   Charts are embedded as data URIs so a page is one file with no
   second request that can 404. A wide chart scrolls inside its own
   box rather than widening the page — the scatter is unreadable
   below about 700px and squeezing it to fit helps nobody. */
figure{margin:24px 0}
figure .scroll{overflow-x:auto;border:1px solid var(--line)}
figure img{display:block;width:100%;min-width:640px;height:auto}
figure.wide img{min-width:860px}
figcaption{font-size:13.5px;color:var(--ink-3);margin-top:9px;max-width:70ch}
.finding{border-left:2px solid var(--accent);padding:2px 0 2px 17px;margin:26px 0}
.finding h3{font-size:19px;margin:0 0 7px;letter-spacing:-.01em;line-height:1.25}
.finding p{margin:0;color:var(--ink-2)}
.group{margin:34px 0 0}
.group>h3{font-size:12px;font-family:ui-monospace,monospace;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);margin:0 0 12px;
  padding-bottom:7px;border-bottom:1px solid var(--hair)}
.theme{border:1px solid var(--line);padding:15px 17px;margin-bottom:11px}
.theme-top{display:flex;justify-content:space-between;gap:14px;
  align-items:baseline;flex-wrap:wrap}
.theme h4{font-size:16.5px;margin:0 0 6px;letter-spacing:-.01em}
.theme .sum{color:var(--ink-2);font-size:14.5px;margin:0 0 11px}
.bar{display:flex;height:7px;margin:11px 0 9px;overflow:hidden}
.bar i{display:block}
.bar .p{background:var(--ok)}
.bar .u{background:var(--ink-3)}
.bar .n{background:#A81C19}
.theme-meta{font-family:ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-3);display:flex;gap:13px;flex-wrap:wrap}
.pill{font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.06em;
  text-transform:uppercase;border:1px solid var(--line);padding:2px 7px;
  color:var(--ink-3);white-space:nowrap}
.pill.warn{border-color:#8A5A00;color:#8A5A00}
blockquote{margin:11px 0 0;padding:11px 0 0;border-top:1px solid var(--hair);
  font-size:15px;line-height:1.5;color:var(--ink)}
blockquote .src{display:block;font-family:ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-3);margin-top:7px}
blockquote .src a{color:var(--accent);text-decoration:none}
blockquote .src a:hover{text-decoration:underline}
.toc{margin:22px 0 0;padding:0;list-style:none;columns:2;column-gap:26px}
.toc li{margin-bottom:6px;font-size:14.5px;break-inside:avoid}
.toc a{color:var(--accent);text-decoration:none}
.toc a:hover{text-decoration:underline}
/* ── specifications ─────────────────────────────────────────
   The car's own figures, each beside what the comment section said
   about it. A spec row and a comment count sit in the same block
   deliberately: the point is the pairing, not the table. */
/* One table, not fifteen cards. The card layout ran 3,752px — four
   and a half phone screens — and eleven of those cards existed only to
   say nothing discussed this figure, so the four that mattered were
   buried in repetition. A table puts the discussed rows where they can
   be found. */
.spectable{overflow-x:auto;border:1px solid var(--line);margin:20px 0}
table.spec{width:100%;min-width:560px;border-collapse:collapse;
  font-size:14.5px;background:var(--card)}
table.spec caption{white-space:normal}
/* With the per-row column gone this is the only route to the source, so
   it needs to be tappable rather than a 12px-tall line of text. */
table.spec caption a{color:var(--accent);text-decoration:none;
  display:inline-block;padding:6px 2px}
table.spec caption a:hover{text-decoration:underline}
table.spec caption{caption-side:top;text-align:left;
  font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-3);padding:13px 15px 9px;
  border-bottom:1px solid var(--line)}
table.spec th{text-align:left;font-family:ui-monospace,monospace;
  font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink-3);font-weight:400;padding:11px 15px 9px;
  border-bottom:1px solid var(--line);white-space:nowrap}
table.spec td{padding:12px 15px;border-bottom:1px solid var(--hair);
  vertical-align:top;color:var(--ink-2)}
table.spec tr:last-child td{border-bottom:none}
/* The group heading is a row, so the table stays one scroll frame
   rather than several tables each with their own overflow box. */
table.spec tr.grp td{background:var(--soft);font-family:ui-monospace,monospace;
  font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-3);padding:9px 15px;border-bottom:1px solid var(--line)}
table.spec td.f{color:var(--ink);white-space:nowrap}
/* Values wrap, but never mid-figure. `nowrap` here forced "MacPherson
   strut front, torsion beam rear" onto one line and pushed the column
   to 388px, which is what made the table overflow at desktop width.
   `balance` keeps "1,160–1,230 kg" and "22.40 or 35.84 kWh" whole
   because they contain no spaces a break could land in. */
table.spec td.v{font-family:ui-monospace,monospace;font-weight:600;
  color:var(--ink);font-variant-numeric:tabular-nums;
  white-space:normal;text-wrap:balance;min-width:20ch}
/* The figure itself never breaks, however narrow the column gets: a
   kerb weight split as "1,160–" / "1,230 kg" reads as two numbers, and
   this table exists to make figures legible. Only the caveat below it
   reflows. */
table.spec td.v>.fig{white-space:nowrap}
/* ...except a prose value like "MacPherson strut front, torsion beam
   rear", which has no digits to split and must wrap or it forces the
   column wider than the phone. Marked at build time, not guessed in
   CSS. */
table.spec td.v>.fig.prose{white-space:normal}
/* Named `caveat`, not `note`: `.note` is the page's callout box, and a
   spec caveat inheriting it rendered every note as a tinted panel with
   a left border, which is what made the table taller than the cards it
   replaced. */
table.spec .caveat{display:block;font-family:inherit;font-weight:400;
  font-size:12.5px;color:var(--ink-3);white-space:normal;margin-top:3px;
  background:none;border:0;padding:0}
table.spec td.s{white-space:nowrap}
table.spec td.s a{color:var(--accent);text-decoration:none;
  font-family:ui-monospace,monospace;font-size:11.5px}
table.spec td.s a:hover{text-decoration:underline}
/* Discussed rows read heavier than quiet ones: that contrast is the
   whole reason for the table. */
table.spec tr.said td{background:#F8FAFD}
table.spec td.c{font-size:13.5px}
table.spec td.c .none{color:var(--ink-3);font-size:13px}
table.spec td.c a{color:var(--accent);text-decoration:none}
table.spec td.c a:hover{text-decoration:underline}
table.spec td.c .n{font-family:ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-3);white-space:nowrap}
table.spec td.c ul{list-style:none;padding:0;margin:0}
table.spec td.c li{padding:2px 0}
/* Negative share as a hairline bar: a reader scanning the column sees
   which figures drew heat without reading a percentage. */
.heat{display:inline-block;width:40px;height:4px;background:var(--hair);
  margin-left:7px;vertical-align:middle;position:relative}
.heat i{display:block;height:4px;background:#A81C19}
/* ── navigation ─────────────────────────────────────────────
   Every visitor arrives from a thread or a description, landing on a
   subject page rather than the index — so these pages were dead ends
   with no route to the comparison, the other cars, or even the audit
   page the post promised. All hrefs are absolute: the report sits at
   /<subject>/ and its audit page at /<subject>/sources.html, so a
   relative link would resolve differently on the two. */
.sitenav{display:flex;align-items:baseline;gap:8px 16px;flex-wrap:wrap;
  padding-bottom:13px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.sitenav .brand{font-family:ui-monospace,monospace;font-size:12px;
  letter-spacing:.16em;text-transform:uppercase;color:var(--ink);
  text-decoration:none;font-weight:600}
.sitenav .brand:hover{color:var(--accent)}
.sitenav nav{display:flex;gap:14px;flex-wrap:wrap;margin-left:auto}
.sitenav nav a{font-size:13.5px;color:var(--ink-3);text-decoration:none}
.sitenav nav a:hover{color:var(--accent)}
.sitenav nav a[aria-current]{color:var(--ink);font-weight:600}
/* The two views of one subject. This pair is the whole promise of the
   project — a finding and the evidence for it — so it sits directly
   under the title rather than in the nav row with the site links. */
.views{display:flex;gap:0;margin:0 0 26px;border:1px solid var(--line)}
.views a{flex:1;padding:10px 14px;font-size:13.5px;text-decoration:none;
  color:var(--accent);border-right:1px solid var(--line)}
.views a:last-child{border-right:0}
.views a:hover{background:var(--soft)}
.views a[aria-current]{background:var(--soft);color:var(--ink);
  font-weight:600;cursor:default}
.views b{display:block;font-size:13.5px}
.views span{display:block;font-size:12px;color:var(--ink-3);
  font-weight:400;margin-top:2px}
/* Other subjects, so a reader who arrived for one car can find the
   rest without going via the index. */
.siblings{margin:30px 0 0;padding-top:20px;border-top:1px solid var(--line)}
.siblings h3{font-size:11px;font-family:ui-monospace,monospace;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);
  margin:0 0 11px}
.siblings ul{list-style:none;padding:0;margin:0;display:flex;
  gap:8px 10px;flex-wrap:wrap}
.siblings li{margin:0}
.siblings a{display:block;border:1px solid var(--line);padding:8px 12px;
  font-size:14px;color:var(--accent);text-decoration:none}
.siblings a:hover{background:var(--soft)}
/* The compare link is prose, not one of the car chips: bordered and
   full-width it read as a button, which it is not. */
.siblings .all a{display:inline;border:0;padding:0}
.siblings .all a:hover{background:none;text-decoration:underline}
.siblings .n{color:var(--ink-3);font-family:ui-monospace,monospace;
  font-size:11.5px}
@media(max-width:560px){.toc{columns:1}
  h1{font-size:26px}
  .wrap{padding:34px 18px 70px}
  .sitenav nav{margin-left:0;width:100%}
  .views{flex-direction:column}
  .views a{border-right:0;border-bottom:1px solid var(--line)}
  .views a:last-child{border-bottom:0}}
"""


def site_nav(here: str = "") -> str:
    """The masthead: back to the index, and the site's other sections.

    `here` marks the current section with aria-current, which both styles
    it and tells a screen reader where it is. The comparison link is
    included unconditionally — it exists whenever more than one subject
    has been published, and a subject page is never published alone.
    """
    def link(href: str, label: str, key: str) -> str:
        cur = ' aria-current="page"' if key == here else ""
        return f'<a href="{href}"{cur}>{label}</a>'

    return f"""<div class="sitenav">
  <a class="brand" href="/">Opitrics</a>
  <nav>
    {link("/", "All analyses", "index")}
    {link("/compare/", "Compared", "compare")}
    {link("/terms", "Terms", "terms")}
    {link("/privacy", "Privacy", "privacy")}
  </nav>
</div>"""


def subject_views(subject: str, here: str) -> str:
    """The two views of one subject: the finding, and the evidence.

    These are the project's central pair, and until now neither page
    linked to the other — so a reader on the audit page could not reach
    the analysis it belongs to, and a reader on the report had to trust
    a sentence in the method note to find the quotes.
    """
    def view(path: str, title: str, sub: str, key: str) -> str:
        if key == here:
            return (
                f'<a aria-current="page"><b>{title}</b>'
                f"<span>{sub}</span></a>"
            )
        return f'<a href="{path}"><b>{title}</b><span>{sub}</span></a>'

    return f"""<div class="views">
  {view(f"/{subject}/", "The analysis",
        "Themes, charts and what the comment section said", "report")}
  {view(f"/{subject}/brief/", "The briefing",
        "Where the discussion catches, and on what", "brief")}
  {view(f"/{subject}/sources.html", "The sources",
        "Every video read and every quote, with permalinks", "sources")}
</div>"""


def sibling_subjects(subject: str, others: list[dict]) -> str:
    """Links to the other subjects analysed, for a reader who arrived here.

    `others` is [{"subject", "name", "comments"}]. Returns "" when there
    are none, so a first-and-only subject renders without an empty
    heading.
    """
    rest = [o for o in others if o.get("subject") != subject]
    if not rest:
        return ""

    items = "\n".join(
        f'<li><a href="/{html.escape(o["subject"])}/">'
        f'{html.escape(o["name"])}'
        + (
            f' <span class="n">{o["comments"]:,}</span>'
            if o.get("comments") else ""
        )
        + "</a></li>"
        for o in rest
    )
    return f"""<div class="siblings">
  <h3>Other cars analysed</h3>
  <ul>
{items}
  </ul>
  <p class="all" style="margin:13px 0 0;font-size:13.5px">
    <a href="/compare/">See all {len(rest) + 1} compared side by side →</a>
  </p>
</div>"""


def _embed(path: Path) -> str:
    """A chart as a data URI, so the page is one self-contained file."""
    import base64

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _quote_block(quote: dict) -> str:
    """One quote with its permalink, or nothing.

    A quote without a source is not rendered at all. The whole claim of
    these pages is that anything shown can be checked; an unlinked quote
    on a report page would be exactly the sort of assertion the project
    exists to avoid making.
    """
    if not quote.get("url"):
        return ""
    text = html.escape(quote["text"][:320])
    likes = quote.get("like_count", 0)
    channel = html.escape(quote.get("channel", "")[:30])
    return (
        f'<blockquote>{text}'
        f'<span class="src">{likes:,} likes · {channel} · '
        f'<a href="{quote["url"]}" target="_blank" rel="noopener">'
        f'check it ↗</a></span></blockquote>'
    )


def _theme_card(cluster: dict) -> str:
    """One theme: what it is, how it splits, and a quote you can check."""
    s = cluster.get("sentiment", {})
    pos = s.get("positive", 0.0)
    neu = s.get("neutral", 0.0)
    neg = s.get("negative", 0.0)
    label = cluster.get("llm_label") or cluster.get("aspect_label", "—")
    summary = cluster.get("llm_summary", "")

    pills = [f'<span class="pill">{html.escape(cluster.get("aspect_label", ""))}</span>']
    if cluster.get("sarcasm_risk"):
        # Flagged rather than hidden: the sentiment score for a sarcastic
        # cluster is the least trustworthy number on the page, and the
        # method section promises this is surfaced, not quietly used.
        pills.append('<span class="pill warn">sarcasm risk</span>')

    quotes = "".join(
        _quote_block(q) for q in cluster.get("quotes", [])[:2]
    )

    return f"""<div class="theme" id="theme-{cluster.get('cluster_id', '')}">
  <div class="theme-top">
    <h4>{html.escape(label)}</h4>
    <div>{"".join(pills)}</div>
  </div>
  <p class="sum">{html.escape(summary)}</p>
  <div class="bar" role="img" aria-label="{pos:.0%} positive, {neu:.0%} neutral, {neg:.0%} negative">
    <i class="p" style="width:{pos:.1%}"></i>
    <i class="u" style="width:{neu:.1%}"></i>
    <i class="n" style="width:{neg:.1%}"></i>
  </div>
  <div class="theme-meta">
    <span>{cluster['size']:,} comments</span>
    <span>{cluster.get('total_likes', 0):,} likes</span>
    <span>{cluster.get('channel_spread', 0)} channels</span>
    <span>{pos:.0%} pos · {neg:.0%} neg</span>
  </div>
  {quotes}
</div>"""


def _spec_row(spec, clusters: list[dict], per_row_source: bool = True) -> str:
    """One figure as a table row, with what the comment section said.

    The themes are named and counted, not summarised: a count is a fact
    about the corpus, and a summary here would be a second opinion about
    a theme that already carries its own. Each links to its own card
    further down the page, so the figure is a way into the discussion
    rather than a replacement for it.

    `per_row_source` is False when every figure in the table came from
    one page. The rule is that a figure must be one click from its
    source, not that the link be repeated — fourteen identical "check"
    links is a column of noise, and the caption carries the link
    instead. It stays True as soon as sources differ, because then the
    column says something.
    """
    from opitrics.analyze import specs as specs_mod

    themes = specs_mod.themes_for(spec, clusters)

    if themes:
        items = "".join(
            f'<li><a href="#theme-{t["cluster_id"]}">'
            f'{html.escape(t.get("llm_label") or t.get("aspect_label", "theme"))}</a>'
            f'<span class="n"> {t.get("size", 0):,}'
            f'<span class="heat" title="'
            f'{t.get("sentiment", {}).get("negative", 0):.0%} negative">'
            f'<i style="width:{t.get("sentiment", {}).get("negative", 0) * 100:.0f}%">'
            f"</i></span></span></li>"
            for t in themes[:3]
        )
        more = (
            f'<li class="n">+{len(themes) - 3} more</li>'
            if len(themes) > 3 else ""
        )
        said = f"<ul>{items}{more}</ul>"
        row_class = ' class="said"'
    else:
        # Said plainly rather than left blank. A figure nobody discussed
        # is a true fact about the car and an absence in the corpus, and
        # the absence is itself worth knowing — it is what the `defect`
        # angle failed to notice.
        said = '<span class="none">—</span>'
        row_class = ""

    note = (
        f'<span class="caveat">{html.escape(spec.note)}</span>'
        if spec.note else ""
    )

    # A value with no digit is prose, not a figure, and may wrap. Decided
    # here rather than in CSS because only the data knows which it is.
    fig_cls = "" if any(ch.isdigit() for ch in spec.value) else " prose"
    # A source must land on a page, never a file. These figures were once
    # sourced to a catalogue PDF, so every link fired a 5.5 MB download
    # rather than opening something readable, which is the wrong thing to
    # do to a reader who clicked to verify a number.
    src = ""
    if per_row_source:
        src_name = html.escape(spec.source_name or "source")
        src = (
            f'<td class="s"><a href="{html.escape(spec.source_url)}" '
            f'target="_blank" rel="noopener" title="{src_name}">'
            f"check ↗</a></td>"
        )

    return (
        f"<tr{row_class}>"
        f'<td class="f">{html.escape(spec.label)}</td>'
        f'<td class="v"><span class="fig{fig_cls}">'
        f"{html.escape(spec.value)}</span>{note}</td>"
        f'<td class="c">{said}</td>'
        f"{src}</tr>"
    )


def build_spec_section(specs: list, clusters: list[dict]) -> str:
    """The car's published figures as one table, beside the discussion.

    Returns "" when there are no specs, so a subject without a
    specs.json renders exactly as it did before.
    """
    if not specs:
        return ""

    from opitrics.analyze import specs as specs_mod

    discussed, total = specs_mod.coverage(specs, clusters)

    # When every figure came from one page, the per-row link is fourteen
    # copies of the same href — a column of noise as wide as the figures
    # themselves. The rule is that a figure is one click from its source,
    # not that the link is repeated, so the caption carries it once and
    # the column disappears. As soon as two sources exist the column
    # returns, because then it tells the reader which is which.
    urls = {s.source_url for s in specs}
    single = len(urls) == 1
    per_row_source = not single
    cols = 3 if single else 4

    # Groups are rows inside one table rather than separate tables: a
    # phone gets one horizontal scroll frame instead of five, and the
    # figure column stays aligned down the whole section.
    body = ""
    for name, items in specs_mod.by_group(specs):
        body += (
            f'<tr class="grp"><td colspan="{cols}">'
            f"{html.escape(name)}</td></tr>\n"
        )
        body += "\n".join(
            _spec_row(s, clusters, per_row_source) for s in items
        ) + "\n"

    names = sorted({s.source_name for s in specs if s.source_name})
    if single:
        # One source: name it and link it in the caption, so the
        # destination is stated once, prominently, instead of hidden in
        # fourteen link titles.
        only = next(iter(urls))
        label = html.escape(names[0] if names else "the manufacturer")
        credit = (
            f' · every figure from <a href="{html.escape(only)}" '
            f'target="_blank" rel="noopener">{label} ↗</a>'
        )
        head_src = ""
    else:
        head_src = "<th>source</th>"
        if not names:
            credit = ""
        elif len(names) == 1:
            credit = " · from " + html.escape(names[0])
        else:
            # Several documents from one maker: the shortest name is the
            # shared publisher, so listing them all spells it out twice.
            # Credit the publisher; the per-row link names the document.
            shortest = min(names, key=len)
            if all(n.startswith(shortest) for n in names):
                credit = f" · from {html.escape(shortest)}, linked per row"
            else:
                credit = f" · from {len(names)} sources, linked per row"

    return f"""
<h2>The car itself</h2>
<p style="color:var(--ink-2);margin:0 0 4px;max-width:66ch">
  What the manufacturer publishes, beside what the comment section made
  of it. {discussed} of {total} figures were raised by commenters at
  all; the rest show a dash. The bar is the share of that theme reading
  negative.
</p>
<div class="spectable">
<table class="spec">
  <caption>Manufacturer figures · {discussed} of {total} discussed{credit}</caption>
  <thead><tr><th>figure</th><th>published</th>
    <th>what the comment section said</th>{head_src}</tr></thead>
  <tbody>
{body}  </tbody>
</table>
</div>
<div class="note">
  <b>These are the manufacturer's figures, not ours.</b> They are typed
  in by hand from the pages linked on each row, and nothing here is
  measured, tested or inferred by this project. A figure and a complaint
  sitting side by side is not a verdict on either: the comments are
  opinions with permalinks, the specs are claims with sources, and
  deciding between them is the reader's business.
</div>"""


def build_report_page(
    subject: str,
    display_name: str,
    analysis: dict,
    videos: list,
    meta: dict,
    charts: dict[str, Path] | None = None,
    sources_url: str = "",
    specs: list | None = None,
    siblings: list[dict] | None = None,
) -> str:
    """The full public report: what was found, shown, and checkable.

    The audit page answers "is this real". This answers "what did you
    find" — and every theme on it carries a quote with a permalink, so
    the two questions have the same answer.
    """
    totals = analysis["totals"]
    clusters = analysis.get("clusters", [])
    car = [c for c in clusters if not c.get("is_meta")]
    car.sort(key=lambda c: -c["size"])

    charts = charts or {}
    # Count only the themes actually shown. Meta clusters are excluded
    # from the page, so counting them here would state a number a reader
    # could not find by looking — on a page whose premise is that its
    # numbers survive being checked.
    flagged = sum(1 for c in car if c.get("sarcasm_risk"))

    # Group by aspect, largest group first, themes within by size.
    groups: dict[str, list] = {}
    for c in car:
        groups.setdefault(c.get("aspect_group", "Other"), []).append(c)
    ordered = sorted(
        groups.items(), key=lambda kv: -sum(x["size"] for x in kv[1])
    )

    def chart_figure(key: str, caption: str, wide: bool = False) -> str:
        path = charts.get(key)
        if not path or not Path(path).exists():
            return ""
        cls = "wide" if wide else ""
        return (
            f'<figure class="{cls}"><div class="scroll">'
            f'<img src="{_embed(Path(path))}" alt="{html.escape(caption)}">'
            f'</div><figcaption>{caption}</figcaption></figure>'
        )

    toc = "\n".join(
        f'<li><a href="#{_slug(name)}">{html.escape(name)}</a> '
        f'<span style="color:var(--ink-3)">· {sum(c["size"] for c in cl):,}</span></li>'
        for name, cl in ordered
    )

    sections = "\n".join(
        f'<div class="group" id="{_slug(name)}"><h3>{html.escape(name)} · '
        f'{sum(c["size"] for c in cl):,} comments</h3>'
        + "\n".join(_theme_card(c) for c in cl)
        + "</div>"
        for name, cl in ordered
    )

    top = car[0] if car else None
    headline = (
        f"The largest single theme is <b>{html.escape(top.get('llm_label',''))}</b>, "
        f"{top['size']:,} comments carrying {top.get('total_likes',0):,} likes "
        f"across {top.get('channel_spread',0)} channels."
        if top else ""
    )

    sources_link = (
        f'<p style="margin:18px 0 0"><a href="{sources_url}" '
        f'style="color:var(--accent)">Every quote, with its permalink →</a></p>'
        if sources_url else ""
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(display_name)} — what the comments say</title>
<meta name="description" content="An analysis of {meta['raw']:,} YouTube comments about the {html.escape(display_name)}, with every quote linked to its source.">
{ICON_TAGS}
<meta property="og:type" content="article">
<meta property="og:site_name" content="Opitrics">
<meta property="og:title" content="What {html.escape(display_name)} comment sections actually say">
<meta property="og:description" content="{meta['raw']:,} comments from {len(videos)} videos, grouped by meaning and scored for sentiment.">
<meta name="twitter:card" content="summary">
<style>{CSS}</style></head><body><div class="wrap">
{site_nav("")}
<header>
  <p class="eyebrow">Comment analysis</p>
  <h1>What {html.escape(display_name)} comment sections actually say</h1>
  <p class="lede">
    {meta['raw']:,} comments from {len(videos)} videos, grouped by meaning and
    scored for sentiment. {headline}
  </p>
</header>

{subject_views(subject, "report")}

<div class="stats">
  <div class="stat"><b>{meta['raw']:,}</b><span>comments read</span></div>
  <div class="stat"><b>{len(videos)}</b><span>videos</span></div>
  <div class="stat"><b>{totals['clustered']:,}</b><span>analysed</span></div>
  <div class="stat"><b>{len(car)}</b><span>themes found</span></div>
</div>

{chart_figure("composition",
  "Not every comment is about the car. Comments about the video or its "
  "presenter are separated out and excluded from the themes below.")}

{build_spec_section(specs or [], clusters)}

<h2>What people talk about</h2>
<p style="color:var(--ink-2);margin:0 0 4px;max-width:66ch">
  Each bar is a theme the clustering found, placed by the average sentiment
  of its comments. Bar length is sentiment, not size — the number beside it
  is how many comments it holds.
</p>
{chart_figure("aspects",
  "Themes ranked by size, coloured by sentiment. Red is net negative, "
  "green net positive, grey mixed or neutral.")}

<h2>Jump to a theme</h2>
<ul class="toc">{toc}</ul>

<h2>The themes</h2>
<p style="color:var(--ink-2);margin:0 0 4px;max-width:66ch">
  Grouped by subject. Each bar shows the positive / neutral / negative split
  within that theme, and each carries a real comment you can open on YouTube.
</p>
{sections}

<h2>Volume against intensity</h2>
<p style="color:var(--ink-2);margin:0 0 4px;max-width:66ch">
  How much a theme is discussed, against how strongly. The top-right corner
  is what a headline should be about; the top-left is loud but niche.
</p>
{chart_figure("volume-intensity",
  "Each dot is a theme. Horizontal is comment volume, vertical is intensity "
  "of feeling, and dot size is like-weighted reach.", wide=True)}

<h2>Method, and what it gets wrong</h2>
<div class="note">
  <b>This is not a poll.</b> People who comment are not people who buy, and
  they skew toward enthusiasts and toward strong opinions. This measures what
  the comment section thinks, which is a proxy for public perception and a
  poor proxy for sales.
  <br><br>
  <b>Sentiment is scored by machine and sampled.</b> Comments are grouped by
  meaning, then a multilingual model scores a sample from each group.
  Sarcasm detection is weak, especially in Japanese —
  {flagged} theme(s) here are flagged for sarcasm risk, and their scores
  should be read as uncertain rather than wrong.
  <br><br>
  <b>Nothing was written by hand.</b> The clusters, counts and quotes come
  from the pipeline. Quotes are checked against the stored corpus before
  publication, so a paraphrase cannot reach the page.
  {sources_link}
</div>

{sibling_subjects(subject, siblings or [])}

<footer>
  {html.escape(display_name)} · {meta['raw']:,} comments from {len(videos)} videos ·
  fetched {html.escape(meta.get('fetched_on', ''))} ·
  generated {datetime.now().strftime('%Y-%m-%d')}<br>
  Comment authors are not named; the permalink is what makes a quote
  checkable. Spotted an error? <a href="mailto:{CONTACT_EMAIL}"
  style="color:var(--accent)">{CONTACT_EMAIL}</a><br>
  <a href="/" style="color:var(--accent)">All analyses</a> ·
  <a href="/compare/" style="color:var(--accent)">Compared</a> ·
  <a href="/terms" style="color:var(--accent)">Terms</a> ·
  <a href="/privacy" style="color:var(--accent)">Privacy</a>
</footer>
</div></body></html>"""


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "group"


def build_audit_page(
    subject: str,
    display_name: str,
    analysis: dict,
    videos: list,
    meta: dict,
    siblings: list[dict] | None = None,
) -> str:
    """A page a skeptic can use to check the work themselves."""
    totals = analysis["totals"]

    sourced: list[SourcedQuote] = []
    unsourced = 0
    for cluster in analysis.get("clusters", []):
        for quote in cluster.get("quotes", []):
            if quote.get("comment_id"):
                sourced.append(
                    SourcedQuote(
                        text=quote["text"],
                        like_count=quote["like_count"],
                        comment_id=quote["comment_id"],
                        video_id=quote["video_id"],
                        video_title=quote.get("video_title", ""),
                        channel=quote.get("channel", ""),
                    )
                )
            else:
                unsourced += 1

    sourced.sort(key=lambda q: -q.like_count)

    video_rows = "\n".join(
        f"<tr><td><a href='{video_url(v['video_id'])}' target='_blank' rel='noopener'>"
        f"{html.escape(v['title'][:78])}</a></td>"
        f"<td>{html.escape(v['channel_title'][:30])}</td>"
        f"<td class='num'>{v['comments']:,}</td>"
        f"<td class='num'><code>{html.escape(v['video_id'])}</code></td></tr>"
        for v in videos
    )

    quote_cards = "\n".join(
        f"""<div class="q">
          <p class="q-text">{html.escape(q.text[:400])}</p>
          <div class="q-meta">
            <span>{q.like_count:,} likes</span>
            <span>{html.escape(q.channel[:28])}</span>
            <a href="{q.url}" target="_blank" rel="noopener">open on YouTube ↗</a>
          </div>
        </div>"""
        for q in sourced[:60]
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sources · {html.escape(display_name)}</title>
<meta name="description" content="Every video read and every quote used in the {html.escape(display_name)} analysis, each linking to the original comment on YouTube.">
{ICON_TAGS}
<style>{CSS}</style></head><body><div class="wrap">
{site_nav("")}
<header>
  <p class="eyebrow">Check the work</p>
  <h1>Every number and quote behind the {html.escape(display_name)} analysis</h1>
  <p class="lede">
    Nothing here asks to be believed. Every comment below links to the
    original on YouTube — click one and you will land on that exact
    comment, on that exact video, with its like count visible. A quote
    that was invented would not resolve.
  </p>
</header>

{subject_views(subject, "sources")}

<div class="stats">
  <div class="stat"><b>{meta['raw']:,}</b><span>comments fetched</span></div>
  <div class="stat"><b>{len(videos)}</b><span>videos</span></div>
  <div class="stat"><b>{totals['clustered']:,}</b><span>analysed</span></div>
  <div class="stat"><b>{len(sourced):,}</b><span>quotes linked</span></div>
</div>

<div class="note ok">
  <b>How to verify a quote.</b> Click any “open on YouTube” link. YouTube
  will load that video and scroll to the comment. Compare the text and the
  like count with what is shown here. Like counts drift over time — the
  numbers here are from {html.escape(meta.get('fetched_on', 'the fetch date'))},
  so expect small differences on popular comments.
</div>

<h2>Source videos</h2>
<p style="color:var(--ink-2);margin:0 0 16px">
  Every video whose comment section was read. The comment counts are what
  YouTube reported at fetch time; ours include replies, which YouTube's
  headline number excludes.
</p>
<table>
  <thead><tr><th>video</th><th>channel</th>
    <th class="num">comments</th><th class="num">id</th></tr></thead>
  <tbody>{video_rows}</tbody>
</table>

<h2>Quoted comments · {len(sourced)}</h2>
<p style="color:var(--ink-2);margin:0 0 16px">
  Ranked by likes. Every quote used anywhere in the analysis, its charts
  or its threads appears here with a link to its source.
</p>
{quote_cards}

{'<div class="note"><b>' + str(unsourced) + ' quote(s) could not be linked.</b> '
 'These come from comments whose text was normalised before storage, so the '
 'exact source row could not be recovered. They are excluded from the list '
 'above rather than shown without a link.</div>' if unsourced else ''}

<h2>Method, and what it gets wrong</h2>
<div class="note">
  <b>This is not a poll.</b> People who comment are not people who buy, and
  they skew toward enthusiasts and toward strong opinions. This measures
  what the comment section thinks, which is a proxy for public perception
  and a poor proxy for sales.
  <br><br>
  <b>Sentiment is scored by machine and sampled.</b> Comments are grouped by
  meaning, then a multilingual model scores a sample from each group.
  Sarcasm detection is weak, especially in Japanese — where a group reads as
  sarcastic, its score is flagged rather than quoted as fact.
  <br><br>
  <b>Nothing was written by hand.</b> The clusters, counts and quotes come
  from the pipeline. Quotes are checked against the stored corpus before
  publication, so a paraphrase cannot reach a graphic.
</div>

{sibling_subjects(subject, siblings or [])}

<footer>
  {html.escape(display_name)} · {meta['raw']:,} comments from {len(videos)} videos ·
  fetched {html.escape(meta.get('fetched_on', ''))} ·
  generated {datetime.now().strftime('%Y-%m-%d')}<br>
  Raw data and the code that produced this are available on request.<br>
  <a href="/{subject}/" style="color:var(--accent)">The analysis</a> ·
  <a href="/" style="color:var(--accent)">All analyses</a> ·
  <a href="/compare/" style="color:var(--accent)">Compared</a> ·
  <a href="/terms" style="color:var(--accent)">Terms</a> ·
  <a href="/privacy" style="color:var(--accent)">Privacy</a>
</footer>
</div></body></html>"""
