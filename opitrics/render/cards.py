"""Social cards — 1200×675, sized for the X timeline.

Quote cards recreate the comment UI they came from rather than dressing
the text up as an editorial pull-quote. That is not a stylistic whim: a
card that looks like a comment reads as evidence, which is exactly the
claim being made. The alternative — big serif text on cream with a thin
accent rule — is the house style of every AI-generated quote graphic
and would undercut the point.

Usernames and avatars are deliberately anonymised. These are real people
who did not volunteer to appear in someone's content; the permalink on
the sources page is what makes a quote checkable, so nothing is lost by
withholding the handle.

Rendered with matplotlib so there is no browser dependency in the
pipeline. Everything is drawn in figure coordinates.
"""

from __future__ import annotations

import hashlib
import logging
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Ellipse, FancyBboxPatch, Rectangle  # noqa: E402

from opitrics.render.charts import CJK_FONTS, LIGHT, _pick_font  # noqa: E402

log = logging.getLogger(__name__)

W, H = 1200, 675
DPI = 100

# Comment-UI palette. Deliberately not the newsprint palette — this is a
# screen surface, and it should read as one.
UI = {
    "ground": "#FFFFFF",     # YouTube light mode
    "surface": "#F9F9F9",
    "text": "#0F0F0F",
    "meta": "#606060",
    "dim": "#909090",
    "rule": "#E5E5E5",
    "accent": "#065FD4",     # the blue used for interactive text
    "like": "#606060",
}

# Avatars are flat colour blocks rather than initials — an initial is
# still identifying information.
AVATAR_COLOURS = [
    "#C0392B", "#1B5E9E", "#1E7D45", "#8A6A0B",
    "#6C3483", "#0E6655", "#96430F", "#4A5A69",
]


def _avatar_colour(seed: str) -> str:
    digest = hashlib.sha256(seed.encode()).digest()
    return AVATAR_COLOURS[digest[0] % len(AVATAR_COLOURS)]


def _fig(bg: str) -> tuple:
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _tracked(text: str) -> str:
    """Fake letter-spacing — matplotlib has no such property."""
    return " ".join(text)


# Latin faces, in preference order. A Japanese face will happily set
# Latin text, but its roman glyphs are an afterthought — mixing the two
# on one card is visible as a mismatch in weight and rhythm, so each
# script gets a face designed for it.
LATIN_FONTS = ["Helvetica Neue", "Avenir Next", "Helvetica", "Arial", "DejaVu Sans"]

# Emoji have no glyph in either face, so matplotlib draws the missing-
# character box. Stripping them is better than shipping tofu.
#
# The ranges are deliberately narrow. An earlier version used
# \U000024C2-\U0001F251, which spans the entire CJK block and silently
# deleted Japanese comments — a destructive bug that looked like a
# rendering fault. Every range below is checked to exclude CJK.
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "\U0001FA00-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\U00002600-\U000027BF"   # misc symbols & dingbats
    "\U00002B00-\U00002BFF"   # arrows
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0000200D"              # zero-width joiner
    "\U000023E9-\U000023FA"   # media controls
    "❤★☆✓✔✕✖▶◀■□●○◆◇]+",
    flags=re.UNICODE,
)


def _latin_font() -> str | None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in LATIN_FONTS:
        if name in available:
            return name
    return None


def _renderable(char: str, font_paths: tuple[str, ...]) -> bool:
    """Whether any available face has a glyph for this character.

    The regex ranges catch the common emoji, but Unicode keeps adding
    pictographs and a single missed one shows up as a tofu box in the
    middle of a quote. Asking the font files directly is exact.
    """
    from fontTools.ttLib import TTFont

    code = ord(char)
    for path in font_paths:
        try:
            font = _FONT_CACHE.get(path)
            if font is None:
                font = TTFont(path, fontNumber=0, lazy=True)
                _FONT_CACHE[path] = font
            for table in font["cmap"].tables:
                if code in table.cmap:
                    return True
        except Exception:  # noqa: BLE001 - an unreadable face just fails over
            continue
    return False


