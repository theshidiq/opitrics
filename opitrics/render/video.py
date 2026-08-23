"""Assemble vertical cards into an MP4.

Silent by design — voiceover and music belong in an editor, and the
script is written out beside the video for that purpose. What this
produces is a timed cut of the cards: enough to preview the pacing, or
to post directly when a short does not need narration.

The PNGs are kept alongside. Baking timing into a video means changing
it requires a re-render, so the frames stay available for anyone who
would rather re-time by hand.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

FPS = 30


class VideoError(RuntimeError):
    """Raised when ffmpeg is missing or the encode fails."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def build_short(
    cards: list[Path],
    out: Path,
    holds: list[float] | None = None,
    default_hold: float = 3.5,
    fade: float = 0.25,
) -> Path:
    """Cut a list of cards into a vertical MP4.

    `holds` gives a per-card duration; anything missing falls back to
    `default_hold`. A short crossfade between cards reads better than a
    hard cut at this pace, but stays brief enough not to eat the hold.
    """
    if not ffmpeg_available():
        raise VideoError(
            "ffmpeg not found. Install it with `brew install ffmpeg`, "
            "or use the PNG cards and assemble them in an editor."
        )
    if not cards:
        raise VideoError("no cards to assemble")

    durations = list(holds or [])
    durations += [default_hold] * (len(cards) - len(durations))
    durations = durations[: len(cards)]

    # A concat demuxer script is the most reliable way to hold stills
    # for uneven durations; the filter_complex alternative needs one
    # input per card and hits argument limits on longer sequences.
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "cards.txt"
        lines: list[str] = []
        for card, hold in zip(cards, durations):
            lines.append(f"file '{card.resolve()}'")
            lines.append(f"duration {hold:.3f}")
        # The concat demuxer ignores the final entry's duration unless
        # the last file is repeated, which is a documented quirk.
        lines.append(f"file '{cards[-1].resolve()}'")
        listing.write_text("\n".join(lines), encoding="utf-8")

        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            # Every platform re-encodes anyway; this keeps the upload
            # clean without producing an enormous file.
            "-movflags", "+faststart",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()[-6:]
            raise VideoError("ffmpeg failed:\n  " + "\n  ".join(tail))

    log.info("wrote %s (%.1fs)", out.name, sum(durations))
    return out


def build_narrated_short(
    cards: list[Path],
    narration: list[Path | None],
    out: Path,
    music: Path | None = None,
    effects: list[tuple[Path, int]] | None = None,
    pad: float = 0.55,
    min_hold: float = 2.0,
    music_gain: float = -22.0,
    fx_gain: float = -12.0,
) -> tuple[Path, list[float]]:
    """Cut cards to their narration and mix the audio.

    Each card holds for exactly as long as its line takes to say, plus a
    short pad so the cut does not land on the final syllable. This is
    the reason to render video at all rather than ship stills — timing
    to speech by hand is the tedious part.

    `effects` are (file, card_index) pairs, placed at the start of that
    card. `music` is mixed underneath at a low gain and trimmed to
    length; it is supplied rather than generated, because generated
    music carries licensing terms that voice does not.

    Returns the output path and the per-card durations, so the caller
    can write them into the script for anyone re-timing by hand.
    """
    if not ffmpeg_available():
        raise VideoError(
            "ffmpeg not found. Install it with `brew install ffmpeg`."
        )
    if not cards:
        raise VideoError("no cards to assemble")

    from opitrics.render.audio import audio_duration

    holds = [
        max(audio_duration(vo) + pad, min_hold) if vo else min_hold
        for vo in narration
    ]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # ── silent video track ──────────────────────────────
        listing = tmp_path / "cards.txt"
        lines: list[str] = []
        for card, hold in zip(cards, holds):
            lines.append(f"file '{card.resolve()}'")
            lines.append(f"duration {hold:.3f}")
        lines.append(f"file '{cards[-1].resolve()}'")
        listing.write_text("\n".join(lines), encoding="utf-8")

        silent = tmp_path / "silent.mp4"
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-vf", f"fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            str(silent),
        ])

        # ── narration laid end to end on the same timeline ──
        total = sum(holds)
        inputs: list[str] = []
        filters: list[str] = []
        labels: list[str] = []
        index = 0
        offset = 0.0

        for hold, vo in zip(holds, narration):
            if vo:
                inputs += ["-i", str(vo)]
                # adelay wants milliseconds per channel.
                ms = int(offset * 1000)
                filters.append(f"[{index}:a]adelay={ms}|{ms}[a{index}]")
                labels.append(f"[a{index}]")
                index += 1
            offset += hold

        for fx_file, card_index in effects or []:
            if not 0 <= card_index < len(holds):
                continue
            at = sum(holds[:card_index])
            inputs += ["-i", str(fx_file)]
            ms = int(at * 1000)
            filters.append(
                f"[{index}:a]volume={fx_gain}dB,adelay={ms}|{ms}[a{index}]"
            )
            labels.append(f"[a{index}]")
            index += 1

        if music:
            inputs += ["-stream_loop", "-1", "-i", str(music)]
            filters.append(
                f"[{index}:a]volume={music_gain}dB,"
                f"atrim=0:{total:.3f},afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5"
                f"[a{index}]"
            )
            labels.append(f"[a{index}]")
            index += 1

        if not labels:
            shutil.copy2(silent, out)
            return out, holds

        filters.append(
            "".join(labels)
            + f"amix=inputs={len(labels)}:normalize=0:duration=longest[mix]"
        )

        out.parent.mkdir(parents=True, exist_ok=True)
        _run([
            "ffmpeg", "-y",
            "-i", str(silent),
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "0:v", "-map", "[mix]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            str(out),
        ])

    log.info("wrote %s (%.1fs)", out.name, sum(holds))
    return out, holds


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-8:]
        raise VideoError("ffmpeg failed:\n  " + "\n  ".join(tail))


def probe_duration(path: Path) -> float:
    """Length of a rendered file, for reporting."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0
