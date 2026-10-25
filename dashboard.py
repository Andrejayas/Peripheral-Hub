"""
dashboard.py
Dashboard - Main Peripheral Hub control window.
420x640 dark-themed tkinter window showing device cards and audio panel.
Positioned at bottom-right corner. Refreshes every 4 seconds when open.
Includes active device scanner (Pindai Perangkat), Custom RGB Keyboard Palette,
tactile Mouse DPI & Cursor Speed adjustment, and Audio Enhancer inspired by FxSound.
"""

import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

# Colors
BG       = "#181818"
CARD     = "#222222"
ACCENT   = "#e26332"
TEXT     = "#ffffff"
DIM      = "#888888"
GREEN    = "#4caf50"
ORANGE   = "#ff9800"
RED      = "#f44336"
BORDER   = "#303030"

WIN_W    = 420
WIN_H    = 640
REFRESH_INTERVAL = 4000  # ms


def _battery_color(pct: Optional[int]) -> str:
    if pct is None:
        return DIM
    if pct >= 50:
        return GREEN
    if pct >= 20:
        return ORANGE
    return RED


def _pct_text(pct: Optional[int]) -> str:
    return f"{pct}%" if pct is not None else "N/A"


class _SectionCard(tk.Frame):
    """A styled card frame for device/audio sections."""
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent, bg=CARD, padx=12, pady=10, **kwargs)
        title_lbl = tk.Label(self, text=title, font=("Segoe UI", 10, "bold"),
                             fg=ACCENT, bg=CARD, anchor="w")
        title_lbl.pack(fill="x", pady=(0, 6))