_FONT_CACHE: dict = {}


def _font_files() -> tuple[str, ...]:
    wanted = set(LATIN_FONTS) | set(CJK_WIDE_FONTS) | set(CJK_FONTS)
    return tuple(
        f.fname for f in font_manager.fontManager.ttflist if f.name in wanted
    )


def strip_emoji(text: str) -> str:
    """Remove emoji and anything the available fonts cannot draw.

    Two passes: the regex handles the bulk cheaply, then any remaining
    non-ASCII, non-CJK character is checked against the actual font
    files. Shipping a tofu box in a quote undermines the claim that the
    quote is real.
    """
    cleaned = EMOJI_RE.sub("", text)

    suspects = {
        ch
        for ch in cleaned
        if ord(ch) > 0x2000
        and not ("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" or "！" <= ch <= "･")
    }
    if suspects:
        files = _font_files()
        drop = {ch for ch in suspects if not _renderable(ch, files)}
        if drop:
            cleaned = "".join(ch for ch in cleaned if ch not in drop)

    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


# Faces covering Simplified Chinese as well as Japanese. Hiragino Sans
# alone lacks the simplified forms — 这, 该, 谢 and friends render as
# tofu — and this corpus contains Chinese comments arguing back at the
# Japanese ones, so both scripts have to work.
CJK_WIDE_FONTS = ["Hiragino Sans GB", "Arial Unicode MS", "Heiti SC", "Songti SC"]

# Simplified-only forms, used to detect that a comment needs the wider
# face rather than the Japanese one.
SIMPLIFIED_RE = re.compile(
    "[这该谢样竞对现车为费优产术经许历实时护业们个来国说没还爱东"
    "长门问题发点无书报见风飞马鸟鱼龙师学习气电话买卖]"
)


def _cjk_font(text: str) -> str | None:
    """Pick a face that can actually set this text.

    Japanese-only faces are preferred for Japanese because their kana
    are better drawn, but a comment containing simplified characters
    needs the wider family or it renders as boxes.
    """
    available = {f.name for f in font_manager.fontManager.ttflist}
    if SIMPLIFIED_RE.search(text):
        for name in CJK_WIDE_FONTS:
            if name in available:
                return name
    return _pick_font()


