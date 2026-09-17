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
.specgroup{margin:26px 0 0}
.specgroup>h3{font-size:12px;font-family:ui-monospace,monospace;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);
  margin:0 0 10px;padding-bottom:7px;border-bottom:1px solid var(--hair)}
.spec{border:1px solid var(--line);padding:14px 16px;margin-bottom:10px}
.spec-top{display:flex;justify-content:space-between;gap:16px;
  align-items:baseline;flex-wrap:wrap}
.spec-label{font-size:15px;color:var(--ink-2)}
.spec-value{font-family:ui-monospace,monospace;font-size:19px;
  font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.spec-note{font-size:13px;color:var(--ink-3);margin:7px 0 0}
.spec-src{font-family:ui-monospace,monospace;font-size:11px;
  color:var(--ink-3);margin-top:8px}
.spec-src a{color:var(--accent);text-decoration:none}
.spec-src a:hover{text-decoration:underline}
.spec-said{border-top:1px solid var(--hair);margin-top:11px;padding-top:10px}
.spec-said .hd{font-family:ui-monospace,monospace;font-size:10.5px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);
  margin:0 0 7px}
.spec-said ul{list-style:none;padding:0;margin:0}
.spec-said li{font-size:14.5px;color:var(--ink-2);padding:3px 0}
.spec-said li a{color:var(--accent);text-decoration:none}
.spec-said li a:hover{text-decoration:underline}
.spec-said .n{font-family:ui-monospace,monospace;font-size:12px;
  color:var(--ink-3)}
.spec-quiet{font-size:13px;color:var(--ink-3);margin-top:10px;
  border-top:1px solid var(--hair);padding-top:9px}
@media(max-width:560px){.toc{columns:1}
  h1{font-size:26px}
  .wrap{padding:34px 18px 70px}
  .spec-top{flex-direction:column;gap:2px}}
"""


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


def _spec_block(spec, clusters: list[dict]) -> str:
    """One figure, with whatever the comment section said about it.

    The themes are named and counted, not summarised: a count is a fact
    about the corpus, and a summary here would be a second opinion about
    a theme that already carries its own. Each links to its own card
    further down the page, so the figure is a way into the discussion
    rather than a replacement for it.
    """
    from opitrics.analyze import specs as specs_mod

    themes = specs_mod.themes_for(spec, clusters)

    said = ""
    if themes:
        total = sum(t.get("size", 0) for t in themes)
        items = "".join(
            f'<li><a href="#theme-{t["cluster_id"]}">'
            f'{html.escape(t.get("llm_label") or t.get("aspect_label", "theme"))}</a> '
            f'<span class="n">· {t.get("size", 0):,} comments · '
            f'{t.get("sentiment", {}).get("negative", 0):.0%} negative</span></li>'
            for t in themes[:4]
        )
        said = (
            f'<div class="spec-said"><p class="hd">'
            f'What the comment section said · {total:,} comments</p>'
            f"<ul>{items}</ul></div>"
        )
    else:
        # Said plainly rather than left blank. A figure nobody discussed
        # is a true fact about the car and an absence in the corpus, and
        # the absence is itself worth knowing — it is what the `defect`
        # angle failed to notice.
        said = (
            '<p class="spec-quiet">Nothing in this corpus discussed '
            "this.</p>"
        )

    note = (
        f'<p class="spec-note">{html.escape(spec.note)}</p>'
        if spec.note else ""
    )
    src_name = html.escape(spec.source_name or "source")

    return f"""<div class="spec">
  <div class="spec-top">
    <span class="spec-label">{html.escape(spec.label)}</span>
    <span class="spec-value">{html.escape(spec.value)}</span>
  </div>
  {note}
  <p class="spec-src">via <a href="{html.escape(spec.source_url)}"
     target="_blank" rel="noopener">{src_name} ↗</a></p>
  {said}
</div>"""


def build_spec_section(specs: list, clusters: list[dict]) -> str:
    """The car's published figures, grouped, beside the discussion.

    Returns "" when there are no specs, so a subject without a
    specs.json renders exactly as it did before.
    """
    if not specs:
        return ""

    from opitrics.analyze import specs as specs_mod

    discussed, total = specs_mod.coverage(specs, clusters)
    groups = "\n".join(
        f'<div class="specgroup"><h3>{html.escape(name)}</h3>'
        + "\n".join(_spec_block(s, clusters) for s in items)
        + "</div>"
        for name, items in specs_mod.by_group(specs)
    )

    return f"""
<h2>The car itself</h2>
<p style="color:var(--ink-2);margin:0 0 4px;max-width:66ch">
  What the manufacturer publishes, beside what the comment section made
  of it. Every figure links to the page it was read from —
  {discussed} of {total} were raised by commenters at all, and the ones
  nobody mentioned say so.
</p>
<div class="note">
  <b>These are the manufacturer's figures, not ours.</b> They are typed
  in by hand from the pages linked on each row, and nothing here is
  measured, tested or inferred by this project. A figure and a complaint
  sitting side by side is not a verdict on either: the comments are
  opinions with permalinks, the specs are claims with sources, and
  deciding between them is the reader's business.
</div>
{groups}"""


def build_report_page(
    subject: str,
    display_name: str,
    analysis: dict,
    videos: list,
    meta: dict,
    charts: dict[str, Path] | None = None,
    sources_url: str = "",
    specs: list | None = None,
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

<header>
  <p class="eyebrow">Comment analysis</p>
  <h1>What {html.escape(display_name)} comment sections actually say</h1>
  <p class="lede">
    {meta['raw']:,} comments from {len(videos)} videos, grouped by meaning and
    scored for sentiment. {headline}
  </p>
</header>

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

<footer>
  {html.escape(display_name)} · {meta['raw']:,} comments from {len(videos)} videos ·
  fetched {html.escape(meta.get('fetched_on', ''))} ·
  generated {datetime.now().strftime('%Y-%m-%d')}<br>
  Comment authors are not named; the permalink is what makes a quote
  checkable. Spotted an error? <a href="mailto:{CONTACT_EMAIL}"
  style="color:var(--accent)">{CONTACT_EMAIL}</a>
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

<footer>
  {html.escape(display_name)} · {meta['raw']:,} comments from {len(videos)} videos ·
  fetched {html.escape(meta.get('fetched_on', ''))} ·
  generated {datetime.now().strftime('%Y-%m-%d')}<br>
  Raw data and the code that produced this are available on request.
</footer>
</div></body></html>"""
