import time
import pytest
from unittest.mock import patch
from src.api.event_bus import EventBus
from src.system.system_monitor import SystemMonitor

CONFIG = {"poll_interval_ms": 30}


def test_emits_sensor_update_on_poll():
    bus = EventBus()
    received = []
    bus.on("sensor_update", received.append)

    with patch("psutil.cpu_percent", return_value=10.0), \
         patch("psutil.sensors_battery", return_value=None):
        mon = SystemMonitor(CONFIG, event_bus=bus)
        mon.start()
        time.sleep(0.12)
        mon.stop()

    assert len(received) >= 2


def test_stop_halts_polling():
    bus = EventBus()
    count = []
    bus.on("sensor_update", lambda d: count.append(1))

    with patch("psutil.cpu_percent", return_value=0.0), \
         patch("psutil.sensors_battery", return_value=None):
        mon = SystemMonitor(CONFIG, event_bus=bus)
        mon.start()
        time.sleep(0.08)
        mon.stop()
        snapshot = len(count)
        time.sleep(0.08)

    assert len(count) == snapshot


def test_sensor_data_fields():
    bus = EventBus()
    received = []
    bus.on("sensor_update", received.append)

    with patch("psutil.cpu_percent", return_value=42.0), \
         patch("psutil.sensors_battery", return_value=None):
        mon = SystemMonitor(CONFIG, event_bus=bus)
        mon.start()
        time.sleep(0.08)
        mon.stop()

    assert received
    data = received[0]
    assert data.cpu_percent == 42.0
    assert data.battery_percent is None
