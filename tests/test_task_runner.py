import pytest
import json
from unittest.mock import MagicMock
from src.system.task_runner import TaskRunner
from src.core.config_manager import DEFAULT_CONFIG

def test_task_runner_add_cancel(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    monkeypatch.setattr("task_runner.get_user_data_dir", lambda: tmp_path)
    
    mock_ai_client = MagicMock()
    runner = TaskRunner(config, mock_ai_client)
    
    t_id = runner.add_task("Test Task", "Desc")
    tasks = runner.get_tasks()
    
    assert len(tasks) == 1
    assert tasks[0]["id"] == t_id
    assert tasks[0]["state"] == "pending"
    
    runner.cancel_task(t_id)
    tasks = runner.get_tasks()
    assert tasks[0]["state"] == "cancelled"

def test_task_runner_approval_blocked(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    monkeypatch.setattr("task_runner.get_user_data_dir", lambda: tmp_path)
    
    mock_ai_client = MagicMock()
    runner = TaskRunner(config, mock_ai_client)
    
    t_id = runner.add_task("Approve me", "Desc", requires_approval=True)
    
    blocked_emitted = []
    runner.task_blocked.connect(lambda t: blocked_emitted.append(t))
    
    runner._process_queue()
    
    assert len(blocked_emitted) == 1
    assert blocked_emitted[0]["error"] == "awaiting_approval"
    
    tasks = runner.get_tasks()
    assert tasks[0]["state"] == "blocked"
    
    runner.approve_task(t_id)
    tasks = runner.get_tasks()
    assert tasks[0]["state"] == "in_progress" or tasks[0]["state"] == "pending" # Because process_queue runs immediately after approve, but we mock httpx
