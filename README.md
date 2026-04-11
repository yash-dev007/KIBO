# KIBO - The AI Virtual Pet Desktop Buddy

KIBO is an intelligent, frameless, and always-on-top virtual pet desktop companion powered by AI. He lives on your screen, reacts to your system state, listens to your voice, and even chats with you using streaming speech bubbles and Text-to-Speech (TTS)!

Featuring perfectly cut-out 60fps transparent WebM-to-PNG animations and smart state machine logic, KIBO is the ultimate desktop sidekick.

## Features ✨
- **60fps Fluid Animations:** Ultra-smooth, fully transparent desktop rendering.
- **Context-Aware AI:** Hooked up to an LLM, KIBO knows what you're doing. He can analyze your system load, open windows, and interact with you intelligently!
- **Voice Interaction:** Press `Ctrl+Shift+L` to talk directly to KIBO using Whisper speech-to-text.
- **Text-to-Speech:** KIBO responds with his own AI-generated voice using `pyttsx3`.
- **System Monitoring:** He automatically becomes `SLEEPY` late at night, or `WORKING` / `STUDIOUS` when you have Visual Studio Code open.
- **Multi-Skin Support:** Fully modular animation system. Use the default `skales` buddy skin or script your own!

## Prerequisites 🛠️
- **Python 3.10+** (Tested running via Conda)
- **Windows OS** (For `PySide6` frameless windows & specific hotkey bindings)

## Quick Start 🚀

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Configure your AI Keys**
Ensure you have your AI variables mapped in an `.env` file (e.g. OpenAI / Groq keys) so KIBO's brain can process chat responses.

3. **Run KIBO!**
```bash
python main.py
```
*(If running under a conda environment: `conda run -n kibo python main.py`)*

## Customizing KIBO ⚙️
Open `config.json` to alter KIBO's behavior:
- Set `buddy_skin` to load different animation packs.
- Adjust `sleepy_hour` to change when KIBO starts dozing off.
- Edit `studious_windows` to specify which apps trigger KIBO's "working" state.
- Change `frame_rate_ms` to speed up or slow down animation playback (Default: `16` for 60fps).

## Controls 🎮
- **Click & Drag**: Move KIBO anywhere on your screen.
- **Right Click**: Open a context menu to Reset KIBO's position or Quit the app.
- **Global Hotkey** (`Ctrl+Shift+L`): Hold to talk to KIBO via microphone.

---
*Created by [yash-dev007](https://github.com/yash-dev007)*
