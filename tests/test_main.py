"""The app's web routes, with the robot, voice and haunting replaced by fakes."""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from graf_reachula import main as main_mod


class FakeStage:
    def __init__(self, robot):
        self.played = []

    def neutral(self):
        pass

    def play_sound(self, name):
        self.played.append(("sound", name))

    def play_move(self, name):
        self.played.append(("move", name))


class FakeVoice:
    def __init__(self, stage, settings):
        self.stage, self.settings, self.status, self.spoken = stage, settings, "Free Edge voice", []
        self.texts = {"intro": [], "voice_test": "Testing", "after_scare": ["Gotcha"]}

    def __call__(self, text):
        self.spoken.append(text)

    def warm_up(self, lines):
        pass

    def reset(self):
        self.status = "reset"


class FakeHaunt:
    def __init__(self, robot, stage, settings, say=None):
        self.scares = 0

    def run(self, stop_event):
        stop_event.wait()

    def jump_scare(self):
        self.scares += 1


@pytest.fixture
def running_app(monkeypatch):
    monkeypatch.setattr(main_mod, "Stage", FakeStage)
    monkeypatch.setattr(main_mod, "Voice", FakeVoice)
    monkeypatch.setattr(main_mod, "Haunt", FakeHaunt)
    app = main_mod.GrafReachula.__new__(main_mod.GrafReachula)
    app.settings_app = FastAPI()
    stop = threading.Event()
    thread = threading.Thread(target=app.run, args=(SimpleNamespace(), stop), daemon=True)
    thread.start()
    time.sleep(0.3)
    client = TestClient(app.settings_app, headers={"host": "reachy-mini.local:8042"})
    yield client
    stop.set()
    thread.join(timeout=5)


def test_get_settings_returns_settings_and_live_status(running_app):
    data = running_app.get("/api/settings").json()
    for field in ("language", "llm_provider", "tts_provider", "talking", "voice_status", "listen_error"):
        assert field in data


def test_settings_update_round_trip(running_app):
    data = running_app.post("/api/settings", json={"changes": {"language": "de", "scares": "false"}}).json()
    assert data["language"] == "de" and data["scares"] is False


def test_foreign_host_is_rejected(running_app):
    response = running_app.get("/api/settings", headers={"host": "evil.example.com"})
    assert response.status_code == 403


def test_play_and_voice_test_buttons(running_app):
    assert running_app.post("/api/play/say/test").status_code == 200
    assert running_app.post("/api/play/sound/ghost").status_code == 200
    time.sleep(0.4)
