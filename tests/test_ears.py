from types import SimpleNamespace
from unittest.mock import MagicMock

import threading

import numpy as np
import pytest

from graf_reachula import ears
from conftest import FakeMedia, FakeRobot
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


def test_steady_music_is_cut_into_short_chunks_and_fades_into_the_background():
    # Under steady party music the Count must still hear a call, so loud sound is cut into
    # short chunks (each one transcribed); the floor adapts slowly until the music is background
    vad = EnergyVAD(RATE)
    rng = np.random.default_rng(0)
    hum = [(rng.standard_normal(FRAME) * 0.03).astype(np.float32) for _ in range(int(240 / FRAME_SECONDS))]
    utterances = feed(vad, hum)
    assert utterances, "the music onset is heard"
    assert all(len(u) / RATE <= 6.5 for u in utterances)
    late = feed(vad, hum[:int(30 / FRAME_SECONDS)])
    assert len(late) <= 1, "after a few minutes steady music is background"


def test_a_call_over_music_lands_in_a_chunk():
    vad = EnergyVAD(RATE)
    rng = np.random.default_rng(1)
    music = lambda n: [(rng.standard_normal(FRAME) * 0.05).astype(np.float32) for _ in range(n)]
    call = [(rng.standard_normal(FRAME) * 0.15).astype(np.float32) for _ in range(int(1.5 / FRAME_SECONDS))]
    utterances = feed(vad, music(int(20 / FRAME_SECONDS)) + call + music(int(10 / FRAME_SECONDS)))
    assert any(np.sqrt(np.mean(u ** 2)) > 0.06 for u in utterances), "the louder call is inside an utterance"


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
    e.provider = "openai"
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


def test_xai_transcription_posts_multipart_with_keyterms(monkeypatch):
    """xAI has its own /v1/stt endpoint instead of /audio/transcriptions."""
    import httpx

    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = str(request.url)
        sent["auth"] = request.headers["authorization"]
        sent["body"] = request.content
        return httpx.Response(200, json={"text": " Hello Count Reachula ", "language": "en"})

    e = Ears.__new__(Ears)
    e.provider, e.api_key, e.base_url, e.language, e.rate = "xai", "xai-test", "https://api.x.ai/v1", "en", 16000
    e.client = httpx.Client(transport=httpx.MockTransport(handler))

    text = e.transcribe(np.zeros(16000, dtype=np.float32) + 0.1)

    assert text == "Hello Count Reachula"
    assert sent["url"] == "https://api.x.ai/v1/stt"
    assert sent["auth"] == "Bearer xai-test"
    body = sent["body"]
    assert b'name="language"' in body and b'name="keyterm"' in body and b"Reachula" in body
    # xAI requires the file to be the last multipart field
    assert body.rfind(b'name="file"') > body.rfind(b'name="keyterm"')


def test_close_stops_mic_only_for_the_current_listener():
    robot = SimpleNamespace(media=MagicMock())
    stage = SimpleNamespace(recording=True, ears=None, lock=threading.RLock())
    old, new = Ears.__new__(Ears), Ears.__new__(Ears)
    for e in (old, new):
        e.robot, e.stage, e.client = robot, stage, MagicMock()
    stage.ears = new

    old.close()   # a superseded listener leaves the mic to the new one
    assert stage.recording and stage.ears is new
    robot.media.stop_recording.assert_not_called()

    new.close()   # talking switched off: the mic goes off
    assert not stage.recording and stage.ears is None
    robot.media.stop_recording.assert_called_once()


def test_flush_ends_although_the_microphone_never_stops(stage):
    """The mic delivers a sample every 16 ms: draining 'until empty' would never end."""
    import time as _time


    class EndlessMedia(FakeMedia):
        reads = 0

        def get_audio_sample(self):
            EndlessMedia.reads += 1
            return np.zeros((256, 2), dtype=np.float32)

    robot = FakeRobot()
    robot.media = EndlessMedia()
    ears = Ears.__new__(Ears)
    ears.robot, ears.stage, ears.rate = robot, stage, 16000
    ears.vad = EnergyVAD(16000)
    start = _time.monotonic()
    ears._flush()
    assert _time.monotonic() - start < 0.5
    assert EndlessMedia.reads <= 20
