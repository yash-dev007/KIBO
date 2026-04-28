<div align="center">

<br/>

<img src="assets/animations/skales/icon.png" alt="KIBO" width="120" />

# KIBO

### A desktop companion that lives on your screen, reacts to what you're doing, and remembers you.

<br/>

[![Stars](https://img.shields.io/github/stars/yash-dev007/KIBO?style=flat-square&color=FFD700&labelColor=1a1a1a)](https://github.com/yash-dev007/KIBO/stargazers)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square&labelColor=1a1a1a)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=1a1a1a)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&labelColor=1a1a1a)](https://doc.qt.io/qtforpython/)
[![LLM: Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20Ollama-F54F29?style=flat-square&labelColor=1a1a1a)](https://console.groq.com)

<br/>

> **KIBO is not a chatbot widget. It's a frameless, transparent animated character that sits on your desktop, listens for your voice, responds with neural TTS, and builds persistent long-term memory — all running locally.**

<br/>

</div>

---

## What makes KIBO different

| | KIBO | Typical AI widget |
|---|---|---|
| **Latency** | ~1.2s voice round-trip | 3–8s |
| **TTS** | Piper neural (streaming, sentence-level) | pyttsx3 / browser |
| **Memory** | Vector RAG (sqlite-vec + bge-small) | Session-only |
| **Rendering** | VP9 alpha WebM, zero CPU chroma-key | PNG sequences or browser canvas |
| **Privacy** | Fully local (Groq is opt-in) | Cloud-dependent |
| **Footprint** | < 2% CPU at idle | — |

---

## Features

### Voice & AI
- **Push-to-talk** (`Ctrl+K`) with faster-whisper `base.en` + optional silero-vad endpointing
- **Streaming sentence → TTS pipeline** — Piper neural audio starts playing while the LLM is still generating
- **Groq cloud LLM** (`llama-3.3-70b`, ~6000 tok/s free tier) with automatic Ollama fallback if no API key is set
- **Inline memory extraction** — the LLM emits `remember` tool calls mid-stream; no second LLM round-trip

### Long-term Memory
- **Vector RAG** via sqlite-vec + fastembed (bge-small-en-v1.5, ~30 MB). Semantic kNN — *"what's my favourite drink?"* finds *"user likes espresso"* without keyword overlap.
- **Obsidian-compatible vault** — every fact is also written to `~/.kibo/vault/memories/*.md`
- **One-click clear** from the Settings window
- Migration: existing vault Markdown files are embedded on first run, no data lost

### Animation Engine
- **VP9 alpha WebM** playback via WMF — zero CPU chroma-key on Windows 10/11 with Web Media Extensions
- **Automatic PNG fallback** if a WebM asset lacks native alpha or the codec pack is missing
- **State machine** — IDLE, THINKING, TALKING, ACTING, HAPPY with smooth transitions and random action animations during idle time

### Clip Mode
- **`Ctrl+Alt+K`** — saves the last 5 seconds of animation as an animated WebP to `~/.kibo/clips/`
- Ring buffer runs passively; zero overhead when not saving

### System Awareness (opt-in)
- Reacts to CPU load, idle time, and active window context
- Google Calendar integration for meeting reminders
- Proactive notifications (all disabled by default — enable in `config.json`)

---

## Quick start

### 1. Install

```bash
git clone https://github.com/yash-dev007/KIBO.git
cd KIBO
pip install -r requirements.txt
```

### 2. Get a free Groq API key

Sign up at [console.groq.com](https://console.groq.com) — free tier, no credit card.

```bash
# Windows (PowerShell)
$env:GROQ_API_KEY = "gsk_..."

# macOS / Linux
export GROQ_API_KEY="gsk_..."
```

> **No key?** KIBO falls back to Ollama automatically. Run `ollama pull llama3.2:3b` first.

### 3. Download a Piper voice (~30 MB, one-time)

```bash
mkdir -p models/piper

# Windows (PowerShell)
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx" -OutFile "models/piper/en_US-amy-medium.onnx"
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json" -OutFile "models/piper/en_US-amy-medium.onnx.json"

# macOS / Linux
curl -L -o models/piper/en_US-amy-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
curl -L -o models/piper/en_US-amy-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
```

> **No Piper voice?** Falls back to pyttsx3. Nothing breaks.

### 4. (Optional) Better endpointing

```bash
pip install torch torchaudio   # enables silero-vad end-of-speech detection
```

### 5. Run

```bash
python main.py
```

---

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+K` | Push-to-talk |
| `Ctrl+Alt+K` | Save last 5-second clip to `~/.kibo/clips/` |

Right-click the pet for Settings, Reset Position, and Quit.

---

## Configuration

Edit `config.json` at the project root.

| Key | Default | Description |
|---|---|---|
| `pet_name` | `"KIBO"` | Name shown in the window title |
| `buddy_skin` | `"skales"` | Animation asset folder under `assets/animations/` |
| `activation_hotkey` | `"ctrl+k"` | Push-to-talk hotkey |
| `clip_hotkey` | `"ctrl+alt+k"` | Clip save hotkey |
| `llm_provider` | `"groq"` | `"groq"` or `"ollama"` |
| `tts_provider` | `"piper"` | `"piper"` or `"pyttsx3"` |
| `memory_provider` | `"vector"` | `"vector"` or `"lexical"` |
| `proactive_enabled` | `false` | System-aware proactive notifications |
| `calendar_provider` | `"none"` | `"google"` to enable Calendar sync |
| `enable_speech_bubbles` | `true` | Show/hide speech bubble overlay |

---

## Measured performance

All numbers on Ryzen 5 5600 + 16 GB RAM, Windows 11, Groq + Piper + base.en Whisper:

| Metric | Result |
|---|---|
| Voice round-trip (hotkey → speech starts) | ~1.2 s |
| First TTS audio chunk after LLM start | < 200 ms |
| Memory embedding (fastembed bge-small) | ~15 ms/fact |
| CPU at idle (animations running) | < 2% |
| Peak RAM | ~380 MB (models loaded) |

---

## Architecture

```
src/
├── ai/
│   ├── llm_providers/       # Groq (default) + Ollama fallback
│   ├── tts_providers/       # Piper neural (default) + pyttsx3 fallback
│   ├── memory_providers/    # Vector sqlite-vec (default) + lexical fallback
│   ├── ai_client.py         # Streaming LLM + inline memory tool calls
│   ├── brain.py             # Pet state machine
│   ├── sentence_buffer.py   # Token stream → sentences → TTS
│   ├── tts_manager.py       # TTS queue + streaming
│   └── voice_listener.py    # Whisper STT + silero-vad
├── ui/
│   ├── animation_engine.py  # VP9 alpha WebM player + PNG fallback
│   ├── clip_recorder.py     # 5-second ring buffer → animated WebP
│   ├── ui_manager.py        # Transparent frameless window + speech bubble
│   ├── chat_window.py       # Streaming chat UI
│   └── settings_window.py
├── system/
│   ├── hotkey_listener.py   # Global hotkeys on a QThread
│   ├── system_monitor.py    # CPU / idle sensors
│   ├── proactive_engine.py  # Opt-in proactive notifications
│   └── calendar_manager.py  # Google Calendar (opt-in)
└── core/
    └── config_manager.py
scripts/
└── preprocess_alpha.py      # One-time WebM → VP9 alpha batch converter
```

### Provider abstraction

Every external dependency is behind a two-level abstraction — default provider with graceful fallback:

```
LLM:    Groq  ──fallback──▶  Ollama
TTS:    Piper ──fallback──▶  pyttsx3
Memory: sqlite-vec ─────────▶  lexical keyword
```

No API key, no voice model, no GPU? Each layer degrades independently. The app always starts.

---

## Asset preprocessing

The animation engine expects WebM files with native VP9 alpha (`yuva420p`). If you add custom character animations with a green-screen background, run the one-time converter:

```bash
# Requires ffmpeg on PATH — https://ffmpeg.org/download.html
python scripts/preprocess_alpha.py
```

This bakes transparency into the files offline. Runtime CPU cost: zero.

---

## Running tests

```bash
pytest tests/ -q
```

77 tests across the AI client, sentence buffer, memory providers, and voice pipeline.

---

## Roadmap

- [ ] macOS support (`pynput` + `pywinctl` to replace Windows-only deps)
- [ ] Custom character SDK — drop in your own WebM sprite sheet
- [ ] `pip install kibo` PyPI release
- [ ] PostHog opt-in telemetry for clip sharing analytics

---

## Contributing

Issues and PRs are welcome. Please open an issue first for anything larger than a bug fix.

1. Fork → create a feature branch
2. Write tests for new behaviour
3. `pytest tests/ -q` must pass
4. Submit PR with a clear description of what changed and why

---

## License

[MIT](LICENSE) © 2026 Yash Patil
