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
