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
<style>
/* Same palette as the audit pages and remotion/src/theme.ts — see the
   note on CSS in opitrics/render/provenance.py. */
body{{background:#FFFFFF;color:#000000;margin:0;
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.wrap{{max-width:720px;margin:0 auto;padding:56px 24px 80px}}
h1{{font-size:30px;margin:0 0 12px;letter-spacing:-.02em}}
p{{color:#3D3D3D;max-width:62ch}}
ul{{list-style:none;padding:0;margin:32px 0 0;border-top:1px solid #BFBFBF}}
li{{padding:15px 0;border-bottom:1px solid #BFBFBF}}
li:last-child{{border-bottom:none}}
li a{{color:#0546A8;font-weight:600;font-size:18px;text-decoration:none}}
li a:hover{{text-decoration:underline}}
li span{{display:block;color:#5A5A5A;font-size:13px;
 font-family:ui-monospace,monospace;margin-top:4px}}
footer{{margin-top:48px;padding-top:20px;border-top:1px solid #BFBFBF;
 color:#5A5A5A;font-size:13.5px}}
</style></head><body><div class="wrap">
<h1>Opitrics — sources</h1>
<p>Every comment analysis published under this name has a page here listing
the videos it read and every comment it quoted, each linking to the original
on YouTube. Nothing asks to be believed; click a quote and check it.</p>
<ul>{rows}</ul>
<footer>Comment authors are not named. The permalink is what makes a quote
checkable, so the handle is withheld.</footer>
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
