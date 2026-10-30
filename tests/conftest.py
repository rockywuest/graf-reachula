"""Shared test setup: no robot, no network, no API keys, no real settings file."""

import socket
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from graf_reachula import settings as settings_mod

PROVIDER_ENV = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY", "GROQ_API_KEY",
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Every test gets its own settings file, no provider keys from the shell, and no network."""
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", tmp_path / "settings.json")

    def blocked(self, *args, **kwargs):
        raise RuntimeError("network access is blocked in the test suite")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    yield


class FakeMedia:
    """Stands in for robot.media: one camera frame, no audio."""

    def __init__(self, frame=None):
        self.frame = frame
        self.recording = False
        self.pushed = []

    def get_frame(self):
        return None if self.frame is None else self.frame.copy()

    def get_input_audio_samplerate(self):
        return 16000

    def get_output_audio_samplerate(self):
        return 16000

    def get_output_channels(self):
        return 2

    def get_audio_sample(self):
        return None

    def start_recording(self):
        self.recording = True

    def stop_recording(self):
        self.recording = False

    def start_playing(self):
        pass

    def push_audio_sample(self, frames):
        self.pushed.append(frames)

    def stop_playing(self):
        pass


class FakeRobot:
    def __init__(self, frame=None):
        self.media = FakeMedia(frame)


class FakeStage:
    """Records what the Count would do with the robot body."""

    def __init__(self):
        self.lock = threading.RLock()
        self.speaking = False
        self.last_performance = time.time() - 1000
        self.moves = {}
        self.calls = []

    def free(self):
        return not self.speaking

    def lurk(self):
        self.calls.append("lurk")

    def jump(self):
        self.calls.append("jump")

    def neutral(self, duration=1.0):
        self.calls.append("neutral")

    def play_sound(self, name):
        self.calls.append(("sound", name))

    def play_move(self, name):
        self.calls.append(("move", name))

    def play_audio(self, audio, rate=16000):
        self.calls.append(("audio", len(audio), rate))


@pytest.fixture
def robot():
    return FakeRobot()


@pytest.fixture
def stage():
    return FakeStage()


@pytest.fixture
def jpeg_frame():
    """A small BGR camera frame."""
    return np.full((480, 640, 3), 120, dtype=np.uint8)
