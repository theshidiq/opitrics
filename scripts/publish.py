"""Review a thread in the browser, then post it to X.

    python scripts/publish.py --subject byd-racco
    python scripts/publish.py --subject byd-racco --dry-run

Opens a local page showing every post exactly as it will appear, with
its card. Nothing reaches X until the button is pressed.
"""

from __future__ import annotations

import argparse
import http.server
import json
import logging
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402
from opitrics.publish.preview import build_preview  # noqa: E402
from opitrics.publish.x import (  # noqa: E402
    PublishError,
    XCredentials,
    XPublisher,
    write_receipt,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

PORT = 8421


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--angle", default="car",
                    help="which thread to publish (see content/threads/)")
    ap.add_argument("--dry-run", action="store_true",
                    help="render the preview and simulate posting, no API calls")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject)
    tp = paths.thread(args.angle)
    if not tp.json.exists():
        available = [t.angle for t in paths.existing_threads()]
        print(f"\n{tp.json} not found.")
        if available:
            print(f"Available angles: {', '.join(available)}")
        else:
            print("Run scripts/thread.py first.")
        print()
        return 1

    if tp.posted:
        receipt = json.loads(tp.receipt.read_text(encoding="utf-8"))
        print(f"\n{YELLOW}This angle was already posted{RESET} "
              f"{DIM}{receipt.get('posted_at', '')}{RESET}")
        print(f"{DIM}{receipt.get('thread_url', '')}{RESET}")
        if input("Post it again? [y/N] ").strip().lower() != "y":
            print()
            return 0

    thread = json.loads(tp.json.read_text(encoding="utf-8"))
    posts = thread.get("posts", [])
    if not posts:
        print(f"\n{RED}Thread has no posts.{RESET}\n")
        return 1

    # ── credentials and identity ────────────────────────────
    publisher = None
    account = None
    if not args.dry_run:
        try:
            publisher = XPublisher(XCredentials.from_env())
            account = publisher.whoami()
        except PublishError as exc:
            print(f"\n{YELLOW}{exc}{RESET}\n")
            return 1
        except Exception as exc:  # noqa: BLE001 - auth failures vary
            print(f"\n{RED}Could not authenticate with X: {exc}{RESET}\n")
            return 1
        print(f"\n{DIM}authenticated as{RESET} {BOLD}@{account}{RESET}")

    warnings = thread.get("quote_warnings", [])
    over = [p for p in posts if len(p.get("text", "")) > 280]
    if over:
        print(f"{RED}{len(over)} post(s) exceed 280 characters.{RESET}")

    # Attach card filenames so the publisher knows what to upload.
    for post in posts:
        card = tp.card(post["index"])
        post["media_path"] = card.name if card.exists() else None

    html = build_preview(thread, tp.root, args.subject, account, warnings)
    preview_path = tp.preview
    preview_path.write_text(html, encoding="utf-8")

    # ── serve the preview ───────────────────────────────────
    outcome: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: A003 - silence the default log
            pass

        def do_GET(self) -> None:
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/approve":
                self.send_error(404)
                return

            print(f"\n{BOLD}Approved — posting{RESET}")
            try:
                if args.dry_run:
                    from opitrics.publish.x import XPublisher as _X

                    result = _X.__new__(_X).post_thread(
                        posts, media_dir=tp.root, dry_run=True
                    )
                else:
                    result = publisher.post_thread(posts, media_dir=tp.root)
            except Exception as exc:  # noqa: BLE001 - report to the page
                payload = {"ok": False, "error": str(exc)}
                outcome.update(payload)
                self._json(payload)
                done.set()
                return

            write_receipt(result, tp.receipt, args.subject)
            payload = (
                {"ok": True, "url": result.thread_url}
                if result.complete
                else {"ok": False, "error": result.error}
            )
            outcome.update({"result": result, **payload})
            self._json(payload)
            done.set()

        def _json(self, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"\n{BOLD}Review{RESET} {url}")
        print(f"{DIM}nothing posts until you press the button — Ctrl-C to cancel{RESET}\n")

        if not args.no_browser:
            webbrowser.open(url)

        thread_srv = threading.Thread(target=server.serve_forever, daemon=True)
        thread_srv.start()
        try:
            done.wait()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Cancelled — nothing was posted.{RESET}\n")
            return 0
        server.shutdown()

    # ── report ──────────────────────────────────────────────
    result = outcome.get("result")
    if outcome.get("ok") and result:
        print(f"{GREEN}{BOLD}Posted{RESET} {len(result.posted)} post(s)")
        print(f"{result.thread_url}\n")
        return 0

    if result and result.posted:
        print(f"{YELLOW}Partial thread posted{RESET} — "
              f"{len(result.posted)} of {len(posts)} went out")
        print(f"{DIM}stopped at post {result.failed_at}: {result.error}{RESET}")
        print(f"{DIM}receipt: {tp.receipt}{RESET}\n")
        return 1

    print(f"{RED}Failed:{RESET} {outcome.get('error', 'unknown')}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
