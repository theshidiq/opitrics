"""Voiceover and sound effects from ElevenLabs.

Voice and SFX only. Generated music carries stricter terms than voice —
ElevenLabs asks for an additional license for advertising and commercial
distribution, and where a monetised short falls is ambiguous enough to
avoid. Music is supplied as a file from a library with unambiguous
terms, and mixed in by the video stage.

Free-tier output cannot be used in monetised work at all; the client
says so rather than letting it be discovered after publishing.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"

# Multilingual, since scripts quote Japanese titles and model names.
DEFAULT_MODEL = "eleven_multilingual_v2"

# A clear, unhurried narrator. Overridable per project.
DEFAULT_VOICE = "onwK4e9ZLuTAKqWW03F9"  # Daniel — measured, documentary


class AudioError(RuntimeError):
    """Raised when generation fails or credentials are missing."""


@dataclass
class VoiceSettings:
    stability: float = 0.45
    similarity_boost: float = 0.75
    style: float = 0.15
    speed: float = 1.0

    def as_dict(self) -> dict:
        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "speed": self.speed,
        }


class ElevenLabs:
    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model: str | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        if not self.api_key:
            raise AudioError(
                "ELEVENLABS_API_KEY is not set.\n"
                "  elevenlabs.io → Profile → API Keys\n"
                "  Paste it into .env as ELEVENLABS_API_KEY=..."
            )
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "").strip() or DEFAULT_VOICE
        self.model = model or os.getenv("ELEVENLABS_MODEL", "").strip() or DEFAULT_MODEL
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # ── plan check ──────────────────────────────────────────

    def subscription(self) -> dict:
        import requests

        resp = requests.get(
            f"{API_BASE}/user/subscription",
            headers={"xi-api-key": self.api_key},
            timeout=30,
        )
        if resp.status_code != 200:
            raise AudioError(f"could not read subscription: {resp.text[:200]}")
        return resp.json()

    def warn_if_free(self) -> str | None:
        """Return a warning when the plan does not permit commercial use."""
        try:
            sub = self.subscription()
        except AudioError:
            return None
        tier = str(sub.get("tier", "")).lower()
        if tier in {"free", "trial", ""}:
            return (
                "This ElevenLabs plan is free tier — generated audio requires "
                "attribution and cannot be used in monetised content. "
                "Starter ($6/mo) is the lowest plan with commercial rights."
            )
        return None

    # ── generation ──────────────────────────────────────────

    def _cache_path(self, kind: str, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{kind}-{digest}.mp3"

    def speak(
        self,
        text: str,
        out: Path,
        settings: VoiceSettings | None = None,
    ) -> Path:
        """Render one line of narration.

        Cached by (voice, model, settings, text): re-rendering a short
        after changing one card should not re-bill every other line.
        """
        import requests

        settings = settings or VoiceSettings()
        key = f"{self.voice_id}|{self.model}|{settings.as_dict()}|{text}"
        cached = self._cache_path("vo", key)
        if cached and cached.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(cached.read_bytes())
            return out

        resp = requests.post(
            f"{API_BASE}/text-to-speech/{self.voice_id}",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": self.model,
                "voice_settings": settings.as_dict(),
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise AudioError(f"speech failed ({resp.status_code}): {resp.text[:240]}")

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        if cached:
            cached.write_bytes(resp.content)
        return out

    def sound_effect(
        self,
        prompt: str,
        out: Path,
        duration: float | None = None,
        influence: float = 0.4,
    ) -> Path:
        """Generate one sound effect.

        Used sparingly — a short with an effect on every cut is
        exhausting. One accent on the hook and one on the payoff is
        usually the whole budget.
        """
        import requests

        key = f"{prompt}|{duration}|{influence}"
        cached = self._cache_path("sfx", key)
        if cached and cached.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(cached.read_bytes())
            return out

        payload: dict = {"text": prompt, "prompt_influence": influence}
        if duration:
            payload["duration_seconds"] = max(0.5, min(duration, 22.0))

        resp = requests.post(
            f"{API_BASE}/sound-generation",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            raise AudioError(f"sfx failed ({resp.status_code}): {resp.text[:240]}")

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        if cached:
            cached.write_bytes(resp.content)
        return out


def audio_duration(path: Path) -> float:
    """Length of an audio file in seconds, via ffprobe."""
    import subprocess

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