def _is_cjk(text: str) -> bool:
    cjk = sum(1 for ch in text if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿")
    return cjk > len(text) * 0.2


def _wrap(text: str, width: int, max_lines: int) -> str:
    lines = textwrap.wrap(text, width=width) or [""]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    kept = lines[:max_lines]
    kept[-1] = kept[-1][: max(0, width - 1)].rstrip() + "…"
    return "\n".join(kept)


def _cjk_wrap(text: str, width: int, max_lines: int) -> str:
    """CJK has no spaces to break on, so wrap by character count."""
    out: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            continue
        out.extend(
            paragraph[i : i + width] for i in range(0, len(paragraph), width)
        )
    if not out:
        return ""
    if len(out) <= max_lines:
        return "\n".join(out)
    kept = out[:max_lines]
    kept[-1] = kept[-1][: width - 1] + "…"
    return "\n".join(kept)


def _fit_body(text: str) -> tuple[str, int, int]:
    """Choose wrap width and type size so the comment fills the body area
    without running past the card's right edge.

    Widths are measured against the ~0.80 of card width available to the
    body column, at 1200px. CJK glyphs are full-width, so they fit
    roughly half as many characters per line as Latin at the same size.
    """
    if _is_cjk(text):
        ladder = ((28, 24, 3), (24, 28, 4), (20, 34, 5), (17, 40, 6))
    else:
        ladder = ((28, 42, 3), (24, 50, 4), (20, 60, 5), (17, 72, 6))

    wrap = _cjk_wrap if _is_cjk(text) else _wrap
    for size, width, max_lines in ladder:
        body = wrap(text, width, max_lines)
        if len(body.split("\n")) <= max_lines and len(text) <= width * max_lines:
            return body, size, len(body.split("\n"))

    size, width, max_lines = ladder[-1]
    body = wrap(text, width, max_lines)
    return body, size, len(body.split("\n"))


def _thumb_icon(ax, x: float, y: float, colour: str, size: float = 0.016) -> None:
    """A small thumbs-up glyph, drawn rather than typeset so it does not
    depend on an emoji font being present."""
    ax.add_patch(Rectangle((x, y - size * 0.55), size * 0.42, size * 1.1,
                           facecolor=colour, edgecolor="none", alpha=0.9))
    ax.add_patch(FancyBboxPatch(
        (x + size * 0.52, y - size * 0.55), size * 0.9, size * 1.15,
        boxstyle="round,pad=0,rounding_size=0.004",
        facecolor=colour, edgecolor="none", alpha=0.9,
    ))


def quote_card(
    original: str,
    english: str,
    likes: int,
    subject: str,
    context: str,
    out: Path,
    replies: int = 0,
    comment_id: str | None = None,
) -> Path:
    """A comment, drawn as the comment it is.

    Layout follows the real thing closely enough to read as authentic —
    avatar, name line, body, like count, reply affordance — while the
    identity itself is withheld.
    """
    jp_font = _pick_font()
    latin = _latin_font()
    if jp_font:
        plt.rcParams["font.family"] = jp_font

    fig, ax = _fig(UI["ground"])

    # ── header strip ────────────────────────────────────────
    ax.text(0.055, 0.935, _tracked(context.upper()), fontsize=11,
            color=UI["dim"], family="monospace", va="center")
    ax.text(0.945, 0.935, _tracked("YOUTUBE COMMENT"), fontsize=10,
            color=UI["dim"], family="monospace", ha="right", va="center")
    ax.plot([0.055, 0.945], [0.895, 0.895], color=UI["rule"], lw=1)

    # ── measure, then centre ────────────────────────────────
    # A short comment and a long one should both sit optically centred
    # in the card rather than hanging from a fixed top edge, so the
    # block height is computed before anything is drawn.
    clean = strip_emoji(original)
    body, size, lines = _fit_body(clean)
    line_height = (size * 1.42) / H

    # Each script gets a face that can set it. The body may be Japanese,
    # Chinese or Latin; the translation is always Latin.
    body_font = _cjk_font(clean) if _is_cjk(clean) else (latin or jp_font)

    translation = ""
    trans_lines = 0
    if english and english.strip() != original.strip():
        translation = _wrap(strip_emoji(english), 74, 3)
        trans_lines = len(translation.split("\n"))

    NAME_H = 0.085
    GAP = 0.085          # breathing room between the two scripts
    TRANS_LH = (15.5 * 1.35) / H
    ENGAGE_GAP = 0.095

    block = (
        NAME_H
        + lines * line_height
        + (GAP + trans_lines * TRANS_LH if translation else 0)
        + ENGAGE_GAP
    )
    # Centre within the area between the header and footer rules, nudged
    # slightly up so the block reads as optically centred rather than
    # mathematically so.
    free = 0.855 - 0.145 - block
    top = 0.855 - max(free / 2, 0.02) + 0.015

    # ── avatar ──────────────────────────────────────────────
    # Ellipse dimensions corrected for the 16:9 figure, or the circle
    # renders as a squashed oval.
    seed = comment_id or original
    radius = 0.026
    name_y = top - 0.028
    ax.add_patch(Ellipse((0.086, name_y), radius, radius * (W / H),
                         facecolor=_avatar_colour(seed), edgecolor="none"))

    # ── name line — anonymised on purpose ───────────────────
    ax.text(0.132, name_y, "▬" * 7, fontsize=13,
            color=UI["rule"], family="monospace", va="center")
    ax.text(0.268, name_y, "identity withheld", fontsize=12.5,
            color=UI["dim"], va="center", family=latin or jp_font)

    # ── body ────────────────────────────────────────────────
    body_top = top - NAME_H
    ax.text(0.132, body_top, body, fontsize=size, color=UI["text"],
            va="top", linespacing=1.42, family=body_font)
    cursor = body_top - lines * line_height

    if translation:
        cursor -= GAP
        ax.text(0.132, cursor, translation, fontsize=15.5,
                color=UI["meta"], va="top", linespacing=1.35,
                family=latin or jp_font)
        cursor -= trans_lines * TRANS_LH

    # ── engagement row ──────────────────────────────────────
    engage_y = cursor - ENGAGE_GAP * 0.75
    _thumb_icon(ax, 0.132, engage_y, UI["like"])
    ax.text(0.163, engage_y, f"{likes:,}", fontsize=15,
            color=UI["meta"], va="center", family="monospace")
    if replies:
        ax.text(0.248, engage_y, f"{replies:,} replies", fontsize=14,
                color=UI["accent"], va="center", family=latin or jp_font)

    # ── footer ──────────────────────────────────────────────
    ax.plot([0.055, 0.945], [0.10, 0.10], color=UI["rule"], lw=1)
    ax.text(0.055, 0.055, _tracked("OPITRICS"), fontsize=10.5,
            color=UI["meta"], family="monospace", weight="bold", va="center")
    ax.text(0.945, 0.055,
            "verifiable — every quote links to its source",
            fontsize=11, color=UI["dim"], ha="right", va="center",
            family=latin or jp_font)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def stat_card(
    figure: str,
    caption: str,
    detail: str,
    subject: str,
    out: Path,
    tone: str = "accent",
) -> Path:
    """One large figure, in the same screen idiom as the quote cards."""
    jp_font = _pick_font()
    latin = _latin_font()
    if jp_font:
        plt.rcParams["font.family"] = jp_font

    fig, ax = _fig(UI["ground"])
    colour = {
        "accent": UI["accent"],
        "pos": LIGHT["pos"],
        "neg": "#FF6B6B",
    }.get(tone, UI["accent"])

    ax.text(0.055, 0.935, _tracked(subject.replace("-", " ").upper()),
            fontsize=11, color=UI["dim"], family="monospace", va="center")
    ax.plot([0.055, 0.945], [0.895, 0.895], color=UI["rule"], lw=1)

    ax.text(0.5, 0.60, figure, fontsize=140, color=colour,
            ha="center", va="center", weight="bold", family=latin or jp_font)
    ax.text(0.5, 0.365, _wrap(strip_emoji(caption), 40, 2), fontsize=28,
            color=UI["text"], ha="center", va="top", linespacing=1.35,
            family=latin or jp_font)
    if detail:
        clean = strip_emoji(detail)
        ax.text(0.5, 0.225, _wrap(clean, 74, 2), fontsize=15,
                color=UI["dim"], ha="center", va="top", linespacing=1.45,
                family=(jp_font if _is_cjk(clean) else (latin or jp_font)))

    ax.plot([0.055, 0.945], [0.10, 0.10], color=UI["rule"], lw=1)
    ax.text(0.055, 0.055, _tracked("OPITRICS"), fontsize=10.5,
            color=UI["meta"], family="monospace", weight="bold", va="center")
    ax.text(0.945, 0.055, "verifiable — every quote links to its source",
            fontsize=11, color=UI["dim"], ha="right", va="center",
            family=latin or jp_font)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def verdict_card(
    praise: list[tuple[str, int]],
    complaints: list[tuple[str, int]],
    subject: str,
    out: Path,
    note: str = "",
) -> Path:
    """Two columns: what people praise, what they complain about.

    The three existing card kinds are a quote, one big number, and a
    chart — all of which show a single fact and none of which reads as
    a judgement. A viewer scrolling wants to know whether the thing is
    any good, and the fastest legible answer to that is two lists side
    by side.

    It carries a caveat by construction rather than by discipline. On
    this corpus the largest "complaint" is a nationalist brand-trust
    argument, which the aspect taxonomy files as being about the car
    and which a naive pros-and-cons card would present as people
    disliking the vehicle. `note` is where that gets said, and callers
    that pass themes about the badge rather than the object should say
    so there.

    Counts sit beside each line rather than in the prose, same as every
    other card: the figure is the card's job.
    """
    jp_font = _pick_font()
    latin = _latin_font()
    if jp_font:
        plt.rcParams["font.family"] = jp_font

    fig, ax = _fig(UI["ground"])

    # Two solid colour fields, edge to edge, split down the middle. The
    # first version was thin type and whitespace on white, which is the
    # look of every generated infographic and reads as one. The quote
    # cards escape that by recreating a real interface; this has no such
    # anchor, so it earns its own presence with weight instead.
    pos_colour, neg_colour = LIGHT["pos"], LIGHT["neg"]
    ax.add_patch(Rectangle((0, 0.175), 0.5, 0.69, facecolor=pos_colour,
                           edgecolor="none", zorder=0))
    ax.add_patch(Rectangle((0.5, 0.175), 0.5, 0.69, facecolor=neg_colour,
                           edgecolor="none", zorder=0))

    ax.text(0.03, 0.945, _tracked(subject.replace("-", " ").upper()),
            fontsize=12, color=UI["text"], family="monospace",
            weight="bold", va="center")

    ax.text(0.25, 0.815, _tracked("PRAISED"), fontsize=20, color="#FFFFFF",
            family="monospace", weight="bold", ha="center", va="center",
            zorder=3)
    ax.text(0.75, 0.815, _tracked("CRITICISED"), fontsize=20, color="#FFFFFF",
            family="monospace", weight="bold", ha="center", va="center",
            zorder=3)

    def column(items: list[tuple[str, int]], left: float) -> None:
        """Count first and large, then the theme under it.

        The number leads because it is the thing that survives being
        seen at thumbnail size, and because the label is often a
        clause-long cluster name that nobody reads at a glance.
        """
        # Three rows, not four. Four fitted only by crowding, and the
        # last one clipped through the colour field into the caveat.
        # Three at this size is legible at thumbnail scale, which is
        # the whole reason for the format.
        y = 0.700
        for label, size in items[:3]:
            clean = strip_emoji(label)
            wrapped = _wrap(clean, 26, 2)
            lines = wrapped.count("\n") + 1

            ax.text(left, y, f"{size:,}", fontsize=52, color="#FFFFFF",
                    weight="bold", va="top", zorder=3,
                    family=latin or jp_font)
            ax.text(left + 0.145, y - 0.014, wrapped, fontsize=17,
                    color="#FFFFFF", va="top", linespacing=1.3, zorder=3,
                    family=(jp_font if _is_cjk(clean) else (latin or jp_font)))
            y -= 0.175

    column(praise, 0.035)
    column(complaints, 0.535)

    # The caveat sits on white below the colour, in black. Grey small
    # print under a bold graphic reads as a disclaimer nobody meant;
    # this one is load-bearing and should look deliberate.
    if note:
        ax.text(0.03, 0.115, _wrap(strip_emoji(note), 100, 2), fontsize=13,
                color=UI["text"], va="top", linespacing=1.45,
                family=latin or jp_font)
    ax.text(0.97, 0.045, "every number links to the comment it came from",
            fontsize=11.5, color=UI["dim"], ha="right", va="center",
            family=latin or jp_font)

    ax.text(0.97, 0.945, _tracked("OPITRICS"), fontsize=12,
            color=UI["text"], family="monospace", weight="bold",
            ha="right", va="center")

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def compare_card(
    left: tuple[str, dict],
    right: tuple[str, dict],
    rows: list[tuple[str, str, str]],
    out: Path,
    note: str = "",
) -> Path:
    """Two cars, one metric per row, side by side.

    Every row is a SHARE or a rate, never a raw count. The corpora are
    not the same size — the Racco drew 15,950 comments and the e Sky
    2,948 — so "681 comments argued about the badge" against "105
    argued with each other" compares audience size, not opinion, and
    reads as the bigger car winning something.

    `rows` is (label, left_value, right_value) already formatted, so
    the caller decides what is comparable. This draws it.

    The larger side of each row is emphasised rather than coloured
    good or bad: on "share not about the car" the bigger number is not
    better, and a green-versus-red reading would invent a verdict the
    data does not support.
    """
    jp_font = _pick_font()
    latin = _latin_font()
    if jp_font:
        plt.rcParams["font.family"] = jp_font

    left_name, _ = left
    right_name, _ = right

    fig, ax = _fig(UI["ground"])

    ax.add_patch(Rectangle((0, 0.755), 1.0, 0.13, facecolor=UI["text"],
                           edgecolor="none", zorder=0))
    ax.text(0.28, 0.818, left_name.upper(), fontsize=27, color="#FFFFFF",
            weight="bold", ha="center", va="center", zorder=3,
            family=latin or jp_font)
    ax.text(0.5, 0.818, "vs", fontsize=15, color="#8A8A8A",
            ha="center", va="center", zorder=3, style="italic",
            family=latin or jp_font)
    ax.text(0.76, 0.818, right_name.upper(), fontsize=27, color="#FFFFFF",
            weight="bold", ha="center", va="center", zorder=3,
            family=latin or jp_font)

    y = 0.645
    for label, left_value, right_value in rows[:4]:
        try:
            lead_left = float(re.sub(r"[^\d.]", "", left_value) or 0) >= \
                float(re.sub(r"[^\d.]", "", right_value) or 0)
        except ValueError:
            lead_left = True

        ax.text(0.28, y, left_value, fontsize=42,
                color=UI["text"] if lead_left else UI["dim"],
                weight="bold" if lead_left else "normal",
                ha="center", va="center", family=latin or jp_font)
        ax.text(0.76, y, right_value, fontsize=42,
                color=UI["dim"] if lead_left else UI["text"],
                weight="normal" if lead_left else "bold",
                ha="center", va="center", family=latin or jp_font)
        ax.text(0.5, y, _wrap(strip_emoji(label), 22, 2), fontsize=14,
                color=UI["meta"], ha="center", va="center",
                linespacing=1.3, family=latin or jp_font)
        y -= 0.145
        if y > 0.16:
            ax.plot([0.04, 0.96], [y + 0.072, y + 0.072],
                    color=UI["rule"], lw=1)

    if note:
        ax.text(0.04, 0.105, _wrap(strip_emoji(note), 100, 2), fontsize=13,
                color=UI["text"], va="top", linespacing=1.45,
                family=latin or jp_font)

    ax.text(0.04, 0.93, _tracked("OPITRICS"), fontsize=12, color=UI["text"],
            family="monospace", weight="bold", va="center")
    ax.text(0.96, 0.045, "every number links to the comments it came from",
            fontsize=11.5, color=UI["dim"], ha="right", va="center",
            family=latin or jp_font)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out


def chart_card(chart_path: Path, title: str, subject: str, out: Path) -> Path:
    """Wrap a chart in the same furniture.

    Uses the dark chart variant so the card is consistent with the quote
    cards around it in a thread.
    """
    import matplotlib.image as mpimg

    jp_font = _pick_font()
    latin = _latin_font()
    if jp_font:
        plt.rcParams["font.family"] = jp_font

    fig, ax = _fig(UI["ground"])
    ax.text(0.055, 0.935, _tracked(title.upper()), fontsize=11,
            color=UI["dim"], family="monospace", va="center")
    ax.plot([0.055, 0.945], [0.895, 0.895], color=UI["rule"], lw=1)

    img = mpimg.imread(chart_path)
    inner = fig.add_axes([0.05, 0.135, 0.90, 0.72])
    inner.imshow(img)
    inner.axis("off")

    ax.plot([0.055, 0.945], [0.10, 0.10], color=UI["rule"], lw=1)
    ax.text(0.055, 0.055, _tracked("OPITRICS"), fontsize=10.5,
            color=UI["meta"], family="monospace", weight="bold", va="center")
    ax.text(0.945, 0.055, "verifiable — every quote links to its source",
            fontsize=11, color=UI["dim"], ha="right", va="center",
            family=latin or jp_font)

    fig.savefig(out, facecolor=UI["ground"])
    plt.close(fig)
    return out
