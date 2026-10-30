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
    client = TestClient(app.settings_app, headers={"host": "reachy-mini.local:8042", "x-graf-reachula": "1"})
    client.app_settings = app
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


def test_writes_without_the_page_header_are_refused(running_app):
    """A drive-by request from another web page can't send the custom header."""
    response = running_app.post("/api/play/sound/ghost", headers={"x-graf-reachula": ""})
    assert response.status_code == 403
    response = running_app.post("/api/settings", json={"changes": {"language": "de"}},
                                headers={"sec-fetch-site": "cross-site"})
    assert response.status_code == 403


def test_pin_locks_sensitive_settings(running_app):
    assert running_app.post("/api/settings", json={"changes": {"new_pin": "4711"}}).status_code == 200
    data = running_app.get("/api/settings").json()
    assert data["pin_set"] is True
    locked = running_app.post("/api/settings", json={"changes": {"stt_provider": "elevenlabs"}})
    assert locked.status_code == 403
    assert running_app.post("/api/settings", json={"changes": {"language": "de"}}).status_code == 200
    ok = running_app.post("/api/settings", json={"changes": {"stt_provider": "elevenlabs"}},
                          headers={"x-graf-pin": "4711"})
    assert ok.status_code == 200 and ok.json()["stt_provider"] == "elevenlabs"
    wrong = running_app.post("/api/settings", json={"changes": {"new_pin": "0000"}}, headers={"x-graf-pin": "1"})
    assert wrong.status_code == 403


def test_play_queue_is_capped(running_app):
    codes = [running_app.post("/api/play/move/scared").status_code for _ in range(20)]
    assert 429 in codes


def test_foreign_host_is_rejected(running_app):
    response = running_app.get("/api/settings", headers={"host": "evil.example.com"})
    assert response.status_code == 403


def test_play_and_voice_test_buttons(running_app):
    assert running_app.post("/api/play/say/test").status_code == 200
    assert running_app.post("/api/play/sound/ghost").status_code == 200
    time.sleep(0.4)
