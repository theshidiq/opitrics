"""Review a short, then upload it to YouTube.

    python scripts/upload.py --subject byd-racco
    python scripts/upload.py --subject byd-racco --scope data --public
    python scripts/upload.py --subject byd-racco --dry-run

Opens a page showing the video, the title, the description and the
image credits. Nothing is uploaded until the button is pressed.

Uploads default to private. Watch it back on the platform before making
it public — YouTube's own player is the only place you will see it the
way a viewer does.
"""

from __future__ import annotations

import argparse
import base64
import html
import http.server
import json
import logging
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.analyze.llm import LLMClient  # noqa: E402
from opitrics.config import settings  # noqa: E402
from opitrics.publish import youtube as yt  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

PORT = 8422

METADATA_SYSTEM = """\
You write YouTube Shorts metadata for a channel that analyses what \
people actually say online about cars.

The title is the whole battle. It appears over the video in the Shorts \
feed and decides whether anyone stops. Write it as the finding, not as \
a description of the video.

  Weak:   "BYD Racco Comment Analysis"
  Strong: "16,000 comments. Most weren't about the car."

Rules:
- Title: under 70 characters. No clickbait the video does not deliver — \
a title the content contradicts costs more than the view was worth.
- Description: two or three short lines saying what was analysed and \
what was found, then the sources link, then the image credits verbatim \
as supplied. Credits are a licence condition, not a courtesy.
- Tags: 6 to 10, lowercase, specific. The car, the brand, the segment, \
the topic. No "viral", no "fyp".

Return JSON only."""


def write_metadata(
    client: LLMClient,
    display: str,
    narration: list[str],
    facts: dict,
    sources_url: str,
    credits: list[str],
) -> dict:
    instruction = (
        f"Write YouTube Shorts metadata for a video about the {display}.\n\n"
        "The narration, in order:\n"
        + "\n".join(f"  {i}. {line}" for i, line in enumerate(narration, 1))
        + "\n\nGround truth — do not contradict:\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
        + f"\n\nSources link to include: {sources_url or '(none yet)'}\n"
        + "Image credits to reproduce verbatim:\n"
        + "\n".join(f"  {c}" for c in credits)
        + "\n\n"
        '{"title":"...","description":"...","tags":["...","..."]}'
    )
    return client._chat(METADATA_SYSTEM, instruction, max_tokens=1200)


CSS = """
:root{--bg:#FBFAF7;--card:#fff;--line:#DBD7CC;--ink:#1A1917;
 --ink2:#4A473F;--ink3:#807B6E;--accent:#8C2B18;--ok:#2C6E49;--warn:#9A6B1F}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:40px 24px 90px;
 display:grid;grid-template-columns:340px 1fr;gap:36px;align-items:start}
header{grid-column:1/-1;border-bottom:2px solid var(--ink);padding-bottom:16px}
.eyebrow{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;
 text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-size:26px;margin:0;letter-spacing:-.015em}
video{width:100%;border:1px solid var(--line);background:#000;border-radius:3px}
.bar{grid-column:1/-1;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
 padding:14px 0;border-bottom:1px solid var(--line);position:sticky;top:0;
 background:var(--bg);z-index:5}
button{padding:10px 20px;border:none;background:var(--ink);color:var(--bg);
 font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
button:hover{background:var(--accent)}
button.ghost{background:none;color:var(--ink);border:1px solid var(--ink)}
button:disabled{background:var(--line);color:var(--ink3);cursor:not-allowed}
.meta{font-family:ui-monospace,monospace;font-size:12px;color:var(--ink3);
 margin-left:auto}
.field{margin-bottom:20px}
.field label{display:block;font-family:ui-monospace,monospace;font-size:10.5px;
 letter-spacing:.11em;text-transform:uppercase;color:var(--ink3);margin-bottom:6px}
.field .val{background:var(--card);border:1px solid var(--line);padding:12px 15px;
 white-space:pre-wrap;font-size:15px;line-height:1.55}
.count{float:right;font-family:ui-monospace,monospace;font-size:11px;color:var(--ink3)}
.tags{display:flex;gap:7px;flex-wrap:wrap}
.tag{font-family:ui-monospace,monospace;font-size:12px;padding:3px 9px;
 border:1px solid var(--line);background:var(--card);color:var(--ink2)}
.note{border-left:2px solid var(--warn);background:#FBF6EC;padding:13px 17px;
 font-size:14.5px;color:var(--ink2);margin:0 0 20px}
.note.ok{border-left-color:var(--ok);background:#F0F7F2}
.note b{color:var(--ink)}
#status{grid-column:1/-1;font-family:ui-monospace,monospace;font-size:13px}
"""


