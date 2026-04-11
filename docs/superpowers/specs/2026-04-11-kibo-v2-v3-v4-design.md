# KIBO v2/v3/v4 — Full Design Specification
**Date:** 2026-04-11  
**Author:** Claude (Sonnet 4.6) via brainstorming session  
**Stack:** Python 3.11 · PySide6 · PyInstaller · Ollama  
**Target Builder:** Gemini Pro (full implementation)

---

## 0. Context & Goal

KIBO is a Python/PySide6 AI desktop companion. Today it is a mascot with a
brain state machine, 60fps PNG animation, speech bubbles, and voice input via
faster-whisper + Ollama.

The goal is to evolve KIBO from a desktop pet into a **fully capable AI
desktop assistant** — with a chat window, persistent smart memory, proactive
intelligence, system tray, settings UI, calendar awareness, and an autonomous
task runner — while keeping the mascot as the friendly face of the product.

**Reference project:** `REF_PROJECT/` (Skales v7, Electron/Next.js/TypeScript).
Ideas are ported; the stack stays Python/PySide6.

---

## 1. Architecture Principle

**Feature-module architecture.** Every capability is a `QObject` subclass in
its own file. Modules communicate exclusively via Qt signals/slots — no module
imports another module's internals. Files stay under 400 lines.

```
Signal flow is the API. Internals are private.
```

---

## 2. Module Map

### 2.1 Existing core (unchanged unless noted)

| File | Role |
|------|------|
| `main.py` | Entry point + signal wiring |
| `brain.py` | State machine |
| `config_manager.py` | Immutable config + path helpers |
| `system_monitor.py` | psutil sensor feed |
| `ui_manager.py` | Pet window + glass UI (AnimationController migrated in Phase 1) |
| `ai_client.py` | Ollama streaming HTTP |
| `voice_listener.py` | faster-whisper recording |
| `hotkey_listener.py` | Global Ctrl+K |
| `tts_manager.py` | pyttsx3 TTS |

### 2.2 Phase 1 — Foundation (v2)

| New File | Role |
|----------|------|
| `animation_engine.py` | WebM playback via QMediaPlayer; replaces AnimationController |
| `chat_window.py` | Floating glass chat panel (380×520px) |
| `memory_store.py` | Fact extraction + keyword-scored retrieval |
| `tray_manager.py` | QSystemTrayIcon + single-instance lock |

### 2.3 Phase 2 — Intelligence (v3)

| New File | Role |
|----------|------|
| `proactive_engine.py` | Rule-based intelligence heartbeat (60s tick) |
| `notification_router.py` | Cooldowns + quiet hours + channel routing |
| `settings_window.py` | Frameless glass settings panel (480×600px) |

### 2.4 Phase 3 — Integrations (v4)

| New File | Role |
|----------|------|
| `calendar_manager.py` | Google/Outlook calendar event fetching |
| `task_runner.py` | Background autonomous task queue |

---

## 3. User Data Directory

All persistent state is stored in `~/.kibo/` (cross-platform via
`Path.home() / ".kibo"`). This survives reinstalls and EXE updates.

```
~/.kibo/
  memories/                ← one JSON file per extracted fact
  conversations/           ← one JSON file per session (last 30 sessions)
  proactive_state.json     ← cooldown timestamps + idle tracking
  tasks.json               ← task queue (Phase 3)
  calendar_state.json      ← cached calendar events (Phase 3)
```

### 3.1 New path helper in config_manager.py

```python
def get_user_data_dir() -> Path:
    """User data directory — persists across reinstalls."""
    d = Path.home() / ".kibo"
    d.mkdir(parents=True, exist_ok=True)
    return d
```

---

## 4. Phase 1 — Foundation (v2)

### 4.1 WebM Animation Engine (`animation_engine.py`)

**Why:** PNG sequences = 500+ files per skin, heavy RAM, complex loader.
WebM = one file per animation, hardware-decoded, already exists in REF_PROJECT
assets for the skales skin.

