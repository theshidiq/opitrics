"""Review a short in the browser, then post it to TikTok.

    python scripts/tiktok.py --subject byd-racco --angle quotes --dry-run
    python scripts/tiktok.py --subject byd-racco --angle quotes

Nothing is sent until the button in the page is pressed. `--dry-run`
renders the page and simulates the call, which is the only way to
exercise this without credentials.

Posting defaults to private. TikTok forces private anyway until the
Content Posting audit clears, but the default does not rely on that —
the audit will one day pass, and a default that quietly becomes
"public" on that day is a trap.
"""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.publish import tiktok as tk  # noqa: E402
from opitrics.publish.tiktok_preview import build_preview  # noqa: E402
from opitrics.render.angles import ANGLES  # noqa: E402

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def offline_info() -> tk.CreatorInfo:
    """What an unaudited client looks like, for --dry-run without keys.

    Deliberately the restricted case rather than an optimistic one: a
    dry run that shows a public post, and a real run that silently does
    not, is worse than no preview at all.
    """
    return tk.CreatorInfo(
        username="your-account",
        avatar_url="",
        nickname="Your account",
        privacy_level_options=["SELF_ONLY"],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--angle", default="quotes", choices=sorted(ANGLES))
    ap.add_argument("--title", help="caption; defaults to the angle title")
    ap.add_argument("--privacy", default="private", choices=sorted(tk.PRIVACY),
                    help="what to ask for; TikTok may offer less")
    ap.add_argument("--dry-run", action="store_true",
                    help="render the page and simulate, no API calls")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    short_dir = paths.content_dir / "shorts" / args.angle
    video = short_dir / "short.mp4"
    if not video.exists():
        print(f"\n{video} not found — run scripts/shorts.py first.\n")
        return 1

    script_path = short_dir / "script.json"
    script = json.loads(script_path.read_text(encoding="utf-8")) \
        if script_path.exists() else {}
    beats = script.get("beats", [])
    duration = float(script.get("duration", 0.0))
    title = args.title or script.get("angle_title") or args.subject

    warnings: list[str] = []

    # ── who are we posting as, and what may we post ─────────
    token = (settings.tiktok_access_token or "").strip() \
        if hasattr(settings, "tiktok_access_token") else ""
    if not token:
        import os

        token = (os.getenv("TIKTOK_ACCESS_TOKEN") or "").strip()

    if token:
        try:
            info = tk.creator_info(token)
        except tk.TikTokError as exc:
            print(f"{RED}{exc}{RESET}")
            return 1
    elif args.dry_run:
        info = offline_info()
        warnings.append(
            "No TIKTOK_ACCESS_TOKEN, so the account shown is a placeholder. "
            "The real one may allow more or less than this."
        )
    else:
        print(f"\n{RED}TIKTOK_ACCESS_TOKEN is not set.{RESET}\n"
              f"  developers.tiktok.com → your app → Content Posting API\n"
              f"  Then put it in .env, or use --dry-run to preview.\n")
        return 1

    # What TikTok will actually do, as opposed to what was asked for.
    wanted = tk.PRIVACY[args.privacy]
    if wanted in info.privacy_level_options:
        resolved = wanted
    elif info.privacy_level_options:
        resolved = "SELF_ONLY" if "SELF_ONLY" in info.privacy_level_options \
            else info.privacy_level_options[0]
        warnings.append(
            f"Asked to post as {args.privacy!r}, but this account is not "
            f"offered that. It will be posted as "
            f"{resolved.lower().replace('_', ' ')} instead."
        )
    else:
        print(f"\n{RED}TikTok is not offering any privacy level for this "
              f"account — it cannot post right now.{RESET}\n")
        return 1

    if duration and duration > info.max_video_seconds:
        warnings.append(
            f"{duration:.0f}s is longer than the {info.max_video_seconds}s "
            f"this account may post."
        )

    meta = tk.PostMeta(
        video=video,
        title=title,
        privacy=args.privacy if resolved == wanted else "private",
    )
    for problem in meta.problems(info):
        warnings.append(problem)

    html_page = build_preview(
        video=video, title=title, privacy=wanted, resolved_privacy=resolved,
        info=info, subject=args.subject, angle=args.angle,
        duration=duration or 0.0, beats=beats, warnings=warnings,
    )
    preview_path = short_dir / "tiktok-preview.html"
    preview_path.write_text(html_page, encoding="utf-8")

    # ── serve it and wait ───────────────────────────────────
    outcome: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: A003
            pass

        def do_GET(self) -> None:
            body = html_page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/approve":
                self.send_error(404)
                return
            print(f"\n{BOLD}Approved — uploading{RESET}")
            try:
                publish_id = tk.post(
                    meta, token, info=info, dry_run=args.dry_run or not token,
                )
            except Exception as exc:  # noqa: BLE001 - report to the page
                payload = {"ok": False, "error": str(exc)}
                outcome.update(payload)
                self._json(payload)
                done.set()
                return

            where = resolved.lower().replace("_", " ")
            payload = {
                "ok": True,
                "message": (
                    f"accepted as {where} · id {publish_id} · "
                    "TikTok processes asynchronously"
                ),
            }
            outcome.update(payload, publish_id=publish_id)
            self._json(payload)
            done.set()

        def _json(self, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    print(f"\n{BOLD}{args.subject} · {args.angle}{RESET} "
          f"{DIM}{duration:.1f}s{RESET}")
    if not info.can_post_public:
        print(f"{YELLOW}unaudited client — this will be visible to you "
              f"only{RESET}")
    for w in warnings:
        print(f"{YELLOW}· {w}{RESET}")
    if args.dry_run:
        print(f"{DIM}dry run — nothing will be sent{RESET}")

    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        httpd.timeout = 1
        url = f"http://127.0.0.1:{args.port}/"
        print(f"\n{BOLD}Review it:{RESET} {url}")
        print(f"{DIM}nothing is sent until you press the button. "
              f"ctrl-c to walk away.{RESET}\n")
        webbrowser.open(url)
        try:
            while not done.is_set():
                httpd.handle_request()
        except KeyboardInterrupt:
            print(f"\n{DIM}left unposted.{RESET}\n")
            return 1

    if not outcome.get("ok"):
        print(f"\n{RED}{outcome.get('error', 'failed')}{RESET}\n")
        return 1

    print(f"\n{GREEN}{BOLD}{outcome['message']}{RESET}")
    print(f"{DIM}check the TikTok app — a publish id is not a live video{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
