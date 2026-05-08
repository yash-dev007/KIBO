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
