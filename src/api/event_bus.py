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
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="eventbus"
        )

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
