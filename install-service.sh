#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/zephyrus-ui.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "Error: zephyrus-ui.service not found in $SCRIPT_DIR"
  exit 1
fi

echo "Installing Zephyrus UI service..."
echo "Make sure you've edited zephyrus-ui.service with your username and paths first!"
echo ""

sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zephyrus-ui
sudo systemctl start zephyrus-ui
sudo systemctl status zephyrus-ui
