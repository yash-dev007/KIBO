# KIBO Revive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean junk from the project root, delete the dead PySide6 UI layer, fix three CPU-wasting patterns, add async dispatch to EventBus, and split memory_store.py into focused modules.

**Architecture:** The Electron+React frontend is the active UI; Python backend runs headlessly via `src/api/main.py` + uvicorn. Root `main.py` becomes a thin shim. All backend components communicate through EventBus; the FastAPI server bridges events to WebSocket clients.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, pytest, threading, concurrent.futures

---

## File Map

| Action | File | Responsibility after change |
|--------|------|-----------------------------|
| DELETE | `pytest-cache-files-qwj5_0bn/`, `pytest-temp-check/`, `pytest-temp-check2/`, `.test_tmp/`, `.tmp/`, `__pycache__/` (root), `.pytest_cache/`, `build/`, `dist/`, `docs/superpowers/`, `.worktrees/`, `KIBO.txt`, `check_incremental.py`, `run_ast.py` | Gone |
| DELETE | `src/ui/` (entire dir) + `tests/test_animation_engine.py`, `tests/test_onboarding_window.py`, `tests/test_settings_window.py` | Gone |
| MODIFY | `src/ai/ai_client.py` | AIThread.run() uses blocking get + None sentinel |
| MODIFY | `src/system/system_monitor.py` | on_config_changed joins old thread before starting new |
| MODIFY | `src/api/event_bus.py` | on() accepts async_dispatch kwarg; executor dispatches heavy handlers |
| CREATE | `src/ai/memory_io.py` | YAML frontmatter parse/build helpers |
| CREATE | `src/ai/memory_dashboard.py` | MemoryDashboard: Obsidian dashboard writer |
| MODIFY | `src/ai/memory_store.py` | Slim CRUD coordinator; fixes Qt signal bug; removes duplicate delete_fact |
| MODIFY | `src/api/server.py` | Forwards brain_output to state WebSocket; emits chat_query_received |
| MODIFY | `main.py` | Thin shim → delegates to src.api.main.start() |

---

## Task 1: Delete junk files and directories

**Files:** Root-level artifact dirs and files only.

- [ ] **Step 1: Delete pytest artifact dirs**

```powershell
Remove-Item -Recurse -Force D:\Projects\KIBO\pytest-cache-files-qwj5_0bn
Remove-Item -Recurse -Force D:\Projects\KIBO\pytest-temp-check
Remove-Item -Recurse -Force D:\Projects\KIBO\pytest-temp-check2
Remove-Item -Recurse -Force "D:\Projects\KIBO\.test_tmp"
Remove-Item -Recurse -Force "D:\Projects\KIBO\.tmp"
Remove-Item -Recurse -Force "D:\Projects\KIBO\__pycache__"
Remove-Item -Recurse -Force "D:\Projects\KIBO\.pytest_cache"
```

- [ ] **Step 2: Delete stale build artifacts**

```powershell
Remove-Item -Recurse -Force D:\Projects\KIBO\build
Remove-Item -Recurse -Force D:\Projects\KIBO\dist
```

- [ ] **Step 3: Delete old AI planning docs and worktrees**

```powershell
Remove-Item -Recurse -Force "D:\Projects\KIBO\docs\superpowers"
Remove-Item -Recurse -Force "D:\Projects\KIBO\.worktrees"
```

- [ ] **Step 4: Delete loose root files**

```powershell
Remove-Item "D:\Projects\KIBO\KIBO.txt"
Remove-Item "D:\Projects\KIBO\check_incremental.py"
Remove-Item "D:\Projects\KIBO\run_ast.py"
```

- [ ] **Step 5: Verify root is clean**

```powershell
Get-ChildItem D:\Projects\KIBO -Force | Select-Object Name
```

Expected: only `.claude`, `.git`, `.gitignore`, `.obsidian`, `assets`, `docs`, `frontend`, `main.py`, `models`, `packaging`, `pytest.ini`, `README.md`, `requirements.txt`, `scripts`, `src`, `tests`, `config.json`, `config.example.json`, `CONTRIBUTING.md`, `LICENSE`, `KIBO.bat`

