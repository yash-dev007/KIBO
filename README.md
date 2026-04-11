<div align="center">
  <img src="https://raw.githubusercontent.com/yash-dev007/KIBO/main/assets/branding/kibo_logo.png" width="120" style="border-radius: 20px" />
  <h1>🦎 KIBO v4: The Elite Desktop AI Companion</h1>
  <p><strong>A Hardware-Accelerated, Long-Term Memory, Multi-Integrated Virtual Companion</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Engine-WebM_Video-00FF88?style=for-the-badge&logo=probot" />
    <img src="https://img.shields.io/badge/UI-Glassmorphism-16181C?style=for-the-badge&logo=windowsterminal" />
    <img src="https://img.shields.io/badge/Memory-Async_RAG-FFD700?style=for-the-badge&logo=memory" />
    <img src="https://img.shields.io/badge/AI-Ollama-FFD700?style=for-the-badge&logo=ollama" />
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python" />
  </p>
</div>

---

## 🌟 Overview
**KIBO** is an elite desktop companion that bridges the gap between static virtual pets and autonomous AI agents. Unlike traditional apps, KIBO lives as a frameless, glass-textured mascot that reacts to your CPU load, active windows, calendar meetings, and background tasks while maintaining a persistent memory of your preferences.

---

## ✨ v4 Milestone Features

### 🎞️ Next-Gen Animation Engine
- **WebM Integration**: Switched from legacy PNG sequences to high-fidelity WebM video assets for ultra-smooth movement.
- **Dynamic Chroma Keying**: Real-time Numpy-accelerated background removal for perfectly transparent "floating" animations.
- **Action Shuffling**: KIBO feels alive with an intelligent state machine that triggers random animations (working out, bubbles, sleeping) during idle time.

### 🧠 Smart Memory & RAG
- **Async Fact Extraction**: KIBO automatically analyzes your conversations in the background to extract factual memories (preferences, names, tasks).
- **Persistent retrieval**: Uses a keyword and recency-based scoring system to inject relevant context into the AI's "brain" before every response.
- **Privacy Control**: Settings > AI > Clear Memory allows you to wipe all learned facts instantly.

### 🗓️ Ecosystem Integrations
- **Google Calendar Sync**: Asynchronous polling of Google Calendar events with proactive meeting reminders.
- **Autonomous Task Runner**: A background worker that can execute long-running AI tasks with built-in rate limiting and user approval flow.
- **Proactive Intelligence**: KIBO won't just wait for you—he checks in if you've been idle, alerts you to low battery, or panics if your CPU is overloaded.

### 🪟 Premium Experience
- **Glassmorphic Chat Window**: A modern, acrylic chat interface with session history persistence.
- **Unified Settings UI**: Multi-tab configuration window for managing AI models, proactive rules, and appearance.
- **System Tray Management**: Full control from the Windows taskbar with a single-instance lock to prevent duplicate processes.

---

## 🛠️ Tech Stack
- 🐍 **Python 3.11+**
- 🎨 **PySide6** (Qt for Python) with Glassmorphism
- 🔢 **Numpy** (Accelerated image processing)
- 🎙️ **faster-whisper** & **sounddevice** (Voice intelligence)
- ☁️ **Ollama** (Local LLM backend)
- 📅 **Google API Client** (Calendar integration)

---

## 🚀 Quick Start

### 📦 Standalone Windows EXE
1. Download the latest `KIBO` folder from Releases.
2. Double-click **`KIBO.exe`**.
3. *Note: Ensure Ollama is running for AI features.*

### 🐍 Developer Setup
```bash
# Clone
git clone https://github.com/yash-dev007/KIBO.git
cd KIBO

# Install requirements
pip install -r requirements.txt

# Launch
python main.py
```

---

<div align="center">
  <p>✨ Developed with 💚 by <a href="https://github.com/yash-dev007">yash-dev007</a> ✨</p>
  <p><strong>Experience the future of desktop companionship.</strong></p>
</div>
