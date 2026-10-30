"""Count Reachula (Graf Reachula): a spooky, child-friendly Halloween ghost for Reachy Mini."""

import logging
import threading
import time

from pydantic import BaseModel
from reachy_mini import ReachyMini, ReachyMiniApp

from graf_reachula.haunt import Haunt
from graf_reachula.settings import Settings
from graf_reachula.stage import Stage
from graf_reachula.voice import Voice

log = logging.getLogger("graf_reachula")


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
        requests: list[tuple[str, str]] = []   # effects requested from the web page

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
            talk_stop.set()
            if talk_thread is not None:
                talk_thread.join(timeout=20)

        # --- web page routes (the server starts before run(); the page retries) ---

        @self.settings_app.get("/api/settings")
        def get_settings():
            return {**settings.public(), **status}

        @self.settings_app.post("/api/settings")
        def update_settings(update: SettingsUpdate):
            talk_related = {"talk", "language", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
                            "stt_provider", "stt_model", "stt_api_key", "stt_base_url"}
            settings.update(update.changes)
            settings.save()
            if talk_related & set(update.changes):
                stop_talking()
                start_talking()
            return {**settings.public(), **status}

        @self.settings_app.post("/api/play/{kind}/{name}")
        def play(kind: str, name: str):
            requests.append((kind, name))
            return {"queued": f"{kind}:{name}"}

        # --- the show ---------------------------------------------------------------

        stage.neutral()
        for line in voice.texts["intro"]:
            voice(line)
            if stop_event.is_set():
                return
        stage.play_sound("laugh")

        start_talking()
        haunt_thread = threading.Thread(target=haunt.run, args=(stop_event,), daemon=True)
        haunt_thread.start()

        try:
            while not stop_event.is_set():
                while requests:
                    kind, name = requests.pop(0)
                    if kind == "sound":
                        stage.play_sound(name)
                    elif kind == "move":
                        stage.play_move(name)
                    elif kind == "scare":
                        haunt.jump_scare()
                time.sleep(0.1)
        finally:
            stop_talking()
            haunt_thread.join(timeout=10)


if __name__ == "__main__":
    app = GrafReachula()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
