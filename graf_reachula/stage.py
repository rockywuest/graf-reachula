"""The robot's body and voice: sounds, recorded moves, poses.

Only one performance runs at a time (speaking, a move, a scare); the rest of
the app asks the stage whether it is free.
"""

import logging
import threading
import time

import numpy as np
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

from graf_reachula import sounds

log = logging.getLogger(__name__)

EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"

# Friendly names (used in the LLM prompt) -> moves in Pollen's emotion library
MOVES = {
    "scared": "scared1",
    "startled": "fear1",
    "laughing": "laughing1",
    "dying": "dying1",
    "surprised": "surprised1",
    "shocked": "electric1",
    "angry": "rage1",
}

# Seconds the ears stay shut after a clip. Measured on the robot: when a clip we push ourselves has ended,
# the mic is back at room level at once; for library sounds and moves only an estimate of the end is known
TAIL_EXACT = 0.3
TAIL_ESTIMATED = 1.5

# Sounds taken from the emotion library instead of being synthesized
LIBRARY_SOUNDS = {"laugh": "laughing2"}


class Stage:
    def __init__(self, robot: ReachyMini):
        self.robot = robot
        self.lock = threading.RLock()
        self.speaking = False           # audio is playing: the ears must not listen
        self.quiet_from = 0.0           # the room still echoes until this time
        self.recording = False          # the ears are using the microphone
        self.ears = None                # the Ears that currently own the microphone
        self.heard_at = 0.0             # when the microphone last heard someone speaking
        self.gesture_thread: threading.Thread | None = None   # a silent move running alongside speech
        self.last_performance = time.time()
        self.pose = "neutral"           # "lurk" while the head hangs down waiting for a victim
        self.sounds = sounds.build_library()
        self.moves: dict = {}
        self.library = None
        try:
            from reachy_mini.motion.recorded_move import RecordedMoves
            self.library = RecordedMoves(EMOTIONS_DATASET)
            available = set(self.library.list_moves())
            self.moves = {name: self.library.get(move) for name, move in MOVES.items() if move in available}
        except Exception as e:
            log.warning("Emotion moves unavailable: %s", e)
        log.info("Sounds: %s; moves: %s", ", ".join(self.sounds), ", ".join(self.moves))

    # -- audio ------------------------------------------------------------------

    def play_audio(self, audio: np.ndarray, sample_rate: int = sounds.SR):
        """Play a mono float32 clip and block until it has finished."""
        if audio is None or not len(audio):
            return
        media = self.robot.media
        out_rate = media.get_output_audio_samplerate() or sample_rate
        if out_rate != sample_rate:
            n_out = int(len(audio) * out_rate / sample_rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n_out), np.arange(len(audio)), audio)
        channels = max(1, media.get_output_channels() or 2)
        frames = np.repeat(np.asarray(audio, dtype=np.float32)[:, None], channels, axis=1)

        with self.lock:
            self.speaking = True
            try:
                media.start_playing()
                media.push_audio_sample(frames)
                time.sleep(len(audio) / out_rate + 0.2)
                media.stop_playing()
            finally:
                # Short: the guest's quick "Yes!" right after his question must be heard
                self._done(TAIL_EXACT)

    def play_sound(self, name: str):
        if name in self.sounds:
            self.play_audio(self.sounds[name])
        elif name in LIBRARY_SOUNDS and self.library is not None and LIBRARY_SOUNDS[name] in self.library.moves:
            path = self.library.sounds.get(LIBRARY_SOUNDS[name])
            duration = self.library.get(LIBRARY_SOUNDS[name]).duration
            if path:
                with self.lock:
                    self.speaking = True
                    try:
                        self.robot.media.play_sound(path)
                        time.sleep(duration + 0.3)
                    finally:
                        self._done()
        else:
            log.info("Unknown sound: %s", name)

    # -- moves --------------------------------------------------------------------

    def gesture(self, name: str):
        """Start a silent move and return at once: it runs while the Count speaks.

        No sound, so the ears keep listening; a gesture after the speech made him deaf
        to the quick "Yes!" after his own question.
        """
        move = self.moves.get(name)
        if move is None:
            log.info("Unknown move: %s", name)
            return
        self.finish_gesture()

        def run():
            try:
                self.robot.play_move(move, initial_goto_duration=0.6, sound=False)
            except Exception as e:
                log.warning("Gesture failed: %s", e)
            finally:
                self.last_performance = time.time()

        self.pose = "move"
        self.gesture_thread = threading.Thread(target=run, daemon=True)
        self.gesture_thread.start()

    def gesturing(self) -> bool:
        return self.gesture_thread is not None and self.gesture_thread.is_alive()

    def finish_gesture(self, timeout: float = 6.0):
        """Wait for a running gesture: two moves at once would fight over the motors."""
        thread = self.gesture_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def play_move(self, name: str):
        """Play a recorded emotion move with its own sound."""
        move = self.moves.get(name)
        if move is None:
            log.info("Unknown move: %s", name)
            return
        self.finish_gesture()
        with self.lock:
            self.speaking = True
            try:
                self.pose = "move"
                self.robot.play_move(move, initial_goto_duration=0.6, sound=True)
            finally:
                self._done()

    def _done(self, tail: float = TAIL_ESTIMATED):
        # On the robot, playback and recording share one GStreamer pipeline:
        # stopping playback (or a sound played along with a move) can stop the microphone
        if self.recording:
            try:
                self.robot.media.start_recording()
            except Exception as e:
                log.warning("Could not re-arm the microphone: %s", e)
        self.speaking = False
        self.last_performance = time.time()
        self.quiet_from = self.last_performance + tail

    # -- poses --------------------------------------------------------------------

    def neutral(self, duration: float = 1.0):
        self.finish_gesture()
        with self.lock:
            self.pose = "neutral"
            self.robot.goto_target(head=create_head_pose(), antennas=np.deg2rad([0, 0]),
                                   duration=duration, method="minjerk")

    def lurk(self):
        """Head down, antennas flat: waiting perfectly still for a victim."""
        self.finish_gesture()
        with self.lock:
            self.pose = "lurk"
            self.robot.goto_target(head=create_head_pose(pitch=18, degrees=True), antennas=np.deg2rad([5, 5]),
                                   duration=2.0, method="minjerk")
            time.sleep(2.2)

    def jump(self):
        """The scare: head up and antennas out, as fast as the motors allow."""
        self.finish_gesture()
        self.pose = "jump"
        self.robot.goto_target(head=create_head_pose(pitch=-15, degrees=True),
                               antennas=np.deg2rad([90, 90]), duration=0.25, method="linear")

    def free(self) -> bool:
        """True when nothing is being performed right now."""
        if not self.lock.acquire(blocking=False):
            return False
        self.lock.release()
        return not self.speaking and not self.gesturing()

    def echoing(self) -> bool:
        """True while playing or just after: the microphone would hear the robot itself."""
        return self.speaking or time.time() < self.quiet_from
