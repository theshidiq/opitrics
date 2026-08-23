"""HTML report — the thing you read before scripting a video.

Self-contained: charts are embedded as data URIs so the file can be
moved, mailed or opened offline without losing its images.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

CSS = """
:root {
  --ground:#0F1216; --surface:#161B21; --surface-alt:#1D242C;
  --line:#2A333D; --ink:#E8ECF1; --ink-mid:#A9B4C0; --ink-soft:#78838F;
  --accent:#00B4D8; --pos:#4CAF7D; --neg:#E5484D; --warn:#E8A33D;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);margin:0;
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",
  "Hiragino Sans","Noto Sans JP",sans-serif;}
.wrap{max-width:940px;margin:0 auto;padding:56px 26px 90px}
.eyebrow{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px}
h1{font-size:clamp(30px,4.6vw,46px);line-height:1.08;margin:0 0 18px;
  letter-spacing:-.02em;text-wrap:balance}
h2{font-size:23px;margin:52px 0 14px;letter-spacing:-.01em;
  padding-top:26px;border-top:1px solid var(--line)}
h3{font-size:17px;margin:26px 0 8px;color:var(--ink)}
p{margin:0 0 14px;color:var(--ink-mid);max-width:68ch}
strong{color:var(--ink)}
.stats{display:flex;gap:26px;flex-wrap:wrap;margin:26px 0 8px;
  padding:20px 24px;background:var(--surface);border:1px solid var(--line);
  border-radius:3px}
.stat b{display:block;font-size:25px;color:var(--ink);
  font-variant-numeric:tabular-nums;line-height:1.2}
.stat span{font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-soft);font-family:ui-monospace,monospace}
figure{margin:26px 0}
figure img{width:100%;border:1px solid var(--line);border-radius:3px;display:block}
.brief{background:var(--surface);border-left:2px solid var(--accent);
  padding:22px 26px;border-radius:0 3px 3px 0;margin:26px 0}
.brief p:last-child{margin-bottom:0}
.tbl{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14.5px;min-width:560px}
th{text-align:left;font-family:ui-monospace,monospace;font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-soft);
  font-weight:400;padding:0 14px 10px 0;border-bottom:1px solid var(--line)}
td{padding:12px 14px 12px 0;border-bottom:1px solid var(--surface-alt);
  color:var(--ink-mid);vertical-align:top}
td:first-child{color:var(--ink);font-weight:600}
.num{font-variant-numeric:tabular-nums;text-align:right;
  font-family:ui-monospace,monospace;font-size:13px}
.pill{display:inline-block;padding:2px 9px;border-radius:2px;
  font-size:11px;font-family:ui-monospace,monospace;letter-spacing:.04em}
.pos{background:rgba(76,175,125,.16);color:var(--pos)}
.neg{background:rgba(229,72,77,.16);color:var(--neg)}
.mix{background:rgba(120,131,143,.16);color:var(--ink-soft)}
.card{background:var(--surface);border:1px solid var(--line);
  border-radius:3px;padding:18px 20px;margin:0 0 12px}
.card.unmapped{border-left:2px solid var(--warn)}
.card h3{margin-top:0}
.quote{color:var(--ink);font-size:14.5px;padding:9px 0 0;
  border-top:1px solid var(--surface-alt);margin-top:12px}
.quote span{color:var(--ink-soft);font-family:ui-monospace,monospace;font-size:11.5px}
ul{color:var(--ink-mid);max-width:68ch;padding-left:20px}
li{margin-bottom:7px}
.warn{border-left:2px solid var(--warn);background:var(--surface);
  padding:16px 20px;border-radius:0 3px 3px 0;margin:20px 0}
footer{margin-top:64px;padding-top:24px;border-top:1px solid var(--line);
  color:var(--ink-soft);font-size:13.5px}
"""


def _embed(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def _pill(label: str) -> str:
    cls = {"positive": "pos", "negative": "neg"}.get(label, "mix")
    return f'<span class="pill {cls}">{html.escape(label)}</span>'


def _md_to_html(text: str) -> str:
    """Enough markdown for the LLM's brief — headings, bold, paragraphs."""
    import re

    out: list[str] = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        esc = html.escape(block)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        if esc.startswith("### "):
            out.append(f"<h3>{esc[4:]}</h3>")
        elif esc.startswith("## "):
            out.append(f"<h3>{esc[3:]}</h3>")
        elif esc.startswith(("- ", "* ")):
            items = "".join(
                f"<li>{line.lstrip('-* ').strip()}</li>"
                for line in esc.split("\n")
                if line.strip()
            )
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{esc.replace(chr(10), '<br>')}</p>")
    return "\n".join(out)


