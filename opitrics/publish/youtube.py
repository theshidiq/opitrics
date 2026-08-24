"""Upload a short to YouTube.

Fetching comments needs only an API key; uploading acts on behalf of a
channel and therefore needs OAuth. The two are separate credentials and
separate flows, which is the first thing that trips people up.

A Short is not a distinct upload type — it is a normal video that
YouTube classifies as a Short because it is vertical and under three
minutes. Nothing here asks for one; the format does the work.

Quota is the real constraint: an upload costs roughly 1,600 units
against a 10,000/day allowance shared with comment fetching. Six
uploads a day, and every one of them competes with the analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Upload needs write access to the channel. Deliberately not the
# broader youtube scope: this pipeline never needs to read or modify
# anything else on the account.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

UPLOAD_COST = 1600
DAILY_QUOTA = 10_000

# YouTube truncates beyond these; better to know before uploading.
TITLE_MAX = 100
DESCRIPTION_MAX = 5000
TAGS_MAX_CHARS = 500


class UploadError(RuntimeError):
    """Raised when credentials are missing or the upload fails."""


@dataclass
class VideoMeta:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    # "private" until you have watched it back on the platform;
    # "public" only when you mean it.
    privacy: str = "private"
    category_id: str = "2"          # Autos & Vehicles
    made_for_kids: bool = False

    def problems(self) -> list[str]:
        """Anything YouTube will reject or silently truncate."""
        issues: list[str] = []
        if not self.title.strip():
            issues.append("title is empty")
        if len(self.title) > TITLE_MAX:
            issues.append(f"title is {len(self.title)} chars (limit {TITLE_MAX})")
        if len(self.description) > DESCRIPTION_MAX:
            issues.append(
                f"description is {len(self.description)} chars (limit {DESCRIPTION_MAX})"
            )
        if "<" in self.title or ">" in self.title:
            issues.append("title contains angle brackets, which YouTube rejects")
        tag_chars = sum(len(t) for t in self.tags)
        if tag_chars > TAGS_MAX_CHARS:
            issues.append(f"tags total {tag_chars} chars (limit {TAGS_MAX_CHARS})")
        if self.privacy not in {"private", "unlisted", "public"}:
            issues.append(f"privacy must be private, unlisted or public — got {self.privacy!r}")
        return issues

    def as_body(self) -> dict:
        return {
            "snippet": {
                "title": self.title[:TITLE_MAX],
                "description": self.description[:DESCRIPTION_MAX],
                "tags": self.tags,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy,
                "selfDeclaredMadeForKids": self.made_for_kids,
            },
        }


@dataclass
class UploadResult:
    video_id: str
    url: str
    privacy: str
    uploaded_at: str


def credentials_path() -> Path:
    """Where the OAuth client secret is expected."""
    import os

    override = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".opitrics" / "youtube-client-secret.json"


def token_path() -> Path:
    return Path.home() / ".opitrics" / "youtube-token.json"


def authorise(interactive: bool = True):
    """Return credentials, running the consent flow once if needed.

    The token is cached, so the browser opens on first use and never
    again unless it is revoked.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = token_path()
    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not interactive:
        raise UploadError("no valid token, and interactive consent is disabled")

    secret = credentials_path()
    if not secret.exists():
        raise UploadError(
            f"OAuth client secret not found at {secret}\n"
            "  1. console.cloud.google.com → your project → Credentials\n"
            "  2. Create credentials → OAuth client ID → Desktop app\n"
            "  3. Download the JSON and save it to that path\n"
            "  (an API key is not enough — uploading acts as your channel)"
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


def channel_name(creds) -> str:
    """Which channel is about to be uploaded to.

    Worth confirming before publishing — an upload to the wrong channel
    is not something a delete fully undoes.
    """
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise UploadError("the authorised account has no YouTube channel")
    return items[0]["snippet"]["title"]


def upload(
    video: Path,
    meta: VideoMeta,
    creds=None,
    on_progress=None,
) -> UploadResult:
    """Upload the file. Resumable, because these are tens of megabytes."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not video.exists():
        raise UploadError(f"video not found: {video}")

    issues = meta.problems()
    if issues:
        raise UploadError("metadata rejected:\n  " + "\n  ".join(issues))

    creds = creds or authorise()
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(
        str(video), chunksize=4 * 1024 * 1024, resumable=True, mimetype="video/mp4"
    )
    request = yt.videos().insert(
        part="snippet,status", body=meta.as_body(), media_body=media
    )

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except Exception as exc:  # noqa: BLE001 - surface whatever the API said
            raise UploadError(f"upload failed: {exc}") from exc
        if status and on_progress:
            on_progress(status.progress())

    video_id = response["id"]
    return UploadResult(
        video_id=video_id,
        url=f"https://youtube.com/shorts/{video_id}",
        privacy=meta.privacy,
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
    )


def write_receipt(result: UploadResult, path: Path, subject: str) -> None:
    """Record what went out, so a published video can be found again."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "subject": subject,
                "platform": "youtube",
                "video_id": result.video_id,
                "url": result.url,
                "privacy": result.privacy,
                "uploaded_at": result.uploaded_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