**Asset migration:**
- Source: `REF_PROJECT/apps/web/public/mascot/skales/*.webm`
- Destination: `assets/animations/skales/` (new WebM layout)
- Folder structure:
  ```
  assets/animations/skales/
    idle/stand.webm
    idle/still.webm
    idle/stillstand.webm
    action/breathing.webm
    action/bubblegum.webm
    ... (15 action clips)
    intro/elevator.webm
    intro/intro.webm
    intro/paper.webm
    intro/spawn.webm
  ```
- PNG sequences kept as fallback (`assets/animations/skales_png/`) for skins
  that don't have WebM yet.

**Class: `VideoAnimationController`**

```python
class VideoAnimationController(QObject):
    animation_finished = Signal()   # emitted when a one-shot clip ends
    frame_ready = Signal(QPixmap)   # emitted each decoded frame

    def __init__(self, size: QSize, skin: str) -> None: ...
    def switch_to(self, name: str, loop: bool = True) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

**Implementation notes:**
- Use `QMediaPlayer` + `QVideoSink` to decode WebM frames.
- `QVideoSink.videoFrameChanged` → convert `QVideoFrame` → `QImage` → `QPixmap`
  → emit `frame_ready`.
- For looping: connect `QMediaPlayer.playbackStateChanged` — when `StoppedState`
  and `loop=True`, call `player.setPosition(0); player.play()`.
- For one-shot: when `StoppedState` and `loop=False`, emit `animation_finished`.
- `UIManager` replaces its `AnimationController` with `VideoAnimationController`.
  The `_on_frame` callback and `animation_finished` signal interface are
  identical — minimal changes in `UIManager`.
- Fallback: if `.webm` not found, fall back to PNG loader (keep
  `AnimationController` as `PngAnimationController` in same file).

**`ui_manager.py` changes:**
- Import `VideoAnimationController` instead of `AnimationController`.
- `ASSETS_DIR` now points to `get_bundle_dir() / "assets" / "animations"`.
- `preload_all()` removed (WebM streams on demand, no preload needed).

---

### 4.2 System Tray (`tray_manager.py`)

**Class: `TrayManager(QObject)`**

```python
class TrayManager(QObject):
    show_chat    = Signal()
    hide_chat    = Signal()
    show_settings = Signal()   # Phase 2
    quit_requested = Signal()

    def __init__(self, config: dict, app: QApplication) -> None: ...
    def set_chat_visible(self, visible: bool) -> None: ...  # updates menu label
```

**Behaviour:**
- Icon: `assets/icons/tray.png` (16×16 or 32×32 PNG).
- Left-click (Windows/Linux): toggle chat window visibility.
- Right-click: context menu —
  ```
  Open Chat / Hide Chat
  ─────────────────────
  Reset Pet Position
  Settings           (Phase 2)
  About KIBO
  ─────────────────────
  Quit
  ```
- On main window close event: hide to tray instead of quitting
  (`app.setQuitOnLastWindowClosed(False)` already set).
- Tooltip: `"KIBO — AI Desktop Companion"`.

**Single-instance lock:**
```python
# In main.py, before QApplication:
from PySide6.QtCore import QLockFile
lock_file = QLockFile(str(Path.home() / ".kibo" / "kibo.lock"))
if not lock_file.tryLock(100):
    sys.exit(0)  # another instance is running
```

**`main.py` wiring:**
```python
tray = TrayManager(config, app)
tray.show_chat.connect(chat_window.show)
tray.hide_chat.connect(chat_window.hide)
tray.quit_requested.connect(app.quit)
ui.quit_requested.connect(app.quit)  # existing right-click Quit
```

---

### 4.3 Chat Window (`chat_window.py`)

**Class: `ChatWindow(QWidget)`**

```python
class ChatWindow(QWidget):
    message_sent = Signal(str)   # user typed/spoke a message
    closed       = Signal()

    def __init__(self, config: dict, parent=None) -> None: ...
    def toggle(self) -> None: ...
    def on_chunk(self, chunk: str) -> None: ...      # stream AI tokens
    def on_response_done(self, text: str) -> None: ...
    def on_error(self, msg: str) -> None: ...
    def load_history(self) -> None: ...              # load last session
