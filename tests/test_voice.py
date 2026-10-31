import io
import sys
import types

import numpy as np
import pytest
import soundfile as sf

from graf_reachula import voice
from graf_reachula.settings import Settings
from graf_reachula.voice import RATE, PITCH, Voice


def wav_bytes(seconds=0.1, rate=16000):
    buf = io.BytesIO()
    sf.write(buf, np.full(int(rate * seconds), 0.1, dtype=np.float32), rate, format="WAV")
    return buf.getvalue()


@pytest.fixture
def fake_edge(monkeypatch):
    """Replaces the edge_tts package: records calls, returns a WAV clip as the 'audio' stream."""
    record = {"calls": [], "error": None, "data": wav_bytes()}

    class Communicate:
        def __init__(self, text, voice_name, rate, pitch):
            record["calls"].append({"text": text, "voice": voice_name, "rate": rate, "pitch": pitch})

        async def stream(self):
            if record["error"]:
                raise record["error"]
            yield {"type": "audio", "data": record["data"]}
            yield {"type": "WordBoundary", "data": None}

    module = types.ModuleType("edge_tts")
    module.Communicate = Communicate
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return record


def test_synthesize_returns_mono_float_audio_and_rate(fake_edge):
    result = voice.synthesize("Boo", "en-GB-RyanNeural")
    assert result is not None
    audio, rate = result
    assert rate == 16000
    assert audio.ndim == 1 and audio.dtype == np.float32
    assert fake_edge["calls"][0] == {"text": "Boo", "voice": "en-GB-RyanNeural", "rate": RATE, "pitch": PITCH}


def test_synthesize_failure_returns_none(fake_edge):
    fake_edge["error"] = RuntimeError("no network to Microsoft")
    assert voice.synthesize("Boo", "en-GB-RyanNeural") is None


def test_voice_speaks_in_the_selected_language(fake_edge, stage):
    settings = Settings(language="de", voice_en="en-GB-RyanNeural", voice_de="de-DE-ConradNeural")
    Voice(stage, settings)("Guten Abend")
    assert fake_edge["calls"][-1]["voice"] == "de-DE-ConradNeural"
    assert stage.calls and stage.calls[-1][0] == "audio"


def test_voice_uses_english_voice_by_default(fake_edge, stage):
    Voice(stage, Settings())("Good evening")
    assert fake_edge["calls"][-1]["voice"] == "en-GB-RyanNeural"


def test_voice_ignores_blank_text(fake_edge, stage):
    Voice(stage, Settings())("   ")
    assert fake_edge["calls"] == []
    assert stage.calls == []


def test_voice_stays_silent_when_tts_fails(fake_edge, stage):
    fake_edge["error"] = RuntimeError("offline")
    Voice(stage, Settings())("Hello")
    assert stage.calls == []


def test_a_failing_edge_voice_shows_a_warning_until_it_works_again(fake_edge, stage):
    speaker = Voice(stage, Settings())
    fake_edge["error"] = RuntimeError("Microsoft is down")
    speaker("Good evening")
    assert speaker.status.startswith("⚠️")
    speaker("Good evening")                  # a retry that still fails, or a line from the cache
    assert speaker.status.startswith("⚠️"), "the warning stays until the voice works again"
    fake_edge["error"] = None
    speaker("Good evening again")
    assert speaker.status == "Free Edge voice"
