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
    assert len(count) == snapshot


def test_is_daemon():
    t = PeriodicThread(interval_ms=100, callback=lambda: None)
    assert t.daemon is True


def test_stop_is_idempotent():
    t = PeriodicThread(interval_ms=50, callback=lambda: None)
    t.start()
    t.stop()
    t.stop()  # must not raise
