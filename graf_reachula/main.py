"""Count Reachula (Graf Reachula): a spooky, child-friendly Halloween ghost for Reachy Mini."""

import logging
import re
import threading
import time

from fastapi import HTTPException, Request
from pydantic import BaseModel
from reachy_mini import ReachyMini, ReachyMiniApp

from graf_reachula.haunt import Haunt
from graf_reachula.settings import Settings
from graf_reachula.stage import Stage
from graf_reachula.voice import Voice

log = logging.getLogger("graf_reachula")

# The settings page holds API keys. Only answer requests addressed to the robot
# itself (IP, local name, mDNS) so a web page on another domain can't reach it
# through DNS rebinding.
LOCAL_HOST = re.compile(r"^(localhost|\d{1,3}(\.\d{1,3}){3}|\[[0-9a-f:]+\]|[\w-]+(\.local)?)(:\d+)?$", re.IGNORECASE)


def check_host(request: Request):
    if not LOCAL_HOST.match(request.headers.get("host", "")):
        raise HTTPException(status_code=403, detail="Open this page via the robot's address")


class SettingsUpdate(BaseModel):
    changes: dict


class GrafReachula(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = None

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
        settings = Settings.load()
        stage = Stage(reachy_mini)
        voice = Voice(stage, settings)
        haunt = Haunt(reachy_mini, stage, settings, say=voice)
        talk_stop = threading.Event()
        talk_thread: threading.Thread | None = None
        status = {"talking": False, "talk_error": ""}
        talk_lock = threading.Lock()
        requests: list[tuple[str, str]] = []   # effects requested from the web page

        def restart_talking():
            """Stop any running conversation and start a new one with the current settings."""
            with talk_lock:
                stop_talking()
                start_talking()

        def start_talking():
            nonlocal talk_thread, talk_stop
            status["talking"], status["talk_error"] = False, ""
            if not settings.can_talk():
                return
            try:
                from graf_reachula.talk import Talk

                talk = Talk(reachy_mini, stage, settings, voice, haunt)
            except Exception as e:
                log.error("Talking disabled: %s", e)
                status["talk_error"] = str(e)
                return
            talk_stop = threading.Event()
            talk_thread = threading.Thread(target=talk.run, args=(talk_stop,), daemon=True)
            talk_thread.start()
            status["talking"] = True

        def stop_talking():
            # A thread stuck in a slow model call finishes on its own; its stop
            # event keeps it from answering, so don't block the web request on it
            talk_stop.set()
            if talk_thread is not None:
                talk_thread.join(timeout=2)
            status["talking"] = False

        # --- web page routes (the server starts before run(); the page retries) ---

        @self.settings_app.get("/api/settings")
        def get_settings(request: Request):
            check_host(request)
            return {**settings.public(), **status, "voice_status": voice.status}

        @self.settings_app.post("/api/settings")
        def update_settings(update: SettingsUpdate, request: Request):
            check_host(request)
            talk_related = {"talk", "language", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
                            "stt_provider", "stt_model", "stt_api_key", "stt_base_url", "elevenlabs_api_key"}
            settings.update(update.changes)
            settings.save()
            if {"tts_provider", "elevenlabs_api_key", "elevenlabs_voice", "elevenlabs_model"} & set(update.changes):
                voice.reset()
            if talk_related & set(update.changes):
                restart_talking()
            return {**settings.public(), **status, "voice_status": voice.status}

        @self.settings_app.post("/api/play/{kind}/{name}")
        def play(kind: str, name: str, request: Request):
            check_host(request)
            requests.append((kind, name))
            return {"queued": f"{kind}:{name}"}

        # --- the show ---------------------------------------------------------------

        stage.neutral()
        for line in voice.texts["intro"]:
            voice(line)
            if stop_event.is_set():
                return
        stage.play_sound("laugh")

        restart_talking()
        haunt_thread = threading.Thread(target=haunt.run, args=(stop_event,), daemon=True)
        haunt_thread.start()

        try:
            while not stop_event.is_set():
                while requests:
                    kind, name = requests.pop(0)
                    try:
                        if kind == "say":
                            voice(voice.texts["voice_test"])
                        elif kind == "sound":
                            stage.play_sound(name)
                        elif kind == "move":
                            stage.play_move(name)
                        elif kind == "scare":
                            haunt.jump_scare()
                    except Exception:
                        log.exception("Could not play %s:%s", kind, name)
                time.sleep(0.1)
        finally:
            with talk_lock:
                stop_talking()
            haunt_thread.join(timeout=10)


if __name__ == "__main__":
    app = GrafReachula()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
