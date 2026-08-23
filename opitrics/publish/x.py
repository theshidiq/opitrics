"""Post a thread to X.

Publishing is deliberately not automatic. A quote can be verbatim,
correctly attributed, and still read as inflammatory once it is on a
timeline with your name on it — this corpus is full of nationalist
argument, and the analysis itself flags clusters whose sentiment it does
not trust. That judgment is the author's, so this module posts only what
it is explicitly told to post, and records what it did.

Pricing note: X moved to pay-per-use in February 2026 — roughly $0.015
per post, $0.20 if the post contains a link. An eight-post thread with
one link costs about thirty cents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

LIMIT = 280


class PublishError(RuntimeError):
    """Raised when X rejects a post or credentials are missing."""


@dataclass
class PostedItem:
    index: int
    tweet_id: str
    text: str
    media: str | None = None


@dataclass
class PublishResult:
    thread_url: str
    posted: list[PostedItem] = field(default_factory=list)
    failed_at: int | None = None
    error: str | None = None

    @property
    def complete(self) -> bool:
        return self.failed_at is None


@dataclass
class XCredentials:
    api_key: str
    api_secret: str
    access_token: str
    access_secret: str

    @classmethod
    def from_env(cls) -> XCredentials:
        import os

        missing = [
            name
            for name in (
                "X_API_KEY",
                "X_API_SECRET",
                "X_ACCESS_TOKEN",
                "X_ACCESS_SECRET",
            )
            if not os.getenv(name, "").strip()
        ]
        if missing:
            raise PublishError(
                "Missing X credentials: " + ", ".join(missing) + "\n"
                "  1. developer.x.com → create an app\n"
                "  2. Set its permissions to Read and Write\n"
                "  3. Generate API key/secret and an access token/secret\n"
                "  4. Paste all four into .env"
            )
        return cls(
            api_key=os.environ["X_API_KEY"].strip(),
            api_secret=os.environ["X_API_SECRET"].strip(),
            access_token=os.environ["X_ACCESS_TOKEN"].strip(),
            access_secret=os.environ["X_ACCESS_SECRET"].strip(),
        )


class XPublisher:
    def __init__(self, creds: XCredentials) -> None:
        self.creds = creds
        self._client = None
        self._api = None

    @property
    def client(self):
        """v2 client — used for creating posts."""
        if self._client is None:
            import tweepy

            self._client = tweepy.Client(
                consumer_key=self.creds.api_key,
                consumer_secret=self.creds.api_secret,
                access_token=self.creds.access_token,
                access_token_secret=self.creds.access_secret,
            )
        return self._client

    @property
    def api(self):
        """v1.1 API — still the reliable path for media upload."""
        if self._api is None:
            import tweepy

            auth = tweepy.OAuth1UserHandler(
                self.creds.api_key,
                self.creds.api_secret,
                self.creds.access_token,
                self.creds.access_secret,
            )
            self._api = tweepy.API(auth)
        return self._api

    def whoami(self) -> str:
        """Confirm which account is about to be posted from.

        Worth surfacing before publishing — posting a thread from the
        wrong account is not undoable in any meaningful sense.
        """
        me = self.client.get_me()
        if not me or not me.data:
            raise PublishError("Could not identify the authenticated account")
        return me.data.username

    def upload_media(self, path: Path) -> str:
        if not path.exists():
            raise PublishError(f"media not found: {path}")
        media = self.api.media_upload(filename=str(path))
        return str(media.media_id)

    def post_thread(
        self,
        posts: list[dict],
        media_dir: Path | None = None,
        dry_run: bool = False,
    ) -> PublishResult:
        """Post each item as a reply to the previous one.

        A partial thread is left in place rather than deleted if a post
        fails midway: deleting posts that people may already have seen
        is worse than an incomplete thread you can finish by hand.
        """
        username = "dry-run" if dry_run else self.whoami()
        result = PublishResult(thread_url="")
        previous: str | None = None

        for item in posts:
            index = int(item["index"])
            text = str(item["text"]).strip()

            if len(text) > LIMIT:
                result.failed_at = index
                result.error = f"post {index} is {len(text)} chars (limit {LIMIT})"
                return result

            media_ids: list[str] = []
            media_path = item.get("media_path")
            if media_path and media_dir:
                candidate = media_dir / str(media_path)
                if candidate.exists() and not dry_run:
                    media_ids.append(self.upload_media(candidate))

            if dry_run:
                log.info("[dry run] %d/%d %s", index, len(posts), text[:60])
                result.posted.append(
                    PostedItem(index=index, tweet_id=f"dry-{index}", text=text,
                               media=str(media_path) if media_path else None)
                )
                continue

            try:
                response = self.client.create_tweet(
                    text=text,
                    media_ids=media_ids or None,
                    in_reply_to_tweet_id=previous,
                )
            except Exception as exc:  # noqa: BLE001 - surface whatever X said
                result.failed_at = index
                result.error = str(exc)
                return result

            tweet_id = str(response.data["id"])
            previous = tweet_id
            result.posted.append(
                PostedItem(index=index, tweet_id=tweet_id, text=text,
                           media=str(media_path) if media_path else None)
            )
            log.info("posted %d/%d → %s", index, len(posts), tweet_id)

        if result.posted:
            first = result.posted[0].tweet_id
            result.thread_url = f"https://x.com/{username}/status/{first}"
        return result


def write_receipt(result: PublishResult, path: Path, subject: str) -> None:
    """Record what was posted, so a partial thread can be finished and a
    published thread can be found again later."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "subject": subject,
                "posted_at": datetime.now().isoformat(timespec="seconds"),
                "thread_url": result.thread_url,
                "complete": result.complete,
                "failed_at": result.failed_at,
                "error": result.error,
                "posts": [
                    {
                        "index": p.index,
                        "tweet_id": p.tweet_id,
                        "media": p.media,
                        "text": p.text,
                    }
                    for p in result.posted
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
