"""Compare two or three cars from corpora already analysed.

    python scripts/compare.py --subjects byd-racco suzuki-e-sky
    python scripts/compare.py --subjects byd-racco suzuki-e-sky --card-only

Reads each subject's analysis.json and renders one comparison card plus
the figures behind it. Runs no LLM and spends no quota: everything here
is arithmetic on analyses that already exist.

Every metric is a SHARE, never a raw count. The corpora are not the
same size — 15,950 comments against 2,948 — so comparing counts
compares audience, not opinion. A card saying "681 vs 105" would read
as the Racco being more criticised when it is only more watched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.render import cards as cards_mod  # noqa: E402

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def load(subject: str) -> tuple[str, dict]:
    paths = settings.workspace.subject(subject)
    if not paths.analysis.exists():
        raise SystemExit(
            f"\n{paths.analysis} not found — run the pipeline for "
            f"{subject} first.\n"
        )
    return paths.display_name, json.loads(
        paths.analysis.read_text(encoding="utf-8")
    )


def metrics(analysis: dict) -> dict:
    """The comparable figures, all shares or rates."""
    totals = analysis["totals"]
    clustered = max(totals.get("clustered", 0), 1)
    clusters = analysis.get("clusters", [])

    def share(keep) -> float:
        return 100 * sum(c["size"] for c in clusters if keep(c)) / clustered

    positive = share(
        lambda c: c["sentiment"]["polarity"] > 0.15 and not c.get("sarcasm_risk")
    )
    negative = share(
        lambda c: c["sentiment"]["polarity"] < -0.15 and not c.get("sarcasm_risk")
    )
    unscorable = share(lambda c: c.get("sarcasm_risk"))

    return {
        "clustered": clustered,
        "about_car": 100 * totals.get("car", 0) / clustered,
        "meta": 100 * totals.get("meta", 0) / clustered,
        "positive": positive,
        "negative": negative,
        "unscorable": unscorable,
    }


def rows_for(left: dict, right: dict) -> list[tuple[str, str, str]]:
    """Which comparisons are honest.

    Sentiment share is included and warmth is not. An average polarity
    across a corpus mixes themes about the car with themes about the
    brand's nationality, and the two cars differ in exactly that mix —
    so a single "how positive" number would say one car is better liked
    when it is really less argued about.
    """
    return [
        ("share about the car itself",
         f"{left['about_car']:.0f}%", f"{right['about_car']:.0f}%"),
        ("share arguing, not reviewing",
         f"{left['meta']:.0f}%", f"{right['meta']:.0f}%"),
        ("share in themes that read positive",
         f"{left['positive']:.0f}%", f"{right['positive']:.0f}%"),
        ("share too sarcastic to score",
         f"{left['unscorable']:.0f}%", f"{right['unscorable']:.0f}%"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subjects", nargs="+", required=True,
                    help="two subjects, already analysed")
    ap.add_argument("--out", type=Path,
                    help="where to write the card (default: the first "
                         "subject's content directory)")
    args = ap.parse_args()

    if len(args.subjects) != 2:
        raise SystemExit("\nGive exactly two subjects. Three-way needs a "
                         "different card and is not built.\n")

    (left_name, left_analysis), (right_name, right_analysis) = (
        load(s) for s in args.subjects
    )
    left, right = metrics(left_analysis), metrics(right_analysis)

    print(f"\n{BOLD}{left_name}{RESET} vs {BOLD}{right_name}{RESET}")
    print(f"{DIM}{left['clustered']:,} vs {right['clustered']:,} clustered "
          f"comments{RESET}\n")

    rows = rows_for(left, right)
    for label, a, b in rows:
        print(f"  {a:>5}  {b:>5}   {DIM}{label}{RESET}")

    ratio = max(left["clustered"], right["clustered"]) / min(
        left["clustered"], right["clustered"]
    )
    note = (
        f"Shares, not totals: {left['clustered']:,} comments against "
        f"{right['clustered']:,}. Counted from comments, not buyers."
    )
    if ratio > 3:
        print(f"\n{YELLOW}corpora differ {ratio:.0f}x in size — the smaller "
              f"one moves more per comment{RESET}")

    out = args.out or (
        settings.workspace.subject(args.subjects[0]).ensure().content_dir
        / f"compare-{args.subjects[0]}-vs-{args.subjects[1]}.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    cards_mod.compare_card(
        (left_name, left), (right_name, right), rows, out, note=note
    )
    print(f"\n{GREEN}{out}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
