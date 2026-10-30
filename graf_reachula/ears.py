"""The Count's ears: cut the robot's microphone stream into utterances and transcribe them."""

import io
import logging
import re
import time

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

FRAME_SECONDS = 0.03
END_SILENCE = 0.8        # seconds of quiet that end an utterance
MIN_SPEECH = 0.4         # shorter blips are ignored
MAX_SPEECH = 15.0

# Whisper invents these on noise (it was trained on subtitled videos)
PHANTOMS = re.compile(
    r"^(thank you\.?|thanks for watching.*|you|bye\.?|untertitel.*|vielen dank\.?|"
    r"danke( schön)?\.?|copyright.*|swr.*|\W*)$",
    re.IGNORECASE,
)


class EnergyVAD:
    """Speech detector on loudness, with a noise floor that follows the room."""

    def __init__(self, rate: int):
        self.rate = rate
        self.floor = 0.005
        self.reset()

    def reset(self):
        self.frames: list[np.ndarray] = []
        self.voiced = 0.0
        self.silence = 0.0
        self.active = False
        self.loud_streak = 0

    def push(self, frame: np.ndarray) -> np.ndarray | None:
        """Feed one frame; returns a finished utterance or None."""
        rms = float(np.sqrt(np.mean(frame ** 2)))
        loud = rms > max(self.floor * 3.0, 0.01)
        # Follow the background level: quickly down, slowly up even while it's loud,
        # so steady party music raises the floor instead of counting as speech forever
        rate = 0.02 if rms < self.floor or not loud else 0.002
        self.floor += rate * (rms - self.floor)

        if not self.active:
            self.loud_streak = self.loud_streak + 1 if loud else 0
            self.frames = (self.frames + [frame])[-10:]   # keep a little pre-roll
            if self.loud_streak >= 3:
                self.active = True
                self.voiced = 3 * FRAME_SECONDS
                self.silence = 0.0
            return None

        self.frames.append(frame)
        if loud:
            self.voiced += FRAME_SECONDS
            self.silence = 0.0
        else:
            self.silence += FRAME_SECONDS
        length = len(self.frames) * FRAME_SECONDS
        if self.silence >= END_SILENCE or length >= MAX_SPEECH:
            audio = np.concatenate(self.frames)
            enough = self.voiced >= MIN_SPEECH
            self.reset()
            return audio if enough else None
        return None


FALLBACK_STT_MODEL = "gpt-4o-mini-transcribe"

# Names the speech recognition should expect (xAI and ElevenLabs support such hints)
KEYTERMS = ("Reachy", "Reachula", "Count", "Graf")


class Ears:
    def __init__(self, robot, stage, stt: dict, language: str):
        self.robot = robot
        self.stage = stage
        self.language = language
        self.provider = stt["provider"]
        self.model = stt["model"]
        self.api_key = stt["api_key"]
        self.base_url = (stt["base_url"] or "").rstrip("/")
        if self.provider in ("xai", "elevenlabs"):
            import httpx

            self.client = httpx.Client(timeout=30.0)
        else:
            import openai

            self.client = openai.OpenAI(api_key=stt["api_key"], base_url=stt["base_url"] or None,
                                        timeout=30.0, max_retries=1)
        self.rate = robot.media.get_input_audio_samplerate() or 16000
        self.vad = EnergyVAD(self.rate)
        self.buffer = np.zeros(0, dtype=np.float32)
        self.robot.media.start_recording()
        stage.recording = True
        stage.ears = self            # the current listener; older ones must not touch the mic

    def _flush(self):
        while self.robot.media.get_audio_sample() is not None:
            pass
        self.buffer = np.zeros(0, dtype=np.float32)
        self.vad.reset()

    def listen(self, stop_event) -> np.ndarray | None:
        """Block until one utterance has been heard (or the app stops)."""
        frame_len = int(self.rate * FRAME_SECONDS)
        while not stop_event.is_set():
            if self.stage.echoing():
                # Don't transcribe the robot's own voice and sounds
                self._flush()
                time.sleep(0.05)
                continue
            samples = self.robot.media.get_audio_sample()
            if samples is None or len(samples) == 0:
                time.sleep(0.01)
                continue
            mono = samples.mean(axis=1) if samples.ndim > 1 else samples
            self.buffer = np.concatenate([self.buffer, mono.astype(np.float32)])
            while len(self.buffer) >= frame_len:
                frame, self.buffer = self.buffer[:frame_len], self.buffer[frame_len:]
                utterance = self.vad.push(frame)
                if utterance is not None:
                    return utterance
        return None

    def transcribe(self, audio: np.ndarray) -> str:
        wav = io.BytesIO()
        sf.write(wav, audio, self.rate, format="WAV", subtype="PCM_16")
        if self.provider == "xai":
            text = self._transcribe_xai(wav.getvalue())
        elif self.provider == "elevenlabs":
            text = self._transcribe_elevenlabs(wav.getvalue())
        else:
            try:
                text = self._transcribe_openai(wav.getvalue())
            except Exception as e:
                # gpt-transcribe is new; if this account or endpoint rejects it, fall back to
                # the previous model (served until February 2027) instead of going deaf
                if not self.model.startswith("gpt-transcribe") or getattr(e, "status_code", None) not in (400, 403, 404, 422):
                    raise
                log.warning("%s rejected (%s); using %s", self.model, e, FALLBACK_STT_MODEL)
                self.model = FALLBACK_STT_MODEL
                text = self._transcribe_openai(wav.getvalue())
        if PHANTOMS.match(text):
            log.info("Ignored phantom transcript: %r", text)
            return ""
        return text

    def _transcribe_openai(self, wav: bytes) -> str:
        # gpt-transcribe takes a list of languages instead of the older single `language`
        if self.model.startswith("gpt-transcribe"):
            language = {"extra_body": {"languages": [self.language]}}
        else:
            language = {"language": self.language}
        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=("speech.wav", wav, "audio/wav"),
            **language,
        )
        return (result.text or "").strip()

    def _transcribe_xai(self, wav: bytes) -> str:
        """xAI's batch speech-to-text (POST /v1/stt, multipart, file last)."""
        # httpx sends form fields before files, as xAI requires (file must be last)
        data = {"language": self.language, "keyterm": list(KEYTERMS)}
        response = self.client.post(
            f"{self.base_url}/stt",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data=data,
            files={"file": ("speech.wav", wav, "audio/wav")},
        )
        response.raise_for_status()
        return (response.json().get("text") or "").strip()

    def _transcribe_elevenlabs(self, wav: bytes) -> str:
        """ElevenLabs Scribe (POST /v1/speech-to-text, multipart)."""
        response = self.client.post(
            f"{self.base_url}/speech-to-text",
            headers={"xi-api-key": self.api_key},
            data={"model_id": self.model, "language_code": self.language, "keyterms": list(KEYTERMS)},
            files={"file": ("speech.wav", wav, "audio/wav")},
        )
        response.raise_for_status()
        return (response.json().get("text") or "").strip()

    def close(self):
        """Turn the microphone off, unless a newer listener has taken over already."""
        if getattr(self.client, "close", None):
            self.client.close()
        if getattr(self.stage, "ears", None) is not self:
            return
        self.stage.recording = False
        self.stage.ears = None
        try:
            self.robot.media.stop_recording()
        except Exception as e:
            log.warning("Could not stop the microphone: %s", e)
