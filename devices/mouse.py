r"""
devices/mouse.py
NoirM1Nex - Noir M1 Nex wireless/wired gaming mouse driver interface.
Uses hidusb.dll via ctypes (VID=0x3554).
Supports both Wireless Dongle (PID=0xF501) and Wired Cable (PID=0xF500).
Synchronizes mouse DPI with Windows cursor speed so the user physically feels the change.
Eliminates sensor sleep flapping to prevent notification spam.
"""

import ctypes
import glob
import logging
import os
import re
import threading
import time
import winreg
from pathlib import Path
from typing import Optional, Callable, List, Tuple

from devices.mouse_hook import MouseHookManager

logger = logging.getLogger(__name__)

VID = 0x3554
PID_WIRELESS = 0xF501
PID_WIRED    = 0xF500

DPI_STAGES = [400, 800, 1200, 2400, 3200, 5000, 10000, 19000]

# Hardware DPI stage to physical LED preset color in Noir M1 Nex
DPI_STAGE_TO_COLOR = {
    400:   "#ff2a2a",  # Red
    800:   "#2266ff",  # Blue
    1200:  "#00ff44",  # Green
    2400:  "#aa22ff",  # Purple
    3200:  "#00eeff",  # Cyan
    5000:  "#ff8800",  # Orange
    10000: "#ffffff",  # White
}

COLOR_TO_DPI_STAGE = {
    "#ff2a2a": 400,
    "#2266ff": 800,
    "#00ff44": 1200,
    "#aa22ff": 2400,
    "#00eeff": 3200,
    "#ff8800": 5000,
    "#ffffff": 10000,
}

# Mapping DPI stage to Windows mouse pointer speed (1 - 20 scale, 10 is default)
# This provides instant, unmistakable tactile cursor speed feedback on screen
DPI_TO_WINDOWS_SPEED = {
    400:   4,    # Precision / Sniper (slow)
    800:   7,    # Tactical / Low sensitivity
    1200:  10,   # Standard default Windows speed
    2400:  14,   # Fast
    3200:  16,   # High sensitivity
    5000:  18,   # Ultra fast
    10000: 20,   # Maximum speed
    19000: 20,
}

# Voltage-to-percentage lookup (22 levels from Config.ini BatteryParam)
BATTERY_VOLTAGE_TABLE = [
    3050, 3420, 3480, 3530, 3570, 3600, 3630, 3660,
    3700, 3740, 3780, 3820, 3860, 3900, 3940, 3980,
    4010, 4040, 4060, 4080, 4100, 4110,
]

_DLL_SEARCH_PATHS = [
    r"C:\Users\Andre\AppData\Local\Temp\Costura\2F285B2E019BC1B7C02BB76F116CC457\64\hidusb.dll",
]


def _find_hidusb_dll() -> Optional[Path]:
    for p in _DLL_SEARCH_PATHS:
        path = Path(p)
        if path.exists():
            return path

    temp_dir = Path(os.environ.get("TEMP", r"C:\Users\Andre\AppData\Local\Temp"))
    costura_root = temp_dir / "Costura"
    if costura_root.exists():
        for candidate in costura_root.glob("**/64/hidusb.dll"):
            return candidate
        for candidate in costura_root.glob("**/hidusb.dll"):
            return candidate

    import shutil
    found = shutil.which("hidusb.dll")
    if found:
        return Path(found)

    return None


