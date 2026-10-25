"""
popup.py
ConnectionPopup - Animated slide-in notification window.
Appears at bottom-right corner of the screen when a device connects/disconnects.
Auto-dismisses after 5 seconds; hover pauses the timer.
"""

import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional, Callable

# Colors
BG_COLOR     = "#1a1a1a"
CARD_COLOR   = "#242424"
ACCENT       = "#e26332"
TEXT_COLOR   = "#ffffff"
DIM_COLOR    = "#888888"
GREEN        = "#4caf50"
ORANGE       = "#ff9800"
RED          = "#f44336"

POPUP_WIDTH  = 320
POPUP_HEIGHT = 90
MARGIN       = 16          # distance from screen edge
AUTO_DISMISS = 5.0         # seconds before auto-dismiss
SLIDE_STEPS  = 20          # animation frames
SLIDE_MS     = 15          # ms per frame


def _battery_color(pct: Optional[int]) -> str:
    if pct is None:
        return DIM_COLOR
    if pct >= 50:
        return GREEN
    if pct >= 20:
        return ORANGE
    return RED


class ConnectionPopup:
    """
    A non-blocking, animated slide-in notification popup.
    Shows device name, connection status, and optional battery level.
    """

    def __init__(self,
                 device_name: str,
                 event: str,                  # "connected" or "disconnected"
                 battery_pct: Optional[int] = None,
                 icon_image=None,             # PIL ImageTk.PhotoImage
                 on_close: Optional[Callable] = None):
        self._device_name = device_name
        self._event = event
        self._battery_pct = battery_pct
        self._icon_image = icon_image
        self._on_close = on_close

        self._hovered = False
        self._dismissed = False
        self._timer_elapsed = 0.0
        self._timer_paused = False
        self._root: Optional[tk.Toplevel] = None

        self._build()
        self._animate_in()
        self._start_dismiss_timer()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Create the popup Toplevel window."""
        self._root = tk.Toplevel()
        root = self._root

        # Window chrome
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.0)   # start transparent for fade-in
        root.configure(bg=CARD_COLOR)
        root.resizable(False, False)

        # Position: off-screen right initially (for slide animation)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        target_x = sw - POPUP_WIDTH - MARGIN
        target_y = sh - POPUP_HEIGHT - MARGIN - 48   # 48 = approx taskbar height
        self._target_x = target_x
        self._target_y = target_y
        self._start_x = sw + 10  # start off-screen right

        root.geometry(f"{POPUP_WIDTH}x{POPUP_HEIGHT}+{self._start_x}+{target_y}")

        # Outer frame with border
        outer = tk.Frame(root, bg=ACCENT, padx=2, pady=2)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg=CARD_COLOR, padx=12, pady=10)
        inner.pack(fill="both", expand=True)

        # Left: device icon
        if self._icon_image:
            icon_lbl = tk.Label(inner, image=self._icon_image,
                                bg=CARD_COLOR, cursor="hand2")
            icon_lbl.pack(side="left", padx=(0, 10))

        # Center: text
        text_frame = tk.Frame(inner, bg=CARD_COLOR)
        text_frame.pack(side="left", fill="both", expand=True)

        status_text = "Connected" if self._event == "connected" else "Disconnected"
        status_color = GREEN if self._event == "connected" else RED

        name_lbl = tk.Label(text_frame, text=self._device_name,
                            font=("Segoe UI", 10, "bold"),
                            fg=TEXT_COLOR, bg=CARD_COLOR, anchor="w")
        name_lbl.pack(fill="x")

        status_lbl = tk.Label(text_frame, text=status_text,
                              font=("Segoe UI", 9),
                              fg=status_color, bg=CARD_COLOR, anchor="w")
        status_lbl.pack(fill="x")

        if self._battery_pct is not None:
            bat_color = _battery_color(self._battery_pct)
            bat_lbl = tk.Label(text_frame,
                               text=f"Battery: {self._battery_pct}%",
                               font=("Segoe UI", 8),
                               fg=bat_color, bg=CARD_COLOR, anchor="w")
            bat_lbl.pack(fill="x")

        # Right: close button
        close_btn = tk.Label(inner, text="✕", font=("Segoe UI", 10),
                             fg=DIM_COLOR, bg=CARD_COLOR, cursor="hand2")
        close_btn.pack(side="right", anchor="n")
        close_btn.bind("<Button-1>", lambda e: self.dismiss())

        # Hover bindings
        for widget in [root, outer, inner, text_frame, name_lbl, status_lbl]:
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _animate_in(self) -> None:
        """Slide window in from the right."""
        if self._root is None:
            return
        total_dx = self._start_x - self._target_x
        step_dx = total_dx / SLIDE_STEPS

        def step(i):
            if self._root is None or self._dismissed:
                return
            x = int(self._start_x - step_dx * i)
            alpha = min(1.0, i / SLIDE_STEPS)
            try:
                self._root.geometry(f"{POPUP_WIDTH}x{POPUP_HEIGHT}+{x}+{self._target_y}")
                self._root.attributes("-alpha", alpha)
            except tk.TclError:
                return
            if i < SLIDE_STEPS:
                self._root.after(SLIDE_MS, lambda: step(i + 1))

        step(1)

    def _animate_out(self, callback: Optional[Callable] = None) -> None:
        """Slide window back out to the right before destroying."""
        if self._root is None:
            if callback:
                callback()
            return
        total_dx = self._start_x - self._target_x
        step_dx = total_dx / SLIDE_STEPS

        def step(i):
            if self._root is None:
                if callback:
                    callback()
                return
            x = int(self._target_x + step_dx * i)
            alpha = max(0.0, 1.0 - i / SLIDE_STEPS)
            try:
                self._root.geometry(f"{POPUP_WIDTH}x{POPUP_HEIGHT}+{x}+{self._target_y}")
                self._root.attributes("-alpha", alpha)
            except tk.TclError:
                if callback:
                    callback()
                return
            if i < SLIDE_STEPS:
                self._root.after(SLIDE_MS, lambda: step(i + 1))
            else:
                self._destroy()
                if callback:
                    callback()

        step(1)

    # ------------------------------------------------------------------
    # Dismiss logic
    # ------------------------------------------------------------------

    def _on_enter(self, event=None) -> None:
        self._hovered = True

    def _on_leave(self, event=None) -> None:
        self._hovered = False

    def _start_dismiss_timer(self) -> None:
        """Start a background thread that auto-dismisses after AUTO_DISMISS seconds."""
        def _timer():
            elapsed = 0.0
            interval = 0.1
            while elapsed < AUTO_DISMISS and not self._dismissed:
                time.sleep(interval)
                if not self._hovered:
                    elapsed += interval
        threading.Thread(target=_timer, daemon=True,
                         name="popup-timer").start()
        # Schedule periodic check on main thread
        self._check_dismiss()

    def _check_dismiss(self) -> None:
        if self._dismissed or self._root is None:
            return
        # Re-schedule every 100ms; actual dismiss is driven by timer thread
        # We do the dismiss check here to stay on the Tk main thread
        self._root.after(100, self._check_dismiss_tick)

    def _check_dismiss_tick(self) -> None:
        if self._dismissed or self._root is None:
            return
        # Count elapsed non-hovered time using after() calls
        if not hasattr(self, "_tick_elapsed"):
            self._tick_elapsed = 0.0
        if not self._hovered:
            self._tick_elapsed += 0.1
        if self._tick_elapsed >= AUTO_DISMISS:
            self.dismiss()
        else:
            try:
                self._root.after(100, self._check_dismiss_tick)
            except tk.TclError:
                pass

    def dismiss(self) -> None:
        """Begin dismiss animation then destroy window."""
        if self._dismissed:
            return
        self._dismissed = True
        self._animate_out(callback=self._on_close)

    def _destroy(self) -> None:
        try:
            if self._root:
                self._root.destroy()
        except tk.TclError:
            pass
        finally:
            self._root = None


class PopupManager:
    """
    Manages multiple popups, stacking them vertically from the bottom-right.
    Called from the main thread only.
    """

    def __init__(self):
        self._active: list = []

    def show(self, device_name: str, event: str,
             battery_pct: Optional[int] = None,
             icon_image=None) -> None:
        """Show a new connection popup. Called from Tk main thread."""
        def _on_close():
            self._active = [p for p in self._active if not p._dismissed]

        popup = ConnectionPopup(
            device_name=device_name,
            event=event,
            battery_pct=battery_pct,
            icon_image=icon_image,
            on_close=_on_close,
        )
        self._active.append(popup)
