"""Render a short as TikTok will receive it, for review before posting.

This page is not decoration. TikTok's Content Posting audit requires
that the creator's username and avatar are shown before publishing, so
the identity block here is a submission requirement rather than a
courtesy — an integration that posts without showing whose account it
is posting to does not pass.

It also exists for a reason particular to this API: an unaudited client
gets a 200 and a publish id whether or not the video will be visible to
anyone. The privacy level TikTok is *actually* offering is read from
creator_info and stated plainly, because "posted successfully" and
"posted where somebody can see it" are different things here and the
API does not distinguish them.

Styling follows the X preview deliberately. Both are the same moment in
the same pipeline, and a reviewer who has learned to read one should
not have to learn another.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

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
.wrap{max-width:1040px;margin:0 auto;padding:44px 22px 90px}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:22px}
.eyebrow{font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin:0 0 8px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--ink-3);font-size:14px;margin:0;font-family:ui-monospace,monospace}

.bar{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);
  padding:12px 0;margin-bottom:26px;display:flex;align-items:center;
  justify-content:space-between;gap:16px;z-index:5}
.state{font-family:ui-monospace,monospace;font-size:12px;color:var(--ink-3)}
button{padding:10px 20px;border:none;background:var(--ink);color:var(--bg);
  font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
button:hover:not(:disabled){background:var(--accent)}
button:disabled{background:var(--ink-3);cursor:not-allowed}

/* Stacks under ~820px, and when it stacks the side column goes FIRST.
   The warnings are the reason this page exists; a stacked layout that
   puts a full-height video above them means scrolling past the video
   to find out the post will be invisible, which is exactly the thing
   nobody should have to hunt for. */
.cols{display:flex;gap:30px;align-items:flex-start;flex-wrap:wrap}
.vid{flex:none;width:300px;order:1}
video{width:300px;border:1px solid var(--line);background:#000;display:block}
.side{flex:1;min-width:400px;order:2}
@media (max-width:820px){
  .cols{flex-direction:column}
  .vid{width:100%;max-width:320px;margin:0 auto;order:2}
  video{width:100%}
  .side{min-width:100%;order:1}
}

/* The identity block the audit checks for. */
.who{display:flex;align-items:center;gap:13px;background:var(--card);
  border:1px solid var(--line);padding:14px 16px;margin:0 0 18px}
.who img{width:46px;height:46px;border-radius:50%;flex:none;object-fit:cover;
  background:var(--soft)}
.who .noavatar{width:46px;height:46px;border-radius:50%;flex:none;
  background:var(--soft);display:flex;align-items:center;justify-content:center;
  font-family:ui-monospace,monospace;font-size:11px;color:var(--ink-3)}
.who b{display:block;font-size:15px}
.who span{font-size:13px;color:var(--ink-3);font-family:ui-monospace,monospace}

.notice{border-left:2px solid var(--accent);background:#FCF3F1;padding:14px 18px;
  margin:0 0 18px;font-size:14.5px;color:var(--ink-2)}
.notice.warn{border-left-color:var(--warn);background:#FBF5E9}
.notice.ok{border-left-color:var(--ok);background:#F0F7F2}
.notice b{color:var(--ink)}

.caption{background:var(--card);border:1px solid var(--line);padding:16px 18px;
  margin:0 0 18px;white-space:pre-wrap;font-size:15px;line-height:1.5}
.caption .count{display:block;margin-top:12px;font-family:ui-monospace,monospace;
  font-size:12px;color:var(--ink-3)}
.caption .count.over{color:var(--accent);font-weight:700}

table{width:100%;border-collapse:collapse;font-size:14px;margin:0 0 18px}
td{padding:7px 0;border-bottom:1px solid var(--soft);vertical-align:top}
td:first-child{color:var(--ink-3);width:42%;font-family:ui-monospace,monospace;
  font-size:12.5px}
td b.no{color:var(--accent)}
td b.yes{color:var(--ok)}

.script{background:var(--card);border:1px solid var(--line);padding:16px 18px;
  font-size:14px;color:var(--ink-2)}
.script h3{margin:0 0 12px;font-size:12px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-3);font-family:ui-monospace,monospace}
.script li{margin:0 0 9px}
#status{font-family:ui-monospace,monospace;font-size:13px;padding:9px 0}
"""

PRIVACY_HUMAN = {
    "PUBLIC_TO_EVERYONE": "everyone",
    "MUTUAL_FOLLOW_FRIENDS": "friends only",
    "FOLLOWER_OF_CREATOR": "followers only",
    "SELF_ONLY": "only you",
}


def _embed_video(path: Path) -> str:
    return "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()