- [ ] **Step 6: Commit**

```bash
cd D:/Projects/KIBO
git add -A
git commit -m "chore: delete junk artifacts, pytest temps, stale build dirs, old planning docs"
```

---

## Task 2: Delete PySide6 UI layer and dead tests

**Files:**
- Delete: `src/ui/` (entire directory)
- Delete: `tests/test_animation_engine.py`, `tests/test_onboarding_window.py`, `tests/test_settings_window.py`

- [ ] **Step 1: Delete the entire src/ui directory**

```powershell
Remove-Item -Recurse -Force D:\Projects\KIBO\src\ui
```

- [ ] **Step 2: Delete dead test files that only test the deleted UI**

```powershell
Remove-Item D:\Projects\KIBO\tests\test_animation_engine.py
Remove-Item D:\Projects\KIBO\tests\test_onboarding_window.py
Remove-Item D:\Projects\KIBO\tests\test_settings_window.py
```

- [ ] **Step 3: Run remaining tests to verify nothing else depended on src/ui**

```bash
cd D:/Projects/KIBO
python -m pytest tests/ -x -q --ignore=tests/test_animation_engine.py --ignore=tests/test_onboarding_window.py --ignore=tests/test_settings_window.py 2>&1 | head -40
```

Expected: tests pass (any failures at this point are pre-existing, not caused by UI deletion).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead PySide6 UI layer and associated tests"
```

---

## Task 3: Fix AIThread busy-wait

**Files:**
- Modify: `src/ai/ai_client.py:325-371`
- Test: `tests/test_ai_client.py`

- [ ] **Step 1: Write the failing test**

Open `tests/test_ai_client.py` and add at the end:

```python
def test_ai_thread_stops_without_busy_wait():
    """AIThread.stop() must unblock a thread waiting on queue.get() with no timeout."""
    import time
    config = {"conversation_history_limit": 10, "memory_extraction_inline": True}
    thread = AIThread(config, memory_store=None, event_bus=None)
    thread.start()
    time.sleep(0.05)
    t0 = time.time()
    thread.stop()
    thread.join(timeout=1.0)
    elapsed = time.time() - t0
    assert not thread.is_alive(), "AIThread did not stop within 1 second"
    assert elapsed < 0.5, f"stop() took {elapsed:.2f}s — sentinel not working"
```

- [ ] **Step 2: Run to confirm it currently passes (it should — stop sets the event, run exits on next 0.1s tick)**

```bash
python -m pytest tests/test_ai_client.py::test_ai_thread_stops_without_busy_wait -v
```

This test currently passes but for the wrong reason (0.1s timeout). After the fix it will pass faster. The real guard is the elapsed < 0.5 assertion — if you remove `timeout=0.1`, the old `stop()` (which only sets `_stop_event`) will leave the thread blocked forever and `is_alive()` will be True.

- [ ] **Step 3: Rewrite AIThread.run() and stop() in `src/ai/ai_client.py`**

Find the `class AIThread` section (around line 325) and replace `__init__`, `run`, and `stop`:

```python
class AIThread(threading.Thread):
    """Daemon thread that owns an AIClient and dispatches calls via a queue."""

    def __init__(
        self,
        config: dict,
        memory_store: Optional[MemoryStore] = None,
        event_bus=None,
    ) -> None:
        super().__init__(daemon=True)
        self._client = AIClient(config, memory_store, event_bus=event_bus)
        self._queue: queue.Queue[Optional[tuple]] = queue.Queue()

    @property
    def client(self) -> AIClient:
        return self._client

    def run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    break
                method, arg = item
                if arg is None:
                    getattr(self._client, method)()
                else:
                    getattr(self._client, method)(arg)
            finally:
                self._queue.task_done()

    def send_query(self, text: str) -> None:
        self._queue.put(("send_query", text))

    def cancel_current(self) -> None:
        self._client.cancel_current()

    def on_config_changed(self, new_config: dict) -> None:
        self._queue.put(("on_config_changed", new_config))

    def stop(self) -> None:
        self.cancel_current()
        self._queue.put(None)
