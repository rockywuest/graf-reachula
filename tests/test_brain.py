from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from graf_reachula.brain import MAX_HISTORY, Brain

ANTHROPIC = {"provider": "anthropic", "model": "claude-test", "base_url": None, "api_key": "test-key"}
OPENAI = {"provider": "openai", "model": "gpt-test", "base_url": None, "api_key": "test-key"}
SYSTEM = "SYSTEM PROMPT"


class ApiError(Exception):
    """An SDK-style error that carries an HTTP status, as the real clients do."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def anthropic_response(text="Boo!", stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def openai_response(text="Boo!"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def anthropic_brain(responses):
    brain = Brain(ANTHROPIC, SYSTEM)
    brain.client = MagicMock()
    brain.client.messages.create.side_effect = responses
    return brain


def openai_brain(responses):
    brain = Brain(OPENAI, SYSTEM)
    brain.client = MagicMock()
    brain.client.chat.completions.create.side_effect = responses
    return brain


# -- Anthropic message shape ------------------------------------------------------------

def test_anthropic_message_has_image_block_first_then_text():
    brain = anthropic_brain([anthropic_response("Nice cape!")])
    assert brain.reply("what do you see", "AAAA") == "Nice cape!"
    kwargs = brain.client.messages.create.call_args.kwargs
    assert kwargs["system"] == SYSTEM
    assert kwargs["model"] == "claude-test"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["output_config"] == {"effort": "low"}
    content = kwargs["messages"][-1]
    assert content["role"] == "user"
    assert [block["type"] for block in content["content"]] == ["image", "text"]
    image = content["content"][0]["source"]
    assert image == {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}
    assert content["content"][1]["text"] == "what do you see"


def test_anthropic_without_photo_sends_text_only():
    brain = anthropic_brain([anthropic_response()])
    brain.reply("hello", None)
    content = brain.client.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert [block["type"] for block in content] == ["text"]


def test_anthropic_joins_text_blocks_and_skips_others():
    response = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="thinking", thinking="..."),
        SimpleNamespace(type="text", text="One."),
        SimpleNamespace(type="text", text="Two."),
    ])
    assert anthropic_brain([response]).reply("hi", None) == "One. Two."


def test_anthropic_refusal_returns_empty_reply():
    brain = anthropic_brain([anthropic_response("ignored", stop="refusal")])
    assert brain.reply("hi", None) == ""


# -- history --------------------------------------------------------------------------------

def test_history_is_trimmed_to_last_exchanges():
    brain = anthropic_brain([anthropic_response(f"answer {i}") for i in range(10)])
    for i in range(10):
        brain.reply(f"question {i}", None)
    assert len(brain.history) == MAX_HISTORY
    last_messages = brain.client.messages.create.call_args.kwargs["messages"]
    # previous 12 history entries plus the new user turn
    assert len(last_messages) == MAX_HISTORY + 1
    assert last_messages[0]["role"] == "user"
    # the 10th request was sent with the 12 entries kept after exchange 8: questions 3..8
    assert last_messages[0]["content"] == "question 3"


def test_failed_call_is_not_stored_in_history():
    brain = anthropic_brain([RuntimeError("boom")])
    with pytest.raises(RuntimeError):
        brain.reply("hi", None)
    assert brain.history == []


def test_refusal_does_not_poison_history_with_empty_assistant_turn():
    # An empty assistant turn would make the next Anthropic request fail
    brain = anthropic_brain([anthropic_response("", stop="refusal"), anthropic_response("Again!")])
    brain.reply("first", None)
    brain.reply("second", None)
    sent = brain.client.messages.create.call_args.kwargs["messages"]
    assert all(m["content"] for m in sent[:-1])


# -- effort retry ---------------------------------------------------------------------------

def test_effort_setting_is_dropped_when_model_rejects_it():
    brain = anthropic_brain([
        Exception("invalid request: output_config.effort is not supported for this model"),
        anthropic_response("Hello"),
    ])
    assert brain.reply("hi", None) == "Hello"
    calls = brain.client.messages.create.call_args_list
    assert "output_config" in calls[0].kwargs
    assert "output_config" not in calls[1].kwargs
    assert brain.effort is False

    brain.client.messages.create.side_effect = [anthropic_response("Again")]
    brain.reply("hi again", None)
    assert "output_config" not in brain.client.messages.create.call_args.kwargs


def test_unrelated_errors_are_not_retried_as_effort_errors():
    brain = anthropic_brain([RuntimeError("rate limited")])
    with pytest.raises(RuntimeError, match="rate limited"):
        brain.reply("hi", None)
    assert brain.effort is True
    assert brain.client.messages.create.call_count == 1


# -- vision fallback -----------------------------------------------------------------------

@pytest.mark.parametrize("status", [400, 404, 415, 422])
def test_vision_fallback_retries_without_photo_and_remembers_it(status):
    brain = anthropic_brain([
        ApiError("this model does not accept image input", status),
        anthropic_response("Text only then"),
        anthropic_response("Still text"),
    ])
    assert brain.reply("look", "AAAA") == "Text only then"
    assert brain.vision is False
    first, second = brain.client.messages.create.call_args_list[:2]
    assert any(b["type"] == "image" for b in first.kwargs["messages"][-1]["content"])
    assert all(b["type"] == "text" for b in second.kwargs["messages"][-1]["content"])

    brain.reply("look again", "AAAA")
    last = brain.client.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert all(b["type"] == "text" for b in last)


def test_vision_fallback_failing_text_retry_propagates():
    brain = anthropic_brain([ApiError("no images", 400), Exception("server down")])
    with pytest.raises(Exception, match="server down"):
        brain.reply("look", "AAAA")


def test_transient_error_with_photo_does_not_disable_vision():
    # Rate limits and timeouts are not a reason to stop looking
    brain = anthropic_brain([ApiError("rate limited", 429), anthropic_response("Hi")])
    with pytest.raises(ApiError):
        brain.reply("look", "AAAA")
    assert brain.vision is True
    assert brain.reply("look again", "AAAA") == "Hi"
    content = brain.client.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert content[0]["type"] == "image"


# -- OpenAI-compatible shape --------------------------------------------------------------

def test_openai_message_has_data_url_image_after_text():
    brain = openai_brain([openai_response("Cute ghost")])
    assert brain.reply("guess my costume", "AAAA") == "Cute ghost"
    messages = brain.client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": SYSTEM}
    user = messages[-1]
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text", "text": "guess my costume"}
    assert user["content"][1] == {"type": "image_url",
                                  "image_url": {"url": "data:image/jpeg;base64,AAAA"}}


def test_openai_text_only_uses_plain_string_content():
    brain = openai_brain([openai_response("Hi")])
    brain.reply("hello", None)
    messages = brain.client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[-1] == {"role": "user", "content": "hello"}


def test_openai_history_is_sent_back_in_order():
    brain = openai_brain([openai_response("one"), openai_response("two")])
    brain.reply("first", None)
    brain.reply("second", None)
    messages = brain.client.chat.completions.create.call_args.kwargs["messages"]
    assert [m["content"] for m in messages[1:]] == ["first", "one", "second"]


def test_openai_vision_fallback_on_text_only_model():
    brain = openai_brain([ApiError("model does not support image_url", 400), openai_response("Text")])
    assert brain.reply("hi", "AAAA") == "Text"
    assert brain.vision is False


def test_openai_empty_content_becomes_empty_string():
    brain = openai_brain([SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))])])
    assert brain.reply("hi", None) == ""
