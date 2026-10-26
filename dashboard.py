"""
dashboard.py
Peripheral Hub - Modern Universal Gaming Peripheral Controller.
Inspired by CustomRP (native Windows desktop window with menu & status bar)
and Coucou (sleek pill navigation tabs, smooth rounded cards, and clean telemetry).

Features:
- Free-floating draggable Windows desktop window with native Dark Mode title bar.
- Clean Menu Bar: File, Devices, Audio, Help.
- Coucou-style pill tab navigation: Mouse, Keyboard, Headset, Audio.
- Dedicated Mouse Noir M1 Nex customizer: button remapping, macros, RGB lighting, DPI, battery mV/%.
- Keyboard AULA S75 Pro: 20 lighting modes, custom RGB palette, Brightness (1-5), Speed (1-5).
- Headset dbE Kumo GS1X Pro: Smart battery tracker, Windows master volume.
- Audio Enhancer: Gaming FPS Step Booster, Music, Bass, Cinematic, and Flat profiles.
- Native Win32 status bar at bottom.
- Window remembers last moved position on screen.
"""

import ctypes
from ctypes import byref, c_int, sizeof
import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List

logger = logging.getLogger(__name__)

# UI Color Palette (Deep Obsidian / Dark Glass aesthetic)
BG           = "#141416"
CARD         = "#1c1c20"
CARD_HOVER   = "#24242a"
BORDER       = "#2c2c34"
BORDER_LIGHT = "#3c3c46"
ACCENT       = "#e26332"
ACCENT_HOVER = "#f27342"
TEXT         = "#ffffff"
TEXT_MUTED   = "#a0a0a8"
DIM          = "#666670"
GREEN        = "#4caf50"
ORANGE       = "#ff9800"
RED          = "#f44336"
BLUE         = "#3b82f6"

WIN_W = 500
WIN_H = 680
CONFIG_PATH = Path(__file__).parent / "config.json"


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