```

- [ ] **Step 4: Run test suite to confirm fix works and nothing broke**

```bash
python -m pytest tests/test_ai_client.py -v
```

Expected: all pass including the new test.

- [ ] **Step 5: Commit**

```bash
git add src/ai/ai_client.py tests/test_ai_client.py
git commit -m "perf: fix AIThread busy-wait — blocking get + None sentinel replaces 100ms poll"
```

---

## Task 4: Fix SystemMonitor thread overlap

**Files:**
- Modify: `src/system/system_monitor.py:36-44`
- Test: `tests/test_system_monitor.py`

- [ ] **Step 1: Write the failing test**

Open `tests/test_system_monitor.py` and add:

```python
def test_config_change_joins_old_thread():
    """on_config_changed must fully stop the old PeriodicThread before starting a new one."""
    config = {"poll_interval_ms": 500}
    monitor = SystemMonitor(config, event_bus=None)
    monitor.start()
    old_thread = monitor._thread

    new_config = {"poll_interval_ms": 600}
    monitor.on_config_changed(new_config)

    # Old thread must be dead — not just stop()-ed but fully terminated
    old_thread.join(timeout=2.0)
    assert not old_thread.is_alive(), "Old PeriodicThread still alive after on_config_changed"

    monitor.stop()
```

- [ ] **Step 2: Run to confirm it fails (or passes for the wrong reason depending on timing)**

```bash
python -m pytest tests/test_system_monitor.py::test_config_change_joins_old_thread -v
```

- [ ] **Step 3: Add thread join in `src/system/system_monitor.py`**

Replace the `on_config_changed` method (lines 36-44):

```python
def on_config_changed(self, new_config: dict) -> None:
    self._config = new_config
    interval = new_config["poll_interval_ms"]
    if interval != self._current_interval and self._thread is not None:
        self._thread.stop()
        self._thread.join(timeout=1.0)
        self._current_interval = interval
        self._thread = PeriodicThread(self._current_interval, self._poll)
        self._thread.start()
        logger.info("SystemMonitor interval updated to %dms.", interval)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_system_monitor.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/system/system_monitor.py tests/test_system_monitor.py
git commit -m "fix: join old PeriodicThread before replacement in SystemMonitor.on_config_changed"
```

---

## Task 5: Add async_dispatch to EventBus

**Files:**
- Modify: `src/api/event_bus.py`
- Test: `tests/test_event_bus.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_event_bus.py` and add at the end:

```python
def test_async_dispatch_runs_handler_off_caller_thread():
    """Handlers registered with async_dispatch=True must run on a different thread."""
    import time
    bus = EventBus()
    caller_tid = threading.get_ident()
    handler_tids = []

    def slow_handler(val):
        handler_tids.append(threading.get_ident())

    bus.on("ev", slow_handler, async_dispatch=True)
    bus.emit("ev", 42)
    time.sleep(0.1)  # give executor time to run
    assert handler_tids, "Handler was never called"
    assert handler_tids[0] != caller_tid, "async_dispatch handler ran on caller thread"
    bus.shutdown()


def test_async_dispatch_does_not_block_emitter():
    """emit() must return immediately even if async handler is slow."""
    import time
    bus = EventBus()

    def blocking_handler(_):
        time.sleep(5)

    bus.on("ev", blocking_handler, async_dispatch=True)
    t0 = time.time()
    bus.emit("ev", 1)
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"emit() blocked for {elapsed:.2f}s"
    bus.shutdown()


