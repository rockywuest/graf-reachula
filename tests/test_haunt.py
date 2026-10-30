import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from graf_reachula import haunt
from graf_reachula.haunt import Haunt, changed_share, small_gray
from graf_reachula.settings import Settings


def solid(value, shape=(480, 640, 3)):
    return np.full(shape, value, dtype=np.uint8)


# -- image comparison ---------------------------------------------------------------

def test_changed_share_identical_frames_is_zero():
    g = small_gray(solid(90))
    assert changed_share(g, g.copy()) == 0.0


def test_changed_share_fully_different_frames_is_one():
    assert changed_share(small_gray(solid(0)), small_gray(solid(255))) == 1.0


def test_changed_share_ignores_small_lighting_drift():
    a = small_gray(solid(100))
    b = small_gray(solid(110))   # 10 levels brighter everywhere
    assert changed_share(a, b) == 0.0


def test_changed_share_counts_only_the_changed_part():
    a = np.zeros((54, 96), dtype=np.int16)
    b = a.copy()
    b[:27] = 200                  # half the picture changes
    assert changed_share(a, b) == pytest.approx(0.5)


def test_small_gray_shape_and_type():
    g = small_gray(solid(50))
    assert g.shape == (54, 96)
    assert g.dtype == np.int16


def test_motion_threshold_separates_still_room_from_person():
    still = np.zeros((54, 96), dtype=np.int16)
    person = still.copy()
    person[:4] = 255              # about 7 % of the image
    assert changed_share(still, still) <= haunt.MOTION_THRESHOLD
    assert changed_share(still, person) > haunt.MOTION_THRESHOLD


# -- Haunt.run with fake robot and stage ----------------------------------------------

class SequenceMedia:
    """Camera that returns the given frames in order, then keeps returning the last one."""

    def __init__(self, frames):
        self.frames = list(frames)

    def get_frame(self):
        if len(self.frames) > 1:
            return self.frames.pop(0)
        return self.frames[0]


def start(haunt_obj):
    stop = threading.Event()
    thread = threading.Thread(target=haunt_obj.run, args=(stop,), daemon=True)
    thread.start()
    return stop, thread


def wait_for(stage, item, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if item in stage.calls:
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def fast_haunt(monkeypatch):
    monkeypatch.setattr(haunt, "LURK_AFTER", 0.0)
    monkeypatch.setattr(haunt, "SCARE_COOLDOWN", 0.0)


def make_haunt(stage, frames, **settings):
    robot = SimpleNamespace(media=SequenceMedia(frames))
    return Haunt(robot, stage, Settings(ambient=False, **settings))


def test_scares_a_person_who_walks_up_after_lurking(stage, fast_haunt):
    h = make_haunt(stage, [solid(0), solid(0), solid(255)])
    stop, thread = start(h)
    try:
        assert wait_for(stage, "lurk")
        assert wait_for(stage, "jump")
        assert ("sound", "boo") in stage.calls
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()


def test_does_not_scare_while_conversation_is_active(stage, fast_haunt):
    h = make_haunt(stage, [solid(0), solid(255)])
    h.conversation_active.set()
    stop, thread = start(h)
    try:
        time.sleep(2.0)
        assert "lurk" not in stage.calls
        assert "jump" not in stage.calls
    finally:
        stop.set()
        thread.join(5)


def test_no_scare_when_conversation_starts_during_lurk(stage, fast_haunt):
    h = make_haunt(stage, [solid(0), solid(0), solid(255)])
    stop, thread = start(h)
    try:
        assert wait_for(stage, "lurk")
        h.conversation_active.set()
        time.sleep(1.5)
        assert "jump" not in stage.calls
    finally:
        h.conversation_active.clear()
        stop.set()
        thread.join(5)


def test_scares_turned_off_never_lurks_or_scares(stage, fast_haunt):
    h = make_haunt(stage, [solid(0), solid(255)], scares=False)
    stop, thread = start(h)
    try:
        time.sleep(1.5)
        assert stage.calls == []
    finally:
        stop.set()
        thread.join(5)


def test_jump_scare_jumps_before_the_line_is_rendered():
    """The BOO must come at once; preparing the voice line may take a moment."""
    import threading
    from types import SimpleNamespace
    from graf_reachula.haunt import Haunt

    order = []
    stage = SimpleNamespace(lock=threading.RLock(), moves={},
                            jump=lambda: order.append("jump"),
                            play_sound=lambda name: order.append(name),
                            play_move=lambda name: order.append(name),
                            neutral=lambda: order.append("neutral"))
    say = SimpleNamespace(texts={"after_scare": ["Gotcha!"]},
                          render=lambda text: order.append("render") or "audio",
                          play=lambda audio: order.append("play"))
    Haunt(robot=None, stage=stage, settings=None, say=say).jump_scare()
    assert order == ["jump", "boo", "render", "play", "neutral"]
