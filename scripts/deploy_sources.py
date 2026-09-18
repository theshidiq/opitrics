"""Publish sources pages to GitHub Pages.

    python scripts/deploy_sources.py --subject byd-racco
    python scripts/deploy_sources.py --all

Keeps a small public repo containing only the audit pages — the videos
read and every quote with a permalink. The pipeline itself stays
private; what is published is the evidence, which is the part a skeptic
needs and the part that cannot be faked.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.render.provenance import (  # noqa: E402
    CONTACT_EMAIL,
    site_nav,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

REPO = "opitrics-sources"
# Held outside the project so a `git status` here never shows it.
CHECKOUT = Path.home() / ".opitrics" / REPO

# The custom domain. GitHub Pages reads this from a CNAME file in the
# repo root, and treats its absence as "no custom domain" — so it is
# rewritten on every deploy rather than set once in the web UI. Delete
# the file through the UI and the next deploy silently puts it back;
# change the domain here and every published URL changes with it, which
# is exactly why this is a constant and not a flag.
DOMAIN = "opitrics.com"

# How many past deploys the public repo keeps.
#
# Every deploy rewrites all subject pages, and git stores each version
# forever — at 100 subjects a dozen rebuilds is ~645 MB of history for a
# 54 MB site, and it only grows. So history is capped rather than kept
# or discarded.
#
# Not zero, deliberately. That history is currently the only record of
# what a page said on a given date: `snapshot()` exists in paths.py but
# has never run, so nothing else preserves it. If someone disputes a
# published figure, "here is what the page said when you read it" is
# the answer, and a site whose product is checkability should be able
# to give it. Twenty deploys is roughly a quarter's worth at the
# current rate — long enough to cover any live dispute, bounded enough
# that the repo stays near the size of the site.
KEEP_DEPLOYS = 20

# The mark, as SVG: two bars each divided at a different point. Same
# geometry as brand/make_assets.py's `small` avatar variant — thicker
# bars, wider inset, tighter notch — because that variant was already
# tuned by looking at a 24px proof, and a favicon is that problem
# exactly. Do not substitute the large variant: at 16px its divisions
# close up and the mark flattens into two blue smudges.
#
# Neither fraction sits near 0.5. The asymmetry is the content — a
# comment section that divides evenly is the one result the data
# essentially never gives, and a centred mark would claim it.
#
# SVG rather than .ico so one file serves every size. On a 32-unit grid:
# inset 0.205 → x from 6.56 to 25.44; bar_h 0.215 → 6.88; gap 0.095 →
# 3.04; notch 0.024 → 0.77.
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" fill="#000000"/>
<rect x="6.56" y="7.54" width="12.34" height="6.88" fill="#FFFFFF"/>
<rect x="20.44" y="7.54" width="5.00" height="6.88" fill="#0546A8"/>
<rect x="6.56" y="17.58" width="7.16" height="6.88" fill="#FFFFFF"/>
<rect x="15.26" y="17.58" width="10.18" height="6.88" fill="#0546A8"/>
</svg>"""

# One manifest for the whole site. `display: browser` rather than
# standalone: this is pages to read, not an app, and a standalone
# install would strip the URL bar from a site whose entire argument is
# that you can check where you are and where a link goes.
WEBMANIFEST = {
    "name": "Opitrics — opinion metrics",
    "short_name": "Opitrics",
    "description": (
        "Analyses of what YouTube comment sections say about cars, with "
        "every quote linked to the original comment."
    ),
    "start_url": "/",
    "scope": "/",
    "display": "browser",
    "background_color": "#FFFFFF",
    "theme_color": "#FFFFFF",
    "icons": [
        {
            "src": "/icon.svg",
            "type": "image/svg+xml",
            "sizes": "any",
            "purpose": "any",
        }
    ],
}


def head_tags(title: str, description: str, path: str = "/") -> str:
    """Icon, manifest and social-card tags, identical on every page.

    `theme_color` is white to match the ground rather than the accent:
    a blue browser chrome above a white page reads as two surfaces, and
    the palette work exists so the site reads as one publication.
    """
    url = f"https://{DOMAIN}{path}"
    return f"""<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#FFFFFF">
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Opitrics">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">"""


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def gh_user() -> str:
    code, out = run(["gh", "api", "user", "--jq", ".login"])
    if code != 0:
        raise RuntimeError(f"gh not authenticated: {out}")
    return out.strip()


