"""main.py — KIBO entry point.

Delegates entirely to the headless backend in src/api/main.
The Electron frontend connects to the FastAPI server via WebSocket.
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    from src.core.config_manager import FileConfigManager
    from src.api.main import start

    config_manager = FileConfigManager()
    sys.exit(start(config_manager.get_config()) or 0)
