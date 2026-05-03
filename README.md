<div align="center">

<br/>

<img src="assets/animations/bubbles/icon.png" alt="KIBO" width="250" />

# KIBO

### A desktop companion that lives on your screen, reacts to what you're doing, and remembers you.

<br/>

[![Stars](https://img.shields.io/github/stars/yash-dev007/KIBO?style=flat-square&color=FFD700&labelColor=1a1a1a)](https://github.com/yash-dev007/KIBO/stargazers)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square&labelColor=1a1a1a)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=1a1a1a)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&labelColor=1a1a1a)](https://doc.qt.io/qtforpython/)
[![LLM: Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20Ollama-F54F29?style=flat-square&labelColor=1a1a1a)](https://console.groq.com)
[![Tests](https://img.shields.io/badge/tests-185%20passing-brightgreen?style=flat-square&labelColor=1a1a1a)]()

<br/>

> **KIBO is not a chatbot widget. It's a frameless, transparent animated character that sits on your desktop, listens for your voice, responds with neural TTS, and builds persistent long-term memory — all running locally.**

<br/>

</div>

---

## What makes KIBO different

| | KIBO | Typical AI widget |
|---|---|---|
| **Latency** | ~1.2 s voice round-trip | 3–8 s |
| **TTS** | Piper neural (streaming, sentence-level) | pyttsx3 / browser |
| **Memory** | Vector RAG (sqlite-vec + bge-small) | Session-only |
| **Rendering** | VP9 alpha WebM via WMF — zero CPU overhead | PNG sequences or browser canvas |
| **Privacy** | Fully local (Groq is opt-in cloud) | Cloud-dependent |
| **Footprint** | < 2 % CPU at idle | — |
| **Proactivity** | Policy-gated with daily cap, quiet hours, snooze | Push-only |
| **Onboarding** | Guided first-run wizard with live provider health checks | Manual config file |

---

## Features

### Voice & AI

- **Push-to-talk** (`Ctrl+K`) with faster-whisper `base.en` + silero-vad endpointing
- **Streaming sentence → TTS pipeline** — Piper neural audio starts playing while the LLM is still generating
- **Groq cloud LLM** (`llama-3.3-70b-versatile`, ~6 000 tok/s free tier) with automatic Ollama fallback
- **Inline memory extraction** — the LLM emits `remember` tool calls mid-stream; malformed tool JSON is suppressed so memory writes never leak into chat bubbles
- **Personality contract** — KIBO's character, tone, and safety constraints are versioned and injected via `PromptBuilder` on every conversation

### Long-term Memory

- **Vector RAG** via sqlite-vec + fastembed (bge-small-en-v1.5, ~30 MB). Semantic kNN — *"what's my favourite drink?"* finds *"user likes espresso"* without keyword overlap.
- **Obsidian-compatible vault** — every fact is also written to `~/.kibo/vault/memories/*.md`
- **One-click clear** from the Settings window
- **Index-safe cleanup** — clearing memory and retention-cap evictions also purge provider indexes
- Migration: existing vault Markdown files are re-embedded on first run, no data lost

### Animation Engine

- **VP9 alpha WebM** playback via Windows Media Foundation — zero CPU overhead, native hardware transparency
- **Multi-skin support** with `skales`, `capy`, and `bubbles` animation folders
- **State machine** — IDLE, THINKING, TALKING, ACTING, HAPPY with smooth transitions and random action animations during idle time

### First-run Onboarding

- **4-page guided wizard** launches automatically on first start
- Page 1 — Welcome: introduces KIBO's capabilities and data model
- Page 2 — Provider: choose Groq cloud, Ollama local, or Mock demo mode; live connection test runs `provider_health` checks before you leave the page
- Page 3 — Privacy: explicit opt-in checkboxes for memory and proactive features; shows the `~/.kibo` data path
- Page 4 — Finish: confirms setup; explains tray access
- Choices are persisted to `config.json`; `first_run_completed` is set to `True` on exit

### Proactivity Engine v1

KIBO initiates conversation only when it has earned the right. Every proactive message passes through a structured policy layer before reaching you.

**Delivery rules:**
- Maximum **4 low-priority utterances per calendar day**
- Minimum **45 minutes between low-priority utterances**
- **Quiet hours** (default 22:00–07:00) block all non-explicit messages
- **Explicit reminders** bypass the daily cap and quiet hours (unless marked normal)

**Trigger set:**
| Trigger | Condition | Priority |
|---|---|---|
| Morning greeting | Once after 08:00, app open ≥ 2 min | Low |
| Idle check-in | No KIBO interaction for 60 min | Low |
| End-of-day note | 17:00–20:00, ≥ 1 task completed | Low |
| Battery low | Below 20 % (once per discharge window) | Medium |
| CPU stress | CPU > 90 % (5-min cooldown) | Medium |
| Meeting reminder | Next event ≤ 30 min away | High |

**User controls (two clicks from the tray):**
- **Snooze 1 hour** — silences all proactive output until the timer expires
- **Disable proactivity** — turns off all ambient interruptions immediately
- Per-category toggles in Settings → Notifications

### Clip Mode

- **`Ctrl+Alt+K`** — saves the last 5 seconds of animation as an animated WebP to `~/.kibo/clips/`
- Ring buffer runs passively; zero overhead when not saving

### System Awareness (opt-in)

- Reacts to CPU load, battery level, and idle time
- Google Calendar integration for meeting reminders
- All notification categories are individually togglable

---

## Quick start

### 1. Clone and install

KIBO uses [uv](https://github.com/astral-sh/uv) for fast, reproducible installs.

```bash
git clone https://github.com/yash-dev007/KIBO.git
cd KIBO

# Install uv if you don't have it
pip install uv

# Install all dependencies
uv sync
```

> Prefer plain pip? `pip install -r requirements.txt` still works.

### 2. Get a free Groq API key *(optional — KIBO runs fully local without one)*

Sign up at [console.groq.com](https://console.groq.com) — free tier, no credit card required.

```powershell
# Windows (PowerShell)
$env:GROQ_API_KEY = "gsk_..."
```

```bash
# macOS / Linux
export GROQ_API_KEY="gsk_..."
```

> **No key?** KIBO falls back to Ollama automatically. Run `ollama pull llama3.2:3b` first.

### 3. Download a Piper voice model *(optional — ~30 MB one-time)*

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path models/piper
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx" -OutFile "models/piper/en_US-amy-medium.onnx"
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json" -OutFile "models/piper/en_US-amy-medium.onnx.json"
```

```bash
# macOS / Linux
mkdir -p models/piper
curl -L -o models/piper/en_US-amy-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
curl -L -o models/piper/en_US-amy-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
```

> **No Piper model?** Falls back to pyttsx3 automatically. Nothing breaks.

### 4. *(Optional)* Better voice endpointing

```bash
pip install torch torchaudio   # enables silero-vad end-of-speech detection
```

### 5. Run

```bash
uv run python main.py
```

The **first-run onboarding wizard** will guide you through provider selection and privacy consent before the pet appears.

---

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+K` | Push-to-talk |
| `Ctrl+Alt+K` | Save last 5-second clip to `~/.kibo/clips/` |

Right-click the pet or the tray icon for Settings, Snooze, and Quit.

---

## Configuration

All settings live in `config.json` at the project root. Unknown keys are accepted with a warning so hand-edited configs don't break on upgrades.

### Core

| Key | Default | Description |
|---|---|---|
| `pet_name` | `"KIBO"` | Name shown in the window title |
| `buddy_skin` | `"skales"` | Animation asset folder under `assets/animations/` |
| `activation_hotkey` | `"ctrl+k"` | Push-to-talk hotkey |
| `clip_hotkey` | `"ctrl+alt+k"` | Clip save hotkey |

### LLM

| Key | Default | Description |
|---|---|---|
| `llm_provider` | `"auto"` | `"auto"`, `"groq"`, or `"ollama"` |
| `groq_model` | `"llama-3.3-70b-versatile"` | Groq model ID |
| `groq_api_key_env` | `"GROQ_API_KEY"` | Environment variable name for the Groq key |
| `ollama_model` | `"qwen2.5-coder:7b"` | Ollama model to pull and use |
| `ollama_base_url` | `"http://localhost:11434"` | Ollama server URL |

### TTS & STT

| Key | Default | Description |
|---|---|---|
| `tts_provider` | `"auto"` | `"auto"`, `"piper"`, or `"pyttsx3"` |
| `piper_model` | `"en_US-amy-medium"` | Piper voice model name |
| `piper_models_dir` | `"models/piper"` | Directory containing `.onnx` + `.json` model files |
| `stt_model` | `"base.en"` | Whisper model size |
| `stt_use_vad` | `true` | Enable silero-vad endpointing |

### Memory

| Key | Default | Description |
|---|---|---|
| `memory_provider` | `"auto"` | `"auto"`, `"vector"`, or `"lexical"` |
| `memory_enabled` | `true` | Persist and retrieve long-term facts |
| `memory_extraction_inline` | `true` | Extract memories via LLM tool calls mid-stream |
| `memory_max_facts` | `200` | Retention cap; oldest facts evicted first |
| `memory_top_k` | `5` | Number of recalled facts injected per turn |

### Proactivity

| Key | Default | Description |
|---|---|---|
| `proactive_enabled` | `true` | Master switch for all proactive messages |
| `quiet_hours_start` | `22` | Hour (0–23) when quiet mode begins |
| `quiet_hours_end` | `7` | Hour (0–23) when quiet mode ends |
| `notification_types` | *(all true)* | Per-category on/off switches |
| `calendar_provider` | `"none"` | `"google"` to enable Calendar sync |

### Personality & Onboarding

| Key | Default | Description |
|---|---|---|
| `personality_version` | `"1.0"` | Contract version tracked by `PromptBuilder` |
| `safety_version` | `"1.0"` | Safety rule version |
| `first_run_completed` | `false` | Set to `true` by the onboarding wizard |
| `onboarding_version` | `"1.0"` | Onboarding schema version |

---

## Measured performance

All numbers on Ryzen 5 5600 + 16 GB RAM, Windows 11, Groq + Piper + base.en Whisper:

| Metric | Result |
|---|---|
| Voice round-trip (hotkey → speech starts) | ~1.2 s |
| First TTS audio chunk after LLM start | < 200 ms |
| Memory embedding (fastembed bge-small) | ~15 ms / fact |
| CPU at idle (animations running) | < 2 % |
| Peak RAM | ~380 MB (models loaded) |
| Test suite (185 tests) | ~16 s |

---

## Architecture

```
src/
├── ai/
│   ├── llm_providers/         # Groq + Ollama provider selection
│   ├── tts_providers/         # Piper neural + pyttsx3 provider selection
│   ├── memory_providers/      # Vector sqlite-vec + lexical fallback
│   ├── ai_client.py           # Streaming LLM + inline memory tool calls
│   ├── brain.py               # Pet state machine (IDLE/THINKING/TALKING/ACTING/HAPPY)
│   ├── prompt_builder.py      # Centralized system prompt assembly with personality contract
│   ├── memory_store.py        # Fact storage — Markdown vault + provider index
│   ├── sentence_buffer.py     # Token stream → sentences → TTS queue
│   ├── tts_manager.py         # TTS queue + sentence-level streaming
│   └── voice_listener.py      # Whisper STT + silero-vad endpointing
├── ui/
│   ├── animation_engine.py    # VP9 alpha WebM player (WMF, zero CPU overhead)
│   ├── clip_recorder.py       # 5-second ring buffer → animated WebP
│   ├── onboarding_window.py   # First-run 4-page setup wizard
│   ├── chat_window.py         # Streaming chat transcript UI
│   ├── settings_window.py     # 4-tab settings (General / AI / Notifications / Appearance)
│   ├── tray_manager.py        # System tray icon + context menu (Snooze, Settings, Quit)
│   └── ui_manager.py          # Transparent frameless window + speech bubble overlay
├── system/
│   ├── proactive_engine.py    # Tick loop — evaluates trigger conditions, emits events
│   ├── proactive_policy.py    # RouterState + ProactivePolicy (injectable clock, pure logic)
│   ├── proactive_types.py     # ProactiveEvent, ProactiveDecision, ProactiveUtterance
│   ├── notification_router.py # State machine — daily cap, snooze, cooldowns, persistence
│   ├── provider_health.py     # Health checks for Groq, Piper, and Ollama
│   ├── hotkey_listener.py     # Global hotkeys on a QThread
│   ├── system_monitor.py      # CPU / battery / idle sensors
│   ├── calendar_manager.py    # Google Calendar sync (opt-in)
│   └── task_runner.py         # Background task management
└── core/
    └── config_manager.py      # Load + validate config.json, returns immutable MappingProxyType
main.py                        # Entry point — onboarding check, Qt app, signal wiring
scripts/
└── preprocess_alpha.py        # One-time WebM → VP9 alpha batch converter (requires ffmpeg)
```

### Provider abstraction

Every external dependency sits behind a two-level abstraction — primary provider with graceful degradation:

```
LLM:    Groq cloud  →  Ollama local  →  Mock (demo mode)
TTS:    Piper neural  →  pyttsx3
Memory: sqlite-vec vector  →  lexical keyword
```

No API key, no voice model, no GPU? Each layer degrades independently. The app always starts.

### Proactivity policy stack

```
ProactiveEngine (tick, sensor data)
       │
       ▼  ProactiveEvent(type, source_data)
ProactivePolicy.evaluate(event, RouterState, config, clock)
       │
       ▼  ProactiveDecision(approved, reason)
NotificationRouter (update RouterState, persist, emit signal)
       │
       ▼  notification_approved(message, type)
UIManager / TTSManager
```

Every layer is independently testable. `ProactivePolicy` is pure — no I/O, injectable clock, deterministic in tests.

---

## Running tests

```bash
uv run python -m pytest tests/ -q
```

**185 tests** across 14 modules — unit, integration, and component coverage:

| Module | Coverage |
|---|---|
| `test_ai_client.py` | Streaming LLM, inline memory tool calls, provider abstraction |
| `test_brain.py` | Pet state machine transitions |
| `test_prompt_builder.py` | Personality contract injection, snapshot tests |
| `test_proactive_engine.py` | ProactivePolicy rules, daily cap, quiet hours, snooze, cooldowns |
| `test_notification_router.py` | Routing, persistence, snooze API, category disable |
| `test_config.py` | Validation, immutability, malformed JSON recovery, onboarding fields |
| `test_provider_health.py` | Groq key format, Piper file existence, Ollama reachability (all offline-safe) |
| `test_memory_store.py` | Fact storage, retention cap, vault compatibility |
| `test_vector_memory.py` | Semantic kNN recall, index cleanup |
| `test_sentence_buffer.py` | Token → sentence splitting, min-chars, flush |
| `test_animation_engine.py` | Asset resolution, skin selection |
| `test_calendar_manager.py` | Event parsing, lookahead window |
| `test_task_runner.py` | Task lifecycle |
| `test_onboarding_window.py` | Config persistence, provider choice |

---

## Asset preprocessing

The animation engine expects WebM files with native VP9 alpha (`yuva420p`). To convert custom character animations from a green-screen source:

```bash
# Requires ffmpeg on PATH — https://ffmpeg.org/download.html
python scripts/preprocess_alpha.py
```

This bakes transparency offline. Runtime CPU cost: zero.

---

## Roadmap

### Completed

- [x] **Phase 0** — Personality contract, PromptBuilder, config versioning
- [x] **Phase 0.5** — First-run onboarding wizard, provider health checks, settings improvements
- [x] **Phase 1** — Proactivity Engine v1: daily cap, quiet hours, snooze, structured policy layer

### In progress / up next

- [ ] **Phase 2** — Memory Transparency UI: inspect, search, edit, and delete individual facts from inside KIBO
- [ ] **Phase 3** — Personality and Memory Coherence: stronger recall, consistent character voice across sessions
- [ ] **Phase 4** — Settings, Controls, and Error Surfaces: Open Data Folder, Reset Onboarding, hotkey conflict detection
- [ ] **Phase 4.5** — Voice, Hotkey, and Device Reliability: audio device fallback, hotkey health signal
- [ ] **Phase 5** — Engineering Credibility and Demo Resilience: demo mode, deterministic replay

### Future

- [ ] macOS support (`pynput` + `pywinctl` replacing Windows-only deps)
- [ ] Custom character SDK — drop in your own VP9 alpha WebM sprite sheet
- [ ] `pip install kibo` PyPI release
- [ ] Opt-in telemetry for clip sharing and usage analytics

---

## Contributing

Issues and PRs are welcome. Please open an issue first for anything larger than a bug fix.

1. Fork → create a feature branch
2. Write tests first (TDD: red → green → refactor)
3. `uv run python -m pytest tests/ -q` must pass (all 185)
4. Submit a PR with a clear description of what changed and why

---

## License

[MIT](LICENSE) © 2026 Yash Patil