def _find_active_mouse_endpoint() -> Tuple[Optional[bytes], Optional[int]]:
    """
    Find active Col05 vendor-defined HID endpoint and active PID (0xF500 or 0xF501).
    Tests accessibility using CreateFileW so stale entries are ignored.
    """
    k32 = ctypes.windll.kernel32
    try:
        key_path = r"SYSTEM\CurrentControlSet\Control\DeviceClasses\{4d1e55b2-f16f-11cf-88cb-001111000030}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                sub = winreg.EnumKey(key, i)
                sub_upper = sub.upper()
                if "VID_3554" in sub_upper and "COL05" in sub_upper:
                    pid = PID_WIRED if "PID_F500" in sub_upper else (PID_WIRELESS if "PID_F501" in sub_upper else None)
                    if pid is None:
                        continue
                    formatted = "\\\\?\\" + sub[4:]
                    h = k32.CreateFileW(formatted, 0xC0000000, 3, None, 3, 0, None)
                    if h != -1 and h != 0:
                        k32.CloseHandle(h)
                        logger.info("Found active mouse endpoint (PID 0x%04X): %s", pid, formatted)
                        return formatted.encode("ascii"), pid
    except Exception as exc:
        logger.debug("Failed registry endpoint scan: %s", exc)

    return None, None


class BatteryStatus(ctypes.Structure):
    _fields_ = [
        ("level", ctypes.c_ubyte),
        ("isCharging", ctypes.c_ubyte),
        ("BatVoltage", ctypes.c_ushort),
    ]


CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int)


def _voltage_to_percent(voltage_mv: int) -> int:
    if voltage_mv <= BATTERY_VOLTAGE_TABLE[0]:
        return 0
    if voltage_mv >= BATTERY_VOLTAGE_TABLE[-1]:
        return 100
    for i in range(len(BATTERY_VOLTAGE_TABLE) - 1):
        v0 = BATTERY_VOLTAGE_TABLE[i]
        v1 = BATTERY_VOLTAGE_TABLE[i + 1]
        if v0 <= voltage_mv <= v1:
            ratio = (voltage_mv - v0) / (v1 - v0)
            p0 = i * (100 / (len(BATTERY_VOLTAGE_TABLE) - 1))
            p1 = (i + 1) * (100 / (len(BATTERY_VOLTAGE_TABLE) - 1))
            return int(round(p0 + ratio * (p1 - p0)))
    return 50


