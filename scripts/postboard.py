"""Everything ready to post for one subject, on one page.

    python scripts/postboard.py --subject byd-racco

Built for posting by hand. The material already exists but is spread
across a dozen directories, and `thread.txt` gives you the words with
no indication of which image belongs to which post. This puts each post
next to its card with a copy button, and the shorts next to their
captions.

It shows what is WRONG as loudly as what is ready. A thread whose files
look finished can still be carrying a rounded count or a missing
sources link, and a page that only listed the content would invite
pasting exactly that. Anything with an unresolved warning is marked and
sorted last.

Read-only: it reads what the pipeline already produced and writes one
HTML file. Nothing here posts anything.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import subprocess
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import settings  # noqa: E402

# Shorts a human has judged unpublishable, which the automated check
# above cannot see. Both are recorded in STATUS.md with the measurement
# behind them. Delete an entry when the short is rebuilt and re-read,
# not when it merely looks fine.
KNOWN_BAD_SHORTS = {
    "defect": (
        "Beat 2 says the loudest complaint is range. Range ranks 39th of "
        "40 by size (n=239); the badge argument is rank 1 at 681. Needs a "
        "re-scope in angles.py, not a narration edit."
    ),
    "defenders": (
        "Beats 2 and 3 quote the sarcasm-flagged 'Encouraging purchase' "
        "cluster and narrate it as sincere support, with a motive nobody "
        "expressed. The comment is needling the reviewer."
    ),
}

CSS = """
:root{
  --bg:#FBFAF7; --card:#FFFFFF; --line:#DBD7CC; --soft:#E8E5DC;
  --ink:#1A1917; --ink-2:#4A473F; --ink-3:#807B6E;
  --accent:#8C2B18; --warn:#9A6B1F; --ok:#2C6E49;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",
  "Hiragino Sans","Noto Sans JP",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:40px 22px 100px}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:10px}
.eyebrow{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--ink-3);font-size:13.5px;margin:0;font-family:ui-monospace,monospace}

nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
  padding:12px 0;margin-bottom:26px;display:flex;gap:8px;flex-wrap:wrap;z-index:9}
nav a{font-family:ui-monospace,monospace;font-size:12px;text-decoration:none;
  color:var(--ink-2);border:1px solid var(--line);padding:5px 11px;background:var(--card)}
nav a:hover{border-color:var(--ink);color:var(--ink)}
nav a.bad{border-color:var(--accent);color:var(--accent)}

section{margin:0 0 46px;scroll-margin-top:70px}
h2{font-size:21px;margin:0 0 4px;display:flex;align-items:baseline;gap:11px}
h2 .k{font-family:ui-monospace,monospace;font-size:12px;color:var(--ink-3);
  font-weight:400;letter-spacing:.08em;text-transform:uppercase}
.headline{color:var(--ink-2);font-size:14.5px;margin:0 0 16px;font-style:italic}

.flags{border-left:2px solid var(--accent);background:#FCF3F1;padding:11px 15px;
  margin:0 0 18px;font-size:13.5px;color:var(--ink-2)}
.flags b{color:var(--accent)}
.flags ul{margin:6px 0 0;padding-left:18px}
.flags li{margin:2px 0}
.ready{border-left:2px solid var(--ok);background:#F0F7F2;padding:9px 15px;
  margin:0 0 18px;font-size:13.5px;color:var(--ink-2)}

.post{background:var(--card);border:1px solid var(--line);margin:0 0 12px;
  display:flex;gap:16px;padding:15px 16px;align-items:flex-start}
.post .n{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--ink-3);
  flex:none;width:34px;padding-top:3px}
.post .body{flex:1;min-width:0}
.post .txt{white-space:pre-wrap;font-size:15px}
.post .meta{margin-top:9px;font-family:ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-3);display:flex;gap:14px;align-items:center}
.post img{width:132px;flex:none;border:1px solid var(--soft);cursor:zoom-in}
.post img.big{width:100%;cursor:zoom-out}
button{font:inherit;font-size:11.5px;font-family:ui-monospace,monospace;
  border:1px solid var(--line);background:var(--bg);color:var(--ink-2);
  padding:3px 10px;cursor:pointer}
button:hover{border-color:var(--ink);color:var(--ink)}
button.done{border-color:var(--ok);color:var(--ok)}
.over{color:var(--accent);font-weight:700}

