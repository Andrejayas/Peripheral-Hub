r"""
devices/mouse_hook.py
Windows Low-Level Mouse Hook (WH_MOUSE_LL) for Noir M1 Nex and universal mice.
Provides instantaneous, zero-latency button remapping & macro execution:
- Button 4 (Backward / XBUTTON1)
- Button 5 (Forward / XBUTTON2)
Supported actions:
- Default: "Browser Backward", "Browser Forward"
- "Double Click": Instant hardware double-click
- "Quick Fire (Macro)": Rapid turbo clicking while holding button
- "Crouch Jump (Macro)": Instant FPS Ctrl+Space jump
- "Volume Up", "Volume Down", "Mute": Windows multimedia master control
- "Sniper 400 DPI": Low sensitivity sniper mode while held, restored on release
- "Screenshot": Windows + Shift + S snippet tool
"""

import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import Optional, Callable, Dict

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_QUIT = 0x0012

XBUTTON1 = 0x0001  # Button 4 (Back)
XBUTTON2 = 0x0002  # Button 5 (Forward)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

VK_LCONTROL = 0xA2
VK_SPACE    = 0x20
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF
VK_LWIN     = 0x5B
VK_LSHIFT   = 0xA0
VK_S        = 0x53

KEYEVENTF_KEYUP = 0x0002

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MouseHookManager:
    """
    Manages a Windows WH_MOUSE_LL low-level hook for button remaps and macros.
    Runs on a dedicated thread with an active Windows message loop.
    """

    _instance: Optional["MouseHookManager"] = None

    def __init__(self, mouse_driver=None):
        self._mouse_driver = mouse_driver
        self._hook_id = None
        self._hook_thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._proc_ref = None

        # Button configurations
        # button 4 = XBUTTON1, button 5 = XBUTTON2
        self._mapping: Dict[int, str] = {
            4: "Browser Forward",
            5: "Browser Backward",
        }

        # Rapid fire state
        self._quick_fire_active = False
        self._quick_fire_thread: Optional[threading.Thread] = None

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
        self._hook_thread = threading.Thread(target=self._run_hook_loop,
                                             name="mouse-hook-loop", daemon=True)
        self._hook_thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._quick_fire_active = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    def _run_hook_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        def _hook_callback(nCode, wParam, lParam):
            if nCode >= 0:
                struct = MSLLHOOKSTRUCT.from_address(lParam)
                msg = wParam

                if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                    xbutton = (struct.mouseData >> 16) & 0xFFFF
                    # XBUTTON1 is Button 4, XBUTTON2 is Button 5
                    btn_idx = 4 if xbutton == XBUTTON1 else (5 if xbutton == XBUTTON2 else None)
                    if btn_idx is not None:
                        action = self._mapping.get(btn_idx, "Default")
                        is_down = (msg == WM_XBUTTONDOWN)

                        handled = self._handle_button_action(btn_idx, action, is_down)
                        if handled:
                            return 1  # Suppress default Windows browser forward/back

            return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        self._proc_ref = HOOKPROC(_hook_callback)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._hook_id = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._proc_ref,
            None,
            0
        )

        if not self._hook_id:
            err = kernel32.GetLastError()
            logger.warning("Failed to install WH_MOUSE_LL hook: error %d", err)
            self._running = False
            return

        logger.info("WH_MOUSE_LL hook successfully installed.")

        # Message pump
        msg = wintypes.MSG()
        while self._running:
            bRet = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if bRet <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        logger.info("WH_MOUSE_LL hook stopped.")

    # ------------------------------------------------------------------
    # Action Handlers
    # ------------------------------------------------------------------

    def _handle_button_action(self, btn_idx: int, action: str, is_down: bool) -> bool:
        """
        Execute custom action. Returns True if event was handled (consumed),
        False to let Windows handle default action.
        """
        if "Default" in action or action in ("Browser Forward", "Browser Backward"):
            return False

        if action == "Double Click":
            if is_down:
                threading.Thread(target=self._send_double_click, daemon=True).start()
            return True

        elif action == "Quick Fire (Macro)":
            if is_down:
                self._quick_fire_active = True
                threading.Thread(target=self._quick_fire_loop, daemon=True).start()
            else:
                self._quick_fire_active = False
            return True

        elif action == "Crouch Jump (Macro)":
            if is_down:
                threading.Thread(target=self._send_crouch_jump, daemon=True).start()
            return True

        elif action == "Volume Up":
            if is_down:
                self._send_key(VK_VOLUME_UP)
            return True

        elif action == "Volume Down":
            if is_down:
                self._send_key(VK_VOLUME_DOWN)
            return True

        elif action == "Mute":
            if is_down:
                self._send_key(VK_VOLUME_MUTE)
            return True

        elif action == "Sniper 400 DPI":
            if is_down:
                if self._mouse_driver:
                    self._sniper_prev_dpi = getattr(self._mouse_driver, "current_dpi", 1200)
                    self._mouse_driver.set_dpi(400)
            else:
                if self._mouse_driver and self._sniper_prev_dpi:
                    self._mouse_driver.set_dpi(self._sniper_prev_dpi)
                    self._sniper_prev_dpi = None
            return True

        elif action == "Screenshot":
            if is_down:
                threading.Thread(target=self._send_screenshot_shortcut, daemon=True).start()
            return True

        return False

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