def ensure_repo(user: str) -> str:
    """Create the public repo and local checkout if they do not exist."""
    code, _ = run(["gh", "repo", "view", f"{user}/{REPO}"])
    if code != 0:
        print(f"{DIM}creating {user}/{REPO}…{RESET}")
        code, out = run([
            "gh", "repo", "create", REPO,
            "--public",
            "--description",
            "Source data behind Opitrics comment analyses — "
            "every quote links to the original comment.",
        ])
        if code != 0:
            raise RuntimeError(f"could not create repo: {out}")

    if not (CHECKOUT / ".git").exists():
        CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
        if CHECKOUT.exists():
            shutil.rmtree(CHECKOUT)
        print(f"{DIM}cloning into {CHECKOUT}…{RESET}")
        code, out = run([
            "gh", "repo", "clone", f"{user}/{REPO}", str(CHECKOUT),
        ])
        if code != 0:
            raise RuntimeError(f"clone failed: {out}")
    else:
        run(["git", "pull", "--rebase", "--autostash"], cwd=CHECKOUT)

    return f"{user}/{REPO}"


def enable_pages(slug: str) -> None:
    """Turn on Pages from the default branch, if it is not already on."""
    code, _ = run(["gh", "api", f"repos/{slug}/pages"])
    if code == 0:
        return
    print(f"{DIM}enabling GitHub Pages…{RESET}")
    code, out = run([
        "gh", "api", "-X", "POST", f"repos/{slug}/pages",
        "-f", "source[branch]=main",
        "-f", "source[path]=/",
    ])
    if code != 0:
        print(f"{YELLOW}could not enable Pages automatically:{RESET} {out[:160]}")
        print(f"{DIM}enable it once at github.com/{slug}/settings/pages{RESET}")


PAGE_CSS = """
/* Same palette as the audit pages and remotion/src/theme.ts — see the
   note on CSS in opitrics/render/provenance.py. */
body{background:#FFFFFF;color:#000000;margin:0;
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",
 "Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:56px 24px 80px}
h1{font-size:30px;margin:0 0 12px;letter-spacing:-.02em}
h2{font-size:13px;font-family:ui-monospace,monospace;letter-spacing:.12em;
 text-transform:uppercase;margin:38px 0 12px;padding-top:16px;
 border-top:1px solid #BFBFBF}
p{color:#3D3D3D;max-width:62ch}
a{color:#0546A8}
ul{list-style:none;padding:0;margin:32px 0 0;border-top:1px solid #BFBFBF}
li{padding:15px 0;border-bottom:1px solid #BFBFBF}
li:last-child{border-bottom:none}
li a{color:#0546A8;font-weight:600;font-size:18px;text-decoration:none}
li a:hover{text-decoration:underline}
li span{display:block;color:#5A5A5A;font-size:13px;
 font-family:ui-monospace,monospace;margin-top:4px}
ul.plain{border:0;margin:0 0 16px;padding:0}
ul.plain li{border:0;padding:3px 0 3px 18px;position:relative;
 color:#3D3D3D;max-width:62ch}
ul.plain li:before{content:"—";position:absolute;left:0;color:#5A5A5A}
.lede{font-size:17px}
.updated{font-family:ui-monospace,monospace;font-size:12px;color:#5A5A5A;
 letter-spacing:.06em;text-transform:uppercase}

/* Masthead. Mirrors the .sitenav rules in opitrics/render/provenance.py
   so every page on the domain carries the same one — these pages are
   built here and the subject reports are built there, but a visitor
   crossing between them should not notice a seam. */
.sitenav{display:flex;align-items:baseline;gap:8px 16px;flex-wrap:wrap;
 padding-bottom:13px;margin-bottom:22px;border-bottom:1px solid #BFBFBF}
.sitenav .brand{font-family:ui-monospace,monospace;font-size:12px;
 letter-spacing:.16em;text-transform:uppercase;color:#000000;
 text-decoration:none;font-weight:600}
.sitenav .brand:hover{color:#0546A8}
.sitenav nav{display:flex;gap:14px;flex-wrap:wrap;margin-left:auto}
.sitenav nav a{font-size:13.5px;color:#5A5A5A;text-decoration:none}
.sitenav nav a:hover{color:#0546A8}
.sitenav nav a[aria-current]{color:#000000;font-weight:600}
@media(max-width:560px){.sitenav nav{margin-left:0;width:100%}}

/* ── comparison ─────────────────────────────────────────────
   The four-way table scrolls inside its own box rather than
   widening the page: five columns of figures cannot compress to
   390px without the numbers wrapping mid-digit. */
.tablewrap{overflow-x:auto;margin:22px 0;border:1px solid #BFBFBF}
table.cmp{width:100%;min-width:560px;border-collapse:collapse;
 font-size:14.5px;background:#FFFFFF}
table.cmp th{text-align:right;font-family:ui-monospace,monospace;
 font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
 color:#5A5A5A;font-weight:400;padding:13px 14px 10px;
 border-bottom:1px solid #BFBFBF;white-space:nowrap}
table.cmp th:first-child{text-align:left}
table.cmp td{padding:12px 14px;border-bottom:1px solid #E0E0E0;
 color:#000000;text-align:right;font-family:ui-monospace,monospace;
 font-variant-numeric:tabular-nums;white-space:nowrap}
table.cmp td:first-child{text-align:left;font-family:inherit;
 color:#3D3D3D}
table.cmp tr:last-child td{border-bottom:none}
table.cmp td a{color:#0546A8;text-decoration:none;font-weight:600}
table.cmp td a:hover{text-decoration:underline}
table.cmp .out{font-weight:700}
table.cmp tbody tr:hover td{background:#F4F4F4}
figure.card{margin:26px 0 0}
figure.card img{display:block;width:100%;height:auto;
 border:1px solid #BFBFBF}
figure.card figcaption{font-size:13.5px;color:#5A5A5A;margin-top:9px;
 max-width:70ch}
figure.card figcaption a{color:#0546A8}
.callout{border-left:2px solid #0546A8;background:#F1F5FB;
 padding:15px 19px;margin:24px 0;font-size:15px;color:#3D3D3D}
.callout b{color:#000000}
.callout.warn{border-left-color:#8A5A00;background:#FBF6EE}
footer{margin-top:48px;padding-top:20px;border-top:1px solid #BFBFBF;
 color:#5A5A5A;font-size:13.5px}
footer p{color:inherit;margin:0 0 10px;max-width:62ch}
footer p:last-child{margin-bottom:0}
footer a{color:#0546A8}
"""


