"""Upload a short to TikTok.

Three things about this API decide the shape of everything below.

**Unaudited apps cannot post publicly.** Until TikTok audits the
client, every video it posts is forced to private ("SELF_ONLY"),
regardless of what the request asks for, and no more than five users
may post in any 24 hours. The audit takes 2–4 weeks. This is not a
limit to design around — it is the normal state of a new app, and the
code says so plainly rather than letting a "successful" upload look
public when it is not.

**`creator_info/query` comes first, always.** It is not optional
metadata: the privacy level sent at init must be one of the values
that call returned, and it also reports whether the account is
currently allowed to post at all. Skipping it produces a rejection
that reads like a permissions bug.

**The upload URL expires in one hour** and the video goes to it by
PUT, not as a multipart form to the API host.

Audit also requires the posting UI to show the creator's username and
avatar before publishing — hence `CreatorInfo` carrying both, and the
preview using them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

API = "https://open.tiktokapis.com/v2"

# Posting on a user's behalf. video.upload puts a video in the user's
# drafts; video.publish posts it. Both are separate grants and an app
# is commonly approved for one and not the other.
SCOPES = ["video.publish", "video.upload"]

# TikTok's own caps. Worth knowing before a 15-minute upload fails.
TITLE_MAX = 2200
MIN_SECONDS = 3
MAX_SECONDS = 600
MAX_BYTES = 4 * 1024 * 1024 * 1024

PRIVACY = {
    "private": "SELF_ONLY",
    "friends": "MUTUAL_FOLLOW_FRIENDS",
    "followers": "FOLLOWER_OF_CREATOR",
    "public": "PUBLIC_TO_EVERYONE",
}


class TikTokError(RuntimeError):
    """Raised when credentials are missing or the upload fails."""


@dataclass
class CreatorInfo:
    """What the account is currently permitted to do.

    `privacy_level_options` is the authoritative list — an app that is
    not yet audited will simply not be offered PUBLIC_TO_EVERYONE, and
    sending it anyway is an error rather than a downgrade.
    """

    username: str
    avatar_url: str
    nickname: str = ""
    privacy_level_options: list[str] = field(default_factory=list)
    comment_disabled: bool = False
    duet_disabled: bool = False
    stitch_disabled: bool = False
    max_video_seconds: int = MAX_SECONDS

    @property
    def can_post_public(self) -> bool:
        return "PUBLIC_TO_EVERYONE" in self.privacy_level_options


@dataclass
class PostMeta:
    video: Path
    title: str
    privacy: str = "private"
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False

    def problems(self, info: CreatorInfo | None = None) -> list[str]:
        found: list[str] = []
        if not self.video.exists():
            found.append(f"video not found: {self.video}")
        else:
            size = self.video.stat().st_size
            if size > MAX_BYTES:
                found.append(f"video is {size / 1e9:.1f}GB, over TikTok's 4GB")
            if size == 0:
                found.append("video is empty")
        if not self.title.strip():
            found.append("title is empty")
        if len(self.title) > TITLE_MAX:
            found.append(f"title is {len(self.title)} chars, over {TITLE_MAX}")
        if self.privacy not in PRIVACY:
            found.append(
                f"unknown privacy {self.privacy!r} — "
                f"choose from {', '.join(sorted(PRIVACY))}"
            )
        elif info and PRIVACY[self.privacy] not in info.privacy_level_options:
            # The usual cause is an unaudited client, where TikTok
            # offers only SELF_ONLY however the request is written.
            found.append(
                f"this account cannot post as {self.privacy!r} right now. "
                f"TikTok is offering: "
                f"{', '.join(info.privacy_level_options) or 'nothing'}"
            )
        return found


def creator_info(access_token: str) -> CreatorInfo:
    """Ask TikTok what this account may currently post.

    Called before every upload rather than cached: the answer changes
    when an audit completes, when the account switches type, or when
    TikTok rate-limits it, and a stale "yes" here posts to the wrong
    audience.
    """
    import requests

    resp = requests.post(
        f"{API}/post/publish/creator_info/query/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise TikTokError(
            f"creator_info failed ({resp.status_code}): {resp.text[:300]}"
        )
    payload = resp.json()
    err = (payload.get("error") or {}).get("code", "ok")
    if err not in {"ok", ""}:
        raise TikTokError(
            f"creator_info refused: {err} — "
            f"{(payload.get('error') or {}).get('message', '')}"
        )
    data = payload.get("data", {})
    return CreatorInfo(
        username=data.get("creator_username", ""),
        avatar_url=data.get("creator_avatar_url", ""),
        nickname=data.get("creator_nickname", ""),
        privacy_level_options=data.get("privacy_level_options", []),
        comment_disabled=data.get("comment_disabled", False),
        duet_disabled=data.get("duet_disabled", False),
        stitch_disabled=data.get("stitch_disabled", False),
        max_video_seconds=data.get("max_video_post_duration_sec", MAX_SECONDS),
    )


def post(
    meta: PostMeta,
    access_token: str,
    info: CreatorInfo | None = None,
    dry_run: bool = False,
) -> str:
    """Upload and post. Returns the publish id.

    The publish id is not a URL: TikTok processes asynchronously, and
    the video appears in the account some seconds to minutes later.
    """
    import requests

    info = info or creator_info(access_token)
    problems = meta.problems(info)
    if problems:
        raise TikTokError("cannot post:\n  " + "\n  ".join(problems))

    size = meta.video.stat().st_size
    if dry_run:
        log.info("dry run: would post %s (%.1fMB) as %s",
                 meta.video.name, size / 1e6, meta.privacy)
        return "dry-run"

    # One chunk. TikTok wants chunked uploads above 64MB; a vertical
    # short of half a minute is nowhere near that, and a chunking path
    # nothing exercises is a path that breaks silently.
    init = requests.post(
        f"{API}/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": meta.title,
                "privacy_level": PRIVACY[meta.privacy],
                "disable_comment": meta.disable_comment,
                "disable_duet": meta.disable_duet,
                "disable_stitch": meta.disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        },
        timeout=120,
    )
    if init.status_code != 200:
        raise TikTokError(f"init failed ({init.status_code}): {init.text[:300]}")

    payload = init.json()
    err = (payload.get("error") or {}).get("code", "ok")
    if err not in {"ok", ""}:
        raise TikTokError(
            f"init refused: {err} — "
            f"{(payload.get('error') or {}).get('message', '')}"
        )
    data = payload.get("data", {})
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id", "")
    if not upload_url:
        raise TikTokError(f"no upload_url in response: {init.text[:300]}")

    # PUT the bytes to the returned URL — not to the API host, and not
    # as multipart form data.
    blob = meta.video.read_bytes()
    put = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        data=blob,
        timeout=900,
    )
    if put.status_code not in {200, 201, 202}:
        raise TikTokError(f"upload failed ({put.status_code}): {put.text[:300]}")

    return publish_id


def status(publish_id: str, access_token: str) -> dict:
    """Where an upload got to.

    Posting is asynchronous, so a 200 from `post()` means TikTok
    accepted the bytes, not that anything is live.
    """
    import requests

    resp = requests.post(
        f"{API}/post/publish/status/fetch/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=60,
    )
    if resp.status_code != 200:
        raise TikTokError(f"status failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json().get("data", {})
