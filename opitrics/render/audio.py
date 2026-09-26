"""Voiceover and sound effects from ElevenLabs.

Voice and SFX are covered by the ordinary commercial licence on any
paid plan, and both may be published.

MUSIC IS A SEPARATE LICENCE AND STARTER DOES NOT CLEAR IT. Checked
against the Eleven Music model-specific terms on 2026-09-26, which are
narrower than the general commercial licence in two ways:

  - "All online and offline commercial use permitted, except film, TV,
    radio, & Studio Games" — so a short is permitted use in principle.
  - Streaming on third-party platforms is permitted only on Creator
    tier and above, and prohibited on Free and Starter.

Publishing a short to YouTube, TikTok or Instagram is third-party
platform distribution, so on Starter generated music cannot go into
anything that ships. Creator tier clears it. Until then music is a
supplied file from a library with its own terms, mixed in by the video
stage via `--music`.

An earlier version of this note said music needed "an additional
license for advertising and commercial distribution" and called the
position ambiguous. That was close but imprecise, and imprecise in the
direction that makes a plan question look like a legal one.

Free-tier output cannot be used in monetised work at all; the client
says so rather than letting it be discovered after publishing.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

# Importing config is what loads the .env. Reading os.getenv without it
# works only when something else happened to import config first, which
# made this module fail confusingly when used on its own.
from opitrics import config as _config  # noqa: F401

log = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"

# Multilingual, since scripts quote Japanese titles and model names.
DEFAULT_MODEL = "eleven_multilingual_v2"

# Chris — "charming, down-to-earth", tagged conversational.
#
# The first choice here was Daniel, "Steady Broadcaster", tagged
# informative_educational. That is a voice designed to hold an even
# line, which is right for a documentary and wrong for a short: it
# read every sentence at the same pitch and no settings fixed it.
#
# Measured across the same script, pitch spread by voice:
#   Chris 5.77 · Jessica 4.74 · Liam 4.35 · Brian 4.14 · Daniel 4.04
# (semitones). Chris is 43% wider than Daniel, well outside the ±1
# semitone run-to-run noise, so the difference is real rather than a
# lucky sample. Notably the social_media-tagged voices scored mid —
# that tag tracks energy and pace, not pitch movement.
DEFAULT_VOICE = "iP95p4xoKVk53GoZ742B"  # Chris — conversational, widest range


class AudioError(RuntimeError):
    """Raised when generation fails or credentials are missing."""


@dataclass
class VoiceSettings:
    """How much the delivery is allowed to move.

    `stability` is inverted from what the name suggests: high values
    hold the voice steady and flatten intonation, low values let it
    move. The first version of this file used 0.45 with style 0.15,
    which sat *above* the chosen voice's own recommended stability and
    added almost no style on top — narration that read every sentence
    at the same pitch.

    Measuring pitch spread across settings turned out not to separate
    them: the same text at the same settings varies more between runs
    (4.1 to 6.3 semitones) than the settings vary between themselves.
    So these are set from the voice's published defaults, loosened,
    rather than from a grid search that was really measuring sampling
    noise.
    """

    stability: float = 0.30
    similarity_boost: float = 0.70
    style: float = 0.45
    # Natural pace. Slowing the read to buy depth bought dead air
    # instead — 30% of the "speech" measured as silence inside the
    # lines. Depth comes from the bass shelf alone (see `deepen`),
    # which costs no time. Pushing past 1.0 on top of the pause
    # trimming overshot into a breathless read, so the tightening is
    # left to `deepen` where it can be measured.
    # Under pace deliberately. At 1.0 the finished shorts measured 169
    # to 192 words per minute against 140 to 160 for conversational
    # speech, which reads as rushed on a phone and leaves no room for a
    # line to land. Lengthening the card holds did not fix it — the
    # narration simply grew to fill them — so the rate itself moves.
    speed: float = 0.92

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
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> Path:
        """Render one line of narration.

        `previous_text` and `next_text` are the neighbouring lines. They
        are not spoken and are not billed; they tell the model where
        this line sits in the paragraph, so it can carry intonation
        across a cut instead of restarting flat on every line. Without
        them a seven-line short is seven unrelated readings, which is
        most of why narration sounds recited rather than told.

        Cached by (voice, model, settings, neighbours, text): re-rendering
        a short after changing one card should not re-bill every other
        line. The neighbours are part of the key because changing the
        line before this one genuinely changes how this one is read.
        """
        import requests

        settings = settings or VoiceSettings()
        key = (
            f"{self.voice_id}|{self.model}|{settings.as_dict()}"
            f"|{previous_text or ''}|{next_text or ''}|{text}"
        )
        cached = self._cache_path("vo", key)
        if cached and cached.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(cached.read_bytes())
            return out

        payload: dict = {
            "text": text,
            "model_id": self.model,
            "voice_settings": settings.as_dict(),
        }
        if previous_text:
            payload["previous_text"] = previous_text
        if next_text:
            payload["next_text"] = next_text

        resp = requests.post(
            f"{API_BASE}/text-to-speech/{self.voice_id}",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
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


def deepen(path: Path, gain_db: float = 4.0, max_pause: float = 0.30) -> Path:
    """Weight a voice track towards the low end and tighten it, in place.

    Two jobs, one pass, because both are ffmpeg filters and running
    the file through twice costs quality for nothing.

    The EQ half: ElevenLabs exposes no pitch or EQ control, so warmth
    has to be added after the fact. This is a shelf, not a pitch
    shift — shifting pitch down makes a voice sound slowed and
    artificial, whereas lifting the low shelf and easing the presence
    region reads as a closer microphone. The high-pass at 60Hz goes
    first, since boosting a shelf that includes rumble the voice does
    not use just muddies it.

    The timing half: the model inserts a real pause at every sentence
    break, and shorts narration is deliberately written in short
    sentences — so the two compound. Measured on a finished short,
    30% of the "speech" was silence inside the lines, including single
    stops over a second long. On a vertical short that is where the
    thumb moves. Silences longer than `max_pause` are cut back to it;
    shorter ones are left alone.

    The default is a measured middle, not a minimum. At 0.22s the
    result came back with no detectable pause at all — breathless,
    which is its own kind of wrong and reads as a machine reading a
    list. 0.30s leaves an audible beat at each sentence break while
    removing the stalls.
    """
    import shutil
    import subprocess
    import tempfile

    if not path.exists():
        return path

    # `--bass 0` turns off the EQ but keeps the timing work, which is
    # the half that matters most for retention.
    tone = (
        "highpass=f=60,"
        f"bass=g={gain_db}:f=110:width_type=q:w=0.7,"
        "treble=g=-1.5:f=5000:width_type=q:w=0.8,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=8:release=180,"
    ) if gain_db else ""

    chain = (
        f"{tone}"
        # Trim the head and tail, then cap pauses in the middle. The
        # head/tail matter because every line is its own file and the
        # leading silence stacks on top of the gap between cards.
        f"silenceremove="
        f"start_periods=1:start_duration=0:start_threshold=-45dB:"
        f"stop_periods=-1:stop_duration={max_pause}:stop_threshold=-45dB:"
        f"detection=rms,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0:"
        "start_threshold=-45dB:detection=rms,"
        "areverse,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )
    tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path),
         "-af", chain, "-codec:a", "libmp3lame", "-q:a", "2", str(tmp)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        log.warning("bass shelf failed, keeping original: %s", proc.stderr[:200])
        tmp.unlink(missing_ok=True)
        return path
    shutil.move(str(tmp), str(path))
    return path


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
