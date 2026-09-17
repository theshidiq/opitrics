"""Where everything lives on disk.

One directory per subject, so adding the fiftieth car does not make the
output folder unusable. Within a subject, artifacts are grouped by what
they are rather than prefixed by whose they are:

    data/subjects/byd-racco/
        subject.json            identity, display name, vehicle types
        analysis/               clusters, scores, narrative — the data
        charts/                 PNGs, light and dark
        content/
            report.html
            thread/             copy + one card per post
        runs/
            2026-08-23T1412/    a frozen copy of a previous analysis

Anything under `analysis/` and `charts/` is the *current* state and gets
overwritten in place. `runs/` keeps dated snapshots so a comparison
between two analyses of the same car stays possible after a re-run.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ThreadPaths:
    """One thread — copy, cards, and its publishing receipt.

    A subject carries several of these, one per angle, because the same
    corpus supports genuinely different stories and they should not
    overwrite each other.
    """

    root: Path
    angle: str

    @property
    def copy(self) -> Path:
        return self.root / "thread.txt"

    @property
    def json(self) -> Path:
        return self.root / "thread.json"

    @property
    def receipt(self) -> Path:
        return self.root / "posted.json"

    @property
    def preview(self) -> Path:
        return self.root / "preview.html"

    def card(self, index: int) -> Path:
        return self.root / f"{index:02d}.png"

    @property
    def posted(self) -> bool:
        return self.receipt.exists()

    def ensure(self) -> ThreadPaths:
        self.root.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class SubjectPaths:
    """Every path belonging to one analysis subject."""

    root: Path
    subject: str

    # ── directories ─────────────────────────────────────────

    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis"

    @property
    def charts_dir(self) -> Path:
        return self.root / "charts"

    @property
    def content_dir(self) -> Path:
        return self.root / "content"

    @property
    def threads_dir(self) -> Path:
        return self.content_dir / "threads"

    def thread(self, angle: str = "car") -> ThreadPaths:
        """One thread per angle, so several can coexist for a subject."""
        return ThreadPaths(root=self.threads_dir / angle, angle=angle)

    def existing_threads(self) -> list[ThreadPaths]:
        if not self.threads_dir.exists():
            return []
        return [
            ThreadPaths(root=p, angle=p.name)
            for p in sorted(self.threads_dir.iterdir())
            if p.is_dir() and (p / "thread.json").exists()
        ]

    @property
    def thread_dir(self) -> Path:
        """Backwards-compatible alias for the default angle."""
        return self.thread("car").root

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    # ── analysis artifacts ──────────────────────────────────

    @property
    def meta(self) -> Path:
        return self.root / "subject.json"

    @property
    def specs(self) -> Path:
        """Hand-entered manufacturer figures, each with its source URL.

        Deliberately not under analysis/: nothing the pipeline computes
        writes here, and a re-analysis must never overwrite it. See
        opitrics/analyze/specs.py for the shape and the reasoning.
        """
        return self.root / "specs.json"

    @property
    def clusters(self) -> Path:
        return self.analysis_dir / "clusters.json"

    @property
    def analysis(self) -> Path:
        return self.analysis_dir / "analysis.json"

    @property
    def narrative(self) -> Path:
        return self.analysis_dir / "narrative.json"

    # ── content artifacts ───────────────────────────────────

    @property
    def report(self) -> Path:
        return self.content_dir / "report.html"

    def chart(self, name: str, theme: str = "light") -> Path:
        """Charts are light-only; the theme argument is kept so callers
        that pass one still resolve to the right file."""
        return self.charts_dir / f"{name}.png"

    # ── lifecycle ───────────────────────────────────────────

    def ensure(self) -> SubjectPaths:
        for directory in (
            self.analysis_dir,
            self.charts_dir,
            self.content_dir,
            self.threads_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def write_meta(self, display_name: str, vehicle_types: list[str]) -> None:
        """Record what this subject is, so later runs and the UI do not
        have to re-derive a display name from the slug."""
        existing = self.read_meta()
        payload = {
            "subject": self.subject,
            "display_name": display_name or existing.get("display_name") or self.subject,
            "vehicle_types": vehicle_types or existing.get("vehicle_types", []),
            "created": existing.get("created") or _stamp(),
            "updated": _stamp(),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def read_meta(self) -> dict:
        if not self.meta.exists():
            return {}
        try:
            return json.loads(self.meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    @property
    def display_name(self) -> str:
        return self.read_meta().get("display_name") or self.subject.replace("-", " ").title()

    def snapshot(self) -> Path | None:
        """Freeze the current analysis and charts into runs/<timestamp>.

        Called before a re-analysis overwrites them. Returns None when
        there is nothing to preserve yet.
        """
        if not self.analysis.exists():
            return None

        target = self.runs_dir / datetime.now().strftime("%Y-%m-%dT%H%M")
        if target.exists():
            return target
        target.mkdir(parents=True)

        for source in (self.analysis_dir, self.charts_dir):
            if source.exists():
                shutil.copytree(source, target / source.name, dirs_exist_ok=True)
        if self.report.exists():
            shutil.copy2(self.report, target / "report.html")
        return target

    def runs(self) -> list[Path]:
        if not self.runs_dir.exists():
            return []
        return sorted((p for p in self.runs_dir.iterdir() if p.is_dir()), reverse=True)


@dataclass(frozen=True)
class Workspace:
    """The output tree as a whole."""

    root: Path

    @property
    def subjects_dir(self) -> Path:
        return self.root / "subjects"

    @property
    def discovery(self) -> Path:
        return self.root / "discovery.json"

    def subject(self, name: str) -> SubjectPaths:
        return SubjectPaths(root=self.subjects_dir / name, subject=name)

    def list_subjects(self) -> list[SubjectPaths]:
        if not self.subjects_dir.exists():
            return []
        return [
            SubjectPaths(root=p, subject=p.name)
            for p in sorted(self.subjects_dir.iterdir())
            if p.is_dir()
        ]


def _stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