```

**Visual design:**
- 380×520px, frameless, `Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`.
- `WA_TranslucentBackground` — same glassmorphism as About dialog.
- Background: `QColor(22, 24, 28, 240)` (dark acrylic), rounded corners 12px,
  subtle white border `rgba(255,255,255,40)`.
- Appears near the pet: positioned 10px to the left of the pet window.
  If that overflows screen, appears to the right.
- Drag handle: top 40px bar ("KIBO" label + close button).

**Layout (top → bottom):**
```
┌─────────────────────────────┐
│ ● KIBO                    ✕ │  ← drag handle (40px)
├─────────────────────────────┤
│                             │
│  [conversation history]     │  ← QScrollArea, flex-grow
│                             │
├─────────────────────────────┤
│ [🎤] [text input field] [→] │  ← input bar (52px)
└─────────────────────────────┘
```

**Conversation history widget:**
- Each message is a custom `MessageBubble(QWidget)`:
  - User messages: right-aligned, `rgba(0,255,136,30)` background (neon green tint).
  - KIBO messages: left-aligned, `rgba(255,255,255,10)` background.
  - Timestamp: small grey text below each bubble.
  - Font: `Outfit 10pt` for message text.
- Auto-scrolls to bottom on new message.
- KIBO's in-progress response streams token by token into the current bubble.

**Input bar:**
- `QLineEdit` with dark glass style, placeholder `"Ask KIBO anything..."`.
- Send button (→ arrow icon) or Enter key triggers `message_sent`.
- Microphone button (🎤) triggers existing voice hotkey flow.
- On send: user bubble appears immediately, input clears, KIBO bubble starts
  accumulating chunks.

**Session persistence:**
- On `on_response_done`: append `{role, content, timestamp}` to
  `~/.kibo/conversations/YYYY-MM-DD.json`.
- On `load_history`: read today's file, render last 50 messages on open.

**`main.py` wiring additions:**
```python
chat_window = ChatWindow(config)

# Pet left-click opens chat (add mousePressEvent in UIManager)
ui.pet_clicked.connect(chat_window.toggle)          # new signal on UIManager

# Chat input → AI pipeline
chat_window.message_sent.connect(brain.on_thinking_started)
chat_window.message_sent.connect(
    lambda text: QMetaObject.invokeMethod(
        ai_thread.client, "send_query",
        Qt.QueuedConnection, Q_ARG(str, text)
    )
)

# AI responses → chat window
ai_thread.response_chunk.connect(chat_window.on_chunk)
ai_thread.response_done.connect(chat_window.on_response_done)
ai_thread.error_occurred.connect(chat_window.on_error)

# Memory extraction after each response (async, non-blocking)
ai_thread.response_done.connect(
    lambda text: QTimer.singleShot(0, lambda: memory_store.extract_facts_async(text))
)
```

**`UIManager` change:** Add `pet_clicked = Signal()` and emit it in
`mousePressEvent` on left-click when `_drag_pos` delta < 5px (distinguish
click from drag).

---

### 4.4 Smart Memory (`memory_store.py`)

**Design (ported from Skales `memory-retrieval.ts`):**

Facts are extracted from conversations and stored as JSON files in
`~/.kibo/memories/`. Before each AI call, the top-5 most relevant facts are
retrieved and injected into the system prompt.

**Fact schema (`~/.kibo/memories/<uuid>.json`):**
```json
{
  "id": "uuid4",
  "category": "preference | fact | person | location | task",
  "content": "User prefers dark mode and uses VS Code.",
  "keywords": ["dark", "mode", "vscode", "prefer"],
  "extracted_at": 1712834400,
  "source_session": "2026-04-11"
}
```

**Class: `MemoryStore(QObject)`**

```python
class MemoryStore(QObject):
    facts_updated = Signal()   # emitted after extraction completes

    def __init__(self) -> None: ...

    def extract_facts_async(self, conversation_text: str) -> None:
        """Non-blocking: runs extraction in a QThread."""

    def retrieve_relevant(self, query: str, max_results: int = 5) -> list[dict]:
        """Synchronous, < 50ms. Returns scored facts."""

    def build_memory_prompt(self, query: str) -> str:
        """Returns injected memory string for system prompt."""

    def invalidate_cache(self) -> None: ...
