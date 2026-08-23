"""YouTube Data API client.

Wraps the bits of the API we need, tracking quota spend as it goes.
Every fetch is resumable and idempotent: comments already in the cache
are skipped, and an interrupted fetch picks up from its page token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from opitrics.ingest.db import Database

log = logging.getLogger(__name__)

# Documented quota costs, units per call.
# https://developers.google.com/youtube/v3/determine_quota_cost
COST_SEARCH = 100
COST_LIST = 1

DAILY_QUOTA = 10_000


class QuotaExceeded(RuntimeError):
    """Raised when the daily quota is spent, or YouTube says it is."""


@dataclass
class Video:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    duration: str | None
    default_lang: str | None

    def as_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "published_at": self.published_at,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "duration": self.duration,
            "default_lang": self.default_lang,
        }


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeClient:
    def __init__(self, api_key: str, db: Database) -> None:
        self._yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self.db = db

    # ── quota ───────────────────────────────────────────────

    def _spend(self, operation: str, units: int) -> None:
        used = self.db.quota_used_today()
        if used + units > DAILY_QUOTA:
            raise QuotaExceeded(
                f"Daily quota would be exceeded: {used}/{DAILY_QUOTA} used, "
                f"{operation} costs {units}. Resets at midnight Pacific."
            )
        self.db.log_quota(operation, units)

    def quota_remaining(self) -> int:
        return DAILY_QUOTA - self.db.quota_used_today()

    # ── videos ──────────────────────────────────────────────

    def get_videos(self, video_ids: list[str]) -> list[Video]:
        """Fetch metadata for up to 50 videos per call (1 unit each call)."""
        videos: list[Video] = []
        for batch_start in range(0, len(video_ids), 50):
            batch = video_ids[batch_start : batch_start + 50]
            self._spend("videos.list", COST_LIST)
            resp = (
                self._yt.videos()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            for item in resp.get("items", []):
                snip = item["snippet"]
                stats = item.get("statistics", {})
                videos.append(
                    Video(
                        video_id=item["id"],
                        title=snip["title"],
                        channel_id=snip["channelId"],
                        channel_title=snip["channelTitle"],
                        published_at=snip["publishedAt"],
                        view_count=_int_or_none(stats.get("viewCount")),
                        like_count=_int_or_none(stats.get("likeCount")),
                        comment_count=_int_or_none(stats.get("commentCount")),
                        duration=item.get("contentDetails", {}).get("duration"),
                        default_lang=snip.get("defaultAudioLanguage")
                        or snip.get("defaultLanguage"),
                    )
                )
        return videos

    def search_videos(
        self,
        query: str,
        max_results: int = 25,
        region_code: str | None = None,
        published_after: str | None = None,
        relevance_language: str | None = None,
    ) -> list[str]:
        """Search for videos, returning ids. Costs 100 units — use sparingly."""
        self._spend("search.list", COST_SEARCH)
        params = {
            "part": "id",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "relevance",
        }
        if region_code:
            params["regionCode"] = region_code
        if published_after:
            params["publishedAfter"] = published_after
        if relevance_language:
            params["relevanceLanguage"] = relevance_language

        resp = self._yt.search().list(**params).execute()
        return [item["id"]["videoId"] for item in resp.get("items", [])]

    # ── comments ────────────────────────────────────────────

    def iter_comment_pages(
        self, video_id: str, page_token: str | None = None
    ) -> Iterator[tuple[list[dict], str | None]]:
        """Yield (comments, next_page_token) per page.

        Each page costs 1 unit and returns up to 100 threads. Replies
        included in the thread response come free; threads with more
        replies than fit are not chased further — the top few carry the
        argument well enough and chasing them multiplies quota spend.
        """
        token = page_token
        while True:
            self._spend("commentThreads.list", COST_LIST)
            try:
                resp = (
                    self._yt.commentThreads()
                    .list(
                        part="snippet,replies",
                        videoId=video_id,
                        maxResults=100,
                        pageToken=token,
                        textFormat="plainText",
                        order="relevance",
                    )
                    .execute()
                )
            except HttpError as exc:
                reason = _http_reason(exc)
                if reason in {"commentsDisabled", "videoNotFound"}:
                    log.warning("%s for %s — skipping", reason, video_id)
                    return
                if reason == "quotaExceeded":
                    raise QuotaExceeded("YouTube reports quota exhausted") from exc
                raise

            comments: list[dict] = []
            for thread in resp.get("items", []):
                top = thread["snippet"]["topLevelComment"]
                snip = top["snippet"]
                comments.append(
                    {
                        "comment_id": top["id"],
                        "video_id": video_id,
                        "parent_id": None,
                        "text": snip.get("textOriginal", ""),
                        "author": snip.get("authorDisplayName"),
                        "like_count": snip.get("likeCount", 0),
                        "reply_count": thread["snippet"].get("totalReplyCount", 0),
                        "published_at": snip["publishedAt"],
                        "updated_at": snip.get("updatedAt"),
                    }
                )
                for reply in thread.get("replies", {}).get("comments", []):
                    rsnip = reply["snippet"]
                    comments.append(
                        {
                            "comment_id": reply["id"],
                            "video_id": video_id,
                            "parent_id": top["id"],
                            "text": rsnip.get("textOriginal", ""),
                            "author": rsnip.get("authorDisplayName"),
                            "like_count": rsnip.get("likeCount", 0),
                            "reply_count": 0,
                            "published_at": rsnip["publishedAt"],
                            "updated_at": rsnip.get("updatedAt"),
                        }
                    )

            token = resp.get("nextPageToken")
            yield comments, token
            if not token:
                return

    def fetch_comments(
        self, video_id: str, max_comments: int | None = None, resume: bool = True
    ) -> int:
        """Fetch a video's comments into the cache. Returns rows added.

        Already-complete videos are skipped entirely — no quota spent.
        """
        if resume and self.db.is_complete(video_id):
            cached = self.db.comment_count(video_id)
            log.info("%s already complete (%d cached) — skipping", video_id, cached)
            return 0

        state = self.db.fetch_state(video_id) if resume else None
        token = state["next_page_token"] if state else None
        total_new = 0
        total_seen = self.db.comment_count(video_id)

        try:
            for comments, next_token in self.iter_comment_pages(video_id, token):
                added = self.db.insert_comments(comments)
                total_new += added
                total_seen += len(comments)
                self.db.record_fetch(
                    video_id,
                    pulled=total_seen,
                    complete=next_token is None,
                    next_page_token=next_token,
                )
                if max_comments and total_seen >= max_comments:
                    log.info("%s hit max_comments=%d", video_id, max_comments)
                    break
        except QuotaExceeded:
            self.db.record_fetch(
                video_id, pulled=total_seen, complete=False, error="quota exceeded"
            )
            raise
        except Exception as exc:  # noqa: BLE001 - record then re-raise
            self.db.record_fetch(
                video_id, pulled=total_seen, complete=False, error=str(exc)[:500]
            )
            raise

        return total_new


def _http_reason(exc: HttpError) -> str:
    """Pull the machine-readable reason out of a Google API error."""
    try:
        errors = exc.error_details or []
        if errors and isinstance(errors, list):
            return errors[0].get("reason", "")
    except Exception:  # noqa: BLE001 - best effort only
        pass
    return ""
