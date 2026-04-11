"""
tests/test_ai_client.py — Unit tests for AIClient.

Mocks httpx so no Ollama instance is needed.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


CONFIG = {
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:7b",
    "system_prompt": "You are KIBO.",
    "conversation_history_limit": 5,
}


@pytest.fixture
def client(qt_app):
    from ai_client import AIClient
    return AIClient(CONFIG)


class TestOllamaReachability:
    def test_check_ollama_returns_true_on_200(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: mock_ctx
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp
            mock_client_cls.return_value = mock_ctx
            assert client.check_ollama() is True

    def test_check_ollama_returns_false_on_connection_error(self, client):
        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: mock_ctx
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = Exception("Connection refused")
            mock_client_cls.return_value = mock_ctx
            assert client.check_ollama() is False


class TestConversationHistory:
    def test_history_trimmed_to_limit(self, client):
        # Add more messages than the limit
        for i in range(12):
            client._history.append({"role": "user", "content": f"msg {i}"})
            client._history.append({"role": "assistant", "content": f"resp {i}"})
        client._trim_history()
        # limit * 2 = 10 messages max
        assert len(client._history) <= CONFIG["conversation_history_limit"] * 2

    def test_clear_history(self, client):
        client._history = [{"role": "user", "content": "hello"}]
        client.clear_history()
        assert client._history == []


class TestSendQuery:
    def test_error_emitted_when_ollama_unreachable(self, client):
        errors = []
        client.error_occurred.connect(lambda e: errors.append(e))

        with patch.object(client, "check_ollama", return_value=False):
            client.send_query("Hello KIBO")

        assert len(errors) == 1
        assert "brain" in errors[0].lower() or "ollama" in errors[0].lower()

    def test_response_done_emitted_on_success(self, client):
        responses = []
        client.response_done.connect(lambda r: responses.append(r))

        stream_lines = [
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " world"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines = MagicMock(return_value=iter(stream_lines))
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)

        mock_http = MagicMock()
        mock_http.__enter__ = lambda s: mock_http
        mock_http.__exit__ = MagicMock(return_value=False)
        mock_http.stream.return_value = mock_resp

        with patch.object(client, "check_ollama", return_value=True), \
             patch("httpx.Client", return_value=mock_http):
            client.send_query("Hello")

        assert len(responses) == 1
        assert responses[0] == "Hello world"