```

**Extraction (LLM-based):**
- After each `response_done`, call Ollama with a cheap extraction prompt:
  ```
  SYSTEM: Extract 0-3 factual memories from this conversation.
          Return JSON array: [{category, content, keywords[]}].
          Only extract durable facts (preferences, names, locations).
          Return [] if nothing worth remembering.
  USER: <last exchange text>
  ```
- Use a fast/small model (configurable: `memory_model` in config, default same
  as main model but with `num_predict: 200`).
- Parse JSON response → write each fact to `~/.kibo/memories/<uuid>.json`.
- Emit `facts_updated`.

**Retrieval scoring (Python port of Skales algorithm):**
```
score = keyword_overlap × 0.70
      + recency_score   × 0.20
      + category_boost  × 0.10
```
- `keyword_overlap`: tokenize query → count matching keywords in fact.
- `recency_score`: `1.0 / (1 + days_since_extracted)`, capped at 1.0.
- `category_boost`: `person=0.15, preference=0.10, task=0.05, else 0`.
- Return top-5 with score > 0, sorted descending.
- 30s in-memory cache (dict keyed by file mtime hash).

**Injection into AI calls (`ai_client.py` change):**
- `AIClient.__init__` takes an optional `MemoryStore` reference.
- In `send_query()`, before building the messages list:
  ```python
  memory_context = self._memory_store.build_memory_prompt(user_text)
  if memory_context:
      system = self._system_prompt + "\n\nWhat you remember:\n" + memory_context
  else:
      system = self._system_prompt
  ```

**Config additions:**
```json
{
  "memory_enabled": true,
  "memory_model": "qwen2.5-coder:7b",
  "memory_max_facts": 200
}
```

---

## 5. Phase 2 — Intelligence (v3)

### 5.1 Notification Router (`notification_router.py`)

Wraps `brain.py`'s speech output with cooldowns and quiet hours.
All proactive speech goes through this router — nothing speaks without its
permission.

**Class: `NotificationRouter(QObject)`**

```python
class NotificationRouter(QObject):
    notification_approved = Signal(str, str)  # (message, notification_type)
    # Wired to: UIManager.show_bubble + Brain._set_ai_state for TALKING

    def route(self, notification_type: str, message: str,
              priority: str = "low") -> bool:
        """Returns True if delivered, False if blocked."""
