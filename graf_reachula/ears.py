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


class Ears:
    def __init__(self, robot, stage, stt: dict, language: str):
        import openai

        self.robot = robot
        self.stage = stage
        self.language = language
        self.model = stt["model"]
        self.client = openai.OpenAI(api_key=stt["api_key"], base_url=stt["base_url"] or None,
                                    timeout=30.0, max_retries=1)
        self.rate = robot.media.get_input_audio_samplerate() or 16000
        self.vad = EnergyVAD(self.rate)
        self.buffer = np.zeros(0, dtype=np.float32)
        self.robot.media.start_recording()
        stage.recording = True

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
        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=("speech.wav", wav.getvalue(), "audio/wav"),
            language=self.language,
        )
        text = (result.text or "").strip()
        if PHANTOMS.match(text):
            log.info("Ignored phantom transcript: %r", text)
            return ""
        return text

    def close(self):
        # The microphone stays on: playback shares its pipeline, and a newer
        # Ears may already be listening after a settings change
        self.stage.recording = False
