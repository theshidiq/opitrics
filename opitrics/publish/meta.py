"""Publish a short to Instagram Reels, and optionally to a Facebook Page.

Instagram publishing is a two-step container model, and the step in
between is the one that catches people: create a container, **wait for
it to finish processing**, then publish. Publishing a container that is
still `IN_PROGRESS` fails, and the failure reads like a permissions
error rather than a timing one. `wait_for_container()` exists for that
single reason.

The video is not uploaded to Meta. A public URL is handed over and
Meta fetches it, which means the file has to be reachable from the
internet at publish time — a local path cannot be used, and neither
can a link that needs auth.

Access requires: an Instagram Business or Creator account linked to a
Facebook Page, a Meta app with `instagram_basic` and
`instagram_content_publish`, and App Review before it serves anyone
beyond 25 test users. Review takes 2–4 weeks.

Instagram allows 25 published posts per account per 24 hours, with
Reels and Stories counting against the same allowance.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"

SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_read_engagement",
    "pages_show_list",
]

CAPTION_MAX = 2200
DAILY_POST_LIMIT = 25

# Reels bounds. A short of 20–40s sits comfortably inside these.
MIN_SECONDS = 3
MAX_SECONDS = 900


class MetaError(RuntimeError):
    """Raised when credentials are missing or publishing fails."""


@dataclass
class ReelMeta:
    """A reel, addressed by public URL rather than by file.

    `video_url` must be publicly fetchable when `create_container` runs
    — Meta pulls the file itself. `local` is carried alongside only so
    the preview can show the video and the checks can read its size.
    """

    video_url: str
    caption: str
    local: Path | None = None
    share_to_feed: bool = True
    cover_url: str | None = None

    def problems(self) -> list[str]:
        found: list[str] = []
        if not self.video_url.startswith(("http://", "https://")):
            found.append(
                "video_url must be a public http(s) URL — Meta fetches the "
                "file itself and cannot read a local path"
            )
        if self.video_url.startswith("http://"):
            found.append("video_url is http, not https; Meta may refuse it")
        if len(self.caption) > CAPTION_MAX:
            found.append(
                f"caption is {len(self.caption)} chars, over {CAPTION_MAX}"
            )
        if self.local and not self.local.exists():
            found.append(f"local file not found: {self.local}")
        return found


def create_container(
    meta: ReelMeta,
    ig_user_id: str,
    access_token: str,
) -> str:
    """Ask Instagram to fetch and prepare the video. Returns a container id."""
    import requests

    problems = meta.problems()
    if problems:
        raise MetaError("cannot publish:\n  " + "\n  ".join(problems))

    params = {
        "media_type": "REELS",
        "video_url": meta.video_url,
        "caption": meta.caption,
        "share_to_feed": str(meta.share_to_feed).lower(),
        "access_token": access_token,
    }
    if meta.cover_url:
        params["cover_url"] = meta.cover_url

    resp = requests.post(f"{GRAPH}/{ig_user_id}/media", data=params, timeout=120)
    if resp.status_code != 200:
        raise MetaError(f"container failed ({resp.status_code}): {resp.text[:300]}")
    container_id = resp.json().get("id")
    if not container_id:
        raise MetaError(f"no container id: {resp.text[:300]}")
    return container_id


def container_status(container_id: str, access_token: str) -> tuple[str, str]:
    """Return (status_code, detail). FINISHED means ready to publish."""
    import requests

    resp = requests.get(
        f"{GRAPH}/{container_id}",
        params={"fields": "status_code,status", "access_token": access_token},
        timeout=60,
    )
    if resp.status_code != 200:
        raise MetaError(f"status failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    return data.get("status_code", "UNKNOWN"), data.get("status", "")


def wait_for_container(
    container_id: str,
    access_token: str,
    timeout: float = 300.0,
    interval: float = 5.0,
) -> None:
    """Block until the container is FINISHED, or raise.

    Meta transcodes on its own schedule; a half-minute vertical video
    is usually ready within about fifteen seconds, but "usually" is not
    something to publish against. Publishing an IN_PROGRESS container
    fails with a message that does not mention timing at all, which is
    why this waits explicitly rather than sleeping a fixed guess.
    """
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        code, detail = container_status(container_id, access_token)
        last = detail or code
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise MetaError(f"Meta could not process the video: {detail}")
        if code == "EXPIRED":
            raise MetaError("container expired before it was published")
        time.sleep(interval)
    raise MetaError(
        f"container still not ready after {timeout:.0f}s (last: {last}). "
        "It may still finish — check before creating another."
    )


def publish(
    container_id: str,
    ig_user_id: str,
    access_token: str,
    dry_run: bool = False,
) -> str:
    """Publish a finished container. Returns the media id."""
    import requests

    if dry_run:
        log.info("dry run: would publish container %s", container_id)
        return "dry-run"

    resp = requests.post(
        f"{GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=120,
    )
    if resp.status_code != 200:
        raise MetaError(f"publish failed ({resp.status_code}): {resp.text[:300]}")
    media_id = resp.json().get("id")
    if not media_id:
        raise MetaError(f"no media id: {resp.text[:300]}")
    return media_id


def publish_reel(
    meta: ReelMeta,
    ig_user_id: str,
    access_token: str,
    dry_run: bool = False,
) -> str:
    """Container, wait, publish — the whole sequence."""
    container_id = create_container(meta, ig_user_id, access_token)
    log.info("container %s created, waiting for processing…", container_id)
    if dry_run:
        return "dry-run"
    wait_for_container(container_id, access_token)
    return publish(container_id, ig_user_id, access_token)


def quota_used(ig_user_id: str, access_token: str) -> int:
    """How many of today's 25 posts are gone.

    Worth checking before a batch: the limit is per account and Reels
    share it with Stories, so a busy day elsewhere on the account
    silently shrinks what this can publish.
    """
    import requests

    resp = requests.get(
        f"{GRAPH}/{ig_user_id}/content_publishing_limit",
        params={"fields": "quota_usage,config", "access_token": access_token},
        timeout=60,
    )
    if resp.status_code != 200:
        raise MetaError(f"quota check failed ({resp.status_code}): {resp.text[:300]}")
    data = (resp.json().get("data") or [{}])[0]
    return int(data.get("quota_usage", 0))
