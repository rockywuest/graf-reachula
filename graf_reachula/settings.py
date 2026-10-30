"""User settings, stored on the robot and editable from the app's web page."""

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SETTINGS_PATH = Path(os.getenv("GRAF_REACHULA_SETTINGS", Path.home() / ".config" / "graf_reachula" / "settings.json"))

LANGUAGES = ("en", "de")

# Voices: free Microsoft Edge voices, or ElevenLabs with the user's own key
TTS_PROVIDERS = ("edge", "elevenlabs")
ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_MODEL = "eleven_flash_v2_5"     # low latency, speaks English and German
# ElevenLabs retires its default voices from time to time, so no voice ID is hard-coded:
# without a configured voice the Count picks the first of these names the account has
ELEVENLABS_VOICE_NAMES = ("Clyde", "Callum", "Adam", "George", "Daniel", "Brian")

# Chat providers. Everything except Anthropic speaks the OpenAI chat API,
# so one client covers them all with a different base URL.
LLM_PROVIDERS = {
    "anthropic": {"base_url": None, "model": "claude-opus-5-5", "env": "ANTHROPIC_API_KEY",
                  "official": ("https://api.anthropic.com",)},
    "openai": {"base_url": None, "model": "gpt-5.6-terra", "env": "OPENAI_API_KEY",
               "official": ("https://api.openai.com/v1",)},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model": "gemini-3.5-flash-lite", "env": "GEMINI_API_KEY"},
    "xai": {"base_url": "https://api.x.ai/v1", "model": "grok-4.20-0309-non-reasoning", "env": "XAI_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-opus-5.5",
                   "env": "OPENROUTER_API_KEY"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "model": "mistral-medium-latest",
                "env": "MISTRAL_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "qwen/qwen3.8-27b",
             "env": "GROQ_API_KEY"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "gemma3", "env": None},
    "custom": {"base_url": "", "model": "", "env": None},
}

# Speech-to-text providers: OpenAI-compatible /audio/transcriptions, plus xAI's own /stt
STT_PROVIDERS = {
    "xai": {"base_url": "https://api.x.ai/v1", "model": "", "env": "XAI_API_KEY"},
    "openai": {"base_url": None, "model": "gpt-transcribe", "env": "OPENAI_API_KEY",
               "official": ("https://api.openai.com/v1",)},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3-turbo",
             "env": "GROQ_API_KEY"},
    "elevenlabs": {"base_url": ELEVENLABS_URL, "model": "scribe_v2", "env": "ELEVENLABS_API_KEY"},
    "custom": {"base_url": "", "model": "gpt-transcribe", "env": None},
}


