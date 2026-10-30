---
title: Count Reachula
emoji: 🧛
colorFrom: purple
colorTo: red
sdk: static
pinned: false
license: mit
short_description: "Spooky Reachy: a friendly vampire ghost who says BOO!"
tags:
 - reachy_mini
 - reachy_mini_python_app
 - halloween
 - spooky
 - kids
---

# 🧛 Count Reachula — Spooky Reachy for Halloween

[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97%20Space-Count%20Reachula-orange)](https://huggingface.co/spaces/RockyRocket/graf_reachula)
[![GitHub](https://img.shields.io/badge/GitHub-graf--reachula-black?logo=github)](https://github.com/rockywuest/graf-reachula)
![Reachy Mini app](https://img.shields.io/badge/Reachy%20Mini-app-purple)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

![Count Reachula — Spooky Reachy](assets/og.png)

**Install:** Reachy Mini Control → *Applications* → *Discover Apps* → **Count Reachula**

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
| 🧛 **Theatrical vampire voice** with your own ElevenLabs key (optional, falls back to Edge) | | ✅ |
| 🗣️ **Talking Count** — answers when called by name, sees costumes, tells stories, riddles, fortunes | | ✅ |

## Setup — pick your level

Everything beyond step 1 is optional. Each level adds to the one before.

### 1. Haunting — no key, nothing to set up

1. Open **Reachy Mini Control** → *Applications* → *Discover Apps*, install **Count Reachula** and start it.
2. The Count introduces himself and starts haunting: lurking, BOO!, spooky sounds and moves.
3. Open the app's page (`http://reachy-mini.local:8042` on a Wireless, `http://localhost:8042` on a Lite)
   to switch to German, test every sound and move, or trigger a scare by hand.

Tip: put him next to the candy bowl, where guests walk straight towards him: on a table, out of reach of small
hands, because his head moves. For toddlers, switch scares off on the app page.

### 2. Talking — one key (recommended: xAI)

The Count needs a **chat model that can see** (for the camera) and **speech-to-text**. The easiest way is one
[xAI](https://console.x.ai) key for both:

1. At [console.x.ai](https://console.x.ai): add a few dollars of credit and create an API key.
2. On the app's page, under **Talking Count**: chat provider `xai`, paste the key; speech-to-text provider `xai`
   (leave its key empty, it reuses the chat key). Click **Save**.
3. The status line should say *"The Count is listening"*. Call him by name: *"Count, what's my costume?"*

In our test runs (October 2026) the Count usually answered within a few seconds, and an answer with a photo cost
about 0.1 cent. Speed depends on your network and the model; check xAI's current prices.

Any other combination works too. Keys can also be set as environment variables:

| Chat provider | Default model | Key variable | Get a key |
|---|---|---|---|
| xAI (Grok) — fastest in our tests | `grok-4.20-0309-non-reasoning` | `XAI_API_KEY` | [console.x.ai](https://console.x.ai) |
| Anthropic (Claude) | `claude-opus-5-5` | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | `gpt-5.6-terra` | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| Google Gemini | `gemini-3.5-flash-lite` | `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/apikey) |
| OpenRouter | `anthropic/claude-opus-5.5` | `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai/keys) |
| Mistral | `mistral-medium-latest` | `MISTRAL_API_KEY` | [console.mistral.ai](https://console.mistral.ai) |
| Groq ⚠️ preview model, may be retired at short notice | `qwen/qwen3.8-27b` | `GROQ_API_KEY` | [console.groq.com](https://console.groq.com/keys) |
| Ollama (local, on your network) | `gemma3` | — | — |
| Custom (any OpenAI-compatible API) | your choice | — | — |

| Speech-to-text | Default model | Key variable |
|---|---|---|
| xAI (Grok) — biased towards the Count's names | — | `XAI_API_KEY` |
| OpenAI | `gpt-transcribe` (falls back to `gpt-4o-mini-transcribe` if rejected) | `OPENAI_API_KEY` |
| ElevenLabs Scribe — biased towards the Count's names | `scribe_v2` | `ELEVENLABS_API_KEY` |
| Groq (fast, generous free tier) | `whisper-large-v3-turbo` | `GROQ_API_KEY` |
| Custom (OpenAI-compatible `/audio/transcriptions`) | your choice | — |

Anthropic has no speech-to-text, so with Claude you need a second key for listening (for example xAI or Groq).

### 3. A real vampire voice — ElevenLabs (optional)

Out of the box the Count speaks with a free Microsoft Edge voice, made deeper and slower. With your own
[ElevenLabs](https://elevenlabs.io) key he gets a theatrical voice:

1. At [elevenlabs.io → API keys](https://elevenlabs.io/app/settings/api-keys), create a key with the permissions
   **Text to Speech** and **Voices: read** (the latter only if you leave the voice ID empty). Add **Speech to Text**
   if ElevenLabs should also listen; then choose **elevenlabs** under *Speech-to-text* (its key is reused).
   You still need a chat key.
2. On the app's page, under **Voice**: service `ElevenLabs`, paste the key, **Save voice**, then **Test the voice**.
3. Voice ID: leave it empty and the Count picks a deep narrator voice from your account, or paste any voice ID
   from your [voice library](https://elevenlabs.io/app/voice-library). For German parties a German voice sounds best.

The default model is `eleven_flash_v2_5` (fast, English and German). Every line uses your ElevenLabs characters;
repeated lines (intro, scare lines) are cached. If ElevenLabs fails (no credits, missing permission, offline), the
Count switches to the free voice for 5 minutes and the page shows why under *Current voice* (after the next
spoken line).

### Troubleshooting

| Problem | Fix |
|---|---|
| The Count doesn't answer | Call him by name ("Count, …", "Reachy, …"). The status line on the app's page shows speech-to-text or chat errors (for example a key without the right permission). |
| *"Add a chat key and a speech-to-text key"* | Talking needs both. With xAI, one key covers both. |
| *Current voice: … missing the permission …* | Edit the ElevenLabs key's permissions (see step 3), then **Save voice** again. |
| A default model stopped working | Providers rename models often: type a current model name in the *Model* field. |

Models without vision work too; the Count then just can't see.

### Before the party: set a settings PIN

Guests on your Wi-Fi can open the app's page too. Under **Settings PIN**, set a PIN (at least 6 characters) right
after installing: from then on, providers, keys and the voice can only be changed with it (sounds, moves and the
language stay open, so guests can play). Wrong guesses lock the settings for a while. Forgot the PIN? Over SSH on
the robot: `/venvs/apps_venv/bin/python -m graf_reachula.settings --reset-pin`. The page uses plain HTTP, so only
enter the PIN on a network you trust.
Saved keys are never shown on the page again, keys only ever go to their provider's official address, and a
stored key is dropped whenever the provider changes.

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

### Einrichtung in drei Stufen (Stufe 1 reicht zum Spuken, alles danach ist optional)

**1. Spuken, ohne Schlüssel:** In Reachy Mini Control unter *Applications → Discover Apps* **Count Reachula**
installieren und starten. Auf der App-Seite (`http://reachy-mini.local:8042`) die Sprache auf **Deutsch** stellen,
Geräusche und Bewegungen testen. Der Graf lauert, erschreckt mit „BUH!“ und macht Gruselgeräusche.

**2. Sprechen, mit einem Schlüssel (empfohlen: xAI):** Auf [console.x.ai](https://console.x.ai) etwas Guthaben
aufladen und einen API-Schlüssel anlegen. Auf der App-Seite unter **Talking Count** als Chat-Modell und als
Spracherkennung `xai` wählen, den Schlüssel einmal beim Chat-Modell eintragen, **Save**. Die Statuszeile zeigt
dann *„The Count is listening“* (die App-Seite ist englisch: die Felder heißen *Chat model* und *Speech-to-text*).
In unseren Tests (Oktober 2026) kostete eine Antwort mit Foto etwa 0,1 Cent; aktuelle Preise bitte prüfen. Andere Anbieter (Claude, OpenAI, Gemini,
OpenRouter, Mistral, Groq, Ollama, ElevenLabs Scribe) stehen in den Tabellen oben; Claude braucht für die
Spracherkennung einen zweiten Schlüssel.

**3. Echte Vampirstimme mit ElevenLabs (optional):** Unter [elevenlabs.io → API keys](https://elevenlabs.io/app/settings/api-keys)
einen Schlüssel mit den Berechtigungen **Text to Speech** und **Voices: read** anlegen (Letzteres nur, wenn die
Stimmen-ID leer bleibt). Für die Spracherkennung zusätzlich **Speech to Text** und unter *Speech-to-text*
**elevenlabs** wählen (der Schlüssel wird wiederverwendet); ein Chat-Schlüssel bleibt nötig. Auf der App-Seite unter **Voice** `ElevenLabs` wählen, Schlüssel eintragen,
**Save voice**, dann **Test the voice**. Ohne Stimmen-ID sucht der Graf selbst eine tiefe Stimme aus; für deutsche
Partys klingt eine deutsche Stimme aus eurer Stimmenbibliothek am besten. Fällt ElevenLabs aus, spricht er
5 Minuten mit der kostenlosen Stimme weiter, und die App-Seite zeigt den Grund. Die Schlüssel bleiben auf dem Roboter;
nach dem Speichern zeigt die Seite nur die letzten vier Zeichen.

**Der Graf antwortet nicht?** Beim Namen rufen („Graf, …“). Fehler der Spracherkennung oder des Chat-Modells
(etwa ein Schlüssel ohne passende Berechtigung) zeigt die Statuszeile auf der App-Seite.

Auf einer lauten Party antwortet der Graf nur, wenn man ihn ruft („Reachy“, „Graf“, „Count“). Auch Wörter wie
„reach“ oder „count“ können ihn wecken. 
**Vor der Party eine PIN setzen:** Gäste im WLAN können die App-Seite auch öffnen. Gleich nach der Installation unter
**Settings PIN** eine PIN mit mindestens 6 Zeichen festlegen; danach lassen sich Anbieter, Schlüssel und Stimme nur noch mit PIN ändern. Gespeicherte Schlüssel zeigt die
Seite nie wieder an, und sie gehen nur an die offizielle Adresse ihres Anbieters.

**Tipp:** Neben die Süßigkeitenschale stellen, auf einen Tisch, außer Reichweite kleiner Hände. Für Kleinkinder das
Erschrecken auf der App-Seite ausschalten.

**Datenschutz:** Mit eingeschalteter Sprachfunktion geht alles, was im Raum gesprochen wird, als Audio an die
Spracherkennung, nicht nur das, was an den Grafen gerichtet ist. Ein Kamerabild geht nur an das Chat-Modell, wenn er
antwortet. Ohne Schlüssel gehen nur die Texte seiner festen Sätze an den Online-Sprachdienst von Microsoft. Audio und
Bilder werden nicht gespeichert; das App-Log zeigt Fragen und Antworten. Der gewählte Anbieter bekommt Stimmen und
Fotos eurer Gäste; einige Anbieter verarbeiten Daten in den USA. Sagt euren Gästen, dass ein sprechender
Roboter mit Kamera auf der Party ist, bevor ihr die Sprachfunktion einschaltet.

---

If he haunted your party, a like on the [Space](https://huggingface.co/spaces/RockyRocket/graf_reachula) helps
other families find him. Source: [GitHub](https://github.com/rockywuest/graf-reachula).

Made with 🧛 by [FRECH & WUEST](https://frechundwuest.de) · MIT License

Community app, not an official Pollen Robotics or Hugging Face product. Reachy Mini is their trademark.
Community-App, kein offizielles Produkt von Pollen Robotics oder Hugging Face.
