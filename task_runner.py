import json
import logging
import uuid
import datetime
import threading
import httpx
from typing import Optional, List, Dict
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

from ai_client import AIClient
from config_manager import get_user_data_dir

logger = logging.getLogger(__name__)

class TaskRunner(QObject):
    task_completed  = Signal(dict)
    task_failed     = Signal(dict)
    task_blocked    = Signal(dict)
    task_started    = Signal(dict)
    status_update   = Signal(str)

    def __init__(self, config: dict, ai_client: AIClient) -> None:
        super().__init__()
        self._config = config
        self._ai_client = ai_client  # Used mainly for URL and model, or we can use our own logic
        self._base_url = config.get("ollama_base_url", "http://localhost:11434")
        self._model = config.get("ollama_model", "qwen2.5-coder:7b")
        
        self._tasks_file = get_user_data_dir() / "tasks.json"
        self._cost_file = get_user_data_dir() / "cost_state.json"
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._process_queue)
        
        self._active_worker = False

    def add_task(self, title: str, description: str, requires_approval: bool = False, source: str = "user") -> str:
        tasks = self.get_tasks()
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "state": "pending",
            "priority": "low",
            "source": source,
            "retry_count": 0,
            "max_retries": 3,
            "requires_approval": requires_approval,
            "created_at": int(datetime.datetime.now().timestamp()),
            "completed_at": None,
            "result": None,
            "error": None
        }
        tasks.append(task)
        self._save_tasks(tasks)
        return task_id

    def cancel_task(self, task_id: str) -> None:
        tasks = self.get_tasks()
        for t in tasks:
            if t["id"] == task_id and t["state"] in ("pending", "blocked"):
                t["state"] = "cancelled"
        self._save_tasks(tasks)

    def get_tasks(self) -> List[dict]:
        if not self._tasks_file.exists():
            return []
        try:
            return json.loads(self._tasks_file.read_text("utf-8"))
        except Exception:
            return []

    def _save_tasks(self, tasks: List[dict]) -> None:
        self._tasks_file.write_text(json.dumps(tasks, indent=2), "utf-8")

    def approve_task(self, task_id: str) -> None:
        tasks = self.get_tasks()
        for t in tasks:
            if t["id"] == task_id and t["state"] == "blocked" and t.get("error") == "awaiting_approval":
                t["requires_approval"] = False
                t["state"] = "pending"
                t["error"] = None
        self._save_tasks(tasks)
        self._process_queue()

    def start(self) -> None:
        self._timer.start(30000)

    def stop(self) -> None:
        self._timer.stop()

    def _check_rate_limit(self) -> bool:
        cost = {"hourly_calls": 0, "last_reset": 0}
        if self._cost_file.exists():
            try:
                cost = json.loads(self._cost_file.read_text("utf-8"))
            except Exception:
                pass
                
        now = int(datetime.datetime.now().timestamp())
        if now - cost["last_reset"] > 3600:
            cost["hourly_calls"] = 0
            cost["last_reset"] = now
            
        if cost["hourly_calls"] >= 20:
            return False
            
        cost["hourly_calls"] += 1
        self._cost_file.write_text(json.dumps(cost, indent=2), "utf-8")
        return True

    def _process_queue(self) -> None:
        if self._active_worker:
            return
            
        tasks = self.get_tasks()
        pending = [t for t in tasks if t["state"] == "pending"]
        if not pending:
            return
            
        # Prioritize older tasks or high priority
        pending.sort(key=lambda x: (x.get("priority", "low") != "high", x.get("created_at", 0)))
        task = pending[0]

        if task.get("requires_approval", False):
            task["state"] = "blocked"
            task["error"] = "awaiting_approval"
            self._save_tasks(tasks)
            self.task_blocked.emit(task)
            return

        if not self._check_rate_limit():
            self.status_update.emit("Rate limit reached. Pausing tasks.")
            return

        # Start execution
        self._active_worker = True
        task["state"] = "in_progress"
        self._save_tasks(tasks)
        self.task_started.emit(task)
        
        threading.Thread(target=self._run_task, args=(task,), daemon=True).start()

    def _run_task(self, task: dict) -> None:
        prompt = (
            f"You are an autonomous agent executing a background task.\n"
            f"Task: {task['title']}\n"
            f"Description: {task['description']}\n"
            f"Provide the final result directly."
        )
        
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        
        error_msg = None
        result_text = None
        
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                result_text = data.get("message", {}).get("content", "").strip()
        except Exception as e:
            error_msg = str(e)
            
        # We must re-fetch tasks before updating since they could have been modified
        tasks = self.get_tasks()
        t = next((t for t in tasks if t["id"] == task["id"]), None)
        if not t:
            self._active_worker = False
            return
            
        if error_msg:
            t["retry_count"] = t.get("retry_count", 0) + 1
            if t["retry_count"] >= t.get("max_retries", 3):
                t["state"] = "blocked"
                t["error"] = f"Max retries exceeded: {error_msg}"
                self._save_tasks(tasks)
                self.task_blocked.emit(t)
            else:
                t["state"] = "pending"
                t["error"] = error_msg
                self._save_tasks(tasks)
                self.task_failed.emit(t)
        else:
            t["state"] = "completed"
            t["completed_at"] = int(datetime.datetime.now().timestamp())
            t["result"] = result_text
            t["error"] = None
            self._save_tasks(tasks)
            self.task_completed.emit(t)
            
        self._active_worker = False
        # Optional: Can emit a signal to self._process_queue here if Qt QueuedConnection is used.
        # But timer will pick it up on next tick.
