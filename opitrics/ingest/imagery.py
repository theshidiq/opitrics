"""Freely-licensed photographs of the car, from Wikimedia Commons.

Manufacturer press images are the obvious source and the wrong one:
their terms are usually editorial-only, which excludes monetised video.
Commons is the opposite — every file states its licence, and the ones
worth using are CC0 or CC BY, both of which permit commercial use.

CC BY requires attribution, and attribution that is easy to forget is
attribution that gets forgotten. So the licence travels with the file
from download to render, and a credit line is generated rather than
remembered.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

API = "https://commons.wikimedia.org/w/api.php"
UA = "Opitrics/0.1 (comment analysis; contact via GitHub theshidiq/opitrics)"

# Licences that permit commercial use. Anything else is skipped rather
# than downloaded and left for someone to check later.
COMMERCIAL_OK = re.compile(
    r"^(CC0|CC BY(?!-NC)|public domain|PD|Attribution)", re.IGNORECASE
)

# Licences that additionally permit use with attribution but require
# derivatives to carry the same licence. Usable, but worth flagging.
SHARE_ALIKE = re.compile(r"SA", re.IGNORECASE)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


@dataclass
class CommonsImage:
    title: str
    url: str
    width: int
    height: int
    license: str
    author: str
    page: str
    local: Path | None = None

    @property
    def needs_attribution(self) -> bool:
        return not self.license.upper().startswith(("CC0", "PUBLIC DOMAIN", "PD"))

    @property
    def share_alike(self) -> bool:
        return bool(SHARE_ALIKE.search(self.license))

    @property
    def credit(self) -> str:
        """The line to put on screen or in the description."""
        if not self.needs_attribution:
            return f"{self.author} · {self.license}"
        return f"© {self.author} · {self.license} · Wikimedia Commons"

    @property
    def landscape(self) -> bool:
        return self.width >= self.height


def search_images(
    query: str,
    limit: int = 20,
    min_width: int = 1200,
    commercial_only: bool = True,
) -> list[CommonsImage]:
    """Find images for a subject, by category first then by search.

    A Commons *category* is curated and almost always better than a
    keyword search, which returns anything whose description mentions
    the term. The search is a fallback for models that have no category
    yet — which is most new cars.
    """
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = UA

    files = _category_members(session, query)
    if not files:
        files = _search_files(session, query, limit)
    if not files:
        return []

    out: list[CommonsImage] = []
    # imageinfo takes up to 50 titles per call.
    for start in range(0, len(files), 50):
        batch = files[start : start + 50]
        resp = session.get(
            API,
            params={
                "action": "query",
                "titles": "|".join(batch),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "iiextmetadatafilter": "LicenseShortName|Artist|UsageTerms",
                "format": "json",
            },
            timeout=45,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("url"):
                continue
            meta = info.get("extmetadata", {})
            licence = _strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            author = _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown"

            if commercial_only and not COMMERCIAL_OK.match(licence):
                log.debug("skipping %s — %s", page.get("title"), licence)
                continue
            if info.get("width", 0) < min_width:
                continue

            out.append(
                CommonsImage(
                    title=page.get("title", "")[5:],
                    url=info["url"],
                    width=info.get("width", 0),
                    height=info.get("height", 0),
                    license=licence or "unknown",
                    author=author[:80],
                    page=info.get("descriptionurl", ""),
                )
            )

    # Prefer CC0 — no attribution to carry — then larger images.
    out.sort(key=lambda i: (i.needs_attribution, -i.width))
    return out[:limit]


def _category_members(session, query: str) -> list[str]:
    """Files in a Commons category matching the subject name."""
    for candidate in (query, query.replace("-", " ").title()):
        resp = session.get(
            API,
            params={
                "action": "query",
                "generator": "categorymembers",
                "gcmtitle": f"Category:{candidate}",
                "gcmtype": "file",
                "gcmlimit": 50,
                "format": "json",
            },
            timeout=45,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        titles = [p["title"] for p in pages.values() if p.get("title")]
        if titles:
            log.info("Category:%s — %d file(s)", candidate, len(titles))
            return titles
    return []


def _search_files(session, query: str, limit: int) -> list[str]:
    resp = session.get(
        API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f'{query} filetype:bitmap',
            "srnamespace": 6,
            "srlimit": min(limit * 2, 50),
            "format": "json",
        },
        timeout=45,
    )
    results = resp.json().get("query", {}).get("search", [])
    log.info("search %r — %d file(s)", query, len(results))
    return [r["title"] for r in results]


def download(images: list[CommonsImage], out_dir: Path) -> list[CommonsImage]:
    """Fetch the files and record what came with what licence."""
    import requests

    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = UA

    kept: list[CommonsImage] = []
    for i, image in enumerate(images, 1):
        # Take the extension from the file title, not the URL: Commons
        # appends analytics parameters, so Path(url).suffix returns the
        # tail of a query string rather than ".jpg".
        suffix = Path(image.title).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        target = out_dir / f"{i:02d}{suffix}"
        for attempt in range(2):
            try:
                resp = session.get(image.url, timeout=90)
                if resp.status_code == 429:
                    time.sleep(4)
                    continue
                resp.raise_for_status()
                target.write_bytes(resp.content)
                break
            except Exception as exc:  # noqa: BLE001 - one bad file is not fatal
                if attempt:
                    log.warning("could not fetch %s: %s", image.title, exc)
        else:
            continue
        if not target.exists():
            continue
        image.local = target
        kept.append(image)

        # Wikimedia rate-limits bulk downloads and returns 429 after a
        # handful of rapid requests. A short pause between files is
        # cheaper than the retry logic the alternative needs.
        if i < len(images):
            time.sleep(1.2)

    # The manifest is the record that makes attribution possible later.
    (out_dir / "credits.json").write_text(
        json.dumps(
            [
                {
                    "file": img.local.name,
                    "title": img.title,
                    "license": img.license,
                    "author": img.author,
                    "credit": img.credit,
                    "needs_attribution": img.needs_attribution,
                    "share_alike": img.share_alike,
                    "source": img.page,
                }
                for img in kept
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = ["Image credits", ""]
    for img in kept:
        lines.append(f"{img.local.name}  {img.credit}")
        lines.append(f"    {img.page}")
    (out_dir / "CREDITS.txt").write_text("\n".join(lines), encoding="utf-8")

    return kept
