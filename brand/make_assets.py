"""Render the account identity assets — avatar, banner, thumbnail plate.

    .venv/bin/python brand/make_assets.py

Writes PNGs into brand/out/. Regenerate rather than hand-editing; the
palette is imported from the same values the shorts use, so a change to
the video theme should be mirrored here and the two re-run together.

The mark is two divided bars: the finding this account produces is that
a comment section split, and the interesting number is where. Meaning
rides on the white/blue contrast rather than on fine detail, which is
what lets it survive being shrunk to a reply avatar.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "out"

# Mirrors remotion/src/theme.ts — the palette a viewer actually meets.
# The shorts are white-ground/black-text; the profile is the inverse so
# the avatar reads as an object on a white feed rather than a hole in it.
GROUND = "#FFFFFF"
SURFACE = "#F4F4F4"
INK = "#000000"
META = "#3D3D3D"
DIM = "#5A5A5A"
RULE = "#BFBFBF"
ACCENT = "#0546A8"

MONO = "/System/Library/Fonts/SFNSMono.ttf"

# Split points for the banner field. Spread wide, none near 0.5 — the
# same claim the avatar makes: comment sections rarely divide evenly.
FIELD_FRACS = (0.66, 0.38, 0.74, 0.44, 0.58, 0.31, 0.69, 0.47)

# Supersampling factor. Pillow has no antialiased line drawing, so
# everything is drawn large and downsampled with LANCZOS.
SS = 4


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO, size)


def tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    f: ImageFont.FreeTypeFont,
    fill: str,
    tracking: float,
) -> int:
    """Draw `text` with letter-spacing, returning the advance width.

    Pillow has no tracking, and the wordmark's whole character comes from
    letterSpacing 6 at 24px — a quarter of the em. Drawing per glyph is
    the only way to reproduce it.
    """
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking
    return int(x - xy[0] - tracking)


def tracked_width(text: str, f: ImageFont.FreeTypeFont, tracking: float) -> float:
    if not text:
        return 0.0
    return sum(f.getlength(c) for c in text) + tracking * (len(text) - 1)


def tally(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    height: float,
    stroke: float,
    gap: float,
    colour: str,
    diagonal: str,
    bars: int = 4,
) -> None:
    """One tally gate: `bars` verticals struck through by a diagonal.

    The diagonal is drawn in its own colour because it is the stroke that
    completes the count — the only accent in the identity marks the
    moment a tally closes.
    """
    span = gap * (bars - 1)
    x0 = cx - span / 2
    top, bottom = cy - height / 2, cy + height / 2

    for i in range(bars):
        x = x0 + i * gap
        draw.line([(x, top), (x, bottom)], fill=colour, width=int(stroke))

    # Overhangs the outer verticals slightly, the way a hand-drawn strike
    # does — a diagonal that stops exactly on the bars reads as a glyph
    # rather than as a gesture. Kept short: on the circular avatar mask a
    # long overhang clips at the disc edge and the strike stops looking
    # like a strike.
    over = gap * 0.30
    draw.line(
        [(x0 - over, bottom - height * 0.20), (x0 + span + over, top + height * 0.20)],
        fill=diagonal,
        width=int(stroke),
    )


def split_mark(
    draw: ImageDraw.ImageDraw,
    s: int,
    *,
    bar_h: float,
    gap: float,
    inset: float,
    notch: float,
    fracs: tuple[float, ...],
) -> None:
    """Two bars, each divided at a different point.

    The finding this account produces is almost never "people liked it"
    — it is that the comment section split, and the interesting number
    is where. The mark is that, and nothing else.

    Two bars rather than one, for a reason that is not aesthetic: a
    single divided bar reads as a progress bar or a battery, and that
    association is strong enough to overwrite the intended meaning.
    Nothing displays two progress bars at different values, so the
    second bar destroys the misreading.

    No `frac` sits near 0.5. The asymmetry is the content — a comment
    section that divides evenly is the one result the data essentially
    never gives, and a centred mark would claim it.
    """
    x0, x1 = s * inset, s * (1.0 - inset)
    total = bar_h * len(fracs) + gap * (len(fracs) - 1)
    y = (s - total) / 2

    for frac in fracs:
        cut = x0 + (x1 - x0) * frac
        draw.rectangle([x0, y, cut - notch, y + bar_h], fill=GROUND)
        draw.rectangle([cut + notch, y, x1, y + bar_h], fill=ACCENT)
        y += bar_h + gap


def avatar(size: int = 800, *, small: bool = False) -> Path:
    """Circular-safe avatar: a tally on ink.

    Drawn on a square; every platform masks it to a circle.

    `small` renders the reply-size variant: thicker bars, a tighter
    notch and a wider inset, because at 24px the divisions are the first
    thing to close up and the mark flattens into two blue-and-white
    smudges.
    """
    s = size * SS
    img = Image.new("RGB", (s, s), INK)
    d = ImageDraw.Draw(img)

    # Geometry, arrived at by looking at the 24px proof rather than by
    # reasoning about it. Three constraints fought each other:
    #
    #   - The verticals must read as FOUR. Wider gaps, fewer apparent
    #     bars. At 0.176 the disc looked like a barcode and the count
    #     was gone.
    #   - The strike must stay inside the circular mask, or it clips
    #     into a stray diagonal bar that reads as a "no entry" sign.
    #     That caps both the bar span and the diagonal's overhang.
    #   - Stroke and gap need clearly different weights, or the whole
    #     mark greys out at reply size.
    if small:
        split_mark(
            d,
            s,
            bar_h=s * 0.215,
            gap=s * 0.095,
            inset=0.205,
            notch=s * 0.024,
            fracs=(0.66, 0.42),
        )
    else:
        split_mark(
            d,
            s,
            bar_h=s * 0.180,
            gap=s * 0.090,
            inset=0.190,
            notch=s * 0.020,
            fracs=(0.66, 0.42),
        )

    img = img.resize((size, size), Image.LANCZOS)
    path = OUT / f"avatar-{size}{'-small' if small else ''}.png"
    img.save(path)
    return path


def avatar_wordmark(size: int = 800) -> Path:
    """Fallback avatar: `OP` in the wordmark's own specification.

    Two letters is the ceiling at 48px. Three crushes. Monospace tracking
    adds trailing space after the final glyph, so the block is measured
    without it and centred on the true ink width.
    """
    s = size * SS
    img = Image.new("RGB", (s, s), INK)
    d = ImageDraw.Draw(img)

    f = font(int(s * 0.40))
    tracking = s * 0.055
    text = "OP"

    w = tracked_width(text, f, tracking)
    box = d.textbbox((0, 0), text, font=f)
    x = (s - w) / 2
    y = (s - (box[3] - box[1])) / 2 - box[1]

    tracked(d, (int(x), int(y)), text, f, GROUND, tracking)

    img = img.resize((size, size), Image.LANCZOS)
    path = OUT / f"avatar-wordmark-{size}.png"
    img.save(path)
    return path


def banner() -> Path:
    """YouTube channel art, 2560x1440.

    Only the centre 1546x423 is guaranteed visible — that is the mobile
    crop, and all text lives inside it. Desktop reveals ~2560x423, TV the
    whole canvas. The tally field outside the safe area means the wider
    crops are a reward rather than the mobile crop being a truncation.

    The avatar overlaps the lower-left of the desktop strip, so the text
    block sits right of centre-left and clear of it.
    """
    W, H = 2560, 1440
    s_w, s_h = W * 2, H * 2  # half the usual supersample; 5120px is enough
    img = Image.new("RGB", (s_w, s_h), GROUND)
    d = ImageDraw.Draw(img)

    safe_w, safe_h = 1546 * 2, 423 * 2
    safe_x0 = (s_w - safe_w) / 2
    safe_y0 = (s_h - safe_h) / 2

    # --- the field: thousands of divided bars, fading outward ----------
    # Deterministic placement. No RNG, so the banner is reproducible and
    # a re-run produces a byte-identical file.
    # Proportioned to echo the avatar: the mark there is a bar roughly
    # 1:3.4 against its own span, sitting in generous padding. A field
    # of much flatter, tighter bars reads as a different mark entirely,
    # so height and spacing are opened up to match.
    mark_h = 14 * 2
    mark_w = 58 * 2
    mark_gap = 7 * 2
    col_pitch = 84 * 2
    row_pitch = 34 * 2

    for row in range(int(s_h / row_pitch) + 2):
        cy = row * row_pitch + row_pitch / 2
        # Stagger alternate rows so the field reads as a list rather
        # than as a grid.
        offset = (row % 3) * col_pitch / 3
        for col in range(int(s_w / col_pitch) + 2):
            cx = col * col_pitch + offset

            # Distance from the safe area, normalised — the field fades
            # out as it approaches the text and is absent behind it.
            dx = max(0.0, max(safe_x0 - cx, cx - (safe_x0 + safe_w)))
            dy = max(0.0, max(safe_y0 - cy, cy - (safe_y0 + safe_h)))
            dist = (dx**2 + dy**2) ** 0.5

            if dist < 90 * 2:
                continue

            # Fade with distance from the plate, capped well below the
            # rule colour so it stays texture and never competes.
            #
            # The horizontal and vertical falloffs are deliberately
            # different. Left and right the field runs long, because
            # that band is only ever seen on desktop and TV where it is
            # the reward for a wider crop. Above and below it fades out
            # fast: that region sits inside the desktop strip, close to
            # the text, and a field that stays dense there turns the
            # wordmark into something read through a screen door.
            t_x = min(1.0, dx / (620 * 2))
            t_y = min(1.0, dy / (150 * 2))
            t = max(t_x, t_y) * (1.0 - 0.55 * t_y)

            v = int(255 - (255 - 0xBF) * t)
            shade = f"#{v:02X}{v:02X}{v:02X}"

            # A divided bar, matching the avatar. The split point varies
            # per cell — the field is many findings, each dividing its
            # own way, and a field of identical bars would read as a
            # pattern rather than as data.
            #
            # Cycled deterministically rather than randomly so the
            # banner is reproducible byte for byte.
            frac = FIELD_FRACS[(row * 5 + col * 3) % len(FIELD_FRACS)]
            bw = mark_w
            bx0 = cx - bw / 2
            cut = bx0 + bw * frac
            notch = mark_gap * 0.30

            d.rectangle(
                [bx0, cy - mark_h / 2, cut - notch, cy + mark_h / 2],
                fill=shade,
            )
            d.rectangle(
                [cut + notch, cy - mark_h / 2, bx0 + bw, cy + mark_h / 2],
                fill=shade,
            )

    # --- the plate: text sits on solid ground, never on the field ------
    plate_pad_x, plate_pad_y = 150 * 2, 96 * 2
    d.rectangle(
        [
            safe_x0 - plate_pad_x,
            safe_y0 - plate_pad_y,
            safe_x0 + safe_w + plate_pad_x,
            safe_y0 + safe_h + plate_pad_y,
        ],
        fill=GROUND,
    )

    # --- the text ------------------------------------------------------
    word_f = font(int(148 * 2))
    word_track = 32 * 2
    sub_f = font(int(36 * 2))
    sub_track = 5.0 * 2

    word = "OPITRICS"
    sub = "COMMENT SECTIONS, COUNTED."
    sub2 = "EVERY NUMBER LINKS TO ITS SOURCE."

    # Left edge shared by all three lines, inside the safe area and clear
    # of the avatar's lower-left overlap on desktop.
    tx = safe_x0 + 40 * 2
    block_cy = s_h / 2

    wb = d.textbbox((0, 0), word, font=word_f)
    word_h = wb[3] - wb[1]
    gap_1 = 52 * 2
    sub_h = d.textbbox((0, 0), sub, font=sub_f)[3] - d.textbbox((0, 0), sub, font=sub_f)[1]
    gap_2 = 20 * 2

    # The rule hangs below the last line, so the ink extends further down
    # than `total` suggests. Centring on `total` alone drops the whole
    # block low in the frame — measure to the rule instead.
    rule_drop = 44 * 2 + 5 * 2
    total = word_h + gap_1 + sub_h + gap_2 + sub_h + rule_drop
    y = block_cy - total / 2

    tracked(d, (int(tx), int(y - wb[1])), word, word_f, INK, word_track)
    y += word_h + gap_1

    sb = d.textbbox((0, 0), sub, font=sub_f)
    tracked(d, (int(tx), int(y - sb[1])), sub, sub_f, META, sub_track)
    y += sub_h + gap_2
    tracked(d, (int(tx), int(y - sb[1])), sub2, sub_f, META, sub_track)

    # A rule under the block, the width of the wordmark — the same
    # hairline the cards use to separate a claim from its evidence.
    rule_y = y + sub_h + 44 * 2
    rule_w = tracked_width(word, word_f, word_track)
    d.line(
        [(tx, rule_y), (tx + rule_w, rule_y)],
        fill=ACCENT,
        width=int(5 * 2),
    )

    img = img.resize((W, H), Image.LANCZOS)
    path = OUT / "banner-2560x1440.png"
    img.save(path)
    return path


def banner_crops(src: Path) -> list[Path]:
    """The crops each platform actually shows, for checking before upload.

    All are centre crops of the same master, which is why the text block
    is centred rather than sitting where a single platform wants it: one
    render has to survive 6:1 and 3:1 without re-laying anything out.

    X's header is 3:1 and is the odd one — it is far taller relative to
    its width than YouTube's visible strip, so it picks up field texture
    above and below the text where YouTube shows almost none.
    """
    img = Image.open(src)
    W, H = img.size
    out = []

    crops = {
        "mobile-1546x423": (1546, 423),
        "desktop-2560x423": (2560, 423),
        # X header. Uploaded at 1500x500; cropped at 2400x800 first so
        # the downscale is a clean 1.6x rather than resampling from an
        # awkward ratio.
        "x-2400x800": (2400, 800),
    }
    for name, (cw, ch) in crops.items():
        x0 = (W - cw) // 2
        y0 = (H - ch) // 2
        p = OUT / f"banner-crop-{name}.png"
        img.crop((x0, y0, x0 + cw, y0 + ch)).save(p)
        out.append(p)

    # The X header at its actual upload size, from the 3:1 crop.
    x_src = OUT / "banner-crop-x-2400x800.png"
    if x_src.exists():
        p = OUT / "header-x-1500x500.png"
        Image.open(x_src).resize((1500, 500), Image.LANCZOS).save(p)
        out.append(p)
    return out


def avatar_proof(src: Path, small_src: Path) -> Path:
    """The avatar at the sizes it is actually seen, on both feed grounds.

    Reading the 800px master proves nothing — every legibility failure in
    this repo was found by looking at the size the viewer sees. 24px uses
    the small variant, which is what would actually be uploaded for
    reply-size use.
    """
    sizes = [88, 48, 24]
    pad = 24
    master = Image.open(src)
    small = Image.open(small_src)

    # Two rows: on white (X, YouTube light) and on near-black (dark mode).
    w = sum(s + pad for s in sizes) + pad
    h = (88 + pad) * 2 + pad

    sheet = Image.new("RGB", (w, h), SURFACE)
    for row, bg in enumerate([GROUND, "#0F0F0F"]):
        y = pad + row * (88 + pad)
        ImageDraw.Draw(sheet).rectangle([0, y - pad // 2, w, y + 88 + pad // 2], fill=bg)
        x = pad
        for s in sizes:
            source = small if s <= 24 else master
            a = source.resize((s, s), Image.LANCZOS)
            mask = Image.new("L", (s * SS, s * SS), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, s * SS, s * SS], fill=255)
            sheet.paste(a, (x, y + (88 - s) // 2), mask.resize((s, s), Image.LANCZOS))
            x += s + pad

    path = OUT / "proof-avatar-sizes.png"
    sheet.save(path)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    written = [
        # 1024 is TikTok's required app-icon size, and the largest any
        # platform has asked for. Render it from the same geometry
        # rather than upscaling a smaller file.
        avatar(1024),
        avatar(800),
        avatar(180),
        avatar(800, small=True),
        avatar_wordmark(800),
        banner(),
    ]
    written += banner_crops(OUT / "banner-2560x1440.png")
    written.append(
        avatar_proof(OUT / "avatar-800.png", OUT / "avatar-800-small.png")
    )

    for p in written:
        print(f"  {p.relative_to(Path.cwd()) if p.is_relative_to(Path.cwd()) else p}")


if __name__ == "__main__":
    main()
