"""The briefing page: what the discourse tells a product or comms team.

A deck rather than a report — full-height panels, one idea each, figures
big enough to read across a room. Kept as HTML rather than slides so
every number stays one click from the comment it came from, which a
.pptx cannot do.

**The framing is load-bearing, not decoration.** Every claim here is
about what the conversation contains. Nothing says a car will or will
not sell, because commenters are not buyers and this corpus cannot
support that. `STATUS.md` records why the line matters: if a brand ever
approaches, "we never claimed demand signal" has to be true across the
whole archive, and a deck is the format most likely to be read as a
market forecast because decks are built to look authoritative.

So the visual polish is spent on making the evidence legible, and every
panel that states a finding also states what it is not.
"""

from __future__ import annotations

import html

from opitrics.analyze import briefing as br
from opitrics.render.provenance import (
    CONTACT_EMAIL,
    ICON_TAGS,
    site_nav,
    subject_views,
)

CSS = """
:root{--bg:#FFFFFF;--card:#FFFFFF;--line:#BFBFBF;--soft:#F4F4F4;--hair:#E0E0E0;
  --ink:#000000;--ink-2:#3D3D3D;--ink-3:#5A5A5A;--accent:#0546A8;--ok:#0A5F2F;
  --warn:#8A5A00;--neg:#A81C19}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",
  "Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:40px 24px 90px}
a{color:var(--accent)}

/* ── panels ──────────────────────────────────────────────────
   Each section is one idea with room around it, the way a slide is.
   Not actual slides: a deck that paginates hides the evidence one
   click deeper, and the evidence is the product. */
/* Masthead and the analysis/briefing/sources switch, mirroring the
   rules in provenance.py so a visitor crossing between the three views
   of a subject sees no seam. */
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
.views{display:flex;gap:0;margin:0 0 8px;border:1px solid var(--line)}
.views a{flex:1;padding:10px 14px;font-size:13.5px;text-decoration:none;
  color:var(--accent);border-right:1px solid var(--line)}
.views a:last-child{border-right:0}
.views a:hover{background:var(--soft)}
.views a[aria-current]{background:var(--soft);color:var(--ink);
  font-weight:600;cursor:default}
.views b{display:block;font-size:13.5px}
.views span{display:block;font-size:12px;color:var(--ink-3);
  font-weight:400;margin-top:2px}

.panel{padding:44px 0;border-top:1px solid var(--line)}
.panel:first-of-type{border-top:0;padding-top:16px}
.kicker{font-family:ui-monospace,monospace;font-size:11px;
  letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
  margin:0 0 12px}
.panel h2{font-size:30px;line-height:1.14;letter-spacing:-.02em;
  margin:0 0 14px;max-width:20ch}
.panel h2.wide{max-width:28ch}
.panel p.say{font-size:17px;color:var(--ink-2);margin:0 0 6px;max-width:64ch}
.panel p.qual{font-size:14px;color:var(--ink-3);margin:10px 0 0;max-width:64ch}

/* The one number a panel exists to deliver. */
.huge{font-family:ui-monospace,monospace;font-size:clamp(52px,11vw,104px);
  line-height:.95;letter-spacing:-.04em;font-variant-numeric:tabular-nums;
  margin:18px 0 6px;display:block}
.huge small{display:block;font-family:inherit;font-size:14px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
  margin-top:12px}

/* ── shape bar: what the corpus is about ─────────────────── */
.shape{display:flex;height:46px;margin:24px 0 14px;overflow:hidden;
  border:1px solid var(--line)}
.shape i{display:block;position:relative;border-right:1px solid #FFFFFF}
.shape i:last-child{border-right:0}
.shape .k{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;font-family:ui-monospace,monospace;font-size:12px;
  color:#FFFFFF;font-weight:600}
.shapekey{display:flex;gap:8px 18px;flex-wrap:wrap;margin:0 0 4px;
  font-size:13.5px;color:var(--ink-2)}
.shapekey span{display:flex;align-items:center;gap:7px}
.shapekey b{width:11px;height:11px;display:inline-block}

/* ── friction rows ───────────────────────────────────────── */
.rows{margin:22px 0 0;border-top:1px solid var(--line)}
.row{display:grid;grid-template-columns:1fr 128px 92px;gap:18px;
  align-items:center;padding:15px 0;border-bottom:1px solid var(--hair)}
.row .t{min-width:0}
.row .t a{font-size:16.5px;font-weight:600;text-decoration:none;
  display:block;line-height:1.3}
.row .t a:hover{text-decoration:underline}
.row .t .sub{font-size:13.5px;color:var(--ink-3);margin-top:3px}
.row .bar{height:9px;background:var(--hair);position:relative}
.row .bar i{display:block;height:9px;background:var(--neg)}
.row .num{font-family:ui-monospace,monospace;font-size:14px;
  text-align:right;font-variant-numeric:tabular-nums;color:var(--ink-2);
  white-space:nowrap}
.row .num b{display:block;font-size:19px;color:var(--ink)}
.tag{display:inline-block;font-family:ui-monospace,monospace;font-size:10px;
  letter-spacing:.07em;text-transform:uppercase;border:1px solid var(--line);
  padding:1px 6px;color:var(--ink-3);margin-left:7px;vertical-align:middle}
.tag.warn{border-color:var(--warn);color:var(--warn)}

/* ── two-up split ────────────────────────────────────────── */
.split{display:grid;grid-template-columns:1fr 1fr;gap:0;
  border:1px solid var(--line);margin:24px 0 0}
.split>div{padding:22px 24px;border-right:1px solid var(--line)}
.split>div:last-child{border-right:0}
.split h3{font-family:ui-monospace,monospace;font-size:11px;
  letter-spacing:.12em;text-transform:uppercase;margin:0 0 4px}
.split .n{font-family:ui-monospace,monospace;font-size:38px;
  font-variant-numeric:tabular-nums;line-height:1.1;margin:6px 0 2px}
.split p{font-size:14px;color:var(--ink-3);margin:6px 0 0}
.split ul{list-style:none;padding:0;margin:14px 0 0}
.split li{font-size:14.5px;padding:5px 0;border-top:1px solid var(--hair);
  color:var(--ink-2)}
.split li a{text-decoration:none}
.split li a:hover{text-decoration:underline}
.split li .c{font-family:ui-monospace,monospace;font-size:12px;
  color:var(--ink-3)}

/* ── caveat, and the line this page will not cross ───────── */
.guard{border:2px solid var(--ink);padding:22px 24px;margin:30px 0 0}
.guard h3{font-size:17px;margin:0 0 10px}
.guard p{font-size:14.5px;color:var(--ink-2);margin:0 0 9px;max-width:68ch}
.guard p:last-child{margin-bottom:0}
.guard .no{color:var(--neg);font-weight:600}
.guard .yes{color:var(--ok);font-weight:600}

footer{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);
  color:var(--ink-3);font-size:13.5px}
footer a{color:var(--accent)}

@media(max-width:620px){
  .wrap{padding:30px 18px 70px}
  .sitenav nav{margin-left:0;width:100%}
  .views{flex-direction:column}
  .views a{border-right:0;border-bottom:1px solid var(--line)}
  .views a:last-child{border-bottom:0}
  .panel{padding:34px 0}
  .panel h2{font-size:25px}
  .row{grid-template-columns:1fr 78px;gap:12px}
  .row .bar{grid-column:1/-1;order:3}
  .split{grid-template-columns:1fr}
  .split>div{border-right:0;border-bottom:1px solid var(--line)}
  .split>div:last-child{border-bottom:0}
}
"""

