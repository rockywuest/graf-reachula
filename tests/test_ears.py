from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from graf_reachula import ears
from graf_reachula.ears import END_SILENCE, FRAME_SECONDS, PHANTOMS, EnergyVAD, Ears

RATE = 16000
FRAME = int(RATE * FRAME_SECONDS)   # 480 samples


def loud():
    return np.full(FRAME, 0.3, dtype=np.float32)


def quiet():
    return np.zeros(FRAME, dtype=np.float32)


def feed(vad, frames):
    return [out for out in (vad.push(f) for f in frames) if out is not None]


def test_silence_never_returns_an_utterance():
    vad = EnergyVAD(RATE)
    assert feed(vad, [quiet() for _ in range(500)]) == []


def test_loud_burst_then_silence_returns_exactly_one_utterance():
    vad = EnergyVAD(RATE)
    burst = 20                                   # 0.6 s of speech
    silence = int(round(END_SILENCE / FRAME_SECONDS)) + 5
    utterances = feed(vad, [loud() for _ in range(burst)] + [quiet() for _ in range(silence)])
    assert len(utterances) == 1
    seconds = len(utterances[0]) / RATE
    assert 0.6 <= seconds <= 1.6, seconds
    assert utterances[0].dtype == np.float32


def test_short_click_is_ignored():
    vad = EnergyVAD(RATE)
    assert feed(vad, [loud(), loud()] + [quiet() for _ in range(60)]) == []


def test_speech_shorter_than_minimum_is_ignored():
    vad = EnergyVAD(RATE)
    # 0.09 s of loud audio: long enough to start, too short to count as speech
    assert feed(vad, [loud() for _ in range(3)] + [quiet() for _ in range(60)]) == []


def test_max_length_cuts_a_long_utterance(monkeypatch):
    # A steady tone fades into the background after a few seconds (by design), so the cap is
    # checked with a short MAX_SPEECH; the cut itself is what's under test
    monkeypatch.setattr(ears, "MAX_SPEECH", 2.0)
    vad = EnergyVAD(RATE)
    utterances = feed(vad, [loud() for _ in range(int(10 / FRAME_SECONDS))])
    assert len(utterances) >= 1
    assert 1.9 <= len(utterances[0]) / RATE <= 2.1


def test_quiet_room_noise_is_not_speech():
    vad = EnergyVAD(RATE)
    rng = np.random.default_rng(0)
    hum = [(rng.standard_normal(FRAME) * 0.005).astype(np.float32) for _ in range(int(60 / FRAME_SECONDS))]
    assert feed(vad, hum) == []


def test_steady_loud_room_noise_is_reported_at_most_once():
    # A party's steady noise is reported once at onset (~4 s), then the floor rises to meet it
    # and it stops counting as speech; it must not be cut into utterances every few seconds
    vad = EnergyVAD(RATE)
    rng = np.random.default_rng(0)
    hum = [(rng.standard_normal(FRAME) * 0.03).astype(np.float32) for _ in range(int(60 / FRAME_SECONDS))]
    utterances = feed(vad, hum)
    assert len(utterances) <= 1
    assert all(len(u) / RATE < 6.0 for u in utterances)


@pytest.mark.parametrize("text", [
    "Thank you.", "thank you", "Thanks for watching!", "Vielen Dank.", "Untertitel der Amara.org",
    "you", "Bye.", "Danke schön.", "...", "",
])
def test_whisper_phantoms_are_recognised(text):
    assert PHANTOMS.match(text)


@pytest.mark.parametrize("text", [
    "Wo ist das Klo", "Thank you for the cake", "Danke, Graf Reachula", "Bye bye Count",
    "Reachy, what time is it?", "Richtig gut",
])
def test_real_sentences_are_not_phantoms(text):
    assert not PHANTOMS.match(text)


def make_ears(text_result):
    e = Ears.__new__(Ears)
    e.model = "stt-model"
    e.language = "en"
    e.rate = RATE
    e.client = MagicMock()
    e.client.audio.transcriptions.create.return_value = SimpleNamespace(text=text_result)
    return e


def test_transcribe_sends_wav_and_returns_text():
    e = make_ears("Reachy, hello")
    assert e.transcribe(np.zeros(RATE, dtype=np.float32)) == "Reachy, hello"
    kwargs = e.client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "stt-model"
    assert kwargs["language"] == "en"
    name, data, mime = kwargs["file"]
    assert name == "speech.wav" and mime == "audio/wav"
    assert data[:4] == b"RIFF"


def test_transcribe_drops_phantoms():
    assert make_ears("Thank you.").transcribe(np.zeros(RATE, dtype=np.float32)) == ""


def test_transcribe_handles_empty_result():
    assert make_ears(None).transcribe(np.zeros(RATE, dtype=np.float32)) == ""
