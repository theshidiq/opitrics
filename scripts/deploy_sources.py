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
from opitrics.render.provenance import CONTACT_EMAIL  # noqa: E402

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
footer{margin-top:48px;padding-top:20px;border-top:1px solid #BFBFBF;
 color:#5A5A5A;font-size:13.5px}
footer p{color:inherit;margin:0 0 10px;max-width:62ch}
footer p:last-child{margin-bottom:0}
footer a{color:#0546A8}
"""


def _page(title: str, body: str) -> str:
    """One shell for the small standalone pages."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{PAGE_CSS}</style></head><body><div class="wrap">
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
    return _page("Privacy — Opitrics", f"""
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

<footer><p><a href="/">Opitrics sources</a> · <a href="/terms">Terms</a></p></footer>""")


def terms_page() -> str:
    """Short, and mostly about the limits of what the numbers mean."""
    return _page("Terms — Opitrics", f"""
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

<footer><p><a href="/">Opitrics sources</a> · <a href="/privacy">Privacy</a></p></footer>""")


def index_page(entries: list[dict]) -> str:
    """A plain index so the repo root is not a 404."""
    import html

    rows = "\n".join(
        f'<li><a href="{html.escape(e["subject"])}/">{html.escape(e["name"])}</a>'
        f' <span>{e["comments"]:,} comments · {e["videos"]} videos'
        f' · {html.escape(e["updated"])}</span></li>'
        for e in entries
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opitrics — sources</title>
<style>{PAGE_CSS}</style></head><body><div class="wrap">
<h1>Opitrics — sources</h1>
<p>Every comment analysis published under this name has a page here listing
the videos it read and every comment it quoted, each linking to the original
on YouTube. Nothing asks to be believed; click a quote and check it.</p>
<ul>{rows}</ul>
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
        })
        print(f"  {GREEN}✓{RESET} {sp.subject}")

    (CHECKOUT / "index.html").write_text(index_page(entries), encoding="utf-8")

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


def _video_count(sp) -> int:
    from opitrics.ingest.db import Database

    db = Database(settings.database_path)
    return len(db.videos_for_subject(sp.subject))


if __name__ == "__main__":
    raise SystemExit(main())
