# KIBO Revive — Design Spec
**Date:** 2026-05-09  
**Scope:** Cleanup + performance fixes + code quality (Option B)

---

## 1. Cleanup

### Directories to delete
| Path | Reason |
|------|--------|
| `pytest-cache-files-qwj5_0bn/` | Stale pytest artifact committed by mistake |
| `pytest-temp-check/` | Temp test dir left at root |
| `pytest-temp-check2/` | Temp test dir left at root |
| `.test_tmp/` | Temp directory |
| `.tmp/` | Temp directory |
| `__pycache__/` (root only) | Compiled bytecode for root main.py |
| `.pytest_cache/` | Pytest cache |
| `build/` | Stale PyInstaller build artifacts |
| `dist/` | Stale Electron/Python dist artifacts |
| `docs/superpowers/` | All AI-generated planning docs (user confirmed delete) |
| `.worktrees/` | Old git worktree state (user opted out of worktrees permanently) |

### Files to delete
| Path | Reason |
|------|--------|
| `KIBO.txt` | Empty file, no purpose |
| `check_incremental.py` | Loose root script, not imported anywhere |
| `run_ast.py` | Loose root script, not imported anywhere |

### Source code to delete — PySide6 UI layer
The Electron + React frontend is the active UI. The entire PySide6 layer is dead code.

**Delete `src/ui/` entirely:**
- `animation_engine.py`
- `chat_window.py`
- `clip_recorder.py`
- `onboarding_window.py`
- `settings_window.py`
- `tray_manager.py`
- `ui_manager.py`
- `__init__.py`

**Delete associated dead tests:**
- `tests/test_animation_engine.py`
- `tests/test_onboarding_window.py`
- `tests/test_settings_window.py`
- `tests/test_chat_window.py` (if present)

**Strip `main.py`** of all `from src.ui import ...` and Qt application boot code (~120 lines removed).

### What stays
`scripts/`, `packaging/`, `models/`, `assets/`, `docs/CREATE_CHARACTER.md`, all `src/` outside `src/ui/`.

---

## 2. Performance Fixes

### Fix 1 — AIThread busy-wait (`src/ai/ai_client.py`)
**Problem:** `run()` polls `queue.get(timeout=0.1)` in a tight loop — 10 thread wakeups/sec doing nothing when idle.

**Fix:** Switch to blocking `queue.get()` (no timeout). Send a `None` sentinel via `stop()` to unbreak the block on shutdown.

```python
# Before
item = self._queue.get(timeout=0.1)  # wakes up 10x/sec

# After
item = self._queue.get()  # blocks until work arrives
if item is None:
    break
```

`stop()` becomes: `self._queue.put(None)` + `self._stop_event.set()`.

### Fix 2 — SystemMonitor thread overlap (`src/system/system_monitor.py`)
**Problem:** `on_config_changed` stops the old `PeriodicThread` but doesn't join it before starting the new one. Rapid config changes can stack overlapping poll threads.

**Fix:** Call `self._thread.join()` (with a short timeout) after `stop()` before creating the replacement thread.

### Fix 3 — EventBus async dispatch (`src/api/event_bus.py`)
**Problem:** All handlers run synchronously on the emitting thread. A slow Brain handler blocks the SystemMonitor poll thread.

**Fix:** Add optional `async_dispatch` parameter to `on()`. Subscriptions with `async_dispatch=True` are dispatched onto a shared `ThreadPoolExecutor(max_workers=4)` instead of the caller's thread. Default is `False` — existing behavior unchanged.

```python
def on(self, event: str, handler: Callable, *, async_dispatch: bool = False) -> None:
    ...
```

Heavy consumers (Brain, MemoryStore migration) opt in via `async_dispatch=True`.

---

## 3. Code Quality

### Split `memory_store.py` (471 lines → 3 files)

| New file | Contents | Est. lines |
|----------|----------|-----------|
| `src/ai/memory_io.py` | YAML frontmatter parsing, markdown read/write helpers | ~120 |
| `src/ai/memory_store.py` | `MemoryStore` class — CRUD, search, migration orchestration | ~200 |
| `src/ai/memory_dashboard.py` | `MemoryDashboard` class — Obsidian dashboard generation | ~80 |

`MemoryStore.__init__` accepts a `MemoryDashboard` instance and delegates `_rebuild_dashboard()` to it. Public API surface is unchanged — no call sites change.

### Simplify `main.py`
After Qt boot code removal (~120 lines), `main.py` should land around 190 lines covering:
1. Config loading
2. Core backend wiring (EventBus, Brain, AIThread, SystemMonitor, MemoryStore, TaskRunner)
3. FastAPI server startup via uvicorn

If still above 200 lines, extract wiring into `src/core/wiring.py` and keep `main.py` as a thin entry point.

---

## Constraints
- No changes to public APIs of `MemoryStore`, `EventBus`, `AIClient`, or `Brain`
- All existing passing tests must continue to pass after the refactor
- Dead test files (testing deleted PySide6 code) are deleted, not fixed
- No worktrees — all work on current branch

## Success Criteria
- `pytest` passes with no failures after cleanup
- `AIThread` CPU contribution drops to ~0% when idle (verifiable with Task Manager)
- No file in `src/` exceeds 400 lines
- `main.py` under 200 lines
- Project root contains no artifact dirs (no `__pycache__`, no `pytest-*`, no `build/`, no `dist/`)
