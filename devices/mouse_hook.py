r"""
devices/mouse_hook.py
Ultra-lightweight, non-blocking asynchronous button & macro manager.
Uses Windows RawInput (RIDEV_INPUTSINK) with GetAsyncKeyState dual-engine detection.
Ensures 100% reliable side button capture (Button 4 & Button 5 / XBUTTON1 & XBUTTON2)
globally across all Windows applications and games with ZERO cursor lag or freeze.

Supported actions:
- "Next Track": Windows Media Next Track (VK_MEDIA_NEXT_TRACK)
- "Previous Track": Windows Media Previous Track (VK_MEDIA_PREV_TRACK)
- "Play/Pause": Windows Media Play/Pause (VK_MEDIA_PLAY_PAUSE)
- "Volume Up", "Volume Down", "Mute": Windows master multimedia volume
- "Browser Forward", "Browser Backward": Native Windows navigation
- "Double Click": Instant hardware double-click
- "Quick Fire (Macro)": Rapid turbo clicking while holding button
- "Crouch Jump (Macro)": Instant FPS Ctrl+Space jump
- "Sniper 400 DPI": Low sensitivity sniper mode while held, restored on release
- "Screenshot": Windows + Shift + S snippet tool
"""

import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import Optional, Dict, Callable

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Virtual key codes
VK_XBUTTON1          = 0x05  # Mouse Button 4 (Backward)
VK_XBUTTON2          = 0x06  # Mouse Button 5 (Forward)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

VK_LCONTROL          = 0xA2
VK_SPACE             = 0x20
VK_VOLUME_MUTE       = 0xAD
VK_VOLUME_DOWN       = 0xAE
VK_VOLUME_UP         = 0xAF
VK_MEDIA_NEXT_TRACK  = 0xB0
VK_MEDIA_PREV_TRACK  = 0xB1
VK_MEDIA_PLAY_PAUSE  = 0xB3
VK_BROWSER_BACK      = 0xA6
VK_BROWSER_FORWARD   = 0xA7
VK_LWIN              = 0x5B
VK_LSHIFT            = 0xA0
VK_S                 = 0x53

KEYEVENTF_KEYUP      = 0x0002

# RawInput Structures
WM_INPUT   = 0x00FF
RID_INPUT  = 0x10000003

LRESULT = ctypes.c_int64
WPARAM  = ctypes.c_uint64
LPARAM  = ctypes.c_int64
HWND    = ctypes.c_void_p
UINT    = ctypes.c_uint

user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("hwndTarget", ctypes.c_void_p),
    ]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", ctypes.c_uint32),
        ("dwSize", ctypes.c_uint32),
        ("hDevice", ctypes.c_uint64),
        ("wParam", ctypes.c_uint64),
    ]

class RAWMOUSE(ctypes.Structure):
    class _U(ctypes.Union):
        class _S(ctypes.Structure):
            _fields_ = [
                ("usButtonFlags", ctypes.c_uint16),
                ("usButtonData", ctypes.c_uint16),
            ]
        _fields_ = [
            ("ulButtons", ctypes.c_uint32),
            ("_s", _S),
        ]
    _anonymous_ = ("_u",)
    _fields_ = [
        ("usFlags", ctypes.c_uint16),
        ("_u", _U),
        ("ulRawButtons", ctypes.c_uint32),
        ("lLastX", ctypes.c_int32),
        ("lLastY", ctypes.c_int32),
        ("ulExtraInformation", ctypes.c_uint32),
    ]

class RAWINPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mouse", RAWMOUSE)]
    _anonymous_ = ("_u",)
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("_u", _U),
    ]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


