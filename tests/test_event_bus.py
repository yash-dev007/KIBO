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
    bus.shutdown()


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
    time.sleep(0.1)
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
