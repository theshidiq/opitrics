"""Content-ready PNG charts.

Sized and weighted for video: large type, high contrast, no thin
hairlines that vanish under compression. Every chart renders from the
same analysis JSON, so numbers cannot drift between a chart and the
report beside it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

log = logging.getLogger(__name__)

# Two palettes. Dark suits video overlay; light matches the newsprint
# web UI, where a dark chart sits on the page like a hole.
DARK = {
    "ink": "#E8ECF1", "ink_mid": "#A9B4C0", "ink_soft": "#78838F",
    "ground": "#0F1216", "surface": "#161B21", "line": "#2A333D",
    "accent": "#00B4D8", "pos": "#4CAF7D", "neg": "#E5484D", "warn": "#E8A33D",
}
LIGHT = {
    "ink": "#1A1917", "ink_mid": "#4A473F", "ink_soft": "#807B6E",
    "ground": "#FBFAF7", "surface": "#F4F2EC", "line": "#DBD7CC",
    "accent": "#8C2B18", "pos": "#2C6E49", "neg": "#A3341F", "warn": "#9A6B1F",
}
# The published palette, mirroring remotion/src/theme.ts. LIGHT is the
# internal web UI's warm theme and stays as it is; a chart on the public
# report sits beside the shorts' own colours and has to match them, not
# the review tooling. Ratios are theme.ts's measured ones.
WEB = {
    "ink": "#000000", "ink_mid": "#3D3D3D", "ink_soft": "#5A5A5A",
    "ground": "#FFFFFF", "surface": "#F4F4F4", "line": "#BFBFBF",
    "accent": "#0546A8", "pos": "#0A5F2F", "neg": "#A81C19", "warn": "#8A5A00",
}

# Module-level so the drawing functions can stay signature-compatible;
# set by apply_theme() before any chart is rendered.
INK = DARK["ink"]
INK_MID = DARK["ink_mid"]
INK_SOFT = DARK["ink_soft"]
GROUND = DARK["ground"]
SURFACE = DARK["surface"]
LINE = DARK["line"]
ACCENT = DARK["accent"]
POS = DARK["pos"]
NEG = DARK["neg"]
WARN = DARK["warn"]

# CJK-capable faces, in preference order. Without one of these,
# matplotlib silently renders Japanese as empty boxes.
CJK_FONTS = [
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans CJK JP",
    "Yu Gothic",
    "Arial Unicode MS",
]


def _pick_font() -> str | None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in CJK_FONTS:
        if name in available:
            return name
    log.warning("no CJK font found — Japanese text may render as boxes")
    return None


def apply_theme(mode: str = "dark") -> None:
    global INK, INK_MID, INK_SOFT, GROUND, SURFACE, LINE, ACCENT, POS, NEG, WARN

    palette = {"light": LIGHT, "web": WEB}.get(mode, DARK)
    INK = palette["ink"]
    INK_MID = palette["ink_mid"]
    INK_SOFT = palette["ink_soft"]
    GROUND = palette["ground"]
    SURFACE = palette["surface"]
    LINE = palette["line"]
    ACCENT = palette["accent"]
    POS = palette["pos"]
    NEG = palette["neg"]
    WARN = palette["warn"]

    font = _pick_font()
    plt.rcParams.update(
        {
            "figure.facecolor": GROUND,
            "axes.facecolor": GROUND,
            "savefig.facecolor": GROUND,
            "text.color": INK,
            "axes.labelcolor": INK_MID,
            "axes.edgecolor": LINE,
            "xtick.color": INK_SOFT,
            "ytick.color": INK_SOFT,
            "grid.color": LINE,
            "axes.grid": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 13,
            "figure.dpi": 160,
        }
    )
    if font:
        plt.rcParams["font.family"] = font


def _tone(polarity: float) -> str:
    if polarity > 0.15:
        return POS
    if polarity < -0.15:
        return NEG
    return INK_SOFT


def aspect_sentiment_chart(clusters: list[dict], out: Path, top: int = 12) -> Path:
    """Horizontal diverging bars — what people talk about and how they feel."""
    car = [c for c in clusters if c.get("aspect") and not c.get("is_meta")]
    car = sorted(car, key=lambda c: -c["size"])[:top]
    car.reverse()

    if not car:
        raise ValueError("no car-aspect clusters to chart")

    labels = [c.get("llm_label") or c["aspect_label"] for c in car]
    sizes = [c["size"] for c in car]
    pols = [c["sentiment"]["polarity"] for c in car]

    fig, ax = plt.subplots(figsize=(11, 0.52 * len(car) + 2.2))
    bars = ax.barh(range(len(car)), pols, color=[_tone(p) for p in pols], height=0.62)

    ax.axvline(0, color=LINE, lw=1.2)
    ax.set_yticks(range(len(car)))
    ax.set_yticklabels(labels, fontsize=12)
    ax.set_xlim(-1, 1)
    ax.set_xlabel("← negative          sentiment          positive →", fontsize=11)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)

    for i, (bar, n, p) in enumerate(zip(bars, sizes, pols)):
        offset = 0.03 if p >= 0 else -0.03
        ax.text(
            p + offset, i, f"{n:,}",
            va="center", ha="left" if p >= 0 else "right",
            color=INK_MID, fontsize=10,
        )

    ax.set_title(
        "What people talk about, and how they feel about it",
        fontsize=15, color=INK, pad=16, loc="left", fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def volume_intensity_chart(clusters: list[dict], out: Path) -> Path:
    """Scatter of volume against intensity.

    The chart that stops low-volume, high-heat findings from being
    buried by a ranked list — a small cluster of alarmed comments about
    a safety issue sits in a different quadrant from a large placid one
    about styling.
    """
    car = [c for c in clusters if c.get("aspect") and not c.get("is_meta")]
    if not car:
        raise ValueError("no car-aspect clusters to chart")

    xs = [c["size"] for c in car]
    ys = [c["sentiment"]["intensity"] for c in car]
    pols = [c["sentiment"]["polarity"] for c in car]
    likes = [max(c["total_likes"], 1) for c in car]
    labels = [c.get("llm_label") or c["aspect_label"] for c in car]

    peak = max(likes)
    areas = [90 + 900 * (v / peak) ** 0.6 for v in likes]

    fig, ax = plt.subplots(figsize=(11.5, 7.4))
    ax.scatter(
        xs, ys, s=areas,
        c=[_tone(p) for p in pols],
        alpha=0.72, edgecolors=GROUND, linewidths=1.6, zorder=3,
    )

    mid_x = (min(xs) + max(xs)) / 2
    mid_y = (min(ys) + max(ys)) / 2
    ax.axvline(mid_x, color=LINE, lw=1, ls=(0, (4, 4)), zorder=1)
    ax.axhline(mid_y, color=LINE, lw=1, ls=(0, (4, 4)), zorder=1)

    # Label only the points worth naming. Annotating all 25 produced an
    # unreadable pile — the outliers are what the chart is for, and the
    # rest are legible from the table in the report.
    ranked = sorted(
        range(len(car)),
        key=lambda i: -(ys[i] * xs[i] * (0.6 + 0.4 * (likes[i] / peak))),
    )
    labelled = set(ranked[:9])

    # Alternate above/below so neighbouring labels do not collide.
    for rank, i in enumerate(ranked):
        if i not in labelled:
            continue
        above = rank % 2 == 0
        ax.annotate(
            labels[i], (xs[i], ys[i]),
            textcoords="offset points",
            xytext=(0, 17 if above else -25),
            ha="center", va="bottom" if above else "top",
            fontsize=10, color=INK, zorder=5,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": GROUND,
                  "edgecolor": LINE, "linewidth": 0.8, "alpha": 0.9},
        )

    ax.text(0.015, 0.97, "ACT ON THIS", transform=ax.transAxes,
            fontsize=9.5, color=INK_SOFT, va="top")
    ax.text(0.985, 0.97, "THE HEADLINE", transform=ax.transAxes,
            fontsize=9.5, color=INK_SOFT, va="top", ha="right")
    ax.text(0.985, 0.03, "TALKED ABOUT, TOLERATED", transform=ax.transAxes,
            fontsize=9.5, color=INK_SOFT, ha="right")

    # Padding so annotation boxes near the extremes are not clipped.
    x_pad = (max(xs) - min(xs)) * 0.14 or 1
    y_pad = (max(ys) - min(ys)) * 0.16 or 0.05
    ax.set_xlim(min(xs) - x_pad, max(xs) + x_pad)
    ax.set_ylim(min(ys) - y_pad, max(ys) + y_pad)

    ax.set_xlabel("comment volume →", fontsize=11)
    ax.set_ylabel("intensity of feeling →", fontsize=11)
    ax.set_title(
        "Volume against intensity",
        fontsize=15, color=INK, pad=16, loc="left", fontweight="bold",
    )
    ax.text(
        0, 1.015,
        "dot size = like-weighted reach",
        transform=ax.transAxes, fontsize=10, color=INK_SOFT,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def composition_chart(totals: dict, out: Path) -> Path:
    """One stacked bar: how much of the conversation is about the car."""
    car, meta, un = totals["car"], totals["meta"], totals["unmapped"]
    total = max(car + meta + un, 1)

    fig, ax = plt.subplots(figsize=(11, 2.9))
    left = 0
    for value, color, name in [
        (car, ACCENT, "about the car"),
        (meta, WARN, "about the video / reviewer"),
        (un, INK_SOFT, "unmapped"),
    ]:
        if value <= 0:
            continue
        ax.barh(0, value, left=left, color=color, height=0.5)
        pct = value / total
        if pct > 0.07:
            ax.text(
                left + value / 2, 0,
                f"{pct:.0%}",
                ha="center", va="center", color=GROUND,
                fontsize=13, fontweight="bold",
            )
        ax.text(
            left + value / 2, -0.46,
            f"{name}\n{value:,}",
            ha="center", va="top", color=INK_MID, fontsize=10.5,
        )
        left += value

    ax.set_xlim(0, total)
    ax.set_ylim(-1.1, 0.6)
    ax.axis("off")
    ax.set_title(
        f"{total:,} clustered comments",
        fontsize=15, color=INK, pad=14, loc="left", fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def render_all(
    analysis: dict, out_dir: Path, modes: tuple[str, ...] = ("light",)
) -> list[Path]:
    """Render every chart in each requested theme into `out_dir`.

    Dark files keep the bare name (they are the ones dropped into a
    video edit); light files get a `-light` suffix and are what the web
    UI serves, so a chart never sits on the newsprint page as a dark
    rectangle. Returns the dark paths, which is what the report embeds.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    clusters = analysis["clusters"]

    jobs = [
        ("composition", lambda p: composition_chart(analysis["totals"], p)),
        ("aspects", lambda p: aspect_sentiment_chart(clusters, p)),
        ("volume-intensity", lambda p: volume_intensity_chart(clusters, p)),
    ]

    written: list[Path] = []
    for mode in modes:
        apply_theme(mode)
        # The first mode listed owns the bare filename; any others get a
        # suffix. With a single light theme this is just `aspects.png`.
        suffix = "" if mode == modes[0] else f"-{mode}"
        for name, fn in jobs:
            path = out_dir / f"{name}{suffix}.png"
            try:
                fn(path)
            except ValueError as exc:
                log.warning("skipped %s chart (%s): %s", name, mode, exc)
                continue
            if mode == modes[0]:
                written.append(path)
    return written
