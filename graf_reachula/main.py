"""Count Reachula (Graf Reachula): a spooky, child-friendly Halloween ghost for Reachy Mini."""

import hmac
import logging
import os
import re
import secrets
import threading
import time

from fastapi import HTTPException, Request
from pydantic import BaseModel
from reachy_mini import ReachyMini, ReachyMiniApp

from graf_reachula.haunt import Haunt
from graf_reachula import settings as settings_file
from graf_reachula.settings import Settings
from graf_reachula.stage import Stage
from graf_reachula.voice import Voice

log = logging.getLogger("graf_reachula")

# The settings page holds API keys. Only answer requests addressed to the robot
# itself (IP, local name, mDNS) so a web page on another domain can't reach it
# through DNS rebinding.
LOCAL_HOST = re.compile(r"^(localhost|\d{1,3}(\.\d{1,3}){3}|\[[0-9a-f:]+\]|[\w-]+(\.local)?)(:\d+)?$", re.IGNORECASE)


# Changing these needs the settings PIN: they decide where keys, voices, the
# microphone's audio and camera photos go. Until a PIN exists they can't be changed
# from the page at all; the first PIN needs the setup code from the robot.
SENSITIVE = {"talk", "wake_word", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
             "stt_provider", "stt_model", "stt_api_key", "stt_base_url", "voice_en", "voice_de",
             "tts_provider", "elevenlabs_api_key", "elevenlabs_voice", "elevenlabs_model", "new_pin"}
MAX_QUEUE = 5
MIN_PIN_LENGTH = 6
PIN_FREE_TRIES = 5        # then a growing lockout against guessing
MAX_LOCKOUT = 300         # seconds; the owner must never be locked out for long
PIN_CHARS = re.compile(r"^[\x21-\x7e]+$")   # printable ASCII: it travels in an HTTP header
TALK_RELATED = {"talk", "language", "llm_provider", "llm_model", "llm_api_key", "llm_base_url",
                "stt_provider", "stt_model", "stt_api_key", "stt_base_url", "elevenlabs_api_key"}


def check_host(request: Request):
    if not LOCAL_HOST.match(request.headers.get("host", "")):
        raise HTTPException(status_code=403, detail="Open this page via the robot's address")


def check_write(request: Request):
    """Writes only from the app's own page: blocks drive-by requests from other web pages."""
    check_host(request)
    # A custom header can't be sent cross-site without a CORS preflight, which this server never allows
    if request.headers.get("x-graf-reachula") != "1":
        raise HTTPException(status_code=403, detail="Use the app's settings page")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request refused")


class SettingsUpdate(BaseModel):
    changes: dict


def new_setup_code() -> str:
    """A fresh one-time code in an owner-only file next to the settings."""
    code = f"{secrets.randbelow(10 ** 6):06d}"
    path = settings_file.SETTINGS_PATH.with_name("setup-code.txt")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)               # also when the file existed with other rights
        with os.fdopen(fd, "w") as f:
            f.write(code + "\n")
        log.info("Settings setup code written to %s", path)
    except OSError as e:
        log.warning("Could not write the setup code file: %s", e)
    return code