# Colours for the shape bar, in the order groups are drawn. Accent for
# the largest, then greys — the point is proportion, not category, and
# a rainbow would imply the groups are equally weighted categories of
# one kind.
SHAPE_COLOURS = ["#0546A8", "#3D3D3D", "#5A5A5A", "#8A8A8A", "#BFBFBF"]


def _shape_bar(rows: list[tuple[str, int, float]]) -> str:
    """The corpus as one proportional bar, with a key."""
    top = rows[:5]
    rest = sum(r[1] for r in rows[5:])
    rest_pct = sum(r[2] for r in rows[5:])
    if rest:
        top = top + [("Other", rest, rest_pct)]

    cols = SHAPE_COLOURS + ["#E0E0E0"]
    segs = "".join(
        f'<i style="width:{pct:.2f}%;background:{cols[min(i, len(cols) - 1)]}">'
        + (f'<span class="k">{pct:.0f}%</span>' if pct >= 9 else "")
        + "</i>"
        for i, (_, _, pct) in enumerate(top)
    )
    key = "".join(
        f'<span><b style="background:{cols[min(i, len(cols) - 1)]}"></b>'
        f"{html.escape(g)} <span style='color:var(--ink-3)'>"
        f"{n:,}</span></span>"
        for i, (g, n, _) in enumerate(top)
    )
    return (
        f'<div class="shape">{segs}</div>'
        f'<div class="shapekey">{key}</div>'
    )