def build_preview(
    *,
    video: Path,
    title: str,
    privacy: str,
    resolved_privacy: str,
    info,
    subject: str,
    angle: str,
    duration: float,
    beats: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """The review page. `info` is a tiktok.CreatorInfo."""
    warnings = warnings or []
    beats = beats or []

    # The one thing a reviewer must not miss: whether this will be
    # visible to anybody. An unaudited client cannot post publicly
    # however the command was written.
    audited = "PUBLIC_TO_EVERYONE" in info.privacy_level_options
    visible = PRIVACY_HUMAN.get(resolved_privacy, resolved_privacy)

    if not audited:
        banner = (
            '<div class="notice"><b>This app is not audited yet, so this '
            'video will be visible to you and nobody else.</b> TikTok forces '
            '<code>SELF_ONLY</code> on unaudited clients whatever the request '
            'asks for, and the API still returns success. Your account also '
            'has to be set to private while posting this way. Publishing '
            'publicly needs the Content Posting audit, which takes two to '
            'four weeks.</div>'
        )
    elif resolved_privacy == "PUBLIC_TO_EVERYONE":
        banner = (
            '<div class="notice warn"><b>This posts publicly, immediately.</b> '
            'Read the caption as a stranger would, and check the first two '
            'seconds of the video — that is all most people will see.</div>'
        )
    else:
        banner = (
            f'<div class="notice ok">Posting as <b>{html.escape(visible)}</b>. '
            'Watch it back in the TikTok app before widening it — their player '
            'is the only place you see it as a viewer does.</div>'
        )

    if info.avatar_url:
        avatar = f'<img src="{html.escape(info.avatar_url)}" alt="">'
    else:
        avatar = '<div class="noavatar">?</div>'

    name = info.nickname or info.username or "unknown account"
    handle = f"@{info.username}" if info.username else "no username returned"

    warn_html = "".join(
        f'<div class="notice warn">{html.escape(w)}</div>' for w in warnings
    )

    over = len(title) > 2200
    beat_html = "".join(
        f"<li><b>{b.get('index', i + 1)}.</b> "
        f"{html.escape(str(b.get('narration', '')))}</li>"
        for i, b in enumerate(beats)
    )
    script_block = (
        f'<div class="script"><h3>What it says</h3><ol>{beat_html}</ol></div>'
        if beat_html else ""
    )

    offered = ", ".join(
        PRIVACY_HUMAN.get(p, p) for p in info.privacy_level_options
    ) or "nothing — this account cannot post right now"

    def yesno(disabled: bool) -> str:
        return ('<b class="no">off</b>' if disabled else '<b class="yes">on</b>')

    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(subject)} · {html.escape(angle)} → TikTok</title>
<style>{CSS}</style>
<div class="wrap">
  <header>
    <p class="eyebrow">review before posting</p>
    <h1>{html.escape(subject)} · {html.escape(angle)}</h1>
    <p class="sub">{duration:.1f}s · {video.stat().st_size / 1e6:.1f}MB · tiktok</p>
  </header>

  <div class="bar">
    <span class="state" id="status">nothing has been sent yet</span>
    <button id="approve">Post to TikTok</button>
  </div>

  <div class="cols">
    <div class="vid">
      <video src="{_embed_video(video)}" controls playsinline preload="metadata">
      </video>
    </div>

    <div class="side">
      <div class="who">
        {avatar}
        <div>
          <b>{html.escape(name)}</b>
          <span>{html.escape(handle)}</span>
        </div>
      </div>

      {banner}
      {warn_html}

      <div class="caption">{html.escape(title)}
        <span class="count{' over' if over else ''}">{len(title)}/2200</span>
      </div>

      <table>
        <tr><td>asked for</td>
            <td>{html.escape(PRIVACY_HUMAN.get(privacy, privacy))}</td></tr>
        <tr><td>will actually be</td>
            <td><b>{html.escape(visible)}</b></td></tr>
        <tr><td>tiktok is offering</td><td>{html.escape(offered)}</td></tr>
        <tr><td>comments</td><td>{yesno(info.comment_disabled)}</td></tr>
        <tr><td>duet</td><td>{yesno(info.duet_disabled)}</td></tr>
        <tr><td>stitch</td><td>{yesno(info.stitch_disabled)}</td></tr>
      </table>

      {script_block}
    </div>
  </div>
</div>

<script>
document.getElementById('approve').onclick = async () => {{
  const btn = document.getElementById('approve');
  const status = document.getElementById('status');
  btn.disabled = true;
  status.textContent = 'uploading…';
  try {{
    const r = await fetch('/approve', {{method: 'POST'}});
    const d = await r.json();
    if (d.ok) {{
      status.textContent = d.message || 'sent';
      btn.textContent = 'Sent';
    }} else {{
      status.textContent = 'failed: ' + (d.error || 'unknown');
      btn.disabled = false;
    }}
  }} catch (e) {{
    status.textContent = 'failed: ' + e.message;
    btn.disabled = false;
  }}
}};
</script>
</html>"""
