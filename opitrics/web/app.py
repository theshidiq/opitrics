"""Local web UI.

    uvicorn opitrics.web.app:app --reload

Long-running work (fetching, embedding, clustering) happens in a
background thread while the browser polls for progress — a comment
fetch can take minutes and an HTTP request should not sit open for it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from opitrics.config import settings
from opitrics.ingest.db import Database

ROOT = Path(__file__).resolve().parent.parent.parent
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Opitrics")


# ── job runner ──────────────────────────────────────────────


@dataclass
class Job:
    id: str
    kind: str
    subject: str
    status: str = "running"
    started: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    lines: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "subject": self.subject,
            "status": self.status,
            "started": self.started,
            # Only the tail matters for a progress view, and sending the
            # whole log on every poll gets expensive fast.
            "lines": self.lines[-40:],
            "error": self.error,
        }


JOBS: dict[str, Job] = {}
_lock = threading.Lock()


def _run(job: Job, argv: list[str]) -> None:
    """Stream a pipeline script's output into the job log."""
    try:
        proc = subprocess.Popen(
            [sys.executable, *argv],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = _strip_ansi(raw.rstrip())
            if line:
                with _lock:
                    job.lines.append(line)
        proc.wait()
        job.status = "done" if proc.returncode == 0 else "failed"
        if proc.returncode != 0:
            job.error = f"exited with code {proc.returncode}"
    except Exception as exc:  # noqa: BLE001 - surface anything to the UI
        job.status = "failed"
        job.error = str(exc)


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _start(kind: str, subject: str, argv: list[str]) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, subject=subject)
    JOBS[job.id] = job
    threading.Thread(target=_run, args=(job, argv), daemon=True).start()
    return job


# ── models ──────────────────────────────────────────────────


class FetchRequest(BaseModel):
    subject: str
    query: str | None = None
    videos: list[str] = []
    region: str | None = None
    limit: int = 6


class RunRequest(BaseModel):
    subject: str
    types: list[str] = []
    clusters: int = 40


class DiscoverRequest(BaseModel):
    regions: list[str] = ["JP", "US", "GB", "DE", "AU", "ID"]
    reviews: bool = True
    top: int = 12


