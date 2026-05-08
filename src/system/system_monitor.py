"""
system_monitor.py — Polls system state and emits SensorData via EventBus.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import psutil

from src.ai.brain import SensorData
from src.core.periodic_thread import PeriodicThread

logger = logging.getLogger(__name__)


class SystemMonitor:
    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._thread: Optional[PeriodicThread] = None
        self._current_interval = config["poll_interval_ms"]
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        self._thread = PeriodicThread(self._current_interval, self._poll)
        self._thread.start()
        logger.info("SystemMonitor started (interval=%dms).", self._current_interval)

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        interval = new_config["poll_interval_ms"]
        if interval != self._current_interval and self._thread is not None:
            self._thread.stop()
            self._current_interval = interval
            self._thread = PeriodicThread(self._current_interval, self._poll)
            self._thread.start()
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
        if self._event_bus:
            self._event_bus.emit("sensor_update", data)

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
