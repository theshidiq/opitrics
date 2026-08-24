"""Charts sized and paced for vertical video.

A chart built for a report is the wrong shape and the wrong density
here: it assumes a reader who can study it. On a card that holds for
three seconds, a chart has to be readable at a glance and has to arrive
in pieces, so the eye is led rather than confronted with a finished
graphic.

So each chart is emitted as layers — axis and labels first, then bars
growing in, then the figure that matters. The bar growth is genuine
animation rather than a fade: a bar that grows communicates a quantity,
a bar that fades in is just a shape appearing.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from opitrics.render.cards import UI, _latin_font, strip_emoji  # noqa: E402
from opitrics.render.charts import _pick_font  # noqa: E402
from opitrics.render.layers import (  # noqa: E402
    MARGIN,
    SAFE_BOTTOM,
    SAFE_TOP,
    Element,
    LayeredCard,
    _blank,
    _chrome_layer,
    _save,
)

log = logging.getLogger(__name__)

W, H = 1080, 1920

POS = "#0F7B3E"
NEG = "#CC2A26"
NEUTRAL = "#8A8A8A"


def _tone(polarity: float) -> str:
    if polarity > 0.15:
        return POS
    if polarity < -0.15:
        return NEG
    return NEUTRAL


def _truncate(label: str, limit: int = 22) -> str:
    label = strip_emoji(label)
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def sentiment_bars_layers(
    clusters: list[dict],
    subject: str,
    out_dir: Path,
    title: str = "what people talk about",
    top: int = 6,
) -> LayeredCard:
    """A ranked bar chart where the bars grow in one at a time.

    Six rows, not twelve: the report's chart can afford a long tail
    because it is read, this one cannot. Bars are drawn at a series of
    widths so the growth is real animation rather than a fade.
    """
    jp = _pick_font()
    latin = _latin_font() or jp
    if jp:
        plt.rcParams["font.family"] = jp

    rows = [
        c for c in clusters
        if c.get("aspect") and not c.get("is_meta")
    ]
    rows = sorted(rows, key=lambda c: -c["size"])[:top]
    if not rows:
        raise ValueError("no car-aspect clusters to chart")

    labels = [_truncate(c.get("llm_label") or c["aspect_label"]) for c in rows]
    sizes = [c["size"] for c in rows]
    pols = [c["sentiment"]["polarity"] for c in rows]
    peak = max(sizes)

    # Geometry, in axes units. Rows run downward from just under the
    # title; the bar column starts after the label column.
    row_top = SAFE_TOP - 0.13
    row_h = (row_top - SAFE_BOTTOM - 0.05) / len(rows)
    bar_x = MARGIN + 0.44
    bar_w = (1 - MARGIN) - bar_x

    bg = _chrome_layer(out_dir / "bg.png", subject.replace("-", " "))
    elements: list[Element] = []

    # Title and the row labels — the frame the bars will fill.
    fig, ax = _blank()
    ax.text(MARGIN, SAFE_TOP - 0.045, title, fontsize=44, color=UI["text"],
            va="top", family=latin)
    for i, label in enumerate(labels):
        y = row_top - i * row_h - row_h / 2
        ax.text(bar_x - 0.022, y, label, fontsize=25, color=UI["meta"],
                ha="right", va="center", family=latin)
        # The empty track, so growth reads against something.
        ax.add_patch(plt.Rectangle((bar_x, y - row_h * 0.20), bar_w,
                                   row_h * 0.40, facecolor="#EFEFEF",
                                   edgecolor="none"))
    elements.append(Element(_save(fig, out_dir / "e1.png"), "fade", 0.0))

    # Bars, drawn at increasing widths. Each frame is one layer, faded
    # on in sequence, which composites into growth.
    STEPS = 7
    for step in range(1, STEPS + 1):
        fraction = step / STEPS
        fig, ax = _blank()
        for i, (n, pol) in enumerate(zip(sizes, pols)):
            y = row_top - i * row_h - row_h / 2
            width = bar_w * (n / peak) * fraction
            ax.add_patch(plt.Rectangle((bar_x, y - row_h * 0.20), width,
                                       row_h * 0.40, facecolor=_tone(pol),
                                       edgecolor="none"))
        elements.append(Element(
            _save(fig, out_dir / f"e{step + 1}.png"),
            "fade",
            # Growth occupies the first 45% of the shot, leaving the
            # rest for the numbers and for reading.
            0.10 + (step - 1) * (0.35 / STEPS),
        ))

    # Counts, arriving after the bars have settled.
    fig, ax = _blank()
    for i, (n, pol) in enumerate(zip(sizes, pols)):
        y = row_top - i * row_h - row_h / 2
        width = bar_w * (n / peak)
        ax.text(bar_x + width + 0.012, y, f"{n:,}", fontsize=24,
                color=UI["meta"], va="center", family="monospace")
    elements.append(Element(_save(fig, out_dir / f"e{STEPS + 2}.png"),
                            "fade", 0.56))

    return LayeredCard(background=bg, elements=elements)


def composition_layers(
    totals: dict,
    subject: str,
    out_dir: Path,
    title: str = "what the comments are about",
) -> LayeredCard:
    """One stacked bar: how much of the conversation is the car.

    The single most repeatable finding this pipeline produces, and the
    one that compares across cars — so it gets its own card rather than
    being a line in a table.
    """
    jp = _pick_font()
    latin = _latin_font() or jp
    if jp:
        plt.rcParams["font.family"] = jp

    car = totals.get("car", 0)
    meta_n = totals.get("meta", 0)
    unmapped = totals.get("unmapped", 0)
    total = max(car + meta_n + unmapped, 1)

    segments = [
        (car, UI["accent"], "about the car"),
        (meta_n, "#B8860B", "about the video, or arguing"),
        (unmapped, NEUTRAL, "unmapped"),
    ]
    segments = [s for s in segments if s[0] > 0]

    bar_y = 0.56
    bar_h = 0.085
    x0, x1 = MARGIN, 1 - MARGIN
    span = x1 - x0

    bg = _chrome_layer(out_dir / "bg.png", subject.replace("-", " "))
    elements: list[Element] = []

    fig, ax = _blank()
    ax.text(MARGIN, SAFE_TOP - 0.045, title, fontsize=44, color=UI["text"],
            va="top", family=latin)
    ax.add_patch(plt.Rectangle((x0, bar_y), span, bar_h,
                               facecolor="#EFEFEF", edgecolor="none"))
    elements.append(Element(_save(fig, out_dir / "e1.png"), "fade", 0.0))

    # Each segment arrives in turn, so the split is read left to right
    # rather than appearing whole.
    cursor = x0
    for i, (value, colour, label) in enumerate(segments):
        width = span * value / total
        fig, ax = _blank()
        ax.add_patch(plt.Rectangle((cursor, bar_y), width, bar_h,
                                   facecolor=colour, edgecolor="none"))
        pct = value / total
        if pct > 0.10:
            ax.text(cursor + width / 2, bar_y + bar_h / 2, f"{pct:.0%}",
                    fontsize=34, color="#FFFFFF", ha="center", va="center",
                    weight="bold", family=latin)
        # Anchor the label so it cannot run off the frame: left-aligned
        # for the first segment, right-aligned for the last.
        if i == 0:
            lx, align = cursor, "left"
        elif i == len(segments) - 1:
            lx, align = cursor + width, "right"
        else:
            lx, align = cursor + width / 2, "center"
        from opitrics.render.cards import _wrap
        ax.text(lx, bar_y - 0.035, _wrap(label, 20, 2), fontsize=23,
                color=UI["meta"], va="top", ha=align, family=latin,
                linespacing=1.3)
        ax.text(lx, bar_y - 0.105, f"{value:,}", fontsize=22,
                color=UI["dim"], va="top", ha=align, family="monospace")
        elements.append(Element(
            _save(fig, out_dir / f"e{i + 2}.png"), "fade", 0.14 + i * 0.16,
        ))
        cursor += width

    return LayeredCard(background=bg, elements=elements)


def photo_layers(
    photo: Path,
    caption: str,
    credit: str,
    subject: str,
    out_dir: Path,
) -> LayeredCard:
    """A photograph of the car, with its licence credit burned in.

    The credit is drawn onto the card rather than left to a description
    field, because a CC BY image used without attribution is a licence
    breach and a description is easy to forget.
    """
    from PIL import Image

    jp = _pick_font()
    latin = _latin_font() or jp

    bg_path = out_dir / "bg.png"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cover-crop the photo to the frame rather than letterboxing it.
    img = Image.open(photo).convert("RGB")
    scale = max(W / img.width, H / img.height)
    resized = img.resize(
        (max(int(img.width * scale), W), max(int(img.height * scale), H)),
        Image.LANCZOS,
    )
    left = (resized.width - W) // 2
    top_px = (resized.height - H) // 2
    resized.crop((left, top_px, left + W, top_px + H)).save(bg_path)

    elements: list[Element] = []

    # A scrim behind the text, or a caption over a bright photo is
    # unreadable.
    fig, ax = _blank()
    ax.add_patch(plt.Rectangle((0, 0), 1, 0.34, facecolor="#000000",
                               alpha=0.62, edgecolor="none"))
    elements.append(Element(_save(fig, out_dir / "e1.png"), "fade", 0.0))

    if caption:
        fig, ax = _blank()
        from opitrics.render.cards import _wrap

        ax.text(MARGIN, 0.26, _wrap(strip_emoji(caption), 24, 3),
                fontsize=46, color="#FFFFFF", va="top", linespacing=1.3,
                family=latin)
        elements.append(Element(_save(fig, out_dir / "e2.png"), "rise", 0.14))

    fig, ax = _blank()
    ax.text(MARGIN, 0.055, credit[:70], fontsize=17, color="#D8D8D8",
            va="center", family=latin)
    elements.append(Element(_save(fig, out_dir / "e3.png"), "fade", 0.30))

    return LayeredCard(background=bg_path, elements=elements)
