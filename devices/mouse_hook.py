r"""
devices/mouse_hook.py
Ultra-lightweight, non-blocking asynchronous button & macro manager.
Does NOT use invasive WH_MOUSE_LL hooks, ensuring 0% cursor stutter,
zero input lag, and completely eliminating mouse freeze issues.

Monitors mouse side buttons (Button 4 / XBUTTON1 and Button 5 / XBUTTON2)
using high-resolution non-invasive Windows state tracking (GetAsyncKeyState).

Supported actions:
- "Browser Forward" / "Browser Backward": Native Windows navigation
- "Double Click": Instant rapid double-click
- "Quick Fire (Macro)": Turbo rapid clicking while holding side button
- "Crouch Jump (Macro)": Instant FPS Ctrl+Space jump
- "Volume Up", "Volume Down", "Mute": Windows multimedia master control
- "Sniper 400 DPI": Low sensitivity sniper mode while held, restored on release
- "Screenshot": Windows + Shift + S snippet tool
"""

import ctypes
import logging
import threading
import time
from typing import Optional, Dict

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

# Virtual key codes for mouse buttons and actions
VK_XBUTTON1 = 0x05  # Mouse Button 4 (Backward)
VK_XBUTTON2 = 0x06  # Mouse Button 5 (Forward)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

VK_LCONTROL    = 0xA2
VK_SPACE       = 0x20
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF
VK_LWIN        = 0x5B
VK_LSHIFT      = 0xA0
VK_S           = 0x53

KEYEVENTF_KEYUP = 0x0002


class MouseHookManager:
    """
    Non-blocking button remapping & macro engine for Noir M1 Nex and universal mice.
    Runs asynchronously without hooking the OS mouse move pipeline.
    """

    _instance: Optional["MouseHookManager"] = None

    def __init__(self, mouse_driver=None):
        self._mouse_driver = mouse_driver
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Button configurations
        # button 4 = XBUTTON1 (Back), button 5 = XBUTTON2 (Forward)
        self._mapping: Dict[int, str] = {
            4: "Browser Forward",
            5: "Browser Backward",
        }

        # Last pressed states
        self._last_state_btn4 = False
        self._last_state_btn5 = False

        # Rapid fire state
        self._quick_fire_active = False

        # Sniper mode state
        self._sniper_prev_dpi: Optional[int] = None

    @classmethod
    def get_instance(cls, mouse_driver=None) -> "MouseHookManager":
        if cls._instance is None:
            cls._instance = cls(mouse_driver)
        elif mouse_driver and cls._instance._mouse_driver is None:
            cls._instance._mouse_driver = mouse_driver
        return cls._instance

    def set_mapping(self, btn_index: int, action: str) -> None:
        """Update button mapping: btn_index is 4 or 5."""
        self._mapping[btn_index] = action
        logger.info("Mouse button %d remapped to: %s", btn_index, action)

    def get_mapping(self, btn_index: int) -> str:
        return self._mapping.get(btn_index, "Default")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop,
                                        name="btn-macro-monitor", daemon=True)
        self._thread.start()
        logger.info("Button & macro monitor engine started (non-blocking).")

    def stop(self) -> None:
        self._running = False
        self._quick_fire_active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)
        logger.info("Button & macro monitor engine stopped.")

    # ------------------------------------------------------------------
    # Non-blocking Polling Loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """
        Polls button states asynchronously at ~80-100Hz with zero OS hook overhead.
        Cursor movement is 100% untouched and native.
        """
        while self._running:
            try:
                # Check Button 4 (VK_XBUTTON1)
                is_down4 = bool(user32.GetAsyncKeyState(VK_XBUTTON1) & 0x8000)
                if is_down4 != self._last_state_btn4:
                    self._last_state_btn4 = is_down4
                    self._on_button_event(4, is_down4)

                # Check Button 5 (VK_XBUTTON2)
                is_down5 = bool(user32.GetAsyncKeyState(VK_XBUTTON2) & 0x8000)
                if is_down5 != self._last_state_btn5:
                    self._last_state_btn5 = is_down5
                    self._on_button_event(5, is_down5)

            except Exception as exc:
                logger.debug("Button monitor error: %s", exc)

            time.sleep(0.012)

    def _on_button_event(self, btn_idx: int, is_down: bool) -> None:
        action = self._mapping.get(btn_idx, "Default")
        if "Default" in action or action in ("Browser Forward", "Browser Backward"):
            return

        if action == "Double Click":
            if is_down:
                threading.Thread(target=self._send_double_click, daemon=True).start()

        elif action == "Quick Fire (Macro)":
            if is_down:
                self._quick_fire_active = True
                threading.Thread(target=self._quick_fire_loop, daemon=True).start()
            else:
                self._quick_fire_active = False

        elif action == "Crouch Jump (Macro)":
            if is_down:
                threading.Thread(target=self._send_crouch_jump, daemon=True).start()

        elif action == "Volume Up":
            if is_down:
                self._send_key(VK_VOLUME_UP)

        elif action == "Volume Down":
            if is_down:
                self._send_key(VK_VOLUME_DOWN)

        elif action == "Mute":
            if is_down:
                self._send_key(VK_VOLUME_MUTE)

        elif action == "Sniper 400 DPI":
            if is_down:
                if self._mouse_driver:
                    self._sniper_prev_dpi = getattr(self._mouse_driver, "current_dpi", 1200)
                    self._mouse_driver.set_dpi(400)
            else:
                if self._mouse_driver and self._sniper_prev_dpi:
                    self._mouse_driver.set_dpi(self._sniper_prev_dpi)
                    self._sniper_prev_dpi = None

        elif action == "Screenshot":
            if is_down:
                threading.Thread(target=self._send_screenshot_shortcut, daemon=True).start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _send_double_click(self) -> None:
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _quick_fire_loop(self) -> None:
        """Rapid turbo clicking (approx 15-18 clicks/sec) while button is held."""
        while self._quick_fire_active:
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.015)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.045)

    def _send_crouch_jump(self) -> None:
        """Sends Ctrl down, Space down, Space up, Ctrl up."""
        user32.keybd_event(VK_LCONTROL, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_SPACE, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_SPACE, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_LCONTROL, 0, KEYEVENTF_KEYUP, 0)

    def _send_screenshot_shortcut(self) -> None:
        """Win + Shift + S for Windows Snipping Tool."""
        user32.keybd_event(VK_LWIN, 0, 0, 0)
        user32.keybd_event(VK_LSHIFT, 0, 0, 0)
        user32.keybd_event(VK_S, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_S, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LSHIFT, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

    def _send_key(self, vk_code: int) -> None:
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