class _BatteryBar(tk.Canvas):
    """A horizontal battery-fill bar widget."""
    def __init__(self, parent, width=120, height=14, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._bar_w = width
        self._bar_h = height
        self._draw(0, DIM)

    def set_value(self, pct: Optional[int]) -> None:
        if pct is None:
            self._draw(0, DIM)
        else:
            color = _battery_color(pct)
            self._draw(pct, color)

    def _draw(self, pct: int, color: str) -> None:
        self.delete("all")
        self.create_rectangle(0, 0, self._bar_w - 1, self._bar_h - 1,
                               outline=BORDER, fill=BG)
        nub_w, nub_h = 4, 6
        self.create_rectangle(self._bar_w, (self._bar_h - nub_h) // 2,
                               self._bar_w + nub_w, (self._bar_h + nub_h) // 2,
                               fill=BORDER, outline="")
        fill_w = int((self._bar_w - 2) * max(0, min(100, pct)) / 100)
        if fill_w > 0:
            self.create_rectangle(1, 1, fill_w, self._bar_h - 2,
                                   fill=color, outline="")


class _DpiButton(tk.Label):
    """A small selectable DPI button."""
    def __init__(self, parent, dpi: int, on_click: Callable, **kwargs):
        super().__init__(parent,
                         text=str(dpi) if dpi < 1000 else f"{dpi//1000}K",
                         font=("Segoe UI", 8),
                         fg=DIM, bg=BORDER,
                         padx=6, pady=3,
                         cursor="hand2",
                         relief="flat",
                         **kwargs)
        self._dpi = dpi
        self._on_click = on_click
        self.bind("<Button-1>", lambda e: on_click(dpi))

    def set_active(self, active: bool) -> None:
        self.configure(
            fg=TEXT if active else DIM,
            bg=ACCENT if active else BORDER,
            font=("Segoe UI", 8, "bold" if active else "normal")
        )


class Dashboard:
    """
    Peripheral Hub main dashboard window.
    Integrated device controls, customizable RGB colors, and FxSound-inspired audio tuner.
    """

    def __init__(self,
                 mouse=None,
                 keyboard=None,
                 headset=None,
                 eq_apo=None,
                 fxsound=None,
                 on_close: Optional[Callable] = None,
                 on_scan: Optional[Callable] = None):
        self._mouse = mouse
        self._keyboard = keyboard
        self._headset = headset
        self._eq_apo = eq_apo
        self._fxsound = fxsound
        self._on_close = on_close
        self._on_scan = on_scan

        self._root: Optional[tk.Toplevel] = None
        self._visible = False
        self._refresh_job = None
        self._dpi_buttons: Dict[int, _DpiButton] = {}
        self._eq_buttons: Dict[str, tk.Button] = {}

        # Audio Enhancement Sliders (Inspired by FxSound)
        self._bass_val = 60
        self._clarity_val = 80
        self._surround_val = 70
        self._boost_val = 50

        self._build()

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = tk.Toplevel()
        self._root = root
        root.title("Peripheral Hub")
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = sw - WIN_W - 16
        y = sh - WIN_H - 48
        root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        root.protocol("WM_DELETE_WINDOW", self.hide)

        self._build_header()
        self._build_scroll_area()
        self._build_footer()

        root.withdraw()

    def _build_header(self) -> None:
        hdr = tk.Frame(self._root, bg=CARD, pady=10)
        hdr.pack(fill="x")

        tk.Label(hdr, text="⬡  Peripheral Hub",
                 font=("Segoe UI", 12, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left", padx=14)

        btn_frame = tk.Frame(hdr, bg=CARD)
        btn_frame.pack(side="right", padx=8)
        self._make_header_btn(btn_frame, "−", self.hide)
        self._make_header_btn(btn_frame, "✕", self.hide)

        # Manual Scan button
        self._scan_btn = tk.Label(hdr, text="🔄 Pindai",
                                  font=("Segoe UI", 9, "bold"),
                                  fg=ACCENT, bg=BORDER,
                                  cursor="hand2", padx=8, pady=3)
        self._scan_btn.pack(side="right", padx=(0, 8))
        self._scan_btn.bind("<Button-1>", lambda e: self.scan_all())
        self._scan_btn.bind("<Enter>", lambda e: self._scan_btn.configure(bg=CARD, fg=TEXT))
        self._scan_btn.bind("<Leave>", lambda e: self._scan_btn.configure(bg=BORDER, fg=ACCENT))

        sep = tk.Frame(self._root, bg=ACCENT, height=2)
        sep.pack(fill="x")

    def _make_header_btn(self, parent, text: str, cmd: Callable) -> tk.Label:
        btn = tk.Label(parent, text=text, font=("Segoe UI", 11),
                       fg=DIM, bg=CARD, cursor="hand2", padx=6)
        btn.pack(side="left")
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(fg=TEXT))
        btn.bind("<Leave>", lambda e: btn.configure(fg=DIM))
        return btn

    def _build_scroll_area(self) -> None:
        container = tk.Frame(self._root, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=4)

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=BG)
        self._scroll_window = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")

        self._scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self._scroll_window, width=e.width))

        # Mouse wheel scroll on canvas ONLY (do NOT use bind_all so comboboxes scroll independently)
        def _on_mousewheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)
        self._scroll_frame.bind("<MouseWheel>", _on_mousewheel)

        self._build_mouse_card()
        self._build_keyboard_card()
        self._build_headset_card()
        self._build_audio_panel()

    def _spacer(self, parent, h=4) -> None:
        tk.Frame(parent, bg=BG, height=h).pack(fill="x")

    # ------------------------------------------------------------------
    # Mouse Card
    # ------------------------------------------------------------------

    def _build_mouse_card(self) -> None:
        self._spacer(self._scroll_frame, 2)
        card = _SectionCard(self._scroll_frame, "🖱  Noir M1 Nex")
        card.pack(fill="x", padx=4, pady=3)

        status_row = tk.Frame(card, bg=CARD)
        status_row.pack(fill="x")

        self._mouse_status_lbl = tk.Label(status_row, text="● Disconnected",
                                           font=("Segoe UI", 9, "bold"),
                                           fg=RED, bg=CARD)
        self._mouse_status_lbl.pack(side="left")

        self._mouse_charging_lbl = tk.Label(status_row, text="",
                                             font=("Segoe UI", 9, "bold"),
                                             fg=ORANGE, bg=CARD)
        self._mouse_charging_lbl.pack(side="right")

        # Battery row
        bat_row = tk.Frame(card, bg=CARD)
        bat_row.pack(fill="x", pady=(5, 2))
        tk.Label(bat_row, text="Battery", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=8, anchor="w").pack(side="left")
        self._mouse_bat_bar = _BatteryBar(bat_row, width=170)
        self._mouse_bat_bar.pack(side="left", padx=6)
        self._mouse_bat_lbl = tk.Label(bat_row, text="N/A",
                                        font=("Segoe UI", 8, "bold"),
                                        fg=DIM, bg=CARD)
        self._mouse_bat_lbl.pack(side="left")

        # DPI Selector row
        dpi_row = tk.Frame(card, bg=CARD)
        dpi_row.pack(fill="x", pady=(5, 2))
        tk.Label(dpi_row, text="DPI Speed", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=8, anchor="w").pack(side="left")
        dpi_btn_frame = tk.Frame(dpi_row, bg=CARD)
        dpi_btn_frame.pack(side="left")
        for dpi in [400, 800, 1200, 2400, 3200, 5000, 10000]:
            btn = _DpiButton(dpi_btn_frame, dpi, self._on_dpi_click)
            btn.pack(side="left", padx=2)
            self._dpi_buttons[dpi] = btn

        rate_row = tk.Frame(card, bg=CARD)
        rate_row.pack(fill="x", pady=2)
        tk.Label(rate_row, text="Current DPI", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")
        self._mouse_dpi_lbl = tk.Label(rate_row, text="1200",
                                        font=("Segoe UI", 9, "bold"),
                                        fg=TEXT, bg=CARD)
        self._mouse_dpi_lbl.pack(side="left")

    def _on_dpi_click(self, dpi: int) -> None:
        if self._mouse is None:
            return
        threading.Thread(target=self._mouse.set_dpi, args=(dpi,),
                         daemon=True, name="dpi-set").start()
        for d, btn in self._dpi_buttons.items():
            btn.set_active(d == dpi)
        self._mouse_dpi_lbl.configure(text=f"{dpi} DPI")

    # ------------------------------------------------------------------
    # Keyboard Card
    # ------------------------------------------------------------------

    def _build_keyboard_card(self) -> None:
        self._spacer(self._scroll_frame, 2)
        card = _SectionCard(self._scroll_frame, "⌨  AULA S75 Pro")
        card.pack(fill="x", padx=4, pady=3)

        self._kb_status_lbl = tk.Label(card, text="● Disconnected",
                                        font=("Segoe UI", 9, "bold"),
                                        fg=RED, bg=CARD, anchor="w")
        self._kb_status_lbl.pack(fill="x")

        # Light mode dropdown
        lm_row = tk.Frame(card, bg=CARD)
        lm_row.pack(fill="x", pady=(5, 2))
        tk.Label(lm_row, text="Light Mode", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")

        from devices.keyboard import LIGHT_MODE_NAMES
        self._kb_light_var = tk.StringVar(value="Colourful")
        self._kb_light_menu = ttk.Combobox(lm_row, textvariable=self._kb_light_var,
                                           values=LIGHT_MODE_NAMES, width=18,
                                           state="readonly")
        self._kb_light_menu.pack(side="left", padx=4)
        self._kb_light_menu.bind("<<ComboboxSelected>>", self._on_light_mode_change)

        # Custom Color Palette row
        color_row = tk.Frame(card, bg=CARD)
        color_row.pack(fill="x", pady=(4, 2))
        tk.Label(color_row, text="Custom RGB", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")

        from devices.keyboard import COLOR_PRESETS
        color_btn_frame = tk.Frame(color_row, bg=CARD)
        color_btn_frame.pack(side="left")

        for name, hex_code, (r, g, b) in COLOR_PRESETS:
            is_rain = (name == "Rainbow")
            cbtn = tk.Label(color_btn_frame,
                            text="🌈" if is_rain else "●",
                            font=("Segoe UI", 11 if not is_rain else 9, "bold"),
                            fg=ACCENT if is_rain else hex_code,
                            bg=CARD, cursor="hand2", padx=3)
            cbtn.pack(side="left")
            cbtn.bind("<Button-1>", lambda e, red=r, green=g, blue=b, rain=is_rain: self._on_kb_color_click(red, green, blue, rain))

        # Brightness slider
        br_row = tk.Frame(card, bg=CARD)
        br_row.pack(fill="x", pady=(4, 2))
        tk.Label(br_row, text="Brightness", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")
        self._kb_br_var = tk.IntVar(value=5)
        self._kb_br_slider = tk.Scale(br_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_br_var,
                                      command=self._on_kb_brightness_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=140,
                                      showvalue=False)
        self._kb_br_slider.pack(side="left")
        self._kb_br_lbl = tk.Label(br_row, text="Level 5",
                                    font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._kb_br_lbl.pack(side="left", padx=4)

        # Speed slider
        sp_row = tk.Frame(card, bg=CARD)
        sp_row.pack(fill="x", pady=(2, 2))
        tk.Label(sp_row, text="Speed", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")
        self._kb_sp_var = tk.IntVar(value=3)
        self._kb_sp_slider = tk.Scale(sp_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_sp_var,
                                      command=self._on_kb_speed_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=140,
                                      showvalue=False)
        self._kb_sp_slider.pack(side="left")
        self._kb_sp_lbl = tk.Label(sp_row, text="Speed 3",
                                    font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._kb_sp_lbl.pack(side="left", padx=4)

    def _on_light_mode_change(self, event=None) -> None:
        if self._keyboard is None:
            return
        name = self._kb_light_var.get()
        threading.Thread(target=self._keyboard.set_light_mode_by_name, args=(name,),
                         daemon=True, name="kb-light").start()

    def _on_kb_color_click(self, r: int, g: int, b: int, is_rainbow: bool) -> None:
        if self._keyboard is None:
            return
        threading.Thread(target=self._keyboard.set_color, args=(r, g, b, is_rainbow),
                         daemon=True, name="kb-color").start()
        if is_rainbow:
            self._kb_light_var.set("Colourful")
        else:
            self._kb_light_var.set("Static")

    def _on_kb_brightness_change(self, val) -> None:
        if self._keyboard is None:
            return
        lvl = int(float(val))
        self._kb_br_lbl.configure(text=f"Level {lvl}")
        threading.Thread(target=self._keyboard.set_brightness, args=(lvl,),
                         daemon=True, name="kb-br").start()

    def _on_kb_speed_change(self, val) -> None:
        if self._keyboard is None:
            return
        lvl = int(float(val))
        self._kb_sp_lbl.configure(text=f"Speed {lvl}")
        threading.Thread(target=self._keyboard.set_speed, args=(lvl,),
                         daemon=True, name="kb-sp").start()

    # ------------------------------------------------------------------
    # Headset Card
    # ------------------------------------------------------------------

    def _build_headset_card(self) -> None:
        self._spacer(self._scroll_frame, 2)
        card = _SectionCard(self._scroll_frame, "🎧  dbE Kumo GS1X Pro")
        card.pack(fill="x", padx=4, pady=3)

        self._hs_status_lbl = tk.Label(card, text="● Dongle Not Detected",
                                        font=("Segoe UI", 9, "bold"),
                                        fg=RED, bg=CARD, anchor="w")
        self._hs_status_lbl.pack(fill="x")

        # Battery estimate
        bat_row = tk.Frame(card, bg=CARD)
        bat_row.pack(fill="x", pady=(5, 2))
        tk.Label(bat_row, text="Est. Battery", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")
        self._hs_bat_bar = _BatteryBar(bat_row, width=140)
        self._hs_bat_bar.pack(side="left", padx=4)
        self._hs_bat_lbl = tk.Label(bat_row, text="N/A",
                                     font=("Segoe UI", 8, "bold"),
                                     fg=DIM, bg=CARD)
        self._hs_bat_lbl.pack(side="left")

        # Volume slider
        vol_row = tk.Frame(card, bg=CARD)
        vol_row.pack(fill="x", pady=(5, 2))
        tk.Label(vol_row, text="Volume", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=10, anchor="w").pack(side="left")
        self._hs_vol_var = tk.IntVar(value=50)
        self._hs_vol_slider = tk.Scale(vol_row, from_=0, to=100, orient="horizontal",
                                       variable=self._hs_vol_var,
                                       command=self._on_volume_change,
                                       bg=CARD, fg=TEXT, troughcolor=BORDER,
                                       highlightthickness=0, length=160,
                                       showvalue=False)
        self._hs_vol_slider.pack(side="left")
        self._hs_vol_lbl = tk.Label(vol_row, text="50%",
                                     font=("Segoe UI", 8, "bold"),
                                     fg=TEXT, bg=CARD)
        self._hs_vol_lbl.pack(side="left", padx=4)

        # Usage & Mark Charged row
        btn_row = tk.Frame(card, bg=CARD)
        btn_row.pack(fill="x", pady=(5, 2))
        self._hs_usage_lbl = tk.Label(btn_row, text="Usage: 0h 00m",
                                       font=("Segoe UI", 8),
                                       fg=DIM, bg=CARD)
        self._hs_usage_lbl.pack(side="left")

        charged_btn = tk.Button(btn_row, text="⚡ Mark Charged",
                                 font=("Segoe UI", 8, "bold"),
                                 fg=TEXT, bg=BORDER,
                                 relief="flat", padx=6, pady=2,
                                 cursor="hand2",
                                 command=self._on_mark_charged)
        charged_btn.pack(side="right")

    def _on_volume_change(self, val) -> None:
        v = int(float(val))
        self._hs_vol_lbl.configure(text=f"{v}%")
        if self._headset is None:
            return
        threading.Thread(target=self._headset.set_volume, args=(v,),
                         daemon=True, name="hs-vol").start()

    def _on_mark_charged(self) -> None:
        if self._headset:
            threading.Thread(target=self._headset.mark_as_charged,
                             daemon=True, name="hs-charge").start()
            self._root.after(100, self._refresh_headset)

    # ------------------------------------------------------------------
    # Audio Panel (Custom Tuning inspired by FxSound)
    # ------------------------------------------------------------------

    def _build_audio_panel(self) -> None:
        self._spacer(self._scroll_frame, 2)
        card = _SectionCard(self._scroll_frame, "🎚  Audio Enhancer (FxSound Style)")
        card.pack(fill="x", padx=4, pady=3)

        profiles = [
            ("fps_step_booster", "🎮 FPS Booster", "Gaming"),
            ("music_movie",      "🎵 Music / Vocal", "Music"),
            ("bass_boost",       "🔊 Bass Boost",    "Bass Boost"),
            ("gaming_surround",  "🎬 Cinematic",     "Movie"),
        ]

        grid_frame = tk.Frame(card, bg=CARD)
        grid_frame.pack(fill="x", pady=2)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        for idx, (key, label, fx_preset) in enumerate(profiles):
            r = idx // 2
            c = idx % 2
            btn = tk.Button(grid_frame, text=label,
                            font=("Segoe UI", 8, "bold"),
                            fg=DIM, bg=BORDER,
                            relief="flat", padx=6, pady=5,
                            cursor="hand2",
                            command=lambda k=key, fp=fx_preset: self._on_eq_profile(k, fp))
            btn.grid(row=r, column=c, padx=3, pady=2, sticky="ew")
            self._eq_buttons[key] = btn

        # Custom Audio Tuning Sliders (Bawaan Sendiri)
        sliders_frame = tk.Frame(card, bg=CARD)
        sliders_frame.pack(fill="x", pady=(6, 2))

        # Bass Boost slider
        self._bass_scale = self._make_audio_slider(sliders_frame, "🔊 Bass Boost", 60)
        # Clarity / Footsteps slider
        self._clarity_scale = self._make_audio_slider(sliders_frame, "🎯 Clarity / Step", 80)
        # Surround Sound slider
        self._surround_scale = self._make_audio_slider(sliders_frame, "🌐 Surround 3D", 70)

        # FxSound routing power toggle
        fx_row = tk.Frame(card, bg=CARD)
        fx_row.pack(fill="x", pady=(6, 2))
        tk.Label(fx_row, text="FxSound Link", font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=12, anchor="w").pack(side="left")
        self._fx_var = tk.BooleanVar(value=True)
        fx_cb = tk.Checkbutton(fx_row, variable=self._fx_var,
                                bg=CARD, fg=TEXT, selectcolor=CARD,
                                activebackground=CARD,
                                command=self._on_fxsound_toggle)
        fx_cb.pack(side="left")
        self._fx_lbl = tk.Label(fx_row, text="Active (Kumo Headset)",
                                 font=("Segoe UI", 8, "bold"),
                                 fg=GREEN, bg=CARD)
        self._fx_lbl.pack(side="left")

        self._spacer(card, 2)

    def _make_audio_slider(self, parent, label_text: str, default_val: int) -> tk.Scale:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label_text, font=("Segoe UI", 8),
                 fg=DIM, bg=CARD, width=14, anchor="w").pack(side="left")
        var = tk.IntVar(value=default_val)
        val_lbl = tk.Label(row, text=f"{default_val}%", font=("Segoe UI", 8, "bold"),
                           fg=TEXT, bg=CARD, width=5)
        scale = tk.Scale(row, from_=0, to=100, orient="horizontal",
                         variable=var,
                         command=lambda v: val_lbl.configure(text=f"{int(float(v))}%"),
                         bg=CARD, fg=TEXT, troughcolor=BORDER,
                         highlightthickness=0, length=140, showvalue=False)
        scale.pack(side="left")
        val_lbl.pack(side="left", padx=2)
        return scale

    def _on_eq_profile(self, profile_key: str, fx_preset: str = "") -> None:
        for key, btn in self._eq_buttons.items():
            btn.configure(fg=ACCENT if key == profile_key else DIM,
                          bg=BORDER)
        if profile_key in self._eq_buttons:
            self._eq_buttons[profile_key].configure(fg=TEXT, bg=ACCENT)

        # Adjust sliders based on preset
        if profile_key == "fps_step_booster":
            self._bass_scale.set(40)
            self._clarity_scale.set(95)
            self._surround_scale.set(85)
        elif profile_key == "music_movie":
            self._bass_scale.set(70)
            self._clarity_scale.set(75)
            self._surround_scale.set(60)
        elif profile_key == "bass_boost":
            self._bass_scale.set(95)
            self._clarity_scale.set(60)
            self._surround_scale.set(50)
        elif profile_key == "gaming_surround":
            self._bass_scale.set(65)
            self._clarity_scale.set(85)
            self._surround_scale.set(95)

        def _apply():
            if self._eq_apo:
                try:
                    self._eq_apo.apply_profile(profile_key)
                except Exception:
                    pass
            if self._fxsound and fx_preset:
                try:
                    self._fxsound.set_output_device(
                        "Speakers (dbE Kumo GS1X Pro)",
                        "{0.0.0.00000000}.{ba396042-5266-4b0e-8bcf-893742e1a503}"
                    )
                    self._fxsound.set_power(True)
                    self._fxsound.set_preset(fx_preset)
                except Exception:
                    pass

        threading.Thread(target=_apply, daemon=True, name="audio-apply").start()

    def _on_fxsound_toggle(self) -> None:
        enabled = self._fx_var.get()
        self._fx_lbl.configure(
            text="Active (Kumo Headset)" if enabled else "Bypassed",
            fg=GREEN if enabled else DIM
        )
        if self._fxsound:
            threading.Thread(target=self._fxsound.set_power, args=(enabled,),
                             daemon=True, name="fx-power").start()

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _build_footer(self) -> None:
        footer = tk.Frame(self._root, bg=CARD, pady=6)
        footer.pack(fill="x", side="bottom")

        self._footer_status = tk.Label(footer, text="Peripheral Hub v1.0.0",
                                       font=("Segoe UI", 8), fg=DIM, bg=CARD)
        self._footer_status.pack(side="left", padx=12)

        self._footer_dot = tk.Label(footer, text="● Active",
                                    font=("Segoe UI", 8, "bold"), fg=GREEN, bg=CARD)
        self._footer_dot.pack(side="right", padx=12)

    # ------------------------------------------------------------------
    # Active Scan All
    # ------------------------------------------------------------------

    def scan_all(self) -> None:
        self._scan_btn.configure(text="⏳ Memindai...", fg=ORANGE)
        self._footer_status.configure(text="Memindai perangkat yang tercolok...", fg=ORANGE)

        def _do_scan():
            count = 0
            if self._mouse:
                try:
                    if self._mouse.scan_and_connect():
                        count += 1
                except Exception:
                    pass
            if self._keyboard:
                try:
                    if self._keyboard.scan_and_connect():
                        count += 1
                except Exception:
                    pass
            if self._headset:
                try:
                    if self._headset.scan_and_connect():
                        count += 1
                except Exception:
                    pass

            if self._on_scan:
                try:
                    self._on_scan()
                except Exception:
                    pass

            if self._root:
                try:
                    self._root.after(0, lambda: self._on_scan_done(count))
                except Exception:
                    pass

        threading.Thread(target=_do_scan, daemon=True, name="manual-scan").start()

    def _on_scan_done(self, found_count: int) -> None:
        self._refresh()
        self._scan_btn.configure(text="✓ Selesai", fg=GREEN)
        self._footer_status.configure(text=f"{found_count} Perangkat Terdeteksi", fg=GREEN)
        self._root.after(2000, lambda: self._scan_btn.configure(text="🔄 Pindai", fg=ACCENT) if self._root else None)
        self._root.after(3000, lambda: self._footer_status.configure(text="Peripheral Hub v1.0.0", fg=DIM) if self._root else None)

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            self._refresh_mouse()
        except Exception:
            pass
        try:
            self._refresh_keyboard()
        except Exception:
            pass
        try:
            self._refresh_headset()
        except Exception:
            pass
        try:
            self._refresh_audio()
        except Exception:
            pass

        if self._visible and self._root:
            self._refresh_job = self._root.after(REFRESH_INTERVAL, self._refresh)

    def _refresh_mouse(self) -> None:
        if self._mouse is None:
            return
        st = self._mouse.get_status()
        online = st.get("online", False)
        conn_type = st.get("connection_type", "Disconnected")
        pct = st.get("battery_level")
        charging = st.get("is_charging", False)
        dpi = st.get("current_dpi", 1200)

        color = GREEN if online else RED
        status_text = f"● Connected ({conn_type})" if online else "● Disconnected"
        self._mouse_status_lbl.configure(text=status_text, fg=color)
        self._mouse_charging_lbl.configure(text="⚡ Charging" if charging else "")

        if pct is not None:
            self._mouse_bat_bar.set_value(pct)
            self._mouse_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))
        if dpi is not None:
            self._mouse_dpi_lbl.configure(text=f"{dpi} DPI")
            for d, btn in self._dpi_buttons.items():
                btn.set_active(d == dpi)

    def _refresh_keyboard(self) -> None:
        if self._keyboard is None:
            return
        st = self._keyboard.get_status()
        connected = st.get("connected", False)
        conn_type = st.get("connection_type", "Disconnected")
        color = GREEN if connected else RED
        status_text = f"● Connected ({conn_type})" if connected else "● Disconnected"
        self._kb_status_lbl.configure(text=status_text, fg=color)

        lm_name = st.get("light_mode_name", "Colourful")
        if self._kb_light_var.get() != lm_name:
            self._kb_light_var.set(lm_name)

        br = st.get("brightness", 5)
        if self._kb_br_var.get() != br:
            self._kb_br_var.set(br)
            self._kb_br_lbl.configure(text=f"Level {br}")

        sp = st.get("speed", 3)
        if self._kb_sp_var.get() != sp:
            self._kb_sp_var.set(sp)
            self._kb_sp_lbl.configure(text=f"Speed {sp}")

    def _refresh_headset(self) -> None:
        if self._headset is None:
            return
        st = self._headset.get_status()
        dongle = st.get("dongle_connected", False)
        conn_type = st.get("connection_type", "Disconnected")
        status_text = f"● Connected ({conn_type})" if dongle else "● Dongle Not Detected"
        self._hs_status_lbl.configure(text=status_text, fg=GREEN if dongle else RED)

        pct = st.get("battery_estimate", 0)
        self._hs_bat_bar.set_value(pct)
        self._hs_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))
        self._hs_usage_lbl.configure(text=f"Usage: {st.get('usage_time', '0h 00m')}")

        vol = st.get("volume", 50)
        self._hs_vol_var.set(vol)
        self._hs_vol_lbl.configure(text=f"{vol}%")

    def _refresh_audio(self) -> None:
        if self._fxsound:
            power = self._fxsound.get_power()
            self._fx_var.set(power)
            self._fx_lbl.configure(text="Active (Kumo Headset)" if power else "Bypassed",
                                    fg=GREEN if power else DIM)

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------

    def show(self) -> None:
        if self._root is None:
            return
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._visible = True
        self._refresh()

    def hide(self) -> None:
        if self._root is None:
            return
        self._root.withdraw()
        self._visible = False
        if self._refresh_job:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self._on_close:
            self._on_close()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def is_visible(self) -> bool:
        return self._visible

    def destroy(self) -> None:
        self.hide()
        if self._root:
            try:
                self._root.destroy()
            except tk.TclError:
                pass
            self._root = None
