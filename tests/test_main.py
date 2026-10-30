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
    latest = None

    def __init__(self, stage, settings):
        self.stage, self.settings, self.status, self.spoken = stage, settings, "Free Edge voice", []
        self.texts = {"intro": [], "voice_test": "Testing", "after_scare": ["Gotcha"], "setup_code": "Code {code}"}
        FakeVoice.latest = self

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


def set_first_pin(client, pin="471100"):
    return client.post("/api/settings", json={"changes": {"new_pin": pin}},
                       headers={"x-graf-setup": client.app_settings.setup["code"]})


def test_first_pin_needs_the_setup_code(running_app):
    """A guest on the Wi-Fi must not set the first PIN and lock the owner out."""
    assert running_app.post("/api/settings", json={"changes": {"new_pin": "471100"}}).status_code == 403
    assert running_app.post("/api/settings", json={"changes": {"new_pin": "471100"}},
                            headers={"x-graf-setup": "000000x"}).status_code == 403
    assert set_first_pin(running_app).status_code == 200
    assert running_app.get("/api/settings").json()["pin_set"] is True


def test_without_a_pin_nothing_sensitive_can_change(running_app):
    """No PIN yet: a guest can't point the microphone or camera at their own server."""
    for changes in ({"llm_provider": "custom", "llm_base_url": "https://evil.example/v1"},
                    {"stt_provider": "custom"}, {"talk": True}, {"wake_word": False}, {"voice_en": "x"},
                    {"tts_provider": "elevenlabs"}):
        assert running_app.post("/api/settings", json={"changes": changes}).status_code == 403, changes
    data = running_app.get("/api/settings").json()
    assert data["llm_provider"] == "anthropic" and data["wake_word"] is True


def test_pin_locks_sensitive_settings(running_app):
    assert running_app.post("/api/settings", json={"changes": {"new_pin": "4711"}},
                            headers={"x-graf-setup": running_app.app_settings.setup["code"]}).status_code == 400
    assert set_first_pin(running_app, "pin€123").status_code == 400      # would break the HTTP header
    assert set_first_pin(running_app).status_code == 200
    locked = running_app.post("/api/settings", json={"changes": {"stt_provider": "elevenlabs"}})
    assert locked.status_code == 403
    assert running_app.post("/api/settings", json={"changes": {"language": "de"}}).status_code == 200
    ok = running_app.post("/api/settings", json={"changes": {"stt_provider": "elevenlabs"}},
                          headers={"x-graf-pin": "471100"})
    assert ok.status_code == 200 and ok.json()["stt_provider"] == "elevenlabs"
    wrong = running_app.post("/api/settings", json={"changes": {"new_pin": "000000"}}, headers={"x-graf-pin": "1"})
    assert wrong.status_code == 403


def test_anyone_may_switch_talking_off_but_not_on(running_app):
    set_first_pin(running_app)
    assert running_app.post("/api/settings", json={"changes": {"talk": False}}).status_code == 200
    assert running_app.post("/api/settings", json={"changes": {"talk": "true"}}).status_code == 403


def test_wrong_pins_lock_out_guessing_for_at_most_five_minutes(running_app):
    set_first_pin(running_app, "secret1")
    codes = [running_app.post("/api/settings", json={"changes": {"llm_model": "x"}},
                              headers={"x-graf-pin": f"guess{i}"}).status_code for i in range(7)]
    assert codes[:5] == [403] * 5 and codes[-1] == 429
    # Even the right PIN waits out the lockout
    right = running_app.post("/api/settings", json={"changes": {"llm_model": "x"}}, headers={"x-graf-pin": "secret1"})
    assert right.status_code == 429
    # ...but switching talking off still works during a lockout
    assert running_app.post("/api/settings", json={"changes": {"talk": False}}).status_code == 200


def test_lockout_is_capped_even_after_many_parallel_guesses(running_app, monkeypatch):
    set_first_pin(running_app, "secret1")
    now = [time.time()]
    monkeypatch.setattr(main_mod.time, "time", lambda: now[0])

    def guess(i):
        return running_app.post("/api/settings", json={"changes": {"llm_model": "x"}},
                                headers={"x-graf-pin": f"guess{i}"}).status_code

    for i in range(40):
        guess(i)
        now[0] += 400          # wait out every lockout, so each guess really counts
    now[0] += main_mod.MAX_LOCKOUT + 1
    assert running_app.post("/api/settings", json={"changes": {"llm_model": "x"}},
                            headers={"x-graf-pin": "secret1"}).status_code == 200


