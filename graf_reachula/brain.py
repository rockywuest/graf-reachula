"""The Count's brain: any chat model that can look at a photo.

Anthropic is called through its own SDK; every other provider (OpenAI, Gemini,
OpenRouter, Mistral, Groq, Ollama, ...) through the OpenAI-compatible chat API.
"""

import logging
import re

log = logging.getLogger(__name__)

MAX_HISTORY = 12   # messages kept as context (6 exchanges)
# Only a guard against run-away replies: models that think (Claude, Gemini, ...) spend
# part of it on thinking, and a tight cap would leave no text. tidy() cuts the length.
MAX_REPLY_TOKENS = 1024
MAX_REPLY_CHARS = 320   # two spoken sentences; longer replies outlast the voice service's timeout

# Reasoning models may put their thinking into the reply text
THINKING = re.compile(r"<think>.*?(</think>|$)", re.IGNORECASE | re.DOTALL)
# Last line of defence for a children's party, on top of the system prompt:
# a reply with any of these is replaced by a fixed harmless line
# (Kept narrow: "Nacktschnecke", "the naked eye", "a sexton" or "sich totlachen" must pass.)
UNSAFE = re.compile(
    r"\b(sex|sexy|sexual\w*|sexuell\w*|porn\w*|nudes?|nackt(foto|bild|video)\w*|naked (photo|picture|pic)s?|"
    r"suicid\w*|selbstmord\w*|kill yourself|bring dich um|cocaine|kokain|heroin|drugs|drogen\w*|(ge)?kiff\w*|"
    r"nazi\w*|hitler|fuck\w*|shit|schei(ß|ss)\w*)\b",
    re.IGNORECASE,
)


def tidy(answer: str, safe_line: str) -> str:
    """Strip thinking, refuse unsafe content, keep the reply short enough to speak."""
    if not (answer or "").strip():
        return ""
    answer = THINKING.sub(" ", answer).strip()
    if not answer:
        return safe_line        # only thinking, no reply (e.g. cut off mid-thought)
    if UNSAFE.search(answer):
        log.warning("Unsafe reply replaced by the safe line")
        return safe_line
    if len(answer) > MAX_REPLY_CHARS:
        cut = answer[:MAX_REPLY_CHARS]
        answer = full_sentences(cut) if len(full_sentences(cut)) > 40 else cut.rsplit(" ", 1)[0] + "…"
        answer = re.sub(r"\[[^\]]*$", "", answer).strip()   # no half effect tag
    return answer


def full_sentences(text: str) -> str:
    """The text up to its last complete sentence ("" if there is none)."""
    end = max(text.rfind(". "), text.rfind("! "), text.rfind("? "))
    if text.rstrip()[-1:] in ".!?":
        end = len(text.rstrip()) - 1
    return text[:end + 1].strip() if end >= 0 else ""


class Brain:
    def __init__(self, llm: dict, system_prompt: str, safe_line: str = ""):
        self.provider = llm["provider"]
        self.model = llm["model"]
        self.system_prompt = system_prompt
        self.safe_line = safe_line
        self.history: list[tuple[str, str]] = []   # (role, text); photos are not kept
        self.vision = True
        self.photo_rejections = 0
        if self.provider == "anthropic":
            import anthropic

            kwargs = {"api_key": llm["api_key"], "timeout": 30.0, "max_retries": 1}
            if llm["base_url"]:
                kwargs["base_url"] = llm["base_url"]
            self.client = anthropic.Anthropic(**kwargs)
            self.effort = True
        else:
            import openai

            # OpenAI's reasoning models reject max_tokens, and max_completion_tokens would count
            # their thinking too (risking empty replies): no cap there, tidy() cuts the length
            self.cap_tokens = self.provider != "openai"

            self.client = openai.OpenAI(api_key=llm["api_key"], base_url=llm["base_url"] or None,
                                        timeout=30.0, max_retries=1)

    def reply(self, text: str, jpeg_b64: str | None) -> str:
        """Answer one transcribed utterance, looking at the current camera photo."""
        image = jpeg_b64 if self.vision else None
        try:
            answer = self._ask(text, image)
        except Exception as e:
            # Text-only models reject images with a 400; carry on without the camera.
            # Timeouts, rate limits and outages are not a reason to stop looking.
            if image is None or getattr(e, "status_code", None) not in (400, 404, 415, 422):
                raise
            self.photo_rejections += 1
            if self.photo_rejections >= 3:
                log.warning("Model keeps rejecting photos (%s); continuing without the camera", e)
                self.vision = False
            answer = self._ask(text, None)
        else:
            if image is not None:
                self.photo_rejections = 0
        answer = tidy(answer, self.safe_line)
        if answer:
            # An empty assistant turn would make later Anthropic calls fail
            self.history += [("user", text), ("assistant", answer)]
            self.history = self.history[-MAX_HISTORY:]
        return answer

    def _ask(self, text: str, image: str | None) -> str:
        if self.provider == "anthropic":
            return self._ask_anthropic(text, image)
        return self._ask_openai(text, image)

    def _ask_anthropic(self, text: str, image: str | None) -> str:
        content = []
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}})
        content.append({"type": "text", "text": text})
        messages = [{"role": r, "content": t} for r, t in self.history] + [{"role": "user", "content": content}]
        kwargs = {"model": self.model, "max_tokens": MAX_REPLY_TOKENS, "system": self.system_prompt, "messages": messages}
        if self.effort:
            # Low effort keeps spoken replies quick; models without the setting reject it
            kwargs["output_config"] = {"effort": "low"}
        try:
            response = self.client.messages.create(**kwargs)
        except Exception as e:
            if not self.effort or not any(w in str(e).lower() for w in ("effort", "output_config")):
                raise
            self.effort = False
            kwargs.pop("output_config")
            response = self.client.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            return ""
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "max_tokens":
            # Cut off mid-sentence: speak only what is complete
            text = full_sentences(text)
        return text

    def _ask_openai(self, text: str, image: str | None) -> str:
        if image:
            content = [{"type": "text", "text": text},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}]
        else:
            content = text
        messages = ([{"role": "system", "content": self.system_prompt}]
                    + [{"role": r, "content": t} for r, t in self.history]
                    + [{"role": "user", "content": content}])
        kwargs = {"model": self.model, "messages": messages}
        if self.cap_tokens:
            kwargs["max_tokens"] = MAX_REPLY_TOKENS
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            # Some models (OpenAI's reasoning models) reject max_tokens; tidy() still cuts the text
            if not self.cap_tokens or "max_tokens" not in str(e):
                raise
            self.cap_tokens = False
            kwargs.pop("max_tokens")
            response = self.client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()
