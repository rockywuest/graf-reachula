"""The Count's brain: any chat model that can look at a photo.

Anthropic is called through its own SDK; every other provider (OpenAI, Gemini,
OpenRouter, Mistral, Groq, Ollama, ...) through the OpenAI-compatible chat API.
"""

import logging

log = logging.getLogger(__name__)

MAX_HISTORY = 12   # messages kept as context (6 exchanges)


class Brain:
    def __init__(self, llm: dict, system_prompt: str):
        self.provider = llm["provider"]
        self.model = llm["model"]
        self.system_prompt = system_prompt
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
        kwargs = {"model": self.model, "max_tokens": 1024, "system": self.system_prompt, "messages": messages}
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
        return " ".join(b.text for b in response.content if b.type == "text").strip()

    def _ask_openai(self, text: str, image: str | None) -> str:
        if image:
            content = [{"type": "text", "text": text},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}]
        else:
            content = text
        messages = ([{"role": "system", "content": self.system_prompt}]
                    + [{"role": r, "content": t} for r, t in self.history]
                    + [{"role": "user", "content": content}])
        response = self.client.chat.completions.create(model=self.model, messages=messages)
        return (response.choices[0].message.content or "").strip()
