"""Verify the translations on a subject's thread cards.

    python scripts/check_translations.py --subject byd-racco
    python scripts/check_translations.py --subject byd-racco --angle car

Translates each quote a second time, independently, and reports where
the two readings disagree. Nothing is changed automatically — a
disagreement is a thing for you to look at, not for the pipeline to
resolve on its own.

Measured on the Racco threads: 6 of 20 translations disagreed, one of
them materially. That was with the same model doing both passes, which
is the weak version of this check; set LLM_PROVIDER to a different
model before running it for a genuinely independent read.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.render.translate import check_translations  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--angle", help="check one thread; default is all")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject)
    threads = (
        [paths.thread(args.angle)] if args.angle else paths.existing_threads()
    )
    threads = [t for t in threads if t.json.exists()]
    if not threads:
        print(f"\nNo threads found for {args.subject}.\n")
        return 1

    # Collect every distinct quote across the threads, remembering where
    # each appears so a problem can be traced back to a card.
    quotes: dict[str, dict] = {}
    for tp in threads:
        data = json.loads(tp.json.read_text(encoding="utf-8"))
        for post in data.get("posts", []):
            original = post.get("quote_original")
            english = post.get("quote_english")
            if not original or not english:
                continue
            entry = quotes.setdefault(
                original, {"english": english, "cards": []}
            )
            entry["cards"].append(f"{tp.angle}/{post['index']:02d}")

    if not quotes:
        print(f"\nNo translated quotes in these threads.\n")
        return 0

    print(f"\n{BOLD}Checking {len(quotes)} translation(s){RESET} "
          f"{DIM}via {settings.llm.provider}/{settings.llm.model}{RESET}")
    if settings.llm.provider == "deepseek":
        print(f"{DIM}note: same model that wrote them — catches slips, "
              f"not systematic blind spots{RESET}")

    try:
        client = LLMClient(settings.require_llm())
    except Exception as exc:  # noqa: BLE001 - config errors explain themselves
        print(f"\n{exc}\n")
        return 1

    pairs = [(original, meta["english"]) for original, meta in quotes.items()]
    results = check_translations(client, pairs)

    counts = {"ok": 0, "nuance": 0, "wrong": 0, "unchecked": 0}
    problems = []
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
        if result.verdict != "ok":
            problems.append(result)

    print(f"\n  {GREEN}{counts['ok']}{RESET} accurate"
          f"   {YELLOW}{counts['nuance']}{RESET} lose nuance"
          f"   {RED}{counts['wrong']}{RESET} materially wrong"
          + (f"   {DIM}{counts['unchecked']} unchecked{RESET}"
             if counts["unchecked"] else ""))

    for result in sorted(problems, key=lambda r: r.verdict != "wrong"):
        cards = quotes[result.original]["cards"]
        colour = RED if result.verdict == "wrong" else YELLOW
        print(f"\n{colour}{BOLD}{result.verdict.upper()}{RESET} "
              f"{DIM}{', '.join(cards)}{RESET}")
        print(f"  {DIM}original {RESET}{result.original[:150]}")
        print(f"  {DIM}on card  {RESET}{result.proposed[:150]}")
        print(f"  {DIM}second   {RESET}{result.independent[:150]}")
        if result.note:
            print(f"  {colour}why      {RESET}{result.note[:160]}")

    out = paths.content_dir / "translation-check.json"
    out.write_text(
        json.dumps(
            {
                "subject": args.subject,
                "checker": f"{settings.llm.provider}/{settings.llm.model}",
                "counts": counts,
                "results": [
                    {
                        "original": r.original,
                        "on_card": r.proposed,
                        "second_reading": r.independent,
                        "verdict": r.verdict,
                        "note": r.note,
                        "cards": quotes[r.original]["cards"],
                    }
                    for r in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{DIM}written: {out}{RESET}")
    if counts["wrong"]:
        print(f"{RED}{BOLD}Fix the cards marked WRONG before posting.{RESET}\n")
        return 1
    if counts["nuance"]:
        print(f"{YELLOW}Nuance flags are judgement calls — read them, "
              f"then decide.{RESET}\n")
    else:
        print(f"{GREEN}Nothing flagged.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
