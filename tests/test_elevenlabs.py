"""ElevenLabs voice and speech-to-text, and gpt-transcribe's language list (no network)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import numpy as np

from graf_reachula import voice as voice_mod
from graf_reachula.ears import Ears
from graf_reachula.settings import Settings
from graf_reachula.voice import Voice, pick_elevenlabs_voice, synthesize_elevenlabs


def test_synthesize_elevenlabs_requests_pcm_and_decodes_s16le():
    seen = {}

    def handler(request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers["xi-api-key"], request.content
        return httpx.Response(200, content=np.array([0, 16384, -32768], dtype="<i2").tobytes())

    audio, rate = synthesize_elevenlabs("Boo!", "el-key", "VOICE", "eleven_flash_v2_5", "de",
                                        client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert rate == 16000
    assert np.allclose(audio, [0.0, 0.5, -1.0])
    assert seen["url"] == "https://api.elevenlabs.io/v1/text-to-speech/VOICE?output_format=pcm_16000"
    assert seen["key"] == "el-key"
    assert b'"model_id":"eleven_flash_v2_5"' in seen["body"].replace(b" ", b"")
    assert b'"language_code":"de"' in seen["body"].replace(b" ", b"")


def test_pick_voice_prefers_deep_narrators_and_falls_back():
    def client_with(names):
        voices = [{"name": n, "voice_id": f"id-{i}"} for i, n in enumerate(names)]
        return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"voices": voices})))

    assert pick_elevenlabs_voice(client_with(["Rachel", "Callum - husky", "Clyde"]), "k") == "id-2"
    assert pick_elevenlabs_voice(client_with(["Rachel", "", "Bella"]), "k") == "id-0"


def test_voice_falls_back_to_edge_when_elevenlabs_fails(monkeypatch):
    s = Settings(tts_provider="elevenlabs", elevenlabs_api_key="el-key", elevenlabs_voice="V")
    played = []
    stage = SimpleNamespace(play_audio=lambda audio, rate: played.append(rate))
    monkeypatch.setattr(voice_mod, "synthesize_elevenlabs", MagicMock(side_effect=RuntimeError("no credits")))
    monkeypatch.setattr(voice_mod, "synthesize", lambda text, v: (np.zeros(10, np.float32), 24000))
    Voice(stage, s)("Hello")
    assert played == [24000]


def test_voice_caches_repeated_lines(monkeypatch):
    s = Settings(tts_provider="elevenlabs", elevenlabs_api_key="el-key", elevenlabs_voice="V")
    calls = MagicMock(return_value=(np.zeros(10, np.float32), 16000))
    monkeypatch.setattr(voice_mod, "synthesize_elevenlabs", calls)
    v = Voice(SimpleNamespace(play_audio=lambda *a: None), s)
    v("Gotcha!")
    v("Gotcha!")
    assert calls.call_count == 1


def test_edge_is_used_without_elevenlabs_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert Settings(tts_provider="elevenlabs").tts()["provider"] == "edge"


def test_elevenlabs_key_serves_scribe_and_is_masked():
    s = Settings(stt_provider="elevenlabs", elevenlabs_api_key="sk_eleven_secret_1234")
    assert s.stt()["api_key"] == "sk_eleven_secret_1234"
    assert s.stt()["model"] == "scribe_v2"
    assert "secret" not in s.public()["elevenlabs_api_key"]


def test_scribe_transcription_sends_model_language_and_keyterms():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), request.content
        return httpx.Response(200, json={"text": " Graf, was bin ich? "})

    e = Ears.__new__(Ears)
    e.provider, e.api_key, e.base_url, e.model = "elevenlabs", "el", "https://api.elevenlabs.io/v1", "scribe_v2"
    e.language, e.rate = "de", 16000
    e.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert e.transcribe(np.zeros(16000, np.float32) + 0.1) == "Graf, was bin ich?"
    assert seen["url"] == "https://api.elevenlabs.io/v1/speech-to-text"
    for field in (b'name="model_id"', b"scribe_v2", b'name="language_code"', b'name="keyterms"', b"Reachula"):
        assert field in seen["body"]


def test_gpt_transcribe_gets_language_list():
    e = Ears.__new__(Ears)
    e.provider, e.model, e.language, e.rate = "openai", "gpt-transcribe", "de", 16000
    e.client = MagicMock()
    e.client.audio.transcriptions.create.return_value = SimpleNamespace(text="Hallo Graf")
    e.transcribe(np.zeros(16000, np.float32) + 0.1)
    kwargs = e.client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"languages": ["de"]} and "language" not in kwargs


def test_elevenlabs_failure_pauses_it_instead_of_retrying_every_line(monkeypatch):
    s = Settings(tts_provider="elevenlabs", elevenlabs_api_key="el-key", elevenlabs_voice="V")
    failing = MagicMock(side_effect=RuntimeError("timeout"))
    monkeypatch.setattr(voice_mod, "synthesize_elevenlabs", failing)
    monkeypatch.setattr(voice_mod, "synthesize", lambda text, v: (np.zeros(10, np.float32), 24000))
    v = Voice(SimpleNamespace(play_audio=lambda *a: None), s)
    v("one")
    v("two")
    v("three")
    assert failing.call_count == 1


def test_gpt_transcribe_rejection_falls_back_to_previous_model():
    class Rejected(Exception):
        status_code = 400

    e = Ears.__new__(Ears)
    e.provider, e.model, e.language, e.rate = "openai", "gpt-transcribe", "en", 16000
    e.client = MagicMock()
    e.client.audio.transcriptions.create.side_effect = [Rejected("unknown model"), SimpleNamespace(text="Hello Count")]
    assert e.transcribe(np.zeros(16000, np.float32) + 0.1) == "Hello Count"
    assert e.model == "gpt-4o-mini-transcribe"
    assert e.client.audio.transcriptions.create.call_args.kwargs["language"] == "en"