video{width:250px;border:1px solid var(--line);background:#000;display:block}
.short{display:flex;gap:18px;background:var(--card);border:1px solid var(--line);
  padding:16px;margin:0 0 12px}
.short .body{flex:1;min-width:0}
.short h3{margin:0 0 8px;font-size:16px}
.short .cap{white-space:pre-wrap;font-size:14.5px;color:var(--ink-2);
  background:var(--bg);border:1px solid var(--soft);padding:11px 13px;margin:9px 0}
"""


def _b64(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def thread_section(directory: Path, url: str) -> tuple[str, str, bool]:
    data = json.loads((directory / "thread.json").read_text(encoding="utf-8"))
    key = data.get("angle", directory.name)
    warnings = data.get("quote_warnings") or []

    if warnings:
        flags = (
            "<div class='flags'><b>Not ready to post.</b> The build flagged "
            f"{len(warnings)} problem(s), so check before pasting:<ul>"
            + "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
            + "</ul></div>"
        )
    else:
        flags = ("<div class='ready'>All checks passed. Quotes verified "
                 "against the corpus.</div>")

    rows: list[str] = []
    for post in data["posts"]:
        card = directory / f"{post['index']:02d}.png"
        n = len(post["text"])
        img = (f"<img src='{_b64(card, 'image/png')}' "
               "onclick='this.classList.toggle(\"big\")'>") if card.exists() else ""
        rows.append(f"""
        <div class="post">
          <div class="n">{post['index']}/{len(data['posts'])}</div>
          <div class="body">
            <div class="txt" id="t-{key}-{post['index']}">{html.escape(post['text'])}</div>
            <div class="meta">
              <button onclick="cp('t-{key}-{post['index']}',this)">copy text</button>
              <span class="{'over' if n > 280 else ''}">{n}/280</span>
              <span>{html.escape(post.get('kind', ''))}</span>
            </div>
          </div>
          {img}
        </div>""")

    body = f"""
    <section id="{key}">
      <h2>{html.escape(data.get('angle_title', key))} <span class="k">{key} · thread</span></h2>
      <p class="headline">{html.escape(data.get('headline', ''))}</p>
      {flags}
      {''.join(rows)}
    </section>"""
    return body, key, bool(warnings)


def _short_warnings(beats: list[dict], analysis: dict | None = None) -> list[str]:
    """Problems in a short's narration that would stop it shipping.

    Shorts have no equivalent of the thread gates, so a disqualified
    video looks identical to a finished one on disk. STATUS.md records
    two that cannot ship: `defect` narrates "range expectations dominate
    the chatter" for a theme ranked 39th of 40, and `defenders` narrates
    a sarcasm-flagged cluster as sincere support.

    This catches less than it looks like it does, and the limit is worth
    knowing before trusting a green board. It matches the theme's full
    label, and narration does not talk that way: `defect` says "the
    loudest complaint is about the range" where the label is "Real-world
    range expectations", so the claim goes through. Substring matching
    on "range" instead would fire on every mention of the word.

    So: a clean result here means nothing was caught, not that nothing
    is wrong. The shorts still need reading before they go out, and
    STATUS.md is the record of which ones are known bad.
    """
    if analysis is None:
        return []
    ranked = sorted(analysis.get("clusters", []), key=lambda c: -c["size"])
    total = len(ranked)
    rank = {c.get("llm_label", ""): i + 1 for i, c in enumerate(ranked)}
    flagged = {c.get("llm_label", "") for c in ranked if c.get("sarcasm_risk")}

    # Sentence by sentence: a superlative three beats away from a theme
    # name is not a claim about that theme, and matching across the whole
    # narration flagged shorts that were fine while missing one that was
    # not.
    import re

    sentences = [
        s.lower()
        for beat in beats
        for s in re.split(r"(?<=[.!?])\s+", beat.get("narration", ""))
    ]
    problems: list[str] = []

    # Spelled-out rounded totals. The thread gate catches "16,000"; a
    # short says "sixteen thousand", which is the same false claim in
    # words and passes every digit-based check.
    raw = analysis.get("totals", {}).get("clustered", 0)
    spoken_all = " ".join(b.get("narration", "") for b in beats).lower()
    for word, value in (("sixteen thousand", 16000),
                        ("fifteen thousand", 15000),
                        ("twenty thousand", 20000)):
        if word in spoken_all and raw and abs(value - raw) > 200:
            problems.append(
                f"narration says '{word}' where the figure is {raw:,}"
            )

    for label, position in rank.items():
        if not label:
            continue
        needle = label.lower()
        for sentence in sentences:
            if needle not in sentence:
                continue
            if position > total / 2 and re.search(
                r"\b(dominates?|dominant|biggest|largest|loudest|most "
                r"(?:common|argued|discussed))\b", sentence
            ):
                problems.append(
                    f"narration calls '{label}' dominant, but it ranks "
                    f"{position} of {total} by size"
                )
            if label in flagged and re.search(
                r"\b(sincere|genuinely|really means|actually means)\b",
                sentence,
            ):
                problems.append(
                    f"'{label}' is sarcasm-flagged and the narration reads "
                    "it as sincere"
                )
    return problems


def short_section(
    directory: Path, analysis: dict | None = None, url: str = ""
) -> tuple[str, str, bool]:
    video = directory / "short.mp4"
    script_file = directory / "script.json"
    if not video.exists() or not script_file.exists():
        return "", "", False
    data = json.loads(script_file.read_text(encoding="utf-8"))
    key = data.get("angle", directory.name)
    beats = data.get("beats", [])
    warnings = _short_warnings(beats, analysis)
    if key in KNOWN_BAD_SHORTS:
        warnings.insert(0, KNOWN_BAD_SHORTS[key])

    # A caption to paste with the upload. The opening beat plus the
    # sources line, not the whole narration concatenated: running every
    # beat together produced a paragraph cut mid-sentence, which is not
    # something anybody would post. The first beat is written to be the
    # hook, so it is already the right sentence.
    import re as _re

    opening = next((b.get("narration", "") for b in beats
                    if b.get("narration")), "")
    sentences = _re.split(r"(?<=[.!?])\s+", opening.strip())
    caption = " ".join(sentences[:2]).strip()
    if url:
        caption = f"{caption}\n\nEvery number links to the comment it came from. {url}"

    size = video.stat().st_size / 1e6
    if warnings:
        flags = (
            "<div class='flags'><b>Do not post this one.</b><ul>"
            + "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
            + "</ul></div>"
        )
    else:
        flags = ""

    return f"""
    <section id="s-{key}">
      <h2>{html.escape(data.get('angle_title', key))} <span class="k">{key} · short</span></h2>
      {flags}
      <div class="short">
        <video src="shorts/{key}/short.mp4" controls playsinline
               preload="metadata"></video>
        <div class="body">
          <h3>{_duration(video):.0f}s · {size:.1f}MB · 1080x1920</h3>
          <div class="cap" id="c-{key}">{html.escape(caption)}</div>
          <button onclick="cp('c-{key}',this)">copy caption</button>
          <div class="meta" style="margin-top:12px">
            <span>{directory / 'short.mp4'}</span>
          </div>
        </div>
      </div>
    </section>""", f"s-{key}", bool(warnings)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--sources-url", default="")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    paths = settings.workspace.subject(args.subject).ensure()
    content = paths.content_dir

    sections, links = [], []
    for directory in sorted((content / "threads").glob("*/")):
        if not (directory / "thread.json").exists():
            continue
        body, key, bad = thread_section(directory, args.sources_url)
        sections.append((bad, body))
        links.append(f"<a href='#{key}' class='{'bad' if bad else ''}'>{key}</a>")

    analysis = (json.loads(paths.analysis.read_text(encoding="utf-8"))
                if paths.analysis.exists() else None)
    for directory in sorted((content / "shorts").glob("*/")):
        body, anchor, bad = short_section(directory, analysis, args.sources_url)
        if body:
            sections.append((bad, body))
            links.append(
                f"<a href='#{anchor}' class='{'bad' if bad else ''}'>{anchor}</a>"
            )

    # Anything flagged sorts last, so the top of the page is what can
    # actually go out today.
    sections.sort(key=lambda s: s[0])
    ready = sum(1 for bad, _ in sections if not bad)

    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(args.subject)} — ready to post</title>
<style>{CSS}</style>
<div class="wrap">
  <header>
    <p class="eyebrow">post board</p>
    <h1>{html.escape(paths.display_name)}</h1>
    <p class="sub">{ready} of {len(sections)} ready · flagged items sorted last · nothing here posts anything</p>
  </header>
  <nav>{''.join(links)}</nav>
  {''.join(body for _, body in sections)}
</div>
<script>
function cp(id, btn) {{
  navigator.clipboard.writeText(document.getElementById(id).innerText).then(() => {{
    const was = btn.textContent;
    btn.textContent = 'copied'; btn.classList.add('done');
    setTimeout(() => {{ btn.textContent = was; btn.classList.remove('done'); }}, 1200);
  }});
}}
</script>
</html>"""

    out = content / "postboard.html"
    out.write_text(page, encoding="utf-8")
    print(f"\n  {out}")
    print(f"  {ready}/{len(sections)} ready to post\n")
    if not args.no_browser:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
