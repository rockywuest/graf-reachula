import numpy as np
import pytest

from graf_reachula import sounds


@pytest.mark.parametrize("name", sorted(sounds.SOUNDS))
def test_every_sound_renders_sanely(name):
    audio = sounds.SOUNDS[name]()
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert np.all(np.isfinite(audio)), "NaN or inf in sample data"
    peak = float(np.max(np.abs(audio)))
    assert peak <= 1.0, f"peak {peak} would clip"
    assert peak > 0.5, f"peak {peak} is too quiet for a small speaker"
    seconds = len(audio) / sounds.SR
    assert 0.5 <= seconds <= 10.0, f"duration {seconds:.2f}s is not sensible"


@pytest.mark.parametrize("name", sorted(sounds.SOUNDS))
def test_every_sound_is_deterministic(name):
    first = sounds.SOUNDS[name]()
    second = sounds.SOUNDS[name]()
    assert np.array_equal(first, second)


def test_build_library_renders_all_sounds_once():
    library = sounds.build_library()
    assert set(library) == set(sounds.SOUNDS)
    for name, audio in library.items():
        assert audio.dtype == np.float32, name


def test_normalize_hits_requested_peak():
    x = np.array([0.1, -0.4, 0.2], dtype=np.float64)
    out = sounds.normalize(x, 0.5)
    assert out.dtype == np.float32
    assert float(np.max(np.abs(out))) == pytest.approx(0.5)


def test_normalize_silence_stays_silent_and_finite():
    out = sounds.normalize(np.zeros(100), 0.8)
    assert np.all(out == 0)
    assert np.all(np.isfinite(out))


def test_fade_starts_and_ends_at_zero():
    out = sounds.fade(np.ones(sounds.SR), 0.1, 0.1)
    assert out[0] == 0.0
    assert out[-1] == pytest.approx(0.0)
