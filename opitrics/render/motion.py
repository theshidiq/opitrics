"""Animated assembly of vertical cards.

The first version cut static cards together at fixed intervals, which
reads as a slideshow rather than a short. Movement is not decoration
here: on a platform where the first second decides whether anyone stays,
a frame that never changes gives the eye no reason to stay on it.

What moves and why:
- Cards drift and scale almost imperceptibly through their hold. The
  amount is small on purpose — the point is that the frame is alive,
  not that the viewer notices a zoom.
- Cuts are crossfades of a few frames, so the sequence reads as one
  piece rather than a series of stills.
- The hook's figure lands with a punch: a fast scale-down onto its
  resting size, which is the one moment worth emphasising.

Everything is timed to the narration, so a line that takes four seconds
to say holds for four seconds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 30


class MotionError(RuntimeError):
    """Raised when the animated render cannot be produced."""


@dataclass
class Shot:
    """One card and how long it stays on screen."""

    card: Path
    hold: float
    kind: str = "statement"
    audio: Path | None = None


def _drift(item, hold: float, index: int) -> None:
    """A slow push or pull across the shot.

    Alternating direction between shots stops the sequence feeling like
    one long zoom. The range is 1.00-1.06, which is perceptible as
    life in the frame but not as an effect.
    """
    import movis as mv

    if index % 2 == 0:
        start, end = 1.0, 1.055
    else:
        start, end = 1.055, 1.0

    item.transform.scale.enable_motion().extend(
        keyframes=[0.0, hold],
        values=[[start, start], [end, end]],
        easings=[mv.Easing.LINEAR],
    )

    # A few pixels of vertical travel, opposite to the scale, so the
    # composition does not simply grow from its centre.
    shift = 14 if index % 2 == 0 else -14
    item.transform.position.enable_motion().extend(
        keyframes=[0.0, hold],
        values=[[W / 2, H / 2], [W / 2, H / 2 + shift]],
        easings=[mv.Easing.LINEAR],
    )


def _fade(item, hold: float, fade_in: float, fade_out: float) -> None:
    """Crossfade in and out at the shot's edges."""
    import movis as mv

    keys = [0.0]
    values = [0.0]
    if fade_in > 0:
        keys.append(fade_in)
        values.append(1.0)
    else:
        values[0] = 1.0

    if fade_out > 0:
        keys += [max(hold - fade_out, keys[-1] + 0.01), hold]
        values += [1.0, 0.0]
    else:
        keys.append(hold)
        values.append(1.0)

    item.transform.opacity.enable_motion().extend(
        keyframes=keys,
        values=values,
        easings=[mv.Easing.EASE_IN_OUT] * (len(keys) - 1),
    )


def _punch(item, hold: float) -> None:
    """The hook's arrival — a fast settle rather than a slow drift.

    Overshoots slightly and eases back, which reads as impact. Reserved
    for the first card; using it on every shot would be exhausting.
    """
    import movis as mv

    item.transform.scale.enable_motion().extend(
        keyframes=[0.0, 0.42, hold],
        values=[[1.14, 1.14], [1.0, 1.0], [1.035, 1.035]],
        easings=[mv.Easing.EASE_OUT5, mv.Easing.LINEAR],
    )


def _entrance(item, kind: str, start: float, hold: float) -> None:
    """Animate one element onto the card.

    Entrances are short — 0.3 to 0.45 seconds. Anything slower reads as
    sluggish at this pace, and the element needs to be settled well
    before the narration moves past it.
    """
    import movis as mv

    dur = 0.36
    end = min(start + dur, hold)
    if end <= start:
        start, end = 0.0, min(dur, hold)

    if kind == "pop":
        item.transform.scale.enable_motion().extend(
            keyframes=[start, min(start + 0.22, hold), end],
            values=[[0.72, 0.72], [1.05, 1.05], [1.0, 1.0]],
            easings=[mv.Easing.EASE_OUT5, mv.Easing.EASE_IN_OUT],
        )
        item.transform.opacity.enable_motion().extend(
            keyframes=[start, min(start + 0.14, hold)],
            values=[0.0, 1.0],
            easings=[mv.Easing.EASE_OUT],
        )
        return

    if kind == "rise":
        item.transform.position.enable_motion().extend(
            keyframes=[start, end],
            values=[[W / 2, H / 2 + 46], [W / 2, H / 2]],
            easings=[mv.Easing.EASE_OUT5],
        )
        item.transform.opacity.enable_motion().extend(
            keyframes=[start, min(start + 0.24, hold)],
            values=[0.0, 1.0],
            easings=[mv.Easing.EASE_OUT],
        )
        return

    # "fade" and anything unrecognised.
    item.transform.opacity.enable_motion().extend(
        keyframes=[start, end],
        values=[0.0, 1.0],
        easings=[mv.Easing.EASE_OUT],
    )


