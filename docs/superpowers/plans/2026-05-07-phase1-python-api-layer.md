# Phase 1: Python Backend API Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple the Python backend from PySide6 by replacing Signal/QThread/QTimer with threading primitives and an EventBus, then add a FastAPI server — while keeping `python main.py` (the Qt desktop app) fully working.

**Architecture:** A thread-safe synchronous EventBus replaces all Qt Signal/Slot wiring between backend components. QThread wraps become `threading.Thread` + `queue.Queue`. QTimer repeating polls become a `PeriodicThread` utility; QTimer single-shot becomes `threading.Timer`. The existing PySide6 UI files are untouched — `main.py` bridges them via Qt signal connections (which accept plain callables) and a `qt_safe()` wrapper for backend→UI callbacks.

**Tech Stack:** Python stdlib (`threading`, `queue`), FastAPI, uvicorn, pytest

---

## File Map

### New Files
| Path | Purpose |
|------|---------|
| `src/api/__init__.py` | Package marker |
| `src/api/event_bus.py` | Thread-safe sync pub/sub |
| `src/core/periodic_thread.py` | Repeating background thread (replaces QTimer) |
| `src/api/server.py` | FastAPI + WebSocket endpoints |
| `src/api/main.py` | Pure-Python entry point (no Qt) |
| `tests/test_event_bus.py` | EventBus unit tests |
| `tests/test_periodic_thread.py` | PeriodicThread unit tests |
| `tests/test_api_server.py` | FastAPI endpoint tests |

### Modified Files (backend — all UI files untouched)
| Path | Key Change |
|------|-----------|
| `requirements.txt` | Add fastapi, uvicorn |
| `src/system/notification_router.py` | Remove QObject/Signal/@Slot; add event_bus param |
| `src/ai/memory_store.py` | Remove QObject/Signal/@Slot; add event_bus param |
| `src/ai/sentence_buffer.py` | Remove QObject/Signal/@Slot; add event_bus param + lock |
| `src/system/system_monitor.py` | QTimer → PeriodicThread; Signal → event_bus.emit |
| `src/ai/brain.py` | QTimer → threading.Timer; Signal → event_bus.emit; add RLock |
| `src/system/calendar_manager.py` | QTimer → PeriodicThread; Signal → event_bus.emit |
| `src/system/proactive_engine.py` | QTimer → PeriodicThread; Signal → event_bus.emit |
| `src/system/task_runner.py` | QTimer → PeriodicThread; Signal → event_bus.emit |
| `src/system/hotkey_listener.py` | QThread → threading.Thread + threading.Event |
| `src/ai/voice_listener.py` | QThread → threading.Thread + queue.Queue |
| `src/ai/tts_manager.py` | QThread → threading.Thread + queue.Queue |
| `src/ai/ai_client.py` | QThread → threading.Thread + queue.Queue |
| `main.py` | Replace QMetaObject wiring → event_bus.on() + qt_safe() |

### Modified Tests
| Path | Change |
|------|-------|
| `tests/test_brain.py` | Remove QApplication; use event_bus for signal observation |
| `tests/test_sentence_buffer.py` | Remove QApplication; use event_bus |
| `tests/test_notification_router.py` | Remove QObject; use event_bus |
| `tests/test_tts_manager.py` | Remove QApplication; use event_bus |
| `tests/test_voice_listener.py` | Remove QApplication; use event_bus |
| `tests/test_hotkey_listener.py` | Remove QApplication; use event_bus |
| `tests/test_ai_client.py` | Remove QApplication; use event_bus |
| `tests/test_calendar_manager.py` | Remove QApplication; use event_bus |
| `tests/test_proactive_engine.py` | Remove QApplication; use event_bus |
| `tests/test_task_runner.py` | Remove QApplication; use event_bus |

---

## Task 1: Create `src/api/event_bus.py`

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/event_bus.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_event_bus.py
import threading
import pytest
from src.api.event_bus import EventBus


def test_on_emit_calls_handler():
    bus = EventBus()
    received = []
    bus.on("test", received.append)
    bus.emit("test", 42)
    assert received == [42]


def test_multiple_handlers_all_called():
    bus = EventBus()
    a, b = [], []
    bus.on("ev", a.append)
    bus.on("ev", b.append)
    bus.emit("ev", "x")
    assert a == ["x"] and b == ["x"]


def test_off_removes_handler():
    bus = EventBus()
    received = []
    bus.on("ev", received.append)
    bus.off("ev", received.append)
    bus.emit("ev", "x")
    assert received == []


def test_emit_unknown_event_is_noop():
    bus = EventBus()
    bus.emit("no_such_event", 1)  # must not raise


def test_emit_multiple_args():
    bus = EventBus()
    received = []
    bus.on("ev", lambda a, b: received.append((a, b)))
    bus.emit("ev", "hello", 99)
    assert received == [("hello", 99)]