def _page(title: str, head: str, body: str, here: str = "") -> str:
    """One shell for the small standalone pages.

    `here` marks the current section in the masthead, so a visitor can
    see where they are rather than only where they can go.
    """
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{head}
<style>{PAGE_CSS}</style></head><body><div class="wrap">
{site_nav(here)}
{body}
</div></body></html>"""


def privacy_page() -> str:
    """What the site collects, which is nothing it could avoid collecting.

    Every sentence here has to survive someone checking it. The pages are
    static HTML with no script tag, so claims about cookies and analytics
    are verifiable with view-source; the server log paragraph is the one
    thing a visitor cannot see, so it is stated plainly rather than
    rounded down to "we collect nothing".
    """
    return _page("Privacy — Opitrics", head_tags(
        "Privacy — Opitrics",
        "This site sets no cookies, runs no analytics and has no script "
        "tag on any page.",
        "/privacy/",
    ), f"""
<h1>Privacy</h1>
<p class="updated">Last updated {datetime.now().strftime('%-d %B %Y')}</p>
<p class="lede">This site collects nothing about you. That is not a
policy position so much as a description of how it is built: these are
static HTML files, and there is no code on them that could collect
anything.</p>

<h2>What this site does not do</h2>
<ul class="plain">
<li>No cookies are set.</li>
<li>No analytics, tracking pixels, or third-party scripts. There is no
<code>&lt;script&gt;</code> tag on any page — you can check with
view-source.</li>
<li>No accounts, logins, forms, or newsletter signups.</li>
<li>Nothing is sold or shared with anyone, because nothing is gathered.</li>
</ul>

<h2>What is unavoidable</h2>
<p>The pages are hosted on GitHub Pages. Like any web server, GitHub's
receives your IP address and browser user-agent in order to send you the
page, and may log it. That is GitHub's processing, not ours — we have no
access to those logs and cannot identify visitors. See
<a href="https://docs.github.com/site-policy/privacy-policies/github-privacy-statement"
rel="noopener">GitHub's privacy statement</a>.</p>
<p>Charts and images are embedded directly in each page rather than
loaded from elsewhere, so viewing a page makes no request to any other
company.</p>

<h2>If you follow a link</h2>
<p>Quotes link to the original comments on YouTube. Opening one takes
you to Google's site, where Google's privacy terms apply. Nothing is
sent to them until you click.</p>

<h2>Comments quoted on this site</h2>
<p>The analyses quote public YouTube comments. <b>Author names and
handles are withheld from every page</b> — the permalink is what makes a
quote checkable, and naming the commenter would expose a private person
to an audience they did not ask for.</p>
<p>If a comment of yours is quoted here and you would like it removed,
email <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> with the link
and it will be taken down. No justification is needed.</p>

<h2>Contact</h2>
<p><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>