@dataclass
class LayeredShot:
    """A shot built from a background plus animated elements."""

    card: object          # LayeredCard, kept loose to avoid a cycle
    hold: float
    kind: str = "statement"
    audio: Path | None = None


def build_layered_short(
    shots: list[LayeredShot],
    out: Path,
    music: Path | None = None,
    music_gain_db: float = -22.0,
    crossfade: float = 0.16,
) -> tuple[Path, float]:
    """Render shots whose parts animate on individually.

    The crossfade is short — 0.16s. A longer dissolve leaves two cards
    legibly overlapping, which reads as a mistake rather than a
    transition when both carry text.

    The background of each shot drifts as before, so the frame stays
    alive between entrances; the elements ride on top of it with their
    own arrivals. That combination is what separates this from a
    slideshow with a zoom on it.
    """
    try:
        import movis as mv
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise MotionError("movis is not installed — run `pip install movis`") from exc

    if not shots:
        raise MotionError("no shots to render")

    starts: list[float] = []
    cursor = 0.0
    for shot in shots:
        starts.append(cursor)
        cursor += max(shot.hold - crossfade, 0.5)
    total = starts[-1] + shots[-1].hold

    scene = mv.layer.Composition(size=(W, H), duration=total)

    for i, (shot, start) in enumerate(zip(shots, starts)):
        # Each shot is its own composition, so its elements fade in and
        # out together at the cut rather than individually.
        sub = mv.layer.Composition(size=(W, H), duration=shot.hold)

        bg = sub.add_layer(
            mv.layer.Image(str(shot.card.background), duration=shot.hold),
            name="bg",
        )
        _drift(bg, shot.hold, i)

        for j, element in enumerate(shot.card.elements):
            item = sub.add_layer(
                mv.layer.Image(str(element.image), duration=shot.hold),
                name=f"el{j}",
            )
            _entrance(item, element.enter, element.at * shot.hold * 0.8, shot.hold)

        item = scene.add_layer(sub, name=f"shot{i}", offset=start)
        _fade(
            item, shot.hold,
            fade_in=0.0 if i == 0 else crossfade,
            fade_out=crossfade if i < len(shots) - 1 else 0.5,
        )

        if shot.audio and shot.audio.exists():
            scene.add_layer(
                mv.layer.Audio(str(shot.audio)),
                name=f"vo{i}",
                offset=start + (0.0 if i == 0 else crossfade * 0.55),
            )

    if music and music.exists():
        scene.add_layer(
            mv.layer.Audio(str(music)), name="music",
            offset=0.0, audio_level=music_gain_db,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    log.info("rendering %d layered shots, %.1fs…", len(shots), total)
    scene.write_video(str(out), fps=FPS)
    return out, total


def build_motion_short(
    shots: list[Shot],
    out: Path,
    music: Path | None = None,
    music_gain_db: float = -22.0,
    crossfade: float = 0.28,
) -> tuple[Path, float]:
    """Render the sequence with movement, transitions and audio.

    Shots overlap by `crossfade` so one card dissolves into the next.
    The timeline is laid out accounting for that overlap, or the
    crossfades would stretch the video beyond the narration.
    """
    try:
        import movis as mv
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise MotionError(
            "movis is not installed — run `pip install movis`"
        ) from exc

    if not shots:
        raise MotionError("no shots to render")

    # Each shot starts before the previous one ends, by the crossfade.
    starts: list[float] = []
    cursor = 0.0
    for shot in shots:
        starts.append(cursor)
        cursor += max(shot.hold - crossfade, 0.4)
    total = starts[-1] + shots[-1].hold

    scene = mv.layer.Composition(size=(W, H), duration=total)

    # No separate background layer: the cards are opaque and every shot
    # after the first overlaps its predecessor, so a dissolve always has
    # something underneath it.

    for i, (shot, start) in enumerate(zip(shots, starts)):
        item = scene.add_layer(
            mv.layer.Image(str(shot.card), duration=shot.hold),
            name=f"card{i}",
            offset=start,
        )
        if shot.kind == "hook" and i == 0:
            _punch(item, shot.hold)
        else:
            _drift(item, shot.hold, i)

        _fade(
            item,
            shot.hold,
            fade_in=0.0 if i == 0 else crossfade,
            fade_out=crossfade if i < len(shots) - 1 else 0.45,
        )

        if shot.audio and shot.audio.exists():
            scene.add_layer(
                mv.layer.Audio(str(shot.audio)),
                name=f"vo{i}",
                # Land the line just after the card appears, so the cut
                # is not simultaneous with the first syllable.
                offset=start + (0.0 if i == 0 else crossfade * 0.6),
            )

    if music and music.exists():
        scene.add_layer(
            mv.layer.Audio(str(music)),
            name="music",
            offset=0.0,
            audio_level=music_gain_db,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    log.info("rendering %d shots, %.1fs…", len(shots), total)
    scene.write_video(str(out), fps=FPS)
    return out, total
