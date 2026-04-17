<div align="center">

  <h1>🦎 KIBO v4: The Elite Desktop AI Companion</h1>
  <p><strong>A Hardware-Accelerated, Long-Term Memory, Multi-Integrated Virtual Companion</strong></p>

  <p>
    <a href="https://github.com/yash-dev007/KIBO/stargazers"><img src="https://img.shields.io/github/stars/yash-dev007/KIBO?style=for-the-badge&color=00FF88" alt="Stars" /></a>
    <a href="https://github.com/yash-dev007/KIBO/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License" /></a>
    <img src="https://img.shields.io/badge/Engine-WebM_Video-00FF88?style=for-the-badge&logo=youtube" alt="Engine" />
    <img src="https://img.shields.io/badge/UI-Black_Glass-000000?style=for-the-badge&logo=windowsterminal" alt="UI" />
    <img src="https://img.shields.io/badge/Performance-Main_Thread_Safe-00FF88?style=for-the-badge&logo=fastapi" alt="Performance" />
    <img src="https://img.shields.io/badge/Memory-Async_RAG-FFD700?style=for-the-badge&logo=memory" alt="Memory" />
    <img src="https://img.shields.io/badge/AI-Ollama-FFD700?style=for-the-badge&logo=ollama" alt="AI" />
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python" alt="Python" />
  </p>
</div>

---

## 🌟 Overview
**KIBO** is an elite desktop companion that bridges the gap between static virtual pets and autonomous AI agents. Unlike traditional apps, KIBO lives directly on your desktop as a frameless, glass-textured mascot. KIBO reacts in real-time to your CPU load, active windows, calendar meetings, and background tasks, all while maintaining a persistent memory of your preferences using a secure local AI backend.

---

## ✨ Features (v4 Milestone)

### 🎞️ Next-Gen Animation Engine
- **WebM Integration**: Enjoy ultra-smooth movement using high-fidelity WebM video assets instead of legacy PNG sequences.
- **Dynamic Chroma Keying**: Employs real-time, software-accelerated background removal for perfectly transparent, "floating" animations.
- **Action Shuffling**: KIBO feels alive! An intelligent state machine triggers random, seamless animations (working out, playing, sleeping) during user idle time.

### 🧠 Smart Memory & RAG
- **Async Fact Extraction**: KIBO automatically processes your conversations in the background to glean factual memories (preferences, names, tasks).
- **Persistent Retrieval**: Driven by a keyword and recency-based scoring algorithm, KIBO injects hyper-relevant context into his "brain" before constructing a response.
- **Total Privacy**: Built completely locally! The `Clear Memory` setting instantly truncates and wipes all learned facts.

### 🗓️ Ecosystem Integrations
- **Google Calendar Sync**: Asynchronous polling surfaces upcoming Google Calendar events directly into KIBO’s proactive reminders.
- **Autonomous Task Runner**: Executes complex, long-running AI instructions with built-in rate-limiting and user verification.
- **Proactive Intelligence**: KIBO acts independently. He brings up low battery warnings, pauses resource-heavy tasks if CPU runs too hot, and encourages you if you've been working long hours.

### 🪟 Premium Desktop Experience
- **Black Glass UI**: A minimalist, high-contrast dark theme across all windows (Chat, Settings, Context Menu) for an elite, premium look.
- **High-Performance Streaming**: Fully asynchronous Chat UI using worker-thread dispatching — no more UI freezes during AI generation.
- **Text & Voice Mastery**: Chat via keyboard with smooth token-by-token streaming, or use push-to-talk to speak directly to KIBO.
- **Privacy-First (No-Logging)**: Chat history is no longer persisted on disk by default, ensuring every session is private and fresh.
- **System Tray Management**: Lightweight global taskbar control for repositioning or adjusting settings without interrupting your workflow.

---

## 🛠️ Architecture & Tech Stack
KIBO guarantees complete privacy, smooth performance, and hardware-accelerated graphics support:
- 🐍 **Language**: Python 3.11+
- 🎨 **GUI Framework**: PySide6 (Qt for Python) with pure C++ window layering
- 🔢 **Video Processing**: Numpy + Python Threading
- 🎙️ **Voice AI**: `faster-whisper` & `sounddevice`
- ☁️ **LLM Backend**: Ollama (Llama 3.2 3B is the designated optimal model) 
- 📅 **Productivity**: Google API Client

---

## 🚀 Getting Started

### 📋 Prerequisites
1. **Python 3.11+** installed locally.
2. Ensure [Ollama](https://ollama.com/) is installed and running in your background. KIBO defaults to using Llama 3 models locally. Preload your preferred model via CLI:
   ```bash
   ollama run llama3.2:3b
   ```

### 💻 Developer Setup
```bash
# Clone the repository
git clone https://github.com/yash-dev007/KIBO.git
cd KIBO

# Create and activate a Conda Environment
conda create -n kibo python=3.11 -y
conda activate kibo

# Install requirements
pip install -r requirements.txt

# Launch KIBO
python main.py
```

---

## ⌨️ Global Shortcuts & Interaction
| Action | Keybinding / Trigger |
| :--- | :--- |
| **Voice Hotkey** | `Ctrl + K` (Hold) |
| **Summon Chat** | Left Click on KIBO |
| **Tray Menu** | Right Click on KIBO |

---

## 🤝 Contributing
Contributions, issues, and feature requests are highly welcome! Please check the [CONTRIBUTING.md](CONTRIBUTING.md) for details on how you can help out.

---

## 📝 License
Distributed under the **MIT License**. See `LICENSE` for more information.

---

<div align="center">
  <p>✨ Developed with 💚 by <a href="https://github.com/yash-dev007">yash-dev007</a> ✨</p>
  <p><strong>Experience the future of desktop companionship.</strong></p>
</div>