<footer><p><a href="/">Opitrics sources</a> · <a href="/terms">Terms</a></p></footer>""", here="privacy")


def terms_page() -> str:
    """Short, and mostly about the limits of what the numbers mean."""
    return _page("Terms — Opitrics", head_tags(
        "Terms — Opitrics",
        "What the numbers here mean and do not mean, how to report an "
        "error, and the terms for reusing a figure.",
        "/terms/",
    ), f"""
<h1>Terms of use</h1>
<p class="updated">Last updated {datetime.now().strftime('%-d %B %Y')}</p>
<p class="lede">This site publishes analyses of public YouTube comment
sections, along with the evidence behind them. It is free to read and
there is nothing to sign up for.</p>

<h2>What the numbers mean, and do not</h2>
<p>Every figure here describes <b>what a comment section said</b>. People
who comment are not people who buy, and they skew toward enthusiasts and
toward strong opinions. These analyses are a proxy for public perception
and a poor proxy for sales, market share, or product quality.</p>
<p>Sentiment is scored by machine on a sample of each group of comments.
Sarcasm detection is weak, particularly in Japanese; groups where that
risk is high are flagged on the page rather than presented as settled.
Treat the findings as a measurement with known error, not a verdict.</p>

<h2>Accuracy, and corrections</h2>
<p>Every quote published here links to the original comment so you can
check it yourself. If you find something wrong — a miscount, a
mistranslation, a quote that does not match its source — email
<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>. Corrections are
made to the page.</p>
<p>Like counts and comment counts are recorded at the time of fetching
and drift afterwards. The fetch date is shown on every analysis.</p>

<h2>Using this material</h2>
<p>You may quote and link to these analyses freely, including
commercially, provided you attribute Opitrics and link to the page you
took the figure from. Do not present a number from here as your own
research, and do not republish a page wholesale.</p>
<p>Quoted comments remain the words of the people who wrote them and are
reproduced here for commentary and analysis.</p>

<h2>Trade marks</h2>
<p>Vehicle and company names are the trade marks of their owners. This
site is not affiliated with, endorsed by, or speaking for any
manufacturer, publication, or the channels whose comment sections it
reads.</p>

<h2>No warranty</h2>
<p>The analyses are provided as they are, without warranty. Decisions
made on the basis of them are yours.</p>

<footer><p><a href="/">Opitrics sources</a> · <a href="/privacy">Privacy</a></p></footer>""", here="terms")


def compare_page(rows: list[dict], cards: list[dict]) -> str:
    """The comparison, with every figure linking to the corpus behind it.

    This page exists because the cards promise something the site could
    not deliver. Each card's footer reads "every number links to the
    comments it came from" — and until there was a page around them,
    those numbers linked nowhere. A figure here is a link to the subject
    page that produced it, which is the whole claim.

    Shares, never counts, and the reason is louder here than on a card:
    the four corpora differ elevenfold, so a table of totals would rank
    these cars by how much they are watched.
    """
    import html

    if not rows:
        return ""

    # Widest corpus against narrowest — stated rather than left for a
    # reader to work out, because it is the caveat that governs every
    # figure on the page.
    sizes = [r["clustered"] for r in rows]
    ratio = max(sizes) / max(min(sizes), 1)

    metric_cols = [
        ("about_car", "about the car"),
        ("meta", "arguing"),
        ("positive", "reads positive"),
        ("unscorable", "unscorable"),
    ]

    # The outlier gets marked per column, but only where it is actually
    # extreme rather than merely first in sort order.
    def is_outlier(key: str, value: float) -> bool:
        vals = sorted(r[key] for r in rows)
        if len(vals) < 3:
            return False
        rest = [v for v in vals if v != value]
        if not rest:
            return False
        # Extreme at either end, and clear of the next value by more
        # than the spread among the remaining cars.
        spread = max(rest) - min(rest)
        return (
            value == vals[-1] and value - vals[-2] > spread
        ) or (
            value == vals[0] and vals[1] - value > spread
        )

    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in metric_cols)
    body = ""
    for r in rows:
        cells = ""
        for key, _ in metric_cols:
            cls = ' class="out"' if is_outlier(key, r[key]) else ""
            cells += f"<td{cls}>{r[key]:.0f}%</td>"
        body += (
            f'<tr><td><a href="/{html.escape(r["subject"])}/">'
            f'{html.escape(r["name"])}</a></td>'
            f'<td>{r["clustered"]:,}</td>{cells}</tr>\n'
        )

    card_figures = "\n".join(
        f'''<figure class="card">
  <img src="{html.escape(c["file"])}" alt="{html.escape(c["alt"])}" loading="lazy">
  <figcaption>{html.escape(c["caption"])}
    Check either corpus: <a href="/{html.escape(c["left"])}/">{html.escape(c["left_name"])}</a>
    · <a href="/{html.escape(c["right"])}/">{html.escape(c["right_name"])}</a></figcaption>
</figure>'''
        for c in cards
    )

    ratio_note = (
        f'<div class="callout warn"><b>The corpora are not the same '
        f'size.</b> The largest is {ratio:.0f}× the smallest, so every '
        f'figure here is a share of that car\'s own comments. A table of '
        f'totals would rank these cars by how much they are watched, '
        f'which is not what any of them measures.</div>'
        if ratio > 3 else ""
    )

    return _page(
        "Compared — Opitrics",
        head_tags(
            "One Chinese car in a Japanese segment",
            "Four kei-car comment sections compared by share: how much is "
            "about the car, how much is arguing, and how much reads positive.",
            "/compare/",
        ),
        f"""