def test_sync_handler_still_works_alongside_async():
    """Sync and async handlers on the same event must both be called."""
    import time
    bus = EventBus()
    sync_results = []
    async_results = []

    bus.on("ev", sync_results.append)
    bus.on("ev", async_results.append, async_dispatch=True)
    bus.emit("ev", 99)
    time.sleep(0.1)
    assert sync_results == [99]
    assert async_results == [99]
    bus.shutdown()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python -m pytest tests/test_event_bus.py::test_async_dispatch_runs_handler_off_caller_thread tests/test_event_bus.py::test_async_dispatch_does_not_block_emitter tests/test_event_bus.py::test_sync_handler_still_works_alongside_async -v
```

Expected: FAIL — `on()` does not accept `async_dispatch` kwarg yet.

- [ ] **Step 3: Rewrite `src/api/event_bus.py`**

```python
from __future__ import annotations

import concurrent.futures
import threading
from collections import defaultdict
from typing import Any, Callable


class EventBus:
    """Thread-safe pub/sub bus.

    Handlers registered with async_dispatch=True are dispatched onto a shared
    ThreadPoolExecutor so slow subscribers cannot block the emitting thread.
    Default behavior (async_dispatch=False) is unchanged: handlers run
    synchronously on the caller's thread.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[Callable, bool]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus")

    def on(self, event: str, handler: Callable, *, async_dispatch: bool = False) -> None:
        with self._lock:
            self._handlers[event].append((handler, async_dispatch))

    def off(self, event: str, handler: Callable) -> None:
        with self._lock:
            self._handlers[event] = [
                (h, a) for h, a in self._handlers[event] if h != handler
            ]

    def emit(self, event: str, *args: Any) -> None:
        with self._lock:
            handlers = list(self._handlers[event])
        for handler, async_dispatch in handlers:
            if async_dispatch:
                self._executor.submit(handler, *args)
            else:
                handler(*args)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
```

- [ ] **Step 4: Run full event bus test suite**

```bash
python -m pytest tests/test_event_bus.py -v
```

Expected: all pass including the 3 new tests. The existing `off()` test may fail if `off()` previously worked differently — fix: the new `off()` compares by identity (`is not handler`), which matches the old behavior.

- [ ] **Step 5: Commit**

```bash
git add src/api/event_bus.py tests/test_event_bus.py
git commit -m "feat: add async_dispatch option to EventBus to prevent slow handlers blocking emitter"
```

---

## Task 6: Extract memory_io.py

**Files:**
- Create: `src/ai/memory_io.py`
- Modify: `src/ai/memory_store.py` (remove the two helpers + their regexes, import from memory_io)
- Test: (inline in test_memory_store.py — add a direct test of the helpers)

- [ ] **Step 1: Write tests for the helpers**

Open `tests/test_memory_store.py` and add:

```python
from src.ai.memory_io import parse_frontmatter, build_frontmatter


def test_parse_frontmatter_extracts_meta_and_body():
    text = "---\nid: abc\ncategory: fact\nkeywords: [foo, bar]\nextracted_at: 1000\n---\n\nSome body text\n"
    meta, body = parse_frontmatter(text)
    assert meta["id"] == "abc"
    assert meta["category"] == "fact"
    assert meta["keywords"] == ["foo", "bar"]
    assert body == "Some body text"


def test_parse_frontmatter_no_frontmatter():
    text = "Just plain text"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == "Just plain text"


def test_build_frontmatter_roundtrip():
    meta = {"id": "abc", "category": "fact", "keywords": ["a", "b"], "extracted_at": 1000}
    fm = build_frontmatter(meta)
    assert fm.startswith("---")
    assert "id: abc" in fm
    assert "keywords: [a, b]" in fm
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python -m pytest tests/test_memory_store.py::test_parse_frontmatter_extracts_meta_and_body tests/test_memory_store.py::test_parse_frontmatter_no_frontmatter tests/test_memory_store.py::test_build_frontmatter_roundtrip -v
```

Expected: FAIL — `src.ai.memory_io` does not exist.

- [ ] **Step 3: Create `src/ai/memory_io.py`**

```python
"""memory_io.py — YAML frontmatter helpers for KIBO memory Markdown files."""
from __future__ import annotations

import re

_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text. Returns (meta, body)."""
    m = _FM_PATTERN.match(text)
    if not m:
        return {}, text

    meta: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        elif val.lower() in ("true", "false"):
            meta[key] = val.lower() == "true"
        elif val.isdigit():
            meta[key] = int(val)
        else:
            meta[key] = val.strip("'\"")

    return meta, text[m.end():].strip()