```

**Notification types and default cooldowns:**

| Type | Cooldown | Priority |
|------|----------|----------|
| `morning-greeting` | 720 min (12h) | low |
| `idle-checkin` | 60 min | low |
| `eod-summary` | 480 min (8h) | low |
| `cpu-panic` | 5 min | medium |
| `battery-low` | 30 min | medium |
| `meeting-reminder` | 25 min | high |
| `email-alert` | 120 min | low |
| `task-blocked` | 60 min | medium |

**Quiet hours:**
- Config: `quiet_hours_start` (default 22), `quiet_hours_end` (default 7).
- `high` priority bypasses quiet hours.
- State persisted to `~/.kibo/proactive_state.json`:
  ```json
  {
    "cooldowns": {"morning-greeting": 1712834400},
    "last_user_interaction": 1712834400
  }
  ```

**`brain.py` change:**
- Existing speech output in `on_sensor_update` routes through `NotificationRouter`
  before emitting. If blocked → emit `BrainOutput` with `speech_text=None`
  (animation updates still fire).

---

### 5.2 Proactive Engine (`proactive_engine.py`)

A heartbeat timer (60s tick) that gathers context and fires notifications
independently of user interaction.

**Class: `ProactiveEngine(QObject)`**

```python
class ProactiveEngine(QObject):
    proactive_notification = Signal(str, str)  # (message, type)
    # Connect to: NotificationRouter.route()

    def __init__(self, config: dict, router: NotificationRouter) -> None: ...
    def start(self) -> None: ...   # starts 60s QTimer
    def stop(self) -> None: ...
    def update_last_interaction(self) -> None: ...  # called on any user input
```

**Context gathered each tick:**
```python
@dataclass(frozen=True)
class ProactiveContext:
    idle_minutes: int
    current_hour: int
    tasks_pending: int        # Phase 3: from task_runner
    tasks_blocked: int        # Phase 3: from task_runner
    tasks_done_today: int     # Phase 3: from task_runner
    next_meeting_minutes: int # Phase 3: from calendar_manager (-1 = none)
    unread_emails: int        # Phase 3: from email integration (-1 = unknown)
```

**Rules (priority-ordered, first match wins):**

```python
RULES = [
    # HIGH — bypass quiet hours
    ProactiveRule(
        type="meeting-reminder",
        condition=lambda ctx: 0 < ctx.next_meeting_minutes <= 30,
        message=lambda ctx: f"⏰ Meeting in {ctx.next_meeting_minutes} min!",
        priority="high",
        enabled_phase=3,
    ),
    # MEDIUM
    ProactiveRule(
        type="battery-low",
        condition=lambda ctx: ctx.battery_percent is not None and ctx.battery_percent < 20,
        message=lambda _: "🔋 Running low on battery...",
        priority="medium",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="task-blocked",
        condition=lambda ctx: ctx.tasks_blocked > 0,
        message=lambda ctx: f"⚠️ {ctx.tasks_blocked} task(s) are blocked.",
        priority="medium",
        enabled_phase=3,
    ),
    # LOW
    ProactiveRule(
        type="morning-greeting",
        condition=lambda ctx: 7 <= ctx.current_hour < 9,
        message=lambda ctx: "☀️ Good morning! Ready to get things done?",
        priority="low",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes > 45 and ctx.tasks_pending > 0,
        message=lambda ctx: f"💤 You've been idle {ctx.idle_minutes} min. {ctx.tasks_pending} task(s) waiting.",
        priority="low",
        enabled_phase=3,
    ),
    ProactiveRule(
        type="eod-summary",
        condition=lambda ctx: 16 <= ctx.current_hour < 19 and ctx.tasks_done_today >= 3,
        message=lambda ctx: f"✅ Great work! {ctx.tasks_done_today} tasks done today.",
        priority="low",
        enabled_phase=3,
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes > 60,
        message=lambda _: "👋 Still there? Anything I can help with?",
        priority="low",
        enabled_phase=1,  # works even without tasks
    ),
]
```

**Idle tracking:**
- Any user input (hotkey, chat message, mouse click on pet) → calls
  `engine.update_last_interaction()`.
- Idle = `(now - last_interaction).seconds // 60`.

---

### 5.3 Settings Window (`settings_window.py`)

Frameless glass panel, 480×600px, same visual language as ChatWindow.

**Class: `SettingsWindow(QWidget)`**

```python
class SettingsWindow(QWidget):
    settings_changed = Signal(dict)  # emits new config dict on Save
    closed = Signal()
```

**Tabs:**

