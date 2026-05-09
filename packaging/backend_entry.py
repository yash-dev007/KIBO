from __future__ import annotations

import argparse
import logging

from src.api.main import start
from src.core.config_manager import FileConfigManager


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="KIBO bundled backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    config_manager = FileConfigManager()
    start(config_manager.get_config(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
