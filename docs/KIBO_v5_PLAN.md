# KIBO v5 — Roadmap from the YC + Anthropic Engineer Debate

This document maps every judge complaint from the v4 product review to a
concrete fix. Phase 1 is **shipped** in this branch. Phases 2 & 3 are the
remaining work to reach the "best virtual pet ever" bar.

---

## Phase 1 — The 1.2-second pet (shipped)

The latency rewrite. Goal: end-to-end voice round-trip under 1.5s on a
mid-tier laptop.

| # | Judge complaint | What landed |
|---|---|---|
| 1 | Confused persona (assistant + pet + romantic AI), hardcoded "Sneha/Aira" | Cleaned `system_prompt` in `config.json`. New persona: warm desktop companion, 2-3 sentence default. |
| 2 | `pyttsx3` is robotic and blocks the thread | New `src/ai/tts_providers/` abstraction. Default = **Piper** (neural, local, ONNX, ~150ms first sample). Auto-falls-back to pyttsx3 if Piper voice missing. |
| 3 | Local-only Ollama = 3s+ first token | New `src/ai/llm_providers/` abstraction. Default = **Groq** free tier (`llama-3.3-70b-versatile`, ~6000 tok/s). Falls back to Ollama if `GROQ_API_KEY` absent. |
| 4 | `tiny.en` Whisper + RMS heuristic = 1.5s STT | Default model bumped to `base.en`. Added optional **silero-vad** endpointing for accurate end-of-speech. |
| 5 | Doubled LLM call for memory extraction | Memories now arrive **inline** as `remember` tool calls during the same streaming response. New `memory_fact_extracted` signal → `MemoryStore.add_fact_inline`. The legacy second-call path is preserved as a fallback. |
| 6 | Calendar/CPU/proactive features dilute the pitch | Defaults flipped to `proactive_enabled: false`, `calendar_provider: "none"`. Power users opt in via settings. |
| 7 | TTS plays full reply in one blocking call | New `src/ai/sentence_buffer.py` splits the streaming token feed into sentences and dispatches them to TTS as they complete. Audio playback overlaps with generation. |

### How to actually run Phase 1 at full speed

```bash
# 1. New deps
pip install -r requirements.txt

# 2. Get a Groq API key (free): https://console.groq.com
$env:GROQ_API_KEY = "gsk_..."

# 3. Download a Piper voice (one-time, ~30 MB)
mkdir models/piper
curl -L -o models/piper/en_US-amy-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
curl -L -o models/piper/en_US-amy-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json

# 4. (optional) Install torch for silero-vad endpointing
pip install torch torchaudio

# 5. Run
python main.py
```

If neither Groq key nor Piper voice is present, KIBO degrades gracefully
to the old Ollama + pyttsx3 stack. Nothing breaks.

### Files touched/created in Phase 1

- **New**: `src/ai/llm_providers/{__init__,base,groq_provider,ollama_provider}.py`
- **New**: `src/ai/tts_providers/{__init__,base,piper_provider,pyttsx3_provider}.py`
- **New**: `src/ai/sentence_buffer.py`
- **Rewritten**: `src/ai/ai_client.py`, `src/ai/tts_manager.py`, `src/ai/voice_listener.py`
- **Modified**: `src/ai/memory_store.py` (added `add_fact_inline`), `main.py` (streaming wiring), `config.json` (new keys, clean prompt), `requirements.txt`
- **New tests**: `tests/test_sentence_buffer.py` (6) + `tests/test_ai_client.py` rewritten (8). All passing.

---

## Phase 2 — Real RAG + animation engine fix

Two technical debts the judges flagged as the next blockers.

### 2A. Replace lexical "memory" with sqlite-vec + fastembed

The current `MemoryStore.retrieve_relevant` does keyword overlap + recency
scoring. "User likes espresso" → "what's my favorite drink?" misses.

**Plan:**

1. Add deps: `sqlite-vec`, `fastembed` (~30 MB ONNX bge-small).
2. Create `src/ai/memory_providers/` with `LexicalProvider` (current) and
   `VectorProvider` (new). Mirror the LLM/TTS pattern.
3. `VectorProvider` schema:
   ```sql
   CREATE TABLE memories (
     id INTEGER PRIMARY KEY,
     content TEXT,
     category TEXT,
     keywords TEXT,
     extracted_at INTEGER
   );
   CREATE VIRTUAL TABLE memories_vec USING vec0(
     embedding float[384]
   );
   ```
4. On `add_fact_inline`: embed `content` with fastembed, INSERT into both
   tables (keyed by id).
5. On `retrieve_relevant(query)`: embed query, kNN against `memories_vec`,
   return top-K rows from `memories`.
6. Keep the markdown export step so Obsidian users still see their vault.
7. Migration: on first run, scan existing `~/.kibo/vault/memories/*.md`,
   embed each, upsert into sqlite-vec. Idempotent (skip if id exists).

**Estimated effort**: 1-2 days. Risk: low. Backward-compat: full.

**Files**: new `src/ai/memory_providers/`, refactor `memory_store.py`, add
test `tests/test_vector_memory.py`.

### 2B. Drop software chroma-keying

