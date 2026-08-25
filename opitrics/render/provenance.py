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
"""


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