def build_frontmatter(meta: dict) -> str:
    """Build YAML frontmatter string from a dict."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)
```

- [ ] **Step 4: Run new tests**

```bash
python -m pytest tests/test_memory_store.py::test_parse_frontmatter_extracts_meta_and_body tests/test_memory_store.py::test_parse_frontmatter_no_frontmatter tests/test_memory_store.py::test_build_frontmatter_roundtrip -v
```

Expected: PASS.

- [ ] **Step 5: Update `src/ai/memory_store.py` — remove helpers, add import**

At the top of `memory_store.py`, replace:

```python
# ── YAML frontmatter helpers (no PyYAML dependency) ─────────────────────

_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LIST_ITEM = re.compile(r"^\s*-\s*(.+)$")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    ...  # entire function


def _build_frontmatter(meta: dict) -> str:
    ...  # entire function
```

With:

```python
from src.ai.memory_io import parse_frontmatter as _parse_frontmatter, build_frontmatter as _build_frontmatter
```

Also remove the `import re` line from memory_store.py if it's only used by the frontmatter helpers (check for other uses of `re` in the file first — `re.sub` is used in `_write_fact_locked`, so keep `import re`).

- [ ] **Step 6: Run full memory store test suite**

```bash
python -m pytest tests/test_memory_store.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/ai/memory_io.py src/ai/memory_store.py tests/test_memory_store.py
git commit -m "refactor: extract YAML frontmatter helpers into src/ai/memory_io.py"
```

---

## Task 7: Extract MemoryDashboard + fix memory_store bugs

**Files:**
- Create: `src/ai/memory_dashboard.py`
- Modify: `src/ai/memory_store.py` (slim down + fix Qt signal bugs + remove duplicate delete_fact)
- Test: `tests/test_memory_store.py`

**Bug context:** `memory_store.py` has three methods calling `self.facts_updated.emit()` (a Qt Signal that doesn't exist on this class) — `update_fact`, the second `delete_fact`, and `_extract_worker`. The correct call is `self._event_bus.emit("facts_updated")`. There is also a duplicate `delete_fact` method (lines 155 and 204) — the second (returning bool) is the intended one; the first must be removed.

- [ ] **Step 1: Write tests**

Open `tests/test_memory_store.py` and add:

```python
from src.ai.memory_dashboard import MemoryDashboard


def test_memory_dashboard_creates_file(tmp_path):
    dash = MemoryDashboard()
    output = tmp_path / "KIBO Dashboard.md"
    facts = [
        {"category": "fact", "content": "User likes Python", "source_session": "2026-05-09"},
        {"category": "preference", "content": "Prefers dark mode", "source_session": "2026-05-09"},
    ]
    dash.rebuild(facts, output)
    text = output.read_text("utf-8")
    assert "KIBO Memory Dashboard" in text
    assert "User likes Python" in text
    assert "Prefers dark mode" in text
    assert "fact".title() in text


def test_memory_dashboard_empty(tmp_path):
    dash = MemoryDashboard()
    output = tmp_path / "KIBO Dashboard.md"
    dash.rebuild([], output)
    text = output.read_text("utf-8")
    assert "Total memories: 0" in text


def test_delete_fact_emits_event_not_qt_signal(tmp_path, monkeypatch, bus):
    """delete_fact must use event_bus.emit, not self.facts_updated.emit (Qt bug)."""
    config = {"memory_enabled": True, "memory_model": "test", "ollama_base_url": "http://localhost:11434"}
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    store = MemoryStore(config, event_bus=bus)

    # Write a fake memory file
    mem_dir = tmp_path / "vault" / "memories"
    mem_dir.mkdir(parents=True, exist_ok=True)
    fact_id = "test01"
    (mem_dir / f"2026-05-09_fact_test_{fact_id}.md").write_text(
        f"---\nid: {fact_id}\ncategory: fact\nkeywords: []\nextracted_at: 1000\nsource_session: 2026-05-09\n---\n\nTest\n",
        "utf-8"
    )

    events = []
    bus.on("facts_updated", lambda: events.append("facts_updated"))

    # Must not raise AttributeError about facts_updated.emit
    result = store.delete_fact(fact_id)
    assert result is True
    assert "facts_updated" in events
```

- [ ] **Step 2: Run to confirm delete_fact test fails (Qt signal bug)**

```bash
python -m pytest tests/test_memory_store.py::test_delete_fact_emits_event_not_qt_signal -v
```

Expected: FAIL with `AttributeError: 'MemoryStore' object has no attribute 'facts_updated'`.

- [ ] **Step 3: Create `src/ai/memory_dashboard.py`**

```python
"""memory_dashboard.py — Obsidian dashboard generator for KIBO memories."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List