def _rows(themes: list, subject: str, max_friction: float) -> str:
    """Friction themes as ranked rows, each linking to its evidence."""
    out = []
    for t in themes:
        width = 100 * t.friction / max(max_friction, 1)
        sarc = '<span class="tag warn">sarcasm risk</span>' if t.sarcasm else ""
        out.append(
            f'<div class="row"><div class="t">'
            f'<a href="/{html.escape(subject)}/#theme-{t.cluster_id}">'
            f"{html.escape(t.label)}</a>{sarc}"
            f'<div class="sub">{html.escape(t.aspect_label)} · '
            f"{t.channels} channels · {t.likes:,} likes</div></div>"
            f'<div class="bar"><i style="width:{width:.0f}%"></i></div>'
            f'<div class="num"><b>{t.size:,}</b>{t.negative:.0%} neg</div>'
            f"</div>"
        )
    return f'<div class="rows">{"".join(out)}</div>'


def build_brief_page(
    subject: str,
    display_name: str,
    analysis: dict,
    meta: dict,
    siblings: list[dict] | None = None,
) -> str:
    """One car's briefing: where the discussion catches, and on what."""
    ts = br.themes(analysis)
    if not ts:
        return ""

    lead, qual = br.headline(ts, display_name)
    sh = br.shape(ts)
    total = sum(t.size for t in ts)
    prod = [t for t in ts if t.addressable == "product"]
    comms = [t for t in ts if t.addressable == "comms"]
    prod_n = sum(t.size for t in prod)
    comms_n = sum(t.size for t in comms)

    pf = br.friction_points(ts, "product", 5)
    cf = br.friction_points(ts, "comms", 5)
    good = br.strengths(ts, 4)
    far = br.travels_furthest(ts, 3)
    peak = max((t.friction for t in ts), default=1)

    def li(t) -> str:
        return (
            f'<li><a href="/{html.escape(subject)}/#theme-{t.cluster_id}">'
            f"{html.escape(t.label)}</a> "
            f'<span class="c">{t.size:,}</span></li>'
        )

    strengths_block = (
        "<ul>" + "".join(li(t) for t in good) + "</ul>"
        if good
        else '<p>No theme in this corpus reads net positive.</p>'
    )
    reach_block = (
        "<ul>"
        + "".join(
            f'<li><a href="/{html.escape(subject)}/#theme-{t.cluster_id}">'
            f"{html.escape(t.label)}</a> "
            f'<span class="c">{t.reach_per_comment:.0f} likes/comment</span>'
            f"</li>"
            for t in far
        )
        + "</ul>"
        if far
        else ""
    )

    sib = ""
    if siblings:
        rest = [s for s in siblings if s.get("subject") != subject]
        if rest:
            sib = (
                '<p class="qual">Same analysis for '
                + " · ".join(
                    f'<a href="/{html.escape(s["subject"])}/brief/">'
                    f'{html.escape(s["name"])}</a>'
                    for s in rest
                )
                + ' · <a href="/compare/">all four compared</a></p>'
            )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(display_name)} — discourse briefing</title>
<meta name="description" content="Where {html.escape(display_name)} discussion catches, and on what: {total:,} comments grouped by subject, with every theme linked to its comments.">
{ICON_TAGS}
<meta property="og:type" content="article">
<meta property="og:site_name" content="Opitrics">
<meta property="og:title" content="{html.escape(display_name)} — what the discussion catches on">
<meta name="twitter:card" content="summary">
<style>{CSS}</style></head><body><div class="wrap">
{site_nav("")}
{subject_views(subject, "brief")}
<section class="panel">
  <p class="kicker">Discourse briefing · {html.escape(display_name)}</p>
  <h2 class="wide">Where the conversation catches, and on what</h2>
  <p class="say">{lead}</p>
  <p class="say">{qual}</p>
  <p class="qual">
    {total:,} comments about the car, from {meta.get('videos', 0)} videos,
    fetched {html.escape(meta.get('fetched_on', ''))}. Every theme below
    links to the comments behind it.
  </p>
