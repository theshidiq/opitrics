"""Drive the Remotion renderer from Python.

The analysis, the quotes and the script stay here; only the drawing
moves. Cards are described as JSON props and handed to a Node process,
which renders every frame in a browser — so a bar's width is computed
from the frame number rather than picked from a handful of pre-drawn
images. That difference is the whole reason for the second toolchain.

Assets have to live under remotion/public/ to be addressable from the
page, so photographs and audio are copied there and referenced by name.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent / "remotion"
PUBLIC = ROOT / "public"
ENTRY = "src/index.ts"
COMPOSITION = "Short"

# Avatar colours, matching the still cards.
AVATARS = [
    "#C0392B", "#1B5E9E", "#1E7D45", "#8A6A0B",
    "#6C3483", "#0E6655", "#96430F", "#4A5A69",
]


class RemotionError(RuntimeError):
    """Raised when the renderer is unavailable or the render fails."""


def available() -> bool:
    return (ROOT / "node_modules" / "remotion").exists()


def avatar_for(seed: str) -> str:
    import hashlib

    return AVATARS[hashlib.sha256(seed.encode()).digest()[0] % len(AVATARS)]


@dataclass
class Shot:
    """One card, how long it holds, and what is said over it."""

    card: dict
    hold: float
    audio: Path | None = None

    def as_props(self, staged: dict[Path, str]) -> dict:
        card = dict(self.card)
        # Photographs are referenced by their staged name.
        src = card.get("src")
        if src:
            card["src"] = staged.get(Path(src), src)
        return {
            "card": card,
            "hold": round(self.hold, 3),
            "audio": staged.get(self.audio) if self.audio else None,
        }


@dataclass
class ShortSpec:
    shots: list[Shot] = field(default_factory=list)
    music: Path | None = None
    music_gain_db: float = -22.0
    crossfade: float = 0.18
    # Held behind every card. Without it, any short whose shape has no
    # "photo" slot never shows the product at all — a quote-led angle
    # was twenty-six seconds of text on a blank page.
    backdrop: Path | None = None


def _stage_assets(spec: ShortSpec) -> dict[Path, str]:
    """Copy media into remotion/public and map originals to their names.

    Remotion serves that directory, so anything referenced by a card has
    to be inside it. Names are prefixed by kind to keep collisions
    between a photograph and an audio file impossible.
    """
    if PUBLIC.exists():
        for stale in PUBLIC.iterdir():
            if stale.is_file():
                stale.unlink()
    PUBLIC.mkdir(parents=True, exist_ok=True)

    mapping: dict[Path, str] = {}

    def stage(path: Path | None, prefix: str, index: int) -> None:
        if not path or not Path(path).exists():
            return
        source = Path(path)
        name = f"{prefix}-{index:02d}{source.suffix.lower()}"
        shutil.copy2(source, PUBLIC / name)
        mapping[source] = name

    for i, shot in enumerate(spec.shots, 1):
        stage(shot.audio, "vo", i)
        src = shot.card.get("src")
        if src:
            stage(Path(src), "img", i)

    if spec.music:
        stage(spec.music, "music", 0)
    if spec.backdrop:
        stage(spec.backdrop, "bg", 0)

    return mapping


def render(spec: ShortSpec, out: Path, concurrency: int | None = None) -> tuple[Path, float]:
    """Render the short. Returns the output path and its duration."""
    if not available():
        raise RemotionError(
            "Remotion is not installed.\n"
            f"  cd {ROOT} && npm install"
        )
    if not spec.shots:
        raise RemotionError("no shots to render")

    staged = _stage_assets(spec)
    props = {
        "shots": [shot.as_props(staged) for shot in spec.shots],
        "music": staged.get(spec.music) if spec.music else None,
        "musicGainDb": spec.music_gain_db,
        "crossfade": spec.crossfade,
        "backdrop": staged.get(spec.backdrop) if spec.backdrop else None,
    }

    props_file = ROOT / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "npx", "remotion", "render", ENTRY, COMPOSITION, str(out.resolve()),
        "--props", str(props_file),
        "--log", "error",
    ]
    if concurrency:
        cmd += ["--concurrency", str(concurrency)]

    log.info("rendering %d shots via Remotion…", len(spec.shots))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-12:]
        raise RemotionError("render failed:\n  " + "\n  ".join(tail))

    # Duration is the sum of holds less the overlaps, matching the
    # layout the composition computes.
    fade = spec.crossfade
    cursor = 0.0
    last = 0.0
    for shot in spec.shots:
        last = cursor + shot.hold
        cursor += max(shot.hold - fade, 0.4)
    return out, last
