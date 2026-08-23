"""Move flat `<subject>__<thing>` outputs into per-subject directories.

    python scripts/migrate_layout.py --dry-run
    python scripts/migrate_layout.py

Safe to run more than once; already-migrated files are left alone.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402

DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

# old filename suffix → (subdirectory, new name)
ANALYSIS = {
    "clusters.json": ("analysis", "clusters.json"),
    "analysis.json": ("analysis", "analysis.json"),
    "narrative.json": ("analysis", "narrative.json"),
    "report.html": ("content", "report.html"),
}

CHART_RE = re.compile(r"^(?P<name>[a-z-]+?)(?P<light>--light)?\.png$")


def plan(out_dir: Path) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []

    for path in sorted(out_dir.iterdir()):
        if path.is_dir():
            # The old thread folder: <subject>__thread/
            if "__" in path.name and path.name.endswith("__thread"):
                subject = path.name.split("__")[0]
                dest = out_dir / "subjects" / subject / "content" / "thread"
                moves.append((path, dest))
            continue

        if "__" not in path.name:
            continue

        subject, _, tail = path.name.partition("__")
        base = out_dir / "subjects" / subject

        if tail in ANALYSIS:
            sub, name = ANALYSIS[tail]
            moves.append((path, base / sub / name))
            continue

        match = CHART_RE.match(tail)
        if match:
            name = match.group("name")
            suffix = "-light" if match.group("light") else ""
            moves.append((path, base / "charts" / f"{name}{suffix}.png"))

    return moves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = settings.output_dir
    if not out_dir.exists():
        print(f"\n{out_dir} does not exist — nothing to migrate.\n")
        return 0

    moves = plan(out_dir)
    if not moves:
        print(f"\n{GREEN}Nothing to migrate.{RESET} Layout is already current.\n")
        return 0

    subjects = sorted({m[1].parts[-3] if m[1].is_dir() or m[1].suffix == "" else
                       _subject_of(m[1], out_dir) for m in moves})
    print(f"\n{BOLD}{len(moves)} item(s){RESET} across {len(subjects)} subject(s)\n")

    for src, dest in moves:
        rel_src = src.relative_to(out_dir)
        rel_dest = dest.relative_to(out_dir)
        print(f"  {DIM}{rel_src}{RESET}\n    → {rel_dest}")

    if args.dry_run:
        print(f"\n{YELLOW}Dry run — nothing moved.{RESET}\n")
        return 0

    print()
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"  {YELLOW}skip{RESET} {dest.relative_to(out_dir)} already exists")
            continue
        shutil.move(str(src), str(dest))

    # Record what each subject is, using the slug as a starting display
    # name — scripts overwrite this with a better one when given --name.
    for subject in {_subject_of(dest, out_dir) for _, dest in moves}:
        if not subject:
            continue
        paths = settings.workspace.subject(subject)
        if not paths.meta.exists():
            paths.ensure().write_meta(subject.replace("-", " ").title(), [])

    print(f"\n{GREEN}{BOLD}Migrated.{RESET} New layout under {out_dir}/subjects/\n")
    return 0


def _subject_of(path: Path, out_dir: Path) -> str:
    try:
        parts = path.relative_to(out_dir).parts
    except ValueError:
        return ""
    return parts[1] if len(parts) > 1 and parts[0] == "subjects" else ""


if __name__ == "__main__":
    raise SystemExit(main())
