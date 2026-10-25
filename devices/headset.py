"""
devices/headset.py
KumoGS1XPro - dbE Kumo GS1X Pro wireless headset interface.
Smart estimator based on usage time since last known charge (JieLi USB limitation).
Windows Core Audio API used for real volume control via pycaw.
VID=0x4C4A, PID=0x4155.
"""

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

VID = 0x4C4A
PID = 0x4155

SPEAKER_NAME_PARTIAL = "dbE Kumo GS1X Pro"

# Smart estimator constants
BATTERY_LIFE_HOURS = 16.0          # nominal battery life
SMART_SLEEP_THRESHOLD_HOURS = 2.0  # reconnect after silence = assume charged


class _BatteryEstimator:
    """
    Smart battery estimator for headsets without USB battery reporting.
    Tracks usage hours since last known charge and persists into config.json.
    """

    def __init__(self, config_path: Path):
        self._config_path = config_path
        self._lock = threading.Lock()

        self.last_charge_time: Optional[datetime] = None
        self.usage_hours: float = 0.0
        self.charge_confirmed: bool = False
        self._session_start: Optional[datetime] = None
        self._last_disconnect_time: Optional[datetime] = None

        self._load_state()

    def _load_state(self) -> None:
        try:
            if not self._config_path.exists():
                return
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            hs = cfg.get("headset", {})
            ts = hs.get("last_charge_timestamp")
            if ts:
                self.last_charge_time = datetime.fromisoformat(ts)
            self.usage_hours = float(hs.get("usage_hours_since_charge", 0.0))
            self.charge_confirmed = bool(hs.get("charge_confirmed", False))
        except Exception as exc:
            logger.debug("Estimator load state error: %s", exc)

    def save_state(self, full_config: dict) -> None:
        try:
            hs = full_config.setdefault("headset", {})
            hs["last_charge_timestamp"] = (
                self.last_charge_time.isoformat() if self.last_charge_time else None
            )
            hs["usage_hours_since_charge"] = round(self.usage_hours, 3)
            hs["charge_confirmed"] = self.charge_confirmed
            hs["battery_life_hours"] = BATTERY_LIFE_HOURS
        except Exception as exc:
            logger.debug("Estimator save state error: %s", exc)

    def mark_session_start(self) -> None:
        with self._lock:
            if self._session_start is None:
                self._session_start = datetime.now()

    def mark_session_end(self) -> None:
        with self._lock:
            if self._session_start is not None:
                elapsed = (datetime.now() - self._session_start).total_seconds() / 3600.0
                self.usage_hours += elapsed
                self._session_start = None
            self._last_disconnect_time = datetime.now()

    def mark_charged(self) -> None:
        with self._lock:
            self.last_charge_time = datetime.now()
            self.usage_hours = 0.0
            self.charge_confirmed = True
            self._session_start = None

    def check_smart_sleep(self) -> bool:
        with self._lock:
            if self._last_disconnect_time is None:
                return False
            elapsed_off = (datetime.now() - self._last_disconnect_time).total_seconds() / 3600.0
            return elapsed_off >= SMART_SLEEP_THRESHOLD_HOURS

    def get_estimated_battery(self) -> int:
        with self._lock:
            current_usage = self.usage_hours
            if self._session_start is not None:
                session_elapsed = (datetime.now() - self._session_start).total_seconds() / 3600.0
                current_usage += session_elapsed
            pct = max(0.0, 1.0 - (current_usage / BATTERY_LIFE_HOURS))
            return int(round(pct * 100))

    def get_usage_str(self) -> str:
        with self._lock:
            total = self.usage_hours
            if self._session_start is not None:
                total += (datetime.now() - self._session_start).total_seconds() / 3600.0
        h = int(total)
        m = int((total - h) * 60)
        return f"{h}h {m:02d}m"


