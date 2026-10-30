"""The Count's voice: Microsoft Edge neural voices (free, no key), deeper and slower."""

import asyncio
import io
import logging

import numpy as np
import soundfile as sf

from graf_reachula.texts import TEXTS

log = logging.getLogger(__name__)

RATE = "-8%"
PITCH = "-12Hz"


async def _synthesize(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
    chunks = [c["data"] async for c in communicate.stream() if c["type"] == "audio"]
    return b"".join(chunks)


def synthesize(text: str, voice: str) -> tuple[np.ndarray, int] | None:
    """Text to (mono float32 audio, sample rate), or None if TTS is unavailable."""
    try:
        mp3 = asyncio.run(_synthesize(text, voice))
        audio, rate = sf.read(io.BytesIO(mp3), dtype="float32")
    except Exception as e:
        log.warning("Text-to-speech failed: %s", e)
        return None
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, rate


class Voice:
    """Callable that speaks a line in the current language."""

    def __init__(self, stage, settings):
        self.stage = stage
        self.settings = settings

    @property
    def texts(self) -> dict:
        return TEXTS[self.settings.language]

    def __call__(self, text: str):
        if not text.strip():
            return
        voice = self.settings.voice_de if self.settings.language == "de" else self.settings.voice_en
        result = synthesize(text, voice)
        if result is not None:
            self.stage.play_audio(*result)