| Tab | Settings |
|-----|----------|
| **General** | Pet name, buddy skin (dropdown with icon previews), activation hotkey |
| **AI** | ai_enabled toggle, Ollama URL, model name, system prompt (text area), memory_enabled toggle |
| **Notifications** | Quiet hours start/end (spinboxes), per-type enable/disable toggles, proactive_enabled master toggle |
| **Appearance** | Window size (slider 150–300px), frame_rate_ms, opaque_fallback toggle, speech bubble timeout |

**Save behaviour:**
- "Save" button: serialize tab values → write to `config.json` via `get_app_root() / "config.json"`.
- Emit `settings_changed` with new config.
- Components that support hot-reload: `SpeechBubble` timeout, `SystemMonitor` poll interval.
- Components requiring restart: skin change, window size, AI model.
- Show restart banner (`"Some changes require restart"`) when restart-required
  fields change.

**Accessing Settings:**
- Via tray menu → "Settings".
- Via right-click context menu on pet → "Settings" (replace current About-only menu).

---

## 6. Phase 3 — Integrations (v4)

### 6.1 Calendar Manager (`calendar_manager.py`)

**Class: `CalendarManager(QObject)`**

```python
class CalendarManager(QObject):
    events_updated = Signal(list)   # list of CalendarEvent dicts

    def start(self) -> None: ...    # poll every 15 minutes
    def stop(self) -> None: ...
    def get_next_event(self) -> dict | None: ...
```

**Providers (plug-in pattern, one at a time):**
- **Google Calendar:** `google-auth-oauthlib` + `googleapiclient`. OAuth2 flow
  opens system browser first time. Token saved to `~/.kibo/google_token.json`.
- **Outlook (Microsoft Graph):** `msal` library. Device-code or browser OAuth.
  Token saved to `~/.kibo/ms_token.json`.
- **CalDAV (Apple/generic):** `caldav` library. Username/password or token.

**Config:**
```json
{
  "calendar_provider": "none | google | outlook | caldav",
  "calendar_lookahead_minutes": 60
}
```

**Integration with ProactiveEngine:**
- `CalendarManager.events_updated` → `ProactiveEngine.on_calendar_updated`.
- ProactiveEngine checks `next_meeting_minutes` from calendar on each tick.

---

### 6.2 Autonomous Task Runner (`task_runner.py`)

Allows users to give KIBO tasks that run in the background via Ollama.

**Task schema (`~/.kibo/tasks.json`):**
```json
{
  "id": "uuid4",
  "title": "Draft a weekly summary email",
  "description": "...",
  "state": "pending | in_progress | completed | failed | blocked | cancelled",
  "priority": "low | medium | high",
  "source": "user | scheduled | proactive",
  "retry_count": 0,
  "max_retries": 3,
  "requires_approval": false,
  "created_at": 1712834400,
  "completed_at": null,
  "result": null,
  "error": null
}
```

**Class: `TaskRunner(QObject)`**

```python
class TaskRunner(QObject):
    task_completed  = Signal(dict)  # task dict
    task_failed     = Signal(dict)
    task_blocked    = Signal(dict)
    task_started    = Signal(dict)
    status_update   = Signal(str)   # log line

    def __init__(self, config: dict, ai_client: AIClient) -> None: ...
    def add_task(self, title: str, description: str) -> str: ...  # returns task id
    def cancel_task(self, task_id: str) -> None: ...
    def get_tasks(self) -> list[dict]: ...
    def start(self) -> None: ...   # begins heartbeat timer (30s)
    def stop(self) -> None: ...
```

**Anti-loop protocol (ported from Skales):**
- `retry_count` incremented on each failed attempt.
- After `max_retries` (default 3): task moves to `blocked` state.
- `ProactiveEngine` detects `blocked` tasks and notifies user.

**Rate limiting:**
- Max 20 Ollama calls per hour (shared with chat).
- Counter persisted to `~/.kibo/cost_state.json`.
- If limit hit: tasks queue, user notified via proactive notification.

