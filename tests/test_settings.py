import json
import os
import stat
import subprocess
import sys

import pytest

from graf_reachula import settings as settings_mod
from graf_reachula.settings import LLM_PROVIDERS, STT_PROVIDERS, Settings


def test_defaults():
    s = Settings()
    assert s.language == "en"
    assert s.scares and s.ambient and s.talk and s.wake_word
    assert s.llm_provider == "anthropic"
    assert s.stt_provider == "openai"
    assert s.voice_en == "en-GB-RyanNeural"
    assert s.voice_de == "de-DE-ConradNeural"


@pytest.mark.parametrize("provider", [p for p in LLM_PROVIDERS if LLM_PROVIDERS[p]["env"]])
def test_llm_preset_resolves_model_url_and_env_key(provider, monkeypatch):
    preset = LLM_PROVIDERS[provider]
    monkeypatch.setenv(preset["env"], "env-secret-key")
    resolved = Settings(llm_provider=provider).llm()
    assert resolved["provider"] == provider
    assert resolved["model"] == preset["model"]
    assert resolved["base_url"] == preset["base_url"]
    assert resolved["api_key"] == "env-secret-key"


def test_ollama_needs_no_key_and_uses_local_url():
    resolved = Settings(llm_provider="ollama").llm()
    assert resolved["api_key"] == "ollama"
    assert resolved["base_url"] == "http://localhost:11434/v1"


def test_explicit_model_and_key_override_preset(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    resolved = Settings(llm_provider="groq", llm_model="my-model", llm_api_key="typed-key").llm()
    assert resolved["model"] == "my-model"
    assert resolved["api_key"] == "typed-key"


def test_no_key_anywhere_means_empty_key_and_cannot_talk():
    s = Settings()
    assert s.llm()["api_key"] == ""
    assert s.can_talk() is False


def test_stt_reuses_llm_key_for_same_provider_and_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env")
    s = Settings(llm_provider="openai")
    assert s.stt()["api_key"] == "openai-env"
    assert s.stt()["model"] == STT_PROVIDERS["openai"]["model"]


def test_stt_reuses_typed_llm_key_when_same_provider():
    s = Settings(llm_provider="openai", llm_api_key="typed-openai")
    assert s.stt()["api_key"] == "typed-openai"


def test_stt_does_not_reuse_key_of_a_different_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-env")
    s = Settings(llm_provider="anthropic", stt_provider="openai")
    assert s.llm()["api_key"] == "anthropic-env"
    assert s.stt()["api_key"] == ""
    assert s.can_talk() is False


def test_stt_uses_its_own_env_key_for_other_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-env")
    monkeypatch.setenv("GROQ_API_KEY", "groq-env")
    s = Settings(llm_provider="anthropic", stt_provider="groq")
    assert s.stt()["api_key"] == "groq-env"
    assert s.stt()["base_url"] == STT_PROVIDERS["groq"]["base_url"]
    assert s.can_talk() is True


def test_can_talk_needs_talk_flag_and_both_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert Settings().can_talk() is True
    assert Settings(talk=False).can_talk() is False


def test_proxy_base_url_does_not_receive_env_key(monkeypatch):
    # The env key must only go to the provider's own endpoint
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-env")
    s = Settings(llm_provider="openrouter", llm_base_url="https://evil.example/v1")
    assert s.llm()["api_key"] == ""


def test_explicit_official_openai_url_still_gets_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env")
    s = Settings(llm_provider="openai", llm_base_url="https://api.openai.com/v1")
    assert s.llm()["api_key"] == "openai-env"


def test_env_var_read_from_settings_path_at_import(tmp_path):
    target = tmp_path / "custom.json"
    env = dict(os.environ, GRAF_REACHULA_SETTINGS=str(target))
    out = subprocess.run(
        [sys.executable, "-c", "from graf_reachula import settings; print(settings.SETTINGS_PATH)"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == str(target)


def test_save_load_round_trip_with_private_mode():
    s = Settings(language="de", llm_provider="gemini", llm_api_key="sk-round-trip-1234", stt_base_url="https://x/v1")
    s.save()
    path = settings_mod.SETTINGS_PATH
    assert path.exists()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert not path.with_suffix(".tmp").exists()
    assert Settings.load() == s


def test_load_missing_file_gives_defaults():
    assert Settings.load() == Settings()


def test_load_corrupt_file_gives_defaults():
    settings_mod.SETTINGS_PATH.write_text("{not json")
    assert Settings.load() == Settings()


def test_load_ignores_unknown_fields():
    settings_mod.SETTINGS_PATH.write_text(json.dumps({"language": "de", "from_the_future": 1}))
    loaded = Settings.load()
    assert loaded.language == "de"
    assert not hasattr(loaded, "from_the_future")


def test_public_masks_keys_and_reports_capabilities(monkeypatch):
    s = Settings(llm_api_key="sk-live-ABCD1234", stt_api_key="")
    data = s.public()
    assert data["llm_api_key"] == "••••1234"
    assert data["stt_api_key"] == ""
    assert "sk-live" not in json.dumps(data)
    assert data["can_talk"] is False
    assert data["llm_providers"] == list(LLM_PROVIDERS)
    assert data["stt_providers"] == list(STT_PROVIDERS)


def test_update_ignores_masked_keys():
    s = Settings(llm_api_key="sk-real-1234")
    s.update({"llm_api_key": "••••1234"})
    assert s.llm_api_key == "sk-real-1234"


def test_update_ignores_unknown_fields():
    s = Settings()
    s.update({"bogus": "x", "can_talk": True, "llm_providers": ["evil"]})
    assert not hasattr(s, "bogus")
    assert "can_talk" not in vars(s)
    assert "llm_providers" not in vars(s)


def test_update_coerces_boolean_fields():
    s = Settings()
    s.update({"scares": "false", "ambient": "true"})
    assert s.scares is False
    assert s.ambient is True


def test_update_sets_new_key_and_strings():
    s = Settings()
    s.update({"llm_api_key": "sk-new-9999", "language": "de"})
    assert s.llm_api_key == "sk-new-9999"
    assert s.language == "de"


def test_changing_provider_drops_old_key():
    s = Settings(llm_provider="openai", llm_api_key="openai-secret")
    s.update({"llm_provider": "gemini"})
    assert s.llm_api_key == ""


def test_changing_provider_with_new_key_keeps_new_key():
    s = Settings(llm_provider="openai", llm_api_key="openai-secret")
    s.update({"llm_provider": "gemini", "llm_api_key": "gemini-secret"})
    assert s.llm_api_key == "gemini-secret"


def test_changing_base_url_does_not_carry_key_to_new_endpoint():
    s = Settings(llm_provider="openrouter", llm_api_key="or-secret")
    s.update({"llm_base_url": "https://evil.example/v1", "llm_api_key": "••••cret"})
    assert s.llm_api_key == ""


def test_unchanged_provider_keeps_key_when_masked_key_sent_back():
    s = Settings(llm_provider="openai", llm_api_key="openai-secret")
    s.update({"llm_provider": "openai", "llm_api_key": "••••cret"})
    assert s.llm_api_key == "openai-secret"


def test_public_does_not_reveal_short_keys():
    data = Settings(llm_api_key="abc").public()
    assert "abc" not in data["llm_api_key"]


def test_xai_key_covers_chat_and_speech(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-env")
    s = Settings(llm_provider="xai", stt_provider="xai")
    assert s.llm()["base_url"] == "https://api.x.ai/v1"
    assert s.llm()["api_key"] == "xai-env"
    assert s.stt()["api_key"] == "xai-env"
    assert s.can_talk()
