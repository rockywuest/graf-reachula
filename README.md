---
title: Count Reachula
emoji: 🧛
colorFrom: purple
colorTo: red
sdk: static
pinned: false
license: mit
short_description: Spooky Reachy: a tiny ghost who says BOO! and tells tales
tags:
 - reachy_mini
 - reachy_mini_python_app
 - halloween
 - spooky
 - kids
---

# 🧛 Count Reachula — Spooky Reachy for Halloween

**Your Reachy Mini just became a vampire ghost.** Count Reachula, the friendly little ghost for your Halloween party,
lurks perfectly still, jumps up with a "BOO!" when someone walks by, fills the room with creaking
doors and howling wind — and, if you give him an AI key, he talks: he guesses costumes through his
camera, reads spooky futures and tells three-sentence ghost stories.

Spooky, but child-friendly: a startle now and then, never gore, nothing mean. Mostly giggles. Works in **English** and **German**.

*🇩🇪 Deutsche Version weiter unten.*

## What the Count does

| | Without any key | With an AI key |
|---|---|---|
| 👻 **Jump scares** — lurks head-down, then "BOO!" when someone steps in front of the camera, followed by a laugh | ✅ | ✅ |
| 🔊 **Spooky sounds** — heartbeat, ghost, creaking door, wind, church bells, laughter (synthesized, no audio files) | ✅ | ✅ |
| 💃 **Spooky moves** — trembling, a dramatic ghostly faint, a wobbly zap, a monster roar (from Pollen's emotion library) | ✅ | ✅ |
| 🎙️ **Intro and scare lines** in a deep vampire voice (Microsoft Edge online voices, no key, needs internet) | ✅ | ✅ |
| 🗣️ **Talking Count** — answers when called by name, sees costumes, tells stories, riddles, fortunes | | ✅ |

## Install

1. Open **Reachy Mini Control** → *Applications* → *Discover Apps* and install **Count Reachula**.
2. Start it. The Count introduces himself and starts haunting.
3. Open the app's page (`http://reachy-mini.local:8042` on a Wireless, `http://localhost:8042` on a Lite)
   to switch the language, test sounds and moves, or add keys.

Tip: put him next to the candy bowl, where guests walk straight towards him: on a table, out of reach of small
hands, because his head moves. For toddlers, switch scares off on the app page.

## Make him talk (optional): bring your own AI

The Count needs two things to talk: a **chat model that can see** (for the camera) and **speech-to-text**.
Enter the keys on the app's page; they are stored only on your robot (`~/.config/graf_reachula/settings.json`,
readable only by its owner). You can also set them as environment variables.

| Chat provider | Default model | Key variable |
|---|---|---|
| Anthropic (Claude) | `claude-opus-5-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-5.6-terra` | `OPENAI_API_KEY` |
| Google Gemini | `gemini-3.5-flash-lite` | `GEMINI_API_KEY` |
| OpenRouter | `anthropic/claude-opus-5.5` | `OPENROUTER_API_KEY` |
| Mistral | `mistral-medium-latest` | `MISTRAL_API_KEY` |
| Groq | `qwen/qwen3.8-27b` | `GROQ_API_KEY` |
| Ollama (local) | `gemma3` | — |
| Custom (any OpenAI-compatible API) | your choice | — |

| Speech-to-text | Default model | Key variable |
|---|---|---|
| OpenAI | `gpt-4o-mini-transcribe` | `OPENAI_API_KEY` |
| Groq (fast, generous free tier) | `whisper-large-v3-turbo` | `GROQ_API_KEY` |
| Custom (OpenAI-compatible `/audio/transcriptions`) | your choice | — |

Every model can be changed on the app's page; providers rename models often, so check their model list if a
default stops working. Models without vision work too; the Count then just can't see.

The settings page has no password: use it only on a network you trust. Keys are never shown again once saved,
and a stored key is dropped whenever the provider or base URL changes.

At a loud party the Count only answers when called by name ("Reachy", "Count", "Graf"), and for 25 seconds
after his last answer. Ordinary words like "reach" or "count" can wake him too. You can switch this off on the
app's page.

## Privacy

- With talking enabled, everything said in the room is sent as audio to your speech-to-text provider, not only
  what is said to the Count; his name only decides whether he answers. A camera photo goes to your chat provider
  only when he answers.
- Without keys, only the text of his fixed lines leaves the robot, to Microsoft's online Edge voice service.
- Audio and photos are not saved on the robot. The app log shows what the Count was asked and what he answered.
- Choosing a provider sends your guests' voices and photos to that company, some of them in the US.
  Tell your guests that a talking robot with a camera is at the party before you switch talking on.

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

Gruselig, aber kindgerecht: ab und zu ein kleiner Schreck, nie Blut, nichts Gemeines, meist nur Gekicher.

**So geht's:** In Reachy Mini Control unter *Applications → Discover Apps* **Count Reachula** installieren
und starten. Auf der App-Seite (`http://reachy-mini.local:8042`) die Sprache auf **Deutsch** stellen,
Geräusche und Bewegungen testen und optional Schlüssel eintragen.

**Ohne Schlüssel:** Erschrecken, Gruselgeräusche, Gruselbewegungen, Begrüßung mit Vampirstimme.
**Mit Schlüssel:** Der Graf spricht. Er braucht ein Chat-Modell mit Bildverständnis (Claude, OpenAI, Gemini,
OpenRouter, Mistral, Groq, Ollama oder jede OpenAI-kompatible Schnittstelle) und eine Spracherkennung
(OpenAI, Groq oder kompatibel). Die Schlüssel bleiben auf dem Roboter.

Auf einer lauten Party antwortet der Graf nur, wenn man ihn ruft („Reachy“, „Graf“, „Count“). Auch Wörter wie
„reach“ oder „count“ können ihn wecken. Die Einstellungsseite hat kein Passwort: nur in vertrauenswürdigen Netzen nutzen.

**Tipp:** Neben die Süßigkeitenschale stellen, auf einen Tisch, außer Reichweite kleiner Hände. Für Kleinkinder das
Erschrecken auf der App-Seite ausschalten.

**Datenschutz:** Mit eingeschalteter Sprachfunktion geht alles, was im Raum gesprochen wird, als Audio an die
Spracherkennung, nicht nur das, was an den Grafen gerichtet ist. Ein Kamerabild geht nur an das Chat-Modell, wenn er
antwortet. Ohne Schlüssel gehen nur die Texte seiner festen Sätze an den Online-Sprachdienst von Microsoft. Audio und
Bilder werden nicht gespeichert; das App-Log zeigt Fragen und Antworten. Sagt euren Gästen, dass ein sprechender
Roboter mit Kamera auf der Party ist, bevor ihr die Sprachfunktion einschaltet.

---

Made with 🧛 by [FRECH & WUEST](https://frechundwuest.de) · MIT License

Community app, not an official Pollen Robotics or Hugging Face product. Reachy Mini is their trademark.
Community-App, kein offizielles Produkt von Pollen Robotics oder Hugging Face.
