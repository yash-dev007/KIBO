"""
tests/test_api_main.py — Tests for the pure-Python headless backend composition.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.api.event_bus import EventBus
from src.core.config_manager import DEFAULT_CONFIG


@pytest.fixture
def config(tmp_path, monkeypatch):
    cfg = dict(DEFAULT_CONFIG)
    cfg["ai_enabled"] = False  # skip AI threads in composition tests
    monkeypatch.setattr("src.api.main.get_user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("src.system.task_runner.get_user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("src.ai.memory_store.get_user_data_dir", lambda: tmp_path)
    return cfg


def test_create_backend_returns_components(config):
    from src.api.main import create_backend

    components = create_backend(config)

    assert "event_bus" in components
    assert "brain" in components
    assert "memory_store" in components
    assert "system_monitor" in components
    assert "proactive_engine" in components
    assert "task_runner" in components
    assert "notification_router" in components


def test_sensor_update_wired_to_brain(config, monkeypatch):
    from src.api.main import create_backend
    from src.ai.brain import SensorData

    components = create_backend(config)
    bus: EventBus = components["event_bus"]
    brain = components["brain"]

    import datetime
    sensor = SensorData(
        battery_percent=80.0,
        cpu_percent=10.0,
        active_window="test",
        current_hour=datetime.datetime.now().hour,
    )
    # Verify wiring: emitting sensor_update should not raise and brain responds
    called = []
    original = brain.on_sensor_update
    brain.on_sensor_update = lambda d: called.append(d) or original(d)
    bus.on("sensor_update", brain.on_sensor_update)

    bus.emit("sensor_update", sensor)

    assert len(called) == 1
    assert called[0].battery_percent == 80.0


def test_task_completed_wired_to_proactive(config, monkeypatch):
    from src.api.main import create_backend

    components = create_backend(config)
    bus: EventBus = components["event_bus"]
    engine = components["proactive_engine"]

    initial_done = engine._tasks_done_today
    bus.emit("task_completed", {"id": "x"})
    assert engine._tasks_done_today == initial_done + 1


def test_memory_fact_wired_to_store(config):
    from src.api.main import create_backend

    components = create_backend(config)
    bus: EventBus = components["event_bus"]
    memory_store = components["memory_store"]

    bus.emit("memory_fact_extracted", {
        "content": "User likes Python",
        "category": "preference",
        "keywords": [],
    })

    facts = memory_store.get_all_facts()
    assert any(f["content"] == "User likes Python" for f in facts)


def test_create_app_uses_backend(config):
    from src.api.main import create_backend
    from src.api.server import create_app

    components = create_backend(config)
    app = create_app(
        components["event_bus"],
        config_manager=components.get("config_manager"),
        memory_store=components["memory_store"],
        task_runner=components["task_runner"],
    )

    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_backend_exposes_config_manager(config, tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.config_manager.get_app_root", lambda: tmp_path)
    monkeypatch.setattr("src.api.main.FileConfigManager", __import__(
        "src.core.config_manager", fromlist=["FileConfigManager"]
    ).FileConfigManager)

    from src.api.main import create_backend

    components = create_backend(config)
    config_manager = components["config_manager"]

    config_manager.update_config({"buddy_skin": "bubbles"})

    assert config_manager.get_config()["buddy_skin"] == "bubbles"
    assert (tmp_path / "config.json").exists()