def switches_off(value) -> bool:
    return value is False or str(value).strip().lower() in ("false", "0", "off", "no")


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
        current = {"talk": None}
        pin_guard = {"failures": 0, "locked_until": 0.0}
        pin_lock = threading.Lock()            # one PIN check at a time: no parallel guessing
        # Proves the first PIN is set by the robot's owner: only readable on the robot itself
        # (never logged, never spoken: the log and the room are open to guests)
        setup = {"code": new_setup_code()}
        self.setup = setup
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
            current["talk"] = talk
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
            current["talk"] = None

        # --- web page routes (the server starts before run(); the page retries) ---

        def live_status() -> dict:
            talk = current["talk"]
            return {**status, "voice_status": voice.status, "listen_error": talk.last_error if talk else ""}

        @self.settings_app.get("/api/settings")
        def get_settings(request: Request):
            check_host(request)
            settings.reload_pin()
            return {**settings.public(), **live_status()}

        def wrong_guess(detail: str):
            pin_guard["failures"] += 1
            if pin_guard["failures"] >= PIN_FREE_TRIES:
                lockout = min(MAX_LOCKOUT, 30 * 2 ** (pin_guard["failures"] - PIN_FREE_TRIES))
                pin_guard["locked_until"] = time.time() + lockout
            raise HTTPException(status_code=403, detail=detail)

        def check_pin_rules(changes: dict, request: Request):
            """Raises unless this request may make these changes. Call with pin_lock held."""
            sensitive = SENSITIVE & set(changes)
            if "talk" in sensitive and switches_off(changes["talk"]):
                sensitive.discard("talk")      # anyone may silence the Count, e.g. during a lockout
            if not sensitive:
                return
            if time.time() < pin_guard["locked_until"]:
                wait = int(pin_guard["locked_until"] - time.time()) + 1
                raise HTTPException(status_code=429, detail=f"Too many wrong guesses, try again in {wait} s")
            if settings.admin_pin_hash:
                if not settings.check_pin(request.headers.get("x-graf-pin")):
                    wrong_guess("Settings PIN required for: " + ", ".join(sorted(sensitive)))
            elif sensitive != {"new_pin"}:
                raise HTTPException(status_code=403, detail="Set a settings PIN first (section 🔒 Settings PIN)")
            elif not hmac.compare_digest(request.headers.get("x-graf-setup", "").strip().encode(), setup["code"].encode()):
                wrong_guess("Enter the setup code from setup-code.txt on the robot (see the README)")
            pin_guard["failures"] = 0

        @self.settings_app.post("/api/settings")
        def update_settings(update: SettingsUpdate, request: Request):
            check_write(request)
            with pin_lock:
                settings.reload_pin()      # a PIN reset over SSH counts right away
                check_pin_rules(update.changes, request)
                new_pin = update.changes.pop("new_pin", None)
                if isinstance(new_pin, str) and new_pin.strip():
                    if len(new_pin.strip()) < MIN_PIN_LENGTH:
                        raise HTTPException(status_code=400, detail=f"The PIN needs at least {MIN_PIN_LENGTH} characters")
                    if not PIN_CHARS.match(new_pin.strip()):
                        raise HTTPException(status_code=400, detail="Use letters, digits and ASCII symbols only, no spaces")
                    settings.set_pin(new_pin.strip())
                    setup["code"] = new_setup_code()    # one use only, e.g. after a PIN reset
                before = settings.public()
                settings.update(update.changes)
                settings.save()
                after = settings.public()
            # The page sends every field on Save; only restart for what really changed
            changed = {name for name in TALK_RELATED if before.get(name) != after.get(name)}
            changed |= {name for name in ("llm_api_key", "stt_api_key", "elevenlabs_api_key")
                        if isinstance(update.changes.get(name), str) and update.changes[name]
                        and not update.changes[name].startswith("••••")}
            if {"tts_provider", "elevenlabs_api_key", "elevenlabs_voice", "elevenlabs_model"} & set(update.changes):
                voice.reset()
            if changed & TALK_RELATED:
                restart_talking()
            return {**settings.public(), **live_status()}

        @self.settings_app.post("/api/play/{kind}/{name}")
        def play(kind: str, name: str, request: Request):
            check_write(request)
            if len(requests) >= MAX_QUEUE:
                raise HTTPException(status_code=429, detail="Easy, the Count is still busy")
            requests.append((kind, name))
            return {"queued": f"{kind}:{name}"}

        # --- the show ---------------------------------------------------------------

        stage.neutral()
        for line in voice.texts["intro"]:
            voice(line)
            if stop_event.is_set():
                return
        stage.play_sound("laugh")

        threading.Thread(target=voice.warm_up, args=(voice.texts["after_scare"],), daemon=True).start()
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
            stop_event.set()   # let the haunt thread finish before the robot connection closes
            with talk_lock:
                stop_talking()
            haunt_thread.join(timeout=10)


if __name__ == "__main__":
    app = GrafReachula()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