_CATEGORY_ICONS: Dict[str, str] = {
    "preference": "⭐", "fact": "📌", "person": "👤",
    "location": "📍", "task": "✅",
}


class MemoryDashboard:
    """Writes an Obsidian-friendly index of all memory facts to a Markdown file."""

    def rebuild(self, facts: List[dict], output_path: Path) -> None:
        grouped: Dict[str, List[dict]] = {}
        for f in facts:
            cat = f.get("category", "other")
            grouped.setdefault(cat, []).append(f)

        lines = [
            "# 🐾 KIBO Memory Dashboard",
            "",
            f"> Auto-generated. Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> Total memories: {len(facts)}",
            "",
        ]

        for cat in sorted(grouped.keys()):
            icon = _CATEGORY_ICONS.get(cat, "📝")
            lines.append(f"## {icon} {cat.title()}")
            lines.append("")
            for f in grouped[cat]:
                content = f.get("content", "")[:80]
                date = f.get("source_session", "unknown")
                lines.append(f"- {content} *({date})*")
            lines.append("")

        output_path.write_text("\n".join(lines), "utf-8")
```

- [ ] **Step 4: Update `src/ai/memory_store.py` — fix bugs, remove dashboard code, slim down**

**4a.** At the top of `memory_store.py`, add the import:
```python
from src.ai.memory_dashboard import MemoryDashboard
```

**4b.** In `__init__`, after setting `self._dashboard_path`, add:
```python
self._dashboard = MemoryDashboard()
```

**4c.** Replace `_rebuild_dashboard` with a one-liner delegation:
```python
def _rebuild_dashboard(self) -> None:
    with self._lock:
        facts = self._load_all()
    self._dashboard.rebuild(facts, self._dashboard_path)
```

**4d.** Remove the first `delete_fact` method (lines ~155-163 — the one that returns `None` and does not return a bool). Keep only the second `delete_fact` (returns `bool`).

**4e.** Fix all three `self.facts_updated.emit()` calls — replace each with:
```python
if self._event_bus:
    self._event_bus.emit("facts_updated")
```

The three locations are:
- `delete_fact` (the one returning bool, near the end of the method)
- `update_fact` (near the end of the method)
- `_extract_worker` (after `self._rebuild_dashboard()`)

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_memory_store.py -v
```

Expected: all pass including the three new tests.

- [ ] **Step 6: Run full test suite to catch regressions**

```bash
python -m pytest tests/ -q
```

Expected: no new failures.

- [ ] **Step 7: Verify file sizes are within limits**

```bash
wc -l D:/Projects/KIBO/src/ai/memory_store.py D:/Projects/KIBO/src/ai/memory_io.py D:/Projects/KIBO/src/ai/memory_dashboard.py
```

Expected: `memory_store.py` under 400 lines, others well under 200.

- [ ] **Step 8: Commit**

```bash
git add src/ai/memory_dashboard.py src/ai/memory_store.py tests/test_memory_store.py
git commit -m "refactor: extract MemoryDashboard, fix Qt signal bugs in MemoryStore, remove duplicate delete_fact"
```

