import threading
import time
from types import SimpleNamespace

from graf_reachula.stage import Stage


class SlowRobot:
    def __init__(self):
        self.moves = []
        self.targets = 0
        self.release = threading.Event()

    def play_move(self, move, initial_goto_duration=0.0, sound=True):
        self.moves.append((move, sound))
        self.release.wait(2)

    def goto_target(self, **kwargs):
        self.targets += 1


def bare_stage(robot):
    stage = Stage.__new__(Stage)
    stage.robot, stage.lock = robot, threading.RLock()
    stage.speaking, stage.quiet_from, stage.recording = False, 0.0, False
    stage.moves, stage.gesture_thread, stage.pose = {"laughing": "MOVE"}, None, "neutral"
    stage.last_performance = 0.0
    return stage


def test_a_gesture_is_silent_and_does_not_block_the_speech():
    robot = SlowRobot()
    stage = bare_stage(robot)
    started = time.monotonic()
    stage.gesture("laughing")
    assert time.monotonic() - started < 0.5, "the Count must start speaking at once"
    assert not stage.echoing(), "the ears keep listening during a silent gesture"
    assert not stage.free(), "the haunt waits for the gesture"
    robot.release.set()
    stage.finish_gesture()
    assert robot.moves == [("MOVE", False)]
    assert stage.free()


def test_the_next_pose_waits_for_a_running_gesture():
    robot = SlowRobot()
    stage = bare_stage(robot)
    stage.gesture("laughing")
    threading.Timer(0.3, robot.release.set).start()
    stage.neutral()
    assert not stage.gesturing() and robot.targets == 1


def test_an_unknown_gesture_is_skipped():
    stage = bare_stage(SimpleNamespace())
    stage.gesture("moonwalk")
    assert stage.gesture_thread is None


def test_the_ears_open_right_after_his_last_word():
    """Measured on the robot: no echo once a pushed clip has ended. A long tail swallowed the "Yes!"."""
    import numpy as np

    media = SimpleNamespace(get_output_audio_samplerate=lambda: 16000, get_output_channels=lambda: 1,
                            start_playing=lambda: None, push_audio_sample=lambda f: None, stop_playing=lambda: None)
    stage = bare_stage(SimpleNamespace(media=media))
    stage.play_audio(np.zeros(160, dtype=np.float32), 16000)
    assert stage.echoing()
    time.sleep(0.4)
    assert not stage.echoing(), "a 'Yes!' 0.4 s after his question must reach the ears"


def test_a_new_gesture_is_skipped_while_one_runs_so_the_answer_does_not_wait():
    robot = SlowRobot()
    stage = bare_stage(robot)
    stage.moves["surprised"] = "MOVE2"
    stage.gesture("laughing")
    started = time.monotonic()
    stage.gesture("surprised")
    assert time.monotonic() - started < 0.2
    robot.release.set()
    stage.finish_gesture()
    assert robot.moves == [("MOVE", False)]
