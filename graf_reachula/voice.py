"""The Count's voice.

Default: Microsoft Edge neural voices (free, no key), made deeper and slower.
Optional: ElevenLabs with the user's own key, for a real theatrical vampire voice.
If ElevenLabs fails (no credits, no network), the Count falls back to Edge.
"""

import asyncio
import io
import logging
import threading
import time
from collections import OrderedDict

import numpy as np
import soundfile as sf

from graf_reachula.settings import ELEVENLABS_URL, ELEVENLABS_VOICE_NAMES
from graf_reachula.texts import TEXTS

log = logging.getLogger(__name__)

RATE = "-8%"
PITCH = "-12Hz"
ELEVENLABS_RATE = 16000
CACHE_SIZE = 32     # the intro and scare lines repeat all evening; don't pay for them twice
TIMEOUT = 8.0       # seconds; a party can't wait longer for one sentence
COOLDOWN = 300      # after an ElevenLabs failure, use the free voice for this long


async def _synthesize(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    chunks = [c["data"] async for c in communicate.stream() if c["type"] == "audio"]
    return b"".join(chunks)


def synthesize(text: str, voice: str) -> tuple[np.ndarray, int] | None:
    """Edge TTS: text to (mono float32 audio, sample rate), or None if unavailable."""
    try:
        mp3 = asyncio.run(asyncio.wait_for(_synthesize(text, voice), TIMEOUT))
        audio, rate = sf.read(io.BytesIO(mp3), dtype="float32")
    except Exception as e:
        log.warning("Text-to-speech failed: %s", e)
        return None
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, rate


def synthesize_elevenlabs(text: str, api_key: str, voice: str, model: str, language: str,
                          client=None) -> tuple[np.ndarray, int]:
    """ElevenLabs TTS as raw 16 kHz PCM (signed 16-bit little-endian mono)."""
    import httpx

    response = (client or httpx.Client(timeout=TIMEOUT)).post(
        f"{ELEVENLABS_URL}/text-to-speech/{voice}",
        params={"output_format": f"pcm_{ELEVENLABS_RATE}"},
        headers={"xi-api-key": api_key},
        json={"text": text, "model_id": model, "language_code": language},
    )
    response.raise_for_status()
    pcm = np.frombuffer(response.content, dtype="<i2")
    return (pcm.astype(np.float32) / 32768.0), ELEVENLABS_RATE


def describe_error(e: Exception) -> str:
    """A short, helpful reason for the settings page (e.g. a missing key permission)."""
    response = getattr(e, "response", None)
    if response is not None:
        try:
            body = response.json()
            detail = body.get("detail") or body.get("error") or {}
            if isinstance(detail, dict) and detail.get("message"):
                return detail["message"][:200]
            if isinstance(detail, str):
                return detail[:200]
        except Exception:
            pass
        return f"HTTP {getattr(response, 'status_code', '?')}"
    return str(e)[:160]


def pick_elevenlabs_voice(client, api_key: str) -> str:
    """A deep narrator voice from the account's voices (default voice IDs change over time)."""
    response = client.get(f"{ELEVENLABS_URL}/voices", headers={"xi-api-key": api_key})
    response.raise_for_status()
    voices = {}
    for v in response.json().get("voices", []):
        first = (v.get("name") or "").split()
        if first and v.get("voice_id"):
            voices.setdefault(first[0].strip(" -"), v["voice_id"])
    for name in ELEVENLABS_VOICE_NAMES:
        if name in voices:
            log.info("ElevenLabs voice: %s", name)
            return voices[name]
    if not voices:
        raise RuntimeError("no ElevenLabs voices on this account")
    name, voice_id = next(iter(voices.items()))
    log.info("ElevenLabs voice: %s (none of the preferred voices found)", name)
    return voice_id


class Voice:
    """Callable that speaks a line in the current language."""

    def __init__(self, stage, settings):
        self.stage = stage
        self.settings = settings
        self.cache: OrderedDict = OrderedDict()
        self.http = None
        self.picked_voice: dict[str, str] = {}   # api key -> voice ID chosen for it
        self.lock = threading.Lock()              # the haunt, talk and main threads all speak
        self.eleven_paused_until = 0.0
        self.eleven_error = ""
        self.status = ""                          # shown on the settings page

    @property
    def texts(self) -> dict:
        return TEXTS[self.settings.language]

    def _elevenlabs(self, text: str, tts: dict) -> tuple[np.ndarray, int]:
        with self.lock:
            if self.http is None:
                import httpx

                self.http = httpx.Client(timeout=TIMEOUT)
            client = self.http
            voice = tts["voice"] or self.picked_voice.get(tts["api_key"])
        if not voice:
            # A network call: don't make the other speakers wait for it
            voice = pick_elevenlabs_voice(client, tts["api_key"])
            with self.lock:
                self.picked_voice[tts["api_key"]] = voice
        with self.lock:
            key = (text, voice, tts["model"], self.settings.language)
            cached = self.cache.get(key)
            if cached is not None:
                self.cache.move_to_end(key)
                return cached
            client = self.http
        result = synthesize_elevenlabs(text, tts["api_key"], voice, tts["model"],
                                       self.settings.language, client=client)
        with self.lock:
            self.cache[key] = result
            while len(self.cache) > CACHE_SIZE:
                self.cache.popitem(last=False)
        return result

    def render(self, text: str) -> tuple[np.ndarray, int] | None:
        """Turn a line into audio (without playing it)."""
        tts = self.settings.tts()
        if tts["provider"] == "elevenlabs" and time.time() < self.eleven_paused_until:
            minutes = max(1, round((self.eleven_paused_until - time.time()) / 60))
            self.status = f"Free Edge voice for {minutes} more min, ElevenLabs failed: {self.eleven_error}"
        elif tts["provider"] == "elevenlabs":
            try:
                result = self._elevenlabs(text, tts)
                self.status = "ElevenLabs"
                return result
            except Exception as e:
                # Out of credits, bad key or offline: the party goes on with the free voice
                log.warning("ElevenLabs failed (%s); using the Edge voice for %d minutes", e, COOLDOWN // 60)
                self.eleven_paused_until = time.time() + COOLDOWN
                self.eleven_error = describe_error(e)
                self.status = f"Free Edge voice for {COOLDOWN // 60} min, ElevenLabs failed: {self.eleven_error}"
        elif tts["provider"] == "edge":
            missing_key = self.settings.tts_provider == "elevenlabs"
            self.status = "Free Edge voice" + (" (ElevenLabs chosen, but no key yet)" if missing_key else "")
        key = ("edge", text, tts["edge_voice"])
        with self.lock:
            cached = self.cache.get(key)
        if cached is not None:
            return cached
        result = synthesize(text, tts["edge_voice"])
        if result is not None:
            with self.lock:
                self.cache[key] = result
                while len(self.cache) > CACHE_SIZE:
                    self.cache.popitem(last=False)
        return result

    def warm_up(self, lines):
        """Render lines ahead of time (e.g. the lines after a scare), so they play instantly."""
        for line in lines:
            try:
                self.render(line)
            except Exception as e:
                log.info("Could not pre-render a line: %s", e)

    def reset(self):
        """Settings changed: try ElevenLabs again right away."""
        with self.lock:
            self.eleven_paused_until = 0.0
            self.picked_voice.clear()

    def play(self, rendered):
        if rendered is not None:
            self.stage.play_audio(*rendered)

    def __call__(self, text: str):
        if text.strip():
            self.play(self.render(text))