class MouseHookManager:
    """
    Non-blocking button remapping & macro engine for Noir M1 Nex and universal mice.
    Uses native Windows RawInput with state polling fallback.
    Cursor movement is 100% untouched and native.
    """

    _instance: Optional["MouseHookManager"] = None

    def __init__(self, mouse_driver=None):
        self._mouse_driver = mouse_driver
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[int, str], None]] = None

        # Button configurations
        # button 4 = XBUTTON1 (Back), button 5 = XBUTTON2 (Forward)
        self._mapping: Dict[int, str] = {
            4: "Next Track",
            5: "Browser Backward",
        }

        # Last pressed states
        self._last_state_btn4 = False
        self._last_state_btn5 = False
        self._last_event_time_btn4 = 0.0
        self._last_event_time_btn5 = 0.0

        # Rapid fire state
        self._quick_fire_active = False

        # Sniper mode state
        self._sniper_prev_dpi: Optional[int] = None

        # Win32 window handles for RawInput
        self._wnd_proc_ref = None
        self._hwnd = None

    @classmethod
    def get_instance(cls, mouse_driver=None) -> "MouseHookManager":
        if cls._instance is None:
            cls._instance = cls(mouse_driver)
        elif mouse_driver and cls._instance._mouse_driver is None:
            cls._instance._mouse_driver = mouse_driver
        return cls._instance

    def set_callback(self, callback: Callable[[int, str], None]) -> None:
        """Register a callback for button press events: cb(btn_idx: int, action: str)."""
        self._callback = callback

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
        self._thread = threading.Thread(target=self._run_dual_engine,
                                        name="btn-rawinput-monitor", daemon=True)
        self._thread.start()
        logger.info("Button & macro monitor engine started (RawInput + Async Polling).")

    def stop(self) -> None:
        self._running = False
        self._quick_fire_active = False
        if self._hwnd:
            try:
                user32.PostMessageW(self._hwnd, 0x0010, 0, 0) # WM_CLOSE
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.3)
        logger.info("Button & macro monitor engine stopped.")

    # ------------------------------------------------------------------
    # Dual Engine Loop (RawInput + Async Polling)
    # ------------------------------------------------------------------

    def _run_dual_engine(self) -> None:
        """
        Runs RawInput message window alongside async state check.
        Ensures 100% catch rate without any cursor hook interference.
        """
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = f"PeripheralHubRaw_{id(self)}"

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                raw = RAWINPUT()
                size = ctypes.c_uint(ctypes.sizeof(RAWINPUT))
                res = user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(raw), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
                if res != -1:
                    bf = raw.mouse.usButtonFlags
                    now = time.time()
                    # RI_MOUSE_BUTTON_4_DOWN (0x0040), UP (0x0080)
                    if (bf & 0x0040) and (now - self._last_event_time_btn4 > 0.05):
                        self._last_event_time_btn4 = now
                        self._last_state_btn4 = True
                        self._on_button_event(4, True)
                    elif bf & 0x0080:
                        self._last_state_btn4 = False
                        self._on_button_event(4, False)

                    # RI_MOUSE_BUTTON_5_DOWN (0x0100), UP (0x0200)
                    if (bf & 0x0100) and (now - self._last_event_time_btn5 > 0.05):
                        self._last_event_time_btn5 = now
                        self._last_state_btn5 = True
                        self._on_button_event(5, True)
                    elif bf & 0x0200:
                        self._last_state_btn5 = False
                        self._on_button_event(5, False)

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(_wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        HWND_MESSAGE = ctypes.c_void_p(-3)
        self._hwnd = user32.CreateWindowExW(0, cls_name, "RawInputWindow", 0, 0, 0, 0, 0,
                                            HWND_MESSAGE, None, hinst, None)

        rid = RAWINPUTDEVICE()
        rid.usUsagePage = 0x01  # Generic Desktop
        rid.usUsage = 0x02      # Mouse
        rid.dwFlags = 0x00000100  # RIDEV_INPUTSINK (receives events globally)
        rid.hwndTarget = self._hwnd
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE))

        msg = wintypes.MSG()
        while self._running:
            # 1. Process RawInput messages
            while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            # 2. Async Polling Fallback (in case hardware sends direct XBUTTON)
            try:
                now = time.time()
                is_down4 = bool(user32.GetAsyncKeyState(VK_XBUTTON1) & 0x8000)
                if is_down4 != self._last_state_btn4:
                    self._last_state_btn4 = is_down4
                    if is_down4 and (now - self._last_event_time_btn4 > 0.08):
                        self._last_event_time_btn4 = now
                        self._on_button_event(4, True)
                    elif not is_down4:
                        self._on_button_event(4, False)

                is_down5 = bool(user32.GetAsyncKeyState(VK_XBUTTON2) & 0x8000)
                if is_down5 != self._last_state_btn5:
                    self._last_state_btn5 = is_down5
                    if is_down5 and (now - self._last_event_time_btn5 > 0.08):
                        self._last_event_time_btn5 = now
                        self._on_button_event(5, True)
                    elif not is_down5:
                        self._on_button_event(5, False)
            except Exception:
                pass

            time.sleep(0.015)

        # Cleanup
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        user32.UnregisterClassW(cls_name, hinst)

    def _on_button_event(self, btn_idx: int, is_down: bool) -> None:
        action = self._mapping.get(btn_idx, "Default")

        # Notify UI callback immediately when button is pressed
        if is_down and self._callback:
            try:
                self._callback(btn_idx, action)
            except Exception as exc:
                logger.debug("Button callback error: %s", exc)

        if "Default" in action:
            return

        if action == "Browser Forward":
            if is_down:
                self._send_key(VK_BROWSER_FORWARD)

        elif action == "Browser Backward":
            if is_down:
                self._send_key(VK_BROWSER_BACK)

        elif action == "Next Track":
            if is_down:
                self._send_key(VK_MEDIA_NEXT_TRACK)

        elif action == "Previous Track":
            if is_down:
                self._send_key(VK_MEDIA_PREV_TRACK)

        elif action == "Play/Pause":
            if is_down:
                self._send_key(VK_MEDIA_PLAY_PAUSE)

        elif action == "Volume Up":
            if is_down:
                self._send_key(VK_VOLUME_UP)

        elif action == "Volume Down":
            if is_down:
                self._send_key(VK_VOLUME_DOWN)

        elif action == "Mute":
            if is_down:
                self._send_key(VK_VOLUME_MUTE)

        elif action == "Double Click":
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
