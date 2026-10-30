"""The haunting: lurk when it's quiet, jump-scare whoever walks up, spooky ambience.

Works without any API key.
"""

import logging
import random
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

LURK_AFTER = 15          # seconds of the Count being silent before he starts lurking
SCARE_COOLDOWN = 40      # seconds between two jump scares
AMBIENT_EVERY = (50, 100)
# Share of pixels that must change between two frames. A still room measured
# at most 1.7 %; someone stepping in front of the camera is far above 6 %.
MOTION_THRESHOLD = 0.06


def small_gray(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(cv2.resize(frame, (96, 54)), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0).astype(np.int16)


def changed_share(previous: np.ndarray, current: np.ndarray) -> float:
    return float(np.mean(np.abs(current - previous) > 25))


class Haunt:
    def __init__(self, robot, stage, settings, say=None):
        self.robot = robot
        self.stage = stage
        self.settings = settings
        self.say = say                  # optional: speak a line after a scare
        self.conversation_active = threading.Event()
        self.lurking = False
        self.last_scare = 0.0
        self.next_ambient = time.time() + random.uniform(*AMBIENT_EVERY)

    def quiet_for(self) -> float:
        return time.time() - self.stage.last_performance

    def jump_scare(self):
        log.info("BOO!")
        self.last_scare = time.time()
        self.lurking = False
        # The jump comes first: whoever walked up must get the BOO right now
        with self.stage.lock:
            self.stage.jump()
            self.stage.play_sound("boo")
        # The line after the scare is pre-rendered at startup; if not, render it
        # without holding the stage, so a slow voice service can't freeze the robot
        line = self.say.render(random.choice(self.say.texts["after_scare"])) if self.say else None
        with self.stage.lock:
            if "laughing" in self.stage.moves:
                self.stage.play_move("laughing")
            if self.say:
                self.say.play(line)
            self.stage.neutral()

    def ambient(self):
        choices = ["heartbeat", "ghost", "door", "wind", "bells", "laugh"]
        choices += [f"move:{m}" for m in ("scared", "shocked") if m in self.stage.moves]
        choice = random.choice(choices)
        log.info("Ambient: %s", choice)
        if choice.startswith("move:"):
            self.stage.play_move(choice[5:])
            self.lurking = False
        else:
            self.stage.play_sound(choice)
        self.next_ambient = time.time() + random.uniform(*AMBIENT_EVERY)

    def run(self, stop_event: threading.Event):
        while not stop_event.is_set():
            try:
                self._haunt(stop_event)
            except Exception:
                log.exception("Haunting hiccup")
                self.lurking = False
                time.sleep(2)

    def _haunt(self, stop_event: threading.Event):
        previous = None
        while not stop_event.is_set():
            time.sleep(0.3)
            busy = self.conversation_active.is_set() or not self.stage.free()
            if busy or self.quiet_for() < LURK_AFTER:
                previous = None
                if busy:
                    self.lurking = False
                continue

            if self.settings.ambient and time.time() > self.next_ambient:
                self.ambient()
                previous = None
                continue

            if not self.settings.scares:
                continue

            if not self.lurking:
                self.stage.lurk()
                self.lurking = True
                previous = None
                continue

            frame = self.robot.media.get_frame()
            if frame is None:
                continue
            current = small_gray(frame)
            if (previous is not None and changed_share(previous, current) > MOTION_THRESHOLD
                    and time.time() - self.last_scare > SCARE_COOLDOWN
                    and not self.conversation_active.is_set()):
                self.jump_scare()
                current = None
            previous = current
