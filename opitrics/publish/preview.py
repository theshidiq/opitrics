"""Render a thread as it will appear, for review before publishing.

The point of this page is to make problems visible: a quote that reads
badly out of context, a post over the character limit, a sentiment claim
the analysis itself flagged as unreliable. Approval happens here or not
at all.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

LIMIT = 280

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
.wrap{max-width:720px;margin:0 auto;padding:44px 22px 90px}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:8px}
.eyebrow{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-size:27px;line-height:1.2;margin:0 0 10px;letter-spacing:-.015em}
.sub{color:var(--ink-3);font-size:14px;margin:0;
  font-family:ui-monospace,monospace}
.bar{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
  padding:14px 0;margin-bottom:22px;z-index:5;display:flex;gap:12px;
  align-items:center;flex-wrap:wrap}
.cost{font-family:ui-monospace,monospace;font-size:12px;color:var(--ink-3);
  margin-left:auto}
button{padding:10px 20px;border:none;background:var(--ink);color:var(--bg);
  font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
button:hover{background:var(--accent)}
button.ghost{background:none;color:var(--ink);border:1px solid var(--ink)}
button.ghost:hover{background:var(--ink);color:var(--bg)}
button:disabled{background:var(--line);color:var(--ink-3);cursor:not-allowed}
.post{background:var(--card);border:1px solid var(--line);margin-bottom:14px;
  padding:17px 19px}
.post.over{border-color:var(--accent);border-left-width:3px}
.post-head{display:flex;align-items:baseline;gap:10px;margin-bottom:9px}
.idx{font-family:ui-monospace,monospace;font-size:12px;color:var(--ink-3)}
.kind{font-family:ui-monospace,monospace;font-size:10px;letter-spacing:.09em;
  text-transform:uppercase;padding:2px 7px;border:1px solid var(--soft);
  color:var(--ink-3)}
.chars{margin-left:auto;font-family:ui-monospace,monospace;font-size:12px;
  color:var(--ink-3)}
.chars.over{color:var(--accent);font-weight:700}
.text{font-size:16.5px;line-height:1.55;white-space:pre-wrap;margin:0 0 12px}
.media{width:100%;border:1px solid var(--soft);display:block;margin-top:10px}
.flag{border-left:2px solid var(--warn);background:#FBF6EC;padding:9px 13px;
  font-size:13.5px;color:var(--ink-2);margin:10px 0 0}
.flag b{color:var(--warn)}
.notice{border-left:2px solid var(--accent);background:#FCF3F1;padding:14px 18px;
  margin:0 0 22px;font-size:14.5px;color:var(--ink-2)}
.done{border-left-color:var(--ok);background:#F0F7F2}
#status{font-family:ui-monospace,monospace;font-size:13px;padding:9px 0}
"""


def _embed(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build_preview(
    thread: dict,
    thread_dir: Path,
    subject: str,
    account: str | None,
    warnings: list[str],
) -> str:
    posts = thread.get("posts", [])
    link_posts = sum(1 for p in posts if "http" in p.get("text", ""))
    cost = len(posts) * 0.015 + link_posts * (0.20 - 0.015)

    blocks: list[str] = []
    for post in posts:
        text = post.get("text", "")
        n = len(text)
        over = n > LIMIT
        card = thread_dir / f"{post['index']:02d}.png"

        flags: list[str] = []
        if post.get("quote_original"):
            flags.append(
                "<b>Contains a real quote.</b> Verified verbatim against the "
                "corpus — but check it still reads fairly out of context."
            )
        if over:
            flags.append(f"<b>Too long.</b> {n} characters, limit is {LIMIT}.")

        blocks.append(f"""
        <div class="post{' over' if over else ''}">
          <div class="post-head">
            <span class="idx">{post['index']}/{len(posts)}</span>
            <span class="kind">{html.escape(post.get('kind', ''))}</span>
            <span class="chars{' over' if over else ''}">{n}/{LIMIT}</span>
          </div>
          <p class="text">{html.escape(text)}</p>
          {f'<img class="media" src="{_embed(card)}" alt="">' if card.exists() else ''}
          {''.join(f'<div class="flag">{f}</div>' for f in flags)}
        </div>""")

    warn_html = ""
    if warnings:
        warn_html = (
            '<div class="notice"><b>Quote check flagged something.</b><br>'
            + "<br>".join(html.escape(w) for w in warnings)
            + "</div>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review · {html.escape(subject)}</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
  <p class="eyebrow">Review before posting</p>
  <h1>{html.escape(thread.get('headline') or subject)}</h1>
  <p class="sub">{len(posts)} posts · {subject}{
    f' · posting as @{html.escape(account)}' if account else ''}</p>
</header>

<div class="bar">
  <button id="approve">Post this thread</button>
  <button class="ghost" onclick="window.close()">Cancel</button>
  <span class="cost">≈ ${cost:.2f} in API fees</span>
</div>

{warn_html}

<div class="notice">
  Nothing is posted until you press the button. Read the quotes as a
  stranger would — verbatim and fair are not the same thing.
</div>

<div id="status"></div>
{''.join(blocks)}

<script>
document.getElementById('approve').onclick = async () => {{
  const btn = document.getElementById('approve');
  const status = document.getElementById('status');
  btn.disabled = true;
  status.textContent = 'posting…';
  try {{
    const r = await fetch('/approve', {{method:'POST'}});
    const d = await r.json();
    if (d.ok) {{
      status.innerHTML = 'posted → <a href="' + d.url + '" target="_blank">' + d.url + '</a>';
      document.querySelector('.notice').className = 'notice done';
    }} else {{
      status.textContent = 'failed: ' + (d.error || 'unknown');
      btn.disabled = false;
    }}
  }} catch (e) {{
    status.textContent = 'failed: ' + e;
    btn.disabled = false;
  }}
}};
</script>
</div></body></html>"""