def build_report(
    analysis: dict,
    narrative: dict,
    charts: list[Path],
    subject: str,
    meta: dict,
) -> str:
    totals = analysis["totals"]
    clusters = analysis["clusters"]

    car = sorted(
        (c for c in clusters if c.get("aspect") and not c.get("is_meta")),
        key=lambda c: -c["size"],
    )
    unmapped = sorted(
        (c for c in clusters if not c.get("aspect")), key=lambda c: -c["size"]
    )

    headline = narrative.get("headline") or f"What people think of the {subject}"
    brief = _md_to_html(narrative.get("brief", ""))
    angles = narrative.get("angles", [])
    caveats = narrative.get("caveats", [])

    figs = "\n".join(
        f'<figure><img src="{_embed(p)}" alt="{html.escape(p.stem)}"></figure>'
        for p in charts
    )

    rows = "\n".join(
        f"<tr><td>{html.escape(c.get('llm_label') or c['aspect_label'] or '—')}</td>"
        f"<td class='num'>{c['size']:,}</td>"
        f"<td class='num'>{c['total_likes']:,}</td>"
        f"<td>{_pill(c['sentiment']['label'])}</td>"
        f"<td class='num'>{c['sentiment']['polarity']:+.2f}</td>"
        f"<td>{html.escape((c.get('llm_summary') or '')[:130])}</td></tr>"
        for c in car[:18]
    )

    unmapped_cards = "\n".join(
        f'<div class="card unmapped"><h3>{html.escape(c.get("llm_label") or "Unnamed theme")}</h3>'
        f'<p>{c["size"]:,} comments · {c["total_likes"]:,} likes · {_pill(c["sentiment"]["label"])}</p>'
        f'<p>{html.escape(c.get("llm_summary") or "")}</p>'
        f'<div class="quote">{html.escape(c["quotes"][0]["text"][:220])}'
        f'<br><span>{c["quotes"][0]["like_count"]:,} likes</span></div></div>'
        for c in unmapped[:6]
    )

    angle_items = "".join(f"<li>{html.escape(a)}</li>" for a in angles)
    caveat_items = "".join(f"<li>{html.escape(c)}</li>" for c in caveats)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)} — comment analysis</title>
<style>{CSS}</style></head><body><div class="wrap">

<p class="eyebrow">Opitrics · comment analysis</p>
<h1>{html.escape(headline)}</h1>

<div class="stats">
  <div class="stat"><b>{meta['raw']:,}</b><span>fetched</span></div>
  <div class="stat"><b>{meta['videos']}</b><span>videos</span></div>
  <div class="stat"><b>{totals['clustered']:,}</b><span>analysed</span></div>
  <div class="stat"><b>{totals['car'] / max(totals['clustered'], 1):.0%}</b><span>about the car</span></div>
</div>

<div class="brief">{brief}</div>

{figs}

<h2>Aspects, ranked</h2>
<div class="tbl"><table>
<thead><tr><th>theme</th><th class="num">comments</th><th class="num">likes</th>
<th>sentiment</th><th class="num">polarity</th><th>what people say</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<h2>Unmapped themes</h2>
<p>Clusters that matched no aspect in the taxonomy. This is where genuinely
new topics surface — and where the conversation stops being about the car.</p>
{unmapped_cards}

<h2>Angles worth covering</h2>
<ul>{angle_items}</ul>

<h2>Read this before you quote a number</h2>
<div class="warn"><ul>{caveat_items}</ul></div>

<h2>Check this yourself</h2>
<div class="warn">
<p>Every quote in this report links to the original comment on YouTube.
The companion <strong>sources page</strong> lists all {meta['videos']} videos
and every quoted comment with a permalink — click one and you land on that
exact comment, with its like count visible. A quote that was invented would
not resolve.</p>
</div>

<footer>
Generated by Opitrics · {html.escape(meta['generated'])}<br>
{meta['videos']} videos · {meta['raw']:,} comments fetched ·
{totals['clustered']:,} clustered · sentiment scored on
{meta['scored']:,} representative comments.<br>
Sentiment is statistical and sampled. Clusters where the wording and the
intent diverge are re-read and re-scored; those numbers are marked in the
data with the original alongside them. Commenters are not buyers.
</footer>
</div></body></html>"""
