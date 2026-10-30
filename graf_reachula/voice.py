"""The Count's voice.

Default: Microsoft Edge neural voices (free, no key), made deeper and slower.
Optional: ElevenLabs with the user's own key, for a real theatrical vampire voice.
If ElevenLabs fails (no credits, no network), the Count falls back to Edge.
"""

import asyncio
import io
import logging
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


async def _synthesize(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    chunks = [c["data"] async for c in communicate.stream() if c["type"] == "audio"]
    return b"".join(chunks)


def synthesize(text: str, voice: str) -> tuple[np.ndarray, int] | None:
    """Edge TTS: text to (mono float32 audio, sample rate), or None if unavailable."""
    try:
        mp3 = asyncio.run(_synthesize(text, voice))
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

    client = client or httpx.Client(timeout=30.0)
    response = client.post(
        f"{ELEVENLABS_URL}/text-to-speech/{voice}",
        params={"output_format": f"pcm_{ELEVENLABS_RATE}"},
        headers={"xi-api-key": api_key},
        json={"text": text, "model_id": model, "language_code": language},
    )
    response.raise_for_status()
    pcm = np.frombuffer(response.content, dtype="<i2")
    return (pcm.astype(np.float32) / 32768.0), ELEVENLABS_RATE


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

    @property
    def texts(self) -> dict:
        return TEXTS[self.settings.language]

    def _render(self, text: str) -> tuple[np.ndarray, int] | None:
        tts = self.settings.tts()
        if tts["provider"] == "elevenlabs":
            try:
                if self.http is None:
                    import httpx

                    self.http = httpx.Client(timeout=30.0)
                voice = tts["voice"]
                if not voice:
                    if tts["api_key"] not in self.picked_voice:
                        self.picked_voice[tts["api_key"]] = pick_elevenlabs_voice(self.http, tts["api_key"])
                    voice = self.picked_voice[tts["api_key"]]
                key = (text, voice, tts["model"], self.settings.language)
                if key in self.cache:
                    self.cache.move_to_end(key)
                    return self.cache[key]
                result = synthesize_elevenlabs(text, tts["api_key"], voice, tts["model"],
                                               self.settings.language, client=self.http)
                self.cache[key] = result
                if len(self.cache) > CACHE_SIZE:
                    self.cache.popitem(last=False)
                return result
            except Exception as e:
                # Out of credits or offline: the party goes on with the free voice
                log.warning("ElevenLabs failed (%s); using the Edge voice", e)
        return synthesize(text, tts["edge_voice"])

    def __call__(self, text: str):
        if not text.strip():
            return
        result = self._render(text)
        if result is not None:
            self.stage.play_audio(*result)
