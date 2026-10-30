"""The talking Count: listen, think (any LLM), answer with voice, sounds and moves."""

import base64
import logging
import random
import re
import threading
import time

import cv2

from graf_reachula.brain import Brain
from graf_reachula.ears import Ears
from graf_reachula.texts import TEXTS, system_prompt
from graf_reachula.voice import describe_error

log = logging.getLogger(__name__)

FOLLOW_UP = 25   # seconds after a reply in which the name isn't needed again

# How speech recognition spells the robot's name when people call it
ADDRESSED = re.compile(
    # Reachy, Reach it, Richie, Ritschi, Reichy, Raichy, Count, Graf, Reachula, Reichula, Dracula
    r"\breach(y|ie|i|\s+it)?\b|\br[ae]?[aei]e?t?s?c?h[iy]e?\b|\bcount\b|\bgraf\b|dracula|re[ai]?chula",
    re.IGNORECASE,
)
ECHO_WINDOW = 5    # seconds after he finished (speech-to-text needs a moment, too) in which a transcript may be his own last line
ECHO_OVERLAP = 0.9  # nearly all words his: a guest who answers ("yes, tell me a ghost story") repeats only some

FILLER_MOVES = ("laughing", "surprised", "scared", "startled", "shocked")   # when the model forgets a move
SOUNDS = ("heartbeat", "ghost", "door", "wind", "bells", "laugh")

TAG = re.compile(r"\[(sound|move|scare)(?::([^\]]*))?\]", re.IGNORECASE)


def split_effects(reply: str) -> tuple[str, list[tuple[str, str]]]:
    """Separate [sound:x] / [move:x] / [scare] tags from the text to speak."""
    effects = [(kind.lower(), (arg or "").strip().lower()) for kind, arg in TAG.findall(reply)]
    text = TAG.sub(" ", reply)
    # Drop any other bracketed stage directions the model may add
    text = re.sub(r"\[[^\]]*\]|\*[^*]*\*", " ", text)
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
        self.brain = Brain(settings.llm(), system_prompt(settings.language, settings.scares),
                           safe_line=TEXTS[settings.language]["safe"])
        self.last_reply = 0.0
        self.last_spoken = ""
        self.last_effects: dict[str, str] = {}   # the last sound and move, so the next differ
        self.stop_event = threading.Event()   # replaced by run()
        # Shown on the settings page; each one is cleared only by its own next success
        self.stt_error = ""
        self.chat_error = ""

    @property
    def last_error(self) -> str:
        return " · ".join(e for e in (self.stt_error, self.chat_error) if e)

    def vary(self, effects):
        """Every answer gets a gesture, and no sound or move twice in a row.

        At the party the model chose "ghost" for nearly every reply and once "dying" three times running.
        """
        known = self.stage.moves
        if not any(kind == "scare" or (kind == "move" and arg in known) for kind, arg in effects):
            # A Count who only talks looks stiff (a move this robot lacks would show nothing)
            effects = [(k, a) for k, a in effects if k != "move"] + [("move", "")]
        varied = []
        for kind, arg in effects:
            if kind == "move":
                if arg not in known or arg == self.last_effects.get("move"):
                    fresh = [m for m in FILLER_MOVES if m in known and m != self.last_effects.get("move")]
                    if not fresh:
                        continue   # no other move on this robot: rather none than the same again
                    arg = random.choice(fresh)
            elif kind == "sound" and arg == self.last_effects.get("sound"):
                arg = random.choice([s for s in SOUNDS if s != arg])
            if kind in ("sound", "move"):
                self.last_effects[kind] = arg
            varied.append((kind, arg))
        return varied

    def perform(self, effects):
        for kind, arg in effects:
            if kind == "sound":
                self.stage.play_sound(arg)
            elif kind == "move":
                self.stage.play_move(arg)
            elif kind == "scare":
                self.haunt.jump_scare()

    def is_echo(self, text: str) -> bool:
        """True if the transcript is mostly the Count's own last sentence (heard through the mic)."""
        if time.time() - self.last_reply > ECHO_WINDOW or not self.last_spoken:
            return False
        words = {w for w in re.findall(r"\w{4,}", text.lower())}
        spoken = {w for w in re.findall(r"\w{4,}", self.last_spoken.lower())}
        # Short calls ("Tell me a ghost story!") are guests answering his offer, not his echo
        return len(words & spoken) >= 4 and len(words & spoken) / len(words) > ECHO_OVERLAP

    def handle(self, text: str):
        if self.is_echo(text):
            log.info("Ignored my own echo")
            return
        addressed = bool(ADDRESSED.search(text))
        if self.settings.wake_word and not addressed and time.time() - self.last_reply > FOLLOW_UP:
            log.debug("Not addressed, ignored")
            return
        # What guests say stays out of the log: the robot's log is readable on the network
        log.info("Heard someone call (%d words)", len(text.split()))
        log.debug("Heard: %r", text)
        self.haunt.conversation_active.set()
        try:
            if getattr(self.stage, "pose", "neutral") == "lurk" or self.haunt.lurking:
                # Look up first: the photo for the costume guess must show the guests, not the floor
                self.stage.neutral()
                self.haunt.lurking = False
            # Without scares, don't offer the model a [scare] tag
            self.brain.system_prompt = system_prompt(self.settings.language, self.settings.scares)
            started = time.monotonic()
            try:
                reply = self.brain.reply(text, frame_as_jpeg_b64(self.robot))
            except Exception as e:
                log.error("LLM call failed: %s", e)
                self.chat_error = f"Chat model failed: {describe_error(e)}"
                self.voice(self.voice.texts["error"])
                return
            if self.stop_event.is_set():
                return   # settings changed while thinking; a newer conversation has taken over
            if not reply:
                # E.g. the model spent its whole budget thinking: say so instead of staying mute
                log.warning("The chat model returned no text")
                self.chat_error = "Chat model returned no answer (try another model)"
                self.voice(self.voice.texts["error"])
                return
            self.chat_error = ""
            spoken, effects = split_effects(reply)
            effects = self.vary(effects)
            log.info("Count answers (%d words, %.1f s) %s", len(spoken.split()), time.monotonic() - started, effects)
            log.debug("Count: %r", spoken)
            self.last_spoken = spoken
            self.voice(spoken)
            self.perform(effects)
            self.last_reply = time.time()
        finally:
            self.haunt.conversation_active.clear()

    def run(self, stop_event: threading.Event):
        self.stop_event = stop_event
        while not stop_event.is_set():
            try:
                audio = self.ears.listen(stop_event)
                if audio is None or stop_event.is_set():
                    continue
                try:
                    text = self.ears.transcribe(audio)
                except Exception as e:
                    log.error("Speech-to-text failed: %s", e)
                    self.stt_error = f"Speech-to-text failed: {describe_error(e)}"
                    time.sleep(1)
                    continue
                self.stt_error = ""
                if text and not stop_event.is_set():
                    self.handle(text)
            except Exception:
                log.exception("Talking hiccup")
                time.sleep(1)
        self.ears.close()