class _BatteryBar(tk.Canvas):
    """Modern horizontal battery bar widget with rounded corners and cell nub."""
    def __init__(self, parent, width=160, height=14, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._bar_w = width
        self._bar_h = height
        self._draw(0, DIM)

    def set_value(self, pct: Optional[int]) -> None:
        if pct is None:
            self._draw(0, DIM)
        else:
            self._draw(pct, _battery_color(pct))

    def _draw(self, pct: int, color: str) -> None:
        self.delete("all")
        # Background bar
        self.create_rectangle(0, 0, self._bar_w - 6, self._bar_h - 1,
                              outline=BORDER, fill=BG, width=1)
        # Positive terminal nub
        self.create_rectangle(self._bar_w - 5, (self._bar_h - 6) // 2,
                              self._bar_w - 1, (self._bar_h + 6) // 2,
                              fill=BORDER, outline="")
        fill_w = int((self._bar_w - 8) * max(0, min(100, pct)) / 100)
        if fill_w > 0:
            self.create_rectangle(1, 1, fill_w, self._bar_h - 2,
                                  fill=color, outline="")


class _PillTabButton(tk.Label):
    """Coucou-style pill tab button with smooth hover state."""
    def __init__(self, parent, text: str, icon: str, tab_id: str, on_select: Callable, **kwargs):
        self.tab_id = tab_id
        self.on_select = on_select
        self._is_active = False
        super().__init__(parent, text=f"{icon} {text}", font=("Segoe UI", 9, "bold"),
                         fg=TEXT_MUTED, bg=BORDER, cursor="hand2", padx=12, pady=6,
                         relief="flat", **kwargs)
        self.bind("<Button-1>", lambda e: self.on_select(self.tab_id))
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set_active(self, active: bool) -> None:
        self._is_active = active
        if active:
            self.configure(fg=TEXT, bg=ACCENT)
        else:
            self.configure(fg=TEXT_MUTED, bg=BORDER)

    def _on_enter(self, e):
        if not self._is_active:
            self.configure(bg=CARD_HOVER, fg=TEXT)

    def _on_leave(self, e):
        if not self._is_active:
            self.configure(bg=BORDER, fg=TEXT_MUTED)


class _DpiPill(tk.Label):
    """Compact selectable DPI pill."""
    def __init__(self, parent, dpi: int, on_click: Callable, **kwargs):
        super().__init__(parent,
                         text=str(dpi) if dpi < 1000 else f"{dpi//1000}K",
                         font=("Segoe UI", 8),
                         fg=DIM, bg=BORDER,
                         padx=8, pady=4,
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
    Peripheral Hub main desktop application window.
    Features:
    - Freely draggable native window with Windows 10/11 Dark Title Bar.
    - Pill Tab navigation for Mouse, Keyboard, Headset, and Audio.
    - Full customizer suite for Noir M1 Nex, AULA S75 Pro, and dbE Kumo.
    - Status bar with connected device counts and battery summary.
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
        self._current_tab = "mouse"

        # Tab buttons & pages
        self._tab_buttons: Dict[str, _PillTabButton] = {}
        self._tab_pages: Dict[str, tk.Frame] = {}

        # Mouse controls
        self._dpi_buttons: Dict[int, _DpiPill] = {}
        self._eq_buttons: Dict[str, tk.Label] = {}

        self._build()

    # ------------------------------------------------------------------
    # Window lifecycle & positioning
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = tk.Toplevel()
        self._root = root
        root.title("Peripheral Hub")
        root.configure(bg=BG)
        root.resizable(False, False)

        # Variables initialized after root exists
        self._mouse_macro_var = tk.StringVar(root, value="Default (Browser Back)")
        self._mouse_btn4_var = tk.StringVar(root, value="Browser Forward")
        self._mouse_btn5_var = tk.StringVar(root, value="Browser Backward")
        self._mouse_rgb_mode_var = tk.StringVar(root, value="Neon Cycle")

        # Keyboard controls
        self._kb_light_var = tk.StringVar(root, value="Colourful")
        self._kb_br_var = tk.IntVar(root, value=5)
        self._kb_sp_var = tk.IntVar(root, value=3)

        # Headset controls
        self._hs_vol_var = tk.IntVar(root, value=50)

        # Audio Enhancer controls
        self._audio_preset_var = tk.StringVar(root, value="FPS Step Booster")
        self._audio_bass_var = tk.IntVar(root, value=60)
        self._audio_clarity_var = tk.IntVar(root, value=80)
        self._audio_surround_var = tk.IntVar(root, value=70)

        # Load saved position or center on primary screen
        pos_x, pos_y = self._load_window_pos()
        if pos_x is None or pos_y is None:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            pos_x = max(50, (sw - WIN_W) // 2)
            pos_y = max(50, (sh - WIN_H) // 2)

        root.geometry(f"{WIN_W}x{WIN_H}+{pos_x}+{pos_y}")

        # Bind window drag / move events to remember position
        root.bind("<Configure>", self._on_window_configure)

        # Enable Windows 10/11 Immersive Dark Mode for Title Bar
        root.after(10, self._apply_windows_dark_titlebar)

        # Native protocol for close button (hides to tray)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        # Build UI layout
        self._build_menu_bar()
        self._build_top_header()
        self._build_pill_tabs()
        self._build_pages_container()
        self._build_bottom_status_bar()

        # Select initial tab
        self.select_tab("mouse")

        # Initially hidden until tray icon or user opens it
        root.withdraw()

    def _apply_windows_dark_titlebar(self) -> None:
        """Call DwmSetWindowAttribute to make the native Windows titlebar dark."""
        if not self._root:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self._root.winfo_id())
            if not hwnd:
                hwnd = self._root.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            val = c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(val), sizeof(val)
            )
        except Exception as e:
            logger.debug("Dark title bar hook error: %s", e)

    def _load_window_pos(self) -> Tuple[Optional[int], Optional[int]]:
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    pos = cfg.get("window_pos")
                    if pos and isinstance(pos, list) and len(pos) == 2:
                        return int(pos[0]), int(pos[1])
        except Exception:
            pass
        return None, None

    def _save_window_pos(self, x: int, y: int) -> None:
        try:
            cfg = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["window_pos"] = [x, y]
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _on_window_configure(self, event=None) -> None:
        if self._root and self._visible and event and event.widget == self._root:
            x = self._root.winfo_x()
            y = self._root.winfo_y()
            if x > 0 and y > 0:
                self._save_window_pos(x, y)

    # ------------------------------------------------------------------
    # Menu Bar (CustomRP inspired)
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        menubar = tk.Menu(self._root, bg=BG, fg=TEXT, activebackground=ACCENT,
                          activeforeground=TEXT, relief="flat", bd=0)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=CARD, fg=TEXT,
                            activebackground=ACCENT, activeforeground=TEXT)
        file_menu.add_command(label="🔄 Scan Devices", command=self.scan_all)
        file_menu.add_command(label="− Minimize to Tray", command=self.hide)
        file_menu.add_separator()
        file_menu.add_command(label="✕ Exit Application", command=self._on_full_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Devices menu
        dev_menu = tk.Menu(menubar, tearoff=0, bg=CARD, fg=TEXT,
                           activebackground=ACCENT, activeforeground=TEXT)
        dev_menu.add_command(label="🖱️ Noir M1 Nex", command=lambda: self.select_tab("mouse"))
        dev_menu.add_command(label="⌨️ AULA S75 Pro", command=lambda: self.select_tab("keyboard"))
        dev_menu.add_command(label="🎧 dbE Kumo GS1X Pro", command=lambda: self.select_tab("headset"))
        dev_menu.add_separator()
        dev_menu.add_command(label="🔄 Re-detect All", command=self.scan_all)
        menubar.add_cascade(label="Devices", menu=dev_menu)

        # Audio menu
        audio_menu = tk.Menu(menubar, tearoff=0, bg=CARD, fg=TEXT,
                            activebackground=ACCENT, activeforeground=TEXT)
        audio_menu.add_command(label="🎯 FPS Step Booster", command=lambda: self._set_audio_preset("FPS Step Booster"))
        audio_menu.add_command(label="🎵 Music / Vocal", command=lambda: self._set_audio_preset("Music / Vocal"))
        audio_menu.add_command(label="💥 Bass Boost", command=lambda: self._set_audio_preset("Bass Boost"))
        audio_menu.add_command(label="🎬 Cinematic", command=lambda: self._set_audio_preset("Cinematic"))
        audio_menu.add_command(label="⚖️ Flat / Neutral", command=lambda: self._set_audio_preset("Flat / Neutral"))
        menubar.add_cascade(label="Audio", menu=audio_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=CARD, fg=TEXT,
                            activebackground=ACCENT, activeforeground=TEXT)
        help_menu.add_command(label="About Peripheral Hub", command=self._show_about)
        help_menu.add_command(label="GitHub Repository", command=self._open_github)
        menubar.add_cascade(label="Help", menu=help_menu)

        self._root.config(menu=menubar)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About Peripheral Hub",
            "Peripheral Hub v1.2.0\n\n"
            "An ultra-lightweight universal gaming peripheral controller for Windows.\n"
            "Supports Noir M1 Nex, AULA S75 Pro, dbE Kumo GS1X Pro, and Gaming Audio DSP.\n\n"
            "Created by Andrejayas."
        )

    def _open_github(self) -> None:
        import webbrowser
        webbrowser.open("https://github.com/Andrejayas/Peripheral-Hub")

    def _on_full_exit(self) -> None:
        if self._on_close:
            self._on_close()
        self._root.quit()

    # ------------------------------------------------------------------
    # Top Header & Coucou Pill Tabs
    # ------------------------------------------------------------------

    def _build_top_header(self) -> None:
        hdr_frame = tk.Frame(self._root, bg=BG, padx=16, pady=12)
        hdr_frame.pack(fill="x")

        # App Brand & Status Dot
        brand_frame = tk.Frame(hdr_frame, bg=BG)
        brand_frame.pack(side="left")

        self._brand_dot = tk.Label(brand_frame, text="●", font=("Segoe UI", 12),
                                   fg=GREEN, bg=BG)
        self._brand_dot.pack(side="left", padx=(0, 6))

        tk.Label(brand_frame, text="Peripheral Hub", font=("Segoe UI", 13, "bold"),
                 fg=TEXT, bg=BG).pack(side="left")

        # Scan Button (Quick Pill)
        self._scan_btn = tk.Label(hdr_frame, text="🔄 Scan", font=("Segoe UI", 9, "bold"),
                                  fg=ACCENT, bg=CARD, cursor="hand2", padx=10, pady=4)
        self._scan_btn.pack(side="right")
        self._scan_btn.bind("<Button-1>", lambda e: self.scan_all())
        self._scan_btn.bind("<Enter>", lambda e: self._scan_btn.configure(bg=BORDER, fg=TEXT))
        self._scan_btn.bind("<Leave>", lambda e: self._scan_btn.configure(bg=CARD, fg=ACCENT))

    def _build_pill_tabs(self) -> None:
        """Coucou-style navigation tab bar across top of content area."""
        tabs_container = tk.Frame(self._root, bg=BG, padx=14, pady=2)
        tabs_container.pack(fill="x")

        tab_bar = tk.Frame(tabs_container, bg=CARD, padx=4, pady=4)
        tab_bar.pack(fill="x")

        tabs = [
            ("mouse",    "Mouse",    "🖱️"),
            ("keyboard", "Keyboard", "⌨️"),
            ("headset",  "Headset",  "🎧"),
            ("audio",    "Audio",    "🔊"),
        ]

        for tab_id, name, icon in tabs:
            btn = _PillTabButton(tab_bar, name, icon, tab_id, self.select_tab)
            btn.pack(side="left", expand=True, fill="x", padx=3)
            self._tab_buttons[tab_id] = btn

    def select_tab(self, tab_id: str) -> None:
        """Switch active tab page smoothly."""
        self._current_tab = tab_id
        for tid, btn in self._tab_buttons.items():
            btn.set_active(tid == tab_id)

        for tid, page in self._tab_pages.items():
            if tid == tab_id:
                page.pack(fill="both", expand=True, padx=14, pady=10)
            else:
                page.pack_forget()

    # ------------------------------------------------------------------
    # Pages Container
    # ------------------------------------------------------------------

    def _build_pages_container(self) -> None:
        self._content_area = tk.Frame(self._root, bg=BG)
        self._content_area.pack(fill="both", expand=True)

        self._build_mouse_page()
        self._build_keyboard_page()
        self._build_headset_page()
        self._build_audio_page()

    # ------------------------------------------------------------------
    # Page 1: 🖱️ Noir M1 Nex (Dedicated Mouse Customizer)
    # ------------------------------------------------------------------

    def _build_mouse_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["mouse"] = page

        # 1. Device Status Card
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_stat.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(card_stat, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="🖱️ Noir M1 Nex", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._mouse_status_lbl = tk.Label(row1, text="● Disconnected",
                                          font=("Segoe UI", 9, "bold"),
                                          fg=RED, bg=CARD)
        self._mouse_status_lbl.pack(side="right")

        # Battery Row
        bat_row = tk.Frame(card_stat, bg=CARD)
        bat_row.pack(fill="x", pady=(8, 2))
        tk.Label(bat_row, text="Battery", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=10, anchor="w").pack(side="left")
        self._mouse_bat_bar = _BatteryBar(bat_row, width=170)
        self._mouse_bat_bar.pack(side="left", padx=6)
        self._mouse_bat_lbl = tk.Label(bat_row, text="N/A",
                                       font=("Segoe UI", 8, "bold"),
                                       fg=TEXT, bg=CARD)
        self._mouse_bat_lbl.pack(side="left")
        self._mouse_volt_lbl = tk.Label(bat_row, text="", font=("Segoe UI", 8),
                                        fg=DIM, bg=CARD)
        self._mouse_volt_lbl.pack(side="left", padx=6)

        # 2. DPI Stage Selector Card
        card_dpi = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_dpi.pack(fill="x", pady=4)

        dpi_head = tk.Frame(card_dpi, bg=CARD)
        dpi_head.pack(fill="x")
        tk.Label(dpi_head, text="DPI Sensitivity", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")
        self._mouse_dpi_val_lbl = tk.Label(dpi_head, text="1200 DPI",
                                           font=("Segoe UI", 9, "bold"),
                                           fg=TEXT, bg=CARD)
        self._mouse_dpi_val_lbl.pack(side="right")

        pills_row = tk.Frame(card_dpi, bg=CARD)
        pills_row.pack(fill="x", pady=(8, 4))
        for dpi in [400, 800, 1200, 2400, 3200, 5000, 10000]:
            btn = _DpiPill(pills_row, dpi, self._on_dpi_click)
            btn.pack(side="left", expand=True, fill="x", padx=2)
            self._dpi_buttons[dpi] = btn

        # 3. Dedicated Noir Button Remapping & Macro Section
        card_btns = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_btns.pack(fill="x", pady=4)

        tk.Label(card_btns, text="Button Mapping & Macro (Posisi Tombol)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        btn_grid = tk.Frame(card_btns, bg=CARD)
        btn_grid.pack(fill="x", pady=(6, 2))

        # Button 4 (Forward)
        b4_row = tk.Frame(btn_grid, bg=CARD)
        b4_row.pack(fill="x", pady=2)
        tk.Label(b4_row, text="Button 4 (Forward)", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=18, anchor="w").pack(side="left")
        b4_opts = ["Browser Forward", "Double Click", "Quick Fire (Macro)", "Volume Up", "Mute"]
        b4_menu = ttk.Combobox(b4_row, textvariable=self._mouse_btn4_var,
                               values=b4_opts, width=20, state="readonly")
        b4_menu.pack(side="left", padx=4)

        # Button 5 (Backward)
        b5_row = tk.Frame(btn_grid, bg=CARD)
        b5_row.pack(fill="x", pady=2)
        tk.Label(b5_row, text="Button 5 (Backward)", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=18, anchor="w").pack(side="left")
        b5_opts = ["Browser Backward", "Crouch Jump (Macro)", "Volume Down", "Play/Pause", "Sniper 400 DPI"]
        b5_menu = ttk.Combobox(b5_row, textvariable=self._mouse_btn5_var,
                               values=b5_opts, width=20, state="readonly")
        b5_menu.pack(side="left", padx=4)

        # 4. Mouse RGB Lighting Card
        card_rgb = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_rgb.pack(fill="x", pady=4)

        rgb_head = tk.Frame(card_rgb, bg=CARD)
        rgb_head.pack(fill="x")
        tk.Label(rgb_head, text="Mouse LED Effect", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")

        m_rgb_modes = ["Neon Cycle", "Breathing", "Static", "LED Off"]
        m_rgb_menu = ttk.Combobox(rgb_head, textvariable=self._mouse_rgb_mode_var,
                                  values=m_rgb_modes, width=14, state="readonly")
        m_rgb_menu.pack(side="right")

        # Color dots
        dots_row = tk.Frame(card_rgb, bg=CARD)
        dots_row.pack(fill="x", pady=(6, 2))
        tk.Label(dots_row, text="Preset Color", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")

        colors = [
            ("#ff2a2a", "Red"),
            ("#00ff44", "Green"),
            ("#2266ff", "Blue"),
            ("#00eeff", "Cyan"),
            ("#aa22ff", "Purple"),
            ("#ff8800", "Orange"),
            ("#ffffff", "White"),
        ]
        for hex_code, name in colors:
            dot = tk.Label(dots_row, text="●", font=("Segoe UI", 12, "bold"),
                           fg=hex_code, bg=CARD, cursor="hand2", padx=3)
            dot.pack(side="left")
            dot.bind("<Button-1>", lambda e, c=hex_code: self._on_mouse_color(c))

    def _on_dpi_click(self, dpi: int) -> None:
        if self._mouse:
            threading.Thread(target=self._mouse.set_dpi, args=(dpi,),
                             daemon=True, name="dpi-set").start()
        for d, btn in self._dpi_buttons.items():
            btn.set_active(d == dpi)
        self._mouse_dpi_val_lbl.configure(text=f"{dpi} DPI")

    def _on_mouse_color(self, hex_code: str) -> None:
        logger.info("Mouse custom color selected: %s", hex_code)

    # ------------------------------------------------------------------
    # Page 2: ⌨️ AULA S75 Pro (Mechanical Keyboard)
    # ------------------------------------------------------------------

    def _build_keyboard_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["keyboard"] = page

        # 1. Device Status Card
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_stat.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(card_stat, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="⌨️ AULA S75 Pro", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._kb_status_lbl = tk.Label(row1, text="● Disconnected",
                                       font=("Segoe UI", 9, "bold"),
                                       fg=RED, bg=CARD)
        self._kb_status_lbl.pack(side="right")

        # 2. Lighting Mode Selector
        card_lm = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_lm.pack(fill="x", pady=4)

        from devices.keyboard import LIGHT_MODE_NAMES
        lm_row = tk.Frame(card_lm, bg=CARD)
        lm_row.pack(fill="x")
        tk.Label(lm_row, text="Lighting Mode (20 Efek)", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")

        self._kb_light_menu = ttk.Combobox(lm_row, textvariable=self._kb_light_var,
                                           values=LIGHT_MODE_NAMES, width=18,
                                           state="readonly")
        self._kb_light_menu.pack(side="right")
        self._kb_light_menu.bind("<<ComboboxSelected>>", self._on_kb_light_mode_change)

        # 3. Custom Color Palette Card
        card_col = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_col.pack(fill="x", pady=4)

        tk.Label(card_col, text="Custom RGB Palette", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(anchor="w")

        from devices.keyboard import COLOR_PRESETS
        pal_row = tk.Frame(card_col, bg=CARD)
        pal_row.pack(fill="x", pady=(8, 2))

        for name, hex_code, (r, g, b) in COLOR_PRESETS:
            is_rain = (name == "Rainbow")
            cbtn = tk.Label(pal_row,
                            text="🌈" if is_rain else "●",
                            font=("Segoe UI", 13 if not is_rain else 11, "bold"),
                            fg=ACCENT if is_rain else hex_code,
                            bg=CARD, cursor="hand2", padx=4)
            cbtn.pack(side="left")
            cbtn.bind("<Button-1>", lambda e, red=r, green=g, blue=b, rain=is_rain: self._on_kb_color_click(red, green, blue, rain))

        # 4. Brightness & Speed Sliders Card (Hardware Control)
        card_tune = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_tune.pack(fill="x", pady=4)

        tk.Label(card_tune, text="Hardware Sliders (Sonix ACK Handshake)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        # Brightness row
        br_row = tk.Frame(card_tune, bg=CARD)
        br_row.pack(fill="x", pady=(8, 4))
        tk.Label(br_row, text="Brightness", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._kb_br_slider = tk.Scale(br_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_br_var,
                                      command=self._on_kb_brightness_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=200, showvalue=False)
        self._kb_br_slider.pack(side="left")
        self._kb_br_lbl = tk.Label(br_row, text="Level 5", font=("Segoe UI", 8, "bold"),
                                   fg=TEXT, bg=CARD)
        self._kb_br_lbl.pack(side="left", padx=8)

        # Speed row
        sp_row = tk.Frame(card_tune, bg=CARD)
        sp_row.pack(fill="x", pady=(4, 2))
        tk.Label(sp_row, text="Speed", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._kb_sp_slider = tk.Scale(sp_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_sp_var,
                                      command=self._on_kb_speed_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=200, showvalue=False)
        self._kb_sp_slider.pack(side="left")
        self._kb_sp_lbl = tk.Label(sp_row, text="Speed 3", font=("Segoe UI", 8, "bold"),
                                   fg=TEXT, bg=CARD)
        self._kb_sp_lbl.pack(side="left", padx=8)

    def _on_kb_light_mode_change(self, event=None) -> None:
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
    # Page 3: 🎧 dbE Kumo GS1X Pro (Wireless Headset)
    # ------------------------------------------------------------------

    def _build_headset_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["headset"] = page

        # 1. Device Status Card
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_stat.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(card_stat, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="🎧 dbE Kumo GS1X Pro", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._hs_status_lbl = tk.Label(row1, text="● Dongle Not Detected",
                                       font=("Segoe UI", 9, "bold"),
                                       fg=RED, bg=CARD)
        self._hs_status_lbl.pack(side="right")

        # Smart Battery Tracker Card
        card_bat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_bat.pack(fill="x", pady=4)

        tk.Label(card_bat, text="Smart Battery Tracker (16h Active Life)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        bat_row = tk.Frame(card_bat, bg=CARD)
        bat_row.pack(fill="x", pady=(8, 4))
        tk.Label(bat_row, text="Est. Battery", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._hs_bat_bar = _BatteryBar(bat_row, width=170)
        self._hs_bat_bar.pack(side="left", padx=6)
        self._hs_bat_lbl = tk.Label(bat_row, text="N/A", font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._hs_bat_lbl.pack(side="left")

        btn_row = tk.Frame(card_bat, bg=CARD)
        btn_row.pack(fill="x", pady=(6, 2))
        self._hs_usage_lbl = tk.Label(btn_row, text="Usage: 0h 00m", font=("Segoe UI", 8),
                                      fg=TEXT_MUTED, bg=CARD)
        self._hs_usage_lbl.pack(side="left")

        charged_btn = tk.Label(btn_row, text="⚡ Mark Charged", font=("Segoe UI", 8, "bold"),
                               fg=TEXT, bg=BORDER, cursor="hand2", padx=8, pady=3)
        charged_btn.pack(side="right")
        charged_btn.bind("<Button-1>", lambda e: self._on_mark_charged())
        charged_btn.bind("<Enter>", lambda e: charged_btn.configure(bg=CARD_HOVER, fg=ACCENT))
        charged_btn.bind("<Leave>", lambda e: charged_btn.configure(bg=BORDER, fg=TEXT))

        # Windows Master Volume Card
        card_vol = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_vol.pack(fill="x", pady=4)

        tk.Label(card_vol, text="Windows Master Audio Volume",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        vol_row = tk.Frame(card_vol, bg=CARD)
        vol_row.pack(fill="x", pady=(8, 2))
        tk.Label(vol_row, text="Master Vol", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._hs_vol_slider = tk.Scale(vol_row, from_=0, to=100, orient="horizontal",
                                       variable=self._hs_vol_var,
                                       command=self._on_volume_change,
                                       bg=CARD, fg=TEXT, troughcolor=BORDER,
                                       highlightthickness=0, length=200, showvalue=False)
        self._hs_vol_slider.pack(side="left")
        self._hs_vol_lbl = tk.Label(vol_row, text="50%", font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._hs_vol_lbl.pack(side="left", padx=8)

    def _on_volume_change(self, val) -> None:
        vol = int(float(val))
        self._hs_vol_lbl.configure(text=f"{vol}%")
        if self._headset:
            threading.Thread(target=self._headset.set_volume, args=(vol,),
                             daemon=True, name="hs-vol").start()

    def _on_mark_charged(self) -> None:
        if self._headset:
            self._headset.mark_charged()
            self._refresh_headset()

    # ------------------------------------------------------------------
    # Page 4: 🔊 Real Sound Enhancer & Equalizer
    # ------------------------------------------------------------------

    def _build_audio_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["audio"] = page

        # 1. Preset Header Card
        card_preset = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_preset.pack(fill="x", pady=(0, 8))

        tk.Label(card_preset, text="Real Sound Enhancer & Gaming EQ",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        # 5 Quick Preset Buttons
        p_row1 = tk.Frame(card_preset, bg=CARD)
        p_row1.pack(fill="x", pady=(8, 4))
        p_row2 = tk.Frame(card_preset, bg=CARD)
        p_row2.pack(fill="x", pady=2)

        presets1 = [
            ("FPS Step Booster", "🎯 FPS Footstep"),
            ("Gaming Surround", "🎮 Surround 3D"),
        ]
        presets2 = [
            ("Music / Vocal", "🎵 Music/Vocal"),
            ("Bass Boost", "💥 Bass Boost"),
            ("Flat / Neutral", "⚖️ Flat"),
        ]

        for key, label in presets1:
            lbl = tk.Label(p_row1, text=label, font=("Segoe UI", 9, "bold"),
                           fg=TEXT, bg=BORDER, cursor="hand2", padx=10, pady=6)
            lbl.pack(side="left", expand=True, fill="x", padx=3)
            lbl.bind("<Button-1>", lambda e, k=key: self._set_audio_preset(k))
            self._eq_buttons[key] = lbl

        for key, label in presets2:
            lbl = tk.Label(p_row2, text=label, font=("Segoe UI", 9, "bold"),
                           fg=TEXT_MUTED, bg=BORDER, cursor="hand2", padx=8, pady=6)
            lbl.pack(side="left", expand=True, fill="x", padx=3)
            lbl.bind("<Button-1>", lambda e, k=key: self._set_audio_preset(k))
            self._eq_buttons[key] = lbl

        # 2. Parametric Audio Sliders Card
        card_sliders = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_sliders.pack(fill="x", pady=4)

        tk.Label(card_sliders, text="Dynamic Frequency Shaping",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        # Bass Boost slider
        s1 = tk.Frame(card_sliders, bg=CARD)
        s1.pack(fill="x", pady=(8, 4))
        tk.Label(s1, text="Bass Boost", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=16, anchor="w").pack(side="left")
        self._bass_slider = tk.Scale(s1, from_=0, to=100, orient="horizontal",
                                     variable=self._audio_bass_var,
                                     bg=CARD, fg=TEXT, troughcolor=BORDER,
                                     highlightthickness=0, length=180, showvalue=False)
        self._bass_slider.pack(side="left")
        self._bass_lbl = tk.Label(s1, text="60%", font=("Segoe UI", 8, "bold"),
                                  fg=TEXT, bg=CARD)
        self._bass_lbl.pack(side="left", padx=8)

        # Footstep Clarity slider
        s2 = tk.Frame(card_sliders, bg=CARD)
        s2.pack(fill="x", pady=4)
        tk.Label(s2, text="Footstep Clarity", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=16, anchor="w").pack(side="left")
        self._clarity_slider = tk.Scale(s2, from_=0, to=100, orient="horizontal",
                                        variable=self._audio_clarity_var,
                                        bg=CARD, fg=TEXT, troughcolor=BORDER,
                                        highlightthickness=0, length=180, showvalue=False)
        self._clarity_slider.pack(side="left")
        self._clarity_lbl = tk.Label(s2, text="80%", font=("Segoe UI", 8, "bold"),
                                     fg=TEXT, bg=CARD)
        self._clarity_lbl.pack(side="left", padx=8)

        # 3D Surround slider
        s3 = tk.Frame(card_sliders, bg=CARD)
        s3.pack(fill="x", pady=(4, 2))
        tk.Label(s3, text="3D Spatial Space", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=16, anchor="w").pack(side="left")
        self._surround_slider = tk.Scale(s3, from_=0, to=100, orient="horizontal",
                                         variable=self._audio_surround_var,
                                         bg=CARD, fg=TEXT, troughcolor=BORDER,
                                         highlightthickness=0, length=180, showvalue=False)
        self._surround_slider.pack(side="left")
        self._surround_lbl = tk.Label(s3, text="70%", font=("Segoe UI", 8, "bold"),
                                      fg=TEXT, bg=CARD)
        self._surround_lbl.pack(side="left", padx=8)

    def _set_audio_preset(self, preset_key: str) -> None:
        self._audio_preset_var.set(preset_key)
        for k, btn in self._eq_buttons.items():
            if k == preset_key:
                btn.configure(bg=ACCENT, fg=TEXT)
            else:
                btn.configure(bg=BORDER, fg=TEXT_MUTED)

        if preset_key == "FPS Step Booster":
            self._audio_bass_var.set(20)
            self._audio_clarity_var.set(90)
            self._audio_surround_var.set(80)
        elif preset_key == "Gaming Surround":
            self._audio_bass_var.set(50)
            self._audio_clarity_var.set(70)
            self._audio_surround_var.set(95)
        elif preset_key == "Bass Boost":
            self._audio_bass_var.set(95)
            self._audio_clarity_var.set(40)
            self._audio_surround_var.set(40)
        elif preset_key == "Music / Vocal":
            self._audio_bass_var.set(60)
            self._audio_clarity_var.set(65)
            self._audio_surround_var.set(50)
        elif preset_key == "Flat / Neutral":
            self._audio_bass_var.set(0)
            self._audio_clarity_var.set(0)
            self._audio_surround_var.set(0)

        self._bass_lbl.configure(text=f"{self._audio_bass_var.get()}%")
        self._clarity_lbl.configure(text=f"{self._audio_clarity_var.get()}%")
        self._surround_lbl.configure(text=f"{self._audio_surround_var.get()}%")
        logger.info("Audio preset changed to: %s", preset_key)

    # ------------------------------------------------------------------
    # Bottom Status Bar (CustomRP inspired)
    # ------------------------------------------------------------------

    def _build_bottom_status_bar(self) -> None:
        sbar = tk.Frame(self._root, bg=CARD, padx=14, pady=6)
        sbar.pack(fill="x", side="bottom")

        self._sbar_devices_lbl = tk.Label(sbar, text="● Detecting devices...",
                                          font=("Segoe UI", 8),
                                          fg=TEXT_MUTED, bg=CARD)
        self._sbar_devices_lbl.pack(side="left")

        self._sbar_battery_lbl = tk.Label(sbar, text="",
                                          font=("Segoe UI", 8, "bold"),
                                          fg=GREEN, bg=CARD)
        self._sbar_battery_lbl.pack(side="right")

    # ------------------------------------------------------------------
    # Visibility & Refresh loop
    # ------------------------------------------------------------------

    def is_visible(self) -> bool:
        """Return True if dashboard window is currently open/visible."""
        return self._visible

    def show(self) -> None:
        if self._root is None:
            return
        self._visible = True
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()
        self.refresh()
        self._schedule_refresh()

    def hide(self) -> None:
        self._visible = False
        if self._refresh_job and self._root:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self._root:
            self._root.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def destroy(self) -> None:
        """Cleanly destroy window and cancel pending callbacks."""
        self.hide()
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

    def _schedule_refresh(self) -> None:
        if not self._visible or self._root is None:
            return
        self._refresh_job = self._root.after(3000, self._on_timer_refresh)

    def _on_timer_refresh(self) -> None:
        if self._visible:
            self.refresh()
            self._schedule_refresh()

    def scan_all(self) -> None:
        if self._on_scan:
            threading.Thread(target=self._on_scan, daemon=True, name="manual-scan").start()
        self.refresh()

    def refresh(self) -> None:
        """Update live telemetry for all components and the status bar."""
        if not self._root:
            return
        try:
            self._refresh_mouse()
            self._refresh_keyboard()
            self._refresh_headset()
            self._refresh_status_bar()
        except Exception as exc:
            logger.debug("Dashboard refresh error: %s", exc)

    def _refresh_mouse(self) -> None:
        if self._mouse is None:
            return
        st = self._mouse.get_status()
        online = st.get("online", False)
        conn_type = st.get("connection_type", "Disconnected")

        if online:
            self._mouse_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
        else:
            self._mouse_status_lbl.configure(text="● Disconnected", fg=RED)

        pct = st.get("battery_level")
        self._mouse_bat_bar.set_value(pct)
        self._mouse_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))

        v = st.get("battery_voltage")
        if v:
            self._mouse_volt_lbl.configure(text=f"({v/1000:.2f}V)")
        else:
            self._mouse_volt_lbl.configure(text="")

        dpi = st.get("current_dpi", 1200)
        self._mouse_dpi_val_lbl.configure(text=f"{dpi} DPI")
        for d, btn in self._dpi_buttons.items():
            btn.set_active(d == dpi)

    def _refresh_keyboard(self) -> None:
        if self._keyboard is None:
            return
        st = self._keyboard.get_status()
        connected = st.get("connected", False)
        conn_type = st.get("connection_type", "Disconnected")

        if connected:
            self._kb_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
        else:
            self._kb_status_lbl.configure(text="● Disconnected", fg=RED)

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

        if dongle:
            self._hs_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
        else:
            self._hs_status_lbl.configure(text="● Dongle Not Detected", fg=RED)

        pct = st.get("battery_estimate", 0)
        self._hs_bat_bar.set_value(pct)
        self._hs_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))

        hrs = st.get("usage_hours", 0.0)
        h = int(hrs)
        m = int((hrs - h) * 60)
        self._hs_usage_lbl.configure(text=f"Usage: {h}h {m:02d}m")

        vol = st.get("volume", 50)
        if self._hs_vol_var.get() != vol:
            self._hs_vol_var.set(vol)
            self._hs_vol_lbl.configure(text=f"{vol}%")

    def _refresh_status_bar(self) -> None:
        connected_count = 0
        batteries = []

        if self._mouse and self._mouse.get_status().get("online"):
            connected_count += 1
            b = self._mouse.get_status().get("battery_level")
            if b is not None:
                batteries.append(("Mouse", b))

        if self._keyboard and self._keyboard.get_status().get("connected"):
            connected_count += 1

        if self._headset and self._headset.get_status().get("dongle_connected"):
            connected_count += 1
            b = self._headset.get_status().get("battery_estimate")
            if b is not None:
                batteries.append(("Headset", b))

        # Status indicator
        if connected_count > 0:
            self._brand_dot.configure(fg=GREEN)
            self._sbar_devices_lbl.configure(
                text=f"● {connected_count} Device{'s' if connected_count > 1 else ''} Online",
                fg=GREEN
            )
        else:
            self._brand_dot.configure(fg=RED)
            self._sbar_devices_lbl.configure(text="● No devices connected", fg=RED)

        if batteries:
            dev_name, min_bat = min(batteries, key=lambda x: x[1])
            col = _battery_color(min_bat)
            self._sbar_battery_lbl.configure(text=f"🔋 Lowest: {dev_name} {min_bat}%", fg=col)
        else:
            self._sbar_battery_lbl.configure(text="")
