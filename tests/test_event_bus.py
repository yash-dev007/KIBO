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