class KumoGS1XPro:
    """
    Interface for dbE Kumo GS1X Pro wireless gaming headset.
    Uses pycaw to control Windows master volume for the headset.
    Estimates battery percentage using time-based tracking.
    """

    def __init__(self, config_path: Path,
                 on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None,
                 on_charge_prompt: Optional[Callable] = None):
        self._config_path = config_path
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_charge_prompt = on_charge_prompt
        self._lock = threading.Lock()

        # State
        self.dongle_connected: bool = False
        self.connection_type: str = "Disconnected"
        self.audio_device_active: bool = False
        self.volume: int = 80
        self._prev_dongle_connected: Optional[bool] = None

        # Smart estimator
        self._estimator = _BatteryEstimator(config_path)

        # Volume endpoint
        self._volume_endpoint = None

        # Check initial USB state & volume
        self.scan_and_connect()

    # ------------------------------------------------------------------
    # USB Dongle detection
    # ------------------------------------------------------------------

    def scan_and_connect(self) -> bool:
        """Actively scan for headset USB dongle and Windows audio device."""
        try:
            import hid
            devices = hid.enumerate(VID, PID)
            connected = len(devices) > 0

            with self._lock:
                prev = self.dongle_connected
                self.dongle_connected = connected
                self.connection_type = "2.4G Wireless Dongle" if connected else "Disconnected"

            if prev and not connected:
                self._estimator.mark_session_end()
                if self._on_disconnect:
                    self._on_disconnect("headset")
            elif not prev and connected:
                if self._estimator.check_smart_sleep():
                    if self._on_charge_prompt:
                        self._on_charge_prompt()
                self._estimator.mark_session_start()
                if self._on_connect:
                    self._on_connect("headset")

            self._prev_dongle_connected = connected

            # Re-acquire audio volume endpoint
            self._volume_endpoint = self._find_volume_endpoint()
            cur_vol = self._get_windows_volume()
            if cur_vol is not None:
                with self._lock:
                    self.volume = cur_vol
                    self.audio_device_active = True

            return connected

        except Exception as exc:
            logger.debug("Headset scan error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Windows Core Audio via pycaw
    # ------------------------------------------------------------------

    def _find_volume_endpoint(self):
        """Find the EndpointVolume object for dbE Kumo GS1X Pro speakers."""
        try:
            from pycaw.pycaw import AudioUtilities
            for dev in AudioUtilities.GetAllDevices():
                name = dev.FriendlyName or ""
                # Match dbE Kumo speaker render device (render IDs start with {0.0.0.)
                if SPEAKER_NAME_PARTIAL.lower() in name.lower() and getattr(dev, "id", "").startswith("{0.0.0."):
                    logger.info("Found dbE Kumo audio device: %s", name)
                    return dev.EndpointVolume
        except Exception as exc:
            logger.debug("Failed to get audio device via pycaw: %s", exc)
        return None

    def _get_windows_volume(self) -> Optional[int]:
        """Read system master volume for the headset."""
        try:
            ep = self._volume_endpoint or self._find_volume_endpoint()
            if ep is not None:
                self._volume_endpoint = ep
                scalar = ep.GetMasterVolumeLevelScalar()
                return int(round(scalar * 100))
        except Exception as exc:
            logger.debug("Get volume error: %s", exc)
        return None

    def set_volume(self, percent: int) -> bool:
        """Set Windows system volume for dbE Kumo GS1X Pro."""
        percent = max(0, min(100, percent))
        with self._lock:
            self.volume = percent

        try:
            ep = self._volume_endpoint or self._find_volume_endpoint()
            if ep is None:
                return False
            self._volume_endpoint = ep
            scalar = percent / 100.0
            ep.SetMasterVolumeLevelScalar(scalar, None)
            return True
        except Exception as exc:
            logger.debug("Set volume error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Refresh dongle presence and sync volume."""
        self.scan_and_connect()

    def mark_as_charged(self) -> None:
        self._estimator.mark_charged()
        logger.info("Headset marked as charged.")

    def mark_not_charged(self) -> None:
        with self._lock:
            self._estimator._last_disconnect_time = None

    def get_battery_estimate(self) -> int:
        return self._estimator.get_estimated_battery()

    def save_state(self, full_config: dict) -> None:
        self._estimator.save_state(full_config)

    def get_status(self) -> dict:
        vol = self._get_windows_volume()
        if vol is not None:
            self.volume = vol
            self.audio_device_active = True

        return {
            "dongle_connected": self.dongle_connected,
            "connection_type": self.connection_type,
            "audio_device_active": self.audio_device_active,
            "battery_estimate": self.get_battery_estimate(),
            "usage_time": self._estimator.get_usage_str(),
            "volume": self.volume,
        }

    def stop(self) -> None:
        if self.dongle_connected:
            self._estimator.mark_session_end()
