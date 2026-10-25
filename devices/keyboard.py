"""
devices/keyboard.py
AulaS75Pro - High-performance hardware controller for AULA S75 Pro keyboard.
Supports live hardware control over:
- 2.4G Wireless Dongle (VID=0x05AC, PID=0x024F) via endpoints MI_04 (65-byte) and MI_03 (33-byte)
- USB Cable mode (VID=0x0C45, PID=0x800A) via Sonix endpoint MI_03 / UsagePage 0xFF13

Dual-transport architecture:
Simultaneously syncs to both USB and 2.4G Dongle if both are plugged into the system,
ensuring hardware RGB changes physically regardless of the keyboard's physical mode toggle switch.
Also syncs with local SQLite state in S75Pro_datav1.db.
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Callable, List, Tuple

logger = logging.getLogger(__name__)

USB_VID = 0x0C45
USB_PID = 0x800A

WIRELESS_VID = 0x05AC
WIRELESS_PID = 0x024F

DB_PATH = Path(r"C:\Users\Andre\AppData\Local\S75Pro Driver Files\db\S75Pro_datav1.db")

# 20 Lighting modes mapped directly from official driver (1033.lan / t_light_data)
LIGHT_MODES = [
    (1,  "Static"),
    (2,  "SingleOn"),
    (3,  "SingleOff"),
    (4,  "Glittering"),
    (5,  "Fluttering"),
    (6,  "Colourful"),
    (7,  "Breath"),
    (8,  "Spectrum"),
    (9,  "Outward"),
    (10, "Scrolling"),
    (11, "Rolling"),
    (12, "Rotating"),
    (13, "Explode"),
    (14, "Launch"),
    (15, "Ripples"),
    (16, "Flowing"),
    (17, "Pulsating"),
    (18, "Tilt"),
    (19, "Shuttle"),
    (0,  "LED Off"),
]

LIGHT_MODE_NAMES = [name for _, name in LIGHT_MODES]
NAME_TO_MODE_VAL = {name: val for val, name in LIGHT_MODES}
MODE_VAL_TO_NAME = {val: name for val, name in LIGHT_MODES}

# Pre-defined custom color presets: (Name, Hex, (R, G, B))
COLOR_PRESETS: List[Tuple[str, str, Tuple[int, int, int]]] = [
    ("Red",     "#ff2a2a", (255, 0, 0)),
    ("Orange",  "#ff8800", (255, 136, 0)),
    ("Yellow",  "#ffee00", (255, 238, 0)),
    ("Green",   "#00ff44", (0, 255, 68)),
    ("Cyan",    "#00eeff", (0, 238, 255)),
    ("Blue",    "#2266ff", (34, 102, 255)),
    ("Purple",  "#aa22ff", (170, 34, 255)),
    ("White",   "#ffffff", (255, 255, 255)),
    ("Rainbow", "#e26332", (0, 0, 0)),  # Dynamic multi-color mode
]


class AulaS75Pro:
    """
    Hardware interface for the AULA S75 Pro keyboard.
    Auto-detects USB Cable (0x0C45:0x800A) and 2.4G Wireless Dongle (0x05AC:0x024F).
    Sends dual-transport commands to guarantee RGB updates regardless of switch position.
    """

    def __init__(self, on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None):
        self._lock = threading.Lock()
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._prev_connected: Optional[bool] = None

        # Discovered hardware endpoints
        self._usb_path: Optional[bytes] = None
        self._wireless_paths: List[bytes] = []

        # Cached hardware telemetry & settings
        self.connected: bool = False
        self.connection_type: str = "Disconnected"
        self.battery_level: Optional[int] = None
        self.light_mode: int = 6                    # Default to Colourful
        self.light_mode_name: str = "Colourful"
        self.current_rgb: Tuple[int, int, int] = (255, 255, 255)
        self.is_rainbow: bool = True
        self.brightness: int = 5                    # 1 - 5 scale
        self.speed: int = 3                         # 1 - 5 scale
        self.game_mode: bool = False
        self.sleep_time: int = 300                  # seconds

        self._sync_from_db()
        self.scan_and_connect()

    def scan_and_connect(self) -> bool:
        """Scan system for USB Cable and 2.4G Wireless Dongle endpoints."""
        try:
            import hid

            usb_path = None
            wireless_paths = []

            # 1. Scan for USB Cable endpoint (VID 0x0C45 PID 0x800A)
            try:
                usb_devs = hid.enumerate(USB_VID, USB_PID)
                for d in usb_devs:
                    p = d.get("path") or b""
                    # Interface 3 with UsagePage 0xFF13 is the Sonix feature report interface
                    if d.get("usage_page") == 0xFF13 or b"MI_03" in p:
                        usb_path = p
                        break
            except Exception as e:
                logger.debug("USB scan error: %s", e)

            # 2. Scan for 2.4G Dongle endpoints (VID 0x05AC PID 0x024F)
            try:
                wl_devs = hid.enumerate(WIRELESS_VID, WIRELESS_PID)
                for d in wl_devs:
                    p = d.get("path") or b""
                    # MI_04 (65-byte) and MI_03 (33-byte) are the vendor OUT endpoints
                    if b"MI_04" in p or b"MI_03" in p:
                        wireless_paths.append(p)
            except Exception as e:
                logger.debug("Wireless scan error: %s", e)

            with self._lock:
                self._usb_path = usb_path
                self._wireless_paths = wireless_paths

                has_usb = bool(usb_path)
                has_wl = bool(wireless_paths)
                is_connected = has_usb or has_wl

                if has_usb and has_wl:
                    self.connection_type = "2.4G Dongle + USB"
                elif has_wl:
                    self.connection_type = "2.4G Wireless"
                elif has_usb:
                    self.connection_type = "USB Cable"
                else:
                    self.connection_type = "Disconnected"

                self.connected = is_connected

            if is_connected:
                if self._prev_connected is not True and self._on_connect:
                    self._on_connect("keyboard")
                self._prev_connected = True
                return True
            else:
                if self._prev_connected is True and self._on_disconnect:
                    self._on_disconnect("keyboard")
                self._prev_connected = False
                return False

        except Exception as exc:
            logger.debug("Keyboard scan error: %s", exc)
            with self._lock:
                self.connected = False
                self.connection_type = "Disconnected"
                self._usb_path = None
                self._wireless_paths = []
            if self._prev_connected is True and self._on_disconnect:
                self._on_disconnect("keyboard")
            self._prev_connected = False
            return False

    def set_light_mode(self, mode_val: int) -> bool:
        """
        Send hardware lighting packets to keyboard:
        - Updates USB via Sonix feature reports if connected
        - Updates 2.4G Dongle via MI_04/MI_03 packets if connected
        - Persists settings to SQLite database
        """
        if not self.connected:
            self.scan_and_connect()
            if not self.connected:
                return False

        r, g, b = self.current_rgb
        mode_name = MODE_VAL_TO_NAME.get(mode_val, "Custom")
        logger.info("Setting AULA S75 Pro mode: %d (%s), RGB: (%d,%d,%d), rainbow=%s",
                    mode_val, mode_name, r, g, b, self.is_rainbow)

        with self._lock:
            usb_path = self._usb_path
            wl_paths = list(self._wireless_paths)
            brightness = self.brightness
            speed = self.speed
            is_rainbow = self.is_rainbow

        success = False

        # --- 1. Send via USB Cable (0x0C45:0x800A) if available ---
        if usb_path:
            try:
                import hid
                d = hid.device()
                d.open_path(usb_path)

                def send_feat(pl: List[int], read_ack: bool = False) -> bool:
                    buf = bytearray(65)
                    buf[0] = 0x00
                    for i, val in enumerate(pl[:64]):
                        buf[1 + i] = val & 0xFF
                    r = d.send_feature_report(bytes(buf))
                    if read_ack:
                        time.sleep(0.020)
                        try:
                            ack = d.get_feature_report(0x00, 65)
                            return len(ack) > 4 and ack[4] == 1
                        except Exception as ack_err:
                            logger.debug("Feature ACK read error: %s", ack_err)
                    return r > 0

                # Step 1: Command mode enter (Sonix Enter Config)
                send_feat([0x04, 0x18], read_ack=True)
                time.sleep(0.020)

                # Step 2: Param init
                p2 = [0x04, 0x13, 0, 0, 0, 0, 0, 0, 1]
                send_feat(p2, read_ack=True)
                time.sleep(0.020)

                # Step 3: Lighting mode packet (exact reverse engineered struct)
                p = bytearray(64)
                p[0] = mode_val & 0xFF
                p[1] = r & 0xFF
                p[2] = g & 0xFF
                p[3] = b & 0xFF
                p[8] = 1 if is_rainbow else 0
                p[9] = brightness & 0xFF
                p[10] = speed & 0xFF
                p[11] = 0  # direction
                p[14] = 0xAA
                p[15] = 0x55
                send_feat(list(p), read_ack=False)
                time.sleep(0.020)

                # Step 4: Save (Sonix EEPROM/RAM sync)
                send_feat([0x04, 0x02], read_ack=True)
                time.sleep(0.020)

                # Step 5: Apply & Exit
                send_feat([0x04, 0xF0], read_ack=False)
                time.sleep(0.020)
                d.close()
                success = True
                logger.info("Successfully sent USB lighting packet to AULA S75 Pro (mode=%d, RGB=(%d,%d,%d), rainbow=%s)",
                            mode_val, r, g, b, is_rainbow)
            except Exception as e:
                logger.error("USB lighting packet error: %s", e)

        # --- 2. Send via 2.4G Wireless Dongle (0x05AC:0x024F) if available ---
        if wl_paths:
            import hid
            for p_bytes in wl_paths:
                try:
                    d = hid.device()
                    d.open_path(p_bytes)
                    sz = 33 if b"MI_03" in p_bytes else 65

                    # Step 1: 2.4G RF Sync Packet
                    sc = bytearray(sz)
                    sc[0] = 0x00
                    sc[1] = 0x0F
                    if sz > 32:
                        sc[32] = 0x0F
                    d.write(bytes(sc))
                    time.sleep(0.025)

                    # Step 2: 2.4G Lighting Command Packet (exact struct from 0x42b170)
                    lp = bytearray(sz)
                    lp[0] = 0x00
                    lp[1] = 0x05
                    lp[2] = 0x10
                    lp[3] = 0x00
                    lp[4] = mode_val & 0xFF
                    lp[5] = r & 0xFF
                    lp[6] = g & 0xFF
                    lp[7] = b & 0xFF
                    lp[12] = 1 if is_rainbow else 0
                    lp[13] = brightness & 0xFF
                    lp[14] = speed & 0xFF
                    lp[15] = 0  # direction
                    lp[18] = 0xAA
                    lp[19] = 0x55
                    if sz >= 33:
                        lp[32] = sum(lp[:32]) & 0xFF

                    d.write(bytes(lp))
                    time.sleep(0.025)
                    d.close()
                    success = True
                    logger.info("Successfully sent 2.4G wireless lighting packet (sz=%d) to AULA S75 Pro", sz)
                except Exception as e:
                    logger.error("Wireless lighting packet error: %s", e)

        with self._lock:
            self.light_mode = mode_val
            self.light_mode_name = mode_name

        self._write_db_light_mode(mode_val, r, g, b)
        return success

    def set_light_mode_by_name(self, mode_name: str) -> bool:
        val = NAME_TO_MODE_VAL.get(mode_name, 6)
        if mode_name == "Colourful" or mode_name == "Spectrum":
            self.is_rainbow = True
        return self.set_light_mode(val)

    def set_color(self, r: int, g: int, b: int, is_rainbow: bool = False) -> bool:
        """Apply custom RGB color or Rainbow mode to the keyboard."""
        self.current_rgb = (r, g, b)
        self.is_rainbow = is_rainbow
        if is_rainbow:
            target_mode = 6 # Colourful
        else:
            # If current mode is 0 (off) or dynamic rainbow (6), switch to Static (1)
            target_mode = self.light_mode if self.light_mode not in (0, 6) else 1
        return self.set_light_mode(target_mode)

    def set_brightness(self, level: int) -> bool:
        """Set lighting brightness (1 to 5)."""
        self.brightness = max(1, min(5, level))
        return self.set_light_mode(self.light_mode)

    def set_speed(self, level: int) -> bool:
        """Set lighting effect speed (1 to 5)."""
        self.speed = max(1, min(5, level))
        return self.set_light_mode(self.light_mode)

    def _sync_from_db(self) -> None:
        """Read active profile and light mode settings from S75Pro SQLite database."""
        if not DB_PATH.exists():
            return
        try:
            con = sqlite3.connect(str(DB_PATH), timeout=2.0)
            cur = con.cursor()
            cur.execute("SELECT key, value FROM t_config_data")
            cfg = dict(cur.fetchall())

            raw_lm = cfg.get("lightmode", "6")
            try:
                mode_val = int(raw_lm)
            except ValueError:
                mode_val = 6

            self.light_mode = mode_val
            self.light_mode_name = MODE_VAL_TO_NAME.get(mode_val, "Colourful")

            raw_sleep = cfg.get("sleep_time", "300")
            try:
                self.sleep_time = int(raw_sleep)
            except ValueError:
                self.sleep_time = 300

            raw_gm = cfg.get("gamemode", "1")
            self.game_mode = str(raw_gm) in ("1", "true", "True")

            cur.execute("SELECT brightness, speed, color_value, colorful FROM t_light_data WHERE mode=?", (mode_val,))
            row = cur.fetchone()
            if row:
                self.brightness = int(row[0]) if row[0] is not None else 5
                self.speed = int(row[1]) if row[1] is not None else 3
                if row[2] is not None:
                    cval = int(row[2])
                    self.current_rgb = (cval & 0xFF, (cval >> 8) & 0xFF, (cval >> 16) & 0xFF)
                self.is_rainbow = bool(row[3]) if row[3] is not None else (mode_val == 6)

            con.close()
        except Exception as exc:
            logger.debug("Keyboard DB sync error: %s", exc)

    def _write_db_light_mode(self, mode_val: int, r: int, g: int, b: int) -> None:
        """Sync mode changes back to S75Pro SQLite database."""
        if not DB_PATH.exists():
            return
        try:
            con = sqlite3.connect(str(DB_PATH), timeout=2.0)
            cur = con.cursor()
            cur.execute("UPDATE t_config_data SET value=? WHERE key='lightmode'", (str(mode_val),))
            cval = (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)
            cur.execute("UPDATE t_light_data SET color_value=?, colorful=? WHERE mode=?",
                        (cval, 1 if self.is_rainbow else 0, mode_val))
            con.commit()
            con.close()
        except Exception as exc:
            logger.debug("Keyboard DB write error: %s", exc)

    def set_game_mode(self, enabled: bool) -> bool:
        self.game_mode = enabled
        if DB_PATH.exists():
            try:
                con = sqlite3.connect(str(DB_PATH), timeout=2.0)
                cur = con.cursor()
                cur.execute("UPDATE t_config_data SET value=? WHERE key='gamemode'",
                            ("1" if enabled else "0",))
                con.commit()
                con.close()
            except Exception:
                pass
        return True

    def set_sleep_time(self, seconds: int) -> bool:
        self.sleep_time = seconds
        if DB_PATH.exists():
            try:
                con = sqlite3.connect(str(DB_PATH), timeout=2.0)
                cur = con.cursor()
                cur.execute("UPDATE t_config_data SET value=? WHERE key='sleep_time'",
                            (str(seconds),))
                con.commit()
                con.close()
            except Exception:
                pass
        return True

    def poll(self) -> None:
        if not self.connected:
            self.scan_and_connect()

    def get_status(self) -> dict:
        with self._lock:
            return {
                "connected": self.connected,
                "connection_type": self.connection_type,
                "battery_level": self.battery_level,
                "light_mode": self.light_mode,
                "light_mode_name": self.light_mode_name,
                "current_rgb": self.current_rgb,
                "is_rainbow": self.is_rainbow,
                "brightness": self.brightness,
                "speed": self.speed,
                "game_mode": self.game_mode,
                "sleep_time": self.sleep_time,
                "db_found": DB_PATH.exists(),
            }

    def get_light_mode_names(self) -> List[str]:
        return list(LIGHT_MODE_NAMES)

    def stop(self) -> None:
        with self._lock:
            self.connected = False
            self.connection_type = "Disconnected"
            self._usb_path = None
            self._wireless_paths = []