<h1>One Chinese car in a Japanese segment</h1>
<p class="updated">{len(rows)} corpora · {sum(sizes):,} comments analysed</p>
<p class="lede">Four kei cars, four comment sections, the same four
questions asked of each. The BYD Racco sits at the extreme of all four,
and on two of them it is clear of the other three by more than they
differ from each other. It is also the only car here that is not
Japanese.</p>

{ratio_note}

<h2>The four, side by side</h2>
<p>Every figure is a share of that car's own clustered comments. Follow a
car's name to the analysis and the comments behind it.</p>
<div class="tablewrap">
<table class="cmp">
  <thead><tr><th>car</th><th>comments</th>{head}</tr></thead>
  <tbody>
{body}  </tbody>
</table>
</div>
<p style="font-size:13.5px;color:#5A5A5A">Bold marks a car that sits
clear of the other three on that measure — extreme, not merely highest.
<b>About the car</b> is the share on the vehicle rather than the video or
its presenter. <b>Arguing</b> is the remainder. <b>Reads positive</b> and
<b>unscorable</b> are shares of comments in themes scored positive, and
in themes flagged too sarcastic to score.</p>

<h2>What the split says</h2>
<p>Three of these cars produce a comment section about a car. The fourth
produces an argument about where it was built. A fifth of the Racco's
comments are not about the vehicle at all, and a quarter are too
sarcastic to score — that sarcasm share is ten times the N-Box's, and
the positive share is under a third of it.</p>
<p>The two clear results are sentiment, not subject matter. On how much
of the conversation is about the car, the Racco leads but the three
Japanese cars differ among themselves by as much, so that gap is not
doing the work. What separates the Racco is <em>how</em> its comment
section talks, not what it talks about.</p>
<p>That is the finding no single corpus gives you: not that the Racco is
disliked, but that it is <em>argued about</em> in a way its rivals are
not.</p>

<h2>Each pair in full</h2>
{card_figures}

<h2>What this does not measure</h2>
<div class="callout">
<b>These are comment sections, not buyers.</b> People who comment are not
people who buy, and they skew toward enthusiasts and strong opinions.
Nothing here says anything about sales, demand, or which car is better.
<br><br>
<b>There is no single "how positive" number</b>, deliberately. Average
polarity across a corpus mixes themes about the car with themes about
the brand's nationality, and these four differ in exactly that mix — so
one warmth figure would report a car as better liked when it is only
less argued about.
<br><br>
<b>Sarcasm detection is weak, particularly in Japanese.</b> The
unscorable column is that uncertainty made visible rather than hidden
inside another number.
</div>