@dataclass
class Settings:
    language: str = "en"            # "en" or "de"
    scares: bool = True             # lurk and jump-scare people walking up
    ambient: bool = True            # spooky sounds now and then when it's quiet
    talk: bool = True               # talking Count (needs an LLM and a speech-to-text key)
    wake_word: bool = True          # only answer when called by name (parties are loud)

    llm_provider: str = "anthropic"
    llm_model: str = ""             # empty: provider default
    llm_api_key: str = ""           # empty: provider's environment variable
    llm_base_url: str = ""          # only for "custom" (or to override)

    stt_provider: str = "openai"
    stt_model: str = ""
    stt_api_key: str = ""           # empty: reuse the LLM key if it's the same provider
    stt_base_url: str = ""

    tts_provider: str = "edge"
    voice_en: str = "en-GB-RyanNeural"     # Edge voices
    voice_de: str = "de-DE-ConradNeural"
    elevenlabs_api_key: str = ""           # also used for ElevenLabs speech-to-text
    elevenlabs_voice: str = ""             # empty: the Count's default voice
    elevenlabs_model: str = ""

    # -- resolved values --------------------------------------------------

    @staticmethod
    def _env_key(preset: dict, base_url: str) -> str:
        # Keys from the environment only ever go to the provider's own endpoint,
        # never to a base URL someone typed into the settings page
        official = {preset["base_url"], *preset.get("official", ())}
        if not preset["env"] or (base_url and base_url.rstrip("/") not in {u.rstrip("/") for u in official if u}):
            return ""
        return os.getenv(preset["env"], "")

    def llm(self) -> dict:
        preset = LLM_PROVIDERS.get(self.llm_provider, LLM_PROVIDERS["custom"])
        return {
            "provider": self.llm_provider,
            "model": self.llm_model or preset["model"],
            "base_url": self.llm_base_url or preset["base_url"],
            "api_key": self.llm_api_key or self._env_key(preset, self.llm_base_url)
                       or ("ollama" if self.llm_provider == "ollama" else ""),
        }

    def stt(self) -> dict:
        preset = STT_PROVIDERS.get(self.stt_provider, STT_PROVIDERS["custom"])
        key = self.stt_api_key or self._env_key(preset, self.stt_base_url)
        same_endpoint = (self.stt_provider == self.llm_provider
                         and (self.stt_base_url or preset["base_url"]) == self.llm()["base_url"])
        if not key and same_endpoint:
            key = self.llm()["api_key"]
        if not key and self.stt_provider == "elevenlabs":
            key = self.elevenlabs_key()
        return {
            "provider": self.stt_provider,
            "model": self.stt_model or preset["model"],
            "base_url": self.stt_base_url or preset["base_url"],
            "api_key": key,
        }

    def elevenlabs_key(self) -> str:
        return self.elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY", "")

    def tts(self) -> dict:
        eleven = self.tts_provider == "elevenlabs" and bool(self.elevenlabs_key())
        return {
            "provider": "elevenlabs" if eleven else "edge",
            "api_key": self.elevenlabs_key() if eleven else "",
            "voice": self.elevenlabs_voice,      # empty: picked from the account's voices
            "model": self.elevenlabs_model or ELEVENLABS_MODEL,
            "edge_voice": self.voice_de if self.language == "de" else self.voice_en,
        }

    def can_talk(self) -> bool:
        return self.talk and bool(self.llm()["api_key"]) and bool(self.stt()["api_key"])

    # -- persistence --------------------------------------------------------

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(SETTINGS_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        settings = cls()
        settings.update(data)
        return settings

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        # API keys live in this file: create it readable by the owner only
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(asdict(self), indent=2))
        os.replace(tmp, SETTINGS_PATH)

    def public(self) -> dict:
        """Settings for the web page, with keys masked."""
        data = asdict(self)
        for name in ("llm_api_key", "stt_api_key", "elevenlabs_api_key"):
            key = data[name]
            data[name] = ("••••" + key[-4:] if len(key) > 12 else "••••") if key else ""
        data["can_talk"] = self.can_talk()
        data["llm_providers"] = list(LLM_PROVIDERS)
        data["stt_providers"] = list(STT_PROVIDERS)
        data["tts_providers"] = list(TTS_PROVIDERS)
        return data

    def update(self, changes: dict):
        known = {f.name: f for f in fields(self)}
        for side in ("llm", "stt"):
            # A key must never follow a request to a new endpoint: when the provider
            # or base URL changes and no new key comes along, the stored key is dropped
            key = changes.get(f"{side}_api_key", "")
            new_key = isinstance(key, str) and key and not key.startswith("••••")
            moved = any(name in changes and changes[name] != getattr(self, name)
                        for name in (f"{side}_provider", f"{side}_base_url"))
            if moved and not new_key:
                setattr(self, f"{side}_api_key", "")
        for name, value in changes.items():
            if name not in known:
                continue
            # The page sends masked keys back unchanged; keep the stored one
            if name.endswith("_api_key") and isinstance(value, str) and value.startswith("••••"):
                continue
            default = getattr(type(self), name, None)
            if isinstance(default, bool):
                value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "on", "yes")
            elif not isinstance(value, str):
                continue
            value = value.strip() if isinstance(value, str) else value
            if name == "language" and value not in LANGUAGES:
                continue
            if name == "llm_provider" and value not in LLM_PROVIDERS:
                continue
            if name == "stt_provider" and value not in STT_PROVIDERS:
                continue
            if name == "tts_provider" and value not in TTS_PROVIDERS:
                continue
            setattr(self, name, value)