# ── routes ──────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/subjects")
def subjects() -> list[dict]:
    """Everything analysed so far, newest activity first."""
    db = Database(settings.database_path)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT v.subject,
                   COUNT(DISTINCT v.video_id) AS videos,
                   COUNT(c.comment_id)        AS comments,
                   MAX(v.fetched_at)          AS last_fetch
            FROM videos v
            LEFT JOIN comments c ON c.video_id = v.video_id
            GROUP BY v.subject
            ORDER BY last_fetch DESC
            """
        ).fetchall()

    out = []
    for row in rows:
        subject = row["subject"]
        sp = settings.workspace.subject(subject)
        analysis = sp.analysis
        report = sp.report
        headline = None
        totals = None

        narrative = sp.narrative
        if narrative.exists():
            try:
                headline = json.loads(narrative.read_text(encoding="utf-8")).get("headline")
            except json.JSONDecodeError:
                pass
        if analysis.exists():
            try:
                totals = json.loads(analysis.read_text(encoding="utf-8")).get("totals")
            except json.JSONDecodeError:
                pass

        out.append(
            {
                "subject": subject,
                "videos": row["videos"],
                "comments": row["comments"],
                "last_fetch": row["last_fetch"],
                "has_analysis": analysis.exists(),
                "has_report": report.exists(),
                "has_thread": sp.thread_copy.exists(),
                "display_name": sp.display_name,
                "runs": len(sp.runs()),
                "headline": headline,
                "totals": totals,
            }
        )
    return out


@app.get("/api/subjects/{subject}")
def subject_detail(subject: str) -> dict:
    sp = settings.workspace.subject(subject)
    if not sp.analysis.exists():
        raise HTTPException(404, f"no analysis for {subject}")

    data = json.loads(sp.analysis.read_text(encoding="utf-8"))
    clusters = sorted(data["clusters"], key=lambda c: -c["size"])
    narrative = sp.narrative

    return {
        "subject": subject,
        "display_name": sp.display_name,
        "totals": data["totals"],
        "narrative": json.loads(narrative.read_text(encoding="utf-8"))
        if narrative.exists()
        else {},
        "clusters": [
            {
                "label": c.get("llm_label") or c.get("aspect_label") or "unnamed",
                "summary": c.get("llm_summary", ""),
                "aspect": c.get("aspect_label"),
                "size": c["size"],
                "likes": c["total_likes"],
                "polarity": c["sentiment"]["polarity"],
                "intensity": c["sentiment"]["intensity"],
                "sentiment": c["sentiment"]["label"],
                "is_meta": c.get("is_meta", False),
                "unmapped": not c.get("aspect"),
                "sarcasm_risk": c.get("sarcasm_risk", False),
                "quotes": c["quotes"][:3],
            }
            for c in clusters
        ],
    }


@app.get("/api/discovery")
def discovery() -> list[dict]:
    path = settings.workspace.discovery
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/quota")
def quota() -> dict:
    db = Database(settings.database_path)
    used = db.quota_used_today()
    return {"used": used, "limit": 10_000, "remaining": 10_000 - used}


@app.get("/preview/{subject}/{angle}")
def thread_preview(subject: str, angle: str) -> FileResponse:
    """The pre-publish review page for one thread.

    Served here as well as by scripts/publish.py so a thread can be read
    through without starting the publishing flow.
    """
    tp = settings.workspace.subject(subject).thread(angle)
    if not tp.preview.exists():
        raise HTTPException(
            404, f"no preview for {angle} — run scripts/publish.py --dry-run first"
        )
    return FileResponse(tp.preview, media_type="text/html")


@app.get("/api/threads/{subject}")
def threads(subject: str) -> list[dict]:
    """Every thread built for a subject, with its publishing state."""
    sp = settings.workspace.subject(subject)
    out = []
    for tp in sp.existing_threads():
        data = json.loads(tp.json.read_text(encoding="utf-8"))
        posts = data.get("posts", [])
        out.append(
            {
                "angle": tp.angle,
                "title": data.get("angle_title", tp.angle),
                "headline": data.get("headline", ""),
                "posts": len(posts),
                "over_limit": sum(1 for p in posts if p.get("chars", 0) > 280),
                "warnings": len(data.get("quote_warnings", [])),
                "posted": tp.posted,
                "has_preview": tp.preview.exists(),
            }
        )
    return out


@app.get("/sources/{subject}")
def sources(subject: str) -> FileResponse:
    """The audit page — every quote linked to its original comment."""
    path = settings.workspace.subject(subject).content_dir / "sources.html"
    if not path.exists():
        raise HTTPException(404, "run scripts/sources.py first")
    return FileResponse(path, media_type="text/html")


@app.get("/report/{subject}")
def report(subject: str) -> FileResponse:
    path = settings.workspace.subject(subject).report
    if not path.exists():
        raise HTTPException(404, "no report yet")
    return FileResponse(path, media_type="text/html")


@app.get("/chart/{subject}/{name}")
def chart(subject: str, name: str, theme: str = "light") -> FileResponse:
    """Serve a chart, preferring the theme that suits the page.

    The UI is newsprint-light, so a dark chart reads as a hole in the
    page — but the dark files are the ones worth dropping into a video,
    so both are kept and this picks between them.
    """
    if not name.replace("-", "").isalnum():
        raise HTTPException(400, "bad chart name")

    sp = settings.workspace.subject(subject)
    candidates = (
        [sp.chart(name, "light"), sp.chart(name)]
        if theme == "light"
        else [sp.chart(name)]
    )
    for path in candidates:
        if path.exists():
            return FileResponse(path, media_type="image/png")
    raise HTTPException(404, "no such chart")


# ── job endpoints ───────────────────────────────────────────


@app.post("/api/discover")
def start_discover(req: DiscoverRequest) -> dict:
    argv = ["scripts/discover.py", "--top", str(req.top), "--regions", *req.regions]
    if not req.reviews:
        argv.append("--no-reviews")
    return _start("discover", "—", argv).as_dict()


@app.post("/api/fetch")
def start_fetch(req: FetchRequest) -> dict:
    if not req.query and not req.videos:
        raise HTTPException(400, "give a search query or at least one video")

    argv = ["scripts/fetch.py", "--subject", req.subject, "--limit", str(req.limit)]
    if req.query:
        argv += ["--query", req.query]
    for video in req.videos:
        argv += ["--video", video]
    if req.region:
        argv += ["--region", req.region]
    return _start("fetch", req.subject, argv).as_dict()


@app.post("/api/analyze")
def start_analyze(req: RunRequest) -> dict:
    """Cluster, score and report in one chained job.

    Chained rather than exposed as three endpoints because the stages
    are strictly sequential and there is no useful point to stop between
    them from the UI's perspective.
    """
    job = Job(id=uuid.uuid4().hex[:12], kind="analyze", subject=req.subject)
    JOBS[job.id] = job

    def chain() -> None:
        stages = [
            ["scripts/cluster.py", "--subject", req.subject,
             "--clusters", str(req.clusters), "--top", "0"],
            ["scripts/analyze.py", "--subject", req.subject, "--types", *req.types],
            ["scripts/report.py", "--subject", req.subject],
        ]
        for argv in stages:
            _run(job, argv)
            if job.status == "failed":
                return
            job.status = "running"
        job.status = "done"

    threading.Thread(target=chain, daemon=True).start()
    return job.as_dict()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return JSONResponse(job.as_dict())


@app.get("/api/jobs")
def all_jobs() -> list[dict]:
    return [j.as_dict() for j in sorted(JOBS.values(), key=lambda j: j.started, reverse=True)]