</section>

<section class="panel">
  <p class="kicker">What it is about</p>
  <h2>The subject mix decides the brief</h2>
  <p class="say">
    Grouped by subject, largest first. A corpus dominated by design
    produces a different brief from one dominated by brand — and no
    amount of engineering moves the second.
  </p>
  {_shape_bar(sh)}
  <p class="qual">Shares of the {total:,} comments about the car.
  Comments about the video or its presenter are excluded.</p>
</section>

<section class="panel">
  <p class="kicker">Addressable or not</p>
  <h2>Two different kinds of friction</h2>
  <div class="split">
    <div>
      <h3 style="color:var(--accent)">A product team could act</h3>
      <div class="n">{100 * prod_n / max(total, 1):.0f}%</div>
      <p>{prod_n:,} comments on build, design, driving, practicality,
      features and EV behaviour.</p>
    </div>
    <div>
      <h3>Only communication reaches</h3>
      <div class="n">{100 * comms_n / max(total, 1):.0f}%</div>
      <p>{comms_n:,} comments on brand, origin, price and ownership
      context — conditions rather than defects.</p>
    </div>
  </div>
  <p class="qual">A car's country of manufacture is not a product
  decision. Treating brand discourse as a defect backlog is the error
  this split exists to prevent.</p>
</section>

<section class="panel">
  <p class="kicker">Product friction</p>
  <h2>Where the product itself draws criticism</h2>
  <p class="say">
    Ranked by how many comments in each theme read negative — volume
    times negative share, not a severity score. Bar length is that
    figure relative to the loudest theme on the page.
  </p>
  {_rows(pf, subject, peak) if pf else '<p class="qual">No product theme in this corpus reads substantially negative.</p>'}
</section>

<section class="panel">
  <p class="kicker">Context friction</p>
  <h2>What no product change would move</h2>
  <p class="say">
    The same measure, for themes about brand, origin, price and
    ownership. These are the arguments a team can answer but not
    engineer away.
  </p>
  {_rows(cf, subject, peak) if cf else '<p class="qual">No context theme in this corpus reads substantially negative.</p>'}
</section>

<section class="panel">
  <p class="kicker">The other half</p>
  <h2>What is working, and what travels</h2>
  <div class="split">
    <div>
      <h3 style="color:var(--ok)">Reads positive</h3>
      <p>Themes where approval outweighs criticism — what not to
      break.</p>
      {strengths_block}
    </div>
    <div>
      <h3>Travels furthest</h3>
      <p>Highest likes per comment among themes of 50+. Reach, not
      volume.</p>
      {reach_block or '<p>No theme large enough to rank.</p>'}
    </div>
  </div>
</section>

<section class="panel">
  <p class="kicker">Read this correctly</p>
  <h2 class="wide">What this measures, and what it does not</h2>
  <div class="guard">
    <h3>Commenters are not buyers.</h3>
    <p><span class="yes">This says</span> which attributes generate
    friction in public discussion, at what volume and intensity, with
    every figure traceable to comments you can open.</p>
    <p><span class="no">This does not say</span> whether the car will
    sell, how demand is moving, or what the market will do. People who
    comment skew toward enthusiasts and strong opinions, and nothing
    here surveys a buyer. A decision that needs demand data needs
    demand data.</p>
    <p>Sentiment is machine-scored on a sample of each theme, and
    sarcasm detection is weak in Japanese — themes at risk are flagged
    on the rows above rather than quietly scored. Counts are from the
    fetch date and drift afterwards.</p>
  </div>
  {sib}
</section>

<footer>
  {html.escape(display_name)} · {total:,} comments about the car ·
  fetched {html.escape(meta.get('fetched_on', ''))}<br>
  <a href="/{html.escape(subject)}/">The full analysis</a> ·
  <a href="/{html.escape(subject)}/sources.html">Every quote with its permalink</a> ·
  <a href="/compare/">Compared</a> ·
  <a href="/">All analyses</a><br>
  Comment authors are not named. Spotted an error?
  <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
</footer>
</div></body></html>"""