<footer><p><a href="/">All analyses</a> · <a href="/terms">Terms</a> ·
<a href="/privacy">Privacy</a> ·
<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
<p>Comment authors are not named. The permalink is what makes a quote
checkable, so the handle is withheld.</p></footer>""",
        here="compare",
    )


def index_page(entries: list[dict]) -> str:
    """A plain index so the repo root is not a 404."""
    import html

    rows = "\n".join(
        f'<li><a href="{html.escape(e["subject"])}/">{html.escape(e["name"])}</a>'
        f' <span>{e["comments"]:,} comments · {e["videos"]} videos'
        f' · {html.escape(e["updated"])}</span></li>'
        for e in entries
    )
    compare_link = (
        '<p style="margin-top:26px"><a href="/compare/" '
        'style="font-weight:600">Compare all '
        f'{len(entries)} side by side →</a><br>'
        '<span style="color:#5A5A5A;font-size:13.5px">The same four '
        'questions asked of each corpus, as shares.</span></p>'
        if len(entries) > 1 else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opitrics — sources</title>
{head_tags(
    "Opitrics — comment analysis with the receipts",
    "Analyses of what YouTube comment sections say about cars, with every "
    "quote linked to the original comment.",
    "/",
)}
<style>{PAGE_CSS}</style></head><body><div class="wrap">
{site_nav("index")}
<h1>Opitrics — sources</h1>
<p>Every comment analysis published under this name has a page here listing
the videos it read and every comment it quoted, each linking to the original
on YouTube. Nothing asks to be believed; click a quote and check it.</p>
<ul>{rows}</ul>
{compare_link}
<footer><p>Comment authors are not named. The permalink is what makes a quote
checkable, so the handle is withheld.</p>
<p>Opitrics — opinion metrics. It reads what people say and counts it. It does
not survey buyers or measure sales, and a comment section is not a sample of
either.</p>
<p><a href="/terms">Terms</a> · <a href="/privacy">Privacy</a> ·
<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p></footer>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", help="one subject to publish")
    ap.add_argument("--all", action="store_true", help="publish every subject with a sources page")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.subject and not args.all:
        ap.error("give --subject or --all")

    workspace = settings.workspace
    subjects = (
        workspace.list_subjects()
        if args.all
        else [workspace.subject(args.subject)]
    )
    ready = [s for s in subjects if (s.content_dir / "sources.html").exists()]

    if not ready:
        print(f"\n{YELLOW}No sources pages found.{RESET}")
        print(f"{DIM}Run: python scripts/sources.py --subject <name>{RESET}\n")
        return 1

    try:
        user = gh_user()
    except RuntimeError as exc:
        print(f"\n{RED}{exc}{RESET}")
        print(f"{DIM}Run `gh auth login` first.{RESET}\n")
        return 1

    print(f"\n{BOLD}Publishing {len(ready)} sources page(s){RESET} "
          f"{DIM}as @{user}{RESET}")

    if args.dry_run:
        for sp in ready:
            print(f"  {DIM}{sp.subject} → https://{DOMAIN}/{sp.subject}/{RESET}")
        print(f"\n{YELLOW}Dry run — nothing pushed.{RESET}\n")
        return 0

    try:
        slug = ensure_repo(user)
    except RuntimeError as exc:
        print(f"\n{RED}{exc}{RESET}\n")
        return 1

    # ── copy pages in ───────────────────────────────────────
    entries: list[dict] = []
    for sp in ready:
        target = CHECKOUT / sp.subject
        target.mkdir(parents=True, exist_ok=True)

        # The report is the front door; the audit page sits behind it at
        # a stable path. `<subject>/` has been published as the audit
        # page, so it keeps resolving — the report link is what changes,
        # and the audit page's own URL never moves again.
        report = sp.content_dir / "report-public.html"
        shutil.copy2(sp.content_dir / "sources.html", target / "sources.html")

        # /<subject>/brief/ rather than brief.html, for the same reason
        # /terms is a directory: a clean URL that can be pasted anywhere
        # and will not need changing.
        brief = sp.content_dir / "brief.html"
        if brief.exists():
            (target / "brief").mkdir(parents=True, exist_ok=True)
            shutil.copy2(brief, target / "brief" / "index.html")
        if report.exists():
            shutil.copy2(report, target / "index.html")
        else:
            # No report built: the audit page stays the landing page
            # rather than leaving the subject with no index at all.
            shutil.copy2(sp.content_dir / "sources.html", target / "index.html")

        analysis = {}
        if sp.analysis.exists():
            analysis = json.loads(sp.analysis.read_text(encoding="utf-8"))
        totals = analysis.get("totals", {})

        entries.append({
            "subject": sp.subject,
            "name": sp.display_name,
            "comments": totals.get("clustered", 0),
            "videos": _video_count(sp),
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "analysis": analysis,
            "content_dir": sp.content_dir,
        })
        print(f"  {GREEN}✓{RESET} {sp.subject}")

    (CHECKOUT / "index.html").write_text(index_page(entries), encoding="utf-8")

    # ── the comparison ──────────────────────────────────────
    # Figures come from compare.py's own metrics(), not from a table
    # retyped here: the page and the cards must not be able to disagree,
    # and a card that contradicts the table beside it would discredit
    # both on the one page whose subject is a comparison.
    cmp_rows, cmp_cards = _comparison(entries)
    if cmp_rows:
        page_dir = CHECKOUT / "compare"
        page_dir.mkdir(parents=True, exist_ok=True)
        for card in cmp_cards:
            shutil.copy2(card.pop("src"), page_dir / card["file"])
        (page_dir / "index.html").write_text(
            compare_page(cmp_rows, cmp_cards), encoding="utf-8"
        )
        print(f"  {GREEN}✓{RESET} compare "
              f"{DIM}({len(cmp_rows)} corpora, {len(cmp_cards)} cards){RESET}")

    # /terms and /privacy rather than /terms.html — a directory with an
    # index.html gives the extensionless URL platforms ask for, and the
    # URL is what gets pasted into a platform's app settings, so it
    # should not need changing later.
    for name, builder in (("terms", terms_page), ("privacy", privacy_page)):
        page_dir = CHECKOUT / name
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(builder(), encoding="utf-8")
    # Skip Jekyll — it would try to process these as templates.
    (CHECKOUT / ".nojekyll").write_text("", encoding="utf-8")
    (CHECKOUT / "CNAME").write_text(f"{DOMAIN}\n", encoding="utf-8")
    (CHECKOUT / "icon.svg").write_text(FAVICON_SVG + "\n", encoding="utf-8")
    (CHECKOUT / "site.webmanifest").write_text(
        json.dumps(WEBMANIFEST, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ── commit and push ─────────────────────────────────────
    run(["git", "add", "-A"], cwd=CHECKOUT)
    code, out = run(["git", "diff", "--cached", "--quiet"], cwd=CHECKOUT)
    if code == 0:
        print(f"\n{DIM}nothing changed since the last publish{RESET}")
    else:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        run(["git", "commit", "-m", f"sources: {', '.join(e['subject'] for e in entries)} ({stamp})"],
            cwd=CHECKOUT)
        code, out = run(["git", "push", "-u", "origin", "HEAD"], cwd=CHECKOUT)
        if code != 0:
            print(f"\n{RED}push failed:{RESET} {out[:200]}\n")
            return 1
        _trim_history()

    enable_pages(slug)

    print(f"\n{GREEN}{BOLD}Published{RESET}")
    for e in entries:
        print(f"  https://{DOMAIN}/{e['subject']}/")
    print(f"\n{DIM}Pages can take a minute to build on first publish.{RESET}")
    print(f"{DIM}Then rebuild threads with the URL:{RESET}")
    first = entries[0]
    print(f"  python scripts/thread.py --subject {first['subject']} --all \\")
    print(f"    --sources-url https://{DOMAIN}/{first['subject']}/\n")
    return 0


def _comparison(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rows for the four-way table, and whichever pair cards exist.

    Metrics come from `scripts/compare.py` so the page cannot disagree
    with the cards it shows. Cards are discovered on disk rather than
    listed here: whichever pairs have been rendered get a figure, and a
    pair nobody built simply does not appear.
    """
    from importlib.machinery import SourceFileLoader

    try:
        cmp_mod = SourceFileLoader(
            "_opitrics_compare",
            str(Path(__file__).resolve().parent / "compare.py"),
        ).load_module()
    except Exception as exc:
        print(f"  {YELLOW}comparison skipped:{RESET} {exc}")
        return [], []

    by_subject = {e["subject"]: e for e in entries}
    rows: list[dict] = []
    for e in entries:
        if not e.get("analysis", {}).get("clusters"):
            continue
        try:
            m = cmp_mod.metrics(e["analysis"])
        except (KeyError, ZeroDivisionError) as exc:
            print(f"  {YELLOW}no metrics for {e['subject']}:{RESET} {exc}")
            continue
        rows.append({"subject": e["subject"], "name": e["name"], **m})

    if len(rows) < 2:
        return [], []

    # Largest corpus first: the outlier leads, and the reader meets the
    # car the comparison is about before the ones it is measured against.
    rows.sort(key=lambda r: -r["clustered"])

    cards: list[dict] = []
    for e in entries:
        for path in sorted(Path(e["content_dir"]).glob("compare-*-vs-*.png")):
            stem = path.stem[len("compare-"):]
            if "-vs-" not in stem:
                continue
            left, right = stem.split("-vs-", 1)
            if left not in by_subject or right not in by_subject:
                continue
            ln = by_subject[left]["name"]
            rn = by_subject[right]["name"]
            cards.append({
                "src": path,
                "file": path.name,
                "left": left,
                "right": right,
                "left_name": ln,
                "right_name": rn,
                "alt": f"{ln} compared with {rn} across four shares",
                "caption": f"{ln} against {rn}.",
            })

    # One card per pair, in table order, so the figures follow the rows.
    order = {r["subject"]: i for i, r in enumerate(rows)}
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for c in sorted(cards, key=lambda c: order.get(c["right"], 99)):
        key = tuple(sorted((c["left"], c["right"])))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    return rows, unique


