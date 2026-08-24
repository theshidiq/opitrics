"""Check a subject's shorts against each platform's requirements.

    python scripts/preflight.py --subject byd-racco

Runs before any credential exists, and is the only part of publishing
that can be verified without one. Everything it checks has a specific
way of going wrong on upload:

  - Colour tagging, because platforms re-encode and an unflagged file
    is a guess at the far end.
  - Duration, because each platform has different bounds and TikTok
    rejects under three seconds outright.
  - Faststart, because a file whose index sits at the end has to be
    read entirely before processing starts.
  - Loudness, because platforms normalise to about -14 LUFS and a
    quiet master gets pushed up, bringing its noise floor with it.

A pass here does not mean an upload will succeed — it means the file
is not the reason if it does not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

# Per platform: (min_seconds, max_seconds, label)
BOUNDS = {
    "TikTok": (3, 600, "3s–10min"),
    "Reels": (3, 900, "3s–15min"),
    "Shorts": (1, 180, "under 3min"),
}

# Platforms normalise to roughly this. Mastering far below it means the
# platform raises the whole track, noise floor included.
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 3.0


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=False,
    )
    return json.loads(out.stdout or "{}")


def loudness(video: Path) -> float | None:
    """Integrated LUFS, via one analysis pass."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(video),
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    # The JSON block is the last balanced {...} in a stream that also
    # carries progress lines and filter banners. Scanning back from the
    # final closing brace is what makes this reliable — an earlier
    # rfind("{") landed inside ffmpeg's own output and parsed nothing.
    text = proc.stderr
    end = text.rfind("}")
    start = text.rfind("{", 0, end) if end > 0 else -1
    if start < 0 or end < 0:
        return None
    try:
        raw = json.loads(text[start:end + 1]).get("input_i")
    except (ValueError, json.JSONDecodeError):
        return None
    # ffmpeg reports "-inf" for a silent track. float() parses that
    # happily into -inf and every comparison downstream then quietly
    # says "very quiet" rather than "there is no audio at all", which
    # is a different and much worse problem.
    if raw in ("-inf", "inf", None):
        return float("-inf")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def faststart(video: Path) -> bool:
    """True when the moov atom precedes the media data."""
    head = video.read_bytes()[:2_000_000]
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    if moov < 0:
        return False
    return mdat < 0 or moov < mdat


def check(video: Path, label: str) -> bool:
    info = probe(video)
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = info.get("format", {})

    if not v:
        print(f"  {RED}no video stream{RESET}")
        return False

    duration = float(fmt.get("duration", 0))
    width, height = int(v.get("width", 0)), int(v.get("height", 0))
    size_mb = int(fmt.get("size", 0)) / 1e6
    lufs = loudness(video)

    problems: list[str] = []
    notes: list[str] = []

    # ── frame ───────────────────────────────────────────────
    if (width, height) != (1080, 1920):
        problems.append(f"{width}x{height}, not 1080x1920")
    if v.get("codec_name") != "h264":
        problems.append(f"video codec {v.get('codec_name')}, not h264")
    if a and a.get("codec_name") != "aac":
        problems.append(f"audio codec {a.get('codec_name')}, not aac")
    if not a:
        problems.append("no audio stream")

    # ── colour ──────────────────────────────────────────────
    if v.get("pix_fmt") != "yuv420p":
        problems.append(
            f"pixel format {v.get('pix_fmt')}, not yuv420p — "
            "platforms re-encode and full-range shifts the picture"
        )
    unflagged = [
        name for name, key in (
            ("primaries", "color_primaries"),
            ("transfer", "color_transfer"),
            ("matrix", "color_space"),
        ) if v.get(key) in (None, "unknown", "")
    ]
    if unflagged:
        problems.append(f"colour {', '.join(unflagged)} unflagged")
    if v.get("color_range") not in (None, "tv"):
        problems.append(f"colour range {v.get('color_range')}, not tv")

    # ── delivery ────────────────────────────────────────────
    if not faststart(video):
        problems.append("moov atom is at the end — needs +faststart")

    # ── duration, per platform ──────────────────────────────
    for platform, (lo, hi, human) in BOUNDS.items():
        if not (lo <= duration <= hi):
            problems.append(
                f"{duration:.1f}s is outside {platform}'s {human}"
            )

    # ── loudness ────────────────────────────────────────────
    if lufs is None:
        notes.append("loudness could not be measured")
    elif lufs == float("-inf"):
        problems.append("the audio track is silent")
    elif abs(lufs - TARGET_LUFS) > LUFS_TOLERANCE:
        direction = "quiet" if lufs < TARGET_LUFS else "loud"
        notes.append(
            f"{lufs:.1f} LUFS is {abs(lufs - TARGET_LUFS):.1f}dB "
            f"{direction} of the ~{TARGET_LUFS:.0f} platforms normalise to"
        )

    ok = not problems
    mark = f"{GREEN}pass{RESET}" if ok else f"{RED}fail{RESET}"
    lufs_text = (
        "silent" if lufs == float("-inf")
        else f"{lufs:.1f} LUFS" if lufs is not None
        else "LUFS ?"
    )
    print(f"  {BOLD}{label:<11}{RESET} {mark}  "
          f"{DIM}{duration:5.1f}s  {size_mb:5.1f}MB  {lufs_text}{RESET}")
    for problem in problems:
        print(f"      {RED}·{RESET} {problem}")
    for note in notes:
        print(f"      {YELLOW}·{RESET} {note}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    root = paths.content_dir / "shorts"
    videos = sorted(root.glob("*/short.mp4"))
    if not videos:
        print(f"\nno shorts under {root} — run scripts/shorts.py first.\n")
        return 1

    print(f"\n{BOLD}{args.subject}{RESET} {DIM}· {len(videos)} short(s) "
          f"against TikTok, Reels and Shorts{RESET}\n")
    passed = sum(check(v, v.parent.name) for v in videos)
    print()
    if passed == len(videos):
        print(f"{GREEN}{BOLD}all {passed} ready to upload{RESET}\n")
        return 0
    print(f"{YELLOW}{passed}/{len(videos)} ready{RESET}  "
          f"{DIM}re-render the rest before uploading{RESET}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
