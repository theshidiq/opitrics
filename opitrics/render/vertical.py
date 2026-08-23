"""Vertical cards for short-form video — 1080×1920.

A short is watched, not read. Each card gets a couple of seconds before
a thumb decides, so it carries one idea at a size legible at arm's
length. That is the whole difference from the timeline cards: same
visual language, far less on each frame.

Safe zones matter here in a way they do not on a still. TikTok, Reels
and Shorts all overlay their own UI — captions and the progress bar
along the bottom, account chrome along the top — so anything placed
there is covered on some platform. Content sits between 12% and 78% of
the height, which survives all three.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, Rectangle  # noqa: E402

from opitrics.render.cards import (  # noqa: E402
    UI,
    _avatar_colour,
    _cjk_font,
    _cjk_wrap,
    _is_cjk,
    _latin_font,
    _thumb_icon,
    _tracked,
    _wrap,
    strip_emoji,
)
from opitrics.render.charts import _pick_font  # noqa: E402

log = logging.getLogger(__name__)

W, H = 1080, 1920
DPI = 100

# Vertical bounds of the area no platform's UI covers.
SAFE_TOP = 0.88
SAFE_BOTTOM = 0.22

MARGIN = 0.085


def _fig() -> tuple:
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    fig.patch.set_facecolor(UI["ground"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _chrome(ax, eyebrow: str, footer: str = "") -> None:
    """The header and footer that make a sequence feel like one piece."""
    ax.text(MARGIN, SAFE_TOP + 0.025, _tracked(eyebrow.upper()), fontsize=15,
            color=UI["dim"], family="monospace", va="center")
    ax.plot([MARGIN, 1 - MARGIN], [SAFE_TOP, SAFE_TOP],
            color=UI["rule"], lw=1.4)

    ax.plot([MARGIN, 1 - MARGIN], [SAFE_BOTTOM, SAFE_BOTTOM],
            color=UI["rule"], lw=1.4)
    ax.text(MARGIN, SAFE_BOTTOM - 0.028, _tracked("OPITRICS"), fontsize=14,
            color=UI["meta"], family="monospace", weight="bold", va="center")
    if footer:
        ax.text(1 - MARGIN, SAFE_BOTTOM - 0.028, footer, fontsize=14,
                color=UI["dim"], ha="right", va="center",
                family=_latin_font() or "sans-serif")


def _text_height(fig, ax, text: str, size: int, family, spacing: float) -> float:
    """Height of a text block in axes units, measured not estimated.

    Draws the text off-canvas, asks matplotlib for its bounding box, then
    removes it. Slower than multiplying point size by line count, and
    correct — which matters when the next element is positioned directly
    beneath it.
    """
    if not text:
        return 0.0
    probe = ax.text(
        -1, -1, text, fontsize=size, family=family,
        linespacing=spacing, va="top",
    )
    fig.canvas.draw()
    bbox = probe.get_window_extent(renderer=fig.canvas.get_renderer())
    probe.remove()
    return bbox.transformed(ax.transAxes.inverted()).height


def _fit_vertical(text: str) -> tuple[str, int, int]:
    """Wrap and size a comment for the tall frame.

    Capped at five lines, hard. A card is on screen for about three
    seconds and nobody reads a seven-line Japanese paragraph in three
    seconds — a long comment gets truncated to its opening thought
    rather than shrunk until it fits, because unreadably small is worse
    than incomplete. The full comment is one permalink away.
    """
    if _is_cjk(text):
        ladder = ((48, 14, 3), (42, 16, 4), (36, 19, 5))
        wrap = _cjk_wrap
    else:
        ladder = ((48, 24, 3), (42, 28, 4), (36, 34, 5))
        wrap = _wrap

    for size, width, max_lines in ladder:
        body = wrap(text, width, max_lines)
        if len(body.split("\n")) <= max_lines and len(text) <= width * max_lines:
            return body, size, len(body.split("\n"))

    # Longer than any rung: truncate at the last rung's capacity.
    size, width, max_lines = ladder[-1]
    body = wrap(text, width, max_lines)
    return body, size, len(body.split("\n"))


def hook_card(
    figure: str,
    caption: str,
    subject: str,
    out: Path,
    detail: str = "",
    tone: str = "accent",
) -> Path:
    """One number, large enough to stop a scroll."""
    jp = _pick_font()
    latin = _latin_font()
    if jp:
        plt.rcParams["font.family"] = jp

    fig, ax = _fig()
    colour = {"accent": UI["accent"], "neg": "#CC0000", "pos": "#0F7B3E"}.get(
        tone, UI["accent"]
    )

    _chrome(ax, subject.replace("-", " "))

    ax.text(0.5, 0.60, figure, fontsize=220, color=colour,
            ha="center", va="center", weight="bold",
            family=latin or jp)
    ax.text(0.5, 0.44, _wrap(strip_emoji(caption), 22, 3), fontsize=52,
            color=UI["text"], ha="center", va="top", linespacing=1.3,
            family=latin or jp)
    if detail:
        ax.text(0.5, 0.31, _wrap(strip_emoji(detail), 40, 2), fontsize=27,
                color=UI["dim"], ha="center", va="top", linespacing=1.4,
                family=latin or jp)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def quote_card(
    original: str,
    english: str,
    likes: int,
    subject: str,
    out: Path,
    comment_id: str | None = None,
) -> Path:
    """A comment, in the same visual language as the timeline cards."""
    jp = _pick_font()
    latin = _latin_font()
    if jp:
        plt.rcParams["font.family"] = jp

    fig, ax = _fig()
    _chrome(ax, "youtube comment", f"{likes:,} likes")

    clean = strip_emoji(original)
    body, size, lines = _fit_vertical(clean)
    body_font = _cjk_font(clean) if _is_cjk(clean) else (latin or jp)

    translation = _wrap(strip_emoji(english), 40, 3) if english else ""

    NAME_H = 0.062
    GAP = 0.040
    LIKES_H = 0.055

    # Line heights are measured from the rendered text rather than
    # estimated from the point size. An estimate was close enough on the
    # 16:9 card and wrong here — the taller frame magnifies the error and
    # the translation ended up printed through the quote.
    body_h = _text_height(fig, ax, body, size, body_font, 1.42)
    trans_h = (
        _text_height(fig, ax, translation, 30, latin or jp, 1.45)
        if translation else 0.0
    )

    block = NAME_H + body_h + (GAP + trans_h if translation else 0) + LIKES_H
    # Centre the block in the safe area: a two-line quote and a five-line
    # one should both sit in the middle of frame, where the eye lands.
    top = SAFE_TOP - (SAFE_TOP - SAFE_BOTTOM - block) / 2

    # Avatar and the withheld name line.
    radius = 0.021
    ax.add_patch(Ellipse((MARGIN + radius, top), radius * 2, radius * 2 * (W / H),
                         facecolor=_avatar_colour(comment_id or original),
                         edgecolor="none"))
    ax.text(MARGIN + radius * 2.8, top, "▬" * 6, fontsize=19,
            color=UI["rule"], family="monospace", va="center")
    ax.text(MARGIN + radius * 2.8 + 0.20, top, "identity withheld", fontsize=17,
            color=UI["dim"], va="center", family=latin or jp)

    cursor = top - NAME_H
    ax.text(MARGIN, cursor, body, fontsize=size, color=UI["text"],
            va="top", linespacing=1.42, family=body_font)
    cursor -= body_h

    if translation:
        cursor -= GAP
        ax.text(MARGIN, cursor, translation, fontsize=30, color=UI["meta"],
                va="top", linespacing=1.45, family=latin or jp)
        cursor -= trans_h

    likes_y = cursor - 0.032
    _thumb_icon(ax, MARGIN, likes_y, UI["like"], size=0.024)
    ax.text(MARGIN + 0.062, likes_y, f"{likes:,}", fontsize=30,
            color=UI["meta"], va="center", family="monospace")

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def statement_card(
    text: str,
    subject: str,
    out: Path,
    eyebrow: str = "",
    emphasis: str = "",
) -> Path:
    """A line of narration — the finding, or the payoff at the end."""
    jp = _pick_font()
    latin = _latin_font()
    if jp:
        plt.rcParams["font.family"] = jp

    fig, ax = _fig()
    _chrome(ax, eyebrow or subject.replace("-", " "))

    clean = strip_emoji(text)
    size = 56 if len(clean) < 70 else (46 if len(clean) < 130 else 38)
    width = 20 if size == 56 else (25 if size == 46 else 32)
    body = _wrap(clean, width, 7)
    lines = len(body.split("\n"))

    centre = SAFE_BOTTOM + (SAFE_TOP - SAFE_BOTTOM) / 2
    ax.text(MARGIN, centre + lines * (size * 1.3) / H / 2, body,
            fontsize=size, color=UI["text"], va="top", linespacing=1.3,
            family=latin or jp)

    if emphasis:
        ax.text(MARGIN, SAFE_BOTTOM + 0.055, strip_emoji(emphasis)[:60],
                fontsize=30, color=UI["accent"], va="center",
                family=latin or jp)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out