---

## Task 8: Add brain_output forwarding to server.py

**Files:**
- Modify: `src/api/server.py`
- Test: `tests/test_server.py`

**Why:** The Electron PetSprite needs brain state changes (animation name, speech text) via the `/ws/state` WebSocket. Currently `brain_output` events are not forwarded by the server.

- [ ] **Step 1: Write the failing test**

Open `tests/test_server.py` and add:

```python
def test_brain_output_registered_on_state_bus():
    """server.create_app must subscribe to brain_output on the event bus."""
    from src.api.event_bus import EventBus
    from src.api.server import create_app

    bus = EventBus()
    create_app(bus)

    # brain_output must have at least one handler registered
    handlers = [h for h, _ in bus._handlers.get("brain_output", [])]
    assert handlers, "No brain_output handler registered — Electron pet will not animate"
    bus.shutdown()
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest tests/test_server.py::test_brain_output_registered_on_state_bus -v
```

Expected: FAIL — no `brain_output` handler registered.

- [ ] **Step 3: Add brain_output forwarding + chat_query_received to `src/api/server.py`**

After the existing `event_bus.on("task_blocked", ...)` line, add:

```python
def _forward_brain_output(output) -> None:
    _forward_state(
        "brain_output",
        state=output.state.name,
        animation=output.animation_name,
        speech=output.speech_text,
        loop=output.loop,
    )

event_bus.on("brain_output", _forward_brain_output)
```

In the `ws_chat` handler, replace:
```python
if msg.get("type") == "query" and ai_thread is not None:
    ai_thread.send_query(msg.get("text", ""))
```

With:
```python
if msg.get("type") == "query" and ai_thread is not None:
    event_bus.emit("chat_query_received", msg.get("text", ""))
    ai_thread.send_query(msg.get("text", ""))
```

- [ ] **Step 4: Run test**

```bash
python -m pytest tests/test_server.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_server.py
git commit -m "feat: forward brain_output to state WebSocket; emit chat_query_received on text input"
```

---

## Task 9: Simplify root main.py

**Files:**
- Modify: `main.py` (rewrite — 314 lines → ~20 lines)

Root `main.py` was the Qt entry point. `src/api/main.py` is already the complete headless backend. Replace the root with a thin shim.

- [ ] **Step 1: Verify src/api/main.py runs independently**

```bash
python -c "from src.api.main import start; print('import ok')"
```

Expected: `import ok` with no errors.

- [ ] **Step 2: Rewrite `main.py`**

```python
"""main.py — KIBO entry point.

Delegates entirely to the headless backend in src/api/main.
The Electron frontend connects to the FastAPI server via WebSocket.
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    from src.core.config_manager import FileConfigManager
    from src.api.main import start

    config_manager = FileConfigManager()
    sys.exit(start(config_manager.get_config()) or 0)
```

- [ ] **Step 3: Verify import chain works**

```bash
python -c "import main; print('main.py imports ok')"
```

Expected: `main.py imports ok` with no PySide6/Qt import errors.

- [ ] **Step 4: Run full test suite one final time**

```bash
python -m pytest tests/ -q
```

Expected: all tests pass, no failures.

- [ ] **Step 5: Verify no file in src/ exceeds 400 lines**

```bash
find D:/Projects/KIBO/src -name "*.py" | xargs wc -l | sort -rn | head -10
```

Expected: top file is under 400 lines.

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "refactor: replace Qt-based main.py with thin shim delegating to src/api/main"
```

---

## Final Verification

- [ ] Run `python -m pytest tests/ -v` — zero failures
- [ ] Check project root: `ls D:/Projects/KIBO/` — no artifact dirs visible
- [ ] Check `wc -l src/ai/memory_store.py` — under 400 lines
- [ ] Check `wc -l main.py` — under 25 lines
- [ ] Confirm `src/ui/` is gone: `ls D:/Projects/KIBO/src/` should show `ai api core system __init__.py`