`animation_engine.py` runs numpy-based color-key removal on every WebM
frame at 30ms intervals. Burns 8-12% CPU on a Ryzen 5 for what should be
a transparent video.

**Plan:**

1. Audit `assets/animations/skales/**/*.webm` — confirm they're VP9 with
   alpha (`yuva420p`). If so, Qt's `QMediaPlayer` with `QGraphicsVideoItem`
   handles alpha natively on Windows 11 via WMF.
2. If assets are RGB-with-green-screen instead: pre-process them once with
   `ffmpeg -vf colorkey=0x00ff00:0.1:0.05 -c:v libvpx-vp9 -pix_fmt yuva420p`
   to bake transparency into the file (offline cost, runtime saving forever).
3. Rewrite `animation_engine.py`:
   - Drop the `_chroma_key_frame` numpy hot loop.
   - Use `QGraphicsView` with transparent background + `QVideoSink` →
     `QGraphicsVideoItem`.
   - Set `setBackgroundBrush(Qt.transparent)`.
4. Remove the `_keyer_pool` thread executor and the per-frame numpy ops.
5. Validate: profile with `cProfile` → main thread CPU should drop from
   8-12% to <2% during animations.

**Estimated effort**: 2-3 days. Risk: medium (asset audit may turn up
non-alpha WebMs requiring a one-time ffmpeg batch).

**Files**: rewrite `src/ui/animation_engine.py`, possibly add
`scripts/preprocess_alpha.py` for the asset batch step.

---

## Phase 3 — Distribution + honesty

The features that turn a polished local app into a *product*.

### 3A. Clip Mode (the viral loop)

The single feature most likely to drive free distribution. Hotkey →
captures the last 5 seconds of the KIBO window (transparent WebM) plus
the audio reply, drops it on the clipboard with a "share" prompt.

**Plan:**

1. Background ring buffer in `src/ui/clip_recorder.py`:
   - Use `mss` to grab the KIBO window region every 33ms (matches
     existing frame_rate_ms).
   - Maintain a deque of the last `5 * 30 = 150` frames in RAM.
   - Tee the TTS audio into a parallel deque (synced via timestamps).
2. New global hotkey `Ctrl+Alt+K` → `ClipRecorder.dump()`:
   - Encode frames + audio with `imageio-ffmpeg` to a transparent WebM
     under `~/.kibo/clips/<timestamp>.webm`.
   - Copy file path to clipboard.
   - Show toast: "Clip saved! Share to Twitter / Discord."
3. Add a one-click share menu (right-click on the clip toast):
   - Twitter: open browser with prefilled tweet text + clip URL hint.
   - Discord: open file picker pointed at clip.
4. Telemetry stub (PostHog free tier): count `clip_recorded` events.
   Opt-in only.

**Estimated effort**: 1 week. Risk: medium (transparent-webm encode
needs validation across players).

**Files**: new `src/ui/clip_recorder.py`, hotkey wiring in `main.py` and
`src/system/hotkey_listener.py`.

### 3B. Honest README rewrite

The current README claims "Hardware-Accelerated" and "Async RAG" — both
false in v4. Rewrite once Phase 2 actually delivers them.

**Plan:**

- New positioning headline: *"A small character that lives on your
  desktop, reacts to what you're doing, and remembers you."*
- Drop the "v4 Milestone" framing — replace with a clear feature matrix
  (Free / Plus / character-pack).
- Add benchmark numbers: voice round-trip latency, CPU at idle,
  memory recall accuracy (measured against a 50-fact eval set).
- One-sentence install: `pip install kibo` (after we publish to PyPI).

### 3C. Delete the dead Rust crate

`kibo_core/` ships PyO3 bindings + 400 MB of build artifacts and is
called by exactly nothing. Either:

- **Option A**: delete the directory. Add to `.gitignore` if it's needed
  for future work.
- **Option B**: ship something through it. The natural candidate is the
  hot path of Phase 2A (vector kNN + audio mixing for Clip Mode). Worth
  doing only if Python perf actually shows up on a profile.

Decision: default to **Option A** unless a profile shows Python is the
bottleneck.

### 3D. Cross-platform path (post-v5)

`keyboard` + `pygetwindow` + frameless overlay are Windows-only. macOS
needs:

- Replace `keyboard` → `pynput` (already cross-platform).
- Replace `pygetwindow` → `pywinctl` (cross-platform fork).
- Test frameless transparent window on macOS Sonoma (Qt supports it but
  needs `Qt.WindowTransparentForInput` tuning).

Not blocking for v5 release. Park for v6.

---

## Sequencing

| When | Work |
|---|---|
| Now | Phase 1 (shipped) — install Groq key + Piper voice, validate latency |
| Week 2 | Phase 2A (vector RAG) — small surface area, low risk |
| Week 3 | Phase 2B (drop chroma-key) — frees frame budget |
| Week 4 | Phase 3A (Clip Mode) — distribution unlock |
| Week 5 | Phase 3B (README), 3C (Rust crate decision), QA pass |

If Phase 1 latency holds in real testing, Phase 2A is the highest-value
next step — it's what makes the "she remembers me" experience actually
work, which is the emotional anchor of the product.
