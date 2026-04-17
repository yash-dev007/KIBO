"""
system_monitor.py — Polls system state and emits SensorData every poll_interval_ms.

Runs on the main thread via QTimer (polls are fast and non-blocking).
All pygetwindow calls are wrapped in try/except — it can raise on minimized
windows or when no window has focus.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import psutil
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from src.ai.brain import SensorData

logger = logging.getLogger(__name__)


class SystemMonitor(QObject):
    sensor_update = Signal(SensorData)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        # Prime psutil so first real call doesn't return 0.0
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        interval = self._config["poll_interval_ms"]
        self._timer.start(interval)
        logger.info("SystemMonitor started (interval=%dms).", interval)

    def stop(self) -> None:
        self._timer.stop()

    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        interval = self._config["poll_interval_ms"]
        if self._timer.isActive() and self._timer.interval() != interval:
            self._timer.setInterval(interval)
            logger.info("SystemMonitor interval updated to %dms.", interval)

    def _poll(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        active_window = self._get_active_window()
        current_hour = datetime.now().hour
        battery = self._get_battery()

        data = SensorData(
            cpu_percent=cpu,
            active_window=active_window,
            current_hour=current_hour,
            battery_percent=battery,
        )
        self.sensor_update.emit(data)

    def _get_active_window(self) -> str:
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win is None:
                return ""
            return win.title or ""
        except Exception as exc:
            logger.debug("pygetwindow error (non-fatal): %s", exc)
            return ""

    def _get_battery(self) -> Optional[float]:
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                return None
            return batt.percent
        except Exception:
            return None
