"""Build the audit page — every quote linked to its original comment.

    python scripts/sources.py --subject byd-racco

Publish this alongside a thread. When someone asks whether the analysis
is real, the answer is a link they can check rather than an assurance
they have to accept.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.ingest.db import Database  # noqa: E402
from opitrics.render.provenance import (  # noqa: E402
    attach_sources,
    build_audit_page,
    build_report_page,
    index_corpus,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument(
        "--sources-url",
        default="",
        help="public URL of the audit page, linked from the report",
    )
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    if not paths.analysis.exists():
        print(f"\n{paths.analysis} not found — run scripts/analyze.py first.\n")
        return 1

    analysis = json.loads(paths.analysis.read_text(encoding="utf-8"))
    db = Database(settings.database_path)
    rows = db.comments_for_subject(args.subject)

    print(f"\n{BOLD}Attaching sources{RESET}")
    index = index_corpus(rows)
    matched = attach_sources(analysis, index)

    total_quotes = sum(len(c.get("quotes", [])) for c in analysis["clusters"])
    rate = matched / max(total_quotes, 1)
    colour = GREEN if rate > 0.95 else YELLOW
    print(f"  {colour}{matched}/{total_quotes}{RESET} quotes linked "
          f"{DIM}({rate:.0%}){RESET}")

    # Persist so charts, threads and the report can carry links too.
    paths.analysis.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    videos = db.videos_for_subject(args.subject)
    video_data = [
        {
            "video_id": v["video_id"],
            "title": v["title"],
            "channel_title": v["channel_title"],
            "comments": db.comment_count(v["video_id"]),
        }
        for v in videos
    ]
    video_data.sort(key=lambda v: -v["comments"])

    fetched = min((v["fetched_at"] for v in videos), default="")[:10]

    # Every visitor arrives from a thread or a video description, so they
    # land on a subject page rather than the index. Without these links
    # the page is a dead end: no route to the comparison, the other cars,
    # or the audit page the post promised. Only subjects with an analysis
    # are listed, since a link to a subject with no page would 404.
    siblings = []
    for sp in settings.workspace.list_subjects():
        if sp.subject == args.subject or not sp.analysis.exists():
            continue
        try:
            sib = json.loads(sp.analysis.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        siblings.append({
            "subject": sp.subject,
            "name": sp.display_name,
            "comments": sib.get("totals", {}).get("clustered", 0),
        })
    siblings.sort(key=lambda s: -s["comments"])

    html = build_audit_page(
        subject=args.subject,
        display_name=paths.display_name,
        analysis=analysis,
        videos=video_data,
        meta={"raw": len(rows), "fetched_on": fetched},
        siblings=siblings,
    )

    out = paths.content_dir / "sources.html"
    out.write_text(html, encoding="utf-8")

    # The report is the front door; the audit page is the receipt behind
    # it. Charts are rendered in the published palette, not the internal
    # dark or warm ones — see WEB in opitrics/render/charts.py.
    from opitrics.render import charts as charts_mod  # noqa: E402

    chart_dir = paths.root / "charts"
    chart_paths: dict = {}
    try:
        charts_mod.render_all(analysis, chart_dir, modes=["web"])
        chart_paths = {
            name: chart_dir / f"{name}.png"
            for name in ("composition", "aspects", "volume-intensity")
        }
        missing = [n for n, p in chart_paths.items() if not p.exists()]
        if missing:
            print(f"  {YELLOW}charts missing:{RESET} {', '.join(missing)}")
    except Exception as exc:  # a chart failure must not lose the report
        print(f"  {YELLOW}charts skipped:{RESET} {exc}")

    # Manufacturer figures, if someone has entered any. Unsourced rows
    # are dropped by `load` with a warning rather than reaching a page —
    # see opitrics/analyze/specs.py.
    from opitrics.analyze import specs as specs_mod  # noqa: E402

    spec_rows = specs_mod.load(paths.specs)
    if spec_rows:
        discussed, total = specs_mod.coverage(spec_rows, analysis["clusters"])
        colour = GREEN if discussed else YELLOW
        print(f"  {colour}{discussed}/{total}{RESET} specs raised by "
              f"commenters {DIM}(the rest say so on the page){RESET}")

    report_html = build_report_page(
        subject=args.subject,
        display_name=paths.display_name,
        analysis=analysis,
        videos=video_data,
        meta={"raw": len(rows), "fetched_on": fetched},
        charts=chart_paths,
        sources_url=args.sources_url or "sources.html",
        specs=spec_rows,
        siblings=siblings,
    )
    report_out = paths.content_dir / "report-public.html"
    report_out.write_text(report_html, encoding="utf-8")

    print(f"\n{GREEN}{BOLD}Pages ready{RESET}")
    print(f"  report  {report_out}")
    print(f"  sources {out}")
    print(f"{DIM}publish these with your threads — they are what makes the "
          f"analysis checkable{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
