<div align="center">
  <h1>🦎 KIBO</h1>
  <p><strong>The Intelligent AI Virtual Pet & Desktop Companion</strong></p>
  <p>
    <a href="#-features"><img src="https://img.shields.io/badge/Features-✨-blue"></a>
    <a href="#-tech-stack"><img src="https://img.shields.io/badge/Stack-Python_3.10+-yellow"></a>
    <a href="#-setup--installation"><img src="https://img.shields.io/badge/Setup-🛠️-green"></a>
  </p>
</div>

---

## 🌟 Overview
**KIBO** is a next-generation, AI-powered frameless virtual pet that lives directly on your desktop! More than just a static mascot, KIBO actively monitors your system state, interacts with your daily workflow, listens to your voice commands, and responds with immersive 60 FPS animations and fully-voiced AI text-to-speech bubbles.

## ✨ Core Features
- 🚀 **60 FPS Fluid Animations:** Silky smooth, frameless, hardware-accelerated animations that seamlessly blend into your desktop environment.
- 🧠 **Context-Aware Intelligence:** Connected to bleeding-edge LLMs, KIBO analyzes your active windows and responds intelligently (e.g., getting `STUDIOUS` when you open an IDE, or `SLEEPY` late at night).
- 🎙️ **Voice Interaction:** Speak directly to KIBO via microphone. He uses advanced Whisper speech-to-text models to process your requests in real-time.
- 🗣️ **Text-to-Speech (TTS):** KIBO talks back! Using integrated Python TTS libraries, you get real-time auditory responses mixed with dynamic UI speech bubbles.
- ⚙️ **Multi-Skin Support:** Fully modular state-machine animation engine. Out of the box, KIBO ships with the high-fidelity **Skales** animation package!

---

## 🛠️ Tech Stack & Requirements
To run KIBO locally across environments, you will need:
- 🐍 **Python 3.10+** (Virtual environments like `venv` or `conda` are highly recommended)
- 🖥️ **OS:** Windows (For `PySide6` frameless integration and active-window monitoring).
- 🔑 **AI API Keys:** OpenAI, Groq, or equivalent keys for LLM inference.

## 🚀 Setup & Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/yash-dev007/KIBO.git
cd KIBO
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Configure Environment Variables
Create a root `.env` file and insert your AI provider keys. KIBO relies on these to process intelligence routines.
```env
# Example .env file
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

### 4️⃣ Launch Your Desktop Buddy!
```bash
python main.py
```

---

## 🎮 Controls & Interactions
- 🖱️ **Drag & Drop:** Click and hold KIBO to move him anywhere around your screen.
- 💬 **Talk Feature:** Press and hold `Ctrl+Shift+L` to activate the microphone stream. Release to send your query to KIBO.
- 🖱️ **Context Menu:** Right-click KIBO to manually `Reset Position` or `Quit` the application safely.

## ⚙️ Configuration
Customize KIBO's personality and logic entirely inside the `config.json` file:
- 🎭 `"buddy_skin"`: Map logic to new asset pipelines.
- ⏱️ `"frame_rate_ms"`: Adjust the playback rendering engine speed (Default: `16` for 60fps).
- 💤 `"sleepy_hour"`: Define what hour KIBO should start getting tired.
- 🧑‍💻 `"studious_windows"`: Array of application names (e.g., `["Visual Studio Code", "code"]`) that put KIBO in a focused "working" state.

---
<div align="center">
  <p>💡 Built with passion by <a href="https://github.com/yash-dev007">yash-dev007</a></p>
</div>
