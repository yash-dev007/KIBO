import pytest
import json
from unittest.mock import MagicMock
from src.api.event_bus import EventBus
from src.system.task_runner import TaskRunner
from src.core.config_manager import DEFAULT_CONFIG


@pytest.fixture
def bus():
    return EventBus()


def test_task_runner_add_cancel(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    monkeypatch.setattr("src.system.task_runner.get_user_data_dir", lambda: tmp_path)

    runner = TaskRunner(config, MagicMock(), event_bus=bus)

    t_id = runner.add_task("Test Task", "Desc")
    tasks = runner.get_tasks()

    assert len(tasks) == 1
    assert tasks[0]["id"] == t_id
    assert tasks[0]["state"] == "pending"

    runner.cancel_task(t_id)
    assert runner.get_tasks()[0]["state"] == "cancelled"


def test_get_tasks_does_not_expose_internal_state(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    monkeypatch.setattr("src.system.task_runner.get_user_data_dir", lambda: tmp_path)

    runner = TaskRunner(config, MagicMock(), event_bus=bus)
    runner.add_task("Keep safe", "Desc")

    tasks = runner.get_tasks()
    tasks[0]["state"] = "completed"

    assert runner.get_tasks()[0]["state"] == "pending"


def test_task_runner_approval_blocked(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    monkeypatch.setattr("src.system.task_runner.get_user_data_dir", lambda: tmp_path)

    runner = TaskRunner(config, MagicMock(), event_bus=bus)

    class DummyThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr("src.system.task_runner.threading.Thread", DummyThread)

    t_id = runner.add_task("Approve me", "Desc", requires_approval=True)

    blocked_emitted = []
    bus.on("task_blocked", blocked_emitted.append)

    runner._process_queue()

    assert len(blocked_emitted) == 1
    assert blocked_emitted[0]["error"] == "awaiting_approval"

    tasks = runner.get_tasks()
    assert tasks[0]["state"] == "blocked"

    runner.approve_task(t_id)
    # approve_task immediately calls _process_queue, which moves it to in_progress
    assert runner.get_tasks()[0]["state"] == "in_progress"