def _trim_history() -> None:
    """Keep the last KEEP_DEPLOYS commits, drop the rest. Never raises.

    The site is already published when this runs, so any failure here
    should cost history and nothing else. The body is wrapped rather
    than only checking return codes, because `run` shells out and can
    raise on a missing directory or a missing git — and a crash after a
    successful push would report failure for a deploy that worked.
    """
    try:
        _trim_history_inner()
    except Exception as exc:  # noqa: BLE001 - housekeeping, never fatal
        print(f"  {YELLOW}history trim skipped{RESET} {DIM}({exc}){RESET}")


def _trim_history_inner() -> None:
    """Keep the last KEEP_DEPLOYS commits, drop the rest.

    Runs AFTER a successful push, never before: the published site is
    already live and correct at this point, so a failure here costs
    some history and nothing else. Every step is checked and the
    function returns quietly rather than raising — a repo-size
    housekeeping task must not be able to break publishing.

    The mechanism is a fresh root commit containing the state
    KEEP_DEPLOYS ago, with the recent commits replayed on top, then a
    force push. That is a rewrite of the public repo's history, which
    is only acceptable because nobody clones it — it is a publishing
    target, not a codebase, and the pipeline that generates it lives in
    the private repo.
    """
    if not (CHECKOUT / ".git").exists():
        return
    code, out = run(["git", "rev-list", "--count", "HEAD"], cwd=CHECKOUT)
    if code != 0 or not out.strip().isdigit():
        return
    total = int(out.strip())
    if total <= KEEP_DEPLOYS:
        return

    # The commit that will become the new root, and its tree.
    code, base = run(
        ["git", "rev-parse", f"HEAD~{KEEP_DEPLOYS - 1}"], cwd=CHECKOUT
    )
    if code != 0:
        return
    base = base.strip()

    code, _ = run(["git", "checkout", "--detach", base], cwd=CHECKOUT)
    if code != 0:
        return

    stamp = datetime.now().strftime("%Y-%m-%d")
    code, new_root = run(
        [
            "git", "commit-tree", f"{base}^{{tree}}",
            "-m",
            f"sources: state as of this point ({stamp})\n\n"
            f"History before this was trimmed to keep the public repo "
            f"near the size of the site it publishes. The last "
            f"{KEEP_DEPLOYS} deploys are preserved above; the pipeline "
            f"that generated every page is in the private repo.",
        ],
        cwd=CHECKOUT,
    )
    if code != 0 or not new_root.strip():
        run(["git", "checkout", "-f", "main"], cwd=CHECKOUT)
        return
    new_root = new_root.strip()

    # Replay the kept commits on top of the new root.
    code, _ = run(
        ["git", "rebase", "--onto", new_root, base, "main"], cwd=CHECKOUT
    )
    if code != 0:
        run(["git", "rebase", "--abort"], cwd=CHECKOUT)
        run(["git", "checkout", "-f", "main"], cwd=CHECKOUT)
        return

    # The published tree must be byte-identical to what was just
    # pushed. If the rebase changed anything, abandon the trim rather
    # than force-push a different site.
    code, diff = run(["git", "diff", "origin/main", "--stat"], cwd=CHECKOUT)
    if code != 0 or diff.strip():
        print(f"  {YELLOW}history trim skipped{RESET} "
              f"{DIM}(tree would change){RESET}")
        run(["git", "fetch", "origin", "main"], cwd=CHECKOUT)
        run(["git", "reset", "--hard", "origin/main"], cwd=CHECKOUT)
        return

    code, out = run(
        ["git", "push", "--force-with-lease", "origin", "main"], cwd=CHECKOUT
    )
    if code != 0:
        print(f"  {YELLOW}history trim not pushed{RESET} {DIM}{out[:90]}{RESET}")
        run(["git", "fetch", "origin", "main"], cwd=CHECKOUT)
        run(["git", "reset", "--hard", "origin/main"], cwd=CHECKOUT)
        return

    run(["git", "reflog", "expire", "--expire=now", "--all"], cwd=CHECKOUT)
    run(["git", "gc", "--prune=now", "--quiet"], cwd=CHECKOUT)
    print(f"  {DIM}history trimmed to {KEEP_DEPLOYS} deploys "
          f"(was {total}){RESET}")


def _video_count(sp) -> int:
    from opitrics.ingest.db import Database

    db = Database(settings.database_path)
    return len(db.videos_for_subject(sp.subject))


if __name__ == "__main__":
    raise SystemExit(main())