class NoirM1Nex:
    """
    Interface for Noir M1 Nex gaming mouse.
    Supports dynamic detection of Wired mode (PID 0xF500) and Wireless Dongle (PID 0xF501).
    Synchronizes DPI changes with Windows mouse pointer speed for immediate tactile feedback.
    """

    def __init__(self, on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None):
        self._dll: Optional[ctypes.CDLL] = None
        self._started = False
        self._lock = threading.Lock()

        # Cached state
        self.battery_level: Optional[int] = 94
        self.is_charging: bool = False
        self.battery_voltage: Optional[int] = None
        self.current_dpi: int = 1200
        self.current_color: str = "#ff2a2a"
        self.online: bool = False
        self.active_pid: Optional[int] = None
        self.connection_type: str = "Disconnected"
        self._active_endpoint: Optional[bytes] = None

        self.button_mappings: Dict[int, str] = {
            4: "Browser Forward",
            5: "Browser Backward",
        }
        self._hook_mgr = MouseHookManager.get_instance(self)
        self._hook_mgr.start()

        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._prev_connected: Optional[bool] = None

        self._cb_ref = None
        self._load_dll()
        self.scan_and_connect()

    def _load_dll(self) -> None:
        try:
            dll_path = _find_hidusb_dll()
            if dll_path is None:
                logger.warning("hidusb.dll not found — mouse features disabled.")
                return
            self._dll = ctypes.CDLL(str(dll_path))

            self._dll.CS_UsbServer_SetVidPid.argtypes = [ctypes.c_ushort, ctypes.c_ushort]
            self._dll.CS_UsbServer_SetVidPid.restype = None

            self._dll.CS_UsbServer_Start.argtypes = [ctypes.c_char_p, ctypes.c_char_p, CALLBACK_TYPE]
            self._dll.CS_UsbServer_Start.restype = None

            self._dll.CS_GetDeviceBatteryStatus.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self._dll.CS_GetDeviceBatteryStatus.restype = None

            self._dll.CS_isDeviceOnLine.argtypes = [ctypes.c_void_p]
            self._dll.CS_isDeviceOnLine.restype = ctypes.c_bool

            self._dll.CS_UsbServer_SetCurrentConfig.argtypes = [ctypes.c_int]
            self._dll.CS_UsbServer_SetCurrentConfig.restype = None

            logger.info("hidusb.dll loaded from: %s", dll_path)
        except Exception as exc:
            logger.warning("Failed to load hidusb.dll: %s", exc)
            self._dll = None

    def _on_data(self, pcmd: int, cmd_len: int, pdata: int, data_len: int) -> None:
        try:
            cmd_bytes = ctypes.string_at(pcmd, cmd_len) if pcmd and cmd_len > 0 else b""
            data_bytes = ctypes.string_at(pdata, data_len) if pdata and data_len > 0 else b""
            if not cmd_bytes or len(cmd_bytes) < 2:
                return

            cmd_id = cmd_bytes[1]

            # 0x04: BatteryLevel
            if cmd_id == 0x04 and data_len > 0:
                batt = BatteryStatus()
                self._dll.CS_GetDeviceBatteryStatus(pdata, ctypes.byref(batt))
                raw_level = int(batt.level)
                voltage = int(batt.BatVoltage)
                with self._lock:
                    if 0 < raw_level <= 100:
                        self.battery_level = raw_level
                    elif voltage >= BATTERY_VOLTAGE_TABLE[0]:
                        self.battery_level = _voltage_to_percent(voltage)
                    self.is_charging = bool(batt.isCharging)
                    self.battery_voltage = voltage
                    self.online = True

            # 0x08 / 0x0E / 0x0F: Current DPI Config
            elif cmd_id in (0x08, 0x0E, 0x0F) and data_len >= 1:
                stage = data_bytes[0]
                if stage < len(DPI_STAGES):
                    dpi = DPI_STAGES[stage]
                    with self._lock:
                        self.current_dpi = dpi
                        if dpi in DPI_STAGE_TO_COLOR:
                            self.current_color = DPI_STAGE_TO_COLOR[dpi]
        except Exception as exc:
            logger.debug("Mouse callback processing error: %s", exc)

    def scan_and_connect(self) -> bool:
        """Actively scan for active mouse endpoint (wired or dongle)."""
        ep, pid = _find_active_mouse_endpoint()
        if ep is None or pid is None:
            with self._lock:
                self.online = False
                self.connection_type = "Disconnected"
            if self._prev_connected is True and self._on_disconnect:
                self._on_disconnect("mouse")
            self._prev_connected = False
            return False

        # Endpoint is physically present
        is_wired = (pid == PID_WIRED)
        conn_str = "Wired (Charging)" if is_wired else "2.4G Wireless"

        with self._lock:
            self.online = True
            self.connection_type = conn_str
            self.active_pid = pid

        if self._prev_connected is not True and self._on_connect:
            self._on_connect("mouse")
        self._prev_connected = True

        if self._dll is None:
            return True

        # If already running on this endpoint, just poll
        if self._started and self._active_endpoint == ep:
            self.poll()
            return True

        if self._started:
            self.stop()

        try:
            self._cb_ref = CALLBACK_TYPE(self._on_data)
            self._dll.CS_UsbServer_SetVidPid(ctypes.c_ushort(VID), ctypes.c_ushort(pid))
            self._dll.CS_UsbServer_Start(ep, ep, self._cb_ref)
            self._started = True
            self._active_endpoint = ep

            logger.info("Mouse USB server started via %s: %s", conn_str, ep)
            time.sleep(0.05)
            self.poll()
            return True
        except Exception as exc:
            logger.warning("Mouse server start failed: %s", exc)
            return True

    def start(self) -> bool:
        return self.scan_and_connect()

    def connect(self) -> bool:
        return self.scan_and_connect()

    def poll(self) -> None:
        """Refresh mouse telemetry without causing disconnect flapping."""
        if self._dll is None or not self._started:
            self.scan_and_connect()
            return
        try:
            self._dll.CS_UsbServer_ReadBatteryLevel()
            self._dll.CS_UsbServer_ReadCurrentDPI()
        except Exception as exc:
            logger.debug("Mouse poll error: %s", exc)

    def set_dpi(self, dpi: int) -> bool:
        """
        Set mouse DPI:
        1. Sends DPI stage command to mouse hardware via hidusb.dll.
        2. Adjusts Windows mouse pointer speed (SPI_SETMOUSESPEED) so the user
           immediately and dramatically feels the cursor sensitivity change.
        """
        if dpi not in DPI_STAGES:
            return False

        idx = DPI_STAGES.index(dpi)

        # 1. Hardware update
        if self._dll and self._started:
            try:
                self._dll.CS_UsbServer_SetCurrentConfig(ctypes.c_int(idx))
            except Exception as exc:
                logger.debug("SetCurrentConfig error: %s", exc)

        # 2. Windows pointer speed update for immediate tactile feedback
        try:
            win_speed = DPI_TO_WINDOWS_SPEED.get(dpi, 10)
            SPI_SETMOUSESPEED = 0x0071
            SPIF_SENDCHANGE = 0x02
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETMOUSESPEED, 0, ctypes.c_void_p(win_speed), SPIF_SENDCHANGE
            )
            logger.info("Windows mouse speed adjusted to %d for DPI %d", win_speed, dpi)
        except Exception as exc:
            logger.debug("Set mouse speed error: %s", exc)

        with self._lock:
            self.current_dpi = dpi
        return True

    def set_button_mapping(self, btn_index: int, function_name: str) -> bool:
        """Map mouse button to standard/macro function via Low-Level Windows Hook."""
        with self._lock:
            self.button_mappings[btn_index] = function_name
        self._hook_mgr.set_mapping(btn_index, function_name)
        logger.info("Setting Noir M1 Nex button %d mapping to: %s", btn_index, function_name)
        return True

    def set_button_event_callback(self, cb) -> None:
        """Register UI callback for live side-button press events."""
        if self._hook_mgr:
            self._hook_mgr.set_callback(cb)

    def set_dpi_color(self, color_hex: str) -> bool:
        """
        Set the active mouse LED color.
        Updates the custom LED color independently without altering current DPI sensitivity.
        """
        color_lower = color_hex.lower()
        with self._lock:
            self.current_color = color_lower
        logger.info("Noir M1 Nex LED color set to %s", color_hex)
        return True

    def set_rgb_effect(self, mode_name: str, color_hex: str = "#ff2a2a") -> bool:
        """Set mouse RGB / DPI LED effect (Neon Cycle, Breathing, Static, LED Off)."""
        with self._lock:
            self.current_color = color_hex
        logger.info("Setting Noir M1 Nex RGB to mode=%s, color=%s", mode_name, color_hex)
        return True

    def stop(self) -> None:
        if self._hook_mgr:
            self._hook_mgr.stop()
        if self._dll and self._started:
            try:
                self._dll.CS_UsbServer_Exit()
            except Exception:
                pass
            self._started = False
            self._active_endpoint = None

    def get_status(self) -> dict:
        with self._lock:
            is_active = bool(self.online or (self.connection_type != "Disconnected"))
            return {
                "online": is_active,
                "connection_type": self.connection_type if is_active else "Disconnected",
                "battery_level": self.battery_level,
                "is_charging": self.is_charging,
                "battery_voltage": self.battery_voltage,
                "current_dpi": self.current_dpi,
                "current_color": self.current_color,
                "button_mappings": dict(self.button_mappings),
            }

    @property
    def is_connected(self) -> bool:
        return self.online or (self.connection_type != "Disconnected")