**Approval gate:**
- Tasks with `requires_approval=True` pause at `pending` and emit
  `task_blocked` with reason `"awaiting_approval"`.
- Chat window shows approval prompt: `[Run] [Cancel]`.

---

## 7. Full Signal Wiring (main.py after all phases)

```python
# ── Tray ──────────────────────────────────────────────────────────
tray.show_chat.connect(chat_window.show)
tray.hide_chat.connect(chat_window.hide)
tray.show_settings.connect(settings_window.show)    # Phase 2
tray.quit_requested.connect(app.quit)

# ── Pet click → Chat ──────────────────────────────────────────────
ui.pet_clicked.connect(chat_window.toggle)

# ── Chat input → AI (queued, thread-safe) ─────────────────────────
chat_window.message_sent.connect(brain.on_thinking_started)
chat_window.message_sent.connect(
    lambda t: QMetaObject.invokeMethod(
        ai_thread.client, "send_query",
        Qt.QueuedConnection, Q_ARG(str, t)
    )
)
chat_window.message_sent.connect(proactive_engine.update_last_interaction)  # Phase 2

# ── AI → Chat + Memory ────────────────────────────────────────────
ai_thread.response_chunk.connect(chat_window.on_chunk)
ai_thread.response_chunk.connect(ui.on_response_chunk)
ai_thread.response_done.connect(chat_window.on_response_done)
ai_thread.response_done.connect(brain.on_talking_started)
ai_thread.response_done.connect(
    lambda t: QTimer.singleShot(0, lambda: memory_store.extract_facts_async(t))  # Phase 1
)
ai_thread.error_occurred.connect(chat_window.on_error)
ai_thread.error_occurred.connect(ui.on_ai_error)
ai_thread.error_occurred.connect(lambda _: brain.on_ai_done())

# ── Proactive Engine → Notification Router ────────────────────────
proactive_engine.proactive_notification.connect(notification_router.route)   # Phase 2
notification_router.notification_approved.connect(ui.show_bubble)            # Phase 2

# ── Task Runner → Proactive ───────────────────────────────────────
task_runner.task_completed.connect(proactive_engine.on_task_completed)        # Phase 3
task_runner.task_blocked.connect(proactive_engine.on_task_blocked)            # Phase 3

# ── Calendar → Proactive ──────────────────────────────────────────
calendar_manager.events_updated.connect(proactive_engine.on_calendar_updated) # Phase 3

# ── Settings ──────────────────────────────────────────────────────
settings_window.settings_changed.connect(ui.on_config_changed)               # Phase 2
settings_window.settings_changed.connect(system_monitor.on_config_changed)   # Phase 2
```

---

## 8. Config Schema (full v4)

```json
{
  "pet_name": "KIBO",
  "buddy_skin": "skales",
  "window_size": [200, 200],
  "frame_rate_ms": 150,
  "opaque_fallback": false,
  "enable_speech_bubbles": true,
  "speech_bubble_timeout_ms": 5000,

  "ai_enabled": true,
  "activation_hotkey": "ctrl+k",
  "ollama_base_url": "http://localhost:11434",
  "ollama_model": "qwen2.5-coder:7b",
  "system_prompt": "...",
  "conversation_history_limit": 10,

  "tts_enabled": true,
  "tts_rate": 175,

  "memory_enabled": true,
  "memory_model": "qwen2.5-coder:7b",
  "memory_max_facts": 200,

  "poll_interval_ms": 3000,
  "cpu_panic_threshold": 80,
  "battery_tired_threshold": 20,
  "sleepy_hour": 23,
  "studious_windows": ["Visual Studio Code", "code"],
  "idle_action_interval_min_s": 30,
  "idle_action_interval_max_s": 60,

  "proactive_enabled": true,
  "quiet_hours_start": 22,
  "quiet_hours_end": 7,
  "notification_types": {
    "morning-greeting": true,
    "idle-checkin": true,
    "eod-summary": true,
    "cpu-panic": true,
    "battery-low": true,
    "meeting-reminder": true,
    "email-alert": true,
    "task-blocked": true
  },

  "calendar_provider": "none",
  "calendar_lookahead_minutes": 60,

  "recording_max_seconds": 8,
  "silence_threshold_seconds": 1.5,
  "whisper_model": "tiny.en"
}
```