def build_page(
    video_b64: str,
    meta: yt.VideoMeta,
    channel: str | None,
    credits: list[str],
    duration: float,
    size_mb: float,
) -> str:
    issues = meta.problems()
    tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in meta.tags)

    warn = ""
    if issues:
        warn = (
            '<div class="note"><b>Metadata problems</b><br>'
            + "<br>".join(html.escape(i) for i in issues)
            + "</div>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload review</title><style>{CSS}</style></head><body><div class="wrap">

<header>
  <p class="eyebrow">Review before uploading</p>
  <h1>{html.escape(meta.title)}</h1>
</header>

<div class="bar">
  <button id="go"{' disabled' if issues else ''}>
    Upload as {html.escape(meta.privacy)}
  </button>
  <button class="ghost" onclick="window.close()">Cancel</button>
  <span class="meta">
    {duration:.0f}s · {size_mb:.1f} MB · ~{yt.UPLOAD_COST:,} quota units
    {f' · {html.escape(channel)}' if channel else ''}
  </span>
</div>

<div>
  <video src="data:video/mp4;base64,{video_b64}" controls playsinline></video>
</div>

<div>
  {warn}
  <div class="note{'' if meta.privacy != 'private' else ' ok'}">
    {'<b>Uploading as private.</b> Watch it back on YouTube before making it public — their player is the only place you see it as a viewer does.'
     if meta.privacy == 'private' else
     f'<b>This will be {html.escape(meta.privacy)} immediately.</b> Read the title as a stranger would first.'}
  </div>

  <div class="field">
    <label>Title <span class="count">{len(meta.title)}/{yt.TITLE_MAX}</span></label>
    <div class="val">{html.escape(meta.title)}</div>
  </div>

  <div class="field">
    <label>Description <span class="count">{len(meta.description)}/{yt.DESCRIPTION_MAX}</span></label>
    <div class="val">{html.escape(meta.description)}</div>
  </div>

  <div class="field">
    <label>Tags</label>
    <div class="tags">{tags}</div>
  </div>

  {'<div class="field"><label>Image credits — licence condition</label><div class="val">'
   + html.escape(chr(10).join(credits)) + '</div></div>' if credits else ''}
</div>

<div id="status"></div>

<script>
document.getElementById('go').onclick = async () => {{
  const b = document.getElementById('go');
  const s = document.getElementById('status');
  b.disabled = true; s.textContent = 'uploading…';
  try {{
    const r = await fetch('/upload', {{method:'POST'}});
    const d = await r.json();
    if (d.ok) {{
      s.innerHTML = 'uploaded → <a href="' + d.url + '" target="_blank">' + d.url + '</a>';
    }} else {{
      s.textContent = 'failed: ' + (d.error || 'unknown');
      b.disabled = false;
    }}
  }} catch (e) {{ s.textContent = 'failed: ' + e; b.disabled = false; }}
}};
</script>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--scope", default="data",
                    help="which short to upload (see content/shorts/)")
    ap.add_argument("--public", action="store_true",
                    help="publish publicly rather than private")
    ap.add_argument("--unlisted", action="store_true")
    ap.add_argument("--sources-url", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the metadata and preview, never upload")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject)
    short_dir = paths.content_dir / "shorts" / args.scope
    video = short_dir / "short.mp4"
    if not video.exists():
        print(f"\n{video} not found — run scripts/datashort.py first.\n")
        return 1

    display = paths.display_name
    script_json = short_dir / "script.json"
    narration: list[str] = []
    if script_json.exists():
        data = json.loads(script_json.read_text(encoding="utf-8"))
        narration = [b.get("narration", "") for b in data.get("beats", [])]
    if not narration:
        txt = short_dir / "script.txt"
        if txt.exists():
            narration = [
                line.split("VO:", 1)[1].strip()
                for line in txt.read_text(encoding="utf-8").splitlines()
                if "VO:" in line
            ]

    # Credits are a licence condition on the CC BY images, so they are
    # read from the manifest rather than retyped.
    credits: list[str] = []
    manifest = settings.database_path.parent / "imagery" / args.subject / "credits.json"
    if manifest.exists():
        seen: set[str] = set()
        for record in json.loads(manifest.read_text(encoding="utf-8")):
            credit = record.get("credit", "")
            if credit and credit not in seen:
                seen.add(credit)
                credits.append(credit)

    analysis = json.loads(paths.analysis.read_text(encoding="utf-8"))
    totals = analysis["totals"]
    car_pct = round(100 * totals["car"] / max(totals["clustered"], 1))

    # ── metadata ────────────────────────────────────────────
    print(f"\n{BOLD}Writing metadata{RESET} {DIM}{display}{RESET}")
    try:
        client = LLMClient(settings.require_llm())
        written = write_metadata(
            client, display, narration,
            {
                "comments_analysed": totals["clustered"],
                "share_about_the_car_pct": car_pct,
                "note": f"{car_pct}% of comments ARE about the car; "
                        f"{100 - car_pct}% are not.",
            },
            args.sources_url, credits,
        )
    except Exception as exc:  # noqa: BLE001 - fall back to something usable
        print(f"  {YELLOW}metadata generation failed: {exc}{RESET}")
        written = {}

    privacy = "public" if args.public else "unlisted" if args.unlisted else "private"
    description = written.get("description", "").strip()
    if credits and not any(c.split("·")[0].strip() in description for c in credits):
        description = (description + "\n\nImage credits:\n"
                       + "\n".join(credits)).strip()

    meta = yt.VideoMeta(
        title=written.get("title", f"{display} — what the comments say")[:yt.TITLE_MAX],
        description=description,
        tags=[str(t).lower() for t in written.get("tags", [])][:12],
        privacy=privacy,
    )

    print(f"  {BOLD}{meta.title}{RESET} {DIM}{len(meta.title)}/{yt.TITLE_MAX}{RESET}")
    for issue in meta.problems():
        print(f"  {RED}·{RESET} {issue}")

    # ── credentials ─────────────────────────────────────────
    creds = None
    channel = None
    if not args.dry_run:
        try:
            creds = yt.authorise()
            channel = yt.channel_name(creds)
            print(f"  {DIM}channel:{RESET} {BOLD}{channel}{RESET}")
        except yt.UploadError as exc:
            print(f"\n{YELLOW}{exc}{RESET}\n")
            return 1

    # ── preview ─────────────────────────────────────────────
    size_mb = video.stat().st_size / 1_048_576
    duration = 0.0
    try:
        from opitrics.render.video import probe_duration

        duration = probe_duration(video)
    except Exception:  # noqa: BLE001 - the preview does not need it
        pass

    if size_mb > 60:
        print(f"  {YELLOW}video is {size_mb:.0f} MB — the preview embeds it "
              f"as base64, which will be slow{RESET}")

    page = build_page(
        base64.b64encode(video.read_bytes()).decode(),
        meta, channel, credits, duration, size_mb,
    )
    (short_dir / "upload-preview.html").write_text(page, encoding="utf-8")

    outcome: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:  # noqa: A003
            pass

        def do_GET(self) -> None:
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/upload":
                self.send_error(404)
                return
            if args.dry_run:
                self._json({"ok": True, "url": "(dry run — nothing uploaded)"})
                outcome.update({"ok": True, "dry": True})
                done.set()
                return

            print(f"\n{BOLD}Approved — uploading{RESET}")
            try:
                result = yt.upload(
                    video, meta, creds,
                    on_progress=lambda p: print(
                        f"  {DIM}{p * 100:.0f}%{RESET}", end="\r", flush=True
                    ),
                )
            except yt.UploadError as exc:
                outcome.update({"ok": False, "error": str(exc)})
                self._json({"ok": False, "error": str(exc)})
                done.set()
                return

            yt.write_receipt(result, short_dir / "posted-youtube.json", args.subject)
            outcome.update({"ok": True, "result": result, "url": result.url})
            self._json({"ok": True, "url": result.url})
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
        print(f"{DIM}nothing uploads until you press the button — "
              f"Ctrl-C to cancel{RESET}\n")
        if not args.no_browser:
            webbrowser.open(url)

        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            done.wait()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Cancelled — nothing was uploaded.{RESET}\n")
            return 0
        server.shutdown()

    if outcome.get("dry"):
        print(f"{DIM}dry run — nothing uploaded{RESET}\n")
        return 0
    if outcome.get("ok"):
        print(f"\n{GREEN}{BOLD}Uploaded{RESET} {outcome['url']}")
        print(f"{DIM}privacy: {meta.privacy}{RESET}\n")
        return 0

    print(f"\n{RED}Failed:{RESET} {outcome.get('error', 'unknown')}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
