"""User settings, stored on the robot and editable from the app's web page."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SETTINGS_PATH = Path(os.getenv("GRAF_REACHULA_SETTINGS", Path.home() / ".config" / "graf_reachula" / "settings.json"))

# Chat providers. Everything except Anthropic speaks the OpenAI chat API,
# so one client covers them all with a different base URL.
LLM_PROVIDERS = {
    "anthropic": {"base_url": None, "model": "claude-opus-5-5", "env": "ANTHROPIC_API_KEY"},
    "openai": {"base_url": None, "model": "gpt-5-mini", "env": "OPENAI_API_KEY"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model": "gemini-2.5-flash", "env": "GEMINI_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-opus-5.5",
                   "env": "OPENROUTER_API_KEY"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "model": "mistral-medium-latest",
                "env": "MISTRAL_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile",
             "env": "GROQ_API_KEY"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3.2-vision", "env": None},
    "custom": {"base_url": "", "model": "", "env": None},
}

# Speech-to-text providers (OpenAI-compatible /audio/transcriptions)
STT_PROVIDERS = {
    "openai": {"base_url": None, "model": "gpt-4o-mini-transcribe", "env": "OPENAI_API_KEY"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3-turbo",
             "env": "GROQ_API_KEY"},
    "custom": {"base_url": "", "model": "whisper-1", "env": None},
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

    voice_en: str = "en-GB-RyanNeural"
    voice_de: str = "de-DE-ConradNeural"

    # -- resolved values --------------------------------------------------

    def llm(self) -> dict:
        preset = LLM_PROVIDERS.get(self.llm_provider, LLM_PROVIDERS["custom"])
        return {
            "provider": self.llm_provider,
            "model": self.llm_model or preset["model"],
            "base_url": self.llm_base_url or preset["base_url"],
            "api_key": self.llm_api_key or (os.getenv(preset["env"], "") if preset["env"] else "")
                       or ("ollama" if self.llm_provider == "ollama" else ""),
        }

    def stt(self) -> dict:
        preset = STT_PROVIDERS.get(self.stt_provider, STT_PROVIDERS["custom"])
        key = self.stt_api_key or (os.getenv(preset["env"], "") if preset["env"] else "")
        if not key and self.stt_provider == self.llm_provider:
            key = self.llm()["api_key"]
        return {
            "provider": self.stt_provider,
            "model": self.stt_model or preset["model"],
            "base_url": self.stt_base_url or preset["base_url"],
            "api_key": key,
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
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        # API keys live in this file
        os.chmod(tmp, 0o600)
        os.replace(tmp, SETTINGS_PATH)

    def public(self) -> dict:
        """Settings for the web page, with keys masked."""
        data = asdict(self)
        for name in ("llm_api_key", "stt_api_key"):
            data[name] = "••••" + data[name][-4:] if data[name] else ""
        data["can_talk"] = self.can_talk()
        data["llm_providers"] = list(LLM_PROVIDERS)
        data["stt_providers"] = list(STT_PROVIDERS)
        return data

    def update(self, changes: dict):
        known = {f.name: f for f in fields(self)}
        for name, value in changes.items():
            if name not in known:
                continue
            # The page sends masked keys back unchanged; keep the stored one
            if name.endswith("_api_key") and isinstance(value, str) and value.startswith("••••"):
                continue
            setattr(self, name, value)