def test_pin_reset_over_ssh_counts_while_the_app_runs(running_app):
    from graf_reachula.settings import Settings

    set_first_pin(running_app)
    on_disk = Settings.load()
    on_disk.reset_pin()
    on_disk.save()                     # what `--reset-pin` does
    assert running_app.get("/api/settings").json()["pin_set"] is False
    # A later save from the page must not write the old PIN back
    running_app.post("/api/settings", json={"changes": {"language": "de"}})
    assert Settings.load().admin_pin_hash == ""


def test_setup_code_lives_in_an_owner_only_file_and_works_once(running_app):
    import os
    import stat
    from graf_reachula import settings as settings_mod

    path = settings_mod.SETTINGS_PATH.with_name("setup-code.txt")
    code = path.read_text().strip()
    assert code == running_app.app_settings.setup["code"]
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert set_first_pin(running_app).status_code == 200
    assert path.read_text().strip() != code            # a used code is replaced
    # Said once at start (no PIN yet), never on request
    running_app.post("/api/play/code/setup")
    time.sleep(0.4)
    assert FakeVoice.latest.spoken == ["Code " + ", ".join(code)]


def test_no_code_announcement_when_a_pin_exists(monkeypatch):
    from graf_reachula.settings import Settings

    stored = Settings()
    stored.set_pin("471100")
    stored.save()
    monkeypatch.setattr(main_mod, "Stage", FakeStage)
    monkeypatch.setattr(main_mod, "Voice", FakeVoice)
    monkeypatch.setattr(main_mod, "Haunt", FakeHaunt)
    app = main_mod.GrafReachula.__new__(main_mod.GrafReachula)
    app.settings_app = FastAPI()
    stop = threading.Event()
    thread = threading.Thread(target=app.run, args=(SimpleNamespace(), stop), daemon=True)
    thread.start()
    time.sleep(0.3)
    stop.set()
    thread.join(5)
    assert FakeVoice.latest.spoken == []


def client_from(running_app, address, host="reachy-mini.local:8042"):
    return TestClient(running_app.app, client=(address, 50000),
                      headers={"host": host, "x-graf-reachula": "1"})


def test_a_guest_guessing_wrong_pins_does_not_lock_out_the_owner(running_app):
    set_first_pin(running_app, "secret1")
    guest = client_from(running_app, "192.168.1.66")
    codes = [guest.post("/api/settings", json={"changes": {"llm_model": "x"}},
                        headers={"x-graf-pin": f"guess{i}"}).status_code for i in range(7)]
    assert codes[-1] == 429
    owner = client_from(running_app, "192.168.1.20")
    assert owner.post("/api/settings", json={"changes": {"llm_model": "x"}},
                      headers={"x-graf-pin": "secret1"}).status_code == 200


def test_many_addresses_guessing_hit_the_global_backstop(running_app):
    set_first_pin(running_app, "secret1")
    for i in range(main_mod.GLOBAL_FAILURES):
        client_from(running_app, f"10.0.0.{i + 1}").post(
            "/api/settings", json={"changes": {"llm_model": "x"}}, headers={"x-graf-pin": "nope"})
    owner = client_from(running_app, "192.168.1.20")
    assert owner.post("/api/settings", json={"changes": {"llm_model": "x"}},
                      headers={"x-graf-pin": "secret1"}).status_code == 429
    assert owner.post("/api/settings", json={"changes": {"talk": False}}).status_code == 200


def test_a_local_proxy_does_not_count_as_this_computer(running_app):
    local = client_from(running_app, "127.0.0.1", host="localhost:8042")
    assert local.post("/api/settings", json={"changes": {"new_pin": "471100"}},
                      headers={"x-forwarded-for": "192.168.1.66"}).status_code == 403
    ipv6 = client_from(running_app, "::1", host="[::1]:8042")
    assert ipv6.post("/api/settings", json={"changes": {"new_pin": "471100"}}).status_code == 200


def test_first_pin_without_code_only_on_the_apps_own_computer(running_app):
    """Reachy Mini Lite: the app runs on your computer, so the owner sits right there."""
    spoofed = client_from(running_app, "192.168.1.66", host="localhost:8042")   # Host header alone is not enough
    assert spoofed.post("/api/settings", json={"changes": {"new_pin": "471100"}}).status_code == 403
    local = client_from(running_app, "127.0.0.1", host="localhost:8042")
    assert local.post("/api/settings", json={"changes": {"new_pin": "471100"}}).status_code == 200


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
