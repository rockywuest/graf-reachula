"""The talking Count: listen, think (any LLM), answer with voice, sounds and moves."""

import base64
import logging
import re
import threading
import time

import cv2

from graf_reachula.brain import Brain
from graf_reachula.ears import Ears
from graf_reachula.texts import system_prompt

log = logging.getLogger(__name__)

FOLLOW_UP = 25   # seconds after a reply in which the name isn't needed again

# How speech recognition spells the robot's name when people call it
ADDRESSED = re.compile(
    r"\breach|\bri[ct]+s?c?h[iy]|r[ei]e?a?t?s?c?h[iy]e?|\bcount\b|\bgraf\b|dracula|reachula",
    re.IGNORECASE,
)

TAG = re.compile(r"\[(sound|move|scare)(?::([^\]]*))?\]", re.IGNORECASE)


def split_effects(reply: str) -> tuple[str, list[tuple[str, str]]]:
    """Separate [sound:x] / [move:x] / [scare] tags from the text to speak."""
    effects = [(kind.lower(), (arg or "").strip().lower()) for kind, arg in TAG.findall(reply)]
    text = TAG.sub("", reply)
    # Drop any other bracketed stage directions the model may add
    text = re.sub(r"\[[^\]]*\]|\*[^*]*\*", "", text)
    return " ".join(text.split()), effects


def frame_as_jpeg_b64(robot, width: int = 640) -> str | None:
    frame = robot.media.get_frame()
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)))
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(jpeg.tobytes()).decode() if ok else None


class Talk:
    def __init__(self, robot, stage, settings, voice, haunt):
        self.robot = robot
        self.stage = stage
        self.settings = settings
        self.voice = voice
        self.haunt = haunt
        self.ears = Ears(robot, stage, settings.stt(), settings.language)
        self.brain = Brain(settings.llm(), system_prompt(settings.language))
        self.last_reply = 0.0

    def perform(self, effects):
        for kind, arg in effects:
            if kind == "sound":
                self.stage.play_sound(arg)
            elif kind == "move":
                self.stage.play_move(arg)
            elif kind == "scare":
                self.haunt.jump_scare()

    def handle(self, text: str):
        addressed = bool(ADDRESSED.search(text))
        if self.settings.wake_word and not addressed and time.time() - self.last_reply > FOLLOW_UP:
            log.debug("Not addressed, ignored")
            return
        log.info("Heard: %r", text)
        self.haunt.conversation_active.set()
        try:
            try:
                reply = self.brain.reply(text, frame_as_jpeg_b64(self.robot))
            except Exception as e:
                log.error("LLM call failed: %s", e)
                self.voice(self.voice.texts["error"])
                return
            spoken, effects = split_effects(reply)
            log.info("Count: %r %s", spoken, effects)
            self.voice(spoken)
            self.perform(effects)
            self.last_reply = time.time()
        finally:
            self.haunt.conversation_active.clear()

    def run(self, stop_event: threading.Event):
        try:
            while not stop_event.is_set():
                audio = self.ears.listen(stop_event)
                if audio is None:
                    continue
                try:
                    text = self.ears.transcribe(audio)
                except Exception as e:
                    log.error("Speech-to-text failed: %s", e)
                    continue
                if text:
                    self.handle(text)
        finally:
            self.ears.close()
