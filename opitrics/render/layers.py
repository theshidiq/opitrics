"""Cards as animated layers rather than flat images.

A PNG that drifts is still one static frame per beat. What reads as
edited is elements arriving separately — a number counting up, a
translation appearing after the original has had a moment to land, a
line of text sliding in under the one above it.

So each card is built as its parts: background, then every text block
as its own transparent PNG with its own entrance. Movis composites and
animates them. The cost is that layout has to be computed here rather
than delegated to a single matplotlib call, which is why the geometry
in this module is explicit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402

from opitrics.render.cards import (  # noqa: E402
    UI,
    _avatar_colour,
    _cjk_font,
    _cjk_wrap,
    _is_cjk,
    _latin_font,
    _wrap,
    strip_emoji,
)
from opitrics.render.charts import _pick_font  # noqa: E402

log = logging.getLogger(__name__)

W, H = 1080, 1920
DPI = 100

SAFE_TOP = 0.88
SAFE_BOTTOM = 0.20
MARGIN = 0.085


@dataclass
class Element:
    """One animated part of a card.

    `enter` names how it arrives; `at` is when, as a fraction of the
    shot's hold, so a beat that runs long stretches its choreography
    rather than leaving elements stranded at the start.
    """

    image: Path
    enter: str = "rise"          # rise | fade | pop | wipe
    at: float = 0.0
    anchor: tuple[float, float] = (0.5, 0.5)


@dataclass
class LayeredCard:
    """A card, as a background plus the parts that animate onto it."""

    background: Path
    elements: list[Element] = field(default_factory=list)


def _blank(transparent: bool = True):
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    if not transparent:
        fig.patch.set_facecolor(UI["ground"])
    else:
        fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_alpha(0.0)
    return fig, ax


def _save(fig, out: Path, transparent: bool = True) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out,
        transparent=transparent,
        facecolor="none" if transparent else UI["ground"],
    )
    plt.close(fig)
    return out


def _measure(fig, ax, text: str, size: int, family, spacing: float) -> float:
    """Rendered height of a text block, in axes units."""
    if not text:
        return 0.0
    probe = ax.text(-1, -1, text, fontsize=size, family=family,
                    linespacing=spacing, va="top")
    fig.canvas.draw()
    bbox = probe.get_window_extent(renderer=fig.canvas.get_renderer())
    probe.remove()
    return bbox.transformed(ax.transAxes.inverted()).height


def _tracked(text: str) -> str:
    return " ".join(text)


def _chrome_layer(out: Path, eyebrow: str, footer: str = "") -> Path:
    """The frame furniture — rules, wordmark, eyebrow. Never animates."""
    jp = _pick_font()
    latin = _latin_font()
    if jp:
        plt.rcParams["font.family"] = jp

    fig, ax = _blank(transparent=False)
    ax.text(MARGIN, SAFE_TOP + 0.025, _tracked(eyebrow.upper()), fontsize=15,
            color=UI["dim"], family="monospace", va="center")
    ax.plot([MARGIN, 1 - MARGIN], [SAFE_TOP, SAFE_TOP], color=UI["rule"], lw=1.4)
    ax.plot([MARGIN, 1 - MARGIN], [SAFE_BOTTOM, SAFE_BOTTOM],
            color=UI["rule"], lw=1.4)
    ax.text(MARGIN, SAFE_BOTTOM - 0.028, _tracked("OPITRICS"), fontsize=14,
            color=UI["meta"], family="monospace", weight="bold", va="center")
    if footer:
        ax.text(1 - MARGIN, SAFE_BOTTOM - 0.028, footer, fontsize=14,
                color=UI["dim"], ha="right", va="center", family=latin or jp)
    return _save(fig, out, transparent=False)


def _text_layer(
    out: Path,
    text: str,
    y: float,
    size: int,
    colour: str,
    family,
    *,
    x: float = MARGIN,
    align: str = "left",
    spacing: float = 1.42,
    weight: str = "normal",
) -> Path:
    """One text block on its own transparent canvas."""
    fig, ax = _blank()
    ax.text(x, y, text, fontsize=size, color=colour, family=family,
            va="top", ha=align, linespacing=spacing, weight=weight)
    return _save(fig, out)


# ── card builders ───────────────────────────────────────────


def hook_layers(
    figure: str,
    caption: str,
    subject: str,
    out_dir: Path,
    detail: str = "",
) -> LayeredCard:
    """A number that lands, then a caption under it, then the detail.

    Three separate arrivals rather than one image, because the number is
    the hook and it should own the frame for a beat before anything
    explains it.
    """
    jp = _pick_font()
    latin = _latin_font() or jp
    if jp:
        plt.rcParams["font.family"] = jp

    bg = _chrome_layer(out_dir / "bg.png", subject.replace("-", " "))
    elements: list[Element] = []

    fig, ax = _blank()
    ax.text(0.5, 0.60, figure, fontsize=230, color=UI["accent"],
            ha="center", va="center", weight="bold", family=latin)
    elements.append(Element(_save(fig, out_dir / "e1.png"), "pop", 0.0))

    fig, ax = _blank()
    ax.text(0.5, 0.44, _wrap(strip_emoji(caption), 22, 3), fontsize=54,
            color=UI["text"], ha="center", va="top", linespacing=1.3,
            family=latin)
    elements.append(Element(_save(fig, out_dir / "e2.png"), "rise", 0.30))

    if detail:
        fig, ax = _blank()
        ax.text(0.5, 0.30, _wrap(strip_emoji(detail), 40, 2), fontsize=28,
                color=UI["dim"], ha="center", va="top", linespacing=1.4,
                family=latin)
        elements.append(Element(_save(fig, out_dir / "e3.png"), "fade", 0.52))

    return LayeredCard(background=bg, elements=elements)


def quote_layers(
    original: str,
    english: str,
    likes: int,
    subject: str,
    out_dir: Path,
    comment_id: str | None = None,
) -> LayeredCard:
    """Avatar, then the comment, then its translation, then the likes.

    The translation deliberately arrives late — a viewer who reads
    Japanese gets a beat with the original before the English appears,
    and one who does not sees the shape of a real comment first.
    """
    jp = _pick_font()
    latin = _latin_font() or jp
    if jp:
        plt.rcParams["font.family"] = jp

    clean = strip_emoji(original)
    if _is_cjk(clean):
        ladder = ((48, 14, 3), (42, 16, 4), (36, 19, 5))
        wrap = _cjk_wrap
    else:
        ladder = ((48, 24, 3), (42, 28, 4), (36, 34, 5))
        wrap = _wrap
    for size, width, max_lines in ladder:
        body = wrap(clean, width, max_lines)
        if len(body.split("\n")) <= max_lines and len(clean) <= width * max_lines:
            break
    else:
        size, width, max_lines = ladder[-1]
        body = wrap(clean, width, max_lines)

    body_font = _cjk_font(clean) if _is_cjk(clean) else latin
    translation = _wrap(strip_emoji(english), 40, 3) if english else ""

    # Measure once on a throwaway figure so the layout is known before
    # any layer is drawn.
    probe_fig, probe_ax = _blank()
    body_h = _measure(probe_fig, probe_ax, body, size, body_font, 1.42)
    trans_h = _measure(probe_fig, probe_ax, translation, 30, latin, 1.45) if translation else 0.0
    plt.close(probe_fig)

    NAME_H, GAP, LIKES_H = 0.062, 0.040, 0.055
    block = NAME_H + body_h + (GAP + trans_h if translation else 0) + LIKES_H
    top = SAFE_TOP - (SAFE_TOP - SAFE_BOTTOM - block) / 2

    bg = _chrome_layer(out_dir / "bg.png", "youtube comment", f"{likes:,} likes")
    elements: list[Element] = []

    # Avatar and withheld name, together — they are one idea.
    fig, ax = _blank()
    radius = 0.021
    ax.add_patch(Ellipse((MARGIN + radius, top), radius * 2, radius * 2 * (W / H),
                         facecolor=_avatar_colour(comment_id or original),
                         edgecolor="none"))
    ax.text(MARGIN + radius * 2.8, top, "▬" * 6, fontsize=19,
            color=UI["rule"], family="monospace", va="center")
    ax.text(MARGIN + radius * 2.8 + 0.20, top, "identity withheld", fontsize=17,
            color=UI["dim"], va="center", family=latin)
    elements.append(Element(_save(fig, out_dir / "e1.png"), "fade", 0.0))

    cursor = top - NAME_H
    elements.append(Element(
        _text_layer(out_dir / "e2.png", body, cursor, size,
                    UI["text"], body_font),
        "rise", 0.12,
    ))
    cursor -= body_h

    if translation:
        cursor -= GAP
        elements.append(Element(
            _text_layer(out_dir / "e3.png", translation, cursor, 30,
                        UI["meta"], latin, spacing=1.45),
            "rise", 0.42,
        ))
        cursor -= trans_h

    fig, ax = _blank()
    likes_y = cursor - 0.032
    ax.add_patch(plt.Rectangle((MARGIN, likes_y - 0.012), 0.010, 0.024,
                               facecolor=UI["like"], edgecolor="none"))
    ax.add_patch(plt.Rectangle((MARGIN + 0.013, likes_y - 0.012), 0.020, 0.026,
                               facecolor=UI["like"], edgecolor="none"))
    ax.text(MARGIN + 0.062, likes_y, f"{likes:,}", fontsize=30,
            color=UI["meta"], va="center", family="monospace")
    elements.append(Element(_save(fig, out_dir / "e4.png"), "pop", 0.62))

    return LayeredCard(background=bg, elements=elements)


def statement_layers(
    text: str,
    subject: str,
    out_dir: Path,
    eyebrow: str = "",
) -> LayeredCard:
    """A narration line, arriving one line at a time.

    Each wrapped line is its own layer, staggered — the closest this
    gets to text typing on, without the cost of per-word layers.
    """
    jp = _pick_font()
    latin = _latin_font() or jp
    if jp:
        plt.rcParams["font.family"] = jp

    clean = strip_emoji(text)
    size = 58 if len(clean) < 70 else (48 if len(clean) < 130 else 40)
    width = 19 if size == 58 else (24 if size == 48 else 30)
    lines = _wrap(clean, width, 7).split("\n")

    probe_fig, probe_ax = _blank()
    line_h = _measure(probe_fig, probe_ax, "X", size, latin, 1.3)
    plt.close(probe_fig)

    total = len(lines) * line_h
    top = SAFE_BOTTOM + (SAFE_TOP - SAFE_BOTTOM + total) / 2

    bg = _chrome_layer(out_dir / "bg.png", eyebrow or subject.replace("-", " "))
    elements: list[Element] = []

    for i, line in enumerate(lines):
        elements.append(Element(
            _text_layer(out_dir / f"e{i + 1}.png", line,
                        top - i * line_h, size, UI["text"], latin,
                        spacing=1.3),
            "rise",
            # Staggered, but compressed so a five-line statement does
            # not spend the whole shot assembling itself.
            min(0.06 + i * 0.13, 0.62),
        ))

    return LayeredCard(background=bg, elements=elements)
