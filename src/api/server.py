"""
server.py — FastAPI server bridging the Python backend to Electron/web frontends.

Endpoints:
  GET  /health              — liveness check
  GET  /settings            — read current config
  POST /settings            — update config (partial)
  GET  /memory              — list all memory facts
  DELETE /memory/{fact_id}  — delete a memory fact
  GET  /tasks               — list tasks
  POST /tasks               — add a task
  DELETE /tasks/{task_id}   — cancel a task
  WS   /ws/chat             — bidirectional chat + event stream
  WS   /ws/state            — system state broadcast
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.event_bus import EventBus

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 8000  # characters; bounds disk/memory per persisted message
ALLOWED_WS_ORIGINS = {
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
    "null",  # file:// origins (packaged Electron)
}


def _origin_allowed(websocket: WebSocket) -> bool:
    """Reject WS handshakes from origins outside the allow-list.

    Origin is absent for non-browser clients (e.g. tests, some Electron configs);
    those are allowed since they cannot be spoofed by a malicious web page.
    """
    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    return origin in ALLOWED_WS_ORIGINS


class _ConnectionSet:
    """Thread-safe set of active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


def create_app(
    event_bus: EventBus,
    *,
    config_manager=None,
    memory_store=None,
    task_runner=None,
    ai_thread=None,
    conversation_store=None,
) -> FastAPI:
    chat_conns = _ConnectionSet()
    state_conns = _ConnectionSet()
    _loop: list[asyncio.AbstractEventLoop] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _loop.append(asyncio.get_running_loop())
        yield

    app = FastAPI(title="KIBO API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Bus → WebSocket forwarding ────────────────────────────────────────

    def _forward_chat(event_type: str, **extra):
        async def _send():
            await chat_conns.broadcast({"type": event_type, **extra})

        if _loop:
            _loop[0].call_soon_threadsafe(_loop[0].create_task, _send())
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_send())
            except RuntimeError:
                asyncio.run(_send())

    event_bus.on("response_chunk", lambda text: _forward_chat("response_chunk", text=text))
    event_bus.on("response_done", lambda text: _forward_chat("response_done", text=text))
    event_bus.on("error_occurred", lambda msg: _forward_chat("error", message=msg))
    event_bus.on("transcript_ready", lambda text: _forward_chat("transcript_ready", text=text))
    event_bus.on("recording_started", lambda: _forward_chat("recording_started"))

    def _forward_state(event_type: str, **extra):
        async def _send():
            await state_conns.broadcast({"type": event_type, **extra})

        if _loop:
            _loop[0].call_soon_threadsafe(_loop[0].create_task, _send())
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_send())
            except RuntimeError:
                asyncio.run(_send())

    event_bus.on("task_completed", lambda t: _forward_state("task_completed", task=t))
    event_bus.on("task_blocked", lambda t: _forward_state("task_blocked", task=t))
    event_bus.on("proactive_notification",
                 lambda tp, msg, pri: _forward_state("proactive_notification",
                                                     notification_type=tp,
                                                     message=msg, priority=pri))

    def _forward_brain_output(output) -> None:
        _forward_state(
            "brain_output",
            state=output.state.name,
            animation=output.animation_name,
            speech=output.speech_text,
            loop=output.loop,
        )

    event_bus.on("brain_output", _forward_brain_output)

    # ── REST endpoints ────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/settings")
    async def get_settings():
        if config_manager is None:
            return {}
        return config_manager.get_config()

    @app.post("/settings")
    async def post_settings(body: dict):
        if config_manager is not None:
            new_config = config_manager.update_config(body)
            event_bus.emit("config_changed", new_config)
        return {"ok": True}

    @app.get("/memory")
    async def get_memory():
        if memory_store is None:
            return []
        return memory_store.get_all_facts()

    @app.delete("/memory/{fact_id}")
    async def delete_memory(fact_id: str):
        if memory_store is not None:
            memory_store.delete_fact(fact_id)
        return {"ok": True}

    @app.put("/memory/{fact_id}")
    async def put_memory(fact_id: str, body: dict):
        updated = False
        if memory_store is not None and hasattr(memory_store, "update_fact"):
            updated = bool(memory_store.update_fact(fact_id, body))
        return {"ok": updated}

    @app.get("/tasks")
    async def get_tasks():
        if task_runner is None:
            return []
        return task_runner.get_tasks()

    @app.post("/tasks")
    async def post_task(body: dict):
        title = body.get("title", "")
        description = body.get("description", "")
        task_id = task_runner.add_task(title, description) if task_runner else ""
        return {"id": task_id}

    @app.delete("/tasks/{task_id}")
    async def delete_task(task_id: str):
        if task_runner is not None:
            task_runner.cancel_task(task_id)
        return {"ok": True}

    # ── Conversations ─────────────────────────────────────────────────────

    @app.get("/conversations")
    async def get_conversations():
        if conversation_store is None:
            return []
        return conversation_store.list_all()

    @app.post("/conversations")
    async def post_conversation():
        if conversation_store is None:
            return {"id": None}
        conv = conversation_store.create()
        return {"id": conv.id, "title": conv.title}

    @app.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str):
        if conversation_store is None:
            return None
        conv = conversation_store.get(conv_id)
        return conv.to_dict() if conv else None

    @app.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str):
        if conversation_store is not None:
            conversation_store.delete(conv_id)
        return {"ok": True}

    # ── WebSocket /ws/chat ────────────────────────────────────────────────

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        if not _origin_allowed(websocket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        chat_conns.add(websocket)

        active_conv: list[str] = []

        def _save_response(text: str) -> None:
            if active_conv and conversation_store is not None:
                conversation_store.add_message(active_conv[0], "assistant", text)

        event_bus.on("response_done", _save_response)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if msg.get("type") == "query":
                    text = (msg.get("text") or "")[:MAX_QUERY_LENGTH]
                    conv_id: Optional[str] = msg.get("conversation_id")

                    if conversation_store is not None:
                        if not conv_id:
                            conv = conversation_store.create()
                            conv_id = conv.id
                            await websocket.send_text(json.dumps({
                                "type": "conversation_created",
                                "id": conv.id,
                                "title": conv.title,
                            }))
                        conversation_store.add_message(conv_id, "user", text)
                        active_conv.clear()
                        active_conv.append(conv_id)

                    if ai_thread is not None:
                        event_bus.emit("chat_query_received", text)
                        ai_thread.send_query(text)

                elif msg.get("type") == "cancel" and ai_thread is not None:
                    ai_thread.cancel_current()
                elif msg.get("type") == "voice_start":
                    event_bus.emit("hotkey_pressed")
        except WebSocketDisconnect:
            pass
        finally:
            event_bus.off("response_done", _save_response)
            chat_conns.remove(websocket)

    # ── WebSocket /ws/state ───────────────────────────────────────────────

    @app.websocket("/ws/state")
    async def ws_state(websocket: WebSocket):
        if not _origin_allowed(websocket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        state_conns.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state_conns.remove(websocket)

    return app