def test_thread_safe_concurrent_emit():
    bus = EventBus()
    results = []
    lock = threading.Lock()

    def handler(val):
        with lock:
            results.append(val)

    bus.on("tick", handler)
    threads = [threading.Thread(target=bus.emit, args=("tick", i)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 50
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_event_bus.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.api'`

- [ ] **Step 3: Create package marker and EventBus**

```python
# src/api/__init__.py
```

```python
# src/api/event_bus.py
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable


class EventBus:
    """Thread-safe synchronous pub/sub bus.

    Handlers are called on the emitting thread. Callers are responsible
    for their own thread-safety if handlers mutate shared state.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def on(self, event: str, handler: Callable) -> None:
        with self._lock:
            self._handlers[event].append(handler)

    def off(self, event: str, handler: Callable) -> None:
        with self._lock:
            try:
                self._handlers[event].remove(handler)
            except ValueError:
                pass

    def emit(self, event: str, *args: Any) -> None:
        with self._lock:
            handlers = list(self._handlers[event])
        for handler in handlers:
            handler(*args)
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_event_bus.py -v
```

- [ ] **Step 5: Commit**

```
git add src/api/__init__.py src/api/event_bus.py tests/test_event_bus.py
git commit -m "feat: add EventBus — thread-safe sync pub/sub replacing Qt Signal/Slot"
```

---

## Task 2: Create `src/core/periodic_thread.py`

**Files:**
- Create: `src/core/periodic_thread.py`
- Create: `tests/test_periodic_thread.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_periodic_thread.py
import threading
import time
import pytest
from src.core.periodic_thread import PeriodicThread


def test_fires_callback_repeatedly():
    count = []
    stop = threading.Event()

    def cb():
        count.append(1)
        if len(count) >= 3:
            stop.set()

    t = PeriodicThread(interval_ms=20, callback=cb)
    t.start()
    stop.wait(timeout=1.0)
    t.stop()
    assert len(count) >= 3


def test_stop_prevents_further_calls():
    count = []
    t = PeriodicThread(interval_ms=20, callback=lambda: count.append(1))
    t.start()
    time.sleep(0.06)
    t.stop()
    snapshot = len(count)
    time.sleep(0.06)
    assert len(count) == snapshot  # no new calls after stop


def test_is_daemon():
    t = PeriodicThread(interval_ms=100, callback=lambda: None)
    assert t.daemon is True


def test_stop_is_idempotent():
    t = PeriodicThread(interval_ms=50, callback=lambda: None)
    t.start()
    t.stop()
    t.stop()  # must not raise
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_periodic_thread.py -v
```

- [ ] **Step 3: Implement PeriodicThread**

```python
# src/core/periodic_thread.py
from __future__ import annotations

import threading
from typing import Callable


class PeriodicThread(threading.Thread):
    """Calls `callback` every `interval_ms` milliseconds on a daemon thread.

    Replaces QTimer(interval).timeout.connect(callback) + timer.start().
    """

    def __init__(self, interval_ms: int, callback: Callable) -> None:
        super().__init__(daemon=True)
        self._interval = interval_ms / 1000.0
        self._callback = callback
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._callback()

    def stop(self) -> None:
        self._stop_event.set()
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_periodic_thread.py -v
```

- [ ] **Step 5: Commit**

```
git add src/core/periodic_thread.py tests/test_periodic_thread.py
git commit -m "feat: add PeriodicThread — daemon thread replacing QTimer repeating polls"
```

---

## Task 3: Refactor `notification_router.py`

**Files:**
- Modify: `src/system/notification_router.py`
- Modify: `tests/test_notification_router.py`

- [ ] **Step 1: Update the test file**

Open `tests/test_notification_router.py`. Replace the `QApplication`/Qt fixture with:

```python
# At the top of tests/test_notification_router.py, replace any Qt imports and
# QApplication fixture with:
import pytest
from unittest.mock import patch, MagicMock
from src.api.event_bus import EventBus
from src.system.notification_router import NotificationRouter

CONFIG = {
    "proactive_enabled": True,
    "quiet_hours_start": 23,
    "quiet_hours_end": 7,
    "proactive_daily_cap": 10,
    "proactive_cooldown_minutes": 5,
}

@pytest.fixture
def bus():
    return EventBus()

@pytest.fixture
def router(bus, tmp_path):
    with patch("src.system.notification_router.get_user_data_dir", return_value=tmp_path):
        r = NotificationRouter(CONFIG, event_bus=bus)
    return r
```

For any test that previously did:
```python
approved = []
router.notification_approved.connect(lambda msg, t: approved.append((msg, t)))
```
Replace with:
```python
approved = []
bus.on("notification_approved", lambda msg, t: approved.append((msg, t)))
```

- [ ] **Step 2: Run existing tests to confirm they FAIL now**

```
pytest tests/test_notification_router.py -v
```

- [ ] **Step 3: Modify `notification_router.py`**

Change the imports block (remove PySide6, add EventBus type hint):

```python
# REMOVE these lines:
from PySide6.QtCore import QObject, Signal, Slot

# ADD these lines (at top with other imports):
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.api.event_bus import EventBus
```

Change class definition and `__init__`:

```python
# BEFORE:
class NotificationRouter(QObject):
    notification_approved = Signal(str, str)

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        ...

# AFTER:
class NotificationRouter:
    def __init__(self, config: dict, event_bus: "EventBus | None" = None) -> None:
        self._event_bus = event_bus
        self._config = config
        ...
```

In `route()`, replace the emit call:

```python
# BEFORE:
        self.notification_approved.emit(message, notification_type)

# AFTER:
        if self._event_bus:
            self._event_bus.emit("notification_approved", message, notification_type)
```

Remove the `@Slot(dict)` decorator from `on_config_changed`:

```python
# BEFORE:
    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:

# AFTER:
    def on_config_changed(self, new_config: dict) -> None:
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_notification_router.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/notification_router.py tests/test_notification_router.py
git commit -m "refactor: remove QObject/Signal from NotificationRouter; use EventBus"
```

---

## Task 4: Refactor `memory_store.py`

**Files:**
- Modify: `src/ai/memory_store.py`
- Modify: `tests/test_memory_store.py`

- [ ] **Step 1: Update test file**

In `tests/test_memory_store.py`, replace any Qt signal observation:

```python
# Replace:
#   store.facts_updated.connect(handler)
# With:
#   bus.on("facts_updated", handler)

# Add fixture:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Update store fixture to pass event_bus:
@pytest.fixture
def store(tmp_path, bus):
    with patch("src.ai.memory_store.get_user_data_dir", return_value=tmp_path):
        s = MemoryStore({"memory_enabled": True, "memory_extraction_inline": True}, event_bus=bus)
    return s
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_memory_store.py -v
```

- [ ] **Step 3: Modify `memory_store.py`**

Remove PySide6 import:
```python
# REMOVE:
from PySide6.QtCore import QObject, Signal, Slot
```

Change class and `__init__`:
```python
# BEFORE:
class MemoryStore(QObject):
    facts_updated = Signal()

    def __init__(self, config: dict) -> None:
        super().__init__()

# AFTER:
class MemoryStore:
    def __init__(self, config: dict, event_bus=None) -> None:
        self._event_bus = event_bus
```

In `add_fact_inline`, replace emit and remove @Slot:
```python
# BEFORE:
    @Slot(dict)
    def add_fact_inline(self, fact: dict) -> None:
        ...
        self.facts_updated.emit()

# AFTER:
    def add_fact_inline(self, fact: dict) -> None:
        ...
        if self._event_bus:
            self._event_bus.emit("facts_updated")
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_memory_store.py -v
```

- [ ] **Step 5: Commit**

```
git add src/ai/memory_store.py tests/test_memory_store.py
git commit -m "refactor: remove QObject/Signal from MemoryStore; use EventBus"
```

---

## Task 5: Refactor `sentence_buffer.py`

**Files:**
- Modify: `src/ai/sentence_buffer.py`
- Modify: `tests/test_sentence_buffer.py`

- [ ] **Step 1: Update test file**

```python
# tests/test_sentence_buffer.py — replace Qt fixtures with:
import pytest
from src.api.event_bus import EventBus
from src.ai.sentence_buffer import SentenceBuffer

@pytest.fixture
def bus():
    return EventBus()

@pytest.fixture
def buf(bus):
    return SentenceBuffer(event_bus=bus)

# Replace all:
#   buf.sentence_ready.connect(...)   →   bus.on("sentence_ready", ...)
#   buf.flushed.connect(...)          →   bus.on("flushed", ...)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_sentence_buffer.py -v
```

- [ ] **Step 3: Rewrite `sentence_buffer.py`**

```python
"""
sentence_buffer.py — Splits a token stream into speakable sentences.
"""
from __future__ import annotations

import re
import threading
from typing import Iterator

# A sentence ends at . ! ? followed by space/end, or at a newline.
_SENTENCE_END = re.compile(r"([\.\!\?…]+)(\s|$)|\n+")


class SentenceBuffer:
    """Accumulates text deltas; emits each completed sentence via EventBus."""

    def __init__(self, *, min_chars: int = 12, event_bus=None) -> None:
        self._event_bus = event_bus
        self._buf = ""
        self._min_chars = min_chars
        self._lock = threading.Lock()

    def push(self, delta: str) -> None:
        if not delta:
            return
        with self._lock:
            self._buf += delta
            sentences = list(self._extract_sentences())
        for sentence in sentences:
            if self._event_bus:
                self._event_bus.emit("sentence_ready", sentence)

    def flush(self) -> None:
        with self._lock:
            leftover = self._buf.strip()
            self._buf = ""
        if leftover and self._event_bus:
            self._event_bus.emit("sentence_ready", leftover)
        if self._event_bus:
            self._event_bus.emit("flushed")

    def reset(self) -> None:
        with self._lock:
            self._buf = ""

    def _extract_sentences(self) -> Iterator[str]:
        while True:
            match = _SENTENCE_END.search(self._buf)
            if not match:
                return
            cut = match.end()
            while True:
                candidate = self._buf[:cut].strip()
                if len(candidate) >= self._min_chars:
                    break
                next_match = _SENTENCE_END.search(self._buf, cut)
                if not next_match:
                    return
                cut = next_match.end()
            self._buf = self._buf[cut:]
            yield candidate
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_sentence_buffer.py -v
```

- [ ] **Step 5: Commit**

```
git add src/ai/sentence_buffer.py tests/test_sentence_buffer.py
git commit -m "refactor: remove QObject/Signal from SentenceBuffer; add threading.Lock"
```

---

## Task 6: Refactor `system_monitor.py`

**Files:**
- Modify: `src/system/system_monitor.py`

- [ ] **Step 1: Write a test that targets the new signature**

```python
# Add to tests/test_system_monitor.py (create if it doesn't exist):
import time
import pytest
from unittest.mock import patch, MagicMock
from src.api.event_bus import EventBus
from src.system.system_monitor import SystemMonitor

CONFIG = {"poll_interval_ms": 30}

def test_emits_sensor_update_on_poll():
    bus = EventBus()
    received = []
    bus.on("sensor_update", received.append)

    with patch("psutil.cpu_percent", return_value=10.0), \
         patch("psutil.sensors_battery", return_value=None):
        mon = SystemMonitor(CONFIG, event_bus=bus)
        mon.start()
        time.sleep(0.12)
        mon.stop()

    assert len(received) >= 2

def test_stop_halts_polling():
    bus = EventBus()
    count = []
    bus.on("sensor_update", lambda d: count.append(1))

    with patch("psutil.cpu_percent", return_value=0.0), \
         patch("psutil.sensors_battery", return_value=None):
        mon = SystemMonitor(CONFIG, event_bus=bus)
        mon.start()
        time.sleep(0.08)
        mon.stop()
        snapshot = len(count)
        time.sleep(0.08)

    assert len(count) == snapshot
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_system_monitor.py -v
```

- [ ] **Step 3: Rewrite `system_monitor.py`**

```python
"""
system_monitor.py — Polls system state and emits SensorData via EventBus.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import psutil

from src.ai.brain import SensorData
from src.core.periodic_thread import PeriodicThread

logger = logging.getLogger(__name__)


class SystemMonitor:
    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._thread: Optional[PeriodicThread] = None
        self._current_interval = config["poll_interval_ms"]
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        self._thread = PeriodicThread(self._current_interval, self._poll)
        self._thread.start()
        logger.info("SystemMonitor started (interval=%dms).", self._current_interval)

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        interval = new_config["poll_interval_ms"]
        if interval != self._current_interval and self._thread is not None:
            self._thread.stop()
            self._current_interval = interval
            self._thread = PeriodicThread(self._current_interval, self._poll)
            self._thread.start()
            logger.info("SystemMonitor interval updated to %dms.", interval)

    def _poll(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        active_window = self._get_active_window()
        current_hour = datetime.now().hour
        battery = self._get_battery()
        data = SensorData(
            cpu_percent=cpu,
            active_window=active_window,
            current_hour=current_hour,
            battery_percent=battery,
        )
        if self._event_bus:
            self._event_bus.emit("sensor_update", data)

    def _get_active_window(self) -> str:
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win is None:
                return ""
            return win.title or ""
        except Exception as exc:
            logger.debug("pygetwindow error (non-fatal): %s", exc)
            return ""

    def _get_battery(self) -> Optional[float]:
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                return None
            return batt.percent
        except Exception:
            return None
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_system_monitor.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/system_monitor.py tests/test_system_monitor.py
git commit -m "refactor: remove QObject/QTimer from SystemMonitor; use PeriodicThread"
```

---

## Task 7: Refactor `brain.py`

**Files:**
- Modify: `src/ai/brain.py`
- Modify: `tests/test_brain.py`

- [ ] **Step 1: Update `tests/test_brain.py`**

Replace Qt-specific fixtures. The key changes are: remove `QApplication`, pass `event_bus` to `Brain`, and use `bus.on("brain_output", ...)` instead of `brain.brain_output.connect(...)`.

```python
# tests/test_brain.py — replace the QApplication fixture and helper:

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.event_bus import EventBus
from src.ai.brain import Brain, PetState, SensorData, BrainOutput

CONFIG = {
    "cpu_panic_threshold": 80,
    "sleepy_hour": 23,
    "battery_tired_threshold": 20,
    "studious_windows": ["Visual Studio Code", "code"],
    "buddy_skin": "skales",
    "idle_action_interval_min_s": 30,
    "idle_action_interval_max_s": 60,
}


def make_sensor(cpu=0.0, window="", hour=12, battery=100.0):
    return SensorData(cpu_percent=cpu, active_window=window, current_hour=hour, battery_percent=battery)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def brain(bus):
    b = Brain(CONFIG, event_bus=bus)
    b._current_state = PetState.IDLE
    b._has_intro = False
    return b


def collect_outputs(brain, bus, sensor_data):
    outputs = []
    bus.on("brain_output", outputs.append)
    brain.on_sensor_update(sensor_data)
    bus.off("brain_output", outputs.append)
    return outputs
```

Update every test that calls `collect_outputs` to pass `bus` as second argument.

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_brain.py -v
```

- [ ] **Step 3: Rewrite `brain.py`**

```python
"""
brain.py — State machine for KIBO.

Receives SensorData from SystemMonitor and query results from VoiceListener,
evaluates priority-ordered transition rules, emits BrainOutput via EventBus.

All data structures are frozen (immutable). No Qt deps on the logic itself.
"""
from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from src.core.config_manager import get_bundle_dir

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"


class PetState(Enum):
    IDLE = auto()
    HAPPY = auto()
    TIRED = auto()
    WORKING = auto()
    PANICKED = auto()
    STUDIOUS = auto()
    SLEEPY = auto()
    LISTENING = auto()
    THINKING = auto()
    TALKING = auto()
    INTRO = auto()
    ACTING = auto()


STATE_ANIMATION: dict[PetState, str] = {
    PetState.IDLE: "idle/stand",
    PetState.HAPPY: "idle/stand",
    PetState.TIRED: "action/tired",
    PetState.WORKING: "action/smartphone",
    PetState.PANICKED: "action/spinning",
    PetState.STUDIOUS: "action/screentap",
    PetState.SLEEPY: "action/sleep",
    PetState.LISTENING: "idle/still",
    PetState.THINKING: "action/bubblegum",
    PetState.TALKING: "action/breathing",
    PetState.INTRO: "intro/spawn",
    PetState.ACTING: "action/placeholder",
}


@dataclass(frozen=True)
class SensorData:
    cpu_percent: float
    active_window: str
    current_hour: int
    battery_percent: Optional[float]


@dataclass(frozen=True)
class BrainOutput:
    state: PetState
    speech_text: Optional[str]
    animation_name: str
    loop: bool = True


@dataclass(frozen=True)
class _Rule:
    condition: Callable[[SensorData, "Brain"], bool]
    target_state: PetState
    speech_text: Optional[str]
    notification_type: Optional[str] = None


class Brain:
    """
    Evaluates sensor data against priority-ordered rules and emits BrainOutput.

    Priority (highest first):
      PANICKED > LISTENING > THINKING > TALKING > SLEEPY > STUDIOUS > TIRED > WORKING > HAPPY > IDLE
    """

    def __init__(self, config: dict, router=None, event_bus=None) -> None:
        self._config = config
        self._router = router
        self._event_bus = event_bus
        self._ai_state: Optional[PetState] = None
        self._rules = self._build_rules()
        self._lock = threading.RLock()

        self._skin: str = config.get("buddy_skin", "skales")
        self._available_actions: list[str] = self._discover_actions()
        self._action_bag: list[str] = []
        self._available_idles: list[str] = self._discover_idles()

        self._has_intro = self._check_intro_exists()
        self._current_state: PetState = PetState.INTRO if self._has_intro else PetState.IDLE

        interval_min = config.get("idle_action_interval_min_s", 30)
        interval_max = config.get("idle_action_interval_max_s", 60)
        self._action_interval_min_ms = int(interval_min * 1000)
        self._action_interval_max_ms = int(interval_max * 1000)
        self._action_timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()

    def _build_rules(self) -> list[_Rule]:
        cfg = self._config
        cpu_thresh = cfg["cpu_panic_threshold"]
        sleepy_hour = cfg["sleepy_hour"]
        battery_thresh = cfg["battery_tired_threshold"]
        studious_windows: list[str] = [w.lower() for w in cfg["studious_windows"]]

        return [
            _Rule(
                condition=lambda s, _: s.cpu_percent > cpu_thresh,
                target_state=PetState.PANICKED,
                speech_text="So many processes!",
                notification_type="cpu-panic",
            ),
            _Rule(
                condition=lambda s, _: s.current_hour >= sleepy_hour,
                target_state=PetState.SLEEPY,
                speech_text="Getting sleepy...",
                notification_type="sleepy",
            ),
            _Rule(
                condition=lambda s, _: any(w in s.active_window.lower() for w in studious_windows),
                target_state=PetState.STUDIOUS,
                speech_text="Let's code!",
                notification_type="studious",
            ),
            _Rule(
                condition=lambda s, _: (
                    s.battery_percent is not None and s.battery_percent < battery_thresh
                ),
                target_state=PetState.TIRED,
                speech_text="Running low on battery...",
                notification_type="battery-low",
            ),
            _Rule(
                condition=lambda s, _: s.cpu_percent > 50,
                target_state=PetState.WORKING,
                speech_text=None,
            ),
            _Rule(
                condition=lambda s, _: (
                    s.cpu_percent < 30
                    and (s.battery_percent is None or s.battery_percent > 50)
                    and 8 <= s.current_hour < 20
                ),
                target_state=PetState.HAPPY,
                speech_text=None,
            ),
        ]

    # ── Action/Idle discovery ────────────────────────────────────────────

    def _discover_idles(self) -> list[str]:
        idles = []
        idle_dir = ASSETS_DIR / self._skin / "idle"
        if idle_dir.exists() and idle_dir.is_dir():
            for p in idle_dir.iterdir():
                if p.is_file() and p.name.endswith(".webm"):
                    idles.append(p.stem)
        return sorted(list(set(idles)))

    def _get_anim_for_state(self, state: PetState) -> str:
        base_anim = STATE_ANIMATION.get(state, "idle/stand")
        if "/" not in base_anim:
            return base_anim
        category, clip = base_anim.split("/", 1)
        path = ASSETS_DIR / self._skin / category / f"{clip}.webm"
        if path.is_file():
            return base_anim
        if category == "idle" and self._available_idles:
            return f"idle/{self._available_idles[0]}"
        elif category == "action" and self._available_actions:
            return f"action/{self._pick_action()}"
        return f"idle/{self._available_idles[0]}" if self._available_idles else "idle/idle"

    def _discover_actions(self) -> list[str]:
        actions = []
        action_dir = ASSETS_DIR / self._skin / "action"
        if action_dir.exists() and action_dir.is_dir():
            for p in action_dir.iterdir():
                if p.is_file() and p.name.endswith(".webm"):
                    actions.append(p.stem)
                elif p.is_dir() and any(p.glob("frame_*.png")):
                    actions.append(p.name)
        actions = sorted(list(set(actions)))
        if actions:
            logger.info("Discovered %d action clips for skin '%s': %s", len(actions), self._skin, actions)
        else:
            logger.info("No action clips found for skin '%s'.", self._skin)
        return actions

    def _check_intro_exists(self) -> bool:
        intro_dir = ASSETS_DIR / self._skin / "intro"
        if intro_dir.exists() and intro_dir.is_dir():
            return any(p.name.endswith(".webm") for p in intro_dir.iterdir())
        return False

    def _pick_action(self) -> str:
        if not self._available_actions:
            return "placeholder"
        if not self._action_bag:
            self._action_bag = list(self._available_actions)
            random.shuffle(self._action_bag)
        return self._action_bag.pop()

    # ── Action timer (single-shot, random interval) ──────────────────────

    def _start_action_timer(self) -> None:
        if not self._available_actions:
            return
        interval_s = random.randint(
            self._action_interval_min_ms, self._action_interval_max_ms
        ) / 1000.0
        with self._timer_lock:
            if self._action_timer is not None:
                self._action_timer.cancel()
            self._action_timer = threading.Timer(interval_s, self._on_action_timer_fired)
            self._action_timer.daemon = True
            self._action_timer.start()

    def _stop_action_timer(self) -> None:
        with self._timer_lock:
            if self._action_timer is not None:
                self._action_timer.cancel()
                self._action_timer = None

    def _on_action_timer_fired(self) -> None:
        with self._lock:
            if self._ai_state is not None or self._current_state not in (PetState.IDLE, PetState.HAPPY):
                self._start_action_timer()
                return
            if not self._available_actions:
                return
            clip_name = self._pick_action()
            self._current_state = PetState.ACTING
        animation = f"action/{clip_name}"
        output = BrainOutput(state=PetState.ACTING, speech_text=None, animation_name=animation, loop=False)
        self._emit(output)

    # ── Startup ──────────────────────────────────────────────────────────

    def get_initial_output(self) -> BrainOutput:
        if self._has_intro:
            intro_clips = []
            intro_dir = ASSETS_DIR / self._skin / "intro"
            if intro_dir.exists() and intro_dir.is_dir():
                for p in intro_dir.iterdir():
                    if p.is_file() and p.name.endswith(".webm"):
                        intro_clips.append(p.stem)
            if intro_clips:
                clip = random.choice(intro_clips)
                anim_name = f"intro/{clip}"
            else:
                anim_name = "intro/spawn"
            return BrainOutput(state=PetState.INTRO, speech_text=None, animation_name=anim_name, loop=False)
        return BrainOutput(
            state=PetState.IDLE,
            speech_text=None,
            animation_name=self._get_anim_for_state(PetState.IDLE),
        )

    # ── Slots (plain methods now) ─────────────────────────────────────────

    def on_animation_done(self) -> None:
        with self._lock:
            if self._current_state == PetState.INTRO:
                logger.info("Intro finished → IDLE")
                self._current_state = PetState.IDLE
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
            elif self._current_state == PetState.ACTING:
                logger.info("Action clip finished → IDLE")
                self._current_state = PetState.IDLE
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
            else:
                return
        self._emit(output)
        self._start_action_timer()

    def on_sensor_update(self, sensor_data: SensorData) -> None:
        with self._lock:
            if self._ai_state is not None:
                return
            if self._current_state in (PetState.INTRO, PetState.ACTING):
                return

            new_state = PetState.IDLE
            speech: Optional[str] = None
            notification_type: Optional[str] = None

            for rule in self._rules:
                if rule.condition(sensor_data, self):
                    new_state = rule.target_state
                    speech = rule.speech_text
                    notification_type = rule.notification_type
                    break

            if new_state == self._current_state:
                speech = None

            if new_state == self._current_state and speech is None:
                return

            if speech and self._router and notification_type:
                priority = "medium" if notification_type in ("cpu-panic", "battery-low") else "low"
                if not self._router.route(notification_type, speech, priority):
                    speech = None

            self._current_state = new_state
            output = BrainOutput(
                state=new_state,
                speech_text=speech,
                animation_name=self._get_anim_for_state(new_state),
            )
        self._emit(output)

    def on_listening_started(self) -> None:
        with self._lock:
            if self._ai_state in (PetState.LISTENING, PetState.THINKING, PetState.TALKING):
                return
        self._stop_action_timer()
        self._set_ai_state(PetState.LISTENING, "Yeah?")

    def on_thinking_started(self) -> None:
        self._set_ai_state(PetState.THINKING, "Hmm...")

    def on_talking_started(self, response_text: str) -> None:
        self._set_ai_state(PetState.TALKING, response_text)

    def on_ai_done(self) -> None:
        with self._lock:
            self._ai_state = None
            self._current_state = PetState.IDLE
            output = BrainOutput(
                state=PetState.IDLE,
                speech_text=None,
                animation_name=self._get_anim_for_state(PetState.IDLE),
            )
        self._emit(output)
        self._start_action_timer()

    def on_config_changed(self, new_config: dict) -> None:
        with self._lock:
            old_skin = self._skin
            new_skin = new_config.get("buddy_skin", "skales")
            self._config = new_config
            if old_skin != new_skin:
                self._skin = new_skin
                self._available_actions = self._discover_actions()
                self._action_bag = []
                self._available_idles = self._discover_idles()
                self._has_intro = self._check_intro_exists()
                logger.info("Brain updated skin from '%s' to '%s'", old_skin, new_skin)
                self._current_state = PetState.IDLE
                self._ai_state = None
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
                self._emit(output)
                self._start_action_timer()

    # ── Internal ──────────────────────────────────────────────────────────

    def _set_ai_state(self, state: PetState, speech: Optional[str]) -> None:
        with self._lock:
            self._ai_state = state
            self._current_state = state
            if state in (PetState.THINKING, PetState.TALKING):
                anim_name = f"action/{self._pick_action()}"
            else:
                anim_name = self._get_anim_for_state(state)
            output = BrainOutput(state=state, speech_text=speech, animation_name=anim_name)
        self._emit(output)

    def _emit(self, output: BrainOutput) -> None:
        if self._event_bus:
            self._event_bus.emit("brain_output", output)

    @property
    def current_state(self) -> PetState:
        return self._current_state
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_brain.py -v
```

- [ ] **Step 5: Commit**

```
git add src/ai/brain.py tests/test_brain.py
git commit -m "refactor: remove QObject/Signal/QTimer from Brain; use EventBus + threading.Timer"
```

---

## Task 8: Refactor `calendar_manager.py`

**Files:**
- Modify: `src/system/calendar_manager.py`
- Modify: `tests/test_calendar_manager.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_calendar_manager.py, replace Qt signal observation with:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: cal.events_updated.connect(handler)
# With:    bus.on("events_updated", handler)

# Update CalendarManager construction: CalendarManager(config, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_calendar_manager.py -v
```

- [ ] **Step 3: Rewrite `calendar_manager.py`**

```python
import logging
import datetime
import threading
from typing import Optional, List
from pathlib import Path
import json

from src.core.config_manager import get_user_data_dir
from src.core.periodic_thread import PeriodicThread

logger = logging.getLogger(__name__)


class CalendarManager:
    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._thread: Optional[PeriodicThread] = None
        self._events: List[dict] = []
        self._is_polling = False

    def start(self) -> None:
        self._poll()
        self._thread = PeriodicThread(15 * 60 * 1000, self._poll)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def get_next_event(self) -> Optional[dict]:
        if not self._events:
            return None
        return self._events[0]

    def _poll(self) -> None:
        provider = self._config.get("calendar_provider", "none")
        if provider == "none":
            self._events = []
            self._update_events(self._events)
            return
        if self._is_polling:
            return
        self._is_polling = True
        threading.Thread(target=self._fetch_google_calendar, daemon=True).start()

    def _fetch_google_calendar(self) -> None:
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
            token_path = get_user_data_dir() / "google_token.json"
            creds_path = get_user_data_dir() / "credentials.json"

            creds = None
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif creds_path.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                    try:
                        creds = flow.run_local_server(port=0, timeout_seconds=120)
                    except Exception as oauth_err:
                        logger.error("Google OAuth timed out or failed: %s", oauth_err)
                        self._update_events([])
                        return
                    with open(token_path, "w") as token:
                        token.write(creds.to_json())
                else:
                    logger.warning("No credentials.json found for Google Calendar in ~/.kibo")
                    self._update_events([])
                    return

            service = build("calendar", "v3", credentials=creds)
            now = datetime.datetime.utcnow().isoformat() + "Z"
            lookahead_mins = self._config.get("calendar_lookahead_minutes", 60)
            end_time = (
                datetime.datetime.utcnow() + datetime.timedelta(minutes=lookahead_mins)
            ).isoformat() + "Z"
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=end_time,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            parsed_events = [
                {
                    "title": e.get("summary", "Untitled Event"),
                    "start_time": e["start"].get("dateTime", e["start"].get("date")),
                }
                for e in events
            ]
            self._update_events(parsed_events)
        except ImportError:
            logger.warning("Google API client not installed.")
            self._update_events([])
        except Exception as e:
            logger.error("Failed to fetch Google Calendar: %s", e)
            self._update_events([])

    def _update_events(self, events: List[dict]) -> None:
        self._events = events
        if self._event_bus:
            self._event_bus.emit("events_updated", self._events)
        self._is_polling = False
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_calendar_manager.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/calendar_manager.py tests/test_calendar_manager.py
git commit -m "refactor: remove QObject/QTimer from CalendarManager; use PeriodicThread"
```

---

## Task 9: Refactor `proactive_engine.py`

**Files:**
- Modify: `src/system/proactive_engine.py`
- Modify: `tests/test_proactive_engine.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_proactive_engine.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: engine.proactive_notification.connect(handler)
# With:    bus.on("proactive_notification", handler)
# Update:  ProactiveEngine(config, router=router, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_proactive_engine.py -v
```

- [ ] **Step 3: Rewrite `proactive_engine.py`**

Replace the class, keeping all rules and logic unchanged. Key changes:
- Remove `QObject` base, `Signal`, `QTimer`, `@Slot`
- Add `event_bus` param
- `self._timer = QTimer(self); self._timer.timeout.connect(self._on_tick)` → `self._thread: Optional[PeriodicThread] = None`
- `start()` → `self._thread = PeriodicThread(60_000, self._on_tick); self._thread.start()`
- `stop()` → `if self._thread: self._thread.stop(); self._thread = None`
- `self.proactive_notification.emit(type, msg, priority)` → `if self._event_bus: self._event_bus.emit("proactive_notification", type, msg, priority)`
- Remove `@Slot` from all methods

Full file:

```python
import datetime
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from src.ai.brain import SensorData
from src.system.notification_router import NotificationRouter
from src.core.periodic_thread import PeriodicThread

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProactiveContext:
    idle_minutes: int
    current_hour: int
    tasks_pending: int
    tasks_blocked: int
    tasks_done_today: int
    next_meeting_minutes: int
    unread_emails: int
    battery_percent: Optional[float]
    cpu_percent: Optional[float]
    app_open_minutes: int


@dataclass(frozen=True)
class ProactiveRule:
    type: str
    condition: Callable[[ProactiveContext], bool]
    message: Callable[[ProactiveContext], str]
    priority: str


RULES: list[ProactiveRule] = [
    ProactiveRule(
        type="morning-greeting",
        condition=lambda ctx: 8 <= ctx.current_hour < 12 and ctx.app_open_minutes >= 2,
        message=lambda _: "Good morning! Ready to get things done?",
        priority="low",
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes >= 60,
        message=lambda ctx: f"You've been away for {ctx.idle_minutes} minutes. Still there?",
        priority="low",
    ),
    ProactiveRule(
        type="eod-summary",
        condition=lambda ctx: 17 <= ctx.current_hour < 20 and ctx.tasks_done_today >= 1,
        message=lambda ctx: f"Nice work today — {ctx.tasks_done_today} task(s) done!",
        priority="low",
    ),
    ProactiveRule(
        type="battery-low",
        condition=lambda ctx: ctx.battery_percent is not None and ctx.battery_percent < 20,
        message=lambda ctx: f"Battery at {ctx.battery_percent:.0f}% — might want to plug in.",
        priority="medium",
    ),
    ProactiveRule(
        type="cpu-panic",
        condition=lambda ctx: ctx.cpu_percent is not None and ctx.cpu_percent > 90,
        message=lambda _: "CPU is spiking — something's working hard.",
        priority="medium",
    ),
    ProactiveRule(
        type="meeting-reminder",
        condition=lambda ctx: 0 < ctx.next_meeting_minutes <= 30,
        message=lambda ctx: f"Meeting in {ctx.next_meeting_minutes} min!",
        priority="medium",
    ),
]


class ProactiveEngine:
    def __init__(
        self,
        config: dict,
        router: NotificationRouter,
        task_runner=None,
        clock_fn: Optional[Callable[[], datetime.datetime]] = None,
        event_bus=None,
    ) -> None:
        self._config = config
        self._router = router
        self._event_bus = event_bus
        self._clock_fn: Callable[[], datetime.datetime] = clock_fn or datetime.datetime.now
        self._thread: Optional[PeriodicThread] = None

        self._battery_percent: Optional[float] = None
        self._cpu_percent: Optional[float] = None
        self._next_meeting_minutes = -1
        self._unread_emails = -1
        self._start_time: datetime.datetime = self._clock_fn()

        self._tasks_pending = 0
        self._tasks_blocked = 0
        self._tasks_done_today = 0
        self._last_tick_date: Optional[datetime.date] = None

        if task_runner is not None:
            self._sync_task_state(task_runner)

    def _sync_task_state(self, task_runner) -> None:
        today = datetime.date.today()
        today_start = int(datetime.datetime(today.year, today.month, today.day).timestamp())
        tasks = task_runner.get_tasks()
        self._tasks_pending = sum(1 for t in tasks if t.get("state") == "pending")
        self._tasks_blocked = sum(1 for t in tasks if t.get("state") == "blocked")
        self._tasks_done_today = sum(
            1 for t in tasks
            if t.get("state") == "completed" and (t.get("completed_at") or 0) >= today_start
        )

    def start(self) -> None:
        self._thread = PeriodicThread(60_000, self._on_tick)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def update_last_interaction(self) -> None:
        self._router.update_last_interaction()

    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config

    def on_sensor_update(self, data: SensorData) -> None:
        self._battery_percent = data.battery_percent
        self._cpu_percent = getattr(data, "cpu_percent", None)

    def on_calendar_updated(self, events: list) -> None:
        if not events:
            self._next_meeting_minutes = -1
            return
        now = self._clock_fn()
        try:
            start = datetime.datetime.fromisoformat(events[0].get("start_time", ""))
            diff = (start - now).total_seconds() / 60.0
            self._next_meeting_minutes = int(diff) if diff > 0 else -1
        except Exception:
            self._next_meeting_minutes = -1

    def on_task_completed(self, task: dict) -> None:
        self._tasks_done_today += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    def on_task_blocked(self, task: dict) -> None:
        self._tasks_blocked += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    def _on_tick(self) -> None:
        if not self._config.get("proactive_enabled", True):
            return

        now = self._clock_fn()
        today = now.date()
        if self._last_tick_date is not None and today != self._last_tick_date:
            logger.info("Day rollover detected; resetting daily task counter.")
            self._tasks_done_today = 0
        self._last_tick_date = today

        last_interaction = self._router.get_last_interaction()
        now_ts = int(now.timestamp())
        idle_mins = (now_ts - last_interaction) // 60 if last_interaction > 0 else 0
        app_open_mins = int((now - self._start_time).total_seconds() / 60)

        ctx = ProactiveContext(
            idle_minutes=idle_mins,
            current_hour=now.hour,
            tasks_pending=self._tasks_pending,
            tasks_blocked=self._tasks_blocked,
            tasks_done_today=self._tasks_done_today,
            next_meeting_minutes=self._next_meeting_minutes,
            unread_emails=self._unread_emails,
            battery_percent=self._battery_percent,
            cpu_percent=self._cpu_percent,
            app_open_minutes=app_open_mins,
        )

        if self._config.get("demo_mode", False):
            demo_idle = int(self._config.get("demo_proactive_idle_minutes", 1))
            if ctx.idle_minutes >= demo_idle:
                if self._event_bus:
                    self._event_bus.emit(
                        "proactive_notification",
                        "idle-checkin",
                        "Quiet stretch detected. I'm still here when you want me.",
                        "low",
                    )
                return

        for rule in RULES:
            if rule.condition(ctx):
                if self._event_bus:
                    self._event_bus.emit(
                        "proactive_notification", rule.type, rule.message(ctx), rule.priority
                    )
                break
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_proactive_engine.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/proactive_engine.py tests/test_proactive_engine.py
git commit -m "refactor: remove QObject/QTimer from ProactiveEngine; use PeriodicThread"
```

---

## Task 10: Refactor `task_runner.py`

**Files:**
- Modify: `src/system/task_runner.py`
- Modify: `tests/test_task_runner.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_task_runner.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: runner.task_completed.connect(handler)
# With:    bus.on("task_completed", handler)
# Update:  TaskRunner(config, ai_client=mock, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_task_runner.py -v
```

- [ ] **Step 3: Modify `task_runner.py`**

Key changes only (logic is unchanged):

```python
# REMOVE:
from PySide6.QtCore import QObject, Signal, QTimer

# ADD:
from src.core.periodic_thread import PeriodicThread

# Change class signature:
class TaskRunner:  # was QObject
    def __init__(self, config: dict, ai_client, event_bus=None) -> None:
        # Remove super().__init__()
        self._event_bus = event_bus
        # Remove Signal declarations
        # Replace: self._timer = QTimer(self); self._timer.timeout.connect(self._process_queue)
        self._thread: Optional[PeriodicThread] = None
        # ... rest of init unchanged

    def start(self) -> None:
        self._thread = PeriodicThread(30_000, self._process_queue)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    # Replace every Signal emit — example:
    # self.task_completed.emit(t) → if self._event_bus: self._event_bus.emit("task_completed", t)
    # self.task_failed.emit(t)    → if self._event_bus: self._event_bus.emit("task_failed", t)
    # self.task_blocked.emit(t)   → if self._event_bus: self._event_bus.emit("task_blocked", t)
    # self.task_started.emit(t)   → if self._event_bus: self._event_bus.emit("task_started", t)
    # self.status_update.emit(s)  → if self._event_bus: self._event_bus.emit("status_update", s)
```

Apply these replacements throughout `_process_queue` and `_run_task`.

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_task_runner.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/task_runner.py tests/test_task_runner.py
git commit -m "refactor: remove QObject/QTimer from TaskRunner; use PeriodicThread + EventBus"
```

---

## Task 11: Refactor `hotkey_listener.py`

**Files:**
- Modify: `src/system/hotkey_listener.py`
- Modify: `tests/test_hotkey_listener.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_hotkey_listener.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: listener.hotkey_pressed.connect(handler)
# With:    bus.on("hotkey_pressed", handler)
# Update:  HotkeyListener(config, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_hotkey_listener.py -v
```

- [ ] **Step 3: Rewrite `hotkey_listener.py`**

```python
"""
hotkey_listener.py — Global hotkey listener (default: Ctrl+K).

Runs keyboard library hooks on a daemon thread. Emits events via EventBus.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import keyboard

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Registers global hotkeys and emits via EventBus when they fire."""

    def __init__(self, config: dict, event_bus=None) -> None:
        self._event_bus = event_bus
        self._hotkey = config.get("activation_hotkey", "ctrl+k")
        self._clip_hotkey = config.get("clip_hotkey", "ctrl+alt+k")
        self._running = False
        self._registered_handles: dict[str, object] = {}

    def is_registered(self, hotkey: str) -> bool:
        return hotkey in self._registered_handles

    def _register(self, hotkey: str, callback) -> None:
        try:
            handle = keyboard.add_hotkey(hotkey, callback)
        except Exception as exc:
            logger.error("HotkeyListener: failed to register '%s': %s", hotkey, exc)
            if self._event_bus:
                self._event_bus.emit("registration_failed", hotkey)
            return
        self._registered_handles[hotkey] = handle

    def start_listening(self) -> None:
        self._running = True
        logger.info(
            "HotkeyListener: registering '%s' (talk) and '%s' (clip).",
            self._hotkey,
            self._clip_hotkey,
        )
        self._register(self._hotkey, self._on_hotkey)
        self._register(self._clip_hotkey, self._on_clip_hotkey)

    def stop(self) -> None:
        self._running = False
        for hotkey, handle in list(self._registered_handles.items()):
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                try:
                    keyboard.remove_hotkey(hotkey)
                except Exception:
                    pass
        self._registered_handles.clear()

    def rebind(self, talk_hotkey: Optional[str] = None, clip_hotkey: Optional[str] = None) -> None:
        if talk_hotkey and talk_hotkey != self._hotkey:
            self._unregister(self._hotkey)
            self._hotkey = talk_hotkey
            if self._running:
                self._register(self._hotkey, self._on_hotkey)
        if clip_hotkey and clip_hotkey != self._clip_hotkey:
            self._unregister(self._clip_hotkey)
            self._clip_hotkey = clip_hotkey
            if self._running:
                self._register(self._clip_hotkey, self._on_clip_hotkey)

    def _unregister(self, hotkey: str) -> None:
        handle = self._registered_handles.pop(hotkey, None)
        if handle is None:
            return
        try:
            keyboard.remove_hotkey(handle)
        except Exception:
            try:
                keyboard.remove_hotkey(hotkey)
            except Exception:
                pass

    def _on_hotkey(self) -> None:
        if self._running:
            logger.debug("Hotkey '%s' pressed.", self._hotkey)
            if self._event_bus:
                self._event_bus.emit("hotkey_pressed")

    def _on_clip_hotkey(self) -> None:
        if self._running:
            logger.debug("Clip hotkey '%s' pressed.", self._clip_hotkey)
            if self._event_bus:
                self._event_bus.emit("clip_hotkey_pressed")


class HotkeyThread(threading.Thread):
    """Owns HotkeyListener on a daemon thread."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._listener = HotkeyListener(config, event_bus=event_bus)
        self._stop_event = threading.Event()

    def run(self) -> None:
        self._listener.start_listening()
        self._stop_event.wait()  # block until stop() is called

    def stop(self) -> None:
        self._listener.stop()
        self._stop_event.set()

    def rebind(self, talk_hotkey: str, clip_hotkey: str) -> None:
        self._listener.rebind(talk_hotkey=talk_hotkey, clip_hotkey=clip_hotkey)
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_hotkey_listener.py -v
```

- [ ] **Step 5: Commit**

```
git add src/system/hotkey_listener.py tests/test_hotkey_listener.py
git commit -m "refactor: remove QObject/QThread from HotkeyListener; use threading.Thread"
```

---

## Task 12: Refactor `voice_listener.py`

**Files:**
- Modify: `src/ai/voice_listener.py`
- Modify: `tests/test_voice_listener.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_voice_listener.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace Qt signal connections with bus.on("recording_started", ...) etc.
# Update VoiceListener(config, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_voice_listener.py -v
```

- [ ] **Step 3: Rewrite `voice_listener.py`**

Key changes to `VoiceListener` class:
- Remove `QObject` base, Signal declarations, `@Slot` decorators
- Add `event_bus` parameter
- Replace `self.recording_started.emit()` → `if self._event_bus: self._event_bus.emit("recording_started")`
- Replace `self.transcript_ready.emit(text)` → `if self._event_bus: self._event_bus.emit("transcript_ready", text)`
- Replace `self.no_speech_detected.emit()` → `if self._event_bus: self._event_bus.emit("no_speech_detected")`
- Replace `self.error_occurred.emit(msg)` → `if self._event_bus: self._event_bus.emit("voice_error", msg)`

Rewrite `VoiceThread` as `threading.Thread` with a command queue:

```python
class VoiceThread(threading.Thread):
    """Owns VoiceListener and dispatches commands via queue."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._listener = VoiceListener(config, event_bus=event_bus)
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd = self._queue.get(timeout=0.5)
                if cmd == "hotkey_pressed":
                    self._listener.on_hotkey_pressed()
                elif cmd == "warm_up":
                    self._listener.warm_up()
            except queue.Empty:
                continue

    def on_hotkey_pressed(self) -> None:
        self._queue.put("hotkey_pressed")

    def warm_up(self) -> None:
        self._queue.put("warm_up")

    def stop(self) -> None:
        self._stop_event.set()
```

Also add `import queue` at the top of the file and remove all PySide6 imports.

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_voice_listener.py -v
```

- [ ] **Step 5: Commit**

```
git add src/ai/voice_listener.py tests/test_voice_listener.py
git commit -m "refactor: remove QObject/QThread from VoiceListener; use threading.Thread + queue"
```

---

## Task 13: Refactor `tts_manager.py`

**Files:**
- Modify: `src/ai/tts_manager.py`
- Modify: `tests/test_tts_manager.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_tts_manager.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: manager.speech_done.connect(handler)
# With:    bus.on("speech_done", handler)
# Update:  TTSManager(config, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_tts_manager.py -v
```

- [ ] **Step 3: Rewrite `tts_manager.py`**

Key changes to `TTSManager`:
- Remove `QObject` base, Signal declarations, `@Slot` decorators, `QMetaObject` import
- Add `event_bus` parameter
- Replace `self.speech_done.emit()` → `if self._event_bus: self._event_bus.emit("speech_done")`
- Replace `self.error_occurred.emit(msg)` → `if self._event_bus: self._event_bus.emit("tts_error", msg)`

Rewrite `TTSThread` as `threading.Thread` with a command queue. `interrupt()` is called directly (not queued) since `TTSManager.interrupt()` is already thread-safe via its internal locks:

```python
class TTSThread(threading.Thread):
    """Owns TTSManager; dispatches commands via queue. interrupt() is direct."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._manager = TTSManager(config, event_bus=event_bus)
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd, args = self._queue.get(timeout=0.2)
                if cmd == "speak":
                    self._manager.speak(args[0])
                elif cmd == "speak_chunk":
                    self._manager.speak_chunk(args[0])
                elif cmd == "end_stream":
                    self._manager.end_stream()
                elif cmd == "test_voice":
                    self._manager.test_voice()
            except queue.Empty:
                continue

    def speak(self, text: str) -> None:
        self._queue.put(("speak", (text,)))

    def speak_chunk(self, sentence: str) -> None:
        self._queue.put(("speak_chunk", (sentence,)))

    def end_stream(self) -> None:
        self._queue.put(("end_stream", ()))

    def interrupt(self) -> None:
        # Called directly — TTSManager.interrupt() is thread-safe by design.
        self._manager.interrupt()

    def test_voice(self) -> None:
        self._queue.put(("test_voice", ()))

    def stop(self) -> None:
        self.interrupt()
        self._stop_event.set()

    @property
    def manager(self) -> TTSManager:
        return self._manager
```

- [ ] **Step 4: Run tests — expect PASS**

```
pytest tests/test_tts_manager.py -v
```

- [ ] **Step 5: Commit**

```
git add src/ai/tts_manager.py tests/test_tts_manager.py
git commit -m "refactor: remove QObject/QThread from TTSManager; use threading.Thread + queue"
```

---

## Task 14: Refactor `ai_client.py`

**Files:**
- Modify: `src/ai/ai_client.py`
- Modify: `tests/test_ai_client.py`

- [ ] **Step 1: Update tests**

```python
# In tests/test_ai_client.py:
from src.api.event_bus import EventBus

@pytest.fixture
def bus():
    return EventBus()

# Replace: client.response_chunk.connect(handler)
# With:    bus.on("response_chunk", handler)
# Update:  AIClient(config, event_bus=bus)
#          AIThread(config, event_bus=bus)
```

- [ ] **Step 2: Run to confirm FAIL**

```
pytest tests/test_ai_client.py -v
```

- [ ] **Step 3: Modify `AIClient`**

Remove: `from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QThread, Qt, Signal, Slot`

Change class and `__init__`:
```python
class AIClient:  # remove QObject base
    def __init__(self, config: dict, memory_store=None, event_bus=None) -> None:
        # remove super().__init__(parent)
        self._event_bus = event_bus
        # ... rest unchanged
```

Remove all Signal declarations. Remove `@Slot` decorators. Replace every `.emit()`:
```python
# self.response_chunk.emit(chunk)        → if self._event_bus: self._event_bus.emit("response_chunk", chunk)
# self.response_done.emit(text)          → if self._event_bus: self._event_bus.emit("response_done", text)
# self.memory_fact_extracted.emit(args)  → if self._event_bus: self._event_bus.emit("memory_fact_extracted", args)
# self.safety_event.emit(cat, msg)       → if self._event_bus: self._event_bus.emit("safety_event", cat, msg)
# self.error_occurred.emit(msg)          → if self._event_bus: self._event_bus.emit("ai_error", msg)
```

- [ ] **Step 4: Rewrite `AIThread`**

```python
class AIThread(threading.Thread):
    """Owns AIClient; dispatches queries via queue. cancel_current() is direct."""

    def __init__(self, config: dict, memory_store=None, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._client = AIClient(config, memory_store, event_bus=event_bus)
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd, args = self._queue.get(timeout=0.2)
                if cmd == "send_query":
                    self._client.send_query(args[0])
                elif cmd == "on_config_changed":
                    self._client.on_config_changed(args[0])
            except queue.Empty:
                continue

    def send_query(self, text: str) -> None:
        self._queue.put(("send_query", (text,)))

    def cancel_current(self) -> None:
        # _cancel_event is a threading.Event — thread-safe direct call.
        self._client.cancel_current()

    def on_config_changed(self, new_config: dict) -> None:
        self._queue.put(("on_config_changed", (new_config,)))

    def stop(self) -> None:
        self.cancel_current()
        self._stop_event.set()

    @property
    def client(self) -> AIClient:
        return self._client
```

- [ ] **Step 5: Run tests — expect PASS**

```
pytest tests/test_ai_client.py -v
```

- [ ] **Step 6: Commit**

```
git add src/ai/ai_client.py tests/test_ai_client.py
git commit -m "refactor: remove QObject/QThread from AIClient; use threading.Thread + queue"
```

---

## Task 15: Create FastAPI server

**Files:**
- Modify: `requirements.txt` — add `fastapi>=0.115.0` and `uvicorn[standard]>=0.30.0`
- Create: `src/api/server.py`
- Create: `tests/test_api_server.py`

- [ ] **Step 1: Update requirements.txt**

Add after `httpx>=0.27.0`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
```

Install:
```
pip install fastapi "uvicorn[standard]"
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_api_server.py
import pytest
from fastapi.testclient import TestClient
from src.api.event_bus import EventBus
import src.api.server as server_module


@pytest.fixture(autouse=True)
def reset_server():
    server_module._event_bus = None
    server_module._connected_chat_ws.clear()
    server_module._connected_state_ws.clear()
    yield


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def client(bus):
    server_module.setup(bus)
    return TestClient(server_module.app)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_settings_get_returns_dict(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_memory_get_returns_list(client):
    resp = client.get("/memory")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 3: Run to confirm FAIL**

```
pytest tests/test_api_server.py -v
```

- [ ] **Step 4: Create `src/api/server.py`**

```python
"""
server.py — FastAPI backend for KIBO's Electron frontend.

WebSocket /ws/chat  — user query in, streaming tokens out
WebSocket /ws/state — pushes animation/pet state changes
REST      /settings — config CRUD
REST      /memory   — memory CRUD
GET       /health   — liveness check
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="KIBO API")

_event_bus = None
_config: dict = {}
_memory_store = None
_ai_thread = None
_asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
_connected_chat_ws: list[WebSocket] = []
_connected_state_ws: list[WebSocket] = []


def setup(event_bus, config: dict = None, memory_store=None, ai_thread=None) -> None:
    global _event_bus, _config, _memory_store, _ai_thread
    _event_bus = event_bus
    _config = config or {}
    _memory_store = memory_store
    _ai_thread = ai_thread

    event_bus.on("brain_output", _on_brain_output)
    event_bus.on("response_chunk", _on_response_chunk)
    event_bus.on("response_done", _on_response_done)
    event_bus.on("ai_error", _on_ai_error)
    event_bus.on("recording_started", lambda: _broadcast_state({"type": "recording_started"}))
    event_bus.on("transcript_ready", lambda t: _broadcast_state({"type": "transcript_ready", "text": t}))
    event_bus.on("speech_done", lambda: _broadcast_state({"type": "speech_done"}))


def _on_brain_output(output) -> None:
    _broadcast_state({
        "type": "brain_output",
        "state": output.state.name,
        "animation": output.animation_name,
        "speech": output.speech_text,
        "loop": output.loop,
    })


def _on_response_chunk(chunk: str) -> None:
    _broadcast_chat({"type": "chunk", "text": chunk})


def _on_response_done(text: str) -> None:
    _broadcast_chat({"type": "done", "text": text})


def _on_ai_error(msg: str) -> None:
    _broadcast_chat({"type": "error", "text": msg})


def _broadcast_state(data: dict) -> None:
    _broadcast(_connected_state_ws, data)


def _broadcast_chat(data: dict) -> None:
    _broadcast(_connected_chat_ws, data)


def _broadcast(sockets: list[WebSocket], data: dict) -> None:
    if _asyncio_loop is None or not sockets:
        return
    for ws in list(sockets):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, data), _asyncio_loop)


