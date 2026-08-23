"""SQLite cache for fetched YouTube data.

Everything fetched lands here before any processing. Quota is finite
(10,000 units/day) and re-running an analysis while tuning downstream
stages must never re-spend it — so fetches are idempotent and results
are read back from here forever after.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    channel_id      TEXT NOT NULL,
    channel_title   TEXT NOT NULL,
    published_at    TEXT NOT NULL,
    view_count      INTEGER,
    like_count      INTEGER,
    comment_count   INTEGER,
    duration        TEXT,
    default_lang    TEXT,
    -- Which analysis subject this video was gathered for, e.g. "byd-racco".
    subject         TEXT NOT NULL,
    -- Region we attribute this video to; set at gather time, used for
    -- the regional sentiment split. NULL when unknown.
    region          TEXT,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_subject ON videos(subject);

CREATE TABLE IF NOT EXISTS comments (
    comment_id      TEXT PRIMARY KEY,
    video_id        TEXT NOT NULL REFERENCES videos(video_id),
    -- NULL for top-level comments; set for replies.
    parent_id       TEXT,
    text            TEXT NOT NULL,
    author          TEXT,
    like_count      INTEGER NOT NULL DEFAULT 0,
    reply_count     INTEGER NOT NULL DEFAULT 0,
    published_at    TEXT NOT NULL,
    updated_at      TEXT,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_id);

-- Records each fetch so we can tell "no comments" from "never fetched",
-- and so a partial fetch can be resumed rather than restarted.
CREATE TABLE IF NOT EXISTS fetch_log (
    video_id        TEXT PRIMARY KEY REFERENCES videos(video_id),
    comments_pulled INTEGER NOT NULL,
    complete        INTEGER NOT NULL DEFAULT 0,
    next_page_token TEXT,
    error           TEXT,
    fetched_at      TEXT NOT NULL
);

-- Quota accounting. YouTube gives no API to read remaining quota, so
-- we track spend ourselves against the documented per-call costs.
CREATE TABLE IF NOT EXISTS quota_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    day             TEXT NOT NULL,
    operation       TEXT NOT NULL,
    units           INTEGER NOT NULL,
    logged_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quota_day ON quota_log(day);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    """UTC date — YouTube quota resets at midnight Pacific, but UTC is
    close enough for a warning threshold and avoids a tz dependency."""
    return datetime.now(timezone.utc).date().isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        # WAL keeps reads working while a long fetch writes.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── videos ──────────────────────────────────────────────

    def upsert_video(self, video: dict, subject: str, region: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO videos (
                    video_id, title, channel_id, channel_title, published_at,
                    view_count, like_count, comment_count, duration,
                    default_lang, subject, region, fetched_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(video_id) DO UPDATE SET
                    view_count    = excluded.view_count,
                    like_count    = excluded.like_count,
                    comment_count = excluded.comment_count,
                    region        = COALESCE(excluded.region, videos.region),
                    fetched_at    = excluded.fetched_at
                """,
                (
                    video["video_id"],
                    video["title"],
                    video["channel_id"],
                    video["channel_title"],
                    video["published_at"],
                    video.get("view_count"),
                    video.get("like_count"),
                    video.get("comment_count"),
                    video.get("duration"),
                    video.get("default_lang"),
                    subject,
                    region,
                    utcnow(),
                ),
            )

    def videos_for_subject(self, subject: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM videos WHERE subject = ? ORDER BY view_count DESC",
                (subject,),
            ).fetchall()

    # ── comments ────────────────────────────────────────────

    def insert_comments(self, comments: list[dict]) -> int:
        """Insert comments, ignoring any already cached.

        Returns the number of genuinely new rows, which is what tells a
        resumed fetch whether it is still making progress.
        """
        if not comments:
            return 0
        now = utcnow()
        with self.connect() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO comments (
                    comment_id, video_id, parent_id, text, author,
                    like_count, reply_count, published_at, updated_at, fetched_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        c["comment_id"],
                        c["video_id"],
                        c.get("parent_id"),
                        c["text"],
                        c.get("author"),
                        c.get("like_count", 0),
                        c.get("reply_count", 0),
                        c["published_at"],
                        c.get("updated_at"),
                        now,
                    )
                    for c in comments
                ],
            )
            return conn.total_changes - before

    def comment_count(self, video_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM comments WHERE video_id = ?", (video_id,)
            ).fetchone()
            return row["n"]

    def comments_for_subject(self, subject: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, v.channel_title, v.region, v.title AS video_title
                FROM comments c
                JOIN videos v ON v.video_id = c.video_id
                WHERE v.subject = ?
                """,
                (subject,),
            ).fetchall()

    # ── fetch log ───────────────────────────────────────────

    def record_fetch(
        self,
        video_id: str,
        pulled: int,
        complete: bool,
        next_page_token: str | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO fetch_log (
                    video_id, comments_pulled, complete, next_page_token, error, fetched_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(video_id) DO UPDATE SET
                    comments_pulled = excluded.comments_pulled,
                    complete        = excluded.complete,
                    next_page_token = excluded.next_page_token,
                    error           = excluded.error,
                    fetched_at      = excluded.fetched_at
                """,
                (video_id, pulled, int(complete), next_page_token, error, utcnow()),
            )

    def fetch_state(self, video_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM fetch_log WHERE video_id = ?", (video_id,)
            ).fetchone()

    def is_complete(self, video_id: str) -> bool:
        state = self.fetch_state(video_id)
        return bool(state and state["complete"])

    # ── quota ───────────────────────────────────────────────

    def log_quota(self, operation: str, units: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO quota_log (day, operation, units, logged_at) VALUES (?,?,?,?)",
                (today(), operation, units, utcnow()),
            )

    def quota_used_today(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(units), 0) AS n FROM quota_log WHERE day = ?",
                (today(),),
            ).fetchone()
            return row["n"]
