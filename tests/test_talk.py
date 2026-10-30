import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from graf_reachula import talk
from graf_reachula.settings import Settings
from graf_reachula.talk import ADDRESSED, FOLLOW_UP, Talk, split_effects
from graf_reachula.texts import TEXTS, system_prompt


# -- split_effects ---------------------------------------------------------------

@pytest.mark.parametrize("reply, spoken, effects", [
    ("Boo! [scare] Hi there", "Boo! Hi there", [("scare", "")]),
    ("[sound:ghost] Woooo [move:Scared]", "Woooo", [("sound", "ghost"), ("move", "scared")]),
    ("[SOUND: Heartbeat ] Tick tock", "Tick tock", [("sound", "heartbeat")]),
    ("No tags at all", "No tags at all", []),
    ("*shudders* Hello [stage direction] there", "Hello there", []),
    ("  a \n\n b\t c  ", "a b c", []),
    ("Hi [sound:xyz]", "Hi", [("sound", "xyz")]),
])
def test_split_effects(reply, spoken, effects):
    assert split_effects(reply) == (spoken, effects)


def test_split_effects_keeps_effect_order():
    _, effects = split_effects("[move:dying] text [sound:bells] more [scare]")
    assert effects == [("move", "dying"), ("sound", "bells"), ("scare", "")]


def test_split_effects_does_not_glue_words_around_a_tag():
    assert split_effects("Hello[scare]there")[0] == "Hello there"


# -- ADDRESSED (wake names) ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Reachy, what time is it?", "Reach it", "Richie", "Ritschi", "Count, tell me a story",
    "Graf, hallo", "Reachula", "hey Dracula", "Rietschi bitte",
])
def test_addressed_matches_name_variants(text):
    assert ADDRESSED.search(text)


@pytest.mark.parametrize("text", [
    "Richtig gut", "Wo ist das Klo", "Rechnung bitte", "I counted to ten", "reicht schon", "erreicht",
    "Wie spät ist es", "Ich bin müde", "Kritisch betrachtet", "Reiche Leute",
])
def test_addressed_ignores_ordinary_sentences(text):
    assert not ADDRESSED.search(text)


# -- Talk.handle (orchestration with fakes; no Ears, no Brain network) ---------------

def make_talk(robot, stage, wake_word=True):
    t = Talk.__new__(Talk)
    t.robot = robot
    t.stage = stage
    t.settings = Settings(wake_word=wake_word, language="en")
    t.voice = MagicMock()
    t.voice.texts = {"error": "ERROR LINE"}
    t.haunt = SimpleNamespace(conversation_active=threading.Event(), jump_scare=MagicMock())
    t.brain = MagicMock()
    t.brain.reply.return_value = "Hello [sound:ghost] friend"
    t.last_reply = 0.0
    t.stop_event = threading.Event()
    return t


def test_unaddressed_speech_is_ignored(robot, stage):
    t = make_talk(robot, stage)
    t.handle("Richtig gut")
    t.brain.reply.assert_not_called()
    t.voice.assert_not_called()


def test_addressed_speech_is_answered_with_voice_and_effects(robot, stage):
    t = make_talk(robot, stage)
    t.handle("Reachy, hello")
    t.brain.reply.assert_called_once_with("Reachy, hello", None)
    t.voice.assert_called_once_with("Hello friend")
    assert ("sound", "ghost") in stage.calls
    assert not t.haunt.conversation_active.is_set()


def test_follow_up_within_window_needs_no_name(robot, stage):
    t = make_talk(robot, stage)
    t.handle("Reachy, hello")
    t.handle("how old is this house")
    assert t.brain.reply.call_count == 2


def test_follow_up_after_window_needs_the_name_again(robot, stage):
    t = make_talk(robot, stage)
    t.handle("Reachy, hello")
    t.last_reply -= FOLLOW_UP + 5
    t.handle("how old is this house")
    assert t.brain.reply.call_count == 1


def test_wake_word_off_answers_everything(robot, stage):
    t = make_talk(robot, stage, wake_word=False)
    t.handle("Richtig gut")
    t.brain.reply.assert_called_once()


def test_reply_is_dropped_when_the_app_stopped_while_thinking(robot, stage):
    t = make_talk(robot, stage)
    t.brain.reply.side_effect = lambda *a: (t.stop_event.set(), "Late answer")[1]
    t.handle("Reachy, hello")
    t.voice.assert_not_called()
    assert stage.calls == []


def test_scare_tag_triggers_haunt_jump(robot, stage):
    t = make_talk(robot, stage)
    t.brain.reply.return_value = "Boo [scare]"
    t.handle("Count, scare me")
    t.haunt.jump_scare.assert_called_once()
    t.voice.assert_called_once_with("Boo")


def test_llm_failure_speaks_error_line_and_clears_conversation_flag(robot, stage):
    t = make_talk(robot, stage)
    t.brain.reply.side_effect = RuntimeError("provider down")
    t.handle("Reachy, hello")
    t.voice.assert_called_once_with("ERROR LINE")
    assert ("sound", "ghost") not in stage.calls
    assert not t.haunt.conversation_active.is_set()


def test_frame_as_jpeg_b64_returns_none_without_camera_frame(robot):
    assert talk.frame_as_jpeg_b64(robot) is None


def test_frame_as_jpeg_b64_encodes_and_downscales(jpeg_frame):
    import base64

    from graf_reachula.talk import frame_as_jpeg_b64

    encoded = frame_as_jpeg_b64(SimpleNamespace(media=SimpleNamespace(get_frame=lambda: jpeg_frame)))
    raw = base64.b64decode(encoded)
    assert raw[:2] == b"\xff\xd8"  # JPEG start-of-image


# -- texts ----------------------------------------------------------------------------

def test_both_languages_define_the_same_text_keys():
    assert set(TEXTS["en"]) == set(TEXTS["de"])


def test_system_prompt_includes_language_rule_and_tags():
    en = system_prompt("en")
    de = system_prompt("de")
    assert "[sound:NAME]" in en and "[scare]" in en
    assert TEXTS["de"]["persona"] in de
    assert "{language_rule}" not in en