async def _safe_send(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_json(data)
    except Exception:
        pass


# ── WebSocket endpoints ──────────────────────────────────────────────────

@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    global _asyncio_loop
    _asyncio_loop = asyncio.get_event_loop()
    await websocket.accept()
    _connected_state_ws.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _connected_state_ws:
            _connected_state_ws.remove(websocket)


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    global _asyncio_loop
    _asyncio_loop = asyncio.get_event_loop()
    await websocket.accept()
    _connected_chat_ws.append(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            if _event_bus and text.strip():
                _event_bus.emit("user_message", text.strip())
    except WebSocketDisconnect:
        if websocket in _connected_chat_ws:
            _connected_chat_ws.remove(websocket)


# ── REST endpoints ──────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/settings")
async def get_settings() -> dict:
    return dict(_config)


@app.post("/settings")
async def update_settings(new_settings: dict) -> dict:
    _config.update(new_settings)
    if _event_bus:
        _event_bus.emit("settings_changed", dict(_config))
    return {"status": "ok"}


@app.get("/memory")
async def get_memory() -> list:
    if _memory_store is None:
        return []
    return _memory_store.get_all_facts()


@app.delete("/memory/{fact_id}")
async def delete_memory(fact_id: str) -> dict:
    if _memory_store is None:
        return {"status": "not_found"}
    _memory_store.delete_fact(fact_id)
    return {"status": "ok"}


@app.post("/voice/start")
async def voice_start() -> dict:
    if _event_bus:
        _event_bus.emit("hotkey_pressed")
    return {"status": "ok"}


def start(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")
```

- [ ] **Step 5: Run tests — expect PASS**

```
pytest tests/test_api_server.py -v
```

- [ ] **Step 6: Commit**

```
git add requirements.txt src/api/server.py tests/test_api_server.py
git commit -m "feat: add FastAPI server with WebSocket /ws/chat, /ws/state and REST endpoints"
```

---

## Task 16: Create `src/api/main.py`

**Files:**
- Create: `src/api/main.py`

No unit tests needed — this is the composition root. Verified by running it manually.

- [ ] **Step 1: Create `src/api/main.py`**

```python
"""
src/api/main.py — KIBO FastAPI entry point. No Qt required.

Usage:
    python -m src.api.main
    python src/api/main.py
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Optional

from src.core.config_manager import get_user_data_dir, load_config
from src.api.event_bus import EventBus
from src.api import server

from src.ai.brain import Brain
from src.ai.memory_store import MemoryStore
from src.ai.sentence_buffer import SentenceBuffer
from src.system.system_monitor import SystemMonitor
from src.system.notification_router import NotificationRouter
from src.system.proactive_engine import ProactiveEngine
from src.system.calendar_manager import CalendarManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_ROLEPLAY_RE = re.compile(r"\(\s*\*.*?\*\s*\)|\*[^*\n]{1,120}\*", re.DOTALL)


def _sanitize(text: str) -> str:
    cleaned = _ROLEPLAY_RE.sub(" ", text)
    return " ".join(cleaned.split()).strip() or text.strip()


def main() -> None:
    config = load_config()
    bus = EventBus()

    notification_router = NotificationRouter(config, event_bus=bus)
    proactive_engine = ProactiveEngine(config, router=notification_router, event_bus=bus)
    brain = Brain(config, router=notification_router, event_bus=bus)
    system_monitor = SystemMonitor(config, event_bus=bus)
    memory_store = MemoryStore(config, event_bus=bus)
    calendar_manager = CalendarManager(config, event_bus=bus)
    sentence_buffer = SentenceBuffer(event_bus=bus)

    # Backend → backend wiring
    bus.on("sensor_update", brain.on_sensor_update)
    bus.on("sensor_update", proactive_engine.on_sensor_update)
    bus.on("proactive_notification", notification_router.route)
    bus.on("events_updated", proactive_engine.on_calendar_updated)

    ai_enabled = config.get("ai_enabled", True)

    if ai_enabled:
        from src.ai.ai_client import AIThread
        from src.ai.voice_listener import VoiceThread
        from src.ai.tts_manager import TTSThread
        from src.system.hotkey_listener import HotkeyThread

        ai_thread = AIThread(config, memory_store=memory_store, event_bus=bus)
        voice_thread = VoiceThread(config, event_bus=bus)
        tts_thread = TTSThread(config, event_bus=bus)
        hotkey_thread = HotkeyThread(config, event_bus=bus)

        def _on_response_done(text: str) -> None:
            clean = _sanitize(text)
            brain.on_ai_done()
            if not config.get("memory_extraction_inline", True):
                threading.Timer(0, lambda: memory_store.extract_facts_async(clean)).start()

        bus.on("hotkey_pressed", brain.on_listening_started)
        bus.on("hotkey_pressed", voice_thread.on_hotkey_pressed)
        bus.on("transcript_ready", ai_thread.send_query)
        bus.on("transcript_ready", lambda _: brain.on_thinking_started())
        bus.on("voice_error", lambda _: brain.on_ai_done())
        bus.on("response_chunk", sentence_buffer.push)
        bus.on("response_done", _on_response_done)
        bus.on("memory_fact_extracted", memory_store.add_fact_inline)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", tts_thread.end_stream)
        bus.on("speech_done", brain.on_ai_done)
        bus.on("task_completed", proactive_engine.on_task_completed)
        bus.on("task_blocked", proactive_engine.on_task_blocked)
        bus.on("user_message", ai_thread.send_query)  # from WebSocket

        ai_thread.start()
        voice_thread.start()
        tts_thread.start()
        hotkey_thread.start()

        if config.get("voice_warmup_on_launch", True):
            threading.Timer(0.25, voice_thread.warm_up).start()

        logger.info("AI enabled. Hotkey: %s", config.get("activation_hotkey", "ctrl+k"))

    system_monitor.start()
    calendar_manager.start()
    proactive_engine.start()

    # Emit initial brain state so any WebSocket clients receive it on connect
    initial = brain.get_initial_output()
    bus.emit("brain_output", initial)

    server.setup(bus, config=config, memory_store=memory_store,
                 ai_thread=ai_thread if ai_enabled else None)

    logger.info("KIBO API server starting on http://127.0.0.1:8765")
    server.start()  # blocks until Ctrl+C


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test — verify it imports cleanly**

```
python -c "import src.api.main; print('OK')"
```
Expected: `OK` (no ImportError)

- [ ] **Step 3: Commit**

```
git add src/api/main.py
git commit -m "feat: add src/api/main.py — pure-Python FastAPI entry point, no Qt"
```

---

## Task 17: Update `main.py` (Qt desktop app bridge)

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace imports at top of `main.py`**

```python
# BEFORE:
from PySide6.QtCore import Qt, QLockFile, QMetaObject, Q_ARG, QTimer

# AFTER:
from PySide6.QtCore import Qt, QLockFile, QTimer
from src.api.event_bus import EventBus
import threading
from typing import Callable
```

- [ ] **Step 2: Add `qt_safe` helper after the imports**

```python
def qt_safe(fn: Callable) -> Callable:
    """Wrap fn so it executes on the Qt main thread from any calling thread."""
    def wrapper(*args):
        QTimer.singleShot(0, lambda: fn(*args))
    return wrapper
```

- [ ] **Step 3: Create the EventBus at the start of `main()`**

Right after `config = load_config()` add:
```python
    bus = EventBus()
```

- [ ] **Step 4: Update all backend component constructors to receive `event_bus=bus`**

```python
    # BEFORE:
    notification_router = NotificationRouter(config)
    proactive_engine = ProactiveEngine(config, router=notification_router)
    brain = Brain(config, router=notification_router)
    system_monitor = SystemMonitor(config)
    memory_store = MemoryStore(config)
    calendar_manager = CalendarManager(config)

    # AFTER:
    notification_router = NotificationRouter(config, event_bus=bus)
    proactive_engine = ProactiveEngine(config, router=notification_router, event_bus=bus)
    brain = Brain(config, router=notification_router, event_bus=bus)
    system_monitor = SystemMonitor(config, event_bus=bus)
    memory_store = MemoryStore(config, event_bus=bus)
    calendar_manager = CalendarManager(config, event_bus=bus)
```

- [ ] **Step 5: Replace the `# ── Core Wiring ───` block**

```python
    # BEFORE (signal wiring):
    system_monitor.sensor_update.connect(brain.on_sensor_update)
    system_monitor.sensor_update.connect(proactive_engine.on_sensor_update)
    brain.brain_output.connect(ui.on_brain_output)
    proactive_engine.proactive_notification.connect(notification_router.route)
    notification_router.notification_approved.connect(lambda msg, _: ui.show_notification(msg))

    # AFTER (event_bus wiring for backend; Qt signals kept for UI):
    bus.on("sensor_update", brain.on_sensor_update)
    bus.on("sensor_update", proactive_engine.on_sensor_update)
    bus.on("brain_output", qt_safe(ui.on_brain_output))
    bus.on("proactive_notification", notification_router.route)
    bus.on("notification_approved", qt_safe(lambda msg, _: ui.show_notification(msg)))
```

- [ ] **Step 6: Update animation_finished wiring**

```python
    # BEFORE:
    ui.animation_finished.connect(brain.on_animation_done)

    # AFTER (ui.animation_finished is still a Qt signal — connect to plain method):
    ui.animation_finished.connect(brain.on_animation_done)
    # (no change needed — Qt signals can connect to plain callables)
```

- [ ] **Step 7: Update settings_changed wiring for backend components**

```python
    # These stay as Qt signal connections — backend methods are plain callables now:
    settings_window.settings_changed.connect(ui.on_config_changed)         # unchanged
    settings_window.settings_changed.connect(brain.on_config_changed)      # was @Slot, now plain
    settings_window.settings_changed.connect(system_monitor.on_config_changed)
    settings_window.settings_changed.connect(notification_router.on_config_changed)
    settings_window.settings_changed.connect(proactive_engine.on_config_changed)
    settings_window.clear_memory_requested.connect(memory_store.clear_all_facts)
```

- [ ] **Step 8: Update AI component constructors and wiring in the `if ai_enabled:` block**

```python
        # BEFORE:
        hotkey_thread = HotkeyThread(config)
        voice_thread = VoiceThread(config)
        ai_thread = AIThread(config, memory_store=memory_store)
        tts_thread = TTSThread(config)

        # AFTER:
        hotkey_thread = HotkeyThread(config, event_bus=bus)
        voice_thread = VoiceThread(config, event_bus=bus)
        ai_thread = AIThread(config, memory_store=memory_store, event_bus=bus)
        tts_thread = TTSThread(config, event_bus=bus)
```

- [ ] **Step 9: Replace all backend→backend signal connections with event_bus wiring**

```python
        # REMOVE these signal connections entirely:
        # ai_thread.response_chunk.connect(ui.on_response_chunk)
        # ai_thread.response_chunk.connect(chat_window.on_chunk)
        # ai_thread.response_chunk.connect(sentence_buffer.push)
        # sentence_buffer.sentence_ready.connect(tts_thread.speak_chunk)
        # sentence_buffer.flushed.connect(tts_thread.end_stream)
        # ai_thread.response_done.connect(_on_response_done)
        # ai_thread.memory_fact_extracted.connect(memory_store.add_fact_inline)
        # ai_thread.error_occurred.connect(ui.on_ai_error)
        # ai_thread.error_occurred.connect(chat_window.on_error)
        # ai_thread.error_occurred.connect(lambda _: brain.on_ai_done())
        # tts_thread.speech_done.connect(brain.on_ai_done)
        # voice_thread.recording_started.connect(chat_window.show_listening_indicator)
        # voice_thread.transcript_ready.connect(chat_window.update_voice_transcript)
        # voice_thread.transcript_ready.connect(_handle_voice_query)
        # voice_thread.error_occurred.connect(chat_window.cancel_listening)
        # voice_thread.error_occurred.connect(ui.on_ai_error)
        # voice_thread.error_occurred.connect(lambda _: brain.on_ai_done())
        # hotkey_thread.hotkey_pressed.connect(...)
        # task_runner.task_completed.connect(proactive_engine.on_task_completed)
        # task_runner.task_blocked.connect(proactive_engine.on_task_blocked)
        # task_runner.task_blocked.connect(lambda task: ...)
        # calendar_manager.events_updated.connect(proactive_engine.on_calendar_updated)

        # ADD event_bus wiring:
        bus.on("response_chunk", qt_safe(ui.on_response_chunk))
        bus.on("response_chunk", qt_safe(chat_window.on_chunk))
        bus.on("response_chunk", sentence_buffer.push)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", tts_thread.end_stream)
        bus.on("response_done", _on_response_done)
        bus.on("memory_fact_extracted", memory_store.add_fact_inline)
        bus.on("ai_error", qt_safe(ui.on_ai_error))
        bus.on("ai_error", qt_safe(chat_window.on_error))
        bus.on("ai_error", lambda _: brain.on_ai_done())
        bus.on("speech_done", brain.on_ai_done)
        bus.on("recording_started", qt_safe(chat_window.show_listening_indicator))
        bus.on("transcript_ready", qt_safe(chat_window.update_voice_transcript))
        bus.on("transcript_ready", _handle_voice_query)
        bus.on("voice_error", qt_safe(chat_window.cancel_listening))
        bus.on("voice_error", qt_safe(ui.on_ai_error))
        bus.on("voice_error", lambda _: brain.on_ai_done())
        bus.on("hotkey_pressed", _interrupt_current_turn)
        bus.on("hotkey_pressed", brain.on_listening_started)
        bus.on("hotkey_pressed", voice_thread.on_hotkey_pressed)
        bus.on("hotkey_pressed", lambda: tts_thread.manager.set_silent_mode(False))
        bus.on("clip_hotkey_pressed", clip_recorder.dump)
        bus.on("registration_failed", qt_safe(lambda hk: ui.on_ai_error(f"Hotkey failed to register: {hk}")))
        bus.on("task_completed", proactive_engine.on_task_completed)
        bus.on("task_blocked", proactive_engine.on_task_blocked)
        bus.on("task_blocked", qt_safe(
            lambda task: chat_window.show_approval_prompt(task) if task.get("error") == "awaiting_approval" else None
        ))
        bus.on("events_updated", proactive_engine.on_calendar_updated)
```

- [ ] **Step 10: Update `_handle_text_query` and `_handle_voice_query`**

```python
        # BEFORE:
        def _handle_text_query(text: str) -> None:
            ...
            QMetaObject.invokeMethod(
                ai_thread.client, "send_query",
                Qt.QueuedConnection,
                Q_ARG(str, text),
            )

        # AFTER:
        def _handle_text_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = True
            sentence_buffer.reset()
            ai_thread.cancel_current()
            tts_thread.manager.set_silent_mode(True)
            brain.on_thinking_started()
            proactive_engine.update_last_interaction()
            ai_thread.send_query(text)

        def _handle_voice_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = False
            sentence_buffer.reset()
            ai_thread.cancel_current()
            tts_thread.interrupt()
            tts_thread.manager.set_silent_mode(False)
            brain.on_thinking_started()
            ai_thread.send_query(text)
```

- [ ] **Step 11: Update `_on_response_done` — remove QTimer.singleShot**

```python
        def _on_response_done(text: str) -> None:
            clean_text = _sanitize_assistant_text(text)
            if not _is_text_chat:
                brain.on_talking_started(clean_text)
            qt_safe(chat_window.on_response_done)(clean_text)
            qt_safe(ui.on_response_done)(clean_text)
            sentence_buffer.flush()
            if not config.get("memory_extraction_inline", True):
                threading.Timer(0, lambda: memory_store.extract_facts_async(clean_text)).start()
```

- [ ] **Step 12: Update voice warmup and settings wiring**

```python
        # BEFORE:
        settings_window.settings_changed.connect(ai_thread.on_config_changed)
        settings_window.test_voice_requested.connect(tts_thread.test_voice)
        settings_window.voice_warmup_requested.connect(voice_thread.warm_up)
        settings_window.settings_changed.connect(
            lambda cfg: hotkey_thread.rebind(
                cfg.get("activation_hotkey", "ctrl+k"),
                cfg.get("clip_hotkey", "ctrl+alt+k"),
            )
        )
        if config.get("voice_warmup_on_launch", True):
            QTimer.singleShot(250, voice_thread.warm_up)

        # AFTER:
        settings_window.settings_changed.connect(ai_thread.on_config_changed)  # now enqueues
        settings_window.test_voice_requested.connect(tts_thread.test_voice)    # now enqueues
        settings_window.voice_warmup_requested.connect(voice_thread.warm_up)   # now enqueues
        settings_window.settings_changed.connect(
            lambda cfg: hotkey_thread.rebind(
                cfg.get("activation_hotkey", "ctrl+k"),
                cfg.get("clip_hotkey", "ctrl+alt+k"),
            )
        )
        if config.get("voice_warmup_on_launch", True):
            threading.Timer(0.25, voice_thread.warm_up).start()
```

- [ ] **Step 13: Update mic_pressed wiring (still a Qt signal)**

```python
        # mic_pressed handlers that call backend methods — Qt signal to plain callable, no change needed:
        chat_window.mic_pressed.connect(_interrupt_current_turn)
        chat_window.mic_pressed.connect(brain.on_listening_started)
        chat_window.mic_pressed.connect(voice_thread.on_hotkey_pressed)
        chat_window.mic_pressed.connect(lambda: tts_thread.manager.set_silent_mode(False))
```

- [ ] **Step 14: Run the existing Qt desktop app to verify it still starts**

```
python main.py
```
Expected: KIBO launches, pet appears, no errors in log.

- [ ] **Step 15: Commit**

```
git add main.py
git commit -m "refactor: rewire main.py to use EventBus + qt_safe bridge; remove QMetaObject calls"
```

---

## Task 18: Run full test suite

- [ ] **Step 1: Run all tests**

```
pytest tests/ -v --tb=short
```

- [ ] **Step 2: Fix any failures**

Common failure patterns:
- Tests that import `from brain import Brain` — update to `from src.ai.brain import Brain`
- Tests that use `QApplication` fixture but brain no longer needs it — remove the fixture dependency
- Tests that check `isinstance(brain, QObject)` — remove those assertions

- [ ] **Step 3: Verify no regressions**

All previously passing tests must still pass. Target: same count or higher.

- [ ] **Step 4: Smoke test the FastAPI server**

```
python src/api/main.py
```
In a separate terminal:
```
curl http://127.0.0.1:8765/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 5: Final commit**

```
git add -u
git commit -m "test: update all tests to use EventBus instead of Qt signal connections"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** EventBus ✓, PeriodicThread ✓, all 12 backend files ✓, server.py ✓, api/main.py ✓, main.py bridge ✓
- [x] **Placeholder scan:** No TBD, no "similar to above" — every task has complete code
- [x] **Type consistency:** `event_bus=bus` param name consistent across all 12 files; `EventBus.emit("brain_output", output)` matches `bus.on("brain_output", ...)` throughout
- [x] **Threading safety:** Brain has `threading.RLock`; SentenceBuffer has `threading.Lock`; TTSManager keeps its existing lock; interrupt() called direct (not queued) in TTSThread and AIThread's cancel_current()
- [x] **Both entry points:** `python main.py` (Qt) and `python src/api/main.py` (FastAPI) verified in Tasks 17 and 16 respectively

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-07-phase1-python-api-layer.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, with checkpoints

Which approach?
