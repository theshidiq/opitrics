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
    html = build_audit_page(
        subject=args.subject,
        display_name=paths.display_name,
        analysis=analysis,
        videos=video_data,
        meta={"raw": len(rows), "fetched_on": fetched},
    )

    out = paths.content_dir / "sources.html"
    out.write_text(html, encoding="utf-8")

    print(f"\n{GREEN}{BOLD}Audit page ready{RESET}  {out}")
    print(f"{DIM}publish this with your threads — it is what makes the "
          f"analysis checkable{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
