---
title: Count Reachula
emoji: 🧛
colorFrom: purple
colorTo: red
sdk: static
pinned: false
license: mit
short_description: Spooky Reachy - a friendly Halloween ghost for Reachy Mini
tags:
 - reachy_mini
 - reachy_mini_python_app
 - halloween
 - spooky
 - kids
---

# 🧛 Count Reachula — Spooky Reachy for Halloween

**Turn your Reachy Mini into Count Reachula, a friendly little vampire ghost for your Halloween party.**
He lurks perfectly still, jumps up with a "BOO!" when someone walks by, fills the room with creaking
doors and howling wind — and, if you give him an AI key, he talks: he guesses costumes through his
camera, reads spooky futures and tells three-sentence ghost stories.

Spooky, but child-friendly: no gore, no real fright, just giggles. Works in **English** and **German**.

*🇩🇪 Deutsche Version weiter unten.*

## What the Count does

| | Without any key | With an AI key |
|---|---|---|
| 👻 **Jump scares** — lurks head-down, then "BOO!" when someone steps in front of the camera, followed by a laugh | ✅ | ✅ |
| 🔊 **Spooky sounds** — heartbeat, ghost, creaking door, wind, church bells, laughter (synthesized, no audio files) | ✅ | ✅ |
| 💃 **Spooky moves** — trembling, dramatic ghostly death, electric shock, monster rage (from Pollen's emotion library) | ✅ | ✅ |
| 🎙️ **Intro and scare lines** in a deep vampire voice (free Microsoft Edge voices, needs internet) | ✅ | ✅ |
| 🗣️ **Talking Count** — answers when called by name, sees costumes, tells stories, riddles, fortunes | | ✅ |

## Install

1. Open **Reachy Mini Control** → *Applications* → *Discover Apps* and install **Count Reachula**.
2. Start it. The Count introduces himself and starts haunting.
3. Open the app's page (`http://reachy-mini.local:8042` on a Wireless, `http://localhost:8042` on a Lite)
   to switch the language, test sounds and moves, or add keys.

Tip: put him next to the candy bowl, where guests walk straight towards him.

## Make him talk (optional): bring your own AI

The Count needs two things to talk: a **chat model that can see** (for the camera) and **speech-to-text**.
Enter the keys on the app's page; they are stored only on your robot (`~/.config/graf_reachula/settings.json`,
readable only by its owner). You can also set them as environment variables.

| Chat provider | Default model | Key variable |
|---|---|---|
| Anthropic (Claude) | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-5-mini` | `OPENAI_API_KEY` |
| Google Gemini | `gemini-2.5-flash` | `GEMINI_API_KEY` |
| OpenRouter | `anthropic/claude-opus-5.5` | `OPENROUTER_API_KEY` |
| Mistral | `mistral-medium-latest` | `MISTRAL_API_KEY` |
| Groq | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| Ollama (local) | `llama3.2-vision` | — |
| Custom (any OpenAI-compatible API) | your choice | — |

| Speech-to-text | Default model | Key variable |
|---|---|---|
| OpenAI | `gpt-4o-mini-transcribe` | `OPENAI_API_KEY` |
| Groq (fast, generous free tier) | `whisper-large-v3-turbo` | `GROQ_API_KEY` |
| Custom (OpenAI-compatible `/audio/transcriptions`) | your choice | — |

Every model can be changed on the app's page. Models without vision work too; the Count then just can't see.

At a loud party the Count only answers when called by name ("Reachy", "Count", "Graf"), and for 25 seconds
after his last answer. You can switch that off on the app's page.

## Privacy

- With talking enabled, the Count sends what he hears (as audio to your speech-to-text provider) and a
  camera photo with each question (to your chat provider). Without keys, nothing leaves the robot except
  the text of his fixed lines for the voice.
- Nothing is recorded or stored on the robot.
- Tell your guests that a talking robot with a camera is at the party.

## Develop

```bash
pip install -e ".[dev]"
pytest                                  # no robot needed
python -m graf_reachula.main            # run against a robot (daemon running)
```

Built on the [Reachy Mini SDK](https://huggingface.co/docs/reachy_mini) by Pollen Robotics and Hugging Face.
Moves from [`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library).

---

## 🇩🇪 Graf Reachula — Spooky Reachy für Halloween

**Graf Reachula verwandelt deinen Reachy Mini in einen freundlichen kleinen Vampirgeist für eure Halloween-Party.**
Er lauert reglos, springt mit einem „BUH!“ hoch, wenn jemand vorbeikommt, lässt Türen knarren und den Wind
heulen — und mit einem KI-Schlüssel spricht er: Er errät Kostüme über seine Kamera, sagt eure gruselige
Zukunft voraus und erzählt Gruselgeschichten in drei Sätzen.

Gruselig, aber kindgerecht: kein Blut, kein echter Schrecken, nur Gekicher.

**So geht's:** In Reachy Mini Control unter *Applications → Discover Apps* **Count Reachula** installieren
und starten. Auf der App-Seite (`http://reachy-mini.local:8042`) die Sprache auf **Deutsch** stellen,
Geräusche und Bewegungen testen und optional Schlüssel eintragen.

**Ohne Schlüssel:** Erschrecken, Gruselgeräusche, Gruselbewegungen, Begrüßung mit Vampirstimme.
**Mit Schlüssel:** Der Graf spricht. Er braucht ein Chat-Modell mit Bildverständnis (Claude, OpenAI, Gemini,
OpenRouter, Mistral, Groq, Ollama oder jede OpenAI-kompatible Schnittstelle) und eine Spracherkennung
(OpenAI, Groq oder kompatibel). Die Schlüssel bleiben auf dem Roboter.

Auf einer lauten Party antwortet der Graf nur, wenn man ihn ruft („Reachy“, „Graf“, „Count“).

**Datenschutz:** Mit eingeschalteter Sprachfunktion gehen das Gehörte an die Spracherkennung und ein Kamerabild
pro Frage an das Chat-Modell. Es wird nichts aufgezeichnet. Sagt euren Gästen, dass ein sprechender Roboter
mit Kamera auf der Party ist.

---

Made with 🧛 by [FRECH & WUEST](https://frechundwuest.de) · MIT License
