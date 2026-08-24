"""Alternative avatar marks, for comparison against the tally.

    .venv/bin/python brand/explore_marks.py

Exploration only — nothing here is shipped. `make_assets.py` renders the
chosen mark; this file exists so the choice is made by looking at
candidates side by side at the size a viewer meets them, rather than by
arguing about them in prose.

Each candidate attacks a different idea. A mark that only restyles the
tally is not an alternative, it is the same mark twice:

  tally      — I counted, because I cannot hold this in my head
  split      — the finding is disagreement, not consensus
  thread     — one comment pulled out of the pile and read
  quote      — the evidence is somebody's actual words
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "out" / "explore"

GROUND = "#FFFFFF"
INK = "#000000"
DIM = "#5A5A5A"
RULE = "#BFBFBF"
ACCENT = "#0546A8"

MONO = "/System/Library/Fonts/SFNSMono.ttf"
SS = 4


def canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    s = size * SS
    img = Image.new("RGB", (s, s), INK)
    return img, ImageDraw.Draw(img), s


def finish(img: Image.Image, size: int, name: str) -> Path:
    img = img.resize((size, size), Image.LANCZOS)
    path = OUT / f"{name}-{size}.png"
    img.save(path)
    return path


def mark_split(size: int = 800) -> Path:
    """Two opposed stacks of bars, divided by a gap.

    The idea: what this account actually finds is *disagreement*. The
    story is rarely "people liked it" — it is that the comment section
    split, and the interesting number is how it split. A divided bar
    stack says argument, which is closer to the product than counting
    is.

    The gap is off-centre because a 50/50 split is the one result the
    data almost never gives, and a symmetrical mark would quietly claim
    balance.
    """
    img, d, s = canvas(size)

    bar_h = s * 0.098
    gap_v = s * 0.060
    x_pad = s * 0.185

    # Four rows, not five. At 48px a fifth row costs more than it adds —
    # the stack greys out — and four still reads as "several themes,
    # each splitting differently".
    #
    # The divisions are spread wide and none sits near 0.50, because a
    # symmetrical mark would quietly claim balance, and balance is the
    # one result a comment section essentially never gives.
    splits = [0.62, 0.34, 0.74, 0.44]
    total_h = len(splits) * bar_h + (len(splits) - 1) * gap_v
    y = (s - total_h) / 2

    for frac in splits:
        x0, x1 = x_pad, s - x_pad
        cut = x0 + (x1 - x0) * frac
        # Narrow: the gap only has to read as a division, and at 24px a
        # wide one eats the shorter side of the split entirely.
        notch = s * 0.011

        d.rectangle([x0, y, cut - notch, y + bar_h], fill=GROUND)
        d.rectangle([cut + notch, y, x1, y + bar_h], fill=ACCENT)
        y += bar_h + gap_v

    return finish(img, size, "split")


def mark_thread(size: int = 800) -> Path:
    """A stack of lines with one pulled out and marked.

    The idea: the method is not "count everything", it is "find the one
    comment that turns out to matter and put it in front of you". The
    stack is the corpus; the displaced line is the quote that made the
    video; the accent is where attention landed.

    This is the most literal of the four and the most legible at small
    size, because the anomaly reads before the pattern does.
    """
    img, d, s = canvas(size)

    rows = 7
    line_h = s * 0.052
    gap = s * 0.043
    total = rows * line_h + (rows - 1) * gap
    y = (s - total) / 2

    x0 = s * 0.20
    full = s * 0.60

    # Ragged right edge — a stack of real comments is not justified.
    widths = [0.86, 1.00, 0.72, 0.94, 0.66, 1.00, 0.80]
    pulled = 3  # zero-indexed row that steps out

    for i, w in enumerate(widths):
        if i == pulled:
            # Steps left, gets the accent, and is the only full-strength
            # element — everything else is recessive.
            d.rectangle(
                [x0 - s * 0.075, y, x0 - s * 0.075 + full * w, y + line_h],
                fill=ACCENT,
            )
        else:
            d.rectangle([x0, y, x0 + full * w, y + line_h], fill=DIM)
        y += line_h + gap

    return finish(img, size, "thread")


def mark_quote(size: int = 800) -> Path:
    """A quotation mark built from tally strokes.

    The idea: the hard rule of this project is that a quote is verbatim
    or it does not run. The quote mark is the promise; building it from
    counted strokes says the promise is backed by a count rather than by
    a claim.

    Two glyph-like blocks, each four short strokes with a diagonal —
    a tally compressed into the shape of an opening quotation mark.
    """
    img, d, s = canvas(size)

    def cluster(cx: float, cy: float, colour: str, diag: str) -> None:
        h = s * 0.30
        stroke = int(s * 0.052)
        gap = s * 0.098
        span = gap * 2
        x0 = cx - span / 2
        for i in range(3):
            x = x0 + i * gap
            d.line([(x, cy - h / 2), (x, cy + h / 2)], fill=colour, width=stroke)
        over = gap * 0.34
        d.line(
            [
                (x0 - over, cy + h * 0.30),
                (x0 + span + over, cy - h * 0.30),
            ],
            fill=diag,
            width=stroke,
        )

    # Set as an opening quote: two clusters, upper area, slight offset.
    cluster(s * 0.345, s * 0.44, GROUND, ACCENT)
    cluster(s * 0.655, s * 0.44, GROUND, ACCENT)

    # The baseline the quote sits on — the permalink rule, the same
    # hairline the cards use under a claim.
    d.rectangle(
        [s * 0.22, s * 0.700, s * 0.78, s * 0.700 + s * 0.026], fill=RULE
    )

    return finish(img, size, "quote")


def mark_split_one(size: int = 800, *, frac: float = 0.64) -> Path:
    """One bar, divided once. The reduction of `split`.

    Four rows said "several themes, each splitting differently". One row
    says only "divided", which is the half that carries — and it is the
    half that survives 24px, because a single division is the last thing
    to disappear.

    `frac` is deliberately not 0.5. The asymmetry is the content: a
    comment section that splits evenly is the result the data almost
    never gives, and a centred mark would claim it.
    """
    img, d, s = canvas(size)

    bar_h = s * 0.30
    x0, x1 = s * 0.13, s * 0.87
    y0 = (s - bar_h) / 2

    cut = x0 + (x1 - x0) * frac
    notch = s * 0.026

    d.rectangle([x0, y0, cut - notch, y0 + bar_h], fill=GROUND)
    d.rectangle([cut + notch, y0, x1, y0 + bar_h], fill=ACCENT)

    return finish(img, size, "split-one")


def mark_split_two(size: int = 800) -> Path:
    """Two bars, split at different points.

    The middle option: one bar risks reading as a progress bar or a
    battery, and two bars kills that reading instantly — nothing shows
    two progress bars at different values as a logo. Keeps a trace of
    "themes differ" without the density of four.
    """
    img, d, s = canvas(size)

    bar_h = s * 0.215
    gap = s * 0.105
    x0, x1 = s * 0.13, s * 0.87

    total = bar_h * 2 + gap
    y = (s - total) / 2

    for frac in (0.66, 0.38):
        cut = x0 + (x1 - x0) * frac
        notch = s * 0.022
        d.rectangle([x0, y, cut - notch, y + bar_h], fill=GROUND)
        d.rectangle([cut + notch, y, x1, y + bar_h], fill=ACCENT)
        y += bar_h + gap

    return finish(img, size, "split-two")


def contact_sheet(names: list[str], size: int = 800) -> Path:
    """Every candidate at 88 / 48 / 24px, circular-masked, on both feeds.

    The only view that decides anything. A mark that wins at 800px and
    dies at 48 has lost.
    """
    sizes = [140, 88, 48, 24]
    pad = 22
    label_h = 26

    col_w = sum(s + pad for s in sizes) + pad
    row_h = 140 + pad * 2 + label_h

    sheet = Image.new("RGB", (col_w, row_h * len(names) * 2), "#EDEDED")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(MONO, 15)

    y = 0
    for name in names:
        master = Image.open(OUT / f"{name}-{size}.png")
        for ground in (GROUND, "#0F0F0F"):
            d.rectangle([0, y, col_w, y + row_h], fill=ground)
            d.text(
                (pad, y + 8),
                f"{name}  ·  {'light' if ground == GROUND else 'dark'}",
                font=f,
                fill=DIM,
            )
            x = pad
            for s in sizes:
                a = master.resize((s, s), Image.LANCZOS)
                m = Image.new("L", (s * SS, s * SS), 0)
                ImageDraw.Draw(m).ellipse([0, 0, s * SS, s * SS], fill=255)
                sheet.paste(
                    a,
                    (x, y + label_h + pad + (140 - s) // 2),
                    m.resize((s, s), Image.LANCZOS),
                )
                x += s + pad
            y += row_h

    path = OUT / "contact-sheet.png"
    sheet.save(path)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    mark_split()
    mark_split_two()
    mark_split_one()
    mark_thread()
    mark_quote()

    # The incumbent, copied in for honest comparison.
    src = OUT.parent / "avatar-800.png"
    if src.exists():
        Image.open(src).save(OUT / "tally-800.png")

    names = ["split", "split-two", "split-one"]
    names = [n for n in names if (OUT / f"{n}-800.png").exists()]
    print(f"  {contact_sheet(names)}")


if __name__ == "__main__":
    main()
