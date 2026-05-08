# Phase 1 Design: Python Backend API Layer

**Date:** 2026-05-07  
**Status:** Approved

## Goal

Decouple the Python backend from PySide6 so it can serve the future Electron frontend via FastAPI/WebSocket, while keeping the existing PySide6 desktop app fully functional as a parallel entry point.

## Threading Model: threading.Thread + threading.Event + queue.Queue

QTimer (requires QApplication event loop to fire) is replaced with `threading.Event.wait()` polling loops. QThread (wraps threading.Thread) is replaced with threading.Thread directly. QMetaObject.invokeMethod (cross-thread dispatch) is replaced with queue.Queue. This is a 1:1 semantic replacement — no new paradigm, no asyncio complexity inside workers.

## EventBus

`src/api/event_bus.py` — thread-safe synchronous pub/sub:
- `on(event, handler)` — register a callback
- `emit(event, *args)` — call all registered handlers on the calling thread
- `off(event, handler)` — deregister
- Internal `threading.Lock` protects the handler registry

All backend-to-backend and backend-to-UI communication flows through this bus. Handlers run on the emitting thread; callers are responsible for thread-safety of their own state.

## FastAPI Server

`src/api/server.py`:
- `WS /ws/chat` — user query in, streaming tokens out, done signal
- `WS /ws/state` — broadcasts animation/pet state changes
- `GET /POST /settings` — config CRUD
- `GET /DELETE /PUT /memory` — memory CRUD  
- `GET /health` — provider health check
- `POST /voice/start`, `POST /hotkey/clip`

Server subscribes to event_bus on startup. WebSocket delivery bridges threading → asyncio via `asyncio.run_coroutine_threadsafe()` at the server boundary only.

## Entry Points

**`src/api/main.py`** (new) — Pure Python, no Qt:
- Instantiates all backend components with a shared EventBus
- Wires via `event_bus.on()` 
- Runs uvicorn

**`main.py`** (modified) — Qt desktop app still works:
- Creates shared EventBus
- Backend components receive event_bus in constructor
- UI → backend: Qt signal connections kept (Qt signals can connect to plain functions)
- Backend → UI: `event_bus.on('event', qt_safe(ui_method))` where `qt_safe` wraps via `QTimer.singleShot(0, fn)` — the only thread-safe Qt API callable from any thread

## File Change Map

### New Files
| File | Purpose | Size |
|------|---------|------|
| `src/api/__init__.py` | Package marker | 1 line |
| `src/api/event_bus.py` | Thread-safe pub/sub | ~40 lines |
| `src/api/server.py` | FastAPI + WebSocket | ~150 lines |
| `src/api/main.py` | FastAPI entry point | ~100 lines |

### Backend Files Modified (remove QObject/Signal/QThread/QTimer)
| File | Key Change |
|------|-----------|
| `src/ai/brain.py` | QTimer → PeriodicThread, Signal → event_bus.emit |
| `src/system/system_monitor.py` | QTimer → PeriodicThread, Signal → event_bus.emit |
| `src/system/calendar_manager.py` | QTimer → PeriodicThread, Signal → event_bus.emit |
| `src/system/proactive_engine.py` | QTimer → PeriodicThread, Signal → event_bus.emit |
| `src/system/task_runner.py` | QTimer → PeriodicThread, Signal → event_bus.emit |
| `src/system/notification_router.py` | QObject/Signal/@Slot removed |
| `src/ai/memory_store.py` | QObject/Signal/@Slot removed |
| `src/ai/sentence_buffer.py` | QObject/Signal/@Slot removed |
| `src/ai/ai_client.py` | AIThread: QThread → Thread + queue.Queue |
| `src/ai/tts_manager.py` | TTSThread: QThread → Thread + queue.Queue |
| `src/ai/voice_listener.py` | VoiceThread: QThread → Thread |
| `src/system/hotkey_listener.py` | HotkeyThread: QThread → Thread |

### Modified Entry Point
| File | Key Change |
|------|-----------|
| `main.py` | Signal wiring → event_bus.on() + qt_safe() for UI callbacks |

### Untouched (all UI files)
`src/ui/animation_engine.py`, `src/ui/chat_window.py`, `src/ui/settings_window.py`, `src/ui/onboarding_window.py`, `src/ui/tray_manager.py`, `src/ui/ui_manager.py`, `src/ui/clip_recorder.py`

## PeriodicThread Pattern

Replaces every `QTimer(self); timer.timeout.connect(fn); timer.start(interval_ms)`:

```python
class PeriodicThread(threading.Thread):
    def __init__(self, interval_ms: int, callback: Callable) -> None:
        super().__init__(daemon=True)
        self._interval = interval_ms / 1000.0
        self._callback = callback
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            self._callback()

    def stop(self) -> None:
        self._stop.set()
```

## qt_safe Bridge Pattern

Used in main.py to marshal event_bus callbacks to the Qt main thread:

```python
def qt_safe(fn: Callable) -> Callable:
    def wrapper(*args):
        QTimer.singleShot(0, lambda: fn(*args))
    return wrapper

event_bus.on('brain_output', qt_safe(ui.on_brain_output))
```

## Invariants

- **Zero logic changes** — only the communication layer changes
- **UI files untouched** — no PySide6 removed from animation_engine, chat_window, etc.
- **Both entry points work** — `python main.py` (Qt app) and `python src/api/main.py` (FastAPI)
- **Thread safety** — EventBus uses Lock; queue.Queue for cross-thread method dispatch; qt_safe for Qt UI marshaling
- **Existing tests stay green** — backend logic is unchanged, only the wiring changes

## Risks

- `QMetaObject.invokeMethod` in `main.py` (send_query dispatch to AIThread) must be replaced with queue.Queue.put() — high-priority change
- `tts_manager.py` uses internal QMetaObject for self-dispatch — must be replaced carefully
- `brain.py` _action_timer logic is complex; PeriodicThread replacement must preserve start/stop/restart semantics
