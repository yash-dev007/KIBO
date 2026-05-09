"""
tests/test_server.py — FastAPI server endpoint tests.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.api.event_bus import EventBus
from src.api.server import create_app


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def memory_store():
    store = MagicMock()
    store.get_all_facts.return_value = [
        {"id": "1", "content": "User likes coffee", "category": "preference", "keywords": []}
    ]
    return store


@pytest.fixture
def config_manager():
    mgr = MagicMock()
    mgr.get_config.return_value = {"tts_enabled": True, "proactive_enabled": True}
    return mgr


@pytest.fixture
def task_runner():
    runner = MagicMock()
    runner.get_tasks.return_value = []
    return runner


@pytest.fixture
def client(bus, memory_store, config_manager, task_runner):
    app = create_app(bus, config_manager=config_manager,
                     memory_store=memory_store, task_runner=task_runner)
    return TestClient(app)


# ── Health ───────────────────────────────────────────────────────────────


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Settings ─────────────────────────────────────────────────────────────


def test_get_settings(client, config_manager):
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert resp.json()["tts_enabled"] is True


def test_post_settings(client, config_manager):
    resp = client.post("/settings", json={"tts_enabled": False})
    assert resp.status_code == 200
    config_manager.update_config.assert_called_once_with({"tts_enabled": False})


# ── Memory ───────────────────────────────────────────────────────────────


def test_get_memory_facts(client, memory_store):
    resp = client.get("/memory")
    assert resp.status_code == 200
    facts = resp.json()
    assert len(facts) == 1
    assert facts[0]["content"] == "User likes coffee"


def test_delete_memory_fact(client, memory_store):
    resp = client.delete("/memory/1")
    assert resp.status_code == 200
    memory_store.delete_fact.assert_called_once_with("1")


def test_put_memory_fact(client, memory_store):
    memory_store.update_fact.return_value = True
    resp = client.put("/memory/1", json={"content": "User likes tea"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    memory_store.update_fact.assert_called_once_with("1", {"content": "User likes tea"})


# ── Tasks ────────────────────────────────────────────────────────────────


def test_get_tasks(client, task_runner):
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_task(client, task_runner):
    task_runner.add_task.return_value = "abc-123"
    resp = client.post("/tasks", json={"title": "Do something", "description": "Details"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "abc-123"
    task_runner.add_task.assert_called_once_with("Do something", "Details")


def test_delete_task(client, task_runner):
    resp = client.delete("/tasks/abc-123")
    assert resp.status_code == 200
    task_runner.cancel_task.assert_called_once_with("abc-123")


# ── WebSocket /ws/chat ───────────────────────────────────────────────────


def test_ws_chat_send_triggers_query(bus, memory_store, config_manager, task_runner):
    ai_thread = MagicMock()
    app = create_app(bus, config_manager=config_manager,
                     memory_store=memory_store, task_runner=task_runner,
                     ai_thread=ai_thread)
    with TestClient(app).websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"type": "query", "text": "hello"}))
        # Give handler time to process
        import time; time.sleep(0.05)

    ai_thread.send_query.assert_called_once_with("hello")


def test_ws_chat_receives_response_chunk(bus, memory_store, config_manager, task_runner):
    app = create_app(bus, config_manager=config_manager,
                     memory_store=memory_store, task_runner=task_runner)
    with TestClient(app).websocket_connect("/ws/chat") as ws:
        bus.emit("response_chunk", "hello ")
        msg = ws.receive_text()

    data = json.loads(msg)
    assert data["type"] == "response_chunk"
    assert data["text"] == "hello "


def test_ws_chat_receives_response_done(bus, memory_store, config_manager, task_runner):
    app = create_app(bus, config_manager=config_manager,
                     memory_store=memory_store, task_runner=task_runner)
    with TestClient(app).websocket_connect("/ws/chat") as ws:
        bus.emit("response_done", "hello world")
        msg = ws.receive_text()

    data = json.loads(msg)
    assert data["type"] == "response_done"
    assert data["text"] == "hello world"


def test_brain_output_registered_on_state_bus(bus):
    """create_app must subscribe brain_output to the state WebSocket."""
    create_app(bus)
    handlers = [h for h, _ in bus._handlers.get("brain_output", [])]
    assert handlers, "No brain_output handler registered — Electron pet will not animate"
    bus.shutdown()


def test_chat_query_received_emitted_on_ws_message(bus, memory_store, config_manager):
    """Sending a query via WebSocket must emit chat_query_received on the bus."""
    from unittest.mock import MagicMock
    ai_thread = MagicMock()
    app = create_app(bus, config_manager=config_manager,
                     memory_store=memory_store, ai_thread=ai_thread)

    emitted = []
    bus.on("chat_query_received", emitted.append)

    with TestClient(app).websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"type": "query", "text": "hello"}))

    assert emitted == ["hello"]
    bus.shutdown()