---

## 9. Implementation Order (for Gemini Pro)

### Phase 1 — v2 (implement in this exact order)

1. **`config_manager.py`** — add `get_user_data_dir()`.
2. **`tray_manager.py`** — full `TrayManager` class + single-instance lock in `main.py`.
3. **`animation_engine.py`** — `VideoAnimationController` + `PngAnimationController` fallback.
4. **Migrate assets** — copy WebM files from `REF_PROJECT/apps/web/public/mascot/skales/` to `assets/animations/skales/`.
5. **`ui_manager.py`** — swap `AnimationController` for `VideoAnimationController`, add `pet_clicked` signal.
6. **`chat_window.py`** — full `ChatWindow` + `MessageBubble`, session persistence.
7. **`memory_store.py`** — `MemoryStore` with extraction + retrieval.
8. **`ai_client.py`** — inject memory context into system prompt.
9. **`main.py`** — wire everything (Phase 1 wiring block above).
10. **Tests** — update existing 51 tests + add Phase 1 unit tests.
11. **`KIBO.spec`** — ensure `assets/` structure change is reflected.

### Phase 2 — v3 (after v2 ships and is stable)

1. **`notification_router.py`** — `NotificationRouter` + cooldown persistence.
2. **`brain.py`** — route speech output through `NotificationRouter`.
3. **`proactive_engine.py`** — `ProactiveEngine` + all Phase 1 rules.
4. **`settings_window.py`** — full `SettingsWindow` with 4 tabs.
5. **`main.py`** — Phase 2 wiring additions.
6. **`config_manager.py`** — validate new config keys (proactive, quiet hours, notification types).

### Phase 3 — v4 (after v3 ships and is stable)

1. **`task_runner.py`** — `TaskRunner` + task persistence + anti-loop + rate limiting.
2. **`calendar_manager.py`** — `CalendarManager` with Google provider first.
3. **`chat_window.py`** — add task approval UI (approve/reject buttons).
4. **`proactive_engine.py`** — add Phase 3 rules (tasks, calendar, idle+tasks).
5. **`main.py`** — Phase 3 wiring additions.

---

## 10. Testing Strategy

- **Unit tests:** Each new module has a corresponding `tests/test_<module>.py`.
- **No Qt in unit tests:** `MemoryStore`, `NotificationRouter`, `ProactiveEngine`
  logic is tested with pure Python (no `QApplication` needed).
- **Mock Ollama:** Use `unittest.mock` to patch `httpx.Client` in `AIClient` tests.
- **Target:** Maintain 80%+ coverage on all new modules.
- **Existing:** 51/51 tests must remain green after each phase.

---

## 11. Security Checklist

- [ ] No API keys or secrets in source code.
- [ ] OAuth tokens stored in `~/.kibo/` (user-owned, not EXE dir).
- [ ] AI responses sanitized before display (no raw HTML injection in `QLabel`
      — use `setText()` not `setHtml()` for untrusted content).
- [ ] Task runner: no shell execution without explicit user approval gate.
- [ ] Memory extraction: user can wipe all memories (`Settings > Clear Memory`).
- [ ] Calendar tokens: revocable from Settings, stored encrypted (Phase 3).

---

## 12. Non-Goals (explicitly out of scope)

- No Electron/browser stack migration — stays Python/PySide6.
- No multi-agent organization (Skales feature — too complex for current scope).
- No built-in browser agent.
- No image/video generation.
- No Discord/Telegram/WhatsApp bots.
- No cloud sync.
